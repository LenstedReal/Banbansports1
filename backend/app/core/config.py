"""Centralised env + constants."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / '.env')


def _required(key: str) -> str:
    val = os.environ.get(key, '').strip()
    if not val:
        raise RuntimeError(
            f"Missing required env var: {key}. "
            f"Set it in {ROOT_DIR}/.env or in your deployment environment."
        )
    return val


# --- Required (fail-fast if missing) ---
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'banbansports')
JWT_SECRET = _required('JWT_SECRET')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@banbansports.local').strip().lower()
ADMIN_PASSWORD = _required('ADMIN_PASSWORD')

# --- Optional ---
CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()

SSPORT_EMAIL = os.environ.get('SSPORT_EMAIL', '')
SSPORT_PASSWORD = os.environ.get('SSPORT_PASSWORD', '')
ST11_TOKEN = os.environ.get('ST11_TOKEN', '')
ST11_TMS = os.environ.get('ST11_TMS', '')

# --- Runtime mode ---
ENV = os.environ.get('ENV', 'development').lower()
IS_PRODUCTION = ENV == 'production'

# --- JWT ---
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TTL_MIN = 60 * 24       # 24h
JWT_REFRESH_TTL_DAYS = 30          # 30d

# --- Timing / cache ---
SCORE_BROADCAST_INTERVAL = 30
ST11_REFRESH_INTERVAL = 24 * 60 * 60
HLS_PROXY_TIMEOUT = 30.0
LIVESCORE_FETCH_TIMEOUT = 12.0
ST11_VALIDATE_TIMEOUT = 8.0
LIVESCORE_CACHE_TTL = 30
MATCH_FT_FRESH_WINDOW = 30 * 60
MATCH_FULL_DURATION = 140 * 60
SETTLEMENT_INTERVAL = 300          # 5 dk — tahmin puanlama döngüsü
