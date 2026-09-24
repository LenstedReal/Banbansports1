"""MongoDB client singleton (Motor) — serverless uyumlu lazy bağlantı."""
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import MONGO_URL, DB_NAME

logger = logging.getLogger("banbansports.db")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_indexed = False


def _connect() -> Optional[AsyncIOMotorDatabase]:
    global _client, _db
    if _db is not None:
        return _db
    if not MONGO_URL.startswith("mongodb"):
        return None
    try:
        _client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=4000)
        _db = _client[DB_NAME]
    except Exception as e:
        logger.warning(f"MongoDB client create failed: {e}")
        _client = None
        _db = None
    return _db


async def init_db() -> Optional[AsyncIOMotorDatabase]:
    global _indexed, _client, _db
    db = _connect()
    if db is None:
        return None
    try:
        await _client.admin.command('ping')
        if not _indexed:
            try:
                await db.livescore_cache.create_index("cached_at", expireAfterSeconds=120)
                await db.users.create_index("email", unique=True)
                await db.users.create_index(
                    "test_expires_at", expireAfterSeconds=0,
                    partialFilterExpression={"test": True},
                )
                await db.predictions.create_index([("user_id", 1), ("match_id", 1)], unique=True)
                await db.chat_messages.create_index("ts")
                await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
                await db.push_subscriptions.create_index("endpoint", unique=True)
                await db.push_subscriptions.create_index("created_at")
            except Exception as e:
                logger.debug(f"index init: {e}")
            _indexed = True
        logger.info("MongoDB connected")
        return db
    except Exception as e:
        logger.warning(f"MongoDB connect failed (cache disabled): {e}")
        _client = None
        _db = None
        return None


def get_db() -> Optional[AsyncIOMotorDatabase]:
    """Lifespan çalışmadıysa (Vercel serverless) ilk çağrıda bağlantı kurulur."""
    return _db if _db is not None else _connect()


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
