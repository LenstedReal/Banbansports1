"""Backend tests for movies feature + basic regression."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cinema-feature.preview.emergentagent.com").rstrip("/")
MOVIE_ID = "spiderman-bnd-4-1"
MOVIE_SIZE = 954393854


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# --- Movies listing ---
def test_list_movies(s):
    r = s.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "movies" in data and len(data["movies"]) >= 1
    m = data["movies"][0]
    assert m["id"] == MOVIE_ID
    assert m["poster"] == "/spiderman_poster.jpg"
    assert m["backdrop"] == "/spiderman_backdrop.jpg"
    assert m["lang"] == "TÜRKÇE DUBLAJ"
    assert "part" not in m, f"'part' field should not exist, got: {list(m.keys())}"


def test_movie_status(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["ready"] is True, f"expected ready:true, got {d}"


# --- Range streaming ---
def test_range_prefix(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=0-1023"}, timeout=30)
    assert r.status_code == 206
    assert r.headers.get("Content-Range") == f"bytes 0-1023/{MOVIE_SIZE}"
    assert len(r.content) == 1024


def test_range_middle(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=470000000-470001023"}, timeout=30)
    assert r.status_code == 206
    assert "Content-Range" in r.headers
    assert len(r.content) == 1024


def test_range_last_byte(s):
    last = MOVIE_SIZE - 1
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": f"bytes={last}-"}, timeout=30)
    assert r.status_code == 206
    assert len(r.content) == 1


def test_range_out_of_bounds(s):
    r = s.get(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream",
              headers={"Range": "bytes=999999999999-"}, timeout=30)
    assert r.status_code == 416


def test_head_accept_ranges(s):
    r = s.head(f"{BASE_URL}/api/movies/{MOVIE_ID}/stream", timeout=30)
    assert r.status_code == 200
    assert r.headers.get("Accept-Ranges") == "bytes"


# --- Regression ---
def test_health(s):
    r = s.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("mongo") is True


def test_channels(s):
    r = s.get(f"{BASE_URL}/api/channels", timeout=15)
    assert r.status_code == 200
