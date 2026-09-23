"""HTTP and WebSocket routers — FastAPI APIRouter instances."""

from app.routers.plivo_webhook import router as plivo_router
from app.routers.telephony import router as telephony_router

__all__ = ["plivo_router", "telephony_router"]
