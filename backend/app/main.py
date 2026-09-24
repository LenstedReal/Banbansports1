"""banbansports v4 — modular FastAPI app."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .core.config import CORS_ORIGINS, SCORE_BROADCAST_INTERVAL, ST11_REFRESH_INTERVAL, SETTLEMENT_INTERVAL, IS_PRODUCTION
from .core.database import init_db, close_db, get_db
from .services.livescore import fetch_live_scores
from .services.ws_manager import manager
from .services.st11 import st11_manager
from .services.settlement import settle_loop
from .services import stream_registry as stream_reg
from .routers import auth_ext, scores, streams, bein, channels, ssport, stream_generic, auth as auth_router, predictions, chat, notifications, ws, match_stats, admin, push, ai_predict, internal, featured, movies, sponsors, boxoffice, stream_auth, site_gate, community, admin_gate, radio

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("banbansports")


# ---------- Background loops ----------
async def score_broadcast_loop():
    while True:
        try:
            if manager.has_clients:
                score = await fetch_live_scores()
                if score:
                    await manager.broadcast(score)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"broadcast: {e}")
        await asyncio.sleep(SCORE_BROADCAST_INTERVAL)


async def st11_refresh_loop():
    await asyncio.sleep(60)
    while True:
        try:
            valid = await st11_manager.is_token_valid()
            if not valid:
                await st11_manager.try_auto_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"st11 refresh: {e}")
        await asyncio.sleep(ST11_REFRESH_INTERVAL)


async def st15_refresh_loop():
    """Tüm kayıtlı stream manager'ları (SSPort + future kanallar) refresh."""
    await asyncio.sleep(75)  # st11 ile çakışma yok
    while True:
        try:
            results = await stream_reg.refresh_all()
            refreshed = [cid for cid, r in results.items() if r.get("refreshed")]
            if refreshed:
                logger.info(f"stream refresh: {refreshed}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"stream refresh: {e}")
        await asyncio.sleep(ST11_REFRESH_INTERVAL)


# ---------- Lifespan ----------
IS_SERVERLESS = bool(os.environ.get("BB_SERVERLESS") or os.environ.get("VERCEL"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()
    if db is not None:
        await auth_router.seed_admin()
    tasks = []
    if not IS_SERVERLESS:
        # Sonsuz döngüler yalnızca kalıcı sunucuda (uvicorn). Vercel'de her istek bağımsızdır.
        tasks = [
            asyncio.create_task(score_broadcast_loop()),
            asyncio.create_task(st11_refresh_loop()),
            asyncio.create_task(st15_refresh_loop()),
            asyncio.create_task(settle_loop()),
            asyncio.create_task(movies.warm_cache()),
            asyncio.create_task(boxoffice.refresh_loop()),
        ]
    logger.info("banbansports v4 ready (env=%s, serverless=%s)", "production" if IS_PRODUCTION else "development", IS_SERVERLESS)
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        if not IS_SERVERLESS:
            await close_db()


# ---------- App ----------
app = FastAPI(lifespan=lifespan, title="banbansports", version="4.0")


@app.get("/api/")
async def root():
    return {"message": "banbansports v4 — API ready", "version": "4.0"}


@app.get("/api/health")
async def health():
    db = get_db()
    return {
        "status": "ok",
        "mongo": db is not None,
        "ws_clients": len(manager.active_connections),
        "version": "4.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Routers
app.include_router(scores.router)
app.include_router(match_stats.router)
app.include_router(streams.router)
app.include_router(bein.router)
app.include_router(ssport.router)            # backward-compat redirect
app.include_router(stream_generic.router)    # generic /api/stream/{ch}/*
app.include_router(featured.router)           # öne çıkan yayın (tünel kaynak proxy)
app.include_router(movies.router)             # film kataloğu + range'li stream
app.include_router(boxoffice.router)          # canlı gişe + IMDb + seyirci sayacı
app.include_router(stream_auth.router)        # korumalı yayın — 30 dk signed token
app.include_router(site_gate.router)          # site girişi — Turnstile "ben robot değilim" kapısı
app.include_router(community.router)          # topluluk sohbeti v2 — anonim kimlik + moderasyon
app.include_router(admin_gate.router)         # admin gate — adminastor + kilit + sifre sifirlama
app.include_router(radio.router)              # BANBAN LIVE RADIO — Radio Browser
app.include_router(channels.router)
app.include_router(auth_router.router)
app.include_router(auth_ext.router)           # Discord OAuth + Resend şifre sıfırlama + providers
app.include_router(predictions.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(push.router)
app.include_router(admin.router)
app.include_router(ws.router)
app.include_router(ai_predict.router)
app.include_router(internal.router)
app.include_router(sponsors.router)

# CORS — cookies require explicit origins (browsers reject '*' + credentials).

# Güncellik: canlı veri uçları (skor, fikstür, kanal durumu, gişe) hiçbir katmanda cache'lenmez
_NO_STORE_PREFIXES = ("/api/livescore", "/api/scores", "/api/stream/status", "/api/featured/status",
                      "/api/boxoffice", "/api/channels", "/api/site-gate", "/api/stream-auth")


@app.middleware("http")
async def _no_store_live_data(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(_NO_STORE_PREFIXES) and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["CDN-Cache-Control"] = "no-store"
    return response


# In production, CORS_ORIGINS must be set in env. In development we fall back
# to a regex that allows localhost + preview URLs.
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif not IS_PRODUCTION:
    # Dev: allow localhost ports + preview subdomains used during testing
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost(:\d+)?|127\.0\.0\.1(:\d+)?|.+\.preview\..+)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Vercel'de frontend + API aynı origin → CORS gerekmez; env eksikse çökmek yerine same-origin çalış.
    logger.warning("CORS_ORIGINS bos — yalnizca same-origin istekler kabul edilir.")
