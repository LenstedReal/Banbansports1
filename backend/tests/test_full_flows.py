"""Full-flow integration tests against public ingress URL.

Covers:
- health / root / channels
- livescore today + scores/top + match/stats
- auth: register → me → logout → login → me; refresh
- predictions: open, leaderboard, submit (auth), me
- chat: recent, send (auth)
- websocket /api/ws/scores
"""
import os
import time
import asyncio
import json

import pytest
import httpx
import websockets

BASE = os.environ.get(
    "TEST_API_URL",
    "http://localhost:8001",
).rstrip("/")
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://")
TS = int(time.time())
TEST_EMAIL = f"testuser-{TS}@banbansports.test"
TEST_PASSWORD = "TestPass123!"


# ---------- Basic health / readonly ----------
@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{BASE}/api/health")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["mongo"] is True
    assert data["version"] == "4.0"


@pytest.mark.asyncio
async def test_livescore_today():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{BASE}/api/livescore/today")
    assert r.status_code == 200
    body = r.json()
    assert "Stages" in body
    assert isinstance(body["Stages"], list)


@pytest.mark.asyncio
async def test_scores_top():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{BASE}/api/scores/top?n=5")
    assert r.status_code == 200
    data = r.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)


@pytest.mark.asyncio
async def test_match_stats_shape():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{BASE}/api/match/stats", params={"home": "Galatasaray", "away": "Fenerbahce"}
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "available" in body
    assert "sources" in body
    assert isinstance(body["sources"], list)


@pytest.mark.asyncio
async def test_channels():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{BASE}/api/channels")
    assert r.status_code == 200


# ---------- Auth flow ----------
@pytest.mark.asyncio
async def test_auth_me_unauth_returns_null_not_401():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{BASE}/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"user": None}


@pytest.mark.asyncio
async def test_auth_register_login_logout_me_cycle():
    """End-to-end cookie cycle on real ingress."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        # Register
        r = await c.post(
            f"{BASE}/api/auth/register",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "Tester"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True, body
        assert body["user"]["email"] == TEST_EMAIL
        # Cookies should be present after register
        access_cookie = c.cookies.get("access_token")
        assert access_cookie, "access_token cookie not set after register"

        # /me with cookie → real user
        r = await c.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        me_body = r.json()
        assert me_body["user"] is not None
        assert me_body["user"]["email"] == TEST_EMAIL

        # Logout
        r = await c.post(f"{BASE}/api/auth/logout")
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # /me without cookie → null
        c.cookies.clear()
        r = await c.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["user"] is None

        # Login again
        r = await c.post(
            f"{BASE}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True, body
        assert c.cookies.get("access_token")

        # Refresh
        r = await c.post(f"{BASE}/api/auth/refresh")
        assert r.status_code == 200
        assert r.json().get("ok") is True


@pytest.mark.asyncio
async def test_auth_login_wrong_password():
    async with httpx.AsyncClient(timeout=10.0) as c:
        # ensure user exists from previous test
        await c.post(
            f"{BASE}/api/auth/register",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "Tester"},
        )
        c.cookies.clear()
        r = await c.post(
            f"{BASE}/api/auth/login",
            json={"email": TEST_EMAIL, "password": "wrongpass"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert "error" in body


# ---------- Predictions ----------
@pytest.mark.asyncio
async def test_predictions_open_and_leaderboard():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r1 = await c.get(f"{BASE}/api/predictions/open")
        r2 = await c.get(f"{BASE}/api/predictions/leaderboard")
    assert r1.status_code == 200
    assert "items" in r1.json()
    assert r2.status_code == 200
    assert "leaderboard" in r2.json()


@pytest.mark.asyncio
async def test_predictions_submit_requires_auth():
    """Unauthenticated submit must be 401."""
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(
            f"{BASE}/api/predictions/submit",
            json={"match_id": "A__B__2099-01-01T20:00", "score1": 2, "score2": 1},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_predictions_submit_authenticated_then_me():
    async with httpx.AsyncClient(timeout=15.0) as c:
        # Login (user was created earlier)
        r = await c.post(
            f"{BASE}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert r.status_code == 200 and r.json().get("ok"), r.text
        match_id = "Galatasaray__Fenerbahce__2099-01-01T20:00"
        r = await c.post(
            f"{BASE}/api/predictions/submit",
            json={"match_id": match_id, "score1": 2, "score2": 1},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        r = await c.get(f"{BASE}/api/predictions/me")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(it["match_id"] == match_id for it in items)


# ---------- Chat ----------
@pytest.mark.asyncio
async def test_chat_recent_public():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{BASE}/api/chat/recent?limit=10")
    assert r.status_code == 200
    assert "messages" in r.json()


@pytest.mark.asyncio
async def test_chat_send_requires_auth():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(f"{BASE}/api/chat/send", json={"text": "hello"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_chat_send_authenticated():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            f"{BASE}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert r.status_code == 200 and r.json().get("ok"), r.text
        msg = f"test message {TS}"
        r = await c.post(f"{BASE}/api/chat/send", json={"text": msg})
        assert r.status_code == 200, r.text
        r = await c.get(f"{BASE}/api/chat/recent?limit=20")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert any(m.get("text") == msg for m in msgs), "Sent chat message not found"


# ---------- WebSocket ----------
@pytest.mark.asyncio
async def test_ws_scores_connect():
    """Just verify socket opens and responds (or stays alive a moment)."""
    url = f"{WS_BASE}/api/ws/scores"
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            # Wait briefly for server to push or just confirm connection
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                # Optional: should be json-decodable if anything is sent
                try:
                    json.loads(msg)
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass  # No initial push is OK; connection itself is the test
    except Exception as e:
        pytest.fail(f"WS connect failed: {e}")
