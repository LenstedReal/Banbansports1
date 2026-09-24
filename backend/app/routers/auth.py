"""Auth — email/password + Google ID Token verification."""
import logging
import re
import uuid
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..core.config import (
    JWT_ACCESS_TTL_MIN, JWT_REFRESH_TTL_DAYS, GOOGLE_CLIENT_ID,
    ADMIN_EMAIL, ADMIN_PASSWORD, IS_PRODUCTION,
)
from ..core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from ..core.database import get_db

logger = logging.getLogger("banbansports.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Loose email validator — accepts anything that looks vaguely like email@host.tld
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ---------- Pydantic models ----------
class RegisterBody(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


class GoogleBody(BaseModel):
    id_token: str


# ---------- Helpers ----------
def _public_user(u: dict) -> dict:
    return {
        "id": str(u.get("id") or u.get("_id") or ""),
        "email": u.get("email", ""),
        "name": u.get("name", ""),
        "role": u.get("role", "user"),
        "picture": u.get("picture") or None,
    }


def _set_cookies(resp: Response, user_id: str, email: str):
    access = create_access_token(user_id, email)
    refresh = create_refresh_token(user_id)
    # In production we need SameSite=None+Secure so the cookie is sent from the
    # Vercel-hosted frontend to a different-origin backend. In dev (http://localhost)
    # browsers reject SameSite=None+Secure cookies, so use Lax + non-secure.
    common = dict(
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        path="/",
    )
    resp.set_cookie("access_token", access, max_age=JWT_ACCESS_TTL_MIN * 60, **common)
    resp.set_cookie("refresh_token", refresh, max_age=JWT_REFRESH_TTL_DAYS * 86400, **common)


def _clear_cookies(resp: Response):
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/")


async def _user_from_request(request: Request) -> Optional[dict]:
    """Read access cookie (or Bearer header), decode, fetch user."""
    db = get_db()
    if db is None:
        return None
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        u = await db.users.find_one({"id": user_id})
        return u
    except Exception:
        return None


# ---------- Endpoints ----------
@router.post("/register")
async def register(body: RegisterBody, response: Response):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    email = body.email.lower().strip()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Geçersiz e-posta adresi"}
    if len(body.password) < 6:
        return {"ok": False, "error": "Parola en az 6 karakter olmalı"}
    existing = await db.users.find_one({"email": email})
    if existing:
        return {"ok": False, "error": "Bu e-posta zaten kayıtlı"}
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": email,
        "name": (body.name or email.split("@")[0]).strip()[:40],
        "password_hash": hash_password(body.password),
        "role": "user",
        "provider": "local",
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    _set_cookies(response, user_id, email)
    return {"ok": True, "user": _public_user(doc)}


@router.post("/login")
async def login(body: LoginBody, response: Response):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    email = body.email.lower().strip()
    u = await db.users.find_one({"email": email})
    if not u or not u.get("password_hash"):
        return {"ok": False, "error": "Geçersiz e-posta veya parola"}
    if not verify_password(body.password, u["password_hash"]):
        return {"ok": False, "error": "Geçersiz e-posta veya parola"}
    _set_cookies(response, u["id"], email)
    return {"ok": True, "user": _public_user(u)}


@router.post("/google")
async def google_login(body: GoogleBody, response: Response):
    """Verify the ID token using Google's tokeninfo endpoint (no SDK needed)."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabanı kullanılamıyor")
    try:
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={body.id_token}")
            if r.status_code != 200:
                return {"ok": False, "error": "Google jeton doğrulanamadı"}
            info = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Google bağlantı hatası: {e}"}

    if GOOGLE_CLIENT_ID and info.get("aud") != GOOGLE_CLIENT_ID:
        return {"ok": False, "error": "Geçersiz Google istemcisi"}
    if info.get("email_verified") not in ("true", True):
        return {"ok": False, "error": "Google e-postası doğrulanmamış"}

    email = (info.get("email") or "").lower().strip()
    if not email:
        return {"ok": False, "error": "Google e-postası alınamadı"}

    u = await db.users.find_one({"email": email})
    if not u:
        user_id = str(uuid.uuid4())
        u = {
            "id": user_id,
            "email": email,
            "name": info.get("name") or email.split("@")[0],
            "picture": info.get("picture"),
            "role": "user",
            "provider": "google",
            "google_sub": info.get("sub"),
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(u)
    else:
        await db.users.update_one({"id": u["id"]}, {"$set": {
            "name": u.get("name") or info.get("name"),
            "picture": info.get("picture") or u.get("picture"),
            "google_sub": info.get("sub"),
        }})
    _set_cookies(response, u["id"], email)
    return {"ok": True, "user": _public_user(u)}


@router.post("/logout")
async def logout(response: Response):
    _clear_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    u = await _user_from_request(request)
    if not u:
        return {"user": None}
    return {"user": _public_user(u)}


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    rt = request.cookies.get("refresh_token")
    if not rt:
        return {"ok": False, "error": "no_refresh"}
    try:
        payload = decode_token(rt)
        if payload.get("type") != "refresh":
            return {"ok": False, "error": "wrong_type"}
        user_id = payload["sub"]
        db = get_db()
        u = await db.users.find_one({"id": user_id}) if db is not None else None
        if not u:
            return {"ok": False, "error": "no_user"}
        _set_cookies(response, user_id, u["email"])
        return {"ok": True}
    except Exception:
        return {"ok": False, "error": "invalid"}


async def seed_admin():
    """Idempotent admin seed (called from main lifespan)."""
    db = get_db()
    if db is None:
        return
    # ADMIN_PASSWORD set edilmemişse admin oluşturma. Lokal dev'de
    # JWT_SECRET de boşken admin paneline ihtiyaç olmayabilir.
    if not ADMIN_PASSWORD:
        logger.warning("ADMIN_PASSWORD env set değil — admin seed atlandı.")
        return
    try:
        # Only seed if admin user does not exist. Do NOT auto-reset password on
        # subsequent boots — that would let anyone reading the running config
        # walk in. To rotate the admin password, delete the user document first.
        existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
        if not existing:
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL.lower(),
                "name": "Admin",
                "password_hash": hash_password(ADMIN_PASSWORD),
                "role": "admin",
                "provider": "local",
                "created_at": datetime.now(timezone.utc),
            })
            logger.info(f"Admin seeded: {ADMIN_EMAIL}")
    except Exception as e:
        logger.warning(f"seed_admin fail: {e}")


# Helper for other routers
async def current_user_or_401(request: Request) -> dict:
    u = await _user_from_request(request)
    if not u:
        raise HTTPException(status_code=401, detail="Giriş gerekli")
    return u
