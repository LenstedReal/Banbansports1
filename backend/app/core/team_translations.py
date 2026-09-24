"""Turkish team & country name translations for international fixtures.

Used by livescore.py to localize the English team names returned by upstream
sources (LiveScore.com, FotMob, SofaScore). Falls back to the original name
if no mapping exists — so missing entries never break the response.

Coverage focus:
  • Every FIFA member national team (Türkiye + top 80 countries)
  • Major European clubs (the only league names users browse internationally)
  • All World Cup 2026 / Euro 2028 / Nations League participants

Add new entries here only
everything else is data-driven.
"""

# --- National teams (English → Turkish) -------------------------------------
NATIONAL_TEAMS_TR = {
    # UEFA / Europe
    "Turkey": "Türkiye",
    "Türkiye": "Türkiye",
    "Turkiye": "Türkiye",
    "Germany": "Almanya",
    "France": "Fransa",
    "Spain": "İspanya",
    "Italy": "İtalya",
    "England": "İngiltere",
    "Netherlands": "Hollanda",
    "Portugal": "Portekiz",
    "Belgium": "Belçika",
    "Croatia": "Hırvatistan",
    "Switzerland": "İsviçre",
    "Austria": "Avusturya",
    "Poland": "Polonya",
    "Czech Republic": "Çek Cumhuriyeti",
    "Czechia": "Çekya",
    "Denmark": "Danimarka",
    "Sweden": "İsveç",
    "Norway": "Norveç",
    "Finland": "Finlandiya",
    "Iceland": "İzlanda",
    "Ireland": "İrlanda",
    "Northern Ireland": "Kuzey İrlanda",
    "Wales": "Galler",
    "Scotland": "İskoçya",
    "Hungary": "Macaristan",
    "Romania": "Romanya",
    "Bulgaria": "Bulgaristan",
    "Serbia": "Sırbistan",
    "Slovenia": "Slovenya",
    "Slovakia": "Slovakya",
    "Greece": "Yunanistan",
    "Ukraine": "Ukrayna",
    "Russia": "Rusya",
    "Belarus": "Belarus",
    "Bosnia and Herzegovina": "Bosna Hersek",
    "Bosnia & Herzegovina": "Bosna Hersek",
    "Albania": "Arnavutluk",
    "North Macedonia": "Kuzey Makedonya",
    "Montenegro": "Karadağ",
    "Kosovo": "Kosova",
    "Moldova": "Moldova",
    "Lithuania": "Litvanya",
    "Latvia": "Letonya",
    "Estonia": "Estonya",
    "Georgia": "Gürcistan",
    "Armenia": "Ermenistan",
    "Azerbaijan": "Azerbaycan",
    "Cyprus": "Kıbrıs",
    "Malta": "Malta",
    "Luxembourg": "Lüksemburg",
    "Andorra": "Andorra",
    "San Marino": "San Marino",
    "Liechtenstein": "Lihtenştayn",
    "Faroe Islands": "Faroe Adaları",
    "Gibraltar": "Cebelitarık",
    "Kazakhstan": "Kazakistan",

    # CONMEBOL / South America
    "Brazil": "Brezilya",
    "Argentina": "Arjantin",
    "Uruguay": "Uruguay",
    "Colombia": "Kolombiya",
    "Chile": "Şili",
    "Peru": "Peru",
    "Ecuador": "Ekvador",
    "Paraguay": "Paraguay",
    "Venezuela": "Venezuela",
    "Bolivia": "Bolivya",

    # CONCACAF / North & Central America
    "USA": "ABD",
    "United States": "ABD",
    "Canada": "Kanada",
    "Mexico": "Meksika",
    "Costa Rica": "Kosta Rika",
    "Honduras": "Honduras",
    "Panama": "Panama",
    "Jamaica": "Jamaika",
    "El Salvador": "El Salvador",
    "Guatemala": "Guatemala",
    "Trinidad and Tobago": "Trinidad ve Tobago",
    "Haiti": "Haiti",
    "Cuba": "Küba",
    "Curaçao": "Curaçao",
    "Curacao": "Curaçao",

    # CAF / Africa
    "Morocco": "Fas",
    "Senegal": "Senegal",
    "Algeria": "Cezayir",
    "Tunisia": "Tunus",
    "Egypt": "Mısır",
    "Nigeria": "Nijerya",
    "Ghana": "Gana",
    "Cameroon": "Kamerun",
    "Ivory Coast": "Fildişi Sahili",
    "Côte d'Ivoire": "Fildişi Sahili",
    "South Africa": "Güney Afrika",
    "Mali": "Mali",
    "Burkina Faso": "Burkina Faso",
    "Cape Verde": "Yeşil Burun",
    "Guinea": "Gine",
    "DR Congo": "Demokratik Kongo Cumhuriyeti",
    "Democratic Republic of Congo": "Demokratik Kongo Cumhuriyeti",
    "Congo": "Kongo",
    "Angola": "Angola",
    "Zambia": "Zambiya",
    "Zimbabwe": "Zimbabve",
    "Kenya": "Kenya",
    "Ethiopia": "Etiyopya",
    "Sudan": "Sudan",
    "Libya": "Libya",
    "Equatorial Guinea": "Ekvator Ginesi",
    "Gabon": "Gabon",
    "Mauritania": "Moritanya",
    "Madagascar": "Madagaskar",
    "Mozambique": "Mozambik",
    "Tanzania": "Tanzanya",
    "Uganda": "Uganda",
    "Comoros": "Komorlar",

    # AFC / Asia
    "Japan": "Japonya",
    "South Korea": "Güney Kore",
    "Korea Republic": "Güney Kore",
    "North Korea": "Kuzey Kore",
    "Korea DPR": "Kuzey Kore",
    "Iran": "İran",
    "Iraq": "Irak",
    "Saudi Arabia": "Suudi Arabistan",
    "Qatar": "Katar",
    "United Arab Emirates": "Birleşik Arap Emirlikleri",
    "UAE": "BAE",
    "Kuwait": "Kuveyt",
    "Bahrain": "Bahreyn",
    "Oman": "Umman",
    "Yemen": "Yemen",
    "Jordan": "Ürdün",
    "Lebanon": "Lübnan",
    "Syria": "Suriye",
    "Palestine": "Filistin",
    "Israel": "İsrail",
    "China": "Çin",
    "China PR": "Çin",
    "Australia": "Avustralya",
    "Indonesia": "Endonezya",
    "Vietnam": "Vietnam",
    "Thailand": "Tayland",
    "Malaysia": "Malezya",
    "Philippines": "Filipinler",
    "Singapore": "Singapur",
    "India": "Hindistan",
    "Pakistan": "Pakistan",
    "Bangladesh": "Bangladeş",
    "Afghanistan": "Afganistan",
    "Uzbekistan": "Özbekistan",
    "Tajikistan": "Tacikistan",
    "Turkmenistan": "Türkmenistan",
    "Kyrgyzstan": "Kırgızistan",

    # OFC / Oceania
    "New Zealand": "Yeni Zelanda",
    "Fiji": "Fiji",
    "Solomon Islands": "Solomon Adaları",
    "Tahiti": "Tahiti",
    "Papua New Guinea": "Papua Yeni Gine",
}


