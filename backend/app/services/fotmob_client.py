"""FotMob erişim modülü — x-mas imzalı header + Next.js data route fallback.

FotMob, /api/* isteklerinde 'x-mas' imza header'ı zorunlu kıldı (imzasız → 401).
Katmanlar:
  1) x-mas imzalı doğrudan API isteği (tercih edilen)
  2) Başarısızsa Next.js data route (/_next/data/{buildId}/...) fallback
  3) O da olmazsa (None, "blocked") döner → çağıran LiveScore-only davranışa düşer.
"""
import base64
import hashlib
import json
import logging
import re
from time import time
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("banbansports.fotmob")

FOTMOB_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# İmza anahtarı — FotMob web istemcisinin kullandığı sabit (Three Lions şarkı sözleri).
# Boş satırlar dahil BİREBİR korunmalı; değişirse imza geçersiz olur.
_LYRICS = '[Spoken Intro: Alan Hansen & Trevor Brooking]\nI think it\'s bad news for the English game\nWe\'re not creative enough, and we\'re not positive enough\n\n[Refrain: Ian Broudie & Jimmy Hill]\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home (We\'ll go on getting bad results)\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\n\n[Verse 1: Frank Skinner]\nEveryone seems to know the score, they\'ve seen it all before\nThey just know, they\'re so sure\nThat England\'s gonna throw it away, gonna blow it away\nBut I know they can play, \'cause I remember\n\n[Chorus: All]\nThree lions on a shirt\nJules Rimet still gleaming\nThirty years of hurt\nNever stopped me dreaming\n\n[Verse 2: David Baddiel]\nSo many jokes, so many sneers\nBut all those "Oh, so near"s wear you down through the years\nBut I still see that tackle by Moore and when Lineker scored\nBobby belting the ball, and Nobby dancing\n\n[Chorus: All]\nThree lions on a shirt\nJules Rimet still gleaming\nThirty years of hurt\nNever stopped me dreaming\n\n[Bridge]\nEngland have done it, in the last minute of extra time!\nWhat a save, Gordon Banks!\nGood old England, England that couldn\'t play football!\nEngland have got it in the bag!\nI know that was then, but it could be again\n\n[Refrain: Ian Broudie]\nIt\'s coming home, it\'s coming\nFootball\'s coming home\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\n(England have done it!)\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\nIt\'s coming home, it\'s coming home, it\'s coming\nFootball\'s coming home\n[Chorus: All]\n(It\'s coming home) Three lions on a shirt\n(It\'s coming home, it\'s coming) Jules Rimet still gleaming\n(Football\'s coming home\nIt\'s coming home) Thirty years of hurt\n(It\'s coming home, it\'s coming) Never stopped me dreaming\n(Football\'s coming home\nIt\'s coming home) Three lions on a shirt\n(It\'s coming home, it\'s coming) Jules Rimet still gleaming\n(Football\'s coming home\nIt\'s coming home) Thirty years of hurt\n(It\'s coming home, it\'s coming) Never stopped me dreaming\n(Football\'s coming home\nIt\'s coming home) Three lions on a shirt\n(It\'s coming home, it\'s coming) Jules Rimet still gleaming\n(Football\'s coming home\nIt\'s coming home) Thirty years of hurt\n(It\'s coming home, it\'s coming) Never stopped me dreaming\n(Football\'s coming home)'


def xmas_header(path: str) -> str:
    body = {"url": path, "code": int(time() * 1000)}
    body_json = json.dumps(body, separators=(",", ":"))
    signature = hashlib.md5((body_json + _LYRICS).encode("utf-8")).hexdigest().upper()
    packet = json.dumps({"body": body, "signature": signature}, separators=(",", ":"))
    return base64.b64encode(packet.encode("utf-8")).decode("ascii")


# ---- Next.js data route fallback ----
_BUILD = {"id": "", "at": 0.0}
_BUILD_TTL = 3600.0


async def _build_id(http: httpx.AsyncClient) -> str:
    if _BUILD["id"] and (time() - _BUILD["at"]) < _BUILD_TTL:
        return _BUILD["id"]
    try:
        r = await http.get("https://www.fotmob.com/", headers=FOTMOB_UA)
        if r.status_code == 200:
            m = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
            if m:
                _BUILD["id"] = m.group(1)
                _BUILD["at"] = time()
    except Exception as e:
        logger.debug(f"fotmob buildId fail: {e}")
    return _BUILD["id"]


def _find_key(node, key: str, depth: int = 5):
    """JSON ağacında verilen anahtarı içeren ilk dict'i döndür (sınırlı derinlik)."""
    if depth < 0:
        return None
    if isinstance(node, dict):
        if key in node:
            return node
        for v in node.values():
            hit = _find_key(v, key, depth - 1)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = _find_key(v, key, depth - 1)
            if hit is not None:
                return hit
    return None


async def _nextdata_fallback(http: httpx.AsyncClient, path: str, expect_key: str) -> Optional[dict]:
    bid = await _build_id(http)
    if not bid:
        return None
    candidates = []
    m = re.search(r"matchDetails\?matchId=(\d+)", path)
    if m:
        mid = m.group(1)
        candidates = [f"/_next/data/{bid}/en/match/{mid}.json",
                      f"/_next/data/{bid}/en/matches/{mid}.json"]
    else:
        m = re.search(r"matches\?date=(\d{8})", path)
        if m:
            candidates = [f"/_next/data/{bid}/en/matches.json?date={m.group(1)}"]
    for url_path in candidates:
        try:
            r = await http.get(f"https://www.fotmob.com{url_path}", headers=FOTMOB_UA)
            if r.status_code != 200:
                continue
            hit = _find_key(r.json(), expect_key)
            if hit is not None:
                return hit
        except Exception as e:
            logger.debug(f"fotmob nextdata fail {url_path}: {e}")
    return None


async def fotmob_get(http: httpx.AsyncClient, path: str, expect_key: str) -> Tuple[Optional[dict], str]:
    """FotMob verisi getir. Döner: (data, durum) — durum: 'ok' | 'ok-nextdata' | 'blocked'.
    data her zaman expect_key anahtarını içeren dict'tir (yoksa None)."""
    try:
        r = await http.get(f"https://www.fotmob.com{path}",
                           headers={**FOTMOB_UA, "x-mas": xmas_header(path)})
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, dict) and expect_key in d:
                return d, "ok"
            hit = _find_key(d, expect_key)
            if hit is not None:
                return hit, "ok"
    except Exception as e:
        logger.debug(f"fotmob signed fail {path}: {e}")
    data = await _nextdata_fallback(http, path, expect_key)
    if data is not None:
        return data, "ok-nextdata"
    return None, "blocked"
