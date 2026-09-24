"""Backend regression tests for banbansports UI redesign iteration.
Covers endpoints listed in review request: health, scores, livescore, channels,
boxoffice, movies, featured/status, stream/status, auth/login.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cinematic-sports-hub-2.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@banbansports.com"
ADMIN_PASSWORD = "200cf39563dc85abb595c284"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health ----------
def test_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("status") == "ok"
    assert d.get("mongo") is True


# ---------- Scores ----------
def test_scores_top(client):
    r = client.get(f"{BASE_URL}/api/scores/top?n=5", timeout=30)
    assert r.status_code == 200
    d = r.json()
    # response is expected to have a list of matches somewhere
    assert isinstance(d, (list, dict))
    if isinstance(d, dict):
        # find list of matches
        found = any(isinstance(v, list) for v in d.values())
        assert found, f"No list in scores response: {d}"


# ---------- Livescore ----------
def test_livescore_today(client):
    r = client.get(f"{BASE_URL}/api/livescore/today", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "Stages" in d or "stages" in d, f"No Stages key: {list(d.keys())[:10]}"


# ---------- Channels ----------
def test_channels(client):
    r = client.get(f"{BASE_URL}/api/channels", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, (list, dict))
    if isinstance(d, dict):
        # expect a channels key or a list of items
        assert any(isinstance(v, list) for v in d.values()) or len(d) > 0


# ---------- Box Office ----------
def test_boxoffice(client):
    r = client.get(f"{BASE_URL}/api/boxoffice", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    assert "gross_usd" in d
    assert "plot" in d
    assert "imdb" in d


# ---------- Movies ----------
def test_movies(client):
    r = client.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    d = r.json()
    movies = d.get("movies") if isinstance(d, dict) else d
    assert isinstance(movies, list)


# ---------- Featured status ----------
def test_featured_status(client):
    r = client.get(f"{BASE_URL}/api/featured/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    # expected to contain some info about live/channel/match
    assert isinstance(d, dict)
    # Not strict on which keys, just log
    keys = set(d.keys())
    assert keys, "empty featured/status"


# ---------- Stream status ----------
def test_stream_status(client):
    r = client.get(f"{BASE_URL}/api/stream/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "channels" in d, f"missing channels key: {list(d.keys())}"
    assert isinstance(d["channels"], (dict, list))


# ---------- Auth login ----------
def test_admin_login(client):
    r = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Accept either token in body or set-cookie
    has_token = bool(d.get("token") or d.get("access_token"))
    has_cookie = bool(r.cookies)
    assert has_token or has_cookie, f"No token/cookie: body={d}, cookies={r.cookies}"


def test_admin_login_invalid(client):
    r = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "wrongpass"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 403)
