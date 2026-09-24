"""Korumalı yayın erişimi V2.1 — Access JWT / Refresh cookie (rotation) / HLS HMAC / Cast (üyelik DEĞİLDİR).

Akış: ID+Şifre → Turnstile → oturum (sid, did, family) → bb_refresh HttpOnly cookie + 30 dk Access JWT (bellek).
Player `/url` ile HMAC imzalı m3u8 URL alır; Worker imzayı kendisi doğrular. Cihaz/eşzamanlılık birimi = refresh family.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..core import stream_tokens as tk
from ..core.config import IS_PRODUCTION
from ..core.database import get_db, init_db
import os

logger = logging.getLogger("banbansports.stream_auth")
router = APIRouter(prefix="/api/stream-auth", tags=["stream-auth"])

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
COOKIE = "bb_refresh"
COOKIE_PATH = "/api/stream-auth"
# site_gate.py geriye dönük import (import-time okunur; login akışı runtime'da _env ile okur)
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()

# Basit brute-force freni: IP başına 5 dk içinde en fazla 12 deneme
_RL_WINDOW, _RL_MAX = 300, 12
_attempts: dict[str, list[float]] = {}
_indexes_ready = False


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _max_concurrent() -> int:
    try:
        return max(1, int(_env("STREAM_MAX_CONCURRENT") or "1"))
    except ValueError:
        return 1


class LoginBody(BaseModel):
    username: str = Field(max_length=120)
    password: str = Field(max_length=120)
    turnstile_token: str = Field(default="", max_length=4096)
    device_id: str = Field(default="", max_length=64)


class UrlBody(BaseModel):
    stream_id: str = Field(max_length=120)
    source: str = Field(max_length=8)
    mode: str = Field(default="js", max_length=8)


class StartBody(BaseModel):
    stream_id: str = Field(max_length=120)
    source: str = Field(max_length=8)


class LeaseBody(BaseModel):
    lease_id: str = Field(default="", max_length=64)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if isinstance(dt, datetime) and dt.tzinfo is None else dt


def _client_ip(request: Request) -> str:
    xff = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _attempts.get(ip, []) if now - t < _RL_WINDOW]
    hits.append(now)
    _attempts[ip] = hits
    if len(_attempts) > 5000:
        for k in [k for k, v in _attempts.items() if not v or now - v[-1] > _RL_WINDOW]:
            _attempts.pop(k, None)
    return len(hits) > _RL_MAX


def _is_https(request: Request) -> bool:
    return IS_PRODUCTION or request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=tk.REFRESH_TTL, httponly=True, secure=_is_https(request),
                        samesite="lax", path=COOKIE_PATH)


def _clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, secure=_is_https(request), samesite="lax")


async def _db():
    global _indexes_ready
    db = get_db()
    if db is None:
        db = await init_db()
    if db is None:
        raise HTTPException(status_code=503, detail="veritabanı yok")
    if not _indexes_ready:
        _indexes_ready = True
        try:
            await db.stream_sessions.create_index("last_seen", expireAfterSeconds=6 * 3600)
            await db.stream_sessions.create_index("family_id")
            await db.stream_refresh_tokens.create_index("token_hash", unique=True)
            await db.stream_refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
            await db.stream_refresh_tokens.create_index("family_id")
            await db.stream_activity.create_index("last_heartbeat", expireAfterSeconds=tk.LEASE_TTL)
            await db.stream_activity.create_index([("family_id", 1), ("session_id", 1)])
        except Exception as e:
            logger.debug("stream_auth index init: %s", e)
    return db


async def verify_turnstile(token: str, remote_ip: str) -> None:
    """Fail-closed: secret yoksa / Cloudflare'e ulaşılamazsa / success=false ise oturum AÇILMAZ."""
    secret = _env("TURNSTILE_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=503, detail="Turnstile yapılandırılmamış (TURNSTILE_SECRET_KEY)")
    if not token:
        raise HTTPException(status_code=400, detail="Bot doğrulaması tamamlanmadı")
    payload = {"secret": secret, "response": token}
    if remote_ip and remote_ip != "?":
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(SITEVERIFY_URL, json=payload)
            r.raise_for_status()
            result = r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=503, detail="Doğrulama servisine ulaşılamadı")
    if not result.get("success"):
        logger.info("turnstile fail: %s", result.get("error-codes"))
        raise HTTPException(status_code=400, detail="Bot doğrulaması başarısız — tekrar deneyin")


