"""Internal endpoints — Vercel Cron tarafından tetiklenir.

Authentication: `Authorization: Bearer <CRON_SECRET>` header gerekli.
  - Vercel Cron otomatik olarak `Authorization: Bearer <CRON_SECRET>` header gönderir
    (CRON_SECRET ENV variable'ı set edildiğinde).
  - Dış dünyaya kapalı: secret bilinmeden çağrılamaz.

Endpoint'ler:
  POST /api/internal/ssport-refresh   → S Sport token refresh
  POST /api/internal/st11-refresh     → beIN ST11 token refresh
  POST /api/internal/settle-once      → settled olmayan tahminleri tek seferlik settle
"""
import os
import logging
from fastapi import APIRouter, HTTPException, Request

from ..services.st11 import st11_manager
from ..services.settlement import settle_once as _settle_once

logger = logging.getLogger("banbansports.internal")
router = APIRouter(prefix="/api/internal", tags=["internal"])


def _check_cron_auth(request: Request) -> None:
    secret = os.environ.get("CRON_SECRET", "").strip()
    if not secret:
        # CRON_SECRET set edilmemişse endpoint çağrılamaz (güvenlik)
        raise HTTPException(status_code=503, detail="CRON_SECRET not configured")
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {secret}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.api_route("/refresh-all", methods=["GET", "POST"])
async def refresh_all_streams(request: Request):
    """Tüm kayıtlı stream manager'ları topluca refresh — Vercel Cron için ana endpoint."""
    _check_cron_auth(request)
    from ..services import stream_registry as reg
    results = await reg.refresh_all()
    return {"ok": True, "results": results}


@router.api_route("/ssport-refresh", methods=["GET", "POST"])
async def ssport_refresh(request: Request):
    _check_cron_auth(request)
    from ..services import stream_registry as reg
    mgr = reg.get("ssport")
    if not mgr:
        raise HTTPException(status_code=404, detail="ssport not registered")
    valid = await mgr.is_token_valid()
    refreshed = False
    if not valid:
        refreshed = await mgr.try_auto_refresh()
    return {"checked": True, "was_valid": valid, "refreshed": refreshed,
            "current_tms": mgr.current_tms or "(dynamic)",
            "token_preview": (mgr.current_token[:8] + "…") if mgr.current_token else ""}


@router.api_route("/st11-refresh", methods=["GET", "POST"])
async def st11_refresh(request: Request):
    _check_cron_auth(request)
    valid = await st11_manager.is_token_valid()
    refreshed = False
    if not valid:
        refreshed = await st11_manager.try_auto_refresh()
    return {
        "checked": True,
        "was_valid": valid,
        "refreshed": refreshed,
        "current_tms": st11_manager.current_tms,
    }


@router.api_route("/settle-once", methods=["GET", "POST"])
async def settle_once(request: Request):
    _check_cron_auth(request)
    try:
        result = await _settle_once()
        return {"ok": True, "settled_count": result if isinstance(result, int) else None}
    except Exception as e:
        logger.warning(f"settle-once: {e}")
        return {"ok": False, "error": str(e)[:200]}
