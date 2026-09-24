"""Channel listing — static catalogue + doğrudan HLS kanalları.

Her kanalın `logo` alanı opsiyonel — frontend logo path veya null kabul eder.
"""
from fastapi import APIRouter

from ..services.direct_channels import DIRECT_CHANNELS

router = APIRouter(prefix="/api", tags=["channels"])

BASE = {
    "tivibuspor": {"name": "TİVİBU SPOR",   "status": "online",      "logo": "/logos/channels/tivibuspor.png"},
    "trt1":       {"name": "TRT 1",         "status": "online",      "logo": "/logos/channels/trt1.png"},
    "trtspor":    {"name": "TRT SPOR",      "status": "maintenance", "logo": "/logos/channels/trtspor.png"},
    "trthaber":   {"name": "TRT HABER",     "status": "online",      "logo": "/logos/channels/trthaber.png"},
    "tv8":        {"name": "TV 8",          "status": "online",      "logo": "/logos/channels/tv8.png"},
    "bein1":      {"name": "beIN SPORTS 1", "status": "maintenance", "logo": "/logos/channels/bein1.png", "premium": True},
    "ssport":     {"name": "S SPORT",       "status": "online",      "logo": "/logos/channels/ssport.png", "premium": True},
    "atv":        {"name": "ATV",           "status": "online",      "logo": "/logos/channels/atv.png"},
}


@router.get("/channels")
async def get_channels():
    out = dict(BASE)
    for cid, (name, _urls) in DIRECT_CHANNELS.items():
        if cid not in out:
            out[cid] = {"name": name, "status": "online", "logo": None}
    return out
