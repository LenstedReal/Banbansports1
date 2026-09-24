"""Film kataloğu — Cloudflare R2 (Object Storage + CDN) üzerinden HLS yayın.

MediaFire / indirme / lokal cache bağımlılığı tamamen kaldırıldı.
Yayınlar .m3u8 manifest olarak doğrudan CDN'den servis edilir; player
tarafında HLS.js ile oynatılır. Sunucu dosya taşımaz, 7/24 hazırdır.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..core.database import get_db, init_db

logger = logging.getLogger("banbansports.movies")
router = APIRouter(prefix="/api/movies", tags=["movies"])

SEED_MOVIE = {
    "id": "spiderman-bnd-4-1",
    "title": "Örümcek-Adam: Yepyeni Bir Gün",
    "title_en": "Spider-Man: Brand New Day",
    "badge": "YENİ",
    "poster": "/spiderman_poster_v2.jpg",
    "backdrop": "/spiderman_backdrop_v2.jpg",
    "lang": "TÜRKÇE DUBLAJ · TÜRKÇE ALTYAZI",
    "release_date": "July 31, 2026",
    "stream_format": "hls",
    "stream_dub": "https://stream.lenstedreal.xyz/stream.m3u8",
    "stream_sub": "https://stream1.lenstedreal.xyz/stream.m3u8",
    "stream_dub_label": "Türkçe Dublaj / English Altyazı",
    "stream_dub_quality": "720p",
    "stream_sub_label": "Orijinal Ses / Türkçe Altyazı",
    "stream_sub_quality": "1080p",
}

# Eski MediaFire dönemi alanları — DB'den temizlenir
_LEGACY_FIELDS = {"source_page": "", "content_type": "", "size": ""}


async def _db():
    db = get_db()
    if db is None:
        db = await init_db()
    return db


async def ensure_seed() -> None:
    db = await _db()
    if db is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    await db.movies.update_one(
        {"id": SEED_MOVIE["id"]},
        {
            "$set": SEED_MOVIE,
            "$unset": _LEGACY_FIELDS,
            "$setOnInsert": {"created_at": now, "is_deleted": False},
        },
        upsert=True,
    )


async def warm_cache() -> None:
    """Startup: film kaydını seed'le (CDN yayını olduğu için indirme yok)."""
    try:
        await ensure_seed()
        logger.info("movies: HLS/CDN seed hazır — indirme gerekmiyor")
    except Exception as e:
        logger.warning(f"movie seed: {e}")


@router.get("")
async def list_movies():
    db = await _db()
    if db is None:
        raise HTTPException(status_code=503, detail="veritabanı yok")
    await ensure_seed()
    movies = await db.movies.find({"is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"movies": movies}


@router.get("/{movie_id}/status")
async def movie_status(movie_id: str):
    db = await _db()
    if db is None:
        raise HTTPException(status_code=503, detail="veritabanı yok")
    movie = await db.movies.find_one({"id": movie_id, "is_deleted": False}, {"_id": 0})
    if not movie:
        raise HTTPException(status_code=404, detail="film bulunamadı")
    # CDN + HLS → yayın her zaman hazır
    return {"id": movie_id, "ready": True, "downloading": False, "mode": "hls"}
