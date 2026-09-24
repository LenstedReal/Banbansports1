"""Topluluk sohbeti v2 — anonim kimlik + moderasyon (PRD-D).

Kimlik: kayitli kullanici (auth cookie) VEYA anonim (device_id + HttpOnly anon JWT + ip hash).
Roller: admin (users.role=admin) > moderator (chat_identities.role=moderator) > user/anon.
Ban: chat_bans {type:user|ip|device, target, until, reason} — sadece sohbeti kisitlar.
Mesaj: chat_log (7 gun TTL), canli gorunum live_limit (75). Bot: lazy cron (recent istegi), atomik kilit.
Guvenlik: tum yetki kontrolleri burada (frontend'e guvenilmez).
"""
import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..core.config import JWT_SECRET, IS_PRODUCTION
from ..core.database import get_db
from .auth import _user_from_request  # type: ignore

logger = logging.getLogger("banbansports.community")
router = APIRouter(prefix="/api/community", tags=["community"])

ANON_COOKIE = "bb_anon"
ANON_TTL = 30 * 24 * 3600
MAX_LEN = 500
RULES = [
    "Hakaret, tehdit ve diğer kullanıcıları hedef alan saldırgan davranışlara izin verilmez.",
    "Spam, flood, otomatik mesaj gönderimi ve sohbeti kullanılamaz hale getiren davranışlar yasaktır.",
    "Reklam, dolandırıcılık, phishing veya kötü amaçlı bağlantı paylaşımı yasaktır.",
    "Başka kullanıcıların kişisel bilgilerini paylaşmayın veya istemeyin.",
    "Aynı mesajı tekrar tekrar göndermek, bot kullanmak veya sistemi suistimal etmek yasaktır.",
    "Moderasyon kararlarını aşmak için yeni hesaplar veya farklı oturumlar kullanılması engellenebilir.",
    "Güvenlik ve moderasyon amacıyla gerekli oturum/ağ bilgileri sınırlı süreyle işlenebilir.",
    "Sohbette siyaset, din, ırk veya mezhep muhabbeti yapmak, provokasyona girmek anında ban sebebidir.",
    "Chatte kasıtlı olarak yanlış skor yazıp milleti trolleyenler veya asılsız maç haberi yayanlar sorgusuz sualsiz uzaklaştırılır.",
    "Başka kaçak/alternatif maç sitelerinin adını anmak, chatte reklamını yapmak veya linkini atmak kesinlikle yasaktır.",
    "Moderatörlerle tartışmaya girmek, chati meşgul edip verilen cezayı sorgulamak yasaktır; modların kararı nihaidir.",
    "Küfür filtresini aşmak için kelimelerin arasına nokta, boşluk veya özel karakter koyarak sansürü delmeye çalışanların hesabı anında kapatılır.",
    "Chatte \"banko kupon\", \"şike var\", \"kasa katlama\" gibi iddialarla milleti dolandırmaya kalkmak veya Telegram/WhatsApp grup linki atmak affedilmez.",
    "Takımlara, taraftar gruplarına, değerlere veya oyunculara yönelik ortamı gerecek holiganca küfürler ve fanatik taşkınlıklar yasaktır.",
    "Kullanıcı adında küfür, argo veya kışkırtıcı kelimeler barındıran hesaplar uyarılmadan sistemden silinir.",
    "Sohbeti felç edecek şekilde sürekli büyük harfle (CAPS LOCK) yazmak veya arka arkaya anlamsız emojiler atıp flood yapmak yasaktır.",
    "Hesabınızın sorumluluğu tamamen size aittir; chat üzerinden hesap satmaya veya takaslamaya çalışanların hesabı kalıcı olarak kapatılır.",
    "Ban yedikten sonra VPN açıp veya yeni hesap alıp tekrar sohbete damlayanların tespit edilen tüm hesapları ve cihaz IP'leri tamamen engellenir.",
    "Yayında anlık donma veya kasma olduğunda chati spamleyip yayıncıya veya siteye küfretmek ban sebebidir; sorun varsa sayfayı yenileyin.",
    "Sohbete +18 cinsel içerikli yazılar yazmak, link veya müstehcen görsel paylaşmaya çalışmak sıfır toleransla cezalandırılır.",
    "Yönetim ekibi; chatte huzuru bozan, ortamı geren veya şüpheli hareketler sergileyen kişileri kurallarda açıkça yazmasa bile inisiyatif kullanarak süresiz uzaklaştırma hakkına sahiptir.",
]

