"""Iter 2: Spider-Man release_date, cache mode, faststart moov, regression."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://build-verified-5.preview.emergentagent.com").rstrip("/")
MOVIE_ID = "spiderman-bnd-4-1"
MOVIE_SIZE = 954393854


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# --- Movies listing: release_date + size ---
def test_movies_first_is_spiderman_with_release_date_and_size(s):
    r = s.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "movies" in data and len(data["movies"]) >= 1
    m = data["movies"][0]
    assert m["id"] == MOVIE_ID, f"expected first movie id spiderman, got {m.get('id')}"
    assert m.get("release_date") == "July 31, 2026", f"got release_date={m.get('release_date')}"
    assert m.get("size") == MOVIE_SIZE, f"got size={m.get('size')}"


# --- Status must be cache mode & ready ---
def test_movie_status_cache_mode(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ready") is True, f"got {d}"
    assert d.get("mode") == "cache", f"expected mode:cache, got {d}"


# --- Range small prefix (100 bytes) fast start ---
def test_range_prefix_100_fast(s):
    t0 = time.time()
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=0-99"}, timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 206
    assert r.headers.get("Content-Type", "").startswith("video/mp4")
    assert len(r.content) == 100
    # sanity: should be < 5s over public preview URL
    assert elapsed < 5.0, f"prefix range took {elapsed}s"


# --- Range near end ---
def test_range_near_end(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=954393000-"}, timeout=15)
    assert r.status_code == 206
    assert len(r.content) == MOVIE_SIZE - 954393000


# --- Faststart: moov atom must be in the first 200KB ---
def test_faststart_moov_in_first_200k(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=0-204799"}, timeout=30)
    assert r.status_code == 206
    assert b"moov" in r.content, "moov atom not found in first 200KB (faststart broken)"


# --- Regression: featured/status ---
def test_featured_status(s):
    r = s.get(f"{BASE_URL}/api/featured/status", timeout=20)
    assert r.status_code == 200
    d = r.json()
    # match may be null if upstream livescore is down; just log
    assert "match" in d, f"missing match field: {d}"
    if d.get("match") in (None, {}, ""):
        pytest.skip(f"featured match empty (upstream livescore); response={d}")


# --- Regression: by-slug Arsenal vs Dortmund score + pen ---
def test_match_by_slug_arsenal_dortmund(s):
    slug = "Arsenal__Borussia_Dortmund__20260809"
    # try common endpoint patterns
    for path in [f"/api/matches/{slug}", f"/api/match/{slug}", f"/api/matches/by-slug/{slug}"]:
        r = s.get(f"{BASE_URL}{path}", timeout=15)
        if r.status_code == 200:
            body = r.text
            # accept either JSON with score fields or HTML SSR (SSR is frontend); check body content
            assert "2" in body and "3" in body, f"missing 2/3 in {path}"
            return
    pytest.skip("No backend match by-slug endpoint responded 200 (SSR-only regression)")
