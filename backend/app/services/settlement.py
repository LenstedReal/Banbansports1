"""Prediction settlement loop.

Maç tamamlandığında (FT) kullanıcının tahminini gerçek skorla karşılaştırır,
puanları hesaplar ve `predictions` koleksiyonunda `settled=True` olarak işaretler.

Puan sistemi (5/3/1/0):
  * Tam skor doğru                  → 5 puan
  * Sonuç + gol farkı doğru          → 3 puan   (örn. tahmin 2-1, gerçek 3-2)
  * Sadece sonuç (galip taraf) doğru → 1 puan
  * Yanlış sonuç                     → 0 puan
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import httpx

from ..core.config import LIVESCORE_FETCH_TIMEOUT, SETTLEMENT_INTERVAL
from ..core.database import get_db
from .livescore import livescore_fetch_day, _normalize_tr

logger = logging.getLogger("banbansports.settlement")

FT_STATES = {"FT", "AET", "AP", "Pen."}


def _team_match(pred: str, actual: str) -> bool:
    """Takım ismi eşleşmesi — substring false-positive'den koruma.

    Kural:
      * Exact (normalize sonrası) eşitlik → True
      * Tek kelime ise: tam kelime eşleşmesi (boundary'li)
      * Aksi halde: en az ortak prefix 4 karakter VE biri diğerini tam içeriyor
                   AND fark "küçük kelime" (örn. "fc", "city", "miami") değil
    """
    if not pred or not actual:
        return False
    if pred == actual:
        return True
    p_tokens = set(pred.split())
    a_tokens = set(actual.split())
    # Tam kelime kesişimi var mı?
    common = p_tokens & a_tokens
    if not common:
        return False
    # En az bir "anlamlı" (>=4 karakter) ortak kelime
    if not any(len(t) >= 4 for t in common):
        return False
    # Diğer kelimelerden biri "ayırıcı şehir/lig token"u mu? (Miami, City, FC vs.)
    # Anlamlı farkı olan iki takımı (Inter ≠ Inter Miami) ayırt et.
    only_pred = p_tokens - a_tokens
    only_actual = a_tokens - p_tokens
    diff = only_pred | only_actual
    # Eğer fark anlamlı bir kelime ise (>=3 karakter, sayısal değil) eşleşme yok.
    for tok in diff:
        if len(tok) >= 3 and not tok.isdigit():
            return False
    return True


def _calc_points(p1: int, p2: int, a1: int, a2: int) -> int:
    """5/3/1/0 puan sistemi."""
    if p1 == a1 and p2 == a2:
        return 5
    pred_sign = (p1 > p2) - (p1 < p2)
    actual_sign = (a1 > a2) - (a1 < a2)
    if pred_sign != actual_sign:
        return 0
    if (p1 - p2) == (a1 - a2):
        return 3
    return 1


async def _find_final_score(http: httpx.AsyncClient, team1: str, team2: str,
                            kickoff_date: Optional[str] = None) -> Optional[Tuple[int, int]]:
    """LiveScore (FotMob/SofaScore fallback) üzerinden FT skoru bul.

    `kickoff_date` formatı YYYYMMDD. Önce bu tarih, sonra son 3 gün denenir.
    """
    t1n, t2n = _normalize_tr(team1), _normalize_tr(team2)
    today = datetime.now(timezone.utc)
    dates: list[str] = []
    if kickoff_date and len(kickoff_date) == 8:
        dates.append(kickoff_date)
    for d in range(0, 4):
        dates.append((today - timedelta(days=d)).strftime("%Y%m%d"))
    # Dedup, sırayı koru
    seen, ordered = set(), []
    for d in dates:
        if d not in seen:
            seen.add(d)
            ordered.append(d)

    for ds in ordered:
        data = await livescore_fetch_day(http, ds)
        if not data:
            continue
        for stage in (data.get("Stages") or []):
            for ev in (stage.get("Events") or []):
                t1 = ((ev.get("T1") or [{}])[0].get("Nm") or "")
                t2 = ((ev.get("T2") or [{}])[0].get("Nm") or "")
                a, b = _normalize_tr(t1), _normalize_tr(t2)
                # Exact match — substring false-positive'den koru ("Inter" ≠ "Inter Miami")
                if _team_match(t1n, a) and _team_match(t2n, b):
                    if (ev.get("Eps") or "") in FT_STATES:
                        return int(ev.get("Tr1") or 0), int(ev.get("Tr2") or 0)
    return None


async def settle_once() -> int:
    """Tek seferlik settlement run — kaç tahmin ödendi onu döner."""
    db = get_db()
    if db is None:
        return 0
    settled_count = 0
    try:
        pending = await db.predictions.find({"settled": {"$ne": True}}).to_list(500)
        if not pending:
            return 0
        async with httpx.AsyncClient(timeout=LIVESCORE_FETCH_TIMEOUT) as http:
            for pred in pending:
                team1 = pred.get("team1") or ""
                team2 = pred.get("team2") or ""
                if not team1 or not team2:
                    continue
                result = await _find_final_score(http, team1, team2, pred.get("kickoff_date"))
                if not result:
                    continue
                a1, a2 = result
                p1, p2 = int(pred.get("score1", -1)), int(pred.get("score2", -1))
                if p1 < 0 or p2 < 0:
                    continue
                points = _calc_points(p1, p2, a1, a2)
                await db.predictions.update_one(
                    {"_id": pred["_id"]},
                    {"$set": {
                        "settled": True,
                        "settled_at": datetime.now(timezone.utc),
                        "final_score": [a1, a2],
                        "points": points,
                    }},
                )
                settled_count += 1
                logger.info(
                    "settle: %s %d-%d vs %s [%d-%d] → %dp (user=%s)",
                    team1, p1, p2, team2, a1, a2, points, pred.get("user_id"),
                )
    except Exception as e:
        logger.exception(f"settle_once: {e}")
    return settled_count


async def settle_loop():
    """Background loop — her SETTLEMENT_INTERVAL saniyede bir çalışır."""
    # İlk çalıştırmada biraz bekle (boot sırasında DB hazır olsun)
    await asyncio.sleep(45)
    while True:
        try:
            n = await settle_once()
            if n:
                logger.info(f"settlement: {n} prediction(s) ödendi")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"settle_loop: {e}")
        await asyncio.sleep(SETTLEMENT_INTERVAL)
