"""Auth uzantıları — Discord OAuth2 + Resend ile e-posta şifre sıfırlama + sağlayıcı listesi.

Mevcut auth.py (e-posta/şifre + Google) DOKUNULMADAN yanında çalışır; aynı cookie/JWT katmanını kullanır.
Env:
  DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI  (yoksa Discord butonu gizli)
  RESEND_API_KEY, RESEND_FROM (örn. "BanbanSports <no-reply@banban.lenstedreal.xyz>")  (yoksa şifre sıfırlama e-postası kapalı)
  PUBLIC_SITE_URL (callback sonrası dönüş; yoksa Referer/'/')
"""
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core.config import GOOGLE_CLIENT_ID
from ..core.database import get_db
from ..core.security import hash_password
from .auth import _set_cookies, _public_user, EMAIL_RE

logger = logging.getLogger("banbansports.auth_ext")
router = APIRouter(prefix="/api/auth", tags=["auth-ext"])


def _env(k: str) -> str:
    return os.environ.get(k, "").strip()


def _discord_ok() -> bool:
    return bool(_env("DISCORD_CLIENT_ID") and _env("DISCORD_CLIENT_SECRET"))


def _resend_ok() -> bool:
    return bool(_env("RESEND_API_KEY"))


def _redirect_uri(request: Request) -> str:
    ru = _env("DISCORD_REDIRECT_URI")
    if ru:
        return ru
    base = _env("PUBLIC_SITE_URL") or str(request.base_url).rstrip("/")
    return f"{base}/api/auth/discord/callback"


@router.get("/providers")
async def providers():
    """Frontend hangi giriş butonlarını göstereceğine buradan karar verir."""
    return {
        "email": True,
        "google": bool(GOOGLE_CLIENT_ID),
        "google_client_id": GOOGLE_CLIENT_ID or "",
        "discord": _discord_ok(),
        "password_reset": _resend_ok(),
    }


# ---------------- DISCORD OAUTH2 ----------------
@router.get("/discord/login")
async def discord_login(request: Request):
    if not _discord_ok():
        raise HTTPException(status_code=503, detail="Discord girişi yapılandırılmamış")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": _env("DISCORD_CLIENT_ID"),
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": "identify email",
        "state": state,
        "prompt": "consent",
    }
    resp = RedirectResponse(url="https://discord.com/oauth2/authorize?" + urlencode(params), status_code=302)
    resp.set_cookie("dc_state", state, max_age=600, httponly=True, samesite="lax", path="/")
    return resp


