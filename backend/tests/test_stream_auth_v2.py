"""BanbanSports Stream Token V2.1 — end-to-end backend tests.

Covers: /config, /login, /refresh (rotation + grace), /logout, /status, /url,
/validate (dev), /cast-token, /start /heartbeat /stop (lease flow), concurrency,
rate limit, plus regression on /health, /movies, /featured/status, /featured/seg.

Uses public preview URL from REACT_APP_BACKEND_URL (Set-Cookie Secure requires https).
"""
import os
import time
import base64
import json
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api/stream-auth"
STREAM_ID = "spiderman-bnd-4-1"
CREDS = {"username": "lenstedreal_marka", "password": "zirvedeyiz", "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"}


def _decode_jwt(tok: str) -> dict:
    _h, payload, _s = tok.split(".")
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _login_session() -> tuple[requests.Session, dict]:
    s = requests.Session()
    r = s.post(f"{API}/login", json=CREDS, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s, r.json()


# ---------- /config ----------
def test_config_public_shape():
    r = requests.get(f"{API}/config", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["turnstile_site_key"] == "1x00000000000000000000AA"
    assert d["token_ttl"] == 1800
    assert d["hls_ttl_js"] == 1800
    assert d["hls_ttl_native"] == 10800
    assert d["heartbeat_interval"] == 45
    assert d["max_concurrent"] == 2


# ---------- /login ----------
def test_login_wrong_creds_401():
    r = requests.post(f"{API}/login", json={**CREDS, "password": "wrong"}, timeout=10)
    assert r.status_code == 401


def test_login_empty_turnstile_400():
    r = requests.post(f"{API}/login", json={**CREDS, "turnstile_token": ""}, timeout=10)
    assert r.status_code == 400


def test_login_success_sets_cookie_and_returns_bearer():
    s = requests.Session()
    r = s.post(f"{API}/login", json=CREDS, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["token_type"] == "Bearer"
    assert d["expires_in"] == 1800
    assert d["sid"] and d["did"]
    assert "bb_refresh" in s.cookies.get_dict()
    # cookie attribute check via raw header
    set_cookie_hdr = r.headers.get("set-cookie", "")
    assert "bb_refresh=" in set_cookie_hdr
    assert "HttpOnly" in set_cookie_hdr
    assert "/api/stream-auth" in set_cookie_hdr
    # JWT payload
    payload = _decode_jwt(d["access_token"])
    assert payload["iss"] == "banbansports"
    assert payload["scope"] == "stream_session"
    assert payload["sid"] == d["sid"]
    assert payload["did"] == d["did"]
    assert payload["jti"]
    assert payload["sub"]


# ---------- /refresh ----------
def test_refresh_rotates_and_grace_allows_old_cookie():
    s, d1 = _login_session()
    old_cookie = s.cookies.get("bb_refresh")
    r = s.post(f"{API}/refresh", timeout=10)
    assert r.status_code == 200
    d2 = r.json()
    assert d2["sid"] == d1["sid"]
    new_cookie = s.cookies.get("bb_refresh")
    assert new_cookie and new_cookie != old_cookie
    # grace: reuse old cookie manually
    s2 = requests.Session()
    s2.cookies.set("bb_refresh", old_cookie, domain=requests.utils.urlparse(BASE_URL).hostname, path="/api/stream-auth")
    r2 = s2.post(f"{API}/refresh", timeout=10)
    assert r2.status_code == 200, f"grace expected 200 got {r2.status_code} {r2.text}"


def test_refresh_no_cookie_401():
    r = requests.post(f"{API}/refresh", timeout=10)
    assert r.status_code == 401


def test_refresh_garbage_cookie_401():
    s = requests.Session()
    s.cookies.set("bb_refresh", "not-a-real-token", domain=requests.utils.urlparse(BASE_URL).hostname, path="/api/stream-auth")
    r = s.post(f"{API}/refresh", timeout=10)
    assert r.status_code == 401


# ---------- /status ----------
def test_status_bearer_ok():
    _s, d = _login_session()
    r = requests.get(f"{API}/status", headers={"Authorization": f"Bearer {d['access_token']}"}, timeout=10)
    assert r.status_code == 200
    b = r.json()
    assert b["sid"] == d["sid"]
    assert b["did"] == d["did"]
    assert b["max_concurrent"] == 2
    assert "family_active" in b


def test_status_no_bearer_401():
    r = requests.get(f"{API}/status", timeout=10)
    assert r.status_code == 401


def test_status_garbage_bearer_401():
    r = requests.get(f"{API}/status", headers={"Authorization": "Bearer garbage.xxx.yyy"}, timeout=10)
    assert r.status_code == 401


# ---------- /url ----------
def _bearer_h(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def test_url_dub_js():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "dub", "mode": "js"}, timeout=10)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["url"].startswith("https://stream.lenstedreal.xyz/stream.m3u8?")
    for k in ("exp", "sid", "did", "m", "st"):
        assert k in b["params"]
    assert b["params"]["m"] == "js"
    sig = b["params"]["sig"]
    assert len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)
    assert b["expires_in"] == 1800


def test_url_sub_host_switch():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "sub", "mode": "js"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://stream1.lenstedreal.xyz/")


def test_url_native_ttl():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "dub", "mode": "native"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["expires_in"] == 10800


def test_url_unknown_stream_404():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": "does-not-exist-xyz", "source": "dub", "mode": "js"}, timeout=10)
    assert r.status_code == 404


def test_url_bad_source_400():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "xx", "mode": "js"}, timeout=10)
    assert r.status_code == 400


def test_url_bad_mode_400():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "dub", "mode": "bad"}, timeout=10)
    assert r.status_code == 400


