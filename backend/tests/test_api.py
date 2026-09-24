"""Backend smoke tests — env-driven, run with `pytest tests/`."""
import os
import pytest
import httpx

API = os.environ.get('TEST_API_URL', 'http://localhost:8001')


@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'ok'
    assert 'mongo' in data
    assert data['version'] == '4.0'


@pytest.mark.asyncio
async def test_root():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/")
    assert r.status_code == 200
    assert 'message' in r.json()


@pytest.mark.asyncio
async def test_livescore_today_shape():
    """LiveScore endpoint'i her durumda Stages key'ini dönmeli (boş array da OK)."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/livescore/today")
    assert r.status_code == 200
    assert 'Stages' in r.json()


@pytest.mark.asyncio
async def test_scores_top_shape():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/scores/top?n=3")
    assert r.status_code == 200
    data = r.json()
    assert 'matches' in data or data.get('type') == 'score_top'


@pytest.mark.asyncio
async def test_channels():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/channels")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_unauth():
    """Cookie yokken /me {user: null} dönmeli, 401 değil."""
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"user": None}


@pytest.mark.asyncio
async def test_predictions_leaderboard_open():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r1 = await c.get(f"{API}/api/predictions/leaderboard")
        r2 = await c.get(f"{API}/api/predictions/open")
    assert r1.status_code == 200
    assert 'leaderboard' in r1.json()
    assert r2.status_code == 200
    assert 'items' in r2.json()


@pytest.mark.asyncio
async def test_chat_recent():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/chat/recent?limit=10")
    assert r.status_code == 200
    assert 'messages' in r.json()


@pytest.mark.asyncio
async def test_settlement_calc_unit():
    """Settlement puan hesabı sanity check (5/3/1/0)."""
    from app.services.settlement import _calc_points
    assert _calc_points(2, 1, 2, 1) == 5  # tam skor
    assert _calc_points(2, 1, 3, 2) == 3  # gol farkı + sonuç
    assert _calc_points(2, 1, 5, 0) == 1  # sadece sonuç (ev kazandı)
    assert _calc_points(2, 1, 0, 3) == 0  # yanlış sonuç
    assert _calc_points(0, 0, 0, 0) == 5  # 0-0 tam skor


@pytest.mark.asyncio
async def test_admin_endpoints_require_auth():
    """Admin endpoint'leri auth olmadan 401 dönmeli."""
    async with httpx.AsyncClient(timeout=8.0) as c:
        for path in ['/api/admin/stats', '/api/admin/users', '/api/admin/predictions/pending',
                     '/api/admin/chat/messages']:
            r = await c.get(f"{API}{path}")
            assert r.status_code == 401, f"{path} → {r.status_code}"


@pytest.mark.asyncio
async def test_push_vapid_key_endpoint():
    """VAPID public key endpoint herkese açık olmalı (configured durumunu da döner)."""
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/push/vapid-key")
    assert r.status_code == 200
    data = r.json()
    assert 'configured' in data
    assert 'public_key' in data


@pytest.mark.asyncio
async def test_match_by_slug_endpoint():
    """Match detail slug endpoint'i her zaman 200 döner (available false bile olsa)."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/match/by-slug/test__team__20260101")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_predictions_streak_and_my_match_require_auth():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r1 = await c.get(f"{API}/api/predictions/streak")
        r2 = await c.get(f"{API}/api/predictions/match/test")
    assert r1.status_code == 401
    assert r2.status_code == 401
