"""Chat — WebSocket-based real-time messaging with HTTP polling fallback.

WS endpoint: /api/ws/chat
HTTP fallback: GET /api/chat/recent + POST /api/chat/send
"""
import uuid
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..core.database import get_db
from ..core.security import decode_token
from .auth import current_user_or_401  # type: ignore

logger = logging.getLogger("banbansports.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendBody(BaseModel):
    text: str


# --------------------- Rate limit (per user, in-memory) ---------------------
_recent: dict[str, list[float]] = {}


def _rate_ok(user_id: str) -> bool:
    now = time.time()
    hits = [t for t in _recent.get(user_id, []) if now - t < 30]
    if len(hits) >= 5:
        return False
    hits.append(now)
    _recent[user_id] = hits[-10:]
    return True


def _clean(text: str) -> str:
    text = ''.join(ch for ch in text if ch == '\n' or ord(ch) >= 32)
    return text.strip()[:300]


# --------------------- WebSocket manager (chat-specific) ---------------------
class ChatConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for c in self.active:
            try:
                await c.send_json(payload)
            except Exception:
                dead.append(c)
        for c in dead:
            self.disconnect(c)


chat_manager = ChatConnectionManager()


async def _persist_and_broadcast(user: dict, text: str) -> Optional[dict]:
    """Mesajı DB'ye yaz + tüm WS client'lara yayınla. Yeni mesaj objesi döner."""
    db = get_db()
    if db is None:
        return None
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": user.get("name", "Anonim"),
        "role": user.get("role", "user"),
        "text": text,
        "ts": datetime.now(timezone.utc),
    }
    await db.chat_messages.insert_one(doc)
    # Yaşlanan mesajları temizle (24h+)
    await db.chat_messages.delete_many(
        {"ts": {"$lt": datetime.now(timezone.utc) - timedelta(hours=24)}}
    )
    payload = {
        "type": "chat_message",
        "id": doc["id"],
        "user_id": doc["user_id"],
        "name": doc["name"],
        "role": doc["role"],
        "text": doc["text"],
        "ts": doc["ts"].isoformat(),
    }
    await chat_manager.broadcast(payload)
    return payload


# --------------------- HTTP polling fallback ---------------------
@router.get("/recent")
async def recent(limit: int = 50):
    db = get_db()
    if db is None:
        return {"messages": []}
    limit = max(1, min(int(limit), 100))
    cursor = db.chat_messages.find({}).sort("ts", -1).limit(limit)
    msgs: List[dict] = []
    async for m in cursor:
        msgs.append({
            "id": m.get("id") or str(m.get("_id")),
            "user_id": m.get("user_id", ""),
            "name": m.get("name", "Anonim"),
            "role": m.get("role", "user"),
            "text": m.get("text", ""),
            "ts": (m.get("ts") or datetime.now(timezone.utc)).isoformat(),
        })
    msgs.reverse()
    return {"messages": msgs}


@router.post("/send")
async def send(body: SendBody, request: Request):
    user = await current_user_or_401(request)
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    text = _clean(body.text)
    if not text:
        return {"ok": False, "error": "Boş mesaj"}
    if not _rate_ok(user["id"]):
        return {"ok": False, "error": "Çok hızlı yazıyorsun, biraz nefes al"}
    try:
        payload = await _persist_and_broadcast(user, text)
        return {"ok": True, "message": payload}
    except Exception as e:
        return {"ok": False, "error": f"DB: {e}"}


# --------------------- Admin: delete message ---------------------
@router.delete("/message/{message_id}")
async def delete_message(message_id: str, request: Request):
    user = await current_user_or_401(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca admin")
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    r = await db.chat_messages.delete_one({"id": message_id})
    if r.deleted_count:
        await chat_manager.broadcast({"type": "chat_delete", "id": message_id})
    return {"ok": True, "deleted": r.deleted_count}


# --------------------- WebSocket endpoint ---------------------
async def _user_from_ws(ws: WebSocket) -> Optional[dict]:
    """WS cookie veya query token üzerinden user çöz."""
    token = ws.cookies.get("access_token") or ws.query_params.get("token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    db = get_db()
    if db is None:
        return None
    user = await db.users.find_one({"id": payload.get("sub")})
    return user


@router.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    await chat_manager.connect(ws)
    try:
        # İlk bağlanan son 30 mesajı görsün
        db = get_db()
        if db is not None:
            cursor = db.chat_messages.find({}).sort("ts", -1).limit(30)
            recent_msgs = []
            async for m in cursor:
                recent_msgs.append({
                    "id": m.get("id"),
                    "user_id": m.get("user_id", ""),
                    "name": m.get("name", "Anonim"),
                    "role": m.get("role", "user"),
                    "text": m.get("text", ""),
                    "ts": (m.get("ts") or datetime.now(timezone.utc)).isoformat(),
                })
            recent_msgs.reverse()
            await ws.send_json({"type": "chat_history", "messages": recent_msgs})

        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
                continue
            try:
                msg = json.loads(data)
            except Exception:
                continue
            if msg.get("type") == "send":
                user = await _user_from_ws(ws)
                if not user:
                    await ws.send_json({"type": "error", "error": "Giriş yap"})
                    continue
                text = _clean(msg.get("text", ""))
                if not text:
                    continue
                if not _rate_ok(user["id"]):
                    await ws.send_json({"type": "error", "error": "Çok hızlı yazıyorsun"})
                    continue
                await _persist_and_broadcast(user, text)
    except WebSocketDisconnect:
        chat_manager.disconnect(ws)
    except Exception as e:
        logger.warning(f"chat ws error: {e}")
        chat_manager.disconnect(ws)