# --- Major clubs (only popular Turkish-broadcast leagues) -------------------
CLUBS_TR = {
    # Turkish Super League (already TR in upstream, but normalize)
    "Galatasaray": "Galatasaray",
    "Fenerbahce": "Fenerbahçe",
    "Fenerbahçe": "Fenerbahçe",
    "Besiktas": "Beşiktaş",
    "Beşiktaş": "Beşiktaş",
    "Trabzonspor": "Trabzonspor",
    "Istanbul Basaksehir": "İstanbul Başakşehir",
    "Adana Demirspor": "Adana Demirspor",
    "Konyaspor": "Konyaspor",
    "Sivasspor": "Sivasspor",
    "Antalyaspor": "Antalyaspor",
    "Goztepe": "Göztepe",
    "Gaziantep": "Gaziantep FK",
    "Alanyaspor": "Alanyaspor",
    "Rizespor": "Çaykur Rizespor",
    "Kasimpasa": "Kasımpaşa",
    "Eyupspor": "Eyüpspor",
    "Bodrum": "Bodrum FK",
    "Hatayspor": "Hatayspor",
    "Samsunspor": "Samsunspor",
    "Kayserispor": "Kayserispor",

    # Premier League (top 10)
    "Manchester City": "Manchester City",
    "Manchester United": "Manchester United",
    "Liverpool": "Liverpool",
    "Chelsea": "Chelsea",
    "Arsenal": "Arsenal",
    "Tottenham": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "Newcastle": "Newcastle",
    "Newcastle United": "Newcastle",
    "Aston Villa": "Aston Villa",

    # La Liga
    "Real Madrid": "Real Madrid",
    "Barcelona": "Barcelona",
    "Atletico Madrid": "Atlético Madrid",
    "Athletic Bilbao": "Athletic Bilbao",
    "Athletic Club": "Athletic Bilbao",
    "Sevilla": "Sevilla",
    "Real Sociedad": "Real Sociedad",
    "Villarreal": "Villarreal",
    "Real Betis": "Real Betis",
    "Valencia": "Valencia",

    # Serie A
    "Inter": "Inter",
    "Inter Milan": "Inter",
    "AC Milan": "AC Milan",
    "Milan": "AC Milan",
    "Juventus": "Juventus",
    "Napoli": "Napoli",
    "Roma": "Roma",
    "AS Roma": "Roma",
    "Lazio": "Lazio",
    "Atalanta": "Atalanta",
    "Fiorentina": "Fiorentina",
    "Bologna": "Bologna",

    # Bundesliga
    "Bayern Munich": "Bayern Münih",
    "Bayern München": "Bayern Münih",
    "Bayern": "Bayern Münih",
    "Borussia Dortmund": "Borussia Dortmund",
    "Dortmund": "Borussia Dortmund",
    "RB Leipzig": "RB Leipzig",
    "Bayer Leverkusen": "Bayer Leverkusen",
    "Leverkusen": "Bayer Leverkusen",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "Stuttgart": "Stuttgart",

    # Ligue 1
    "Paris Saint-Germain": "Paris Saint-Germain",
    "PSG": "PSG",
    "Marseille": "Marsilya",
    "Lyon": "Lyon",
    "Monaco": "Monaco",
    "Lille": "Lille",
    "Nice": "Nice",
    "Rennes": "Rennes",

    # Other Europe
    "Ajax": "Ajax",
    "PSV": "PSV",
    "PSV Eindhoven": "PSV",
    "Feyenoord": "Feyenoord",
    "Porto": "Porto",
    "FC Porto": "Porto",
    "Benfica": "Benfica",
    "Sporting": "Sporting CP",
    "Sporting CP": "Sporting CP",
    "Celtic": "Celtic",
    "Rangers": "Rangers",
}