# ---------- /validate ----------
def test_validate_ok_and_tamper_and_wrong_src():
    _s, d = _login_session()
    r = requests.post(f"{API}/url", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "dub", "mode": "js"}, timeout=10)
    p = r.json()["params"]
    q = {"host": "stream.lenstedreal.xyz", "src": "dub", **{k: p[k] for k in ("st", "sid", "did", "exp", "m", "sig")}}
    r_ok = requests.get(f"{API}/validate", params=q, timeout=10)
    assert r_ok.status_code == 200 and r_ok.json()["ok"] is True

    q_bad = dict(q, sig="0" * 64)
    assert requests.get(f"{API}/validate", params=q_bad, timeout=10).status_code == 403

    q_wrong = dict(q, src="sub")
    assert requests.get(f"{API}/validate", params=q_wrong, timeout=10).status_code == 403


# ---------- /cast-token ----------
def test_cast_token_and_validate():
    _s, d = _login_session()
    r = requests.post(f"{API}/cast-token", headers=_bearer_h(d),
                      json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    assert r.status_code == 200
    b = r.json()
    assert b["content_type"] == "application/x-mpegURL"
    assert b["expires_in"] == 10800
    assert f"cs={b['cast_session_id']}" in b["media_url"]
    assert "m=native" in b["media_url"]
    # /validate with cs
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(b["media_url"]).query)
    q_flat = {k: v[0] for k, v in q.items()}
    r_ok = requests.get(f"{API}/validate", params={"host": "stream.lenstedreal.xyz", "src": "dub", **q_flat}, timeout=10)
    assert r_ok.status_code == 200 and r_ok.json().get("cast") is True


# ---------- lease flow ----------
def test_lease_start_heartbeat_stop_flow():
    s, d = _login_session()
    h = _bearer_h(d)
    r = requests.post(f"{API}/start", headers=h, json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    assert r.status_code == 200, r.text
    lease_id = r.json()["lease_id"]
    assert r.json()["heartbeat_interval"] == 45
    assert r.json()["ttl"] == 90

    r_hb = requests.post(f"{API}/heartbeat", headers=h, json={"lease_id": lease_id}, timeout=10)
    assert r_hb.status_code == 200

    r_bogus = requests.post(f"{API}/heartbeat", headers=h, json={"lease_id": "bogus"}, timeout=10)
    assert r_bogus.status_code == 404

    r_stop = requests.post(f"{API}/stop", headers=h, json={"lease_id": lease_id}, timeout=10)
    assert r_stop.status_code == 200

    r_hb2 = requests.post(f"{API}/heartbeat", headers=h, json={"lease_id": lease_id}, timeout=10)
    assert r_hb2.status_code == 404


def test_stop_beacon_without_bearer():
    _s, d = _login_session()
    h = _bearer_h(d)
    r = requests.post(f"{API}/start", headers=h, json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    lease_id = r.json()["lease_id"]
    r_stop = requests.post(f"{API}/stop", json={"lease_id": lease_id}, timeout=10)
    assert r_stop.status_code == 200


# ---------- concurrency ----------
def test_same_session_start_twice_replaces_lease():
    _s, d = _login_session()
    h = _bearer_h(d)
    r1 = requests.post(f"{API}/start", headers=h, json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/start", headers=h, json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    assert r2.status_code == 200
    r_st = requests.get(f"{API}/status", headers=h, timeout=10)
    # family_active counts OTHER sessions than self; own lease excluded → 0
    assert r_st.json()["family_active"] == 0


def test_two_families_can_both_start():
    _sA, dA = _login_session()
    _sB, dB = _login_session()
    rA = requests.post(f"{API}/start", headers=_bearer_h(dA), json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    rB = requests.post(f"{API}/start", headers=_bearer_h(dB), json={"stream_id": STREAM_ID, "source": "dub"}, timeout=10)
    assert rA.status_code == 200 and rB.status_code == 200


# ---------- /logout ----------
def test_logout_revokes_and_clears():
    s, d = _login_session()
    old_bearer = d["access_token"]
    r = s.post(f"{API}/logout", timeout=10)
    assert r.status_code == 200
    # old bearer → session revoked → 401
    r_st = requests.get(f"{API}/status", headers={"Authorization": f"Bearer {old_bearer}"}, timeout=10)
    assert r_st.status_code == 401
    # refresh with (now cleared) cookie → 401
    r_ref = s.post(f"{API}/refresh", timeout=10)
    assert r_ref.status_code == 401


# ---------- rate limit ----------
def test_rate_limit_login_eventually_429():
    saw_429 = False
    for _ in range(15):
        r = requests.post(f"{API}/login", json={**CREDS, "password": "wrong"},
                          headers={"X-Forwarded-For": "10.9.9.9"}, timeout=10)
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "expected 429 after >12 attempts"


# ---------- regression ----------
def test_regression_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200


def test_regression_movies_has_spiderman_streams():
    r = requests.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    movies = r.json()
    m = next((x for x in movies if x.get("id") == STREAM_ID), None)
    assert m is not None, f"{STREAM_ID} not found in /api/movies"
    assert m.get("stream_dub")
    assert m.get("stream_sub")


def test_regression_featured_status():
    r = requests.get(f"{BASE_URL}/api/featured/status", timeout=15)
    assert r.status_code == 200


def test_regression_featured_seg_evil_host_blocked_403():
    r = requests.get(f"{BASE_URL}/api/featured/seg", params={"u": "https://evil.example/x.ts"}, timeout=10)
    assert r.status_code == 403


def test_regression_featured_seg_missing_u():
    r = requests.get(f"{BASE_URL}/api/featured/seg", timeout=10)
    assert r.status_code in (400, 422)
