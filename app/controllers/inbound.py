"""Inbound call controller — handles Plivo's incoming-call webhook."""

import os

from app.models import InboundSchema


class InboundController:
    """Handles the Plivo incoming-call webhook.

    Takes a validated ``InboundSchema``, decides what XML to return,
    and hands the call off to the WebSocket.

    The caller (Plivo) sends this webhook twice:
    1. ``CallStatus=ringing`` — caller is ringing the DID.
    2. ``CallStatus=answered`` — DID was answered (by you or an app).

    We only return ``<Stream>`` on the answered event so Plivo opens
    the WebSocket and the TelephonyController takes over.
    """

    def __init__(self, ws_base_url: str | None = None):
        """
        Args:
            ws_base_url: Public WebSocket base URL. If None, reads from
                ``PLIVO_PUBLIC_BASE_URL`` env var.
        """
        self._ws_base_url = ws_base_url or os.getenv(
            "PLIVO_PUBLIC_BASE_URL", ""
        ).strip()

    def build_stream_xml(self, call: InboundSchema) -> str:
        """Build the Plivo <Stream> XML for the given inbound call.

        Returns the XML string Plivo expects — including the <Response> wrapper.
        """
        ws_url = self._build_ws_url()
        return (
            "<Response>"
            "<Stream bidirectional=\"true\" "
            "keepCallAlive=\"true\" "
            "audioTrack=\"inbound\" "
            "contentType=\"audio/x-l16;rate=16000\" "
            f"streamTimeout=\"7200\">"
            f"{ws_url}"
            "</Stream>"
            "</Response>"
        )

    def handle(self, call: InboundSchema) -> str:
        """Return the appropriate XML for this call.

        Always returns ``<Stream>`` immediately — Plivo opens the WebSocket,
        the TelephonyController starts, and the greeting is spoken via TTS
        over the WebSocket.  No blocking ``<Speak>`` elements.
        """
        return self.build_stream_xml(call)

    def _build_ws_url(self) -> str:
        """Derive the WebSocket URL.

        Priority:
        1. ``PLIVO_PUBLIC_BASE_URL`` env var (for ngrok/production).
        2. ``Host`` header from Plivo (only if available at call time).
        3. ``localhost`` fallback (dev only).
        """
        if self._ws_base_url:
            base = self._ws_base_url.rstrip("/")
            # Convert https:// → wss://, http:// → ws://
            if base.startswith("https://"):
                base = "wss://" + base[len("https://"):]
            elif base.startswith("http://"):
                base = "ws://" + base[len("http://"):]
            return f"{base}/stream"

        # Fallback — use a placeholder; caller must provide ws_base_url
        return "ws://localhost:5000/stream"
