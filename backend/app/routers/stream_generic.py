"""Generic stream router — kayıtlı tüm StreamManager'ları HTTP endpoint'ler üzerinden sunar.

Endpointler:
  GET  /api/stream/{ch}/health      → config + canlılık
  POST /api/stream/{ch}/refresh     → manuel token refresh
  GET  /api/stream/{ch}/stream.m3u8 → master proxy (segment rewrite)
  GET  /api/stream/{ch}/seg.ts      → tek segment proxy (SSRF allowlist)
  GET  /api/stream/list             → tüm kayıtlı kanallar
  GET  /api/stream/status           → tüm kanalların anlık {configured, ok} — 60sn cache
"""
import asyncio
import httpx
from urllib.parse import quote
from time import time
from fastapi import APIRouter, HTTPException, Response

from ..services import stream_registry as reg

router = APIRouter(prefix="/api/stream", tags=["stream"])

# Bulk status için process-içi cache (Vercel serverless'ta invocation ömrü boyunca yaşar)
_STATUS_CACHE: dict = {"at": 0.0, "data": {}}
_STATUS_TTL = 60.0  # saniye — segment fetch ağır olduğu için 60sn boyunca aynı sonucu döneriz


@router.get("/list")
async def list_streams():
    out = {}
    for cid, mgr in reg.all_managers().items():
        out[cid] = {
            "configured": mgr.is_configured(),
            "host": mgr.live_host,
            "stream_id": mgr.stream_id,
            "dynamic_tms": mgr.dynamic_tms,
        }
    return out


@router.get("/status")
async def bulk_status():
    """Tüm kanalların anlık `configured + ok` durumu — 60sn cache.
    Frontend LED'lerini bu endpoint'ten dinamik boyar (30sn polling).
    Segment fetch ağır olduğu için cache TTL yüksek tutulur; canlı yayın
    değişikliği maksimum 60sn içinde LED'lere yansır.
    """
    now = time()
    if _STATUS_CACHE["data"] and (now - _STATUS_CACHE["at"]) < _STATUS_TTL:
        return {"cached": True, "age": int(now - _STATUS_CACHE["at"]),
                "channels": _STATUS_CACHE["data"]}

    async def _one(mgr):
        ok = False
        if mgr.is_configured():
            try:
                ok = await mgr.is_token_valid()
            except Exception:
                ok = False
        return mgr.channel_id, {"configured": mgr.is_configured(), "ok": ok}

    tasks = [_one(m) for m in reg.all_managers().values()]
    pairs = await asyncio.gather(*tasks, return_exceptions=False)
    results = dict(pairs)
    _STATUS_CACHE["at"] = now
    _STATUS_CACHE["data"] = results
    return {"cached": False, "age": 0, "channels": results}


