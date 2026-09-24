"""Backend regression tests for HLS/CDN movie stream + boxoffice rewrite."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://branded-sports-shop.preview.emergentagent.com").rstrip("/")


class TestMovies:
    def test_movies_list_first_entry(self):
        r = requests.get(f"{BASE_URL}/api/movies", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # data may be list or dict wrapper
        movies = data if isinstance(data, list) else data.get("movies") or data.get("items") or []
        assert len(movies) > 0, f"No movies returned: {data}"
        m = movies[0]
        assert m.get("id") == "spiderman-bnd-4-1", f"Unexpected id: {m.get('id')}"
        assert m.get("stream_dub") == "https://stream.lenstedreal.xyz/stream.m3u8"
        assert m.get("stream_sub") == "https://stream1.lenstedreal.xyz/stream.m3u8"
        assert "source_page" not in m, "source_page should not be present"

    def test_movie_status_hls(self):
        r = requests.get(f"{BASE_URL}/api/movies/spiderman-bnd-4-1/status", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ready") is True, data
        assert data.get("mode") == "hls", data


class TestBoxOffice:
    def test_boxoffice_current(self):
        r = requests.get(f"{BASE_URL}/api/boxoffice", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True, data
        local = data.get("local", {})
        tr = local.get("TRY", {})
        assert tr.get("ticket_price_used_native") == 240.0, tr
        assert tr.get("viewers", 0) > 1_000_000, tr
        fx = data.get("fx", {})
        assert 40 <= fx.get("TRY", 0) <= 60, fx
        assert fx.get("EUR", 999) < 1, fx
        assert "active_source" in data.get("fx_metadata", {}), data.get("fx_metadata")

    def test_boxoffice_history(self):
        r = requests.get(f"{BASE_URL}/api/boxoffice/history", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True, data
        assert isinstance(data.get("history"), list), data


class TestHLSStreams:
    @pytest.mark.parametrize("url", [
        "https://stream.lenstedreal.xyz/stream.m3u8",
        "https://stream1.lenstedreal.xyz/stream.m3u8",
    ])
    def test_hls_reachable(self, url):
        r = requests.get(url, timeout=15)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        assert r.text.lstrip().startswith("#EXTM3U"), f"{url} not HLS: {r.text[:80]}"
