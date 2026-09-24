"""
Canlı Box Office + IMDb + TradingView FX + History — /api/boxoffice

Kaynaklar:
1. Box Office Mojo + curl_cffi -> Canlı Gişe & Ülke Verileri
2. IMDb Resmi Günlük Dataset -> Puan / Oy
3. TradingView Scanner API -> Birincil FX Kurları
4. Doviz.com / BtcTurk / Paribu -> İkincil USD/TRY Fallback
5. In-Memory + MongoDB Snapshot -> Önbellek & Yedekleme
6. /api/boxoffice/history -> Lightweight Charts zaman serisi
"""

import asyncio
import logging
import re
import zlib
from datetime import datetime, timezone
from time import time

import httpx
from fastapi import APIRouter

from ..core.database import get_db, init_db

logger = logging.getLogger("banbansports.boxoffice")
router = APIRouter(prefix="/api/boxoffice", tags=["boxoffice"])

# =========================================================
# CONFIG
# =========================================================

IMDB_ID = "tt22084616"
MOJO_URL = f"https://www.boxofficemojo.com/title/{IMDB_ID}/"
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"

TV_SCANNER_URL = "https://scanner.tradingview.com/forex/scan"

DOVIZ_URL = "https://www.doviz.com/api/v1/currencies/usd"
BTCTURK_URL = "https://api.btcturk.com/api/v2/ticker?pairSymbol=USDTTRY"
PARIBU_URL = "https://web.paribu.com/ticker"

CURRENCIES = ("TRY", "EUR", "GBP", "JPY")

US_AVG_TICKET = 10.50
INTL_AVG_TICKET = 6.50

# Türkiye gerçekçi bilet modeli: standart + premium (IMAX/4DX) ağırlıklı ortalama
TR_STD_TICKET = 200.0
TR_PREMIUM_TICKET = 300.0
TR_PREMIUM_RATIO = 0.40
TR_WEIGHTED_TICKET = (
    TR_STD_TICKET * (1 - TR_PREMIUM_RATIO)
    + TR_PREMIUM_TICKET * TR_PREMIUM_RATIO
)  # 240.0 TL

# Yerel para cinsinden bilet fiyatları — seyirci = yerel hasılat / yerel bilet
LOCAL_TICKET_NATIVE = {
    "USD": US_AVG_TICKET,
    "TRY": TR_WEIGHTED_TICKET,
    "EUR": 11.50,
    "GBP": 10.00,
    "JPY": 2000.0,
}

LOCAL_LABEL = {
    "USD": "ABD / KANADA",
    "TRY": "TÜRKİYE",
    "EUR": "EURO BÖLGESİ",
    "GBP": "BİRLEŞİK KRALLIK",
    "JPY": "JAPONYA",
}

RELEASE_DATE = datetime(2026, 7, 31, tzinfo=timezone.utc)

TITLE = "Örümcek-Adam: Yepyeni Bir Gün"
TITLE_EN = "Spider-Man: Brand New Day"

PLOT_TR = (
    "Doktor Strange'in büyüsü tüm dünyaya Peter Parker'ı unutturalı dört yıl oldu. "
    "Kendisini artık kimsenin hatırlamadığı bu düzende Peter, sevdiklerini korumak için "
    "gölgede kalmayı seçer ve New York'u tam zamanlı olarak koruyan isimsiz kahraman "
    "Örümcek-Adam'a dönüşür. MIT'den mezun olup şehre dönen MJ ve Ned, eski hayatlarına "
    "onsuz devam etmektedir — MJ'in yeni bir sevgilisi bile vardır. Yalnızlığın, yasın ve "
    "aralıksız kahramanlığın yarattığı baskı, Peter'ın güçlerinde kontrol edemediği tekinsiz "
    "bir evrimi tetikler: duyuları keskinleşir, gözleri zaman zaman simsiyah kesilir ve "
    "bileklerinden organik ağlar fışkırmaya başlar. Tam bu sırada şehir; zihinden zihne "
    "atlayabilen, kimsenin göremediği telepatik bir düşmanın hedefi olur. Punisher'ın acımasız "
    "yöntemleri, Yelena Belova'nın istihbaratı ve Bruce Banner'ın bilimi arasında sıkışan "
    "Peter, hem içindeki karanlıkla hem de görünmez tehditle aynı anda yüzleşmek zorundadır — "
    "çünkü bu ürkütücü dönüşüm, sevdiklerini kurtarabilecek tek silahı da olabilir."
)

