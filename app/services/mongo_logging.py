"""Best-effort persistence for calls, chat history, and pipeline metrics."""

from datetime import datetime, timezone
import os
from threading import Lock

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - optional dependency during local development
    MongoClient = None


class MongoLogger:
    def __init__(self):
        self._client = None
        self._collection = None
        self._lock = Lock()

    def _get_collection(self):
        url = os.getenv("MONGO_URL", "").strip()
        if not url or MongoClient is None:
            return None
        with self._lock:
            if self._collection is None:
                self._client = MongoClient(url, serverSelectionTimeoutMS=3000)
                database = os.getenv("MONGO_DB", "voice_ai")
                collection = os.getenv("MONGO_COLLECTION", "calls")
                self._collection = self._client[database][collection]
        return self._collection

    def start_call(self, call_uuid: str, from_number: str, to_number: str) -> None:
        self._write({"_id": call_uuid, "call_uuid": call_uuid, "from_number": from_number,
                     "to_number": to_number, "started_at": datetime.now(timezone.utc),
                     "turns": [], "metrics": {"turn_count": 0}})

    def add_turn(self, call_uuid: str, turn: dict) -> None:
        collection = self._get_collection()
        if collection is None:
            return
        try:
            collection.update_one({"_id": call_uuid}, {"$push": {"turns": turn},
                "$inc": {"metrics.turn_count": 1}})
        except Exception as exc:
            print(f"[Mongo] turn write failed: {type(exc).__name__}: {exc}")

    def finish_call(self, call_uuid: str, metrics: dict, error: str | None = None) -> None:
        update = {"ended_at": datetime.now(timezone.utc), "metrics": metrics}
        if error:
            update["error"] = error
        collection = self._get_collection()
        if collection is None:
            return
        try:
            collection.update_one({"_id": call_uuid}, {"$set": update}, upsert=True)
        except Exception as exc:
            print(f"[Mongo] call write failed: {type(exc).__name__}: {exc}")

    def add_hangup(self, call_uuid: str, payload: dict) -> None:
        """Attach the complete Plivo hangup webhook payload to the call."""
        collection = self._get_collection()
        if collection is None or not call_uuid:
            return
        try:
            collection.update_one({"_id": call_uuid}, {"$set": {
                "hangup": payload, "plivo_duration_seconds": payload.get("Duration"),
                "plivo_bill_duration_seconds": payload.get("BillDuration"),
                "plivo_total_cost": payload.get("TotalCost"),
                "metrics.cost_breakup.telephony_plivo.provider_cost": _number(payload.get("TotalCost")),
                "metrics.cost_breakup.telephony_plivo.currency": "INR",
            }}, upsert=True)
            doc = collection.find_one({"_id": call_uuid}, {"metrics.cost_breakup": 1}) or {}
            breakup = (doc.get("metrics") or {}).get("cost_breakup") or {}
            if breakup:
                provider_cost = _number(payload.get("TotalCost")) or 0.0
                currency = os.getenv("PLIVO_PROVIDER_CURRENCY", "USD").upper()
                conversion = 1.0 if currency == "INR" else float(os.getenv("PLIVO_USD_TO_INR", "83.5"))
                telephony = provider_cost * conversion
                collection.update_one({"_id": call_uuid}, {"$set": {
                    "metrics.cost_breakup.telephony_plivo.cost_inr": round(telephony, 8)
                }})
                service_total = sum((_number((breakup.get(k) or {}).get("cost_inr")) or 0.0)
                                    for k in ("saaras_stt", "bulbul_tts", "sarvam_105b"))
                collection.update_one({"_id": call_uuid}, {"$set": {
                    "metrics.cost_breakup.total_cost_inr": round(service_total + telephony, 8)
                }})
        except Exception as exc:
            print(f"[Mongo] hangup write failed: {type(exc).__name__}: {exc}")

    def _write(self, document: dict) -> None:
        collection = self._get_collection()
        if collection is None:
            return
        try:
            collection.replace_one({"_id": document["_id"]}, document, upsert=True)
        except Exception as exc:
            print(f"[Mongo] call write failed: {type(exc).__name__}: {exc}")


mongo_logger = MongoLogger()


def _number(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
