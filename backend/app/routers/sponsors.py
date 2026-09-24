"""Sponsor tıklama sayacı.

  POST /api/sponsors/click  → public, sponsor tıklamasını sayar
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel

from ..core.database import get_db

router = APIRouter(prefix="/api/sponsors", tags=["sponsors"])


class ClickBody(BaseModel):
    sponsor_id: str
    name: str = ""


@router.post("/click")
async def sponsor_click(body: ClickBody):
    db = get_db()
    if db is None:
        return {"ok": False}
    sid = body.sponsor_id.strip()[:64]
    if not sid:
        return {"ok": False}
    await db.sponsor_clicks.update_one(
        {"sponsor_id": sid},
        {
            "$inc": {"count": 1},
            "$set": {
                "name": (body.name or sid)[:100],
                "last_click_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )
    return {"ok": True}
