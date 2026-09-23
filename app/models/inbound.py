"""Pydantic schema for Plivo's incoming-call webhook POST."""

from pydantic import BaseModel, Field


class InboundSchema(BaseModel):
    """Fields Plivo POSTs to the incoming-call webhook.

    This schema is used both as input to the inbound controller and
    to document the exact shape of Plivo's form payload.
    """

    From: str = Field(default="", description="Caller E.164 number.")
    To: str = Field(default="", description="Called Plivo DID.")
    CallUUID: str = Field(default="", description="Unique ID for this call leg.")
    CallStatus: str = Field(
        default="",
        description="ringing | answered | completed | ...",
    )
    CallerName: str = Field(default="", description="CNAM display name.")
    Direction: str = Field(default="inbound", description="inbound | outbound.")
