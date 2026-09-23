"""Transcript shape returned by the STT service — Pydantic model."""

from pydantic import BaseModel, Field


class Transcript(BaseModel):
    """A transcription result from Saaras STT.

    Attributes:
        text: The transcribed text.
        language_code: BCP-47 language code (e.g. "en-IN"), or None.
        confidence: Confidence score 0.0–1.0, or None.
    """

    text: str = ""
    language_code: str | None = Field(default=None, description="BCP-47 language code.")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0–1.0.",
    )
