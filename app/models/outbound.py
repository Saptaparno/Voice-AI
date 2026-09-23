"""Pydantic schemas for outbound call initiation."""

from pydantic import BaseModel, Field


class OutboundCallRequest(BaseModel):
    """Body of POST /call/outbound."""

    to: str = Field(
        ...,
        description="Destination E.164 number to dial (e.g. +919876543210).",
    )


class OutboundCallResponse(BaseModel):
    """Response from POST /call/outbound (mirrors Plivo's API)."""

    request_uuid: str = Field(..., description="Plivo's request UUID for this call.")
    api_id: str = Field(..., description="Plivo API request ID.")
    message: str = Field(default="call queued", description="Status message from Plivo.")
