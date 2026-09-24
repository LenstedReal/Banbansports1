"""Iteration 3 backend smoke tests for banbansports."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")


def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200


def test_scores_top():
    r = requests.get(f"{BASE_URL}/api/scores/top?n=5", timeout=20)
    assert r.status_code == 200
    data = r.json()
    matches = data.get("matches") if isinstance(data, dict) else data
    assert isinstance(matches, list)
    assert len(matches) >= 1, f"expected >=1 matches, got: {data}"


def test_livescore_today():
    r = requests.get(f"{BASE_URL}/api/livescore/today", timeout=20)
    assert r.status_code == 200


def test_featured_status():
    r = requests.get(f"{BASE_URL}/api/featured/status", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("match"), f"featured.match empty: {data}"


def test_movies_list():
    r = requests.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    data = r.json()
    movies = data if isinstance(data, list) else data.get("movies", [])
    assert len(movies) >= 1
    # find spiderman
    found = None
    for m in movies:
        if "spiderman" in (m.get("id") or m.get("slug") or "").lower() or "spider" in (m.get("title_en") or m.get("title") or "").lower():
            found = m
            break
    assert found is not None, "spiderman movie not found"
    assert "July 31, 2026" in (found.get("release_date") or ""), f"release_date wrong: {found.get('release_date')}"


def test_movie_status():
    r = requests.get(f"{BASE_URL}/api/movies/spiderman-bnd-4-1/status", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ready") is True, f"not ready: {data}"
    assert data.get("mode") == "cache", f"mode not cache: {data}"


def test_movie_stream_range():
    r = requests.get(
        f"{BASE_URL}/api/movies/spiderman-bnd-4-1/stream",
        headers={"Range": "bytes=0-99"},
        timeout=20,
    )
    assert r.status_code == 206, f"status: {r.status_code}"
    assert "video/mp4" in r.headers.get("content-type", "")
    assert len(r.content) == 100, f"got {len(r.content)} bytes"


def test_match_by_slug():
    slug = "Arsenal__Borussia_Dortmund__20260809"
    r = requests.get(f"{BASE_URL}/api/match/by-slug/{slug}", timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    score = data.get("score") or {}
    assert score.get("home") == 2, f"home: {score}"
    assert score.get("away") == 3, f"away: {score}"
    assert str(score.get("pen_home")) == "5"
    assert str(score.get("pen_away")) == "4"


def test_ssr_match_page():
    slug = "Arsenal__Borussia_Dortmund__20260809"
    r = requests.get(f"{BASE_URL}/match/{slug}", timeout=30)
    assert r.status_code == 200
    html = r.text
    assert "2" in html and "3" in html
    assert "PEN" in html.upper() or "pen" in html.lower()
