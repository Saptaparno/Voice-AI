"""Hangup controller — handles Plivo's call-ended webhook."""

from app.models import HangupSchema
from app.services.mongo_logging import mongo_logger


class HangupController:
    """Handles Plivo's hangup webhook.

    Logs call metadata after a call ends.  Extend to persist records,
    send analytics events, etc.
    """

    def handle(self, event: HangupSchema, payload: dict | None = None) -> None:
        """Process a hangup event.

        Args:
            event: Validated hangup data from Plivo.
        """
        print(
            f"[Hangup] UUID={event.CallUUID} "
            f"Cause={event.HangupCause} Duration={event.Duration}s"
        )
        mongo_logger.add_hangup(event.CallUUID, payload or event.model_dump())
