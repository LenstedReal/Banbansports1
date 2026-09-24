"""Iteration 6 regression tests: boxoffice TR model, stream-auth, movies, vercel entry."""
import os
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://yasal-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok" or j.get("ok") is True


def test_boxoffice_tr_range():
    r = requests.get(f"{API}/boxoffice", timeout=20)
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    local = j.get("local") or {}
    tr = local.get("TRY") or local.get("try") or {}
    assert tr, f"local.TRY missing: {j}"
    viewers = tr.get("viewers")
    assert viewers is not None
    assert 1_500_000 <= viewers <= 2_500_000, f"TR viewers out of range: {viewers}"
    assert tr.get("gross_native") is not None and tr.get("gross_usd") is not None
    assert tr.get("fx") is not None or tr.get("label")
    label = (tr.get("label") or "").upper()
    assert "TÜRK" in label or "TURK" in label or "TR" in label


def test_stream_auth_success():
    r = requests.post(f"{API}/stream-auth/login",
                      json={"username": "lenstedreal_marka", "password": "zirvedeyiz"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True
    assert j.get("token_dub") and j.get("token_sub")


def test_stream_auth_wrong_password():
    r = requests.post(f"{API}/stream-auth/login",
                      json={"username": "lenstedreal_marka", "password": "wrong"}, timeout=15)
    assert r.status_code == 401


def test_movies_list_has_spiderman():
    r = requests.get(f"{API}/movies", timeout=20)
    assert r.status_code == 200
    j = r.json()
    items = j if isinstance(j, list) else (j.get("items") or j.get("movies") or [])
    assert len(items) >= 1
    titles = " ".join([str(it.get("title", "")) for it in items]).lower()
    assert "spider" in titles or any("badge" in it for it in items)


def test_scores_top():
    r = requests.get(f"{API}/scores/top?n=5", timeout=20)
    assert r.status_code == 200


def test_livescore_today():
    r = requests.get(f"{API}/livescore/today", timeout=20)
    assert r.status_code == 200


def test_vercel_entry_routes():
    """Simulate Vercel entry import and check registered routes include stream-auth, boxoffice, sponsors."""
    script = (
        "import os, sys;"
        "os.environ.setdefault('MONGO_URL','mongodb://localhost:27017');"
        "sys.path.insert(0,'/app/frontend');"
        "from api.index import app;"
        "paths=[r.path for r in app.routes];"
        "print('\\n'.join(paths))"
    )
    out = subprocess.run(["python3", "-c", script], capture_output=True, text=True, timeout=60,
                         cwd="/app/frontend")
    assert out.returncode == 0, f"import failed: {out.stderr}"
    paths = out.stdout
    assert "/api/stream-auth" in paths or "stream-auth" in paths, paths
    assert "/api/boxoffice" in paths or "boxoffice" in paths, paths
    assert "sponsors" in paths, f"sponsors router not loaded: {paths}"


def test_backend_and_vercel_boxoffice_match():
    """frontend/_backend_app/routers/boxoffice.py must equal backend/app/routers/boxoffice.py"""
    out = subprocess.run(
        ["diff", "-q", "/app/backend/app/routers/boxoffice.py",
         "/app/frontend/_backend_app/routers/boxoffice.py"],
        capture_output=True, text=True)
    assert out.returncode == 0, f"boxoffice files differ: {out.stdout}"
