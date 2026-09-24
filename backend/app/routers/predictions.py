"""Prediction game — submit + leaderboard + settlement when match finishes."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.database import get_db
from ..services.livescore import fetch_live_scores
from .auth import current_user_or_401, _public_user  # type: ignore

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class SubmitBody(BaseModel):
    match_id: str
    score1: int
    score2: int


def _match_id(team1: str, team2: str, kickoff: str) -> str:
    """Deterministic match id from teams + kickoff timestamp prefix."""
    return f"{team1}__{team2}__{kickoff[:16]}".replace(' ', '_')


@router.get("/open")
async def open_matches() -> dict:
    """Open predictable matches = NS (not started) within next 36h."""
    top = await fetch_live_scores(top_n=10)
    if not top or not top.get("matches"):
        return {"items": []}
    items = []
    now = datetime.now(timezone.utc)
    for m in top["matches"]:
        status = (m.get("status") or "").upper()
        # Only accept matches with kickoff time (NS / Today / Tomorrow)
        if "BUGÜN" in status or "YARIN" in status or m.get("score1") is None:
            kickoff_iso = m.get("timestamp") or now.isoformat()
            # If status has HH:MM, attach to today/tomorrow
            try:
                if "BUGÜN" in status:
                    parts = status.split()
                    if len(parts) >= 2 and ":" in parts[-1]:
                        h, mn = parts[-1].split(":")
                        ko = now.replace(hour=int(h), minute=int(mn), second=0, microsecond=0)
                        kickoff_iso = ko.isoformat()
                elif "YARIN" in status:
                    parts = status.split()
                    if len(parts) >= 2 and ":" in parts[-1]:
                        h, mn = parts[-1].split(":")
                        ko = (now + timedelta(days=1)).replace(hour=int(h), minute=int(mn), second=0, microsecond=0)
                        kickoff_iso = ko.isoformat()
            except Exception:
                pass
            mid = _match_id(m["team1"], m["team2"], kickoff_iso)
            items.append({
                "id": mid,
                "team1": m["team1"], "team2": m["team2"],
                "league": m.get("league", ""),
                "kickoff": kickoff_iso,
                "status_label": m.get("status", ""),
                "score1": None, "score2": None,
                "status": "open",
            })
    return {"items": items[:8]}


@router.post("/submit")
async def submit(body: SubmitBody, request: Request):
    user = await current_user_or_401(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    if not (0 <= body.score1 <= 20) or not (0 <= body.score2 <= 20):
        return {"ok": False, "error": "Geçersiz skor"}

    # match_id format: "team1__team2__YYYY-MM-DDTHH:MM" → split for settlement.
    team1 = team2 = ""
    kickoff_iso = ""
    parts = body.match_id.split("__")
    if len(parts) >= 3:
        team1 = parts[0].replace("_", " ").strip()
        team2 = parts[1].replace("_", " ").strip()
        kickoff_iso = parts[2]
    # YYYYMMDD prefix — settlement loop bunu kullanıyor.
    kickoff_date = ""
    if kickoff_iso and len(kickoff_iso) >= 10:
        kickoff_date = kickoff_iso[:10].replace("-", "")

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "match_id": body.match_id,
        "team1": team1,
        "team2": team2,
        "kickoff": kickoff_iso,
        "kickoff_date": kickoff_date,
        "score1": int(body.score1),
        "score2": int(body.score2),
        "submitted_at": datetime.now(timezone.utc),
        "settled": False,
        "points": 0,
        "final_score": None,
    }
    try:
        await db.predictions.update_one(
            {"user_id": user["id"], "match_id": body.match_id},
            {"$set": doc}, upsert=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"DB hata: {e}"}
    return {"ok": True}


@router.get("/me")
async def my_predictions(request: Request):
    user = await current_user_or_401(request)
    db = get_db()
    if db is None:
        return {"items": []}
    cursor = db.predictions.find({"user_id": user["id"]}).sort("submitted_at", -1).limit(50)
    items: List[dict] = []
    async for p in cursor:
        items.append({
            "id": p.get("id"),
            "match_id": p.get("match_id"),
            "team1": p.get("team1", ""),
            "team2": p.get("team2", ""),
            "score1": p.get("score1"), "score2": p.get("score2"),
            "final_score": p.get("final_score"),
            "settled": bool(p.get("settled")),
            "points": int(p.get("points") or 0),
            "submitted_at": (p.get("submitted_at") or datetime.now(timezone.utc)).isoformat(),
        })
    return {"items": items}


@router.get("/match/{match_id}")
async def my_prediction_for_match(match_id: str, request: Request):
    """Tek bir maç için kullanıcının tahminini döner — MatchStatsModal rozet için."""
    user = await current_user_or_401(request)
    db = get_db()
    if db is None:
        return {"prediction": None}
    p = await db.predictions.find_one({"user_id": user["id"], "match_id": match_id})
    if not p:
        return {"prediction": None}
    return {"prediction": {
        "score1": p.get("score1"), "score2": p.get("score2"),
        "final_score": p.get("final_score"),
        "settled": bool(p.get("settled")),
        "points": int(p.get("points") or 0),
        "submitted_at": (p.get("submitted_at") or datetime.now(timezone.utc)).isoformat(),
    }}


@router.get("/streak")
async def my_streak(request: Request):
    """Kullanıcının son ardışık doğru tahmin sayısı (gamification)."""
    user = await current_user_or_401(request)
    db = get_db()
    if db is None:
        return {"streak": 0, "best_streak": 0}
    cursor = db.predictions.find(
        {"user_id": user["id"], "settled": True}
    ).sort("settled_at", -1).limit(100)
    # DESC iterate: en yeni → en eski.
    # `streak` = en sondan başlayan ardışık doğru (ilk yanlışa kadar).
    # `best`   = tüm geçmişteki maksimum ardışık doğru.
    streak = 0
    best = 0
    cur = 0
    streak_closed = False
    async for p in cursor:
        pts = int(p.get("points") or 0)
        if pts > 0:
            cur += 1
            if not streak_closed:
                streak = cur
        else:
            if cur > best:
                best = cur
            cur = 0
            streak_closed = True
    if cur > best:
        best = cur
    if streak > best:
        best = streak
    return {"streak": streak, "best_streak": best}


@router.get("/leaderboard")
async def leaderboard():
    db = get_db()
    if db is None:
        return {"leaderboard": []}
    pipe = [
        {"$group": {
            "_id": "$user_id",
            "name": {"$last": "$user_name"},
            "points": {"$sum": {"$ifNull": ["$points", 0]}},
            "correct": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, 1, 0]}},
            "exact":   {"$sum": {"$cond": [{"$gte": ["$points", 5]}, 1, 0]}},
        }},
        {"$sort": {"points": -1}},
        {"$limit": 50},
    ]
    out = []
    async for row in db.predictions.aggregate(pipe):
        out.append({
            "user_id": str(row["_id"]),
            "name": row.get("name") or "Anonim",
            "points": int(row.get("points") or 0),
            "correct": int(row.get("correct") or 0),
            "exact": int(row.get("exact") or 0),
        })
    return {"leaderboard": out}
