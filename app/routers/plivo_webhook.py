"""Plivo webhook router — maps HTTP endpoints to controllers."""

import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.controllers import InboundController, HangupController, OutboundController
from app.models import InboundSchema, HangupSchema, OutboundCallRequest


router = APIRouter(prefix="", tags=["plivo"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xml_response(xml: str) -> Response:
    """Return a Plivo-compatible XML response."""
    return Response(content=xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# GET /debug/xml — preview the XML Plivo will receive
# ---------------------------------------------------------------------------


@router.get("/debug/xml", include_in_schema=False)
async def debug_xml(request: Request) -> Response:
    """Preview the exact XML returned to Plivo for an inbound call."""
    inbound = InboundController()
    xml = inbound.build_stream_xml(InboundSchema(CallStatus="answered"))
    return _xml_response(xml)


# ---------------------------------------------------------------------------
# POST /call/incoming — inbound call webhook
# ---------------------------------------------------------------------------


@router.post(
    os.getenv("PLIVO_INBOUND_ENDPOINT", "/call/incoming"),
    summary="Plivo incoming-call webhook",
)
async def inbound_call(request: Request) -> Response:
    """Handle Plivo's incoming-call webhook.

    Plivo POSTs here when someone dials your Plivo number.
    Returns <Stream> XML so Plivo opens the WebSocket and the
    TelephonyController takes over the call.
    """
    form = await request.form()
    call = InboundSchema(
        From=form.get("From", ""),
        To=form.get("To", ""),
        CallUUID=form.get("CallUUID", ""),
        CallStatus=form.get("CallStatus", ""),
        CallerName=form.get("CallerName", ""),
        Direction=form.get("Direction", "inbound"),
    )

    print(
        f"[Inbound] From={call.From} To={call.To} "
        f"UUID={call.CallUUID} Status={call.CallStatus}"
    )
    print(f"[Inbound raw] {dict(form)}")

    controller = InboundController()
    xml = controller.handle(call)
    return _xml_response(xml)


# ---------------------------------------------------------------------------
# POST /call/hangup — hangup webhook
# ---------------------------------------------------------------------------


@router.post(
    os.getenv("PLIVO_HANGUP_ENDPOINT", "/call/hangup"),
    summary="Plivo call-hangup webhook",
)
async def hangup(request: Request) -> PlainTextResponse:
    """Handle Plivo's hangup webhook."""
    form = await request.form()
    # AnswerTime tells us whether the call was ever actually answered —
    # an unanswered call has no inbound media path.
    print(f"[Hangup raw] {dict(form)}")
    event = HangupSchema(
        CallUUID=form.get("CallUUID", ""),
        HangupCause=form.get("HangupCause", ""),
        Duration=form.get("Duration", ""),
    )

    controller = HangupController()
    controller.handle(event, dict(form))
    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# POST /call/outbound — trigger outbound call
# ---------------------------------------------------------------------------


@router.post(
    "/call/outbound",
    summary="Trigger an outbound call",
)
async def outbound(request: OutboundCallRequest) -> dict:
    """POST /call/outbound with JSON body ``{"to": "+919876543210"}``."""
    controller = OutboundController()
    response = controller.handle(request)
    return response.model_dump()
