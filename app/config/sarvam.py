"""Sarvam API credential helpers."""

from app.config import (
    SARVAM_API_KEY,
    SARVAM_SUBSCRIPTION_KEY,
    SARVAM_BASE_URL,
)
from app.models import SarvamCredentials


def load_sarvam_credentials() -> SarvamCredentials:
    """Build the two header-sets Sarvam APIs require.

    The ``subscription_headers`` dict is used for the STT and TTS REST
    endpoints.  The ``bearer_headers`` dict is used for the OpenAI-compatible
    chat endpoint.

    Raises:
        RuntimeError: if ``SARVAM_API_KEY`` is not set.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError(
            "SARVAM_API_KEY is not set.  Copy .env.example to .env "
            "and fill in your key."
        )

    subscription_headers = {
        "api-subscription-key": SARVAM_API_KEY,
    }

    bearer_headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "Content-Type": "application/json",
    }

    return SarvamCredentials(
        api_key=SARVAM_API_KEY,
        subscription_headers=subscription_headers,
        bearer_headers=bearer_headers,
    )


__all__ = ["load_sarvam_credentials", "SarvamCredentials"]
