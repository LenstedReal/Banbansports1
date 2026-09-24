"""Generic HLS proxy + stream health (proxy any m3u8 with CORS + segment rewriting)."""
import re
import httpx
from urllib.parse import urlparse, urljoin, quote
from fastapi import APIRouter, HTTPException, Response

from ..core.config import HLS_PROXY_TIMEOUT, ST11_VALIDATE_TIMEOUT

router = APIRouter(prefix="/api", tags=["streams"])

# === SSRF Allowlist — sadece bilinen yayın domainleri (güvenlik fix) ===
STREAM_PROXY_ALLOWED_HOSTS = {
    # TRT
    "tv-trt1.medya.trt.com.tr", "tv-trt2.medya.trt.com.tr",
    "tv-trthaber.medya.trt.com.tr", "tv-trtspor1.medya.trt.com.tr",
    "tv-trtspor2.medya.trt.com.tr", "tv-trtbelgesel.medya.trt.com.tr",
    # Doğan/Demirören CDN
    "tv8.daioncdn.net", "tv8-5.daioncdn.net", "tv8int.daioncdn.net",
    # ST11/ST23 beIN
    "st11.lol", "st23.lol",
    # ST15 S Sport
    "live.st15.lol", "st15.lol",
    # Akamai
    "dt-vod-bc-hd.akamaized.net", "cph-p2p-msl.akamaized.net",
    # Test/demo
    "demo.unified-streaming.com", "test-streams.mux.dev",
}


def _host_allowed(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").split(":")[0].lower()
        if not host:
            return False
        if host in STREAM_PROXY_ALLOWED_HOSTS:
            return True
        # subdomain match (örn. *.akamaized.net, *.medya.trt.com.tr)
        for allowed in STREAM_PROXY_ALLOWED_HOSTS:
            if host.endswith("." + allowed):
                return True
        return False
    except Exception:
        return False


@router.get("/stream/health")
async def check_stream_health(url: str):
    if not _host_allowed(url):
        raise HTTPException(status_code=403, detail="Host not allowed")
    try:
        async with httpx.AsyncClient(timeout=ST11_VALIDATE_TIMEOUT, follow_redirects=True) as http:
            r = await http.head(url, headers={"User-Agent": "Mozilla/5.0"})
            return {"url": url, "status": r.status_code, "ok": r.status_code == 200,
                    "content_type": r.headers.get("content-type", "")}
    except Exception as e:
        return {"url": url, "status": 0, "ok": False, "error": str(e)}


@router.get("/stream/proxy")
async def proxy_stream(url: str, max_level: int = 2160):
    """HLS master/playlist proxy.
    max_level: maks dikey çözünürlük. Default 2160 → 4K destekleyen streamler için.
    Düşük cihazlar `?max_level=720` ile düşürebilir.
    """
    if not _host_allowed(url):
        raise HTTPException(status_code=403, detail="Host not allowed")
    try:
        async with httpx.AsyncClient(timeout=HLS_PROXY_TIMEOUT, follow_redirects=True) as http:
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            base_url = f"{parsed.scheme}://{parsed.netloc}{'/'.join(parsed.path.split('/')[:-1])}/"
            r = await http.get(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
                "Origin": domain,
                "Referer": domain + "/",
            })
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Stream fetch failed")
            lines = r.text.split('\n')
            new_lines, i = [], 0
            while i < len(lines):
                line = lines[i]
                if line.startswith('#EXT-X-STREAM-INF'):
                    res_m = re.search(r'RESOLUTION=\d+x(\d+)', line)
                    if res_m and int(res_m.group(1)) > max_level:
                        i += 2
                        continue
                    # CODECS attribute'unu KALDIRMA — HLS.js level negotiation'ı CODECS'e bakıyor.
                    # Eski hack: tüm CODECS'i siliyordu → bazı tarayıcılarda levels.length=1 → kalite dropdown çalışmıyor (Bug #1).
                    # Yeni davranış: SADECE eski H.264 + AAC codec string'leri varsa temizle (manifestIncompatibleCodecsError yaratabilir).
                    # Modern codec string'leri (avc1.640028, mp4a.40.2 vs.) bırak — HLS.js doğru level seçer.
                    # Eğer codecs string'i şüpheli karakterler içeriyorsa (boşluk fazla, çift virgül) temizle.
                    codecs_m = re.search(r'CODECS="([^"]*)"', line)
                    if codecs_m:
                        codecs_str = codecs_m.group(1)
                        # Sadece tamamen bozuk / boş / şüpheli codec string'lerini temizle
                        if not codecs_str.strip() or codecs_str.count(',,') > 0 or len(codecs_str) > 100:
                            line = re.sub(r',?CODECS="[^"]*"', '', line)
                if line.startswith('#'):
                    if 'URI="' in line:
                        m = re.search(r'URI="([^"]+)"', line)
                        if m:
                            key_url = m.group(1)
                            if not key_url.startswith('http'):
                                key_url = urljoin(base_url, key_url)
                            line = re.sub(r'URI="[^"]+"', f'URI="/api/stream/ts?url={quote(key_url, safe="")}"', line)
                    new_lines.append(line)
                elif line.strip() and not line.startswith('#'):
                    seg_url = line.strip()
                    if not seg_url.startswith('http'):
                        seg_url = urljoin(base_url, seg_url)
                    new_lines.append(f'/api/stream/ts?url={quote(seg_url, safe="")}')
                else:
                    new_lines.append(line)
                i += 1
            return Response(content='\n'.join(new_lines),
                            media_type="application/vnd.apple.mpegurl",
                            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/ts")
async def proxy_ts(url: str):
    if not _host_allowed(url):
        raise HTTPException(status_code=403, detail="Host not allowed")
    try:
        async with httpx.AsyncClient(timeout=HLS_PROXY_TIMEOUT, follow_redirects=True) as http:
            r = await http.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Segment fetch failed")
            content_type = r.headers.get('content-type', 'video/mp2t')
            if 'mpegurl' in content_type.lower() or url.endswith('.m3u8'):
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}{'/'.join(parsed.path.split('/')[:-1])}/"
                lines = r.text.split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith('#'):
                        if 'URI="' in line:
                            m = re.search(r'URI="([^"]+)"', line)
                            if m:
                                key_url = m.group(1)
                                if not key_url.startswith('http'):
                                    key_url = urljoin(base_url, key_url)
                                line = re.sub(r'URI="[^"]+"', f'URI="/api/stream/ts?url={quote(key_url, safe="")}"', line)
                        new_lines.append(line)
                    elif line.strip() and not line.startswith('#'):
                        seg_url = line.strip()
                        if not seg_url.startswith('http'):
                            seg_url = urljoin(base_url, seg_url)
                        new_lines.append(f'/api/stream/ts?url={quote(seg_url, safe="")}')
                    else:
                        new_lines.append(line)
                return Response(content='\n'.join(new_lines),
                                media_type="application/vnd.apple.mpegurl",
                                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"})
            if url.endswith('.ts'):
                content_type = 'video/mp2t'
            elif url.endswith('.key') or 'key' in url.lower():
                content_type = 'application/octet-stream'
            return Response(content=r.content, media_type=content_type,
                            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
