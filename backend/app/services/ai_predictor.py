"""AI Match Prediction Service — Multi-model harmonization.

3 providers, direct SDK calls (no third-party wrapper library):
  • OpenAI       — GPT-5.2          (env: OPENAI_API_KEY)
  • Anthropic    — Claude Sonnet 4.5 (env: ANTHROPIC_API_KEY)
  • Google       — Gemini 3 Pro      (env: GEMINI_API_KEY)

Behaviour:
1. Run all 3 models in parallel with the same prompt.
2. Each model returns structured JSON (winner, score, key factors, analysis).
3. Harmonize via Claude (best reasoning) to produce a single consensus.
4. Cache results in MongoDB for 1 hour.

Missing keys → that model is skipped
remaining models still run.
All 3 missing → service returns `{available: False}` with a friendly error.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from ..core.database import get_db

logger = logging.getLogger("banbansports.ai")

# --- Provider keys ----------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY", "").strip()
    or os.environ.get("GOOGLE_API_KEY", "").strip()
)

# --- Model identifiers (kept generous to allow upgrades via env override) ----
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-pro-preview")

CACHE_TTL_SECONDS = 60 * 60  # 1 hour

SYSTEM_PROMPT = (
    "Sen banbansports için uzman bir futbol analistsin. Türkçe yanıt ver.\n"
    "Görevin: İki takım arasındaki maç için kısa, profesyonel ve VERİYE DAYALI "
    "bir tahmin üretmek.\n"
    "Çıktın MUTLAKA aşağıdaki JSON formatında olmalı, başka açıklama EKLEME:\n\n"
    "{\n"
    '  "winner": "home" | "away" | "draw",\n'
    '  "predicted_score": "X-Y",\n'
    '  "confidence": 0-100,\n'
    '  "key_factors": ["faktör 1 (max 60 karakter)", "faktör 2", "faktör 3"],\n'
    '  "analysis": "Kısa, akıcı paragraf (max 280 karakter, Türkçe)"\n'
    "}"
)


def _user_prompt(home: str, away: str, league: str = "", context: str = "") -> str:
    ctx = f"\nMaç bağlamı: {context}" if context else ""
    lg = f"\nLig: {league}" if league else ""
    return (
        f"Ev sahibi: {home}\nDeplasman: {away}{lg}{ctx}\n\n"
        f"Yukarıdaki maç için tahminini ver. SADECE JSON döndür."
    )


def _extract_json(text: str) -> Optional[dict]:
    """LLM bazen JSON'u markdown veya extra metinle sarar — robust extraction."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", m.group(0))
        try:
            return json.loads(cleaned)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Individual provider callers — each runs in its own thread (SDKs are sync)
# ---------------------------------------------------------------------------
def _call_openai_sync(prompt: str) -> Optional[str]:
    try:
        from openai import OpenAI
    except Exception as e:
        logger.warning(f"openai sdk import failed: {e}")
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=600,
        )
        return resp.choices[0].message.content or None
    except Exception as e:
        logger.warning(f"openai call failed: {e}")
        return None


def _call_anthropic_sync(prompt: str) -> Optional[str]:
    try:
        import anthropic
    except Exception as e:
        logger.warning(f"anthropic sdk import failed: {e}")
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=600,
            temperature=0.4,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        # content is a list of TextBlock
        if msg.content and len(msg.content) > 0:
            return getattr(msg.content[0], "text", None)
        return None
    except Exception as e:
        logger.warning(f"anthropic call failed: {e}")
        return None


def _call_gemini_sync(prompt: str) -> Optional[str]:
    try:
        import google.generativeai as genai
    except Exception as e:
        logger.warning(f"gemini sdk import failed: {e}")
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
        )
        resp = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 600,
                "response_mime_type": "application/json",
            },
        )
        return getattr(resp, "text", None)
    except Exception as e:
        logger.warning(f"gemini call failed: {e}")
        return None


async def _run_in_thread(fn, *args):
    """Run a sync SDK call in a thread without blocking the event loop."""
    return await asyncio.to_thread(fn, *args)


# ---------------------------------------------------------------------------
# Per-model predictors (return parsed dict or None)
# ---------------------------------------------------------------------------
async def _predict_openai(prompt: str) -> Optional[dict]:
    if not OPENAI_API_KEY:
        return None
    raw = await _run_in_thread(_call_openai_sync, prompt)
    parsed = _extract_json(raw or "")
    if parsed:
        parsed["_model"] = f"openai/{OPENAI_MODEL}"
    return parsed


async def _predict_anthropic(prompt: str) -> Optional[dict]:
    if not ANTHROPIC_API_KEY:
        return None
    raw = await _run_in_thread(_call_anthropic_sync, prompt)
    parsed = _extract_json(raw or "")
    if parsed:
        parsed["_model"] = f"anthropic/{ANTHROPIC_MODEL}"
    return parsed


async def _predict_gemini(prompt: str) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    raw = await _run_in_thread(_call_gemini_sync, prompt)
    parsed = _extract_json(raw or "")
    if parsed:
        parsed["_model"] = f"google/{GEMINI_MODEL}"
    return parsed