BOT_TEXT = "Bizi takip et ;\nTikTok: https://www.tiktok.com/@lenstedreal\nX: https://x.com/lenstedreal"
BOT_INTERVAL_MIN = 75
DEFAULT_SETTINGS = {
    "_id": "main", "slow_mode_sec": 0, "live_limit": 75, "bot_enabled": True, "bot_interval_min": BOT_INTERVAL_MIN,
    "bot_text": BOT_TEXT, "bot_last_at": None,
}


# ---------------- yardimcilar ----------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request) -> str:
    for h in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(h)
        if v:
            return v.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(f"{JWT_SECRET}:{ip}".encode()).hexdigest()[:32]


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_LEN]


async def _ensure_indexes(db):
    try:
        await db.chat_log.create_index("created_at", expireAfterSeconds=7 * 24 * 3600)
        await db.chat_seclog.create_index("created_at", expireAfterSeconds=7 * 24 * 3600)
        await db.chat_identities.create_index("id", unique=True)
        await db.chat_identities.create_index("device_id")
    except Exception as e:
        logger.debug("index: %s", e)


async def _settings(db) -> dict:
    s = await db.chat_settings.find_one({"_id": "main"})
    if not s:
        await db.chat_settings.update_one({"_id": "main"}, {"$setOnInsert": DEFAULT_SETTINGS}, upsert=True)
        s = dict(DEFAULT_SETTINGS)
    # Eski bot metni (@querte) → yeni format + 75 dk (tek seferlik migrasyon)
    if "querte" in (s.get("bot_text") or "") or "TikTok @lenstedreal" in (s.get("bot_text") or ""):
        await db.chat_settings.update_one({"_id": "main"}, {"$set": {"bot_text": BOT_TEXT, "bot_interval_min": BOT_INTERVAL_MIN}})
        s["bot_text"], s["bot_interval_min"] = BOT_TEXT, BOT_INTERVAL_MIN
    return {**DEFAULT_SETTINGS, **s}


async def _seclog(db, kind: str, detail: dict):
    try:
        await db.chat_seclog.insert_one({"id": str(uuid.uuid4()), "kind": kind, "detail": detail, "created_at": _now()})
    except Exception:
        pass


async def _anon_from_cookie(db, request: Request) -> Optional[dict]:
    tok = request.cookies.get(ANON_COOKIE)
    if not tok:
        return None
    try:
        p = jwt.decode(tok, JWT_SECRET, algorithms=["HS256"])
        if p.get("scope") != "anon":
            return None
        return await db.chat_identities.find_one({"id": p["sub"]})
    except jwt.PyJWTError:
        return None


async def _merge_anon_into_user(db, anon: dict, user_ident: dict) -> None:
    """Misafir giriş yaptığı anda: anonim mesajları + kural onayı hesabına taşınır, misafir kaydı işaretlenir."""
    if not anon or anon.get("kind") != "anon" or anon.get("merged_into"):
        return
    await db.chat_log.update_many(
        {"identity_id": anon["id"]},
        {"$set": {"identity_id": user_ident["id"], "name": user_ident["name"], "kind": "user", "role": user_ident.get("role", "user")}})
    upd = {"last_seen": _now()}
    if anon.get("accepted_rules") and not user_ident.get("accepted_rules"):
        upd["accepted_rules"] = True
        upd["accepted_at"] = anon.get("accepted_at") or _now()
        user_ident["accepted_rules"] = True
    if anon.get("device_id") and not user_ident.get("device_id"):
        upd["device_id"] = anon["device_id"]
        user_ident["device_id"] = anon["device_id"]
    await db.chat_identities.update_one({"id": user_ident["id"]}, {"$set": upd})
    await db.chat_identities.update_one({"id": anon["id"]}, {"$set": {"merged_into": user_ident["id"], "merged_at": _now()}})
    await _seclog(db, "anon_merged", {"anon": anon["id"], "user": user_ident["id"]})


