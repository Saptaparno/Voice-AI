"""FastAPI application entry point — Plivo telephony server."""

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
# Allow `python app/main.py` to resolve `app` as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.plivo_webhook import router as plivo_router
from app.routers.telephony import router as telephony_router


app = FastAPI(
    title="Voice AI",
    description="Sarvam-powered voice AI assistant with Plivo telephony.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plivo_router)
app.include_router(telephony_router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Voice AI",
        "docs": "/docs",
        "telephony": {
            "inbound_webhook": "/call/incoming",
            "hangup_webhook":  "/call/hangup",
            "outbound":        "/call/outbound",
            "websocket":        "/stream",
            "health":           "/health",
        },
    }
if __name__ == "__main__":
    import uvicorn
    from app.config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)