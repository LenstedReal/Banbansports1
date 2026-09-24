import rawIndex from './footyIndex.json';

const INDEX: Record<string, string> = rawIndex as Record<string, string>;
const BASE = '/footy/';

const STOP = new Set(['fc','fk','cf','sk','sc','sv','afc','cfc','ss','ssc','as','ac','us','ud','cd','rc','rcd','krc','kv','vfb','vfl','tsg','tsv','bsc','fsv','spvgg','club','1','if','bk','nk','gnk','hnk','pfc','sl','ca','ec','se','u18','u19','u21','u23','ii','b']);

// LiveScore / Türkçe isim düzeltmeleri (normalize edilmiş halleriyle)
const ALIAS: Record<string, string> = {
  'lyon': 'olympique lyonnais',
  'marseille': 'olympique de marseille om',
  'olympique marseille': 'olympique de marseille om',
  'psg': 'paris saint germain',
  'inter': 'inter milan',
  'istanbul basaksehir': 'basaksehir',
  'rizespor': 'caykur rizespor',
  'karagumruk': 'fatih karagumruk',
  'bayern munchen': 'bayern munich',
  'bayern munih': 'bayern munich',
  'fc bayern munchen': 'bayern munich',
  'wolves': 'wolverhampton wanderers',
  'man city': 'manchester city',
  'man utd': 'manchester united',
  'man united': 'manchester united',
  'turkiye': 'nt turkey',
  'ingiltere': 'nt england',
  'almanya': 'nt germany',
  'fransa': 'nt france',
  'italya': 'nt italy',
  'ispanya': 'nt spain',
  'hollanda': 'nt netherlands',
  'portekiz': 'nt portugal',
  'czechia': 'nt czech republic',
  'usa': 'nt united states',
  'ivory coast': 'nt cote divoire',
  // LiveScore kısa/Türkçe kulüp adları
  'newcastle': 'newcastle united',
  'psv': 'psv eindhoven',
  'real betis': 'real betis balompie',
  'sampdoria': 'uc sampdoria',
  'reims': 'stade de reims',
  'brest': 'stade brestois 29',
  'nice': 'ogc nice',
  'lille': 'losc lille',
  'auxerre': 'aj auxerre',
  'anderlecht': 'rsc anderlecht',
  'gent': 'kaa gent',
  'eibar': 'sd eibar',
  'ankaragucu': 'mke ankaragucu',
  'alcorcon': 'ad alcorcon',
  'cracovia': 'ks cracovia',
  'tolima': 'deportes tolima',
  'hearts': 'heart of midlothian',
  'marsilya': 'olympique de marseille om',
  'atl madrid': 'atletico madrid',
  'atletico de madrid': 'atletico madrid',
  'leverkusen': 'bayer leverkusen',
  'gladbach': 'borussia monchengladbach',
  'borussia m gladbach': 'borussia monchengladbach',
  'spurs': 'tottenham hotspur',
  'tottenham': 'tottenham hotspur',
  'west ham': 'west ham united',
  'leeds': 'leeds united',
  'nottm forest': 'nottingham forest',
  'sheffield utd': 'sheffield united',
  'basaksehir fk': 'basaksehir',
  'kasimpasa sk': 'kasimpasa',
  'goztepe sk': 'goztepe',
  'gaziantep fk': 'gaziantep',
};

// Anahtar listesi (ön-ek / son-ek eşleşmesi için) — bir kere kurulur
const KEYS = Object.keys(INDEX);
function fuzzy(n: string): string | null {
  if (n.length < 4) return null;
  // "newcastle" → "newcastle united" (tek/ilk aday)
  const pre = KEYS.filter((k) => k.startsWith(n + ' '));
  if (pre.length === 1) return INDEX[pre[0]];
  // "sampdoria" → "uc sampdoria" (kısaltma ön-ekli tek aday)
  const suf = KEYS.filter((k) => k.endsWith(' ' + n) && k.split(' ').length - n.split(' ').length <= 2);
  if (suf.length === 1) return INDEX[suf[0]];
  return null;
}

