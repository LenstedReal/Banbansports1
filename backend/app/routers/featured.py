"""Öne çıkan yayın (featured) — tünellenmiş residential kaynağı proxy'ler.

Kaynak env'den gelir (FEATURED_SOURCE_URL). Genelde bir cloudflared/ngrok tüneli
(residential IP'li Termux köprüsü) — datacenter'dan erişilebilir olduğu için düz
httpx yeterli (curl_cffi gerekmez).

Manifest içindeki segment URL'leri MUTLAK CDN adresleridir; bunları rewrite ETMEYİZ
→ son kullanıcının tarayıcısı (residential IP) segmentleri doğrudan CDN'den çeker,
böylece datacenter IP engeli devreye girmez. Yalnız göreli URL'ler FEATURED_SEGMENT_BASE
ile mutlaklaştırılır.

Endpointler:
  * /api/featured/status      → kaynak canlı mı? (yeşil/turuncu LED) — 30sn cache
  * /api/featured/stream.m3u8 → manifest proxy (CORS + göreli→mutlak)
"""
import logging
import os
import asyncio
import httpx
try:
    # curl_cffi opsiyonel: Vercel/serverless'ta paket yoksa httpx fallback
    from curl_cffi import requests as cffi_requests
except Exception:  # pragma: no cover
    cffi_requests = None
import jwt  # noqa: F401 — geriye dönük import uyumluluğu
from time import time
from urllib.parse import urljoin, quote, urlparse
from fastapi import APIRouter, HTTPException, Response

from ..core.stream_tokens import sign_hls_params, strip_auth_params, with_params
from ..services.tv_schedule import pick_featured, pick_day_match, APP_CHANNEL_NAMES

logger = logging.getLogger("banbansports.featured")
router = APIRouter(prefix="/api/featured", tags=["featured"])

_TIMEOUT = 15.0
_STATUS_CACHE = {"at": 0.0, "live": False}
_STATUS_TTL = 30.0
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _cfg():
    return {
        "source": os.environ.get("FEATURED_SOURCE_URL", "").strip(),
        "channel": os.environ.get("FEATURED_CHANNEL", "bein1").strip(),
        "name": os.environ.get("FEATURED_NAME", "").strip(),
        "seg_base": os.environ.get("FEATURED_SEGMENT_BASE", "").strip(),
    }


_GUARDED_HOSTS = {"stream.lenstedreal.xyz": "dub", "stream1.lenstedreal.xyz": "sub"}


def _guard_url(url: str) -> str:
    """Kaynak Worker korumalı hostta ise backend kendi kısa ömürlü HMAC imzasını (m=srv, 5 dk) URL'e ekler."""
    host = urlparse(url).hostname or ""
    src = _GUARDED_HOSTS.get(host)
    if not src or not os.environ.get("STREAM_TOKEN_SECRET", "").strip():
        return url
    params, _ttl = sign_hls_params(host, "featured", src, "featured-proxy", "backend", "srv")
    return with_params(url, params)


