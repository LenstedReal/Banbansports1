"""Password hashing + JWT helpers."""
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from .config import JWT_SECRET, JWT_ALGORITHM, JWT_ACCESS_TTL_MIN, JWT_REFRESH_TTL_DAYS


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        'sub': user_id,
        'email': email,
        'type': 'access',
        'exp': datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TTL_MIN),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        'sub': user_id,
        'type': 'refresh',
        'exp': datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TTL_DAYS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