# ---------- oturum / refresh yardımcıları ----------
async def _issue_refresh(db, session: dict) -> str:
    raw = tk.new_id(48)
    await db.stream_refresh_tokens.insert_one({
        "token_hash": tk.hash_token(raw), "session_id": session["_id"], "family_id": session["family_id"],
        "created_at": _now(), "expires_at": _now() + timedelta(seconds=tk.REFRESH_TTL),
        "revoked": False, "rotated_at": None, "replaced_by": None,
    })
    return raw


def _access_payload(session: dict) -> dict:
    token, exp, _jti = tk.make_access_token(session["_id"], session["device_id"], session["family_id"])
    return {"ok": True, "access_token": token, "token_type": "Bearer", "expires_in": tk.ACCESS_TTL,
            "expires_at": exp, "sid": session["_id"], "did": session["device_id"],
            "heartbeat_interval": tk.HEARTBEAT_INTERVAL}


async def _revoke_family(db, family_id: str, reason: str) -> None:
    await db.stream_refresh_tokens.update_many({"family_id": family_id}, {"$set": {"revoked": True}})
    await db.stream_sessions.update_many({"family_id": family_id}, {"$set": {"revoked": True}})
    await db.stream_activity.delete_many({"family_id": family_id})
    logger.warning("family revoked fam=%s reason=%s", tk.fingerprint(family_id), reason)


async def _bearer(request: Request) -> tuple[dict, dict, object]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer gerekli")
    payload = tk.decode_access_token(auth[7:].strip())
    db = await _db()
    session = await db.stream_sessions.find_one({"_id": payload["sid"]})
    if not session or session.get("revoked"):
        raise HTTPException(status_code=401, detail="oturum geçersiz — yeniden giriş yapın")
    return payload, session, db


async def _stream_target(db, stream_id: str, source: str) -> tuple[str, str]:
    """stream_id → movies koleksiyonundan base m3u8 URL + host (dub → stream. / sub → stream1.)."""
    if source not in tk.SOURCES:
        raise HTTPException(status_code=400, detail="source dub|sub olmalı")
    movie = await db.movies.find_one({"id": stream_id, "is_deleted": False}, {"_id": 0, "stream_dub": 1, "stream_sub": 1})
    base = (movie or {}).get(f"stream_{source}")
    if not base:
        raise HTTPException(status_code=404, detail="yayın bulunamadı")
    host = urlparse(base).hostname or ""
    return base, host


async def _active_family_leases(db, family_id: str, exclude_sid: str) -> int:
    cutoff = _now() - timedelta(seconds=tk.LEASE_TTL)
    return await db.stream_activity.count_documents(
        {"family_id": family_id, "session_id": {"$ne": exclude_sid}, "last_heartbeat": {"$gt": cutoff}})


