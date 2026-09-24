"""Live scores aggregator — multi-source (LiveScore, FotMob, SofaScore) + MongoDB cache."""
import logging
import re
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    TR_TZ = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover - Python <3.9 fallback
    TR_TZ = timezone(timedelta(hours=3))

from ..core.config import LIVESCORE_CACHE_TTL, LIVESCORE_FETCH_TIMEOUT, MATCH_FT_FRESH_WINDOW, MATCH_FULL_DURATION
from ..core.database import get_db
from ..core.team_translations import tr_team_name

logger = logging.getLogger("banbansports.livescore")

LIVESCORE_BASE = "https://prod-public-api.livescore.com/v1/api/app/date/soccer"
LIVESCORE_HEADERS = {"User-Agent": "Mozilla/5.0"}
FOTMOB_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SOFASCORE_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

LIVESCORE_STATUS_MAP = {
    "NS": "BAŞLAMADI", "1H": "1. YARI", "HT": "DEVRE ARASI", "2H": "2. YARI",
    "ET": "UZATMA", "PEN": "PENALTILAR", "FT": "MAÇ SONU", "AET": "UZATMA SONU",
    "AP": "PENALTI SONU", "Pen.": "PENALTI SONU", "CANC": "İPTAL",
    "POSTP": "ERTELENDİ", "SUSP": "ASKIDA", "INT": "DURDURULDU",
}

BIG_CLUB_REGEX_S = re.compile(r'\b(galatasaray|fenerbah[cç]e|be[sş]ikta[sş]|trabzonspor)\b', re.IGNORECASE)

EXCLUDE_KEYWORDS = ["u18", "u19", "u20", "u21", "u23", "youth", "reserve", "women",
                    "primavera", "qualification: round", "u15", "u16", "u17",
                    "amateur", "regionalliga", "oberliga", "veterans",
                    "championship play-off", "championship group",
                    "primera division b", "segunda federacion",
                    "laliga 2", "laliga2", "la liga 2",
                    "bundesliga 2", "2. bundesliga",
                    "serie b", "serie c", "ligue 2",
                    "premier league 2", "premier division",
                    "championship", "league two", "league one"]
BIG_COUNTRIES = ["england", "spain", "germany", "italy", "france", "turkiye",
                 "turkey", "türkiye", "europe", "europe / europa", "international",
                 "world", "world cup", "fifa"]
# NOTE: International / World Cup matches override country exclusions.
# Filter is only used for *club* leagues from low-profile confederations.
EXCLUDED_COUNTRIES = ["afc club", "caf club", "concacaf club"]

# UEFA-dışı konfederasyonların KULÜP kupaları — 'champions league' kelimesi geçse de
# uluslararası (UEFA) turnuva DEĞİLDİR; tanınmayan-lig yoluna düşerler.
NON_UEFA_CONFED_CUPS = [
    "ofc champions", "caf champions", "afc champions", "concacaf champions",
    "caf confederation", "afc cup", "ofc ", "oceania",
]

# Keywords that mark an "international" tournament (overrides country exclusion).
INTL_KEYWORDS = [
    "world cup", "world cup qualif", "world cup qualifying",
    "champions league", "europa league", "conference league",
    "uefa nations", "nations league", "uefa euro",
    "euro 2028", "european championship", "euro qualif",
    "copa america", "copa libertadores", "copa sudamericana",
    "friendly", "international friendly", "club friendly",
    "summer series", "pre-season", "preseason",
    "afcon", "africa cup of nations", "asian cup", "gold cup",
    "milli", "national team", "intercontinental",
]