@router.get("/{channel_id}/health")
async def health(channel_id: str):
    mgr = reg.get(channel_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Channel not registered")
    if not mgr.is_configured():
        return {"configured": False, "ok": False}
    valid = await mgr.is_token_valid()
    return {
        "configured": True,
        "ok": valid,
        "dynamic_tms": mgr.dynamic_tms,
        "current_tms": mgr._effective_tms(),
        "token_preview": (mgr.current_token[:8] + "…") if mgr.current_token else "",
        "last_refresh_age_seconds": int(time() - mgr.last_refresh),
    }


@router.post("/{channel_id}/refresh")
async def refresh(channel_id: str):
    mgr = reg.get(channel_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Channel not registered")
    ok = await mgr.try_auto_refresh()
    return {"refreshed": ok, "token_preview": (mgr.current_token[:8] + "…") if mgr.current_token else ""}


@router.get("/{channel_id}/stream.m3u8")
async def stream_m3u8(channel_id: str):
    mgr = reg.get(channel_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Channel not registered")
    if not mgr.is_configured():
        raise HTTPException(status_code=503, detail=f"{channel_id} token not configured")

    await mgr.hydrate()  # cron'un DB'ye yazdığı güncel token'ı kullan (Vercel serverless)
    url = mgr.get_stream_url()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
            r = await http.get(url, headers={
                "User-Agent": mgr.user_agent,
                "Accept": "*/*",
                "Host": mgr.live_host,
            })
            # Token expired → auto refresh + 1 retry
            if r.status_code in (401, 403, 404, 410):
                if await mgr.try_auto_refresh():
                    r = await http.get(mgr.get_stream_url(), headers={
                        "User-Agent": mgr.user_agent,
                        "Accept": "*/*",
                        "Host": mgr.live_host,
                    })
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Upstream unavailable")

            base = mgr.get_segment_base()
            lines = r.text.split("\n")
            new = []
            for line in lines:
                if line.startswith("#") or not line.strip():
                    new.append(line)
                    continue
                seg = line.strip()
                # Absolute URL değilse absolute yap
                if not seg.startswith("http"):
                    if seg.startswith("/"):
                        seg = f"https://{mgr.live_host}{seg}"
                    else:
                        seg = base + seg
                # ÖNEMLİ: Child playlist (.m3u8) mı yoksa segment (.ts vs) mi?
                # Master playlist'te BANDWIDTH/RESOLUTION variant'ları yer alır ve satırlar
                # child m3u8'i işaret eder. Bunları `seg.ts` proxy'sine gönderirsek HLS.js
                # binary bekleyip m3u8 alır → siyah ekran. Doğrusu: child'ları
                # `/playlist.m3u8?url=...` üzerinden proxy'lemek.
                seg_lower = seg.split("?", 1)[0].lower()
                if seg_lower.endswith(".m3u8"):
                    new.append(f"/api/stream/{channel_id}/playlist.m3u8?url={quote(seg, safe='')}")
                else:
                    new.append(f"/api/stream/{channel_id}/seg.ts?url={quote(seg, safe='')}")
            return Response(
                content="\n".join(new),
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {e}")


@router.get("/{channel_id}/playlist.m3u8")
async def child_playlist(channel_id: str, url: str):
    """Master playlist'in içindeki VARIANT/CHILD playlist'i proxy'ler.
    İçindeki segment URL'lerini de aynı prensiple `seg.ts?url=...` şeklinde rewrite eder.
    SSRF allowlist ile korunur (stream registry'deki host'lar).
    """
    mgr = reg.get(channel_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Channel not registered")
    if not mgr.host_allowed(url):
        raise HTTPException(status_code=403, detail="Host not allowed")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
            r = await http.get(url, headers={
                "User-Agent": mgr.user_agent,
                "Accept": "*/*",
                "Host": mgr.live_host,
            })
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Child playlist unavailable")
            # Child playlist'in içindeki segment path'lerini absolute'a çevir + rewrite et
            # Base URL child playlist'in dirname'i
            base = url.rsplit("/", 1)[0] + "/" if "/" in url else url
            lines = r.text.split("\n")
            new = []
            for line in lines:
                if line.startswith("#") or not line.strip():
                    new.append(line)
                    continue
                seg = line.strip()
                if not seg.startswith("http"):
                    if seg.startswith("/"):
                        # Absolute path — live_host'a yasla
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        seg = f"{parsed.scheme}://{parsed.netloc}{seg}"
                    else:
                        seg = base + seg
                seg_lower = seg.split("?", 1)[0].lower()
                if seg_lower.endswith(".m3u8"):
                    # Nested child (nadiren olur ama) — yine playlist proxy
                    new.append(f"/api/stream/{channel_id}/playlist.m3u8?url={quote(seg, safe='')}")
                else:
                    new.append(f"/api/stream/{channel_id}/seg.ts?url={quote(seg, safe='')}")
            return Response(
                content="\n".join(new),
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Child playlist proxy error: {e}")


@router.get("/{channel_id}/seg.ts")
async def segment(channel_id: str, url: str):
    mgr = reg.get(channel_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Channel not registered")
    if not mgr.host_allowed(url):
        raise HTTPException(status_code=403, detail="Host not allowed")
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http:
            r = await http.get(url, headers={
                "User-Agent": mgr.user_agent,
                "Accept": "*/*",
                "Host": mgr.live_host,
            })
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Segment failed")
            return Response(
                content=r.content,
                media_type="video/mp2t",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "private, max-age=60",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Segment proxy error: {e}")
