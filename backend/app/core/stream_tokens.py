"""Stream token yardımcıları — Access JWT / HLS HMAC / Cast imzaları (stream_auth + featured ortak).

Token modeli (V2.1):
  Access JWT  30 dk   {iss, sub, scope:"stream_session", sid, did, jti}  → yalnızca bellekte tutulur
  HLS HMAC    query   exp, sid, did, m, st, sig=HMAC-SHA256(STREAM_TOKEN_SECRET, host|st|src|sid|did|exp|m)
              m=js → 30 dk · m=native → 3 saat (Safari/Chromecast, URL yenilenemez) · m=srv → 5 dk (backend proxy)
  Cast        query   + cs=cast_session_id, sig=HMAC-SHA256(STREAM_CAST_SECRET, host|st|src|sid|did|exp|m|cs), 3 saat
Secret'lar env'den okunur, default yok: STREAM_JWT_SECRET, STREAM_TOKEN_SECRET, STREAM_CAST_SECRET.
"""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi import HTTPException

ISSUER = "banbansports"
ALG = "HS256"
ACCESS_SCOPE = "stream_session"
ACCESS_TTL = 30 * 60
REFRESH_TTL = 30 * 24 * 3600
REFRESH_GRACE = 45
CAST_TTL = 3 * 3600
LEASE_TTL = 90
HEARTBEAT_INTERVAL = 45
HLS_TTL = {"js": 30 * 60, "native": 3 * 3600, "srv": 5 * 60}
SOURCES = ("dub", "sub")
AUTH_PARAMS = ("token", "exp", "sid", "did", "m", "st", "cs", "sig")


def env_secret(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise HTTPException(status_code=503, detail=f"{name} yapılandırılmamış")
    return val


def fingerprint(value: str) -> str:
    """Log için kısa parmak izi — tam sid/token asla loglanmaz."""
    return hashlib.sha256((value or "").encode()).hexdigest()[:10]


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_id(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


# ---------- Access JWT ----------
def make_access_token(sid: str, did: str, family_id: str) -> tuple[str, int, str]:
    now = int(time.time())
    jti = new_id(12)
    payload = {"iss": ISSUER, "sub": family_id, "scope": ACCESS_SCOPE, "sid": sid, "did": did,
               "jti": jti, "iat": now, "exp": now + ACCESS_TTL}
    return jwt.encode(payload, env_secret("STREAM_JWT_SECRET"), algorithm=ALG), now + ACCESS_TTL, jti


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, env_secret("STREAM_JWT_SECRET"), algorithms=[ALG], issuer=ISSUER)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="erişim token'ı geçersiz veya süresi dolmuş")
    if payload.get("scope") != ACCESS_SCOPE or not payload.get("sid") or not payload.get("did"):
        raise HTTPException(status_code=401, detail="erişim token'ı kapsamı geçersiz")
    return payload


# ---------- HLS HMAC ----------
def hls_message(host: str, stream: str, src: str, sid: str, did: str, exp: int, mode: str, cs: str = "") -> str:
    parts = [host, stream, src, sid, did, str(exp), mode]
    if cs:
        parts.append(cs)
    return "|".join(parts)


def hls_sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def sign_hls_params(host: str, stream: str, src: str, sid: str, did: str, mode: str,
                    cast_session_id: str = "") -> tuple[dict, int]:
    """Worker'ın doğruladığı query param seti + ttl. cs varsa Cast secret'ı ile imzalanır."""
    if mode not in HLS_TTL:
        raise HTTPException(status_code=400, detail="mode js|native olmalı")
    ttl = CAST_TTL if cast_session_id else HLS_TTL[mode]
    exp = int(time.time()) + ttl
    secret = env_secret("STREAM_CAST_SECRET" if cast_session_id else "STREAM_TOKEN_SECRET")
    params = {"exp": str(exp), "sid": sid, "did": did, "m": mode, "st": stream}
    if cast_session_id:
        params["cs"] = cast_session_id
    params["sig"] = hls_sign(secret, hls_message(host, stream, src, sid, did, exp, mode, cast_session_id))
    return params, ttl


def verify_hls_params(host: str, src: str, params: dict) -> dict:
    """Backend tarafı doğrulama (/validate — yalnızca dev). Worker prod'da kendi doğrular."""
    for k in ("exp", "sid", "did", "m", "st", "sig"):
        if not params.get(k):
            raise HTTPException(status_code=403, detail=f"eksik param: {k}")
    try:
        exp = int(params["exp"])
    except ValueError:
        raise HTTPException(status_code=403, detail="exp geçersiz")
    if exp <= int(time.time()):
        raise HTTPException(status_code=403, detail="süresi dolmuş")
    cs = params.get("cs", "")
    secret = env_secret("STREAM_CAST_SECRET" if cs else "STREAM_TOKEN_SECRET")
    expected = hls_sign(secret, hls_message(host, params["st"], src, params["sid"], params["did"], exp, params["m"], cs))
    if not hmac.compare_digest(expected, params["sig"]):
        raise HTTPException(status_code=403, detail="imza geçersiz")
    return {"ok": True, "src": src, "st": params["st"], "m": params["m"], "exp": exp, "cast": bool(cs)}


def strip_auth_params(url: str) -> str:
    """Cache anahtarı için auth param'larını URL'den ayıkla."""
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in AUTH_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def with_params(url: str, params: dict) -> str:
    base = strip_auth_params(url)
    return base + ("&" if "?" in base else "?") + urlencode(params)