BIG_LEAGUE_KEYWORDS = [
    ("uefa champions league", "UEFA ŞAMPİYONLAR LİGİ", 200),
    ("champions league",      "UEFA ŞAMPİYONLAR LİGİ", 195),
    ("uefa europa league",    "UEFA AVRUPA LİGİ",       180),
    ("europa league",         "UEFA AVRUPA LİGİ",       175),
    ("conference league",     "UEFA KONFERANS LİGİ",    165),
    ("süper lig",             "TRENDYOL SÜPER LİG",     220),
    ("super lig",             "TRENDYOL SÜPER LİG",     220),
    ("premier league",        "PREMİER LİG",            150),
    ("la liga",               "LA LİGA",                145),
    ("laliga",                "LA LİGA",                145),
    ("bundesliga",            "BUNDESLIGA",             140),
    ("serie a",               "SERİE A",                138),
    ("ligue 1",               "LIGUE 1",                130),
    ("world cup qualif",      "DÜNYA KUPASI ELEMELERİ", 245),
    ("world cup",             "DÜNYA KUPASI",           260),
    ("euro qualif",           "EURO ELEMELERİ",         235),
    ("euro 2028",             "AVRUPA ŞAMPİYONASI",     240),
    ("european championship", "AVRUPA ŞAMPİYONASI",     240),
    ("uefa nations",          "ULUSLAR LİGİ",           175),
    ("nations league",        "ULUSLAR LİGİ",           175),
    ("copa america",          "COPA AMERİCA",           170),
    ("international friendly","ULUSLAR ARASI HAZIRLIK", 150),
    ("summer series",         "PREMİER LİG YAZ SERİSİ", 120),
    ("pre-season",            "SEZON ÖNCESİ HAZIRLIK",  115),
    ("preseason",             "SEZON ÖNCESİ HAZIRLIK",  115),
    ("club friendly",         "KULÜP HAZIRLIK MAÇI",    110),
    ("friendly",              "HAZIRLIK MAÇI",          115),
    ("afcon",                 "AFRİKA KUPASI",          155),
    ("africa cup",            "AFRİKA KUPASI",          155),
    ("asian cup",             "ASYA KUPASI",            150),
]


def _normalize_tr(s: str) -> str:
    if not s:
        return ""
    return (s.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g")
            .replace("ü", "u").replace("ö", "o").replace("ç", "c"))


def _livescore_status(ev: dict) -> Tuple[str, bool]:
    eps = ev.get("Eps") or ""
    is_live = eps in ("1H", "2H", "HT", "ET", "PEN")
    if eps in ("1H", "2H"):
        minute = ev.get("Eo") or ev.get("Mn") or ev.get("Esm")
        if minute:
            return f"{minute}'", True
        return ("1. YARI" if eps == "1H" else "2. YARI"), True
    return LIVESCORE_STATUS_MAP.get(eps, eps or "CANLI"), is_live