# ---------- endpoints ----------
@router.get("/config")
async def config():
    """Public bilgi — secret ASLA dönmez."""
    return {"turnstile_site_key": _env("TURNSTILE_SITE_KEY"), "token_ttl": tk.ACCESS_TTL,
            "hls_ttl_js": tk.HLS_TTL["js"], "hls_ttl_native": tk.HLS_TTL["native"],
            "heartbeat_interval": tk.HEARTBEAT_INTERVAL, "max_concurrent": _max_concurrent()}


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    """IP RL → user/pass → Turnstile → did → session → refresh cookie → access JWT."""
    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Çok fazla deneme — birkaç dakika sonra tekrar deneyin")
    user, pw = tk.env_secret("STREAM_ACCESS_USER"), tk.env_secret("STREAM_ACCESS_PASS")
    if body.username.strip() != user or body.password.strip() != pw:
        raise HTTPException(status_code=401, detail="Geçersiz erişim bilgileri")
    await verify_turnstile(body.turnstile_token.strip(), ip)
    db = await _db()
    session = {
        "_id": tk.new_id(16), "device_id": body.device_id.strip() or tk.new_id(12), "family_id": tk.new_id(16),
        "created_at": _now(), "last_seen": _now(), "ip_hash": tk.hash_token(ip)[:32], "revoked": False,
        "active_stream_id": None, "active_stream_source": None, "last_heartbeat": None,
    }
    await db.stream_sessions.insert_one(session)
    _set_cookie(response, request, await _issue_refresh(db, session))
    logger.info("login ok sid=%s fam=%s", tk.fingerprint(session["_id"]), tk.fingerprint(session["family_id"]))
    return _access_payload(session)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    """Cookie'deki opaque refresh → rotation → yeni access (+cookie). 45 sn grace, sonra replay = family revoke."""
    raw = request.cookies.get(COOKIE, "")
    if not raw:
        raise HTTPException(status_code=401, detail="refresh yok")
    db = await _db()
    doc = await db.stream_refresh_tokens.find_one({"token_hash": tk.hash_token(raw)})
    if not doc or _aware(doc["expires_at"]) <= _now():
        _clear_cookie(response, request)
        raise HTTPException(status_code=401, detail="refresh geçersiz")
    session = await db.stream_sessions.find_one({"_id": doc["session_id"]})
    if doc.get("revoked"):
        rotated = _aware(doc.get("rotated_at"))
        in_grace = rotated is not None and (_now() - rotated).total_seconds() <= tk.REFRESH_GRACE and doc.get("replaced_by")
        if not in_grace:
            await _revoke_family(db, doc["family_id"], "refresh replay")
            _clear_cookie(response, request)
            raise HTTPException(status_code=401, detail="oturum güvenlik nedeniyle kapatıldı — yeniden giriş yapın")
        if not session or session.get("revoked"):
            _clear_cookie(response, request)
            raise HTTPException(status_code=401, detail="oturum geçersiz")
        return _access_payload(session)  # grace: cookie zaten yeni token'ı taşıyor
    if not session or session.get("revoked"):
        _clear_cookie(response, request)
        raise HTTPException(status_code=401, detail="oturum geçersiz")
    new_raw = await _issue_refresh(db, session)
    await db.stream_refresh_tokens.update_one(
        {"_id": doc["_id"]}, {"$set": {"revoked": True, "rotated_at": _now(), "replaced_by": tk.hash_token(new_raw)}})
    await db.stream_sessions.update_one({"_id": session["_id"]}, {"$set": {"last_seen": _now()}})
    _set_cookie(response, request, new_raw)
    logger.info("refresh ok sid=%s", tk.fingerprint(session["_id"]))
    return _access_payload(session)


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Session + family revoke, cookie sil (cookie veya Bearer ile)."""
    db = await _db()
    family_id = None
    raw = request.cookies.get(COOKIE, "")
    if raw:
        doc = await db.stream_refresh_tokens.find_one({"token_hash": tk.hash_token(raw)}, {"family_id": 1})
        family_id = (doc or {}).get("family_id")
    if not family_id:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                family_id = tk.decode_access_token(auth[7:].strip()).get("sub")
            except HTTPException:
                family_id = None
    if family_id:
        await _revoke_family(db, family_id, "logout")
    _clear_cookie(response, request)
    return {"ok": True}


@router.get("/status")
async def status(request: Request):
    payload, session, db = await _bearer(request)
    active = await _active_family_leases(db, session["family_id"], "")
    return {"ok": True, "sid": session["_id"], "did": session["device_id"], "exp": payload["exp"],
            "active_stream_id": session.get("active_stream_id"), "active_stream_source": session.get("active_stream_source"),
            "family_active": active, "max_concurrent": _max_concurrent()}


@router.post("/url")
async def signed_url(body: UrlBody, request: Request):
    """Bearer + {stream_id, source, mode} → HMAC imzalı m3u8 URL (m=js 30 dk | m=native 3 saat)."""
    if body.mode not in ("js", "native"):
        raise HTTPException(status_code=400, detail="mode js|native olmalı")
    _payload, session, db = await _bearer(request)
    base, host = await _stream_target(db, body.stream_id, body.source)
    params, ttl = tk.sign_hls_params(host, body.stream_id, body.source, session["_id"], session["device_id"], body.mode)
    return {"ok": True, "url": tk.with_params(base, params), "base_url": base, "params": params,
            "mode": body.mode, "expires_in": ttl, "expires_at": int(params["exp"])}


@router.post("/start")
async def start(body: StartBody, request: Request):
    """İzleme lease'i (TTL 90 sn). Family (aynı tarayıcı) başına STREAM_MAX_CONCURRENT."""
    _payload, session, db = await _bearer(request)
    await _stream_target(db, body.stream_id, body.source)
    limit = _max_concurrent()
    active = await _active_family_leases(db, session["family_id"], session["_id"])
    if active >= limit:
        raise HTTPException(status_code=409, detail=f"Eş zamanlı izleme sınırı ({limit}) doldu")
    await db.stream_activity.delete_many({"session_id": session["_id"]})
    lease_id = tk.new_id(16)
    lease = {"_id": lease_id, "session_id": session["_id"], "family_id": session["family_id"],
             "stream_id": body.stream_id, "source": body.source, "started_at": _now(), "last_heartbeat": _now()}
    await db.stream_activity.insert_one(lease)
    await db.stream_sessions.update_one({"_id": session["_id"]}, {"$set": {
        "active_stream_id": body.stream_id, "active_stream_source": body.source, "last_heartbeat": _now(), "last_seen": _now()}})
    logger.info("lease start sid=%s st=%s src=%s", tk.fingerprint(session["_id"]), body.stream_id, body.source)
    return {"ok": True, "lease_id": lease_id, "heartbeat_interval": tk.HEARTBEAT_INTERVAL, "ttl": tk.LEASE_TTL,
            "family_active": active + 1, "max_concurrent": limit}