export function normName(s: string): string {
  return s
    .toLowerCase()
    .replace(/ı/g, 'i')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

const cache = new Map<string, string | null>();

function find(n: string): string | null {
  if (!n) return null;
  const direct = INDEX[ALIAS[n] || n] || INDEX['nt ' + n];
  if (direct) return direct;
  const toks = n.split(' ').filter((t) => !STOP.has(t));
  const base = toks.join(' ');
  if (base !== n) {
    const hit = INDEX[ALIAS[base] || base] || INDEX['nt ' + base];
    if (hit) return hit;
  }
  // son kelimeleri sırayla düşür (Chelsea U18 → Chelsea)
  for (let i = toks.length - 1; i >= 1; i--) {
    const k = toks.slice(0, i).join(' ');
    const hit = INDEX[ALIAS[k] || k];
    if (hit) return hit;
  }
  // baş kelimeleri düşür (Deportivo Alaves → Alaves)
  for (let i = 1; i < toks.length; i++) {
    const k = toks.slice(i).join(' ');
    const hit = INDEX[ALIAS[k] || k];
    if (hit) return hit;
  }
  // son çare: ön-ek / son-ek eşleşmesi (tek aday varsa)
  return fuzzy(n) || (base !== n ? fuzzy(base) : null);
}

export function teamLogo(name: string | undefined | null): string | null {
  if (!name || name === '—') return null;
  const key = name;
  if (cache.has(key)) return cache.get(key)!;
  const rel = find(normName(name));
  const url = rel ? BASE + rel : null;
  cache.set(key, url);
  return url;
}

// Lig etiketi (Türkçe/İngilizce) → lig logosu
const LEAGUE_LOGOS: [RegExp, string][] = [
  [/süper\s*lig|super\s*lig|trendyol/i, 'super-lig-turkey-logo-footylogos.svg'],
  [/şampiyonlar|champions league/i, 'uefa-champions-league-logo-footylogos.svg'],
  [/konferans|conference league/i, 'uefa-conference-league-logo-footylogos.svg'],
  [/avrupa ligi|europa league/i, 'europa-league-logo-footylogos.svg'],
  [/uluslar|nations league/i, 'uefa-nations-league-logo-footylogos.svg'],
  [/dünya kupasi|dünya kupası|world cup/i, 'fifa-world-cup-2026-logo-footylogos.svg'],
  [/premier league|premier lig|premıer/i, 'premier-league-england-logo-footylogos.svg'],
  [/laliga\s*2|hypermotion/i, 'laliga-2-spain-logo-footylogos.svg'],
  [/la\s*liga|laliga/i, 'laliga-spain-logo-footylogos.svg'],
  [/bundesliga\s*2/i, 'bundesliga-2-germany-logo-footylogos.svg'],
  [/bundesliga/i, 'bundesliga-germany-logo-footylogos.svg'],
  [/serie\s*b/i, 'serie-b-italy-logo-footylogos.svg'],
  [/serie\s*a/i, 'serie-a-italy-logo-footylogos.svg'],
  [/ligue\s*2/i, 'ligue-2-france-logo-footylogos.svg'],
  [/ligue\s*1/i, 'ligue-1-france-logo-footylogos.svg'],
  [/eredivisie/i, 'eredivisie-netherlands-logo-footylogos.svg'],
  [/primeira liga/i, 'primeira-liga-portugal-logo-footylogos.svg'],
  [/championship/i, 'efl-championship-england-logo-footylogos.svg'],
  [/1\.?\s*lig/i, '1-lig-turkey-logo-footylogos.svg'],
  [/mls/i, 'mls-logo-footylogos.svg'],
  [/saudi|arabistan/i, 'saudi-pro-league-logo-footylogos.svg'],
  [/scottish prem/i, 'scottish-premiership-logo-footylogos.svg'],
  [/fa cup/i, 'emirates-fa-cup-logo-footylogos.svg'],
  [/copa libertadores/i, 'copa-libertadores-logo-footylogos.svg'],
  [/liga mx/i, 'liga-mx-logo-footylogos.svg'],
];

export function leagueLogo(label: string | undefined | null): string | null {
  if (!label) return null;
  for (const [re, file] of LEAGUE_LOGOS) {
    if (re.test(label)) return BASE + 'leagues/' + file;
  }
  return null;
}
