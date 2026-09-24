"""Supervisor entry shim — re-exports the FastAPI app from app/main.py."""
from app.main import app  # noqa: F401
