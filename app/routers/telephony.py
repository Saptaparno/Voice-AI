"""FastAPI WebSocket router for Plivo audio streaming.

Exports:
    router  — FastAPI APIRouter (include in your app with app.include_router(router))
    app     — Standalone FastAPI app for ``uvicorn app.routers.telephony:app``
"""

import sys
from pathlib import Path

# Allow `python app/routers/telephony.py` to resolve `app` as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import PlainTextResponse

from app.config import SERVER_HOST, SERVER_PORT

router = APIRouter(tags=["telephony"])


# ---------------------------------------------------------------------------
# WebSocket audio endpoint
# ---------------------------------------------------------------------------


@router.websocket("/stream")
async def stream(
    ws: WebSocket,
    call_uuid: str = Query(default="unknown"),
    from_: str = Query(default="", alias="from"),
    to: str = Query(default=""),
):
    """Plivo WebSocket audio endpoint.

    Plivo opens a bidirectional WebSocket to this URL after answering a call.
    Events arrive as JSON text frames; the TelephonyController handles the
    listen → think → speak loop and streams TTS audio back as JSON playAudio
    frames over the same connection.
    """
    from app.controllers.telephony_controller import TelephonyController

    await ws.accept()
    print(f"[WS] Connected call_uuid={call_uuid} from={from_} to={to}")

    controller = TelephonyController(
        call_uuid=call_uuid,
        from_number=from_,
        to_number=to,
    )

    # Single reader loop — passes every incoming frame to the controller.
    async def read_incoming() -> None:
        try:
            while True:
                raw = await ws.receive()
                if raw["type"] == "websocket.disconnect":
                    controller.stop()
                    break
                if raw["type"] != "websocket.receive":
                    continue

                if "text" in raw:
                    try:
                        event = json.loads(raw["text"])
                    except json.JSONDecodeError:
                        continue
                    # A bug in one handler must not kill the reader: if this
                    # task dies the call goes silently deaf for its remainder.
                    try:
                        controller.on_ws_event(event)
                    except Exception as e:
                        print(f"[WS reader] handler error: {type(e).__name__}: {e}")
                elif "bytes" in raw:
                    # Binary audio frame — queue for VAD.
                    try:
                        controller._audio_queue.put_nowait(raw["bytes"])
                    except asyncio.QueueFull:
                        pass
        except WebSocketDisconnect:
            controller.stop()
        except Exception as e:
            print(f"[WS reader] fatal: {type(e).__name__}: {e}")
            controller.stop()

    reader_task = asyncio.create_task(read_incoming())

    try:
        await controller.run_async(ws)
    except WebSocketDisconnect:
        print(f"[WS] Plivo disconnected call_uuid={call_uuid}")
    except Exception as e:
        print(f"[WS] Error on {call_uuid}: {type(e).__name__}: {e}")
    finally:
        controller.finish_logging()
        controller.stop()
        reader_task.cancel()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health", response_class=PlainTextResponse)
async def health():
    """Basic health endpoint for load balancers and uptime checks."""
    return "ok"


# ---------------------------------------------------------------------------
# Standalone FastAPI app for ``uvicorn app.routers.telephony:app``
# ---------------------------------------------------------------------------

app: Any = None   # lazily created below


def _get_app():
    global app
    if app is not None:
        return app

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.routers.plivo_webhook import router as plivo_router

    _app = FastAPI(
        title="Voice AI – Telephony Server",
        description="Plivo webhook + WebSocket server for the Sarvam voice AI pipeline.",
    )
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _app.include_router(plivo_router)
    _app.include_router(router)
    app = _app
    return app


# Satisfy uvicorn's module-level ``app`` convention when run directly.
app = _get_app()


if __name__ == "__main__":
    import uvicorn
    from app.config import SERVER_HOST, SERVER_PORT

    uvicorn.run(
        "app.routers.telephony:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )
