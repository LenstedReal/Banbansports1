"""Match stats — LiveScore + SportsDB + SofaScore fallback chain."""
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter

from ..core.config import LIVESCORE_FETCH_TIMEOUT
from ..core.team_translations import tr_to_en_candidates
from ..services.livescore import (
    livescore_fetch_day, _normalize_tr,
    LIVESCORE_HEADERS, SDB_BASE, SOFASCORE_HEADERS, FOTMOB_HEADERS,
)

logger = logging.getLogger("banbansports.matchstats")
router = APIRouter(prefix="/api/match", tags=["match"])

SDB_HEADERS = {"User-Agent": "Mozilla/5.0"}


async def _sdb_get(http: httpx.AsyncClient, path: str) -> Optional[dict]:
    try:
        r = await http.get(f"{SDB_BASE}{path}", headers=SDB_HEADERS)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


@router.get("/stats")
async def get_match_stats(home: str, away: str, date: Optional[str] = None):
    # Accept both Turkish and English team names — generate all candidates
    home_candidates = [_normalize_tr(c) for c in tr_to_en_candidates(home.strip())]
    away_candidates = [_normalize_tr(c) for c in tr_to_en_candidates(away.strip())]

    def _forms(s: str) -> set:
        """İsim varyantları: normalize, boşluksuz, baş harf kısaltması.
        (FotMob 'LAFC' der, LiveScore 'Los Angeles FC' — ikisi de eşleşmeli.)"""
        n = _normalize_tr(s)
        out = {n}
        ns = n.replace(" ", "").replace(".", "").replace("-", "")
        if ns:
            out.add(ns)
        words = [w for w in n.replace(".", " ").replace("-", " ").split() if w]
        if len(words) >= 2:
            # Kısa ekler (FC, SC, AS...) tam kalır: "Los Angeles FC" → "lafc"
            acr = "".join(w if len(w) <= 2 else w[0] for w in words)
            if len(acr) >= 3:
                out.add(acr)
            # Sondaki kısaltma ekini at: "Botafogo FR" / "Botafogo RJ" → "botafogo"
            # (kaynaklar aynı takıma farklı federasyon eki verir; iki takım birden
            # eşleşmek zorunda olduğundan yanlış maça bağlanma riski yoktur)
            if len(words[-1]) <= 3 and len(" ".join(words[:-1])) >= 5:
                stripped = " ".join(words[:-1])
                out.add(stripped)
                out.add(stripped.replace(" ", ""))
        return out

    home_forms: set = set()
    away_forms: set = set()
    for c in tr_to_en_candidates(home.strip()):
        home_forms |= _forms(c)
    for c in tr_to_en_candidates(away.strip()):
        away_forms |= _forms(c)
    stats: dict = {"home": home, "away": away, "events": [], "stats": {}, "sources": []}

    def _match_level(t1: str, t2: str) -> int:
        """2 = tam eşleşme, 1 = bulanık (substring/kısaltma), 0 = yok.
        Çakışma fix: iki canlı maçta benzer isimler (ör. 'Inter' ~ 'Inter Miami')
        yanlış maça bağlanmasın diye önce TAM eşleşme tercih edilir."""
        t1n, t2n = _normalize_tr(t1), _normalize_tr(t2)
        h_exact = any(h == t1n for h in home_candidates if h)
        a_exact = any(a == t2n for a in away_candidates if a)
        if h_exact and a_exact:
            return 2
        t1f, t2f = _forms(t1), _forms(t2)
        h_ok = any(h in t1n or t1n in h for h in home_candidates if h) or bool(home_forms & t1f)
        a_ok = any(a in t2n or t2n in a for a in away_candidates if a) or bool(away_forms & t2f)
        return 1 if (h_ok and a_ok) else 0

    def _match(t1: str, t2: str) -> bool:
        return _match_level(t1, t2) > 0

    async with httpx.AsyncClient(timeout=LIVESCORE_FETCH_TIMEOUT) as http:
        found = None
        incidents_ok = False   # incidents endpoint'inden GERÇEK olay verisi geldi mi
        stat_ok = False        # statistics endpoint'i cevap verdi mi (0 değerleri de gerçek olur)
        subs_counts = None     # lineups'tan doğrulanmış değişiklik sayısı [home, away]
        dates_to_try = [date] if (date and len(date) == 8) else [
            (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y%m%d") for d in range(0, 15)
        ]
        for d in dates_to_try:
            data = await livescore_fetch_day(http, d)
            if not data:
                continue
            exact = None
            fuzzy = None
            for stage in (data.get("Stages") or []):
                for ev in (stage.get("Events") or []):
                    t1 = ((ev.get("T1") or [{}])[0].get("Nm") or "")
                    t2 = ((ev.get("T2") or [{}])[0].get("Nm") or "")
                    lvl = _match_level(t1, t2)
                    if lvl == 2 and exact is None:
                        exact = (ev, d, stage)
                        break
                    if lvl == 1 and fuzzy is None:
                        fuzzy = (ev, d, stage)
                if exact:
                    break
            found = exact or fuzzy
            if found:
                break

        if found:
            ev, ev_date, stage = found
            stats["sources"].append("livescore")
            stats["live_event_id"] = ev.get("Eid")
            stats["date"] = ev_date
            _snm = stage.get("Snm") or ""
            _cnm = stage.get("Cnm") or ""
            # Aşama-adı (Final, Third Place Play-Off...) tek başına anlamsız → turnuva adıyla birleştir
            import re as _re
            if _cnm and _re.match(r'^(third[\s-]?place|3rd[\s-]?place|finals?$|semi|quarter|round of|knockout|play[\s-]?offs?$)', _snm, _re.I):
                stats["league"] = f"{_cnm} {_snm}"
            else:
                stats["league"] = _snm or _cnm or ""
            stats["score"] = {
                "home": ev.get("Tr1", 0), "away": ev.get("Tr2", 0),
                "pen_home": ev.get("Trp1"), "pen_away": ev.get("Trp2"),
            }
            # Skor alanları sayısal olsun (LiveScore bazen '1' string döner)
            for _k in ("home", "away"):
                try:
                    stats["score"][_k] = int(stats["score"][_k])
                except (TypeError, ValueError):
                    pass
            stats["eps"] = ev.get("Eps")

            event_id = ev.get("Eid")
            md_incs = []
            if event_id:
                try:
                    r = await http.get(f"https://prod-public-api.livescore.com/v1/api/app/scoreboard/soccer/{event_id}",
                                       headers=LIVESCORE_HEADERS)
                    if r.status_code == 200:
                        md = r.json()
                        if md.get("Tr1") is not None:
                            stats["score"]["home"] = md.get("Tr1")
                        if md.get("Tr2") is not None:
                            stats["score"]["away"] = md.get("Tr2")
                        for _k in ("home", "away"):
                            try:
                                stats["score"][_k] = int(stats["score"][_k])
                            except (TypeError, ValueError):
                                pass
                        venue_raw = md.get("Venue")
                        if isinstance(venue_raw, dict):
                            stats["venue"] = venue_raw.get("Vnm") or venue_raw.get("Nm") or ""
                        elif isinstance(venue_raw, str):
                            stats["venue"] = venue_raw
                        if md.get("Esd"):
                            stats["start_date"] = md.get("Esd")
                except Exception:
                    pass

                # OLAYLAR — dedicated incidents endpoint (scoreboard Incs-s eksik veriyordu).
                # IT kodları 12 bitmiş maçta resmi istatistiklerle çapraz doğrulandı:
                # 36=GOL, 37=PENALTI GOL, 38=K.KALE, 43=SARI KART, 45=KIRMIZI, 63=ASİST.
                try:
                    inc_r = await http.get(f"https://prod-public-api.livescore.com/v1/api/app/incidents/soccer/{event_id}",
                                           headers=LIVESCORE_HEADERS)
                    if inc_r.status_code == 200:
                        def _walk(node):
                            if isinstance(node, dict):
                                if "IT" in node:
                                    side = "a" if str(node.get("Nm", "1")) == "2" else "h"
                                    md_incs.append((side, node))
                                for v in node.values():
                                    _walk(v)
                            elif isinstance(node, list):
                                for v in node:
                                    _walk(v)
                        _walk((inc_r.json() or {}).get("Incs"))
                        incidents_ok = True
                        stats["sources"].append("livescore_incidents")
                except Exception:
                    pass

                # Statistics
                try:
                    stat_r = await http.get(f"https://prod-public-api.livescore.com/v1/api/app/statistics/soccer/{event_id}",
                                            headers=LIVESCORE_HEADERS)
                    if stat_r.status_code == 200:
                        stat_list = (stat_r.json() or {}).get("Stat") or []
                        home_stat, away_stat = {}, {}
                        for s in stat_list:
                            if s.get("Tnb") == 1:
                                home_stat = s
                            elif s.get("Tnb") == 2:
                                away_stat = s
                        stat_map = {
                            "ball_possession":   ("Pss", "%"),
                            "shots_on_goal":     ("Shon", None),
                            "shots_off_goal":    ("Shof", None),
                            "blocked_shots":     ("Shbl", None),
                            "shots_woodwork":    ("Shwd", None),
                            "corner_kicks":      ("Cos", None),
                            "offsides":          ("Ofs", None),
                            "fouls":             ("Fls", None),
                            "yellow_cards":      ("Ycs", None),
                            "second_yellow":     ("YRcs", None),
                            "red_cards":         ("Rcs", None),
                            "goalkeeper_saves":  ("Gks", None),
                            "throw_ins":         ("Ths", None),
                        }
                        for stat_key, (field, suffix) in stat_map.items():
                            hv = home_stat.get(field, 0)
                            av = away_stat.get(field, 0)
                            if hv or av:
                                stats["stats"][stat_key] = {
                                    "home": f"{hv}{suffix or ''}",
                                    "away": f"{av}{suffix or ''}",
                                }
                        # TOPLAM ŞUT = isabetli + isabetsiz + bloklanan (gerçek alanlardan türetilir)
                        th = sum(int(home_stat.get(f) or 0) for f in ("Shon", "Shof", "Shbl"))
                        ta = sum(int(away_stat.get(f) or 0) for f in ("Shon", "Shof", "Shbl"))
                        if th or ta:
                            stats["stats"]["total_shots"] = {"home": th, "away": ta}
                        if home_stat or away_stat:
                            stat_ok = True
                        stats["sources"].append("livescore_statistics")
                except Exception:
                    pass

                # DEĞİŞİKLİKLER — lineups endpoint (IT 5 = oyuna giren, IDo = çıkan oyuncunun ID'si).
                # Doğrulandı: takım başına 0-5 arası gerçekçi sayımlar dönüyor.
                try:
                    lu_r = await http.get(f"https://prod-public-api.livescore.com/v1/api/app/lineups/soccer/{event_id}",
                                          headers=LIVESCORE_HEADERS)
                    if lu_r.status_code == 200:
                        lu = lu_r.json() or {}
                        if lu.get("Lu"):
                            subs_counts = [0, 0]
                            sub_records = []
                            name_by_id = {}
                            for _period, recs in (lu.get("Subs") or {}).items():
                                for rec in (recs or []):
                                    pid = str(rec.get("ID") or "")
                                    pn = rec.get("Pn") or f"{rec.get('Fn', '')} {rec.get('Ln', '')}".strip()
                                    if pid and pn:
                                        name_by_id[pid] = pn
                                    sub_records.append(rec)
                            for rec in sub_records:
                                if rec.get("IT") != 5:  # sadece 'giren oyuncu' kaydı = 1 değişiklik
                                    continue
                                side_i = 1 if str(rec.get("Nm", "1")) == "2" else 0
                                subs_counts[side_i] += 1
                                stats["events"].append({
                                    "minute": rec.get("Min") or 0,
                                    "type": "sub", "label": "DEĞİŞİKLİK",
                                    "team": "away" if side_i else "home",
                                    "player": rec.get("Pn") or "—",
                                    "assist": name_by_id.get(str(rec.get("IDo") or "")),
                                })
                except Exception:
                    pass

            # Incidents fallback: incidents endpoint'i başarısızsa gün feed'indeki Incs kullan
            if not incidents_ok:
                for inc in (ev.get("Incs") or []):
                    side = "a" if str(inc.get("Nm", "1")) == "2" else "h"
                    md_incs.append((side, inc))

            # === IT KOD HARİTASI — YALNIZCA DOĞRULANMIŞ KODLAR ===
            # Eski koddaki 39/40/41/49/50/4/6/7/11-31 kodları KALDIRILDI:
            # ör. 41 = penaltı atışları demekti, '2. SARI' sanılıp yanlış veri üretiyordu.
            GOAL_ITS = {36}
            PEN_ITS = {37}
            OG_ITS = {38}
            YC_ITS = {43}
            RC_ITS = {45}
            seen = set()
            for side, inc in md_incs:
                it = inc.get("IT")
                player_name = inc.get("Pn") or (f"{inc.get('Fn','')} {inc.get('Ln','')}".strip()) or inc.get("Player") or "—"
                key = (side, it, inc.get("Min"), player_name)
                if key in seen:
                    continue
                seen.add(key)
                kind = label = None
                if it in YC_ITS:
                    kind, label = "yellow", "SARI KART"
                elif it in RC_ITS:
                    kind, label = "red", "KIRMIZI KART"
                elif it in PEN_ITS:
                    kind, label = "goal", "PENALTI GOL"
                elif it in OG_ITS:
                    kind, label = "goal", "K. KALE GOL"
                elif it in GOAL_ITS:
                    kind, label = "goal", "GOL"
                if kind:
                    stats["events"].append({
                        "minute": inc.get("Min") or inc.get("Mn") or 0,
                        "type": kind, "label": label,
                        "team": "home" if side == "h" else "away",
                        "player": player_name,
                        "assist": inc.get("Pn2") or inc.get("P2"),
                    })

        # === FotMob ZENGİNLEŞTİRME — xG (gol beklentisi) ve gelişmiş istatistikler ===
        # LiveScore'da xG yok; FotMob matchDetails'ten eksik alanlar doldurulur (üzerine yazılmaz).
        FOT_MAP = {
            "expected_goals": "xg",
            "expected_goals_on_target": "xgot",
            "big_chance": "big_chances",
            "big_chance_missed_title": "big_chances_missed",
            "touches_opp_box": "touches_in_opp_box",
            "passes": "total_passes",
            "accurate_passes": "passes_accurate",
            "accurate_crosses": "accurate_crosses",
            "long_balls_accurate": "long_balls",
            "matchstats.headers.tackles": "tackles",
            "interceptions": "interceptions",
            "clearances": "clearances",
            "keeper_saves": "goalkeeper_saves",
            "duel_won": "duels_won",
            "aerials_won": "aerial_duels",
            "dribbles_succeeded": "dribbles",
            "shots_inside_box": "shots_inside_box",
            "shots_outside_box": "shots_outside_box",
            "total_shots": "total_shots",
            "ShotsOnTarget": "shots_on_goal",
            "ShotsOffTarget": "shots_off_goal",
            "blocked_shots": "blocked_shots",
            "shots_woodwork": "shots_woodwork",
            "corners": "corner_kicks",
            "Offsides": "offsides",
            "fouls": "fouls",
            "yellow_cards": "yellow_cards",
            "red_cards": "red_cards",
            "BallPossesion": "ball_possession",
        }
        # FotMob artık imzasız istekleri engelliyor (401) → x-mas imzalı modül,
        # başarısızsa Next.js data route, o da olmazsa LiveScore-only (regresyon imkânsız).
        fot_blocked = False
        try:
            from ..services.fotmob_client import fotmob_get
            fot_date = stats.get("date") or (date if (date and len(date) == 8)
                                             else datetime.now(timezone.utc).strftime("%Y%m%d"))
            fot_list, _list_st = await fotmob_get(http, f"/api/data/matches?date={fot_date}",
                                                  expect_key="leagues")
            fot_blocked = fot_list is None
            fot_id = None
            fuzzy_fid = None
            if fot_list:
                for lg in (fot_list.get("leagues") or []):
                    for m in (lg.get("matches") or []):
                        hn = (m.get("home") or {}).get("name") or ""
                        an = (m.get("away") or {}).get("name") or ""
                        lvl = _match_level(hn, an)
                        if lvl == 2:
                            fot_id = m.get("id")
                            break
                        if lvl == 1 and fuzzy_fid is None:
                            fuzzy_fid = m.get("id")
                    if fot_id:
                        break
                # Bulanık eşleşme SADECE tam eşleşme yoksa devreye girer.
                # Liste zaten fot_date gününe ait → tarih doğrulaması yapısal olarak sağlanır.
                if fot_id is None:
                    fot_id = fuzzy_fid
            added = False
            if fot_id:
                det, _det_st = await fotmob_get(http, f"/api/data/matchDetails?matchId={fot_id}",
                                                expect_key="content")
                fot_blocked = fot_blocked or det is None
                groups = ((((((det or {}).get("content") or {}).get("stats") or {})
                           .get("Periods") or {}).get("All") or {}).get("stats") or [])
                for grp in groups:
                    for st in (grp.get("stats") or []):
                        key = FOT_MAP.get(st.get("key"))
                        if not key or st.get("type") == "title" or key in stats["stats"]:
                            continue
                        vals = st.get("stats") or []
                        if len(vals) != 2 or (vals[0] is None and vals[1] is None):
                            continue
                        hv = 0 if vals[0] is None else vals[0]
                        av = 0 if vals[1] is None else vals[1]
                        suffix = "%" if key == "ball_possession" else ""
                        stats["stats"][key] = {"home": f"{hv}{suffix}", "away": f"{av}{suffix}"}
                        added = True
                if added:
                    stats["sources"].append("fotmob")
            # Kaynak durumu — sessiz bozulma biter: panel neden eksikse sources'tan görülür
            if added:
                stats["sources"].append("fotmob:ok")
            elif fot_blocked:
                stats["sources"].append("fotmob:blocked")
            else:
                stats["sources"].append("fotmob:nodata")
        except Exception as _fe:
            logger.warning(f"fotmob enrich fail: {type(_fe).__name__}: {_fe}")
            stats["sources"].append("fotmob:blocked")
        try:
            sofa_id = None
            # Çakışma fix: tarih verilmişse SADECE o günü (±1 gün) ara — 8 gün geriye
            # bulanık tarama başka maçın verisini yapıştırıyordu.
            target_date = stats.get("date") or (date if (date and len(date) == 8) else None)
            if target_date:
                base_dt = datetime.strptime(target_date, "%Y%m%d")
                sofa_dates = [base_dt.strftime("%Y-%m-%d"),
                              (base_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                              (base_dt - timedelta(days=1)).strftime("%Y-%m-%d")]
            else:
                sofa_dates = [datetime.now(timezone.utc).strftime("%Y-%m-%d")] + \
                             [(datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(1, 8)]
            # Önce TÜM tarihlerde TAM eşleşme ara; bulanık eşleşme sadece hiçbir yerde
            # tam eşleşme yoksa VE yalnızca hedef tarihte (sofa_dates[0]) kabul edilir —
            # ±1 gün bulanık tarama benzer isimli başka maçın verisini yapıştırıyordu.
            fuzzy_id = None
            for d_iso in sofa_dates:
                r = await http.get(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{d_iso}",
                                   headers=SOFASCORE_HEADERS)
                if r.status_code != 200:
                    continue
                for ev in (r.json().get("events") or []):
                    h = (ev.get("homeTeam") or {}).get("name") or ""
                    a = (ev.get("awayTeam") or {}).get("name") or ""
                    lvl = _match_level(h, a)
                    if lvl == 2:
                        sofa_id = ev.get("id")
                        break
                    if lvl == 1 and fuzzy_id is None and d_iso == sofa_dates[0]:
                        fuzzy_id = ev.get("id")
                if sofa_id:
                    break
            if sofa_id is None:
                sofa_id = fuzzy_id
            if sofa_id:
                # Stadyum bilgisi eksikse SofaScore event detayından al
                if not stats.get("venue"):
                    try:
                        ev_r = await http.get(f"https://api.sofascore.com/api/v1/event/{sofa_id}",
                                              headers=SOFASCORE_HEADERS)
                        if ev_r.status_code == 200:
                            venue_obj = ((ev_r.json() or {}).get("event") or {}).get("venue") or {}
                            v_name = (venue_obj.get("stadium") or {}).get("name") or venue_obj.get("name") or ""
                            v_city = (venue_obj.get("city") or {}).get("name") or ""
                            if v_name:
                                stats["venue"] = f"{v_name}, {v_city}" if v_city else v_name
                    except Exception:
                        pass
                inc_r = await http.get(f"https://api.sofascore.com/api/v1/event/{sofa_id}/incidents",
                                       headers=SOFASCORE_HEADERS)
                if inc_r.status_code == 200:
                    # Dedup key player ismi ile zenginleştirildi → aynı dakikada 2 değişiklik artık merge olmuyor (Bug #8)
                    existing = set((e.get("minute"), e["type"], e["team"], (e.get("player") or '')) for e in stats["events"])
                    for inc in (inc_r.json() or {}).get("incidents") or []:
                        itype = inc.get("incidentType") or ""
                        is_home = inc.get("isHome", True)
                        minute = inc.get("time") or 0
                        team = "home" if is_home else "away"
                        new_ev = None
                        if itype == "substitution":
                            p_in = (inc.get("playerIn") or {}).get("name") or "—"
                            p_out = (inc.get("playerOut") or {}).get("name")
                            new_ev = {"minute": minute, "type": "sub", "label": "DEĞİŞİKLİK", "team": team,
                                      "player": p_in, "assist": p_out}
                        elif itype == "card":
                            color = (inc.get("incidentClass") or "").lower()
                            if color == "yellow":
                                new_ev = {"minute": minute, "type": "yellow", "label": "SARI KART", "team": team,
                                          "player": (inc.get("player") or {}).get("name") or "—"}
                            elif color in ("red", "yellowred"):
                                new_ev = {"minute": minute, "type": "red",
                                          "label": "KIRMIZI KART" if color == "red" else "2. SARI = KIRMIZI",
                                          "team": team, "player": (inc.get("player") or {}).get("name") or "—"}
                        elif itype == "goal":
                            cls = (inc.get("incidentClass") or "").lower()
                            label = "PENALTI GOL" if cls == "penalty" else ("K. KALE GOL" if cls == "owngoal" else "GOL")
                            new_ev = {"minute": minute, "type": "goal", "label": label, "team": team,
                                      "player": (inc.get("player") or {}).get("name") or "—",
                                      "assist": (inc.get("assist1") or {}).get("name") if inc.get("assist1") else None}
                        if new_ev:
                            key = (new_ev["minute"], new_ev["type"], new_ev["team"], new_ev.get("player") or '')
                            if key not in existing:
                                stats["events"].append(new_ev)
                                existing.add(key)
                    stats["sources"].append("sofascore")
                    stats["events"].sort(key=lambda e: int(e.get("minute") or 0))
        except Exception:
            pass

    # === SAYIM BAZLI İSTATİSTİKLER — YALNIZCA DOĞRULANMIŞ VERİ, YOKSA '?' ===
    # Kullanıcı kuralı: yanlış istatistik göstermektense '?' (bilinmiyor) göster.
    stats["events"].sort(key=lambda e: int(e.get("minute") or 0))
    started = stats.get("eps") not in (None, "", "NS", "Not Started", "Postp.", "POSTP",
                                       "Canc.", "CANC", "TBA", "TBD", "Delayed")

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    ev_counts = {"penalty_goals": [0, 0], "own_goals": [0, 0],
                 "yellow_cards": [0, 0], "red_cards": [0, 0]}
    for ev in stats["events"]:
        side = 0 if ev.get("team") == "home" else 1
        ev_type = ev.get("type") or ""
        label = (ev.get("label") or "").upper()
        if ev_type == "goal":
            if "PENALTI" in label:
                ev_counts["penalty_goals"][side] += 1
            elif "K. KALE" in label or "KENDİ KALE" in label:
                ev_counts["own_goals"][side] += 1
        elif ev_type == "yellow":
            ev_counts["yellow_cards"][side] += 1
        elif ev_type == "red":
            ev_counts["red_cards"][side] += 1

    if started:
        # GOLLER — skor her zaman güvenilir kaynak
        if "goals" not in stats["stats"]:
            sc = stats.get("score") or {}
            gh, ga = _int(sc.get("home")), _int(sc.get("away"))
            if gh is not None and ga is not None:
                stats["stats"]["goals"] = {"home": gh, "away": ga}
            else:
                stats["stats"]["goals"] = {"home": "?", "away": "?"}

        # PENALTI / K.KALE GOLÜ — yalnızca gerçekten varsa göster (yoksa satır gizli kalır)
        for k in ("penalty_goals", "own_goals"):
            h, a = ev_counts[k]
            if (h or a) and k not in stats["stats"]:
                stats["stats"][k] = {"home": h, "away": a}

        # SARI/KIRMIZI KART — resmi statistics alanı varsa o (zaten yazıldı);
        # yoksa doğrulanmış incidents sayımı; ikisi de yoksa statistics-0; en son '?'
        for k in ("yellow_cards", "red_cards"):
            if k not in stats["stats"]:
                if incidents_ok:
                    h, a = ev_counts[k]
                    stats["stats"][k] = {"home": h, "away": a}
                elif stat_ok:
                    stats["stats"][k] = {"home": 0, "away": 0}  # statistics geldi, alan yok = gerçekten 0
                else:
                    stats["stats"][k] = {"home": "?", "away": "?"}

        # DEĞİŞİKLİK — yalnızca lineups'tan doğrulanmış sayım; yoksa '?'
        if "substitutions" not in stats["stats"]:
            if subs_counts is not None:
                stats["stats"]["substitutions"] = {"home": subs_counts[0], "away": subs_counts[1]}
            else:
                stats["stats"]["substitutions"] = {"home": "?", "away": "?"}

    stats["available"] = bool(stats["sources"])
    if not stats["available"]:
        stats["message"] = "Bu maç için detaylı istatistik henüz yok."
    return stats


# ============== Match detail by slug ==============
@router.get("/by-slug/{slug:path}")
async def get_match_by_slug(slug: str):
    """Slug format: team1__team2__YYYYMMDD.
    Hem ham (Güney_Kore) hem percent-encoded (G%C3%BCney_Kore) gelir, ikisi de çözülür."""
    from urllib.parse import unquote
    try:
        decoded = unquote(slug)
        if "%" in decoded:
            try:
                decoded = unquote(decoded)
            except Exception:
                pass
    except Exception:
        decoded = slug
    parts = decoded.split("__")
    if len(parts) < 2:
        return {"available": False, "message": "Geçersiz slug"}
    home = parts[0].replace("_", " ").strip()
    away = parts[1].replace("_", " ").strip()
    date = parts[2] if len(parts) >= 3 else None
    return await get_match_stats(home=home, away=away, date=date)
