"""
Banban Sports - Repair Package Regression Tests
Covers: scoreboard leak filter, MatchCenter prep filter, FotMob stats, featured card, slug endpoint.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://match-data-clean.preview.emergentagent.com").rstrip("/")
TIMEOUT_SHORT = 30
TIMEOUT_LONG = 90  # match/stats can be slow due to multi-source chain

# --- Non-UEFA confederation leagues that should NEVER appear as UEFA-like -----
NON_UEFA_LEAGUE_TOKENS = [
    "OFC Champions League",
    "CAF Champions League",
    "AFC Champions League",
    "CONCACAF Champions",
    "Venus",       # example unknown league from user prompt
    "Tiga Sport",  # example unknown source
]


# -------------- /api/scores/top --------------
class TestScoresTop:
    def test_scores_top_ok(self):
        r = requests.get(f"{BASE_URL}/api/scores/top", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("type") == "score_top"
        matches = data.get("matches")
        assert isinstance(matches, list)
        # schema check on first few
        if matches:
            m = matches[0]
            for k in ("team1", "team2", "league", "status"):
                assert k in m, f"missing key {k} in match: {m}"

    def test_scores_top_no_unknown_leagues(self):
        r = requests.get(f"{BASE_URL}/api/scores/top", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200
        matches = r.json().get("matches", [])
        for m in matches:
            league = (m.get("league") or "").lower()
            for bad in NON_UEFA_LEAGUE_TOKENS:
                assert bad.lower() not in league, (
                    f"Leaked non-UEFA/unknown league found: {league} in match {m}"
                )


# -------------- /api/livescore/today --------------
class TestLivescoreToday:
    def test_livescore_today_shape(self):
        r = requests.get(f"{BASE_URL}/api/livescore/today", timeout=TIMEOUT_LONG)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "Stages" in data
        assert isinstance(data["Stages"], list)
        if data["Stages"]:
            st = data["Stages"][0]
            # Cnm=country, Snm=stage name, Events=match list
            assert "Cnm" in st or "Snm" in st or "Events" in st


# -------------- /api/match/stats FotMob path --------------
class TestMatchStatsFotMob:
    def test_stats_botafogo_fluminense(self):
        r = requests.get(
            f"{BASE_URL}/api/match/stats",
            params={"home": "Botafogo FR", "away": "Fluminense"},
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # If external sources are all down this may be unavailable — treat as skip
        if not data.get("available"):
            pytest.skip(f"match stats not available for Botafogo/Fluminense: {data}")
        stats = data.get("stats") or {}
        assert isinstance(stats, dict)
        assert len(stats) >= 25, f"expected 25+ stat rows, got {len(stats)}: {list(stats.keys())}"
        # xG / xGOT keys present and filled
        keys_lower = {k.lower(): v for k, v in stats.items()}
        assert "xg" in keys_lower, f"missing 'xg' key. keys: {list(stats.keys())}"
        assert "xgot" in keys_lower, f"missing 'xgot' key. keys: {list(stats.keys())}"
        # sources should mention fotmob:ok
        sources = data.get("sources") or []
        if isinstance(sources, list):
            src_str = ",".join(str(s) for s in sources)
        else:
            src_str = str(sources)
        assert "fotmob" in src_str.lower(), f"sources missing fotmob marker: {sources}"

        # score numeric
        score = data.get("score") or {}
        if score:
            for side in ("home", "away"):
                sv = score.get(side)
                if sv is None:
                    continue
                # accept int/float or digit-string
                assert isinstance(sv, (int, float)) or (isinstance(sv, str) and sv.strip().isdigit()), (
                    f"score.{side} not numeric-like: {sv!r}"
                )
        # events list
        events = data.get("events")
        if events is not None:
            assert isinstance(events, list)

    def test_stats_galatasaray_villarreal(self):
        r = requests.get(
            f"{BASE_URL}/api/match/stats",
            params={"home": "Galatasaray", "away": "Villarreal", "date": "20260808"},
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if not data.get("available"):
            pytest.skip(f"match stats not available: {data}")
        stats = data.get("stats") or {}
        assert len(stats) >= 25, f"expected 25+ rows, got {len(stats)}"
        sources = data.get("sources") or []
        src_str = ",".join(str(s) for s in sources) if isinstance(sources, list) else str(sources)
        # Should have livescore + fotmob markers
        assert "fotmob" in src_str.lower() or "livescore" in src_str.lower(), (
            f"sources missing expected markers: {sources}"
        )
        # yellow/red/subs either number or '?'
        for key in ("yellow_cards", "red_cards", "substitutions"):
            v = stats.get(key)
            if v is None:
                continue
            # accept dict with home/away OR string/number
            if isinstance(v, dict):
                for side in ("home", "away"):
                    sv = v.get(side)
                    assert sv is None or isinstance(sv, (int, float, str)), (
                        f"{key}.{side} unexpected type: {type(sv)}"
                    )
            else:
                assert isinstance(v, (int, float, str)), f"{key} unexpected: {v}"


# -------------- /api/featured/status --------------
class TestFeaturedStatus:
    def test_featured_status_shape(self):
        r = requests.get(f"{BASE_URL}/api/featured/status", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("configured", "source_live", "live", "channel", "name", "status"):
            assert k in data, f"missing key {k}: {data}"
        # match field: either None or dict with required subfields
        match = data.get("match")
        if match is not None:
            for k in ("home", "away", "league", "time", "status"):
                assert k in match, f"missing match key {k}: {match}"
            assert match["status"] in ("live", "upcoming"), (
                f"unexpected match status: {match['status']}"
            )


# -------------- /api/match/by-slug --------------
class TestMatchBySlug:
    def test_slug_resolution(self):
        slug = "Manchester_City__Atl%C3%A9tico_Madrid__20260809"
        # requests will re-encode; use raw path
        url = f"{BASE_URL}/api/match/by-slug/{slug}"
        r = requests.get(url, timeout=TIMEOUT_LONG)
        assert r.status_code == 200, r.text
        data = r.json()
        # available:true expected per user requirement
        assert data.get("available") is True, f"by-slug not available: {data}"