def _seg_allowed(url: str) -> bool:
    """Host allowlist: FEATURED_SEGMENT_BASE / FEATURED_SOURCE_URL hostları + son manifestte görülen hostlar."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    cfg = _cfg()
    static = {urlparse(cfg["seg_base"]).hostname, urlparse(cfg["source"]).hostname} - {None, ""}
    return p.hostname in static or p.hostname in _manifest_hosts


async def _fetch(url: str):
    # Kaynak Cloudflare arkasında (tünel = orange cloud). Düz httpx bazen bot
    # challenge (HTML) yiyor; curl_cffi impersonate gerçek Chrome TLS parmak izi
    # ile bunu güvenilir şekilde geçer. Sync olduğu için thread'e alıyoruz.
    headers = {"User-Agent": _UA, "Accept": "*/*"}
    url = _guard_url(url)

    def _do():
        if cffi_requests is not None:
            return cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=_TIMEOUT)
        return httpx.get(url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
    return await asyncio.to_thread(_do)


# === SEGMENT CACHE + ARKA PLAN ÖN-YÜKLEME ===
# Evin upload hızı darboğaz (4MB segment ~7sn). Backend segmentleri sürekli
# önceden indirip belleğe alır → oynatıcı istediğinde ANINDA verir, home upload
# gizlenir, çoklu izleyicide telefon yükü artmaz (her segment 1 kez indirilir).
_seg_cache: dict = {}            # abs_url (auth param'sız) -> (bytes, ts)
_SEG_CACHE_MAX = 24
_SEG_TTL = 180.0
_last_activity = 0.0
_prefetch_started = False
_manifest_hosts: set = set()     # son manifestte görülen segment hostları (seg allowlist)


def _seg_abs_urls(text: str, source: str) -> list:
    seg_base = _cfg()["seg_base"] or (source.rsplit("/", 1)[0] + "/")
    urls = []
    for line in text.split("\n"):
        s = line.strip()
        if s and not s.startswith("#"):
            # Worker'ın bastığı auth param'ları cache anahtarından ayıklanır (her manifestte exp/sig değişir)
            u = strip_auth_params(s if s.startswith("http") else urljoin(seg_base, s))
            urls.append(u)
            h = urlparse(u).hostname
            if h:
                _manifest_hosts.add(h)
    return urls


def _cache_put(url: str, data: bytes):
    _seg_cache[url] = (data, time())
    if len(_seg_cache) > _SEG_CACHE_MAX:
        for k in sorted(_seg_cache, key=lambda k: _seg_cache[k][1])[:len(_seg_cache) - _SEG_CACHE_MAX]:
            _seg_cache.pop(k, None)


_inflight: dict = {}   # url -> asyncio.Task (aynı segment 2 kez indirilmesin)


async def _get_segment(url: str) -> bytes:
    """Segmenti getir: önce cache (TTL'li), sonra tek bir indirme (in-flight dedup)."""
    c = _seg_cache.get(url)
    if c:
        if time() - c[1] < _SEG_TTL:
            return c[0]
        _seg_cache.pop(url, None)
    task = _inflight.get(url)
    fresh = task is None
    if fresh:
        task = asyncio.create_task(_fetch_seg(url))
        _inflight[url] = task
    try:
        return await task
    finally:
        if fresh:
            _inflight.pop(url, None)


async def _fetch_seg(url: str) -> bytes:
    r = await _fetch(url)
    if r.status_code != 200 or not r.content:
        raise HTTPException(status_code=502, detail=f"segment {r.status_code}")
    _cache_put(url, r.content)
    return r.content


async def _prefetch_loop():
    global _prefetch_started
    _prefetch_started = True
    logger.info("featured prefetch loop started")
    while True:
        try:
            if (time() - _last_activity) > 90:      # izleyici yoksa dinlen
                await asyncio.sleep(3)
                continue
            cfg = _cfg()
            if not cfg["source"]:
                await asyncio.sleep(5)
                continue
            r = await _fetch(cfg["source"])
            if r.status_code == 200 and r.text.lstrip().startswith("#EXTM3U"):
                for u in _seg_abs_urls(r.text, cfg["source"]):
                    if u not in _seg_cache:
                        try:
                            await _get_segment(u)   # dedup'lı: viewer ile çakışmaz
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"prefetch err: {e}")
        await asyncio.sleep(1.5)


def _ensure_prefetch():
    global _last_activity, _prefetch_started
    _last_activity = time()
    if not _prefetch_started:
        _prefetch_started = True
        try:
            asyncio.create_task(_prefetch_loop())
        except Exception as e:
            _prefetch_started = False
            logger.debug(f"prefetch start fail: {e}")


async def _source_live() -> bool:
    """mono.m3u8 kaynağı erişilebilir mi? (30sn cache — telefon/tünel yormasın)"""
    now = time()
    if (now - _STATUS_CACHE["at"]) < _STATUS_TTL:
        return _STATUS_CACHE["live"]
    live = False
    try:
        r = await _fetch(_cfg()["source"])
        live = r.status_code == 200 and r.text.lstrip().startswith("#EXTM3U")
    except Exception as e:
        logger.debug(f"featured source check fail: {e}")
    _STATUS_CACHE["at"] = now
    _STATUS_CACHE["live"] = live
    return live


