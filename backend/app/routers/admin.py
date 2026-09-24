"""Admin endpoints — sadece admin role.

  GET    /api/admin/predictions/pending  → settled olmamış tahminler
  POST   /api/admin/predictions/{id}/settle  → manuel settle (force final score)
  POST   /api/admin/predictions/{id}/cancel  → tahmin iptal
  GET    /api/admin/users                → kullanıcı listesi
  POST   /api/admin/users/{id}/ban       → kullanıcıyı banla
  POST   /api/admin/users/{id}/unban     → banı kaldır
  GET    /api/admin/chat/messages        → son 200 mesaj
  DELETE /api/admin/chat/clear           → tüm chat'i sil
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.database import get_db
from ..services.settlement import _calc_points
from .auth import current_user_or_401  # type: ignore

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(request: Request) -> dict:
    user = await current_user_or_401(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca admin")
    return user


# ============== PREDICTIONS ==============
@router.get("/predictions/pending")
async def pending_predictions(request: Request, limit: int = 100):
    await _require_admin(request)
    db = get_db()
    if db is None:
        return {"items": []}
    cursor = db.predictions.find({"settled": {"$ne": True}}).sort("submitted_at", -1).limit(limit)
    items = []
    async for p in cursor:
        items.append({
            "id": p.get("id"),
            "user_id": p.get("user_id"),
            "user_name": p.get("user_name", ""),
            "match_id": p.get("match_id"),
            "team1": p.get("team1", ""),
            "team2": p.get("team2", ""),
            "kickoff": p.get("kickoff", ""),
            "score1": p.get("score1"), "score2": p.get("score2"),
            "submitted_at": (p.get("submitted_at") or datetime.now(timezone.utc)).isoformat(),
        })
    return {"items": items}


class ManualSettleBody(BaseModel):
    final_home: int
    final_away: int


@router.post("/predictions/{prediction_id}/settle")
async def manual_settle(prediction_id: str, body: ManualSettleBody, request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    pred = await db.predictions.find_one({"id": prediction_id})
    if not pred:
        raise HTTPException(status_code=404, detail="Tahmin bulunamadı")
    p1, p2 = int(pred.get("score1", 0)), int(pred.get("score2", 0))
    a1, a2 = int(body.final_home), int(body.final_away)
    points = _calc_points(p1, p2, a1, a2)
    await db.predictions.update_one(
        {"id": prediction_id},
        {"$set": {
            "settled": True,
            "settled_at": datetime.now(timezone.utc),
            "final_score": [a1, a2],
            "points": points,
            "settled_by": "admin",
        }},
    )
    return {"ok": True, "points": points, "final_score": [a1, a2]}


@router.post("/predictions/{prediction_id}/cancel")
async def cancel_prediction(prediction_id: str, request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.predictions.delete_one({"id": prediction_id})
    return {"ok": True, "deleted": r.deleted_count}


# ============== USERS ==============
@router.get("/users")
async def list_users(request: Request, limit: int = 100, role: Optional[str] = None):
    await _require_admin(request)
    db = get_db()
    if db is None:
        return {"items": []}
    q = {}
    if role:
        q["role"] = role
    cursor = db.users.find(q).sort("created_at", -1).limit(limit)
    items = []
    async for u in cursor:
        items.append({
            "id": u.get("id"),
            "email": u.get("email"),
            "name": u.get("name", ""),
            "role": u.get("role", "user"),
            "provider": u.get("provider", "local"),
            "banned": bool(u.get("banned", False)),
            "test": bool(u.get("test", False)),
            "created_at": (u.get("created_at") or datetime.now(timezone.utc)).isoformat(),
        })
    return {"items": items}


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: str, request: Request):
    admin = await _require_admin(request)
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Kendini banlayamazsın")
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.users.update_one({"id": user_id}, {"$set": {"banned": True}})
    return {"ok": True, "modified": r.modified_count}


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: str, request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.users.update_one({"id": user_id}, {"$set": {"banned": False}})
    return {"ok": True, "modified": r.modified_count}


# ============== CHAT ==============
@router.get("/chat/messages")
async def admin_chat_list(request: Request, limit: int = 200):
    await _require_admin(request)
    db = get_db()
    if db is None:
        return {"items": []}
    cursor = db.chat_messages.find({}).sort("ts", -1).limit(limit)
    items = []
    async for m in cursor:
        items.append({
            "id": m.get("id"),
            "user_id": m.get("user_id", ""),
            "name": m.get("name", "Anonim"),
            "role": m.get("role", "user"),
            "text": m.get("text", ""),
            "ts": (m.get("ts") or datetime.now(timezone.utc)).isoformat(),
        })
    return {"items": items}


@router.delete("/chat/clear")
async def clear_chat(request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.chat_messages.delete_many({})
    return {"ok": True, "deleted": r.deleted_count}


# ============== SPONSOR CLICKS ==============
@router.get("/sponsors/clicks")
async def sponsor_clicks(request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        return {"items": [], "total": 0}
    cursor = db.sponsor_clicks.find({}).sort("count", -1)
    items = []
    total = 0
    async for s in cursor:
        cnt = int(s.get("count", 0))
        total += cnt
        last = s.get("last_click_at")
        items.append({
            "sponsor_id": s.get("sponsor_id"),
            "name": s.get("name", s.get("sponsor_id", "")),
            "count": cnt,
            "last_click_at": last.isoformat() if last else None,
        })
    return {"items": items, "total": total}


# ============== STATS / DASHBOARD ==============
@router.get("/stats")
async def admin_stats(request: Request):
    await _require_admin(request)
    db = get_db()
    if db is None:
        return {}
    total_users = await db.users.count_documents({})
    banned = await db.users.count_documents({"banned": True})
    total_predictions = await db.predictions.count_documents({})
    pending = await db.predictions.count_documents({"settled": {"$ne": True}})
    settled = total_predictions - pending
    total_msgs = await db.chat_messages.count_documents({})
    return {
        "users": {"total": total_users, "banned": banned},
        "predictions": {"total": total_predictions, "pending": pending, "settled": settled},
        "chat": {"messages_24h": total_msgs},
    }
