"""Backend regression for banbansports Box Office redesign."""
import os
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True or body.get("status") in ("ok", "healthy")

def test_boxoffice():
    r = requests.get(f"{BASE_URL}/api/boxoffice", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    assert d.get("plot"), "plot must be non-empty"
    assert d["movie"]["title"]
    assert d["gross_usd"]["worldwide"] > 0
    assert isinstance(d.get("fx"), dict)

def test_movies():
    r = requests.get(f"{BASE_URL}/api/movies", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("movies"), list) and len(d["movies"]) > 0

def test_sponsor_click():
    r = requests.post(
        f"{BASE_URL}/api/sponsors/click",
        json={"sponsor_id": "TEST_sponsor", "name": "TEST"},
        timeout=15,
    )
    assert r.status_code in (200, 201, 202, 204)
