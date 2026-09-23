"""Credentials — Pydantic models."""

from pydantic import BaseModel, Field


class SarvamCredentials(BaseModel):
    """Sarvam API credentials — loaded once at startup."""

    api_key: str = Field(..., description="Sarvam API key.")
    subscription_headers: dict = Field(
        default_factory=dict,
        description="Headers for STT/TTS REST endpoints.",
    )
    bearer_headers: dict = Field(
        default_factory=dict,
        description="Headers for OpenAI-compatible chat endpoint.",
    )


class PlivoCredentials(BaseModel):
    """Plivo API credentials — loaded once at startup."""

    auth_id: str = Field(..., description="Plivo Auth ID.")
    auth_token: str = Field(..., description="Plivo Auth Token.")
