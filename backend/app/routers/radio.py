"""BANBAN LIVE RADIO — Radio Browser API (PRD-B).

/api/radio?tag=&q=&country=TR  → skorlanmis istasyon listesi (5 dk cache)
/api/radio/click/{uuid}         → istasyon sayaci (Radio Browser'a iletilir)
/api/radio/servers              → kesfedilen sunucular
DNS sunucu kesfi: all.api.radio-browser.info → yedek sabit liste. UA zorunlu. hidebroken=true.
"""
import logging
import random
import socket
import time

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("banbansports.radio")
router = APIRouter(prefix="/api/radio", tags=["radio"])

UA = "banbansports/1.0 (https://banban.lenstedreal.xyz)"
FALLBACK = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info", "at1.api.radio-browser.info", "fi1.api.radio-browser.info"]
_cache: dict[str, tuple[float, list]] = {}
_servers: tuple[float, list[str]] = (0.0, [])
CACHE_TTL = 300


def _discover() -> list[str]:
    global _servers
    if time.time() - _servers[0] < 3600 and _servers[1]:
        return _servers[1]
    hosts: list[str] = []
    try:
        for info in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
            ip = info[4][0]
            try:
                hosts.append(socket.gethostbyaddr(ip)[0])
            except Exception:
                pass
    except Exception as e:
        logger.debug("radio dns: %s", e)
    hosts = sorted(set(h for h in hosts if h.endswith("radio-browser.info"))) or list(FALLBACK)
    random.shuffle(hosts)
    _servers = (time.time(), hosts)
    return hosts


def _score(s: dict) -> float:
    sc = 0.0
    url = (s.get("url_resolved") or s.get("url") or "")
    if url.startswith("https://"):
        sc += 30
    codec = (s.get("codec") or "").upper()
    if codec in ("MP3", "AAC", "AAC+"):
        sc += 20
    br = int(s.get("bitrate") or 0)
    sc += min(br, 320) / 16
    if int(s.get("lastcheckok") or 0) == 1:
        sc += 25
    sc += min(int(s.get("clickcount") or 0), 5000) / 250
    sc += min(int(s.get("votes") or 0), 5000) / 500
    if ".m3u8" in url or ".pls" in url or ".m3u" in url.split("?")[0]:
        sc -= 40
    return sc


def _pub(s: dict) -> dict:
    return {"uuid": s.get("stationuuid"), "name": (s.get("name") or "").strip()[:60], "url": s.get("url_resolved") or s.get("url"),
            "codec": (s.get("codec") or "").upper(), "bitrate": int(s.get("bitrate") or 0), "country": s.get("countrycode") or "",
            "tags": (s.get("tags") or "")[:80], "favicon": s.get("favicon") or "", "homepage": s.get("homepage") or "",
            "clicks": int(s.get("clickcount") or 0), "ok": int(s.get("lastcheckok") or 0) == 1}


async def _fetch(path: str, params: dict) -> list:
    last = None
    for host in _discover()[:4]:
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": UA}) as c:
                r = await c.get(f"https://{host}{path}", params=params)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            last = e
            continue
    raise HTTPException(status_code=502, detail=f"Radio Browser'a ulasilamadi: {last}")


@router.get("")
async def stations(tag: str = "", q: str = "", country: str = "TR", limit: int = 60):
    key = f"{country}|{tag}|{q}|{limit}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return {"stations": hit[1], "cached": True}
    params = {"hidebroken": "true", "order": "clickcount", "reverse": "true", "limit": min(max(limit, 1), 150) * 2}
    if country:
        params["countrycode"] = country.upper()[:2]
    if tag:
        params["tag"] = tag.lower()[:40]
    if q:
        params["name"] = q[:60]
    raw = await _fetch("/json/stations/search", params)
    seen, out = set(), []
    for s in sorted(raw, key=_score, reverse=True):
        u = s.get("url_resolved") or s.get("url")
        if not u or u in seen:
            continue
        base = u.split("?")[0].lower()
        # Tarayıcı <audio> HLS/playlist dosyalarını çalamaz; yalnızca doğrudan MP3/AAC akışları
        if base.endswith((".m3u8", ".m3u", ".pls", ".asx", ".xspf")) or int(s.get("hls") or 0) == 1:
            continue
        if int(s.get("lastcheckok") or 0) != 1:
            continue
        seen.add(u)
        out.append(_pub(s))
    _cache[key] = (time.time(), out)
    return {"stations": out, "cached": False}


@router.get("/servers")
async def servers():
    return {"servers": _discover()}


@router.post("/click/{uuid}")
async def click(uuid: str):
    try:
        await _fetch(f"/json/url/{uuid[:64]}", {})
    except HTTPException:
        pass
    return {"ok": True}
