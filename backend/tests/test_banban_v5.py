"""Banban v5 — Iteration 3 tests covering:
- Provider removal → direct SDKs (openai, anthropic, google-generativeai)
- /api/ai/health configured:false (no keys)
- /api/ai/predict graceful available:false (no 500)
- Turkish team translations (Kanada/ABD/Brezilya...) + team*_en preservation
- Istanbul timezone status strings (BUGÜN/YARIN HH:MM)
- /api/match/stats accepts BOTH Turkish and English team names (reverse mapping)
- /api/livescore/today Stages with NmEn (English original) preserved
- Auth cookie flow (regression)
"""
import os
import uuid
import pytest
import httpx

API = os.environ.get('TEST_API_URL', 'http://localhost:8001')
EXTERNAL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ---------------- Health ----------------
@pytest.mark.asyncio
async def test_health_mongo_true():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d['status'] == 'ok' and d['mongo'] is True


# ---------------- AI (no keys → graceful) ----------------
@pytest.mark.asyncio
async def test_ai_health_configured_false_no_keys():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/api/ai/health")
    assert r.status_code == 200
    d = r.json()
    assert d['configured'] is False
    p = d['providers']
    assert p == {"openai": False, "anthropic": False, "gemini": False}
    assert 'models' in d and 'gpt-5.2' in d['models']['openai']


@pytest.mark.asyncio
async def test_ai_predict_graceful_when_no_keys():
    """Must return 200 with available:false + Turkish error, NOT 500."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{API}/api/ai/predict",
                         json={"home": "Galatasaray", "away": "Fenerbahçe"})
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d['available'] is False
    assert 'yapılandırılmamış' in d.get('error', '') or 'AI' in d.get('error', '')


# ---------------- Turkish team translation + EN fallback ----------------
@pytest.mark.asyncio
async def test_scores_top_turkish_names():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{API}/api/scores/top?n=5")
    assert r.status_code == 200
    d = r.json()
    matches = d.get('matches') or []
    assert len(matches) >= 1
    # At least one match must have Turkish translation (Kanada, ABD, Brezilya, Katar, İsviçre…)
    turkish_markers = {"Kanada", "ABD", "Brezilya", "Katar", "İsviçre", "Bosna Hersek", "Fas", "İskoçya"}
    found = any(m.get('team1') in turkish_markers or m.get('team2') in turkish_markers
                for m in matches)
    assert found, f"No Turkish team names found in top: {[(m.get('team1'), m.get('team2')) for m in matches]}"
    # team1_en must be preserved
    for m in matches:
        assert 'team1_en' in m and 'team2_en' in m, f"team1_en/team2_en missing: {m}"


@pytest.mark.asyncio
async def test_scores_live_turkish_with_en():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/scores/live")
    assert r.status_code == 200
    d = r.json()
    if d.get('type') == 'score_update':
        assert 'team1' in d and 'team2' in d
        assert 'team1_en' in d and 'team2_en' in d


@pytest.mark.asyncio
async def test_livescore_today_stages_and_nmen():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{API}/api/livescore/today")
    assert r.status_code == 200
    d = r.json()
    stages = d.get('Stages') or []
    assert len(stages) >= 1
    # find an event with T1[0].NmEn
    saw_nmen = False
    for s in stages:
        for e in s.get('Events', []):
            t1 = (e.get('T1') or [{}])[0]
            if 'NmEn' in t1:
                saw_nmen = True
                # Nm should be Turkish-friendly (may equal English if no mapping)
                assert isinstance(t1.get('Nm'), str)
                break
        if saw_nmen:
            break
    assert saw_nmen, "No NmEn field found in any Stage.Events.T1"


@pytest.mark.asyncio
async def test_status_uses_istanbul_timezone():
    """BUGÜN/YARIN HH:MM expected for upcoming WC matches (Istanbul TZ)."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/scores/top?n=5")
    d = r.json()
    statuses = [m.get('status', '') for m in (d.get('matches') or [])]
    joined = " | ".join(statuses)
    # Accept BUGÜN, YARIN, FT, or HH:MM format
    assert any('BUGÜN' in s or 'YARIN' in s or ':' in s for s in statuses), (
        f"No Istanbul-formatted status: {joined}"
    )


# ---------------- Match stats reverse mapping ----------------
@pytest.mark.asyncio
async def test_match_stats_accepts_turkish():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{API}/api/match/stats",
                        params={"home": "Kanada", "away": "Bosna Hersek"})
    assert r.status_code == 200
    d = r.json()
    assert 'sources' in d
    assert 'eps' in d  # NS/Live/FT/etc


@pytest.mark.asyncio
async def test_match_stats_accepts_english_same_result():
    async with httpx.AsyncClient(timeout=20.0) as c:
        r_tr = await c.get(f"{API}/api/match/stats",
                           params={"home": "Kanada", "away": "Bosna Hersek"})
        r_en = await c.get(f"{API}/api/match/stats",
                           params={"home": "Canada", "away": "Bosnia"})
    assert r_tr.status_code == 200 and r_en.status_code == 200
    d_tr, d_en = r_tr.json(), r_en.json()
    # Should resolve to same upstream event
    assert d_tr.get('live_event_id') == d_en.get('live_event_id'), (
        f"reverse mapping broken: tr={d_tr.get('live_event_id')} en={d_en.get('live_event_id')}"
    )


# ---------------- Other endpoints ----------------
@pytest.mark.asyncio
async def test_predictions_open():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/api/predictions/open")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, (list, dict))


@pytest.mark.asyncio
async def test_auth_cookie_flow():
    suffix = uuid.uuid4().hex[:8]
    email = f"TEST_user_{suffix}@banban.test"
    password = "Banban_Test_2026!"
    async with httpx.AsyncClient(timeout=15.0) as c:
        r_reg = await c.post(f"{API}/api/auth/register",
                             json={"email": email, "password": password,
                                   "username": f"u_{suffix}"})
        assert r_reg.status_code in (200, 201), r_reg.text[:200]
        r_me = await c.get(f"{API}/api/auth/me")
        assert r_me.status_code == 200
        if not r_me.json().get('user'):
            r_login = await c.post(f"{API}/api/auth/login",
                                   json={"email": email, "password": password})
            assert r_login.status_code == 200
            r_me2 = await c.get(f"{API}/api/auth/me")
            assert r_me2.status_code == 200
            assert r_me2.json().get('user') is not None


@pytest.mark.asyncio
async def test_external_ingress_health():
    if not EXTERNAL:
        pytest.skip("No REACT_APP_BACKEND_URL set")
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
        r = await c.get(f"{EXTERNAL}/api/health")
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'
