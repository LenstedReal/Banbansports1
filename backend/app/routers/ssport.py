"""Backward-compat: /api/ssport/* → /api/stream/ssport/* redirect.

Eski URL'leri koruyoruz ki mevcut frontend kırılmasın. Yeni kanal eklemek için
generic /api/stream/{ch}/* kullanın.
"""
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/api/ssport", tags=["ssport-compat"])


@router.get("/health")
async def health_redirect():
    return RedirectResponse(url="/api/stream/ssport/health", status_code=307)


@router.post("/refresh")
async def refresh_redirect():
    return RedirectResponse(url="/api/stream/ssport/refresh", status_code=307)


@router.get("/stream.m3u8")
async def stream_redirect():
    return RedirectResponse(url="/api/stream/ssport/stream.m3u8", status_code=307)


@router.get("/seg.ts")
async def segment_redirect(url: str):
    from urllib.parse import quote
    return RedirectResponse(url=f"/api/stream/ssport/seg.ts?url={quote(url, safe='')}", status_code=307)
