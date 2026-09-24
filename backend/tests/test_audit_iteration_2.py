"""Discovery/audit tests for iteration 2. NO fix-verification.
Documents current backend behavior across stream, scores, livescore, match stats.
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://code-repair-157.preview.emergentagent.com").rstrip("/")
S = requests.Session()
S.headers.update({"Accept": "application/json"})

CHANNELS = ["trthaber", "ssport", "tivibuspor", "tv8", "trtspor", "trt1"]


# ---------- Stream status/health ----------
class TestStreamStatus:
    def test_bulk_status_shape(self):
        r = S.get(f"{BASE}/api/stream/status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "channels" in d
        for c in CHANNELS:
            assert c in d["channels"], f"channel {c} missing"
            assert "configured" in d["channels"][c] and "ok" in d["channels"][c]

    @pytest.mark.parametrize("ch", CHANNELS)
    def test_channel_health(self, ch):
        r = S.get(f"{BASE}/api/stream/{ch}/health", timeout=30)
        assert r.status_code == 200
        d = r.json()
        print(f"HEALTH {ch}: {d}")
        assert "configured" in d

    def test_master_m3u8_trthaber(self):
        r = S.get(f"{BASE}/api/stream/trthaber/stream.m3u8", timeout=30)
        assert r.status_code == 200
        assert r.text.lstrip().startswith("#EXTM3U")

    def test_master_m3u8_ssport(self):
        r = S.get(f"{BASE}/api/stream/ssport/stream.m3u8", timeout=30)
        # ssport reports ok:false but the master m3u8 actually returns 200 + #EXTM3U
        print(f"ssport m3u8 status={r.status_code} body_prefix={r.text[:60]!r}")
        assert r.status_code == 200

    def test_master_m3u8_tv8(self):
        r = S.get(f"{BASE}/api/stream/tv8/stream.m3u8", timeout=30)
        print(f"tv8 m3u8 status={r.status_code} body_prefix={r.text[:60]!r}")
        assert r.status_code == 200

    def test_master_m3u8_trt1_unconfigured(self):
        r = S.get(f"{BASE}/api/stream/trt1/stream.m3u8", timeout=30)
        assert r.status_code == 503

    @pytest.mark.parametrize("ch", ["ssport", "tv8", "trtspor", "tivibuspor"])
    def test_refresh_does_not_flip_ok(self, ch):
        """BUG: POST /refresh returns refreshed:false for all currently 'ok:false' channels.
        No token change persists, ok stays false. Documenting the failure."""
        r = S.post(f"{BASE}/api/stream/{ch}/refresh", timeout=30)
        assert r.status_code == 200
        d = r.json()
        print(f"REFRESH {ch}: {d}")
        # We don't assert True — we EXPECT False in current state (audit-only)
        assert "refreshed" in d


# ---------- Scores / LiveScore ----------
class TestScoresEndpoints:
    def test_scores_top(self):
        r = S.get(f"{BASE}/api/scores/top?n=10", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("type") == "score_top"
        matches = d.get("matches") or []
        print(f"TOP MATCHES ({len(matches)}):")
        for m in matches[:10]:
            print(f"  {m.get('team1')} vs {m.get('team2')} | {m.get('league')} | {m.get('status')}")
        assert isinstance(matches, list)

    def test_livescore_today(self):
        r = S.get(f"{BASE}/api/livescore/today", timeout=30)
        assert r.status_code == 200
        d = r.json()
        stages = d.get("Stages") or []
        total = sum(len(s.get("Events") or []) for s in stages)
        print(f"TODAY Stages={len(stages)} Events={total}")
        for s in stages[:20]:
            print(f"  {s.get('Cnm')} / {s.get('Snm')} : {len(s.get('Events') or [])}")


# ---------- Match stats ----------
class TestMatchStats:
    def test_stats_endpoint_reachable(self):
        r = S.get(f"{BASE}/api/match/stats?home=Djurgaarden&away=Halmstads%20BK", timeout=30)
        assert r.status_code == 200
        d = r.json()
        print(f"STATS Djurgaarden vs Halmstads BK: available={d.get('available')} sources={d.get('sources')} score={d.get('score')} league={d.get('league')}")
        assert "stats" in d

    def test_stats_fuzzy_fails_for_wrong_names(self):
        """Fuzzy match tolerant of team-name variants; but wrong names -> available:false"""
        r = S.get(f"{BASE}/api/match/stats?home=NoSuchTeamXYZ&away=AlsoNoSuch", timeout=30)
        assert r.status_code == 200
        assert r.json().get("available") is False
