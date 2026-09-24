"""TV yayın programı scraper — sporekrani.com'dan günlük futbol maçlarını çekip
öne çıkan yayının HANGİ kanal kutusuna (bein1/trt1/...) ait olduğunu OTOMATİK bulur.

Neden gerekli? LiveScore/FotMob API'leri TV yayın kanalı bilgisini VERMEZ. Bu yüzden
sporekrani.com günlük programı hafif regex ile parse edilir (bs4 gibi ek bağımlılık YOK,
motoru zorlamaz). Sonuç 15 dk cache'lenir → tekrar tekrar scrape yapılmaz.

Kullanıcı öncelik kuralları:
  * Aynı anda birden fazla maç canlıysa: ÖNCELİK Galatasaray > beIN Sports 1 > diğerleri.
  * Galatasaray ile beIN Sports 1 çakışırsa → Galatasaray kazanır.
  * Maç saatinden 10 dk ÖNCE "canlı" pencereye girer (başlamak üzere).
  * Şu an canlı maç yoksa: gelecek 12 saat içindeki EN YAKIN maç "yakında" gösterilir.
  * Hiçbir maç yoksa → gizli (channel="").
"""
import re
import json
import logging
import asyncio
from time import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

try:
    # Tercih edilen: gerçek Chrome TLS parmak izi (Cloudflare bot challenge geçer)
    from curl_cffi import requests as cffi_requests
except Exception:  # serverless/Vercel veya paket yoksa → httpx fallback
    cffi_requests = None

logger = logging.getLogger("banbansports.tv_schedule")

_TZ = ZoneInfo("Europe/Istanbul")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Maç aktiflik pencereleri (dakika / saat)
PRE_START_MIN = 10        # kick-off'tan 10 dk önce "canlı" say
MATCH_DURATION_MIN = 150  # ~2.5 saat (devre arası + uzatma dahil) sonra "bitti"
UPCOMING_WINDOW_HOURS = 12

# Uygulamadaki 8 kanal kutusunun görünen adları
APP_CHANNEL_NAMES = {
    "tivibuspor": "TİVİBU SPOR", "trt1": "TRT 1", "trtspor": "TRT SPOR",
    "trthaber": "TRT HABER", "tv8": "TV 8", "bein1": "beIN SPORTS 1",
    "ssport": "S SPORT", "atv": "ATV",
}

# ==== Program cache (hafif; tarih -> {at, matches}) ====
_SCHED_CACHE: dict = {}
_SCHED_TTL = 900.0  # 15 dk


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    tr = str.maketrans("ıİşğüöç", "iisguoc")
    s = s.translate(tr)
    s = s.replace("ı", "i")
    s = re.sub(r"\s+", " ", s)
    return s


def map_channel_name(raw: str):
    """sporekrani kanal adı → uygulama kanal id'si (yoksa None).
    Alt-kanallar (beIN 4, TV 8 Buçuk, S Sport 2, TRT Spor Yıldız) BİLEREK dışlanır —
    uygulamada karşılığı yok, yanlış kutuyu yakmasın."""
    n = _norm(raw)
    if not n:
        return None
    # beIN Sports 1 (max/haber/4 vб. DEĞİL)
    if n.startswith("bein sport") and n.endswith(" 1") and "max" not in n:
        return "bein1"
    if n == "trt 1":
        return "trt1"
    if n == "trt spor":  # "trt spor yildiz" hariç
        return "trtspor"
    if n == "trt haber":
        return "trthaber"
    if n == "tv 8":  # "tv 8 bucuk" hariç
        return "tv8"
    if n in ("s sport", "s sport plus"):  # "s sport 2" hariç
        return "ssport"
    if n == "tivibu spor":
        return "tivibuspor"
    if n == "atv":
        return "atv"
    return None


def _fetch_html(date_str: str) -> str:
    def _do():
        url = f"https://www.sporekrani.com/home/day/{date_str}"
        if cffi_requests is not None:
            r = cffi_requests.get(url, headers={"User-Agent": _UA},
                                  impersonate="chrome120", timeout=20)
        else:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
        return r.text if r.status_code == 200 else ""
    return _do()