# ---------------------------------------------------------------------------
# Harmonizer — uses Claude (preferred) or fallbacks to the first available model
# ---------------------------------------------------------------------------
async def _harmonize(home: str, away: str, league: str,
                     predictions: list) -> Optional[dict]:
    if not predictions:
        return None
    if len(predictions) == 1:
        return predictions[0]

    summary = "\n\n".join([
        f"### Model {i+1} ({p.get('_model', '?')}):\n"
        f"- Kazanan: {p.get('winner', '?')}\n"
        f"- Skor: {p.get('predicted_score', '?')}\n"
        f"- Güven: {p.get('confidence', 0)}\n"
        f"- Faktörler: {p.get('key_factors', [])}\n"
        f"- Analiz: {p.get('analysis', '')}"
        for i, p in enumerate(predictions)
    ])
    synth_prompt = (
        f"{len(predictions)} farklı yapay zeka modeli {home} vs {away} "
        f"({league}) maçı için aşağıdaki tahminleri yaptı:\n\n{summary}\n\n"
        "Görevin: Bu modellerin tahminlerini HARMANLAYIP, en güçlü konsensüsü "
        "ortaya çıkaran TEK bir nihai tahmin üret. Modeller arası fikir "
        "ayrılığını belirt. SADECE JSON döndür (system prompt formatı), "
        "ekstra 'consensus' alanı ekle."
    )
    extra_sys = SYSTEM_PROMPT + "\nEkstra alan: \"consensus\": \"modeller arası uyum yorumu (max 200 karakter)\""

    # Prefer Claude as the harmonizer (best reasoning), then OpenAI, then Gemini
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            def _go():
                msg = client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=700,
                    temperature=0.3,
                    system=extra_sys,
                    messages=[{"role": "user", "content": synth_prompt}],
                )
                return getattr(msg.content[0], "text", "") if msg.content else ""
            raw = await _run_in_thread(_go)
            parsed = _extract_json(raw or "")
            if parsed:
                return parsed
        except Exception as e:
            logger.warning(f"harmonize via Claude failed: {e}")

    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)

            def _go():
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": extra_sys},
                        {"role": "user", "content": synth_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=700,
                )
                return resp.choices[0].message.content or ""
            raw = await _run_in_thread(_go)
            parsed = _extract_json(raw or "")
            if parsed:
                return parsed
        except Exception as e:
            logger.warning(f"harmonize via OpenAI failed: {e}")

    # Final fallback: just return the first prediction
    return predictions[0]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
async def _cache_get(key: str) -> Optional[dict]:
    db = get_db()
    if db is None:
        return None
    try:
        doc = await db.ai_predictions.find_one({"_id": key})
        if not doc:
            return None
        if (datetime.now(timezone.utc) - doc["cached_at"]).total_seconds() > CACHE_TTL_SECONDS:
            return None
        return doc.get("data")
    except Exception:
        return None


async def _cache_set(key: str, data: dict):
    db = get_db()
    if db is None or not data:
        return
    try:
        await db.ai_predictions.update_one(
            {"_id": key},
            {"$set": {"data": data, "cached_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"ai cache set fail: {e}")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def configured_providers() -> dict:
    """Useful for /api/ai/health — returns which providers have keys."""
    return {
        "openai": bool(OPENAI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
async def predict_match(home: str, away: str, league: str = "",
                        context: str = "", use_cache: bool = True) -> dict:
    """Run multi-model prediction with cache."""
    providers = configured_providers()
    if not any(providers.values()):
        return {
            "available": False,
            "error": "Hiçbir AI sağlayıcı yapılandırılmamış. "
                     ".env dosyasına OPENAI_API_KEY / ANTHROPIC_API_KEY / "
                     "GEMINI_API_KEY ekleyin.",
            "providers": providers,
        }

    cache_key = f"{_norm(home)}|{_norm(away)}|{_norm(league)}"
    if use_cache:
        cached = await _cache_get(cache_key)
        if cached:
            cached["_cached"] = True
            return cached

    prompt = _user_prompt(home, away, league, context)
    # Fan-out — only call configured providers
    tasks = []
    if providers["openai"]:
        tasks.append(_predict_openai(prompt))
    if providers["gemini"]:
        tasks.append(_predict_gemini(prompt))
    if providers["anthropic"]:
        tasks.append(_predict_anthropic(prompt))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    predictions = [r for r in results if isinstance(r, dict) and r.get("winner")]

    if not predictions:
        return {
            "available": False,
            "error": "Hiçbir model tahmin üretemedi. Lütfen tekrar deneyin.",
            "providers": providers,
        }

    harmonized = await _harmonize(home, away, league, predictions)

    output = {
        "available": True,
        "home": home,
        "away": away,
        "league": league,
        "models_used": [p["_model"] for p in predictions],
        "individual": [
            {k: v for k, v in p.items() if not k.startswith("_")}
            for p in predictions
        ],
        "harmonized": harmonized or predictions[0],
        "providers": providers,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _cache_set(cache_key, output)
    return output
