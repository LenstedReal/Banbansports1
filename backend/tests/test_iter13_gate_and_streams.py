"""Iteration 13 - Site gate + Stream auth + Direct channels + livescore no-store."""
import os
import time

import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to reading from frontend/.env for external URL
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

STREAM_JWT_SECRET = ""
try:
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("STREAM_JWT_SECRET="):
                STREAM_JWT_SECRET = line.split("=", 1)[1].strip().strip('"')
                break
except Exception:
    pass

DUMMY_TS = "XXXX.DUMMY.TOKEN.XXXX"
CREDS = {"username": "lenstedreal_marka", "password": "zirvedeyiz"}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# --- stream-auth ---
class TestStreamAuth:
    def test_config(self, s):
        r = s.get(f"{BASE_URL}/api/stream-auth/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["token_ttl"] == 1800
        assert d["turnstile_site_key"]

    def test_login_missing_turnstile(self, s):
        r = s.post(f"{BASE_URL}/api/stream-auth/login", json={**CREDS, "turnstile_token": ""}, timeout=15)
        assert r.status_code == 400

    def test_login_wrong_creds(self, s):
        r = s.post(f"{BASE_URL}/api/stream-auth/login",
                   json={"username": "x", "password": "y", "turnstile_token": DUMMY_TS}, timeout=15)
        assert r.status_code == 401

    def test_login_success_and_decode(self, s):
        r = s.post(f"{BASE_URL}/api/stream-auth/login",
                   json={**CREDS, "turnstile_token": DUMMY_TS}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["expires_in"] == 1800
        assert d["token_dub"] and d["token_sub"]
        # decode using STREAM_JWT_SECRET
        for src, tok in [("dub", d["token_dub"]), ("sub", d["token_sub"])]:
            p = jwt.decode(tok, STREAM_JWT_SECRET, algorithms=["HS256"], issuer="banbansports")
            assert p["scope"] == "hls"
            assert p["src"] == src
            assert abs(p["exp"] - (time.time() + 1800)) < 60
        # save for later
        pytest.token_dub = d["token_dub"]
        pytest.token_sub = d["token_sub"]

    def test_refresh_valid(self, s):
        r = s.post(f"{BASE_URL}/api/stream-auth/refresh", json={"token": pytest.token_dub}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["token_dub"] and d["token_sub"]

    def test_refresh_garbage(self, s):
        r = s.post(f"{BASE_URL}/api/stream-auth/refresh", json={"token": "garbage.token.xyz"}, timeout=15)
        assert r.status_code == 403

    def test_validate_ok(self, s):
        r = s.get(f"{BASE_URL}/api/stream-auth/validate",
                  params={"token": pytest.token_dub, "source": "dub"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_validate_wrong_source(self, s):
        r = s.get(f"{BASE_URL}/api/stream-auth/validate",
                  params={"token": pytest.token_dub, "source": "sub"}, timeout=15)
        assert r.status_code == 403


# --- site-gate ---
class TestSiteGate:
    def test_status_without_cookie(self):
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/site-gate/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert d["ok"] is False
        assert d["turnstile_site_key"]

    def test_verify_then_status_ok(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/site-gate/verify",
                   json={"turnstile_token": DUMMY_TS}, timeout=20)
        assert r.status_code == 200, r.text
        assert "bb_gate" in s.cookies.get_dict() or any("bb_gate" in c for c in r.headers.get("set-cookie", ""))
        r2 = s.get(f"{BASE_URL}/api/site-gate/status", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["ok"] is True


# --- channels + stream proxy ---
CHANNEL_IDS = ["aspor", "htspor", "beinxtra", "trt1", "showtv", "kanald", "cnnturk", "trtmuzik", "powerturk"]


class TestChannels:
    def test_channels_list(self):
        r = requests.get(f"{BASE_URL}/api/channels", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, list):
            n = len(data)
        elif isinstance(data, dict):
            n = len(data.get("channels") or data.get("items") or list(data.keys()))
        else:
            n = 0
        assert n >= 27, f"expected >=27 channels got {n}"

    @pytest.mark.parametrize("cid", CHANNEL_IDS)
    def test_stream_m3u8(self, cid):
        url = f"{BASE_URL}/api/stream/{cid}/stream.m3u8"
        # one retry for upstream flakiness
        for _ in range(2):
            r = requests.get(url, timeout=25)
            if r.status_code == 200:
                break
            time.sleep(1)
        assert r.status_code == 200, f"{cid} → {r.status_code}: {r.text[:200]}"
        body = r.text
        assert body.startswith("#EXTM3U"), f"{cid} body: {body[:120]}"
        # segments must be rewritten
        assert ("/api/stream/" in body) or ("/playlist.m3u8?url=" in body) or ("/seg.ts?url=" in body)


# --- livescore cache header ---
class TestLivescore:
    def test_livescore_no_store(self):
        r = requests.get(f"{BASE_URL}/api/livescore/today", params={"days": 1}, timeout=20)
        assert r.status_code == 200
        cc = r.headers.get("Cache-Control", "")
        assert "no-store" in cc.lower(), f"Cache-Control={cc!r}"
