"""Vercel Python Function entry — /api/* → FastAPI (backend/app).

vercel.json: rewrites /api/:path* → /api/index ; includeFiles backend/app/**
Serverless'ta arka plan döngüleri yok (BB_SERVERLESS=1), DB bağlantısı lazy.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ["BB_SERVERLESS"] = "1"
# config._required guard'ları import anında patlamasın (env eksikse auth zaten devre dışı kalır)
for _k in ("JWT_SECRET", "ADMIN_PASSWORD"):
    if not os.environ.get(_k, "").strip():
        os.environ[_k] = "vercel-missing-env-placeholder"

from app.main import app  # noqa: E402,F401
