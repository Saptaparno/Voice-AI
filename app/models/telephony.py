"""Pydantic schema for a telephony call context (WebSocket metadata)."""

from pydantic import BaseModel, Field


class CallContext(BaseModel):
    """Metadata for an active telephony call (from Plivo WebSocket query params)."""

    call_uuid: str = Field(default="unknown", description="Plivo's unique call identifier.")
    from_number: str = Field(default="", description="Caller E.164 number.")
    to_number: str = Field(default="", description="Called Plivo DID.")
