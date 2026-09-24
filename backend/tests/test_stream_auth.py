"""Tests for /api/stream-auth/* endpoints and movies/health regression."""
import os
import time
import base64
import json

import pytest
import requests

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
API = f"{BASE_URL}/api"

DUMMY_TS = "XXXX.DUMMY.TOKEN.XXXX"
USER = "lenstedreal_marka"
PASS = "zirvedeyiz"


def _decode_jwt_payload(tok: str) -> dict:
    part = tok.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


# --- Config ---
def test_config():
    r = requests.get(f"{API}/stream-auth/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["turnstile_site_key"] == "1x00000000000000000000AA"
    assert d["token_ttl"] == 1800


# --- Login ---
def test_login_missing_turnstile():
    r = requests.post(f"{API}/stream-auth/login",
                      json={"username": USER, "password": PASS, "turnstile_token": ""},
                      timeout=15)
    assert r.status_code == 400


def test_login_wrong_creds():
    r = requests.post(f"{API}/stream-auth/login",
                      json={"username": "x", "password": "y", "turnstile_token": DUMMY_TS},
                      timeout=15)
    assert r.status_code == 401


def test_login_success_and_claims():
    r = requests.post(f"{API}/stream-auth/login",
                      json={"username": USER, "password": PASS, "turnstile_token": DUMMY_TS},
                      timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["expires_in"] == 1800
    assert d["token_dub"] and d["token_sub"]
    p_dub = _decode_jwt_payload(d["token_dub"])
    p_sub = _decode_jwt_payload(d["token_sub"])
    assert p_dub["iss"] == "banbansports"
    assert p_dub["scope"] == "hls"
    assert p_dub["src"] == "dub"
    assert p_sub["src"] == "sub"
    assert p_dub["sid"] == p_sub["sid"]
    assert p_dub["exp"] - p_dub["iat"] == 1800
    # stash for later tests
    pytest.token_dub = d["token_dub"]
    pytest.token_sub = d["token_sub"]
    pytest.sid = p_dub["sid"]


# --- Refresh ---
def test_refresh_valid():
    tok = getattr(pytest, "token_dub", None)
    if not tok:
        pytest.skip("no token from login")
    r = requests.post(f"{API}/stream-auth/refresh", json={"token": tok}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["token_dub"] and d["token_sub"]
    p = _decode_jwt_payload(d["token_dub"])
    assert p["sid"] == pytest.sid


def test_refresh_garbage():
    r = requests.post(f"{API}/stream-auth/refresh", json={"token": "garbage"}, timeout=15)
    assert r.status_code == 403


# --- Validate ---
def test_validate_ok_dub():
    tok = getattr(pytest, "token_dub", None)
    if not tok:
        pytest.skip()
    r = requests.get(f"{API}/stream-auth/validate", params={"token": tok, "source": "dub"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["src"] == "dub"


def test_validate_source_mismatch():
    tok = getattr(pytest, "token_dub", None)
    if not tok:
        pytest.skip()
    r = requests.get(f"{API}/stream-auth/validate", params={"token": tok, "source": "sub"}, timeout=15)
    assert r.status_code == 403


def test_validate_garbage():
    r = requests.get(f"{API}/stream-auth/validate", params={"token": "garbage", "source": "dub"}, timeout=15)
    assert r.status_code == 403


# --- Regression ---
def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200


def test_featured_status():
    r = requests.get(f"{API}/featured/status", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_movies_seed():
    r = requests.get(f"{API}/movies", timeout=15)
    assert r.status_code == 200
    data = r.json()
    movies = data if isinstance(data, list) else data.get("movies") or data.get("items") or []
    assert len(movies) >= 1
    m = movies[0]
    assert m.get("stream_dub") == "https://stream.lenstedreal.xyz/stream.m3u8"
    assert m.get("stream_sub") == "https://stream1.lenstedreal.xyz/stream.m3u8"


# --- Rate limit (run last, isolated IP) ---
def test_rate_limit_flood():
    headers = {"X-Forwarded-For": "10.9.9.9"}
    body = {"username": "wrong", "password": "wrong", "turnstile_token": DUMMY_TS}
    got_429 = False
    for i in range(18):
        r = requests.post(f"{API}/stream-auth/login", json=body, headers=headers, timeout=15)
        if r.status_code == 429:
            got_429 = True
            break
    assert got_429, "expected 429 after >12 attempts"


# --- Site Gate ---
def test_site_gate_status_no_cookie():
    r = requests.get(f"{API}/site-gate/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    assert d["ok"] is False
    assert d["turnstile_site_key"] == "1x00000000000000000000AA"


def test_site_gate_verify_and_status_with_cookie():
    s = requests.Session()
    r = s.post(f"{API}/site-gate/verify", json={"turnstile_token": DUMMY_TS}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # cookie set
    assert "bb_gate" in s.cookies.get_dict()
    r2 = s.get(f"{API}/site-gate/status", timeout=15)
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

