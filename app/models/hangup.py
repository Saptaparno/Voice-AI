"""Pydantic schema for Plivo's hangup webhook POST."""

from pydantic import BaseModel, Field


class HangupSchema(BaseModel):
    """Fields Plivo POSTs to the hangup webhook."""

    CallUUID: str = Field(default="", description="Plivo call leg UUID.")
    HangupCause: str = Field(
        default="",
        description="NORMAL_CLEARING | USER_BUSY | CALL_REJECTED | ...",
    )
    Duration: str = Field(default="", description="Call duration in seconds.")
