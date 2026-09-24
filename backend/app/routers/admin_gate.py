"""Admin Gate — kullanici adi (ADMIN_USERNAME, varsayilan 'adminastor') + ADMIN_PASSWORD ile giris.

Basarili giris ADMIN_EMAIL kullanicisina eslenir ve ayni HttpOnly auth cookie'leri set edilir (JWT).
5 hatali denemede IP 10 dk kilitlenir (Mongo'da tutulur → serverless uyumlu). Denemeler guvenlik loguna yazilir.
Ayrica sifre sifirlama: kod uretilir, admin panelinde gorunur (Telegram ile iletilir).
"""
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..core.config import ADMIN_EMAIL, ADMIN_PASSWORD
from ..core.database import get_db
from ..core.security import hash_password
from .auth import _set_cookies, _public_user  # type: ignore

logger = logging.getLogger("banbansports.admin_gate")
router = APIRouter(prefix="/api/admin-gate", tags=["admin-gate"])

ADMIN_USERNAME = (os.environ.get("ADMIN_USERNAME") or "adminastor").strip().lower()
MAX_FAIL = 5
LOCK_MIN = 10


def _now():
    return datetime.now(timezone.utc)


def _ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


class GateBody(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=200)


@router.get("/status")
async def status(request: Request):
    db = get_db()
    lock = await db.admin_lockouts.find_one({"ip": _ip(request)}) if db is not None else None
    locked = bool(lock and lock.get("until") and lock["until"] > _now())
    return {"locked": locked, "retry_in": int((lock["until"] - _now()).total_seconds()) if locked else 0}


@router.post("/login")
async def login(body: GateBody, request: Request, response: Response):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabani kullanilamiyor")
    ip = _ip(request)
    lock = await db.admin_lockouts.find_one({"ip": ip})
    if lock and lock.get("until") and lock["until"] > _now():
        raise HTTPException(status_code=429, detail=f"Cok fazla hatali deneme. {int((lock['until'] - _now()).total_seconds() // 60) + 1} dk sonra tekrar deneyin")
    ok = secrets.compare_digest(body.username.strip().lower(), ADMIN_USERNAME) and secrets.compare_digest(body.password, ADMIN_PASSWORD)
    if not ok:
        fails = int((lock or {}).get("fails", 0)) + 1
        upd = {"fails": fails, "last_fail": _now()}
        if fails >= MAX_FAIL:
            upd["until"] = _now() + timedelta(minutes=LOCK_MIN)
            upd["fails"] = 0
        await db.admin_lockouts.update_one({"ip": ip}, {"$set": upd}, upsert=True)
        await db.chat_seclog.insert_one({"id": str(uuid.uuid4()), "kind": "admin_login_fail", "detail": {"ip": ip, "user": body.username[:30]}, "created_at": _now()})
        raise HTTPException(status_code=401, detail="Gecersiz kullanici adi veya parola")
    await db.admin_lockouts.delete_one({"ip": ip})
    u = await db.users.find_one({"email": ADMIN_EMAIL})
    if not u:
        # Serverless'ta lifespan seed calismamis olabilir → burada idempotent seed
        from .auth import seed_admin
        await seed_admin()
        u = await db.users.find_one({"email": ADMIN_EMAIL})
    if not u:
        raise HTTPException(status_code=500, detail="Admin hesabi bulunamadi")
    if u.get("role") != "admin":
        await db.users.update_one({"id": u["id"]}, {"$set": {"role": "admin"}})
        u["role"] = "admin"
    _set_cookies(response, u["id"], u["email"])
    await db.chat_seclog.insert_one({"id": str(uuid.uuid4()), "kind": "admin_login_ok", "detail": {"ip": ip}, "created_at": _now()})
    return {"ok": True, "user": _public_user(u)}


# ---------------- sifre sifirlama (kod admin panelinde gorunur) ----------------
class ForgotBody(BaseModel):
    email: str = Field(max_length=120)


class ResetBody(BaseModel):
    email: str = Field(max_length=120)
    code: str = Field(max_length=12)
    new_password: str = Field(min_length=6, max_length=200)


@router.post("/forgot")
async def forgot(body: ForgotBody, request: Request):
    db = get_db()
    email = body.email.lower().strip()
    u = await db.users.find_one({"email": email})
    if u:  # kullanici var/yok bilgisi sizdirilmaz
        code = f"{secrets.randbelow(10**6):06d}"
        await db.password_resets.insert_one({"email": email, "code": code, "used": False, "created_at": _now(), "ip": _ip(request)})
    return {"ok": True, "message": "Talebiniz alindi. Kod, Telegram destek hattindan iletilecek."}


@router.post("/reset")
async def reset(body: ResetBody):
    db = get_db()
    email = body.email.lower().strip()
    r = await db.password_resets.find_one({"email": email, "code": body.code.strip(), "used": False, "created_at": {"$gt": _now() - timedelta(hours=24)}})
    if not r:
        raise HTTPException(status_code=400, detail="Kod gecersiz veya suresi dolmus")
    await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await db.password_resets.update_one({"_id": r["_id"]}, {"$set": {"used": True}})
    return {"ok": True}