@router.get("/discord/callback")
async def discord_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    site = _env("PUBLIC_SITE_URL") or "/"
    if error or not code:
        return RedirectResponse(url=f"{site}?auth=discord_cancel", status_code=302)
    if not _discord_ok():
        raise HTTPException(status_code=503, detail="Discord girişi yapılandırılmamış")
    if request.cookies.get("dc_state") and request.cookies.get("dc_state") != state:
        return RedirectResponse(url=f"{site}?auth=discord_state", status_code=302)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            tr = await http.post("https://discord.com/api/oauth2/token", data={
                "client_id": _env("DISCORD_CLIENT_ID"),
                "client_secret": _env("DISCORD_CLIENT_SECRET"),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            if tr.status_code != 200:
                logger.warning("discord token %s %s", tr.status_code, tr.text[:200])
                return RedirectResponse(url=f"{site}?auth=discord_token", status_code=302)
            tok = tr.json()
            ur = await http.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {tok.get('access_token','')}"})
            if ur.status_code != 200:
                return RedirectResponse(url=f"{site}?auth=discord_user", status_code=302)
            info = ur.json()
    except Exception as e:
        logger.warning("discord oauth error: %s", e)
        return RedirectResponse(url=f"{site}?auth=discord_error", status_code=302)

    did = str(info.get("id") or "")
    email = (info.get("email") or f"{did}@discord.local").lower().strip()
    name = (info.get("global_name") or info.get("username") or f"discord_{did[-5:]}")[:40]
    avatar = info.get("avatar")
    picture = f"https://cdn.discordapp.com/avatars/{did}/{avatar}.png?size=64" if (did and avatar) else None

    u = await db.users.find_one({"$or": [{"discord_id": did}, {"email": email}]})
    if not u:
        u = {
            "id": str(uuid.uuid4()), "email": email, "name": name, "picture": picture,
            "role": "user", "provider": "discord", "discord_id": did,
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(u)
    else:
        await db.users.update_one({"id": u["id"]}, {"$set": {"discord_id": did, "picture": picture or u.get("picture"), "name": u.get("name") or name}})
    resp = RedirectResponse(url=f"{site}?auth=ok", status_code=302)
    _set_cookies(resp, u["id"], email)
    resp.delete_cookie("dc_state", path="/")
    return resp


# ---------------- ŞİFRE SIFIRLAMA (Resend) ----------------
class ForgotBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    email: str
    code: str
    password: str


async def _send_email(to: str, subject: str, html: str) -> bool:
    if not _resend_ok():
        return False
    sender = _env("RESEND_FROM") or "BanbanSports <onboarding@resend.dev>"
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post("https://api.resend.com/emails",
                                headers={"Authorization": f"Bearer {_env('RESEND_API_KEY')}", "Content-Type": "application/json"},
                                json={"from": sender, "to": [to], "subject": subject, "html": html})
            if r.status_code in (200, 201):
                return True
            logger.warning("resend %s %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("resend error: %s", e)
    return False


@router.post("/forgot")
async def forgot(body: ForgotBody, request: Request):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    email = body.email.lower().strip()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçersiz e-posta"}
    if not _resend_ok():
        return {"ok": False, "error": "E-posta servisi henüz yapılandırılmadı — destek için Telegram'dan yazın."}
    u = await db.users.find_one({"email": email})
    # Kullanıcı yoksa da aynı cevabı ver (hesap keşfini engelle)
    if u and u.get("provider", "local") in ("local", "google", "discord"):
        code = f"{secrets.randbelow(1000000):06d}"
        await db.password_resets.update_one({"email": email}, {"$set": {
            "email": email, "code": code, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15), "used": False,
        }}, upsert=True)
        html = f"""<div style='font-family:Arial,sans-serif;background:#07061a;color:#f3f1fa;padding:28px;border-radius:12px'>
        <h2 style='margin:0 0 8px;color:#38e8ff'>banbansports</h2>
        <p style='color:#a79fc4;margin:0 0 18px'>UNDERGROUND HD · Şifre sıfırlama</p>
        <p>Şifre sıfırlama kodun:</p>
        <p style='font-size:30px;letter-spacing:8px;font-weight:700;color:#ff4fd8'>{code}</p>
        <p style='color:#a79fc4'>Kod 15 dakika geçerlidir. Bu isteği sen yapmadıysan bu e-postayı yok say.</p></div>"""
        await _send_email(email, "BanbanSports — şifre sıfırlama kodu", html)
    return {"ok": True, "message": "Kayıtlıysa e-posta adresine 6 haneli kod gönderildi."}


@router.post("/reset")
async def reset(body: ResetBody, response: Response):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    email = body.email.lower().strip()
    if len(body.password) < 6:
        return {"ok": False, "error": "Parola en az 6 karakter olmalı"}
    pr = await db.password_resets.find_one({"email": email})
    if not pr or pr.get("used") or pr.get("code") != body.code.strip():
        return {"ok": False, "error": "Kod geçersiz"}
    exp = pr.get("expires_at")
    if exp and exp.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return {"ok": False, "error": "Kodun süresi dolmuş"}
    u = await db.users.find_one({"email": email})
    if not u:
        return {"ok": False, "error": "Kullanıcı bulunamadı"}
    await db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_resets.update_one({"email": email}, {"$set": {"used": True}})
    _set_cookies(response, u["id"], email)
    return {"ok": True, "user": _public_user(u)}