CREDITS_TR = (
    "Yönetmen: Destin Daniel Cretton · Tom Holland, Zendaya, Sadie Sink, "
    "Jon Bernthal, Florence Pugh, Mark Ruffalo · 145 dk · MCU 6. Faz"
)

IMDB_TTL = 12 * 3600
FX_TTL = 6 * 3600
HISTORY_TTL = 15 * 60

# USD -> para birimi çevirim seed'leri
FX_SEED = {
    "TRY": 36.20,
    "EUR": 0.92,
    "GBP": 0.78,
    "JPY": 155.0,
}

EUROZONE = (
    "Germany", "France", "Italy", "Spain", "Netherlands",
    "Belgium", "Austria", "Portugal", "Ireland", "Finland",
    "Greece", "Slovakia", "Slovenia", "Croatia", "Lithuania",
    "Latvia", "Estonia", "Luxembourg", "Cyprus", "Malta",
)

# =========================================================
# STATE
# =========================================================

_state = {
    "gross": None,
    "countries": None,
    "fetched_at": 0.0,

    "imdb": None,
    "imdb_at": 0.0,

    "fx": None,
    "fx_at": 0.0,
    "fx_source": "seed",

    "observed_rate": 0.0,
    "observed_at": 0.0,

    "history_at": 0.0,

    "refresh_sec": 900,
    "loaded_from_db": False,
}

_lock = asyncio.Lock()

_MONEY_RE = re.compile(r'class="money">\$?([\d,]+)<')

_ROW_RE = re.compile(
    r'<tr><td><a class="a-link-normal" href="/release/[^"]*">'
    r'([^<]+)</a></td>'
    r'<td>[^<]*</td>'
    r'<td[^>]*><span class="money">\$?[\d,]+</span></td>'
    r'<td[^>]*><span class="money">\$?([\d,]+)</span></td></tr>'
)

# =========================================================
# DATABASE
# =========================================================

async def _db():
    db = get_db()
    if db is None:
        try:
            db = await init_db()
        except Exception:
            db = None
    return db


# =========================================================
# BOX OFFICE MOJO
# =========================================================

def _mojo_fetch_sync() -> dict:
    from curl_cffi import requests as creq

    r = creq.get(
        MOJO_URL,
        impersonate="chrome131",
        timeout=25,
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    r.raise_for_status()
    html = r.text

    idx = html.find("mojo-performance-summary-table")
    section = html[idx:idx + 4000] if idx >= 0 else html

    values = [
        int(v.replace(",", ""))
        for v in _MONEY_RE.findall(section)[:3]
    ]

    if len(values) < 3:
        raise ValueError("Box Office tablosu bulunamadı")

    domestic, international, worldwide = values

    if not (
        worldwide >= domestic
        and worldwide >= international
        and abs((domestic + international) - worldwide)
        <= max(0.03 * worldwide, 5_000_000)
    ):
        raise ValueError(f"Gişe verisi tutarsız: {values}")

    countries = {
        name.strip(): int(value.replace(",", ""))
        for name, value in _ROW_RE.findall(html)
    }

    return {
        "domestic": domestic,
        "international": international,
        "worldwide": worldwide,
        "countries": countries,
    }


# =========================================================
# IMDB
# =========================================================

async def _fetch_imdb():
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    buffer = b""
    needle = f"{IMDB_ID}\t".encode()

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("GET", IMDB_RATINGS_URL) as response:
            response.raise_for_status()

            async for chunk in response.aiter_bytes(131072):
                buffer += decoder.decompress(chunk)

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)

                    if line.startswith(needle):
                        parts = line.decode().split("\t")
                        return {
                            "rating": float(parts[1]),
                            "votes": int(parts[2]),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }

    return None