@router.post("/heartbeat")
async def heartbeat(body: LeaseBody, request: Request):
    _payload, session, db = await _bearer(request)
    r = await db.stream_activity.update_one({"_id": body.lease_id, "session_id": session["_id"]},
                                            {"$set": {"last_heartbeat": _now()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="lease yok — /start ile yeniden başlat")
    await db.stream_sessions.update_one({"_id": session["_id"]}, {"$set": {"last_heartbeat": _now(), "last_seen": _now()}})
    return {"ok": True, "ttl": tk.LEASE_TTL}


@router.post("/stop")
async def stop(body: LeaseBody, request: Request):
    """Lease'i bırak. Bearer varsa oturumun tüm lease'leri; yoksa (sendBeacon) yalnızca lease_id."""
    db = await _db()
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        _payload, session, db = await _bearer(request)
        await db.stream_activity.delete_many({"session_id": session["_id"]})
        await db.stream_sessions.update_one({"_id": session["_id"]}, {"$set": {"active_stream_id": None, "active_stream_source": None}})
        return {"ok": True}
    if not body.lease_id:
        raise HTTPException(status_code=400, detail="lease_id gerekli")
    lease = await db.stream_activity.find_one_and_delete({"_id": body.lease_id})
    if lease:
        await db.stream_sessions.update_one({"_id": lease["session_id"]}, {"$set": {"active_stream_id": None, "active_stream_source": None}})
    return {"ok": True}


@router.post("/cast-token")
async def cast_token(body: StartBody, request: Request):
    """Bearer + {stream_id, source} → cast_session_id'ye bağlı, m=native imzalı media_url (3 saat, STREAM_CAST_SECRET)."""
    _payload, session, db = await _bearer(request)
    base, host = await _stream_target(db, body.stream_id, body.source)
    cast_session_id = tk.new_id(16)
    params, ttl = tk.sign_hls_params(host, body.stream_id, body.source, session["_id"], session["device_id"], "native", cast_session_id)
    await db.stream_sessions.update_one({"_id": session["_id"]}, {"$set": {"last_cast_session_id": cast_session_id, "last_seen": _now()}})
    logger.info("cast token sid=%s cs=%s", tk.fingerprint(session["_id"]), tk.fingerprint(cast_session_id))
    return {"ok": True, "cast_session_id": cast_session_id, "media_url": tk.with_params(base, params),
            "content_type": "application/x-mpegURL", "expires_in": ttl}


@router.get("/validate")
async def validate(request: Request, host: str, src: str, st: str, sid: str, did: str, exp: str, m: str, sig: str, cs: str = ""):
    """Yalnızca dev/debug — prod'da kapalı (Worker kendi doğrular). STREAM_VALIDATE_ENABLED=true gerekir."""
    if IS_PRODUCTION or _env("STREAM_VALIDATE_ENABLED").lower() != "true":
        raise HTTPException(status_code=404, detail="Not Found")
    if src not in tk.SOURCES:
        raise HTTPException(status_code=403, detail="kaynak geçersiz")
    return tk.verify_hls_params(host, src, {"st": st, "sid": sid, "did": did, "exp": exp, "m": m, "sig": sig, "cs": cs})