_ANCHOR_RE = re.compile(r'<a[^>]+href="(/home/match/[^"]+hangi-kanalda)"[^>]*>(.*?)</a>', re.S)
_SPORT_RE = re.compile(r'src="[^"]*/sports/[^"]*"[^>]*?alt="([^"]*)"')
_TIME_RE = re.compile(r'event-list__time[^>]*>\s*([0-9]{1,2}:[0-9]{2})')
_NAME_RE = re.compile(r'event-list__name[^>]*>([^<]+)<')
_LEAGUE_RE = re.compile(r'event-list__league[^>]*>([^<]+)<')
_CHAN_RE = re.compile(r'src="[^"]*/channels/[^"]*"[^>]*?alt="([^"]*)"')
# Sayfaya gömülü Nuxt JSON'u — GERÇEK TR saati burada ("Z" yanıltıcı, değer TR yereldir)
_JSON_EVT_RE = re.compile(
    r'\{"id":(\d+),"event_type_name":"match","date_time":"([^"]+)","league_name":"([^"]*)","name":"([^"]*)"')


def _unesc(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def _parse_json_events(html: str, date_str: str) -> dict:
    """Gömülü JSON'dan {id: {time, league, name}} — saatler kesin doğru (TR yerel)."""
    out = {}
    for mid, dt, lg, name in _JSON_EVT_RE.findall(html):
        if not dt.startswith(date_str):
            continue
        out[mid] = {"time": dt[11:16], "league": _unesc(lg), "name": _unesc(name)}
    return out


def _parse(html: str) -> list:
    """HTML → futbol maçları [{time, home, away, league, channels[], app_channel}]."""
    out = []
    for _href, inner in _ANCHOR_RE.findall(html):
        mid_m = re.search(r'/home/match/(\d+)/', _href)
        mid = mid_m.group(1) if mid_m else ""
        sport = _SPORT_RE.search(inner)
        if not sport or _norm(sport.group(1)) != "futbol":
            continue  # sadece futbol (öne çıkan yayın futbol odaklı)
        t = _TIME_RE.search(inner)
        name = _NAME_RE.search(inner)
        if not t or not name:
            continue
        teams = name.group(1).strip()
        if " - " not in teams:
            continue  # program/haber satırı (maç değil)
        home, away = [x.strip() for x in teams.split(" - ", 1)]
        league = (_LEAGUE_RE.search(inner).group(1).strip()
                  if _LEAGUE_RE.search(inner) else "")
        # kanal adayları → uygulama kanalına eşle (dedup, sıra korunur)
        raw_chans, seen = [], set()
        for c in _CHAN_RE.findall(inner):
            if c not in seen:
                seen.add(c)
                raw_chans.append(c)
        # beIN 1 varsa onu tercih et, yoksa ilk eşleşen; bizde olmayan kanal → None
        mapped = [map_channel_name(c) for c in raw_chans]
        mapped = [m for m in mapped if m]
        app_ch = "bein1" if "bein1" in mapped else (mapped[0] if mapped else None)
        # NOT: app_ch None olsa bile maç TUTULUR (GÜNÜN MAÇI kutusu bilgi gösterir, TV100 vb.)
        out.append({"id": mid, "time": t.group(1), "home": home, "away": away,
                    "league": league, "channels": raw_chans, "app_channel": app_ch})
    return out


async def _get_schedule(day_offset: int = 0) -> list:
    """Günün (veya yarının) programı. Anchor'lardan kanallar + gömülü JSON'dan KESİN saatler.
    JSON'da olup anchor'da olmayan maçlar da eklenir (json_only, kanal bilgisi yok)."""
    now = time()
    d = (datetime.now(_TZ) + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    c = _SCHED_CACHE.get(d)
    if c and (now - c["at"]) < _SCHED_TTL:
        return c["matches"]
    try:
        html = await asyncio.to_thread(_fetch_html, d)
        matches = _parse(html) if html else []
        jevents = _parse_json_events(html, d) if html else {}
        seen = set()
        for m in matches:
            seen.add(m.get("id"))
            je = jevents.get(m.get("id"))
            if je and je.get("time"):
                m["time"] = je["time"]  # JSON saati kesindir (anchor bazen yanlış/eksik)
        for mid, je in jevents.items():
            if mid in seen or " - " not in je["name"]:
                continue
            home, away = [x.strip() for x in je["name"].split(" - ", 1)]
            matches.append({"id": mid, "time": je["time"], "home": home, "away": away,
                            "league": je["league"], "channels": [], "app_channel": None,
                            "json_only": True})
        if html:
            _SCHED_CACHE[d] = {"at": now, "matches": matches}
        return matches
    except Exception as e:
        logger.debug(f"tv schedule fetch fail: {e}")
        return c["matches"] if c else []


def _is_gala(m: dict) -> bool:
    blob = _norm(m["home"] + " " + m["away"])
    return "galatasaray" in blob


# ===== ÖNEM SIRALAMASI — skorboard/match center (livescore.py) ile AYNI mantık =====
# Lig baz puanları + GS +1000, büyük TR kulübü +350, canlı maç +2000
_LEAGUE_SCORES = [
    ("super lig", 500), ("turkiye kupasi", 380), ("ziraat", 380),
    ("dunya kupasi", 260), ("world cup", 260),
    ("sampiyonlar ligi", 200), ("champions league", 200),
    ("avrupa ligi", 180), ("europa league", 180),
    ("konferans ligi", 165), ("conference league", 165),
    ("uluslar ligi", 175), ("nations league", 175),
    ("premier lig", 150), ("premier league", 150),
    ("la liga", 145), ("bundesliga", 140), ("serie a", 138), ("ligue 1", 130),
    ("hazirlik", 115), ("friendly", 115),
]
_BIG_TR_RE = re.compile(r"galatasaray|fenerbahce|besiktas|trabzonspor")
# Gençlik/kadın/rezerv/alt ligler + "championship" gibi alt kategoriler ASLA günün maçı olamaz
_EXCLUDE_RE = re.compile(
    r"u-?1[5-9]\b|u-?2[0-3]\b|genc|kadin|women|rezerv|reserve|youth|amator|amateur"
    r"|championship|akademi|academy|primavera|2\. lig|3\. lig|serie b|serie c|ligue 2"
    r"|bundesliga 3|3\. liga|liga 3\b")


def _importance(m: dict) -> int:
    lg = _norm(m["league"])
    base = 50
    for kw, sc in _LEAGUE_SCORES:
        if kw in lg:
            base = sc
            break
    blob = _norm(m["home"] + " " + m["away"])
    if "galatasaray" in blob:
        base += 1000
    elif _BIG_TR_RE.search(blob):
        base += 350
    return base


async def pick_day_match():
    """GÜNÜN MAÇI kutusu — KUSURSUZ hibrit sistem:
    1) Maç seçimi: skorboard/match center'ın BİREBİR aynı sistemi (fetch_live_scores,
       LiveScore→FotMob→SofaScore zinciri + aynı önem sıralaması).
    2) Kanal bilgisi: sporekrani'den takım adı eşleştirmesiyle zenginleştirilir
       (YouTube / "Yayın Yok" elenir). Bulunamazsa kanal boş — maç yine gösterilir.
    3) LiveScore zinciri komple çökerse: sporekrani-only yedek seçim devreye girer.
    Sonuç 60 sn cache'lenir (motor yorulmaz)."""
    now_ts = time()
    if _DAY_CACHE["val"] is not None and (now_ts - _DAY_CACHE["at"]) < 60:
        return _DAY_CACHE["val"]
    val = None
    try:
        val = await _pick_from_livescore()
    except Exception as e:
        logger.debug(f"livescore day pick fail: {e}")
    if val is None:
        try:
            val = await _pick_from_sporekrani()
        except Exception as e:
            logger.debug(f"sporekrani day pick fail: {e}")
            val = None
    # Kaynaklar geçici çökerse son başarılı seçimi koru — GÜNÜN MAÇI asla kaybolmaz
    if val is not None:
        _DAY_LAST_GOOD.update(at=now_ts, val=val)
    elif _DAY_LAST_GOOD["val"] is not None:
        val = _DAY_LAST_GOOD["val"]
    _DAY_CACHE.update(at=now_ts, val=val)
    return val


_DAY_LAST_GOOD = {"at": 0.0, "val": None}


_DAY_CACHE = {"at": 0.0, "val": None}


async def _sporekrani_lookup(home: str, away: str):
    """Takım adlarına göre maçı bugün+yarın programında ara.
    Döner: (kanal_adı, app_channel, kesin_saat, gün_offset) — bulunamazsa ('', None, '', None)."""
    nh, na = _norm(home), _norm(away)

    def _sim(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:  # önce tam eşitlik
            return True
        # substring fallback: min 5 karakter — kısa adlar ('roma','psg') yanlış maça eşleşmesin
        if len(a) < 5 or len(b) < 5:
            return False
        return a in b or b in a

    for off in (0, 1):
        try:
            matches = await _get_schedule(off)
        except Exception:
            continue
        for m in matches:
            if _sim(_norm(m["home"]), nh) and _sim(_norm(m["away"]), na):
                real = [c for c in m["channels"]
                        if "youtube" not in _norm(c) and "yayin yok" not in _norm(c)]
                return (real[0] if real else ""), m["app_channel"], (m.get("time") or ""), off
    return "", None, "", None


async def correct_kickoff_labels(top_list) -> None:
    """Skorboard NS maçlarının BUGÜN/YARIN saatlerini sporekrani'nin KESİN TR saatiyle düzeltir
    (LiveScore bazen yanlış saat verir — örn. GS-Venezia 19:00 değil 21:00)."""
    for it in (top_list or []):
        st = it.get("status") or ""
        m_cur = re.match(r"^(BUGÜN|YARIN)\s+(\d{1,2}):(\d{2})$", st)
        if not m_cur:
            continue
        try:
            _ch, _app, sp_time, off = await _sporekrani_lookup(
                it.get("team1_en") or it.get("team1") or "",
                it.get("team2_en") or it.get("team2") or "")
        except Exception:
            continue
        if not sp_time or off is None:
            continue
        m_new = re.match(r"^(\d{1,2}):(\d{2})$", sp_time.strip())
        if not m_new:
            continue
        # ±3 SAAT SİGORTASI: sapma 3 saati aşıyorsa büyük ihtimalle YANLIŞ maç
        # eşleşti (veya program hatalı) → düzeltme UYGULANMAZ, LiveScore saati kalır.
        cur_min = (0 if m_cur.group(1) == "BUGÜN" else 1440) + int(m_cur.group(2)) * 60 + int(m_cur.group(3))
        new_min = off * 1440 + int(m_new.group(1)) * 60 + int(m_new.group(2))
        if abs(new_min - cur_min) > 180:
            continue
        it["status"] = f"{'BUGÜN' if off == 0 else 'YARIN'} {sp_time}"


async def _sporekrani_channel_for(home: str, away: str):
    """Seçilen maçın TV kanalını sporekrani programından bul (yoksa boş döner)."""
    ch, app_ch, _t, _o = await _sporekrani_lookup(home, away)
    return ch, app_ch


async def _pick_from_livescore():
    """Skorboard'ın top-10 listesinden, kullanıcı pencere kurallarına uyan İLK maçı seç:
    canlı (veya başlamasına ≤10 dk) → live; ≤12 saat → upcoming; MAÇ SONU/uzak tarih → atla."""
    from .livescore import fetch_live_scores
    data = await fetch_live_scores(top_n=10)
    if not data or not data.get("matches"):
        return None
    now = datetime.now(_TZ)
    fb = None  # 12 saat penceresine girmese de İLK yaklaşan maç (kutu asla boş kalmasın)
    for c in data["matches"]:
        st_label = c.get("status") or ""
        is_live = bool(c.get("isLive"))
        kick = None
        status = None
        if is_live:
            status = "live"
        else:
            m2 = re.match(r"^(BUGÜN|YARIN)\s+(\d{1,2}):(\d{2})$", st_label)
            if not m2:
                continue  # MAÇ SONU / 12 saatten uzak tarih → kutuya girmez
            d = now.date() if m2.group(1) == "BUGÜN" else (now + timedelta(days=1)).date()
            kick = datetime(d.year, d.month, d.day, int(m2.group(2)), int(m2.group(3)), tzinfo=_TZ)
            diff = kick - now
            if diff <= timedelta(minutes=PRE_START_MIN):
                status = "live"  # 10 dk kala canlı sayılır (kullanıcı kuralı)
            elif diff <= timedelta(hours=UPCOMING_WINDOW_HOURS):
                status = "upcoming"
            else:
                if fb is None or kick < fb[1]:
                    fb = (c, kick)
                continue
        home = c.get("team1") or c.get("team1_en") or ""
        away = c.get("team2") or c.get("team2_en") or ""
        ch_name, app_ch = await _sporekrani_channel_for(
            c.get("team1_en") or home, c.get("team2_en") or away)
        starts_in = (max(0, int((kick - now).total_seconds() // 60))
                     if (kick and status == "upcoming") else 0)
        return {
            "home": home, "away": away, "league": c.get("league") or "",
            "time": (kick.strftime("%H:%M") if kick else ""),
            "kickoff_iso": (kick.isoformat() if kick else ""),
            "starts_in_min": starts_in, "status": status,
            "channel_name": ch_name, "app_channel": app_ch,
            "watchable": bool(app_ch),
            "score1": c.get("score1"), "score2": c.get("score2"),
            "status_label": st_label if is_live else "",
        }
    if fb is not None:
        c, kick = fb
        home = c.get("team1") or c.get("team1_en") or ""
        away = c.get("team2") or c.get("team2_en") or ""
        ch_name, app_ch = await _sporekrani_channel_for(
            c.get("team1_en") or home, c.get("team2_en") or away)
        return {
            "home": home, "away": away, "league": c.get("league") or "",
            "time": kick.strftime("%H:%M"), "kickoff_iso": kick.isoformat(),
            "starts_in_min": max(0, int((kick - now).total_seconds() // 60)),
            "status": "upcoming", "channel_name": ch_name, "app_channel": app_ch,
            "watchable": bool(app_ch),
            "score1": c.get("score1"), "score2": c.get("score2"),
            "status_label": "",
        }
    return None


async def _pick_from_sporekrani():
    """YEDEK seçim — LiveScore zinciri çökerse sporekrani programından önem sıralı seçim."""
    matches = await _get_schedule()
    now = datetime.now(_TZ)
    today = now.date()
    best = None  # (score, start, match, status)
    for m in matches:
        try:
            hh, mm = m["time"].split(":")
            start = datetime(today.year, today.month, today.day,
                             int(hh), int(mm), tzinfo=_TZ)
        except Exception:
            continue
        active = (start - timedelta(minutes=PRE_START_MIN)) <= now <= (start + timedelta(minutes=MATCH_DURATION_MIN))
        upcoming = now < start - timedelta(minutes=PRE_START_MIN) and (start - now) <= timedelta(hours=UPCOMING_WINDOW_HOURS)
        if not (active or upcoming):
            continue
        lg = _norm(m["league"])
        if _EXCLUDE_RE.search(lg):
            continue  # gençlik/kadın/alt lig/championship → asla günün maçı değil
        # YouTube-only / "Yayın Yok" maçlar günün maçı olamaz (izlenebilir TV kanalı şart)
        real_chans = [c for c in m["channels"]
                      if "youtube" not in _norm(c) and "yayin yok" not in _norm(c)]
        if not real_chans and not m["app_channel"]:
            continue
        imp = _importance(m)
        if imp < 100:
            continue  # skorboard gibi: tanınmayan küçük ligler GÜNÜN MAÇI olamaz
        sc = imp + (2000 if active else 0)
        if best is None or sc > best[0] or (sc == best[0] and start < best[1]):
            best = (sc, start, m, "live" if active else "upcoming", real_chans)
    if not best:
        return None
    _sc, start, m, st, real_chans = best
    return {
        "home": m["home"], "away": m["away"], "league": m["league"], "time": m["time"],
        "kickoff_iso": start.isoformat(),
        "starts_in_min": max(0, int((start - now).total_seconds() // 60)),
        "status": st,
        "channel_name": (real_chans[0] if real_chans else (m["channels"][0] if m["channels"] else "")),
        "app_channel": m["app_channel"],
        "watchable": bool(m["app_channel"]),
    }


async def pick_featured(source_live: bool) -> dict:
    """Öne çıkan yayının HANGİ kanal kutusuna ait olduğunu döndürür.

    Yayın kaynağı FİZİKSEL olarak beIN Sports 1'dir → varsayılan kutu HER ZAMAN beIN 1.
    TEK istisna: Galatasaray maçı canlıysa (kullanıcı yayını GS maçına çevirir ve bu maç
    başka bir kanalda olabilir) → o kanala geçer. Öncelik: Galatasaray > beIN Sports 1.
    Diğer kanallar (TRT Spor, S Sport vb.) öne çıkan yayına ASLA otomatik atanmaz.
    """
    matches = await _get_schedule()
    now = datetime.now(_TZ)
    today = now.date()

    gala_live = None      # (match, start) — canlı Galatasaray maçı
    gala_upcoming = None  # (match, start) — 12s içinde başlayacak GS maçı
    bein_live = None      # (match, start) — canlı beIN Sports 1 maçı (bilgi amaçlı)

    for m in matches:
        try:
            hh, mm = m["time"].split(":")
            start = datetime(today.year, today.month, today.day,
                             int(hh), int(mm), tzinfo=_TZ)
        except Exception:
            continue
        active_from = start - timedelta(minutes=PRE_START_MIN)
        active_to = start + timedelta(minutes=MATCH_DURATION_MIN)
        is_active = active_from <= now <= active_to
        is_upcoming = now < active_from and (start - now) <= timedelta(hours=UPCOMING_WINDOW_HOURS)

        if _is_gala(m) and m["app_channel"]:
            if is_active and (gala_live is None or start < gala_live[1]):
                gala_live = (m, start)
            elif is_upcoming and (gala_upcoming is None or start < gala_upcoming[1]):
                gala_upcoming = (m, start)
        if m["app_channel"] == "bein1" and is_active and (bein_live is None or start < bein_live[1]):
            bein_live = (m, start)

    def _match_info(m, start):
        starts_in = max(0, int((start - now).total_seconds() // 60))
        return {"home": m["home"], "away": m["away"], "league": m["league"],
                "time": m["time"], "kickoff_iso": start.isoformat(),
                "starts_in_min": starts_in}

    def _pack(channel, status, info):
        return {"channel": channel,
                "name": APP_CHANNEL_NAMES.get(channel, channel.upper()),
                "status": status, "match": info}

    # Kaynak ayaktaysa → mutlaka bir yayın göster
    if source_live:
        if gala_live:  # Galatasaray canlı → onun kanalına geç (öncelik GS)
            m, start = gala_live
            return _pack(m["app_channel"], "live", _match_info(m, start))
        # Varsayılan: yayın beIN Sports 1'dir
        info = _match_info(*bein_live) if bein_live else None
        return _pack("bein1", "live", info)

    # Kaynak kapalı → oynatılamaz; yalnızca GS için "yakında" bilgisi göster
    if gala_upcoming:
        m, start = gala_upcoming
        return _pack(m["app_channel"], "upcoming", _match_info(m, start))
    if gala_live:
        m, start = gala_live
        return _pack(m["app_channel"], "upcoming", _match_info(m, start))
    return {"channel": "", "name": "", "status": "none", "match": None}