@router.get("/status")
async def status():
    """Öne çıkan yayının DİNAMİK durumu:
      * channel  → günün programına göre otomatik seçilen kanal kutusu (bein1/trt1/...)
      * live     → kaynak ayakta VE şu an o kanalda canlı maç var
      * status   → live | upcoming | none
      * match    → seçilen maçın bilgisi (takımlar, lig, saat, başlangıca kalan dk)
    """
    cfg = _cfg()
    if not cfg["source"]:
        # GÜNÜN MAÇI kaynak yapılandırmasından bağımsız çalışsın
        try:
            day_match = await pick_day_match()
        except Exception as e:
            logger.debug(f"day match fail: {e}")
            day_match = None
        return {"configured": False, "live": False, "source_live": False,
                "channel": "", "name": "", "status": "none", "match": day_match}

    source_live = await _source_live()

    # Günün TV programından öne çıkan kanalı bul (schedule 15dk cache'li).
    # Yayın kaynağı fiziksel olarak beIN Sports 1 → varsayılan kutu beIN 1;
    # yalnızca Galatasaray başka kanalda canlıysa o kanala geçer.
    try:
        pick = await pick_featured(source_live)
    except Exception as e:
        logger.debug(f"featured pick fail, env fallback: {e}")
        pick = None

    # GÜNÜN MAÇI kutusu — günün en önemli maçı (kanal bizde olmasa da bilgi döner)
    try:
        day_match = await pick_day_match()
    except Exception as e:
        logger.debug(f"day match fail: {e}")
        day_match = None

    if pick is None:
        # Scraper patlarsa: env kanalına düş (yayın gizlenmesin — graceful degrade)
        env_ch = cfg["channel"] or "bein1"
        name = cfg["name"] or APP_CHANNEL_NAMES.get(env_ch, env_ch.upper())
        return {"configured": True, "source_live": source_live,
                "live": source_live, "channel": env_ch, "name": name,
                "status": "live" if source_live else "none", "match": day_match}

    return {"configured": True, "source_live": source_live,
            "live": pick["status"] == "live", "channel": pick["channel"],
            "name": pick["name"], "status": pick["status"], "match": day_match}


@router.get("/stream.m3u8")
async def stream_m3u8():
    cfg = _cfg()
    if not cfg["source"]:
        raise HTTPException(status_code=503, detail="Öne çıkan yayın yapılandırılmadı")
    _ensure_prefetch()   # izleyici geldi → arka plan ön-yükleme başlasın
    try:
        r = await _fetch(cfg["source"])
        if r.status_code != 200 or not r.text.lstrip().startswith("#EXTM3U"):
            raise HTTPException(status_code=502, detail="Kaynak yayın erişilemez")
        seg_base = cfg["seg_base"] or (cfg["source"].rsplit("/", 1)[0] + "/")
        out = []
        for line in r.text.split("\n"):
            s = line.strip()
            if not s or s.startswith("#"):
                out.append(line)
                continue
            # Segment URL'sini MUTLAKLAŞTIR, sonra BACKEND proxy'sine sar.
            # Böylece tarayıcı segmenti bizim üzerimizden çeker → istemcinin
            # stream.lenstedreal.xyz'yi çözebilmesi GEREKMEZ (short.io/DNS sorunu biter).
            abs_url = strip_auth_params(s if s.startswith("http") else urljoin(seg_base, s))
            h = urlparse(abs_url).hostname
            if h:
                _manifest_hosts.add(h)
            out.append(f"/api/featured/seg?u={quote(abs_url, safe='')}")
        return Response(content="\n".join(out),
                        media_type="application/vnd.apple.mpegurl",
                        headers={"Access-Control-Allow-Origin": "*",
                                 "Cache-Control": "no-cache, no-store, must-revalidate"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {e}")


@router.get("/seg")
async def seg(u: str):
    """Segment proxy — host allowlist + cache/in-flight dedup ile tek indirme, çoklu servis."""
    if not u:
        raise HTTPException(status_code=400, detail="segment yok")
    u = strip_auth_params(u)
    if not _seg_allowed(u):
        raise HTTPException(status_code=403, detail="segment hostu izinli değil")
    global _last_activity
    _last_activity = time()
    hit = u in _seg_cache
    try:
        data = await _get_segment(u)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"segment fetch failed: {e}")
    return Response(content=data, media_type="video/mp2t",
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache",
                             "X-Cache": "HIT" if hit else "MISS"})
