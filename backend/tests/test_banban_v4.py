"""Banban v4 — Comprehensive test suite for World Cup 2026 + 3-model AI prediction merge.

Covers:
- /api/health (mongo:true)
- /api/ai/health (3-model configured)
- /api/scores/live, /api/scores/top (Morocco-bug fix: World Cup matches must surface)
- /api/livescore/today (Stages including World Cup Group B/D)
- /api/ai/predict (multi-LLM blend: GPT-5.2 + Gemini 3 Pro + Claude Sonnet 4.5)
- /api/auth/register + login + me (cookie-based)
"""
import os
import uuid
import pytest
import httpx

# Internal port - reliable in this preview container (ingress sometimes adds overhead).
# External REACT_APP_BACKEND_URL also tested separately via test_external_ingress.
API = os.environ.get('TEST_API_URL', 'http://localhost:8001')
EXTERNAL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ---------------- Health ----------------
@pytest.mark.asyncio
async def test_health_mongo_true():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d['status'] == 'ok'
    assert d['mongo'] is True
    assert d['version'] == '4.0'


@pytest.mark.asyncio
async def test_ai_health_3_models():
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/api/ai/health")
    assert r.status_code == 200
    d = r.json()
    assert d['configured'] is True
    assert isinstance(d['models'], list)
    assert len(d['models']) == 3
    # Verify the 3 specific models
    joined = ",".join(d['models']).lower()
    assert 'gpt-5.2' in joined
    assert 'gemini' in joined and 'pro' in joined
    assert 'claude' in joined and 'sonnet' in joined
    assert d['harmonizer']  # not empty


# ---------------- Scoreboard / Morocco bug fix ----------------
@pytest.mark.asyncio
async def test_scores_live_shape():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/api/scores/live")
    assert r.status_code == 200
    d = r.json()
    # Single match dict expected (type score_update)
    assert d.get('type') in ('score_update', 'score_top')
    if d.get('type') == 'score_update':
        assert 'team1' in d and 'team2' in d


@pytest.mark.asyncio
async def test_scores_top_world_cup_visible():
    """KRITIK: Morocco exclusion bug fix — World Cup matches MUST appear in top scores."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{API}/api/scores/top?n=5")
    assert r.status_code == 200
    d = r.json()
    assert d.get('type') == 'score_top'
    matches = d.get('matches') or []
    assert isinstance(matches, list)
    assert len(matches) >= 1
    leagues = [m.get('league', '') for m in matches]
    has_wc = any('DÜNYA KUPASI' in (lg or '').upper() or 'WORLD CUP' in (lg or '').upper()
                 for lg in leagues)
    assert has_wc, f"World Cup matches missing from top scores. Leagues: {leagues}"


@pytest.mark.asyncio
async def test_livescore_today_world_cup_stages():
    """Stages array must contain World Cup groups (Group B/D etc)."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(f"{API}/api/livescore/today")
    assert r.status_code == 200
    d = r.json()
    assert 'Stages' in d
    stages = d.get('Stages') or []
    # Should have non-trivial number of stages
    assert len(stages) >= 1
    # World Cup 2026 stages contain "Group" naming
    stage_names = " ".join([(s.get('Snm', '') + " " + s.get('Scd', '')) for s in stages]).lower()
    # Allow either explicit Group X or world cup keywords
    assert ('group' in stage_names or 'world' in stage_names or 'dünya' in stage_names), (
        f"No World Cup-style stages found. Sample: {stage_names[:200]}"
    )


# ---------------- AI predict (multi-LLM blend) ----------------
@pytest.mark.asyncio
async def test_ai_predict_3_models_harmonized():
    """POST /api/ai/predict — must return 3-model individual + harmonized output."""
    payload = {
        "home": "Galatasaray",
        "away": "Fenerbahçe",
        "league": "Süper Lig",
        "no_cache": True,
    }
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(f"{API}/api/ai/predict", json=payload)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get('available') is True, f"AI not available: {d}"
    assert d.get('home') == 'Galatasaray'
    assert d.get('away') == 'Fenerbahçe'

    models = d.get('models_used') or []
    assert isinstance(models, list) and len(models) == 3, f"Expected 3 models, got {models}"

    individual = d.get('individual') or []
    assert isinstance(individual, list) and len(individual) == 3, (
        f"Expected 3 individual predictions, got {len(individual)}"
    )
    for item in individual:
        assert item.get('winner') in ('home', 'away', 'draw'), item
        assert 'predicted_score' in item
        assert isinstance(item.get('confidence'), (int, float))
        assert isinstance(item.get('key_factors'), list)
        assert isinstance(item.get('analysis'), str) and len(item['analysis']) > 10

    h = d.get('harmonized') or {}
    assert isinstance(h, dict) and h, "harmonized object missing"
    assert h.get('winner') in ('home', 'away', 'draw')
    assert 'predicted_score' in h
    assert isinstance(h.get('confidence'), (int, float))
    assert isinstance(h.get('key_factors'), list)
    assert isinstance(h.get('analysis'), str)


# ---------------- Auth (cookie based) ----------------
@pytest.mark.asyncio
async def test_auth_register_login_me_cookie_flow():
    suffix = uuid.uuid4().hex[:8]
    email = f"TEST_user_{suffix}@banban.test"
    password = "Banban_Test_2026!"
    username = f"testuser_{suffix}"

    async with httpx.AsyncClient(timeout=15.0) as c:
        # Register
        r_reg = await c.post(f"{API}/api/auth/register",
                             json={"email": email, "password": password, "username": username})
        assert r_reg.status_code in (200, 201), f"register failed: {r_reg.status_code} {r_reg.text[:200]}"

        # /me should now be authenticated via cookie set on register
        r_me1 = await c.get(f"{API}/api/auth/me")
        assert r_me1.status_code == 200
        me1 = r_me1.json()
        # Either user is set (auto-login after register) or null (then we explicit login)
        if not me1.get('user'):
            r_login = await c.post(f"{API}/api/auth/login",
                                   json={"email": email, "password": password})
            assert r_login.status_code == 200, r_login.text[:200]
            r_me2 = await c.get(f"{API}/api/auth/me")
            assert r_me2.status_code == 200
            assert r_me2.json().get('user') is not None
        else:
            assert me1['user'].get('email', '').lower() == email.lower()


@pytest.mark.asyncio
async def test_auth_me_no_cookie_returns_null():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{API}/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"user": None}


# ---------------- External ingress reachability ----------------
@pytest.mark.asyncio
async def test_external_ingress_health():
    if not EXTERNAL:
        pytest.skip("No REACT_APP_BACKEND_URL set")
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
        r = await c.get(f"{EXTERNAL}/api/health")
    assert r.status_code == 200, f"External ingress unreachable: {r.status_code}"
    assert r.json().get('status') == 'ok'
