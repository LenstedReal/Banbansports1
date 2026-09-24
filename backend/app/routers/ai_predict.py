"""AI prediction endpoints — multi-model match analysis."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services.ai_predictor import predict_match

logger = logging.getLogger("banbansports.ai_router")
router = APIRouter(prefix="/api/ai", tags=["ai"])


class PredictionBody(BaseModel):
    home: str
    away: str
    league: Optional[str] = ""
    context: Optional[str] = ""
    no_cache: Optional[bool] = False


@router.post("/predict")
async def ai_predict(body: PredictionBody):
    if not body.home or not body.away:
        raise HTTPException(status_code=400, detail="home ve away takım isimleri gerekli")
    result = await predict_match(
        home=body.home.strip(),
        away=body.away.strip(),
        league=(body.league or "").strip(),
        context=(body.context or "").strip(),
        use_cache=not body.no_cache,
    )
    return result


@router.get("/predict")
async def ai_predict_get(home: str, away: str, league: str = "", context: str = ""):
    """GET variant for SSR / quick links."""
    if not home or not away:
        raise HTTPException(status_code=400, detail="home ve away parametreleri gerekli")
    return await predict_match(home=home.strip(), away=away.strip(),
                               league=league.strip(), context=context.strip())


@router.get("/health")
async def ai_health():
    from ..services.ai_predictor import configured_providers, OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL
    p = configured_providers()
    return {
        "configured": any(p.values()),
        "providers": p,
        "models": {
            "openai": OPENAI_MODEL,
            "anthropic": ANTHROPIC_MODEL,
            "gemini": GEMINI_MODEL,
        },
        "harmonizer": "anthropic (preferred) → openai → first-model fallback",
    }
