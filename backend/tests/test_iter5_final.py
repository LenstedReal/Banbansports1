import os
import requests
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env.get("REACT_APP_BACKEND_URL")).rstrip("/")


def test_health():
    r = requests.get(f"{BASE}/api/health", timeout=15)
    assert r.status_code == 200, r.text


def test_movies_list_release_date():
    r = requests.get(f"{BASE}/api/movies", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("movies") or data.get("items") or []
    assert items, f"no movies: {data}"
    found = False
    for m in items:
        rd = m.get("release_date") or m.get("releaseDate")
        if rd == "July 31, 2026":
            found = True
            break
    assert found, f"release_date 'July 31, 2026' not found in {[m.get('release_date') or m.get('releaseDate') for m in items]}"


def test_movie_status_ready_cache():
    r = requests.get(f"{BASE}/api/movies/spiderman-bnd-4-1/status", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ready") is True, d
    assert d.get("mode") == "cache", d


def test_movie_stream_range():
    r = requests.get(
        f"{BASE}/api/movies/spiderman-bnd-4-1/stream",
        headers={"Range": "bytes=0-99"},
        timeout=30,
        stream=True,
    )
    assert r.status_code == 206, f"{r.status_code} {r.headers}"
    ct = r.headers.get("Content-Type", "")
    assert "video/mp4" in ct, ct


def test_featured_status():
    r = requests.get(f"{BASE}/api/featured/status", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("match"), f"match empty: {d}"


def test_scores_top():
    r = requests.get(f"{BASE}/api/scores/top?n=3", timeout=20)
    assert r.status_code == 200, r.text


def test_match_by_slug():
    slug = "Arsenal__Borussia_Dortmund__20260809"
    r = requests.get(f"{BASE}/api/match/by-slug/{slug}", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    # look for score 2-3 pen 5-4
    text = str(d)
    assert ("2-3" in text or ("home" in text and "away" in text)), d
    # try common fields
    score = d.get("score") or {}
    pens = d.get("penalties") or d.get("pen") or {}
    home = d.get("home_score", score.get("home"))
    away = d.get("away_score", score.get("away"))
    assert (home == 2 and away == 3) or "2-3" in text, f"expected 2-3, got {d}"
    ph = d.get("pen_home", pens.get("home") if isinstance(pens, dict) else None)
    pa = d.get("pen_away", pens.get("away") if isinstance(pens, dict) else None)
    assert (ph == 5 and pa == 4) or "5-4" in text, f"expected pen 5-4, got {d}"
