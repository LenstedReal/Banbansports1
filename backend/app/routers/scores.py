"""Score endpoints — /api/scores/*, /api/livescore/*"""
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

from ..services.livescore import fetch_live_scores, livescore_fetch_day, TR_TZ
from ..core.team_translations import tr_team_name
from ..core.config import LIVESCORE_FETCH_TIMEOUT

logger = logging.getLogger("banbansports.scores")
router = APIRouter(prefix="/api", tags=["scores"])


def _translate_stages(data: dict) -> dict:
    """Apply Turkish team-name translation to all Events within Stages."""
    if not data or "Stages" not in data:
        return data
    for stage in data.get("Stages") or []:
        for ev in (stage.get("Events") or []):
            t1_arr = ev.get("T1") or []
            t2_arr = ev.get("T2") or []
            if t1_arr and isinstance(t1_arr, list):
                for t in t1_arr:
                    if isinstance(t, dict) and t.get("Nm"):
                        t["NmEn"] = t["Nm"]
                        t["Nm"] = tr_team_name(t["Nm"])
            if t2_arr and isinstance(t2_arr, list):
                for t in t2_arr:
                    if isinstance(t, dict) and t.get("Nm"):
                        t["NmEn"] = t["Nm"]
                        t["Nm"] = tr_team_name(t["Nm"])
    return data


@router.get("/scores/live")
async def get_live_scores():
    score = await fetch_live_scores(top_n=1)
    if not score:
        return {"type": "score_update", "available": False, "message": "Şu an için maç verisi yok",
                "timestamp": datetime.now(timezone.utc).isoformat()}
    return score


@router.get("/scores/top")
async def get_top_scores(n: int = 5):
    n = max(1, min(int(n), 10))
    data = await fetch_live_scores(top_n=n)
    if not data:
        return {"type": "score_top", "matches": [], "timestamp": datetime.now(timezone.utc).isoformat()}
    return data


async def _today_plus_upcoming(http, today_str: str, upcoming_days: int = 2) -> dict:
    """Bugün + yaklaşan `upcoming_days` günü tek Stages listesinde birleştir. Dünya Kupası /
    milli maçlar çoğu zaman yarın-öbür gün olduğundan Match Center'da görünmesi için gerekli.
    TBD finalist placeholder'ları (ör. 'France/Spain') ve mükerrer maçlar elenir; ufak kulüp
    elemesi küratörlemesi frontend'de yapılır."""
    merged: dict = {}
    order: list = []

    def _add(data: dict):
        for stage in (data.get("Stages") or []):
            cnm = stage.get("Cnm") or ""
            snm = stage.get("Snm") or ""
            key = (cnm, snm)
            if key not in merged:
                merged[key] = {"Cnm": cnm, "Snm": snm, "Events": []}
                order.append(key)
            existing = merged[key]["Events"]
            seen = {(e.get("Eid"), str(e.get("Esd"))) for e in existing}
            for ev in (stage.get("Events") or []):
                t1 = ((ev.get("T1") or [{}])[0].get("Nm") or "")
                t2 = ((ev.get("T2") or [{}])[0].get("Nm") or "")
                if "/" in t1 or "/" in t2:   # TBD finalist placeholder — gösterme
                    continue
                sig = (ev.get("Eid"), str(ev.get("Esd")))
                if sig in seen:
                    continue
                seen.add(sig)
                existing.append(ev)
        # boş kalan stage'leri at
        for k in list(merged.keys()):
            if not merged[k]["Events"] and k in order:
                order.remove(k)
                del merged[k]

    td = await livescore_fetch_day(http, today_str)
    if td:
        _add(td)
    base = datetime.now(TR_TZ)
    for i in range(1, upcoming_days + 1):
        ds = (base + timedelta(days=i)).strftime("%Y%m%d")
        d = await livescore_fetch_day(http, ds)
        if d:
            _add(d)
    return {"Stages": [merged[k] for k in order]}


@router.get("/livescore/today")
async def livescore_today(days: int = 2):
    days = max(0, min(int(days), 4))
    date_str = datetime.now(TR_TZ).strftime("%Y%m%d")
    try:
        async with httpx.AsyncClient(timeout=LIVESCORE_FETCH_TIMEOUT) as http:
            data = await _today_plus_upcoming(http, date_str, days)
            if data.get("Stages"):
                return _translate_stages(data)
    except Exception as e:
        logger.warning(f"LiveScore today error: {e}")
    return {"Stages": []}


@router.get("/livescore/date/{date_str}")
async def livescore_date(date_str: str):
    try:
        async with httpx.AsyncClient(timeout=LIVESCORE_FETCH_TIMEOUT) as http:
            data = await livescore_fetch_day(http, date_str)
            if data:
                return _translate_stages(data)
    except Exception as e:
        logger.warning(f"LiveScore date error: {e}")
    return {"Stages": []}