# =========================================================
# FX (TRADINGVIEW + TR FALLBACK)
# =========================================================

async def _fetch_tradingview():
    symbols = [
        "FX_IDC:USDTRY",
        "FX_IDC:EURUSD",
        "FX_IDC:GBPUSD",
        "FX_IDC:USDJPY",
    ]

    payload = {
        "symbols": {
            "tickers": symbols,
            "query": {"types": []},
        },
        "columns": ["close"],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(TV_SCANNER_URL, json=payload)
        response.raise_for_status()

        rows = response.json().get("data", [])
        if not isinstance(rows, list):
            raise ValueError("TradingView geçersiz cevap verdi")

        values = {}
        for row in rows:
            symbol = row.get("s", "")
            data = row.get("d", [])
            if not data or data[0] is None:
                continue
            values[symbol] = float(data[0])

        usdtry = values.get("FX_IDC:USDTRY")
        eurusd = values.get("FX_IDC:EURUSD")
        gbpusd = values.get("FX_IDC:GBPUSD")
        usdjpy = values.get("FX_IDC:USDJPY")

        if not all(x and x > 0 for x in (usdtry, eurusd, gbpusd, usdjpy)):
            raise ValueError("TradingView eksik FX verisi")

        # DÜZELTME: EURUSD/GBPUSD "1 EUR/GBP kaç USD" verir.
        # Sistemin ihtiyacı USD -> para birimi olduğu için tersi alınır.
        return {
            "TRY": usdtry,
            "EUR": round(1.0 / eurusd, 6),
            "GBP": round(1.0 / gbpusd, 6),
            "JPY": usdjpy,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


async def _fetch_tr_usdtry():
    async with httpx.AsyncClient(timeout=10) as client:
        # 1. Doviz.com
        try:
            response = await client.get(DOVIZ_URL)
            data = response.json()
            value = data.get("selling") or data.get("buying") or data.get("price")
            if value and float(value) > 0:
                return float(value), "doviz_com"
        except Exception as e:
            logger.warning(f"Doviz.com FX: {e}")

        # 2. BtcTurk USDT/TRY
        try:
            response = await client.get(BTCTURK_URL)
            data = response.json().get("data") or response.json()
            if isinstance(data, list):
                data = data[0]
            value = data.get("last") or data.get("ask") or data.get("bid")
            if value and float(value) > 0:
                return float(value), "crypto_proxy"
        except Exception as e:
            logger.warning(f"BtcTurk FX: {e}")

        # 3. Paribu
        try:
            response = await client.get(PARIBU_URL)
            data = response.json()
            ticker = data.get("USDT_TL") or data.get("USDTTRY")
            if isinstance(ticker, dict):
                value = ticker.get("last") or ticker.get("lowestAsk") or ticker.get("highestBid")
                if value and float(value) > 0:
                    return float(value), "crypto_proxy"
        except Exception as e:
            logger.warning(f"Paribu FX: {e}")

    return None, None


async def _fetch_fx():
    # 1. TradingView Scanner API
    try:
        tv_data = await _fetch_tradingview()
        return tv_data, "tradingview"
    except Exception as e:
        logger.warning(f"TradingView FX hatası: {e}")

    # 2. Türkiye Yerel USD/TRY Fallback
    tr_try, source = await _fetch_tr_usdtry()
    if tr_try:
        old_fx = _state.get("fx") or {}
        return {
            "TRY": tr_try,
            "EUR": old_fx.get("EUR", FX_SEED["EUR"]),
            "GBP": old_fx.get("GBP", FX_SEED["GBP"]),
            "JPY": old_fx.get("JPY", FX_SEED["JPY"]),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, source

    # 3. Bellek / Mongo snapshot
    if _state.get("fx"):
        return _state["fx"], "mongo_cache"

    # 4. Static Seed
    return dict(FX_SEED, updated_at=None), "static_seed"


# =========================================================
# RATE / REFRESH
# =========================================================

def _heuristic_rate(worldwide: int) -> float:
    days = max(
        1.0,
        (datetime.now(timezone.utc) - RELEASE_DATE).total_seconds() / 86400,
    )
    return max(1.0, (worldwide / days) * 0.5 / 86400)


def _current_rate() -> float:
    gross = _state["gross"]
    if not gross:
        return 0.0
    if _state["observed_rate"] > 0 and (time() - _state["observed_at"]) < 48 * 3600:
        return _state["observed_rate"]
    return round(_heuristic_rate(gross["worldwide"]), 4)


def _pick_refresh(rate: float) -> int:
    if rate >= 40:
        return 900
    if rate >= 15:
        return 1200
    return 1800


# =========================================================
# COUNTRY HELPERS
# =========================================================

def _find_country(countries: dict, *names) -> int:
    normalized = {
        str(key).strip().lower(): value
        for key, value in countries.items()
    }
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return value
    return 0


# =========================================================
# LOCAL MARKET
# =========================================================

def _build_local(rate: float) -> dict:
    gross = _state["gross"]
    countries = _state["countries"] or {}
    fx = _state["fx"] or FX_SEED

    worldwide = gross["worldwide"] or 1

    turkey_gross = _find_country(countries, "Türkiye", "Turkey")
    turkey_estimated = False

    if turkey_gross <= 0:
        turkey_gross = int(gross["international"] * 0.0115)
        turkey_estimated = True

    regions = {
        "USD": gross["domestic"],
        "TRY": turkey_gross,
        "EUR": sum(_find_country(countries, country) for country in EUROZONE),
        "GBP": _find_country(countries, "United Kingdom"),
        "JPY": _find_country(countries, "Japan"),
    }

    result = {}

    for code, gross_usd in regions.items():
        share = gross_usd / worldwide
        fx_rate = 1.0 if code == "USD" else float(fx.get(code) or FX_SEED.get(code, 1.0))
        ticket = LOCAL_TICKET_NATIVE[code]

        # Seyirci = yerel para hasılat / yerel para bilet fiyatı (154TL saçmalığı düzeltildi)
        gross_native = gross_usd * fx_rate
        rate_usd = rate * share
        rate_native = rate_usd * fx_rate

        viewers = int(gross_native / ticket) if ticket > 0 else 0
        viewers_per_sec = round(rate_native / ticket, 5) if ticket > 0 else 0

        result[code] = {
            "label": LOCAL_LABEL[code],
            "gross_usd": gross_usd,
            "gross_native": round(gross_native, 2),
            "fx_rate": fx_rate,
            "rate_per_sec_usd": round(rate_usd, 4),
            "rate_per_sec_native": round(rate_native, 4),
            "viewers": viewers,
            "viewers_per_sec": viewers_per_sec,
            "ticket_price_used_native": ticket,
        }

    result["TRY"]["is_estimated"] = turkey_estimated
    result["TRY"]["data_source"] = (
        "mojo_actual" if not turkey_estimated else "estimated_share"
    )

    return result


# =========================================================
# HISTORY SNAPSHOT
# =========================================================

async def _save_history():
    now_ts = time()
    if (now_ts - _state["history_at"]) < HISTORY_TTL:
        return

    db = await _db()
    if db is None or not _state["gross"]:
        return

    now = datetime.now(timezone.utc)
    gross = _state["gross"]
    rate = _current_rate()

    try:
        document = {
            "movie_id": IMDB_ID,
            "ts": now.isoformat(),
            "timestamp": now.timestamp(),
            "worldwide": gross["worldwide"],
            "domestic": gross["domestic"],
            "international": gross["international"],
            "rate_per_sec": rate,
            "viewers": int(
                gross["domestic"] / US_AVG_TICKET
                + gross["international"] / INTL_AVG_TICKET
            ),
            "imdb_rating": (
                _state["imdb"]["rating"] if _state["imdb"] else None
            ),
            "fx": _state["fx"],
        }

        await db.boxoffice_history.update_one(
            {
                "movie_id": IMDB_ID,
                "timestamp": document["timestamp"],
            },
            {"$set": document},
            upsert=True,
        )
        _state["history_at"] = now_ts
    except Exception as e:
        logger.warning(f"History yazılamadı: {e}")


# =========================================================
# SNAPSHOT
# =========================================================

async def _save_snapshot():
    db = await _db()
    if db is None:
        return

    try:
        document = {
            "id": IMDB_ID,
            "gross": _state["gross"],
            "countries": _state["countries"],
            "fetched_at": _state["fetched_at"],
            "imdb": _state["imdb"],
            "imdb_at": _state["imdb_at"],
            "fx": _state["fx"],
            "fx_at": _state["fx_at"],
            "fx_source": _state["fx_source"],
            "observed_rate": _state["observed_rate"],
            "observed_at": _state["observed_at"],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.boxoffice_cache.update_one(
            {"id": IMDB_ID},
            {"$set": document},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Snapshot yazılamadı: {e}")


async def _load_snapshot():
    if _state["loaded_from_db"]:
        return

    _state["loaded_from_db"] = True
    db = await _db()
    if db is None:
        return

    try:
        document = await db.boxoffice_cache.find_one(
            {"id": IMDB_ID},
            {"_id": 0},
        )

        if document and document.get("gross"):
            for key in (
                "gross",
                "countries",
                "fetched_at",
                "imdb",
                "imdb_at",
                "fx",
                "fx_at",
                "fx_source",
                "observed_rate",
                "observed_at",
            ):
                if document.get(key) is not None:
                    _state[key] = document[key]

            logger.info("boxoffice: Mongo snapshot yüklendi")
    except Exception as e:
        logger.warning(f"Snapshot okunamadı: {e}")


# =========================================================
# REFRESH
# =========================================================

async def _refresh(force=False):
    async with _lock:
        now = time()
        stale = (now - _state["fetched_at"]) >= _state["refresh_sec"]

        if _state["gross"] and _state["countries"] and not stale and not force:
            return

        # BOX OFFICE
        try:
            gross = await asyncio.to_thread(_mojo_fetch_sync)
            countries = gross.pop("countries", {})

            if countries:
                _state["countries"] = countries

            previous = _state["gross"]
            previous_at = _state["fetched_at"]

            if previous and gross["worldwide"] > previous["worldwide"] and now > previous_at:
                observed = (gross["worldwide"] - previous["worldwide"]) / (now - previous_at)
                if 0 < observed < 5000:
                    _state["observed_rate"] = round(observed, 4)
                    _state["observed_at"] = now

            _state["gross"] = gross
            _state["fetched_at"] = now
            _state["refresh_sec"] = _pick_refresh(_current_rate())
        except Exception as e:
            logger.warning(f"Mojo scrape hatası: {e}")

        # IMDb
        if (now - _state["imdb_at"]) >= IMDB_TTL or not _state["imdb"]:
            try:
                imdb = await _fetch_imdb()
                if imdb:
                    _state["imdb"] = imdb
                    _state["imdb_at"] = now
            except Exception as e:
                logger.warning(f"IMDb dataset hatası: {e}")

        # FX
        if (now - _state["fx_at"]) >= FX_TTL or not _state["fx"]:
            fx, source = await _fetch_fx()
            if fx:
                _state["fx"] = fx
                _state["fx_at"] = now
                _state["fx_source"] = source

        await _save_snapshot()
        await _save_history()


# =========================================================
# BACKGROUND LOOP
# =========================================================

async def refresh_loop():
    await _load_snapshot()

    while True:
        try:
            await _refresh()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Refresh loop hatası: {e}")

        await asyncio.sleep(min(_state["refresh_sec"], 900))


# =========================================================
# LIVE API
# =========================================================

@router.get("")
async def get_boxoffice():
    await _load_snapshot()
    now = time()

    if (
        not _state["gross"]
        or not _state["countries"]
        or (now - _state["fetched_at"]) >= _state["refresh_sec"]
    ):
        try:
            await asyncio.wait_for(_refresh(), timeout=45)
        except Exception as e:
            logger.warning(f"Lazy refresh: {e}")

    gross = _state["gross"]
    if not gross:
        return {
            "ok": False,
            "detail": "veri henüz alınamadı — tekrar denenecek",
        }

    rate = _current_rate()

    domestic_share = (
        gross["domestic"] / gross["worldwide"]
        if gross["worldwide"]
        else 0.3
    )
    international_share = 1 - domestic_share

    viewers_domestic = int(gross["domestic"] / US_AVG_TICKET)
    viewers_international = int(gross["international"] / INTL_AVG_TICKET)
    viewers_rate = rate * (
        domestic_share / US_AVG_TICKET
        + international_share / INTL_AVG_TICKET
    )

    fx = _state["fx"] or FX_SEED
    age = max(0.0, now - _state["fetched_at"])

    return {
        "ok": True,
        "movie": {
            "id": IMDB_ID,
            "title": TITLE,
            "title_en": TITLE_EN,
            "release_date": "2026-07-31",
        },
        "gross_usd": gross,
        "rate_per_sec_usd": rate,
        "viewers": {
            "domestic": viewers_domestic,
            "international": viewers_international,
            "total": (viewers_domestic + viewers_international),
            "per_sec": round(viewers_rate, 5),
        },
        "local": _build_local(rate),
        "imdb": _state["imdb"],
        "fx": {
            "USD": 1.0,
            **{code: fx.get(code) for code in CURRENCIES},
            "updated_at": fx.get("updated_at"),
        },
        "fx_metadata": {
            "active_source": _state["fx_source"],
        },
        "pricing_info": {
            "tr_std_ticket_try": TR_STD_TICKET,
            "tr_premium_ticket_try": TR_PREMIUM_TICKET,
            "tr_premium_ratio": TR_PREMIUM_RATIO,
            "tr_weighted_average_used": TR_WEIGHTED_TICKET,
        },
        "plot": PLOT_TR,
        "credits": CREDITS_TR,
        "fetched_at": datetime.fromtimestamp(
            _state["fetched_at"], timezone.utc
        ).isoformat(),
        "age_sec": round(age, 1),
        "refresh_sec": _state["refresh_sec"],
        "source": "live" if age < _state["refresh_sec"] * 2 else "cache",
    }


# =========================================================
# HISTORY API
# =========================================================

@router.get("/history")
async def get_boxoffice_history(hours: int = 168, limit: int = 2000):
    """Lightweight Charts tarzı zaman serisi. hours=geriye dönük saat, limit=maks nokta."""
    db = await _db()

    if db is None:
        return {"ok": False, "history": [], "detail": "history database unavailable"}

    hours = max(1, min(hours, 24 * 365))
    limit = max(1, min(limit, 10000))

    since = datetime.now(timezone.utc).timestamp() - (hours * 3600)

    try:
        cursor = (
            db.boxoffice_history
            .find(
                {"movie_id": IMDB_ID, "timestamp": {"$gte": since}},
                {"_id": 0},
            )
            .sort("timestamp", 1)
            .limit(limit)
        )

        history = await cursor.to_list(length=limit)

        return {
            "ok": True,
            "movie_id": IMDB_ID,
            "interval_hours": hours,
            "count": len(history),
            "history": history,
        }

    except Exception as e:
        logger.warning(f"history okunamadı: {e}")
        return {"ok": False, "history": [], "detail": "history okunamadı"}
