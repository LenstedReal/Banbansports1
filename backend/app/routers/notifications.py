"""Notifications endpoint — log notification events to Mongo for history."""
from datetime import datetime, timezone
from fastapi import APIRouter
import logging

from ..core.database import get_db

logger = logging.getLogger("banbansports.notifications")
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.post("/log")
async def log_notification(payload: dict):
    db = get_db()
    if db is None:
        return {"ok": False, "reason": "db_unavailable"}
    try:
        await db.notifications.insert_one({**payload, "ts": datetime.now(timezone.utc)})
        return {"ok": True}
    except Exception as e:
        logger.warning(f"notif log fail: {e}")
        return {"ok": False, "reason": str(e)}
