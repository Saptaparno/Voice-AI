"""Outbound call controller — initiates calls via the Plivo API."""

import os

from app.config import PLIVO_CALLER_NUMBER, SERVER_PORT
from app.models import OutboundCallRequest, OutboundCallResponse, PlivoCallRequest
from app.services.plivo_client import make_call


class OutboundController:
    """Initiates an outbound call through Plivo.

    The Plivo number dials ``request.to``.  When the destination picks up,
    Plivo hits the inbound webhook — the same WebSocket flow as an inbound call.
    """

    def handle(self, request: OutboundCallRequest) -> OutboundCallResponse:
        """Initiate an outbound call.

        Args:
            request: Validated ``OutboundCallRequest`` Pydantic model.

        Returns:
            ``OutboundCallResponse`` from Plivo.

        Raises:
            ValueError: if ``PLIVO_CALLER_NUMBER`` is not configured.
        """
        if not PLIVO_CALLER_NUMBER:
            raise ValueError(
                "PLIVO_CALLER_NUMBER is not set. Set it to your Plivo DID in .env."
            )

        if not PLIVO_CALLER_NUMBER.startswith("+"):
            raise ValueError(
                "PLIVO_CALLER_NUMBER must be in E.164 format (e.g. +14155551234)."
            )

        to_number = request.to.strip()
        if not to_number:
            raise ValueError('"to" is required.')

        answer_url = self._build_answer_url()

        call_request = PlivoCallRequest(
            from_number=PLIVO_CALLER_NUMBER,
            to_number=to_number,
            answer_url=answer_url,
            answer_method="POST",
        )

        result = make_call(call_request)

        return OutboundCallResponse(
            request_uuid=result.get("request_uuid", ""),
            api_id=result.get("api_id", ""),
            message=result.get("message", "call queued"),
        )

    def _build_answer_url(self) -> str:
        base = os.getenv("PLIVO_PUBLIC_BASE_URL", "").strip()
        if base:
            base = base.rstrip("/")
        else:
            base = f"http://localhost:{SERVER_PORT}"

        endpoint = os.getenv("PLIVO_INBOUND_ENDPOINT", "/call/incoming")
        return f"{base}{endpoint}"
