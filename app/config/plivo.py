"""Plivo credential helpers."""

from app.config import PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN
from app.models import PlivoCredentials


def load_plivo_credentials() -> PlivoCredentials:
    """Return Plivo credentials loaded from the environment.

    Raises:
        RuntimeError: if ``PLIVO_AUTH_ID`` or ``PLIVO_AUTH_TOKEN`` are not set.
    """
    if not PLIVO_AUTH_ID or PLIVO_AUTH_ID == "YOUR_PLIVO_AUTH_ID_HERE":
        raise RuntimeError(
            "PLIVO_AUTH_ID is not set.  Copy .env.example to .env "
            "and fill in your Plivo Auth ID."
        )
    if not PLIVO_AUTH_TOKEN or PLIVO_AUTH_TOKEN == "YOUR_PLIVO_AUTH_TOKEN_HERE":
        raise RuntimeError(
            "PLIVO_AUTH_TOKEN is not set.  Copy .env.example to .env "
            "and fill in your Plivo Auth Token."
        )
    return PlivoCredentials(auth_id=PLIVO_AUTH_ID, auth_token=PLIVO_AUTH_TOKEN)


__all__ = ["load_plivo_credentials", "PlivoCredentials"]