def tr_team_name(name: str) -> str:
    """Return Turkish team/country name, or original if no mapping exists.

    Performs exact match first, then case-insensitive fallback.
    Never returns None — always safe to use as drop-in for display.
    """
    if not name:
        return name
    s = str(name).strip()
    if s in NATIONAL_TEAMS_TR:
        return NATIONAL_TEAMS_TR[s]
    if s in CLUBS_TR:
        return CLUBS_TR[s]
    # case-insensitive fallback
    sl = s.lower()
    for k, v in NATIONAL_TEAMS_TR.items():
        if k.lower() == sl:
            return v
    for k, v in CLUBS_TR.items():
        if k.lower() == sl:
            return v
    return s


def tr_to_en_candidates(tr_name: str) -> list:
    """Reverse lookup: given Turkish name, return likely English originals.

    Used by match-stats endpoint so the frontend can pass Turkish team names
    (post-display translation) and still match upstream English data.
    """
    if not tr_name:
        return []
    s = str(tr_name).strip()
    out = [s]  # always try original first
    # case-insensitive reverse from both maps
    sl = s.lower()
    for k, v in NATIONAL_TEAMS_TR.items():
        if v.lower() == sl and k not in out:
            out.append(k)
    for k, v in CLUBS_TR.items():
        if v.lower() == sl and k not in out:
            out.append(k)
    return out
