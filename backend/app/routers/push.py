"""Web Push notifications — VAPID-based browser push.

Endpoints:
  POST /api/push/subscribe    → tarayıcıdan VAPID subscription kaydet
  POST /api/push/unsubscribe  → subscription sil
  GET  /api/push/vapid-key    → public VAPID anahtarını dön (frontend için)

Push gönderimi: gerçek push işlemi `pywebpush` ile yapılır. Bu MVP için sadece
subscription saklama + admin'in trigger edebileceği basit `send` endpoint'i sunar.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from ..core.database import get_db
from ..core.config import IS_PRODUCTION
import os

logger = logging.getLogger("banbansports.push")
router = APIRouter(prefix="/api/push", tags=["push"])

VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '').strip()
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:admin@banbansports.local').strip()


class SubscribeBody(BaseModel):
    endpoint: str
    keys: dict  # { p256dh: ..., auth: ... }


class UnsubscribeBody(BaseModel):
    endpoint: str


@router.get("/vapid-key")
async def get_vapid_key():
    """Public anahtarı frontend'e ver (yoksa boş döner — frontend push'u devre dışı bırakır)."""
    return {"public_key": VAPID_PUBLIC_KEY or None, "configured": bool(VAPID_PUBLIC_KEY)}


@router.post("/subscribe")
async def subscribe(body: SubscribeBody, request: Request):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    # Optional: bağlı kullanıcıyı da kaydet (anonim de OK)
    user_id = None
    try:
        from .auth import _user_from_request  # type: ignore
        u = await _user_from_request(request)
        if u:
            user_id = u["id"]
    except Exception:
        pass

    doc = {
        "endpoint": body.endpoint,
        "keys": body.keys,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "ua": request.headers.get("user-agent", "")[:200],
    }
    # Idempotent upsert
    await db.push_subscriptions.update_one(
        {"endpoint": body.endpoint},
        {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True}


@router.post("/unsubscribe")
async def unsubscribe(body: UnsubscribeBody):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.push_subscriptions.delete_one({"endpoint": body.endpoint})
    return {"ok": True, "deleted": r.deleted_count}


# --------------- Admin: manual broadcast ---------------
class SendBody(BaseModel):
    title: str
    body: str
    url: Optional[str] = "/"


@router.post("/send")
async def admin_push_send(body: SendBody, request: Request):
    from .auth import current_user_or_401  # type: ignore
    user = await current_user_or_401(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca admin")
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return {"ok": False, "error": "VAPID anahtarları yapılandırılmamış (VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY env)"}

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {"ok": False, "error": "pywebpush yüklü değil — requirements.txt'ye ekleyin"}

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    payload = {"title": body.title, "body": body.body, "url": body.url or "/"}
    sent = failed = 0
    dead = []
    async for sub in db.push_subscriptions.find({}):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": sub["keys"],
                },
                data=__import__('json').dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
                ttl=86400,
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            # 410 Gone → subscription dead, sil
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 410:
                dead.append(sub["endpoint"])
        except Exception:
            failed += 1
    if dead:
        await db.push_subscriptions.delete_many({"endpoint": {"$in": dead}})
    return {"ok": True, "sent": sent, "failed": failed, "cleaned": len(dead)}