def _livescore_event_to_score(ev: dict, league_name: str) -> dict:
    eps = ev.get("Eps") or ""
    t1_raw = ((ev.get("T1") or [{}])[0].get("Nm")) or "—"
    t2_raw = ((ev.get("T2") or [{}])[0].get("Nm")) or "—"
    t1 = tr_team_name(t1_raw)
    t2 = tr_team_name(t2_raw)
    status, is_live = _livescore_status(ev)
    is_ns = eps in ("NS", "Not Started")
    return {
        "type": "score_update",
        "team1": t1, "team2": t2,
        "team1_en": t1_raw, "team2_en": t2_raw,
        "score1": None if is_ns else int(ev.get("Tr1") or 0),
        "score2": None if is_ns else int(ev.get("Tr2") or 0),
        "league": league_name,
        "status": status,
        "isLive": is_live,
        "pen1": ev.get("Trp1"),
        "pen2": ev.get("Trp2"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# === MongoDB-backed cache ===
async def _cache_get(key: str) -> Optional[dict]:
    db = get_db()
    if db is None:
        return None
    try:
        doc = await db.livescore_cache.find_one({"_id": key})
        if not doc:
            return None
        if (datetime.now(timezone.utc) - doc["cached_at"]).total_seconds() > LIVESCORE_CACHE_TTL:
            return None
        return doc.get("data")
    except Exception as e:
        logger.debug(f"cache_get fail: {e}")
        return None


async def _cache_set(key: str, data: dict):
    db = get_db()
    if db is None or not data:
        return
    try:
        await db.livescore_cache.update_one(
            {"_id": key}, {"$set": {"data": data, "cached_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"cache_set fail: {e}")


async def _fetch_livescore_raw(http: httpx.AsyncClient, date_str: str) -> Optional[dict]:
    try:
        # tz=0 → upstream returns Esd in UTC; we convert to Istanbul at render time.
        # (The repo previously used "-3" which means UTC-3 and caused a 3h-shifted Esd.)
        r = await http.get(f"{LIVESCORE_BASE}/{date_str}/0?MD=1", headers=LIVESCORE_HEADERS)
        if r.status_code == 200:
            d = r.json()
            if d.get("Stages"):
                return d
    except Exception as e:
        logger.debug(f"LiveScore fail {date_str}: {e}")
    return None


async def _fetch_fotmob_as_livescore(http: httpx.AsyncClient, date_str: str) -> Optional[dict]:
    try:
        from .fotmob_client import fotmob_get
        d, _st = await fotmob_get(http, f"/api/data/matches?date={date_str}", expect_key="leagues")
        if not d:
            return None
        stages = []
        for league in (d.get("leagues") or []):
            cn = league.get("ccode") or league.get("primaryId") or ""
            sn = league.get("name") or ""
            events = []
            for m in (league.get("matches") or []):
                home, away = m.get("home", {}), m.get("away", {})
                status = m.get("status", {})
                eps = "NS"
                if status.get("finished"):
                    eps = "FT"
                elif status.get("started") or status.get("ongoing"):
                    eps = str(status.get("liveTime", {}).get("short", "1H"))
                events.append({
                    "Eid": m.get("id"),
                    "T1": [{"Nm": home.get("name") or home.get("longName") or ""}],
                    "T2": [{"Nm": away.get("name") or away.get("longName") or ""}],
                    "Tr1": home.get("score") or 0, "Tr2": away.get("score") or 0,
                    "Eps": eps,
                    "Esd": m.get("utcTime") or m.get("status", {}).get("utcTime"),
                })
            if events:
                stages.append({"Cnm": cn, "Snm": sn, "Events": events})
        return {"Stages": stages, "_source": "fotmob"} if stages else None
    except Exception as e:
        logger.debug(f"FotMob fail {date_str}: {e}")
        return None


async def _fetch_sofascore_as_livescore(http: httpx.AsyncClient, date_str: str) -> Optional[dict]:
    try:
        iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        r = await http.get(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{iso}", headers=SOFASCORE_HEADERS)
        if r.status_code != 200:
            return None
        d = r.json()
        by_tournament: dict = {}
        for ev in (d.get("events") or []):
            t = ev.get("tournament") or {}
            cat = t.get("category") or {}
            key = (cat.get("name") or "", t.get("name") or "")
            home, away = ev.get("homeTeam", {}), ev.get("awayTeam", {})
            code = (ev.get("status") or {}).get("code", 0)
            # Sofascore status code mapping — eksik kodlar 'NS' default'una düşüyordu
            # (Bug #6 fix: kod 4/5/8/10/11/32/33/70/110 eksikti)
            if code == 100:
                eps = "FT"
            elif code == 60:
                eps = "FT"
            elif code == 110:
                eps = "AET"
            elif code == 120:  # after penalties
                eps = "AP"
            elif code == 31:
                eps = "HT"
            elif code == 32:  # interrupted
                eps = "INT"
            elif code == 33:  # cancelled
                eps = "CANC"
            elif code == 34:  # suspended
                eps = "SUSP"
            elif code == 6:
                eps = "1H"
            elif code == 7:
                eps = "2H"
            elif code in (10, 11):  # extra time / pen.
                eps = "ET"
            elif code == 70:
                eps = "CANC"
            elif code in (4, 5):  # just started
                eps = "1H"
            elif code == 8:  # just ended
                eps = "FT"
            elif code == 13:  # postponed
                eps = "POSTP"
            elif code == 23:
                eps = "POSTP"
            else:
                eps = "NS"
            by_tournament.setdefault(key, []).append({
                "Eid": ev.get("id"),
                "T1": [{"Nm": home.get("name") or ""}], "T2": [{"Nm": away.get("name") or ""}],
                "Tr1": (ev.get("homeScore") or {}).get("current", 0),
                "Tr2": (ev.get("awayScore") or {}).get("current", 0),
                "Eps": eps, "Esd": ev.get("startTimestamp"),
            })
        stages = [{"Cnm": k[0], "Snm": k[1], "Events": v} for k, v in by_tournament.items()]
        return {"Stages": stages, "_source": "sofascore"} if stages else None
    except Exception as e:
        logger.debug(f"Sofascore fail {date_str}: {e}")
        return None


async def livescore_fetch_day(http: httpx.AsyncClient, date_str: str) -> Optional[dict]:
    cached = await _cache_get(f"day:{date_str}")
    if cached:
        return cached
    for fetcher in (_fetch_livescore_raw, _fetch_fotmob_as_livescore, _fetch_sofascore_as_livescore):
        data = await fetcher(http, date_str)
        if data:
            await _cache_set(f"day:{date_str}", data)
            return data
    return None


def _too_old_ft(ev: dict, today_str: str) -> bool:
    if (ev.get("Eps") or "") not in ("FT", "AET", "AP", "Pen."):
        return False
    now = datetime.now(timezone.utc)
    ewt = ev.get("Ewt")
    if isinstance(ewt, int):
        try:
            ts = ewt / 1000 if ewt > 10**12 else ewt
            end_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return (now - end_dt).total_seconds() > MATCH_FT_FRESH_WINDOW
        except Exception:
            pass
    esd = ev.get("Esd")
    if esd and isinstance(esd, int):
        try:
            s = str(esd)
            year, month, day = int(s[:4]), int(s[4:6]), int(s[6:8])
            hour = int(s[8:10]) if len(s) >= 10 else 0
            minute = int(s[10:12]) if len(s) >= 12 else 0
            start_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            return (now - start_dt).total_seconds() > MATCH_FULL_DURATION
        except Exception:
            pass
    return False


async def fetch_live_scores(top_n: int = 1) -> Optional[dict]:
    """Top N important matches (live first, then upcoming, then recently FT)."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(TR_TZ).strftime("%Y%m%d")

    async with httpx.AsyncClient(timeout=LIVESCORE_FETCH_TIMEOUT) as http:

        async def collect(d_str: str, day_offset: int) -> list:
            data = await livescore_fetch_day(http, d_str)
            if not data:
                return []
            out = []
            for stage in (data.get("Stages") or []):
                cn = (stage.get("Cnm") or "").lower()
                sn = (stage.get("Snm") or "").lower()
                combined = cn + " " + sn
                if any(x in combined for x in EXCLUDE_KEYWORDS):
                    continue
                sn_root = sn.split(":")[0].strip()
                is_tr_stage = "turkiye" in cn or "türk" in cn or "turkey" in cn
                # International tournaments override country-based exclusion.
                # Detect by stage NAME (Snm) primarily — World Cup hosted in Morocco
                # still shows "World Cup" in Snm.
                is_intl = any(k in combined for k in INTL_KEYWORDS)
                # UEFA-dışı konfederasyon KULÜP kupaları (OFC/CAF/AFC/CONCACAF Champions
                # League...) 'champions league' anahtarıyla uluslararası SAYILMAZ —
                # aksi halde 'Venus - Tiga Sport' gibi maçlar UEFA ŞL etiketiyle sızıyordu.
                if is_intl and any(c in combined for c in NON_UEFA_CONFED_CUPS):
                    is_intl = False
                # Only exclude low-profile club confederations (AFC/CAF/CONCACAF club)
                # AFTER we've checked is_intl, so national-team & World Cup pass through.
                if not is_intl and any(c in combined for c in EXCLUDED_COUNTRIES):
                    continue
                league_match = None
                if is_tr_stage:
                    if "süper" in sn or "super lig" in sn:
                        league_match = ("TRENDYOL SÜPER LİG", 500)
                    elif "cup" in sn or "kupa" in sn:
                        league_match = ("ZİRAAT TÜRKİYE KUPASI", 380)
                elif is_intl:
                    # Match longest keyword first so "world cup qualif" beats "world cup"
                    for kw, label, base_score in sorted(BIG_LEAGUE_KEYWORDS,
                                                       key=lambda x: -len(x[0])):
                        if kw in combined:
                            league_match = (label, base_score)
                            break
                else:
                    if any(c in combined for c in BIG_COUNTRIES):
                        for kw, label, score in BIG_LEAGUE_KEYWORDS:
                            if sn_root == kw:
                                league_match = (label, score)
                                break
                if league_match:
                    league_label, base = league_match
                else:
                    # Tanınmayan lig/ülke → stage ATLANMAZ; event bazında SADECE büyük
                    # TR kulübü (GS/FB/BJK/TS) maçları alınır (GS maçı ASLA kaçmaz).
                    league_label, base = None, 0
                for ev in (stage.get("Events") or []):
                    eps = (ev.get("Eps") or "")
                    if eps not in ("NS", "Not Started", "1H", "2H", "HT", "ET", "PEN",
                                   "FT", "AET", "AP", "Pen."):
                        continue
                    t1_raw = ((ev.get("T1") or [{}])[0].get("Nm") or "")
                    t2_raw = ((ev.get("T2") or [{}])[0].get("Nm") or "")
                    # TBD finalist placeholder'ı ele (ör. "France/Spain" — henüz belli olmayan eşleşme)
                    if "/" in t1_raw or "/" in t2_raw:
                        continue
                    t1 = _normalize_tr(t1_raw)
                    t2 = _normalize_tr(t2_raw)
                    is_gs = bool(re.search(r'\bgalatasaray\b', t1) or re.search(r'\bgalatasaray\b', t2))
                    is_big_tr = is_gs or bool(BIG_CLUB_REGEX_S.search(t1) or BIG_CLUB_REGEX_S.search(t2))
                    if league_label is None:
                        # Tanınmayan lig → güvenli davranış: SADECE büyük TR kulübü
                        # (GS/FB/BJK/TS) maçları geçer. (Gevşek BIG_EU_CLUB_REGEX bypass'ı
                        # 'inter'/'milan'/'roma' gibi desenlerle sızıntı yaratıyordu — kaldırıldı.)
                        if not is_big_tr:
                            continue
                        # Etiket TÜRKÇE: hazırlık turnuvaları "HAZIRLIK MAÇI" olur
                        _snm_l = (stage.get("Snm") or "").lower()
                        cur_label = ("HAZIRLIK MAÇI" if ("friendl" in _snm_l or "pre-season" in _snm_l or "preseason" in _snm_l)
                                     else (stage.get("Snm") or "ÖZEL MAÇ").upper())
                        cur_base = 120
                    else:
                        cur_label, cur_base = league_label, base
                    # UEFA KULÜP kupalarının ELEME turlarındaki ufak kulüpleri (KuPS/Riga/TNS/Larne...)
                    # ele — sadece büyük bir Türk kulübü oynuyorsa göster. Grup/eleme dışı turlar
                    # (gerçek UCL/UEL) etkilenmez; milli takım (Dünya Kupası/Euro/Uluslar/Hazırlık) etkilenmez.
                    if ("ŞAMPİYONLAR" in cur_label or "AVRUPA LİGİ" in cur_label
                            or "KONFERANS" in cur_label):
                        is_qualifier = any(q in combined for q in (
                            "qualif", "preliminary", "prelim", "1st round", "2nd round",
                            "3rd round", "play-off", "playoff"))
                        if is_qualifier and not is_big_tr:
                            continue
                    score = cur_base
                    if eps in ("1H", "2H", "HT", "ET", "PEN"):
                        score += 2000
                    elif eps in ("FT", "AET", "AP", "Pen."):
                        if day_offset == 0 and not _too_old_ft(ev, d_str):
                            score += 800
                        elif day_offset == -1 and is_gs:
                            score += 600
                        elif day_offset == -1 and is_big_tr:
                            score += 300
                        else:
                            continue
                    elif eps in ("NS", "Not Started"):
                        if day_offset < 0:
                            continue
                        score += max(0, 700 - day_offset * 80)
                    if is_gs:
                        score += 1000
                    elif is_big_tr:
                        score += 350
                    out.append((score, ev, cur_label, d_str, day_offset, eps))
            return out

        all_c = []
        all_c.extend(await collect(today, 0))
        for d_back in (1, 2):
            past = (now - timedelta(days=d_back)).strftime("%Y%m%d")
            past_cs = await collect(past, -d_back)
            for c in past_cs:
                t1 = _normalize_tr(((c[1].get("T1") or [{}])[0].get("Nm") or ""))
                t2 = _normalize_tr(((c[1].get("T2") or [{}])[0].get("Nm") or ""))
                if re.search(r'\bgalatasaray\b', t1) or re.search(r'\bgalatasaray\b', t2):
                    all_c.append(c)
        for day_offset in range(1, 8):
            future = (now + timedelta(days=day_offset)).strftime("%Y%m%d")
            all_c.extend(await collect(future, day_offset))

        if not all_c:
            return None

        all_c.sort(key=lambda x: x[0], reverse=True)

        def _build(item):
            score, ev, league_label, d_str, day_offset, eps = item
            res = _livescore_event_to_score(ev, league_label)
            if eps in ("FT", "AET", "AP", "Pen."):
                res["status"] = "MAÇ SONU" if day_offset == 0 else f"SON MAÇ - {d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            elif eps in ("NS", "Not Started"):
                esd = ev.get("Esd")
                time_lbl = ""
                if esd and len(str(esd)) >= 12:
                    try:
                        s = str(esd)
                        utc_dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]),
                                          int(s[8:10]), int(s[10:12]), tzinfo=timezone.utc)
                        local_dt = utc_dt.astimezone(TR_TZ)
                        time_lbl = local_dt.strftime("%H:%M")
                    except Exception:
                        pass
                if day_offset == 0:
                    res["status"] = f"BUGÜN {time_lbl}" if time_lbl else "BUGÜN"
                elif day_offset == 1:
                    res["status"] = f"YARIN {time_lbl}" if time_lbl else "YARIN"
                else:
                    day_name = (now.astimezone(TR_TZ) + timedelta(days=day_offset)).strftime("%d.%m")
                    res["status"] = f"{day_name} {time_lbl}" if time_lbl else day_name
            return res

        seen = set()
        top_list = []
        for item in all_c:
            ev = item[1]
            key = (((ev.get("T1") or [{}])[0].get("Nm") or ""),
                   ((ev.get("T2") or [{}])[0].get("Nm") or ""))
            if key in seen:
                continue
            seen.add(key)
            top_list.append(_build(item))
            if len(top_list) >= top_n:
                break

        # SAAT DÜZELTME: sporekrani'nin (TR yayın rehberi) kesin saatleri LiveScore'u düzeltir
        try:
            from .tv_schedule import correct_kickoff_labels
            await correct_kickoff_labels(top_list)
        except Exception as _e:
            logger.debug(f"kickoff label correction skipped: {_e}")

        if top_n == 1:
            return top_list[0] if top_list else None
        return {"type": "score_top", "matches": top_list, "timestamp": datetime.now(timezone.utc).isoformat()}