async def _identity(request: Request, response: Optional[Response] = None, device_id: str = "") -> Optional[dict]:
    """Kayitli kullanici > anon cookie > (response varsa) yeni anon olustur."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabani kullanilamiyor")
    ip = _client_ip(request)
    ip_h = _ip_hash(ip)
    user = await _user_from_request(request)
    if user:
        ident = await db.chat_identities.find_one({"id": user["id"]})
        if not ident:
            ident = {"id": user["id"], "kind": "user", "name": user.get("name") or user["email"].split("@")[0],
                     "role": "admin" if user.get("role") == "admin" else "user", "device_id": device_id, "ip_hash": ip_h, "ip_last": ip,
                     "accepted_rules": False, "created_at": _now(), "last_seen": _now()}
            await db.chat_identities.insert_one(ident)
        else:
            upd = {"last_seen": _now(), "ip_hash": ip_h, "ip_last": ip}
            if user.get("role") == "admin":
                upd["role"] = "admin"
            await db.chat_identities.update_one({"id": ident["id"]}, {"$set": upd})
            ident.update(upd)
        anon = await _anon_from_cookie(db, request)
        if anon:
            await _merge_anon_into_user(db, anon, ident)
            if response is not None:
                response.delete_cookie(ANON_COOKIE, path="/")
        return ident
    tok = request.cookies.get(ANON_COOKIE)
    if tok:
        try:
            p = jwt.decode(tok, JWT_SECRET, algorithms=["HS256"])
            if p.get("scope") == "anon":
                ident = await db.chat_identities.find_one({"id": p["sub"]})
                if ident and not ident.get("merged_into"):
                    await db.chat_identities.update_one({"id": ident["id"]}, {"$set": {"last_seen": _now(), "ip_hash": ip_h, "ip_last": ip}})
                    return ident
        except jwt.PyJWTError:
            pass
    if response is None:
        return None
    ident = None
    if device_id:
        ident = await db.chat_identities.find_one({"device_id": device_id, "kind": "anon", "merged_into": {"$exists": False}})
    if not ident:
        aid = str(uuid.uuid4())
        ident = {"id": aid, "kind": "anon", "name": f"Misafir-{aid[:4].upper()}", "role": "anon", "device_id": device_id[:64],
                 "ip_hash": ip_h, "ip_last": ip, "accepted_rules": False, "created_at": _now(), "last_seen": _now()}
        await db.chat_identities.insert_one(ident)
    now = int(time.time())
    tok = jwt.encode({"sub": ident["id"], "scope": "anon", "iat": now, "exp": now + ANON_TTL}, JWT_SECRET, algorithm="HS256")
    response.set_cookie(ANON_COOKIE, tok, max_age=ANON_TTL, httponly=True, secure=IS_PRODUCTION, samesite="lax", path="/")
    return ident


async def _active_ban(db, ident: dict) -> Optional[dict]:
    now = _now()
    q = {"$or": [{"type": "user", "target": ident["id"]}, {"type": "ip", "target": ident.get("ip_hash")}]}
    if ident.get("device_id"):
        q["$or"].append({"type": "device", "target": ident["device_id"]})
    async for b in db.chat_bans.find(q):
        if b.get("until") is None or b["until"] > now:
            return b
    return None


def _is_mod(ident: dict) -> bool:
    return ident.get("role") in ("admin", "moderator")


async def _require_admin(request: Request) -> dict:
    user = await _user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Giris gerekli")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnizca admin")
    return user


def _pub_msg(m: dict) -> dict:
    return {"id": m["id"], "text": m["text"], "name": m["name"], "role": m.get("role", "anon"), "kind": m.get("kind", "anon"),
            "identity_id": m.get("identity_id", ""), "created_at": m["created_at"].isoformat(), "bot": bool(m.get("bot"))}


def _pub_ident(i: dict, ban: Optional[dict] = None) -> dict:
    return {"id": i["id"], "name": i["name"], "role": i.get("role", "anon"), "kind": i.get("kind", "anon"),
            "accepted_rules": bool(i.get("accepted_rules")), "banned": bool(ban), "ban_reason": (ban or {}).get("reason", ""),
            "ban_until": ban["until"].isoformat() if ban and ban.get("until") else None}


# ---------------- public ----------------
class IdentityBody(BaseModel):
    device_id: str = Field(default="", max_length=64)


@router.post("/identity")
async def identity(body: IdentityBody, request: Request, response: Response):
    db = get_db()
    await _ensure_indexes(db)
    ident = await _identity(request, response, body.device_id)
    ban = await _active_ban(db, ident)
    s = await _settings(db)
    return {"ok": True, "identity": _pub_ident(ident, ban), "slow_mode_sec": s["slow_mode_sec"], "rules": RULES}


@router.get("/rules")
async def rules():
    db = get_db()
    cnt = await db.chat_identities.count_documents({"accepted_rules": True}) if db is not None else 0
    return {"rules": RULES, "accepted_count": cnt}


@router.post("/rules/accept")
async def accept_rules(request: Request):
    db = get_db()
    ident = await _identity(request)
    if not ident:
        raise HTTPException(status_code=401, detail="Kimlik yok")
    await db.chat_identities.update_one({"id": ident["id"]}, {"$set": {"accepted_rules": True, "accepted_at": _now()}})
    cnt = await db.chat_identities.count_documents({"accepted_rules": True})
    return {"ok": True, "accepted_count": cnt}


async def _maybe_bot(db, s: dict):
    if not s.get("bot_enabled"):
        return
    interval = timedelta(minutes=max(5, int(s.get("bot_interval_min") or 45)))
    threshold = _now() - interval
    r = await db.chat_settings.find_one_and_update(
        {"_id": "main", "$or": [{"bot_last_at": None}, {"bot_last_at": {"$lt": threshold}}]},
        {"$set": {"bot_last_at": _now()}})
    if r is not None:  # kilidi biz aldik
        await db.chat_log.insert_one({"id": str(uuid.uuid4()), "text": s["bot_text"][:MAX_LEN], "name": "BANBAN BOT", "role": "bot",
                                      "kind": "bot", "identity_id": "bot", "bot": True, "created_at": _now()})


@router.get("/recent")
async def recent(request: Request, since: str = ""):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Veritabani kullanilamiyor")
    s = await _settings(db)
    await _maybe_bot(db, s)
    ident = await _identity(request)
    q = {}
    if since:
        try:
            q = {"created_at": {"$gt": datetime.fromisoformat(since.replace("Z", "+00:00"))}}
        except ValueError:
            q = {}
    limit = int(s.get("live_limit") or 75)
    cur = db.chat_log.find(q).sort("created_at", -1).limit(limit)
    msgs = [_pub_msg(m) async for m in cur]
    msgs.reverse()
    online = await db.chat_identities.count_documents({"last_seen": {"$gt": _now() - timedelta(minutes=2)}})
    return {"messages": msgs, "online": online, "slow_mode_sec": s["slow_mode_sec"], "live_limit": limit,
            "me": _pub_ident(ident, await _active_ban(db, ident)) if ident else None}


class SendBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_LEN)


_last_sent: dict[str, float] = {}


@router.post("/send")
async def send(body: SendBody, request: Request):
    db = get_db()
    ident = await _identity(request)
    if not ident:
        raise HTTPException(status_code=401, detail="Once kimlik olusturun")
    ban = await _active_ban(db, ident)
    if ban:
        raise HTTPException(status_code=403, detail="Topluluk kurallarina uymadiginiz icin banlandiniz")
    if not ident.get("accepted_rules"):
        raise HTTPException(status_code=403, detail="Once topluluk kurallarini onaylayin")
    text = _clean(body.text)
    if not text:
        raise HTTPException(status_code=400, detail="Bos mesaj")
    s = await _settings(db)
    now = time.time()
    gap = max(int(s.get("slow_mode_sec") or 0), 2) if not _is_mod(ident) else 0
    last = _last_sent.get(ident["id"], 0)
    if gap and now - last < gap:
        raise HTTPException(status_code=429, detail=f"Yavas mod: {int(gap - (now - last)) + 1} sn bekleyin")
    _last_sent[ident["id"]] = now
    doc = {"id": str(uuid.uuid4()), "text": text, "name": ident["name"], "role": ident.get("role", "anon"), "kind": ident.get("kind", "anon"),
           "identity_id": ident["id"], "ip_hash": ident.get("ip_hash"), "device_id": ident.get("device_id", ""), "created_at": _now()}
    await db.chat_log.insert_one(doc)
    return {"ok": True, "message": _pub_msg(doc)}


@router.delete("/message/{message_id}")
async def delete_message(message_id: str, request: Request):
    db = get_db()
    ident = await _identity(request)
    if not ident:
        raise HTTPException(status_code=401, detail="Giris gerekli")
    if not _is_mod(ident):
        raise HTTPException(status_code=403, detail="Yetki yok")
    r = await db.chat_log.delete_one({"id": message_id})
    await _seclog(db, "delete_message", {"by": ident["id"], "message_id": message_id})
    return {"ok": r.deleted_count == 1}


# ---------------- admin / moderasyon (yalnizca admin) ----------------
@router.get("/admin/identities")
async def admin_identities(request: Request, limit: int = 200):
    await _require_admin(request)
    db = get_db()
    out = []
    async for i in db.chat_identities.find({"merged_into": {"$exists": False}}).sort("last_seen", -1).limit(min(limit, 500)):
        out.append({**_pub_ident(i, await _active_ban(db, i)), "device_id": i.get("device_id", "")[:12], "ip_hash": (i.get("ip_hash") or "")[:10],
                    "ip": i.get("ip_last") or "", "last_seen": i["last_seen"].isoformat() if i.get("last_seen") else None})
    return {"identities": out}


class ModBody(BaseModel):
    on: bool = True


@router.post("/admin/mod/{identity_id}")
async def admin_mod(identity_id: str, body: ModBody, request: Request):
    admin = await _require_admin(request)
    db = get_db()
    i = await db.chat_identities.find_one({"id": identity_id})
    if not i:
        raise HTTPException(status_code=404, detail="Kimlik yok")
    if i.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admin rolu degistirilemez")
    role = "moderator" if body.on else ("user" if i.get("kind") == "user" else "anon")
    await db.chat_identities.update_one({"id": identity_id}, {"$set": {"role": role}})
    await _seclog(db, "mod_change", {"by": admin["id"], "target": identity_id, "role": role})
    return {"ok": True, "role": role}


class BanBody(BaseModel):
    type: str = Field(pattern="^(user|ip|device)$")
    target: str = Field(min_length=1, max_length=80)  # user -> identity id ; ip/device -> identity id (hash/device oradan alinir)
    minutes: int = Field(default=0, ge=0, le=60 * 24 * 365)
    reason: str = Field(default="Topluluk kurallarina aykiri davranis", max_length=200)


@router.post("/admin/ban")
async def admin_ban(body: BanBody, request: Request):
    admin = await _require_admin(request)
    db = get_db()
    i = await db.chat_identities.find_one({"id": body.target})
    if not i:
        raise HTTPException(status_code=404, detail="Kimlik yok")
    if i.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admin banlanamaz")
    target = i["id"] if body.type == "user" else (i.get("ip_hash") if body.type == "ip" else i.get("device_id"))
    if not target:
        raise HTTPException(status_code=400, detail="Hedef bilgisi yok")
    ban = {"id": str(uuid.uuid4()), "type": body.type, "target": target, "identity_id": i["id"], "name": i["name"],
           "until": (_now() + timedelta(minutes=body.minutes)) if body.minutes else None, "reason": body.reason,
           "by": admin["id"], "created_at": _now()}
    await db.chat_bans.insert_one(ban)
    await _seclog(db, "ban", {"by": admin["id"], "type": body.type, "identity": i["id"], "minutes": body.minutes, "reason": body.reason})
    ban.pop("_id", None)
    return {"ok": True, "ban": {**ban, "until": ban["until"].isoformat() if ban["until"] else None, "created_at": ban["created_at"].isoformat()}}


@router.get("/admin/bans")
async def admin_bans(request: Request):
    await _require_admin(request)
    db = get_db()
    out = []
    async for b in db.chat_bans.find({}).sort("created_at", -1).limit(300):
        out.append({"id": b["id"], "type": b["type"], "name": b.get("name", ""), "identity_id": b.get("identity_id", ""), "reason": b.get("reason", ""),
                    "until": b["until"].isoformat() if b.get("until") else None, "created_at": b["created_at"].isoformat(),
                    "active": b.get("until") is None or b["until"] > _now()})
    return {"bans": out}


@router.post("/admin/unban/{ban_id}")
async def admin_unban(ban_id: str, request: Request):
    admin = await _require_admin(request)
    db = get_db()
    r = await db.chat_bans.delete_one({"id": ban_id})
    await _seclog(db, "unban", {"by": admin["id"], "ban_id": ban_id})
    return {"ok": r.deleted_count == 1}


class SettingsBody(BaseModel):
    slow_mode_sec: Optional[int] = Field(default=None, ge=0, le=600)
    live_limit: Optional[int] = Field(default=None, ge=10, le=300)
    bot_enabled: Optional[bool] = None
    bot_interval_min: Optional[int] = Field(default=None, ge=5, le=1440)
    bot_text: Optional[str] = Field(default=None, max_length=MAX_LEN)


@router.get("/admin/settings")
async def admin_settings(request: Request):
    await _require_admin(request)
    s = await _settings(get_db())
    s.pop("_id", None)
    if s.get("bot_last_at"):
        s["bot_last_at"] = s["bot_last_at"].isoformat()
    return {"settings": s}


@router.post("/admin/settings")
async def admin_settings_set(body: SettingsBody, request: Request):
    admin = await _require_admin(request)
    db = get_db()
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.chat_settings.update_one({"_id": "main"}, {"$set": upd}, upsert=True)
        await _seclog(db, "settings", {"by": admin["id"], **upd})
    return {"ok": True, "settings": {k: v for k, v in (await _settings(db)).items() if k not in ("_id", "bot_last_at")}}


@router.get("/admin/log")
async def admin_log(request: Request, limit: int = 200):
    await _require_admin(request)
    db = get_db()
    out = [{"id": x["id"], "kind": x["kind"], "detail": x.get("detail", {}), "created_at": x["created_at"].isoformat()}
           async for x in db.chat_seclog.find({}).sort("created_at", -1).limit(min(limit, 500))]
    return {"log": out}


@router.get("/admin/messages")
async def admin_messages(request: Request, limit: int = 300):
    """7 gunluk tam kayit (silinmez, sadece TTL)."""
    await _require_admin(request)
    db = get_db()
    out = [_pub_msg(m) async for m in db.chat_log.find({}).sort("created_at", -1).limit(min(limit, 1000))]
    return {"messages": out}


@router.get("/admin/reset-requests")
async def admin_reset_requests(request: Request):
    await _require_admin(request)
    db = get_db()
    out = [{"email": r["email"], "code": r["code"], "created_at": r["created_at"].isoformat(), "used": bool(r.get("used"))}
           async for r in db.password_resets.find({}).sort("created_at", -1).limit(100)]
    return {"requests": out}
