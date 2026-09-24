"""Site giriş kapısı — Cloudflare Turnstile ile "ben robot değilim" (site açılmadan önce).

Cloudflare WAF Managed Challenge'ın uygulama içi eşleniği: *.vercel.app gibi Cloudflare
proxy'si olmayan adreslerde de çalışır. Başarılı siteverify → 12 saat geçerli HttpOnly çerez.
Yayın yetkisi VERMEZ; player içindeki Turnstile + şifre + JWT katmanı ayrıdır.
"""
import logging
import os
import time

import jwt
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .stream_auth import TURNSTILE_SECRET, TURNSTILE_SITE_KEY, _client_ip, verify_turnstile

logger = logging.getLogger("banbansports.site_gate")
router = APIRouter(prefix="/api/site-gate", tags=["site-gate"])

COOKIE = "bb_gate"
TTL = 12 * 3600
SECRET = (os.environ.get("STREAM_JWT_SECRET") or os.environ.get("JWT_SECRET") or "").strip()


class VerifyBody(BaseModel):
    turnstile_token: str = Field(max_length=4096)


def _enabled() -> bool:
    # SITE_GATE_DISABLED=1 → test/preview ortamında kapı kapalı (Turnstile domain'e bağlı)
    if os.environ.get('SITE_GATE_DISABLED', '').strip() in ('1', 'true', 'yes'):
        return False
    return bool(TURNSTILE_SECRET and TURNSTILE_SITE_KEY and SECRET)


def _valid(tok: str | None) -> bool:
    if not tok:
        return False
    try:
        return jwt.decode(tok, SECRET, algorithms=["HS256"]).get("scope") == "site"
    except jwt.PyJWTError:
        return False


@router.get("/status")
async def status(request: Request):
    enabled = _enabled()
    if not enabled:
        logger.warning("site-gate devre dışı: TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY / STREAM_JWT_SECRET eksik")
    passed = enabled and _valid(request.cookies.get(COOKIE))
    return {"ok": passed or not enabled, "enabled": enabled, "turnstile_site_key": TURNSTILE_SITE_KEY}


@router.post("/verify")
async def verify(body: VerifyBody, request: Request, response: Response):
    await verify_turnstile(body.turnstile_token.strip(), _client_ip(request))
    now = int(time.time())
    tok = jwt.encode({"scope": "site", "iat": now, "exp": now + TTL}, SECRET, algorithm="HS256")
    response.set_cookie(COOKIE, tok, max_age=TTL, httponly=True, secure=True, samesite="lax", path="/")
    return {"ok": True, "expires_in": TTL}
