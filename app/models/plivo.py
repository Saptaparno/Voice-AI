"""Plivo webhook / API data shapes — Pydantic models."""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound / hangup webhook payloads (Plivo POSTs form data)
# ---------------------------------------------------------------------------


class PlivoInboundRequest(BaseModel):
    """Form fields Plivo POSTs to the incoming-call webhook."""

    From: str = Field(default="", description="Caller E.164 number.")
    To: str = Field(default="", description="Called Plivo DID.")
    CallUUID: str = Field(default="", description="Unique ID for this call leg.")
    CallStatus: str = Field(
        default="",
        description="ringing | answered | completed | ...",
    )
    CallerName: str = Field(
        default="",
        description="CNAM display name if available.",
    )
    Direction: str = Field(
        default="inbound",
        description="inbound | outbound",
    )


class PlivoHangupRequest(BaseModel):
    """Form fields Plivo POSTs to the hangup webhook."""

    CallUUID: str = Field(default="", description="Plivo call leg UUID.")
    HangupCause: str = Field(
        default="",
        description="NORMAL_CLEARING | USER_BUSY | ...",
    )
    Duration: str = Field(
        default="",
        description="Call duration in seconds as string.",
    )


# ---------------------------------------------------------------------------
# Outbound call
# ---------------------------------------------------------------------------


class OutboundCallRequest(BaseModel):
    """Body of POST /call/outbound."""

    to: str = Field(..., description="Destination E.164 number to dial.")


# ---------------------------------------------------------------------------
# Internal: PlivoCallRequest for plivo_client.py
# ---------------------------------------------------------------------------


class PlivoCallRequest(BaseModel):
    """Payload for initiating an outbound call via the Plivo Calls API."""

    from_number: str = Field(
        ...,
        description="Plivo DID the call originates from (E.164).",
    )
    to_number: str = Field(
        ...,
        description="Destination E.164 number.",
    )
    answer_url: str = Field(
        ...,
        description="URL Plivo fetches when the call is answered to get XML instructions.",
    )
    answer_method: str = Field(
        default="GET",
        description="HTTP method for answer_url (GET or POST).",
    )
    hangup_url: str = Field(
        default="",
        description="Optional URL Plivo POSTs call metadata to on hangup.",
    )
    sip_headers: dict | None = Field(
        default=None,
        description="Optional custom SIP headers forwarded to answer_url.",
    )


class OutboundCallResponse(BaseModel):
    """Response from POST /call/outbound (mirrors Plivo's API shape)."""

    request_uuid: str = Field(..., description="Plivo's request UUID for this call.")
    api_id: str = Field(..., description="Plivo API request ID.")
    message: str = Field(default="")
