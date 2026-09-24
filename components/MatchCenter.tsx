'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { getClient } from '@/lib/api';
import { TR, trLeagueName } from '@/lib/i18n';
import { isKnownTeam } from '@/lib/knownTeams';
import TeamLogo from './TeamLogo';
import { leagueLogo } from '@/lib/footy';

type Event = {
  Eid?: any;
  T1?: { Nm?: string }[];
  T2?: { Nm?: string }[];
  Tr1?: number; Tr2?: number;
  Eps?: string; Esd?: any;
  Trp1?: number; Trp2?: number;
};
type Stage = { Cnm?: string; Snm?: string; Events?: Event[] };

// === LİG FİLTRELERİ ===
const isTRSuperLig = (s: Stage) => /turk/i.test(s.Cnm || '') && /(süper|super)\s*lig/i.test(s.Snm || '');
const isTRCup      = (s: Stage) => /turk/i.test(s.Cnm || '') && /(cup|kupa)/i.test(s.Snm || '');
// UEFA-dışı konfederasyon kupaları (OFC/CAF/AFC/CONCACAF Champions League) UEFA sayılmaz
const isNonUefaConfed = (c: string) => /(ofc|caf|afc|concacaf)\s+(champions|confederation|cup)|oceania/i.test(c);
const isUCL        = (s: Stage) => /(uefa\s)?champions league/i.test(s.Snm || '') && !/youth|women/i.test(s.Snm || '') && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);
const isUEL        = (s: Stage) => /(uefa\s)?europa league/i.test(s.Snm || '') && !/conference|women/i.test(s.Snm || '') && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);
const isUECL       = (s: Stage) => /conference league/i.test(s.Snm || '') && !/women/i.test(s.Snm || '') && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);
const isPremier    = (s: Stage) => /england/i.test(s.Cnm || '') && /^premier league/i.test((s.Snm || '').trim());
const isLaLiga     = (s: Stage) => /spain/i.test(s.Cnm || '') && /^la\s?liga/i.test((s.Snm || '').trim()) && !/laliga\s*2|hypermotion/i.test(s.Snm || '');
const isBundesliga = (s: Stage) => /germany/i.test(s.Cnm || '') && /^bundesliga(?!\s*2|\s*[23])/i.test((s.Snm || '').trim());
const isSerieA     = (s: Stage) => /italy/i.test(s.Cnm || '') && /^serie a/i.test((s.Snm || '').trim());
const isLigue1     = (s: Stage) => /france/i.test(s.Cnm || '') && /^ligue 1/i.test((s.Snm || '').trim());
const isWorldCup   = (s: Stage) => {
  const combined = `${s.Cnm || ''} ${s.Snm || ''}`;
  return /(world cup|fifa world cup|wc qualif|world cup qualif)/i.test(combined) && !/women|u17|u19|u21/i.test(combined);
};
const isEuro       = (s: Stage) => {
  const combined = `${s.Cnm || ''} ${s.Snm || ''}`;
  return /(european championship|euro 20\d{2}|euro qualif|uefa euro)/i.test(combined) && !/women|u17|u19|u21/i.test(combined);
};
const isNations    = (s: Stage) => {
  const combined = `${s.Cnm || ''} ${s.Snm || ''}`;
  return /(uefa nations|nations league)/i.test(combined) && !/women|u17|u19|u21/i.test(combined);
};
const isFriendly   = (s: Stage) => {
  const combined = `${s.Cnm || ''} ${s.Snm || ''}`;
  return /(friendl(y|ies)|hazırlık|summer series|pre-?season|yaz serisi|emirates cup)/i.test(combined) && !/women|u17|u19|u21/i.test(combined);
};
const isMilli      = (s: Stage) => {
  // National team matches — includes World Cup, Euro, Nations League, NT Friendly
  // Fix: kulüp hazırlık maçları (Club Friendlies) MİLLİ MAÇ sayılmaz
  const isNTFriendly = isFriendly(s) && !/club/i.test(`${s.Cnm || ''} ${s.Snm || ''}`);
  return isWorldCup(s) || isEuro(s) || isNations(s) || isNTFriendly;
};
const isUCL2       = (s: Stage) => /champions league/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !/youth|women/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);
const isUEL2       = (s: Stage) => /europa league/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !/conference|women/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);
const isUECL2      = (s: Stage) => /conference league/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !/women/i.test(`${s.Cnm || ''} ${s.Snm || ''}`) && !isNonUefaConfed(`${s.Cnm || ''} ${s.Snm || ''}`);

// Büyük Türk kulüpleri — UEFA elemelerinde bunlar oynarsa maç KALIR, ufak kulüpler ELENİR.
const BIG_CLUB_RE = /(galatasaray|fenerbah[cç]e|be[sş]ikta[sş]|trabzonspor)/i;
// UEFA KULÜP kupalarının ELEME/ön eleme turları (KuPS, TNS, Riga gibi ufak kulüpler buradan geliyordu)
const isUefaClubQualifier = (s: Stage) => {
  const c = `${s.Cnm || ''} ${s.Snm || ''}`;
  return (isUCL2(s) || isUEL2(s) || isUECL2(s)) &&
    /(qualif|preliminary|prelim|1st round|2nd round|3rd round|play[\s-]?off)/i.test(c);
};

const ALL_MAJOR = (s: Stage) =>
  isTRSuperLig(s) || isTRCup(s) || isUCL(s) || isUEL(s) || isUECL(s) ||
  isUCL2(s) || isUEL2(s) || isUECL2(s) ||
  isPremier(s) || isLaLiga(s) || isBundesliga(s) || isSerieA(s) || isLigue1(s) ||
  isWorldCup(s) || isEuro(s) || isNations(s) || isFriendly(s);

export const FILTERS: { id: string; label: string; img?: string; test: (s: Stage) => boolean }[] = [
  { id: 'all',    label: TR.ALL,            test: ALL_MAJOR },
  { id: 'tr',     label: 'SÜPER LİG',       img: '/footy/leagues/super-lig-turkey-logo-footylogos.svg', test: isTRSuperLig },
  { id: 'milli',  label: 'MİLLİ MAÇ',       test: isMilli },
  { id: 'wc',     label: 'DÜNYA KUPASI',    img: '/footy/leagues/fifa-world-cup-2026-logo-footylogos.svg', test: isWorldCup },
  { id: 'euro',   label: 'AVRUPA ŞAMP.',    test: isEuro },
  { id: 'fr',     label: 'HAZIRLIK',        test: isFriendly },
  { id: 'ucl',    label: 'ŞAMPİYONLAR LİGİ', img: '/footy/leagues/uefa-champions-league-logo-footylogos.svg', test: isUCL },
  { id: 'uel',    label: 'AVRUPA LİGİ',     img: '/footy/leagues/europa-league-logo-footylogos.svg', test: isUEL },
  { id: 'uecl',   label: 'KONFERANS LİGİ',  img: '/footy/leagues/uefa-conference-league-logo-footylogos.svg', test: isUECL },
  { id: 'pl',     label: 'PREMİER LİG',     img: '/footy/leagues/premier-league-england-logo-footylogos.svg', test: isPremier },
  { id: 'laliga', label: 'LA LİGA',         img: '/footy/leagues/laliga-spain-logo-footylogos.svg', test: isLaLiga },
  { id: 'bun',    label: 'BUNDESLIGA',      img: '/footy/leagues/bundesliga-germany-logo-footylogos.svg', test: isBundesliga },
  { id: 'seriea', label: 'SERİE A',         img: '/footy/leagues/serie-a-italy-logo-footylogos.svg', test: isSerieA },
  { id: 'l1',     label: 'LIGUE 1',         img: '/footy/leagues/ligue-1-france-logo-footylogos.svg', test: isLigue1 },
];

const epsToLabel = (e: Event) => {
  const eps = (e.Eps || '').toString();
  if (eps === '1H') return { txt: TR.FIRST_HALF, live: true, finished: false, notStarted: false };
  if (eps === '2H') return { txt: TR.SECOND_HALF, live: true, finished: false, notStarted: false };
  if (eps === 'HT') return { txt: TR.HALF_TIME, live: true, finished: false, notStarted: false };
  if (eps === 'ET') return { txt: TR.EXTRA_TIME, live: true, finished: false, notStarted: false };
  if (eps === 'PEN') return { txt: TR.PENALTIES, live: true, finished: false, notStarted: false };
  if (['FT', 'AET', 'AP', 'Pen.'].includes(eps)) return { txt: TR.MATCH_ENDED, live: false, finished: true, notStarted: false };
  if (eps === 'NS' || eps === 'Not Started') {
    // ESD = UTC YYYYMMDDhhmm — İstanbul saatine (+3) TAM datetime olarak çevir,
    // gün taşmasını hesapla; maç bugün değilse "GG.AA SS:DD" olarak göster
    const esd = String(e.Esd || '');
    if (esd.length >= 12 && /^\d+$/.test(esd.slice(0, 12))) {
      const Y = parseInt(esd.slice(0, 4), 10);
      const Mo = parseInt(esd.slice(4, 6), 10);
      const D = parseInt(esd.slice(6, 8), 10);
      const h = parseInt(esd.slice(8, 10), 10);
      const m = esd.slice(10, 12);
      if (!isNaN(h) && !isNaN(Y)) {
        const ist = new Date(Date.UTC(Y, Mo - 1, D, h, parseInt(m, 10) || 0) + 3 * 3600 * 1000);
        const hh = String(ist.getUTCHours()).padStart(2, '0');
        const mm = String(ist.getUTCMinutes()).padStart(2, '0');
        const nowIst = new Date(Date.now() + 3 * 3600 * 1000);
        const sameDay = ist.getUTCFullYear() === nowIst.getUTCFullYear()
          && ist.getUTCMonth() === nowIst.getUTCMonth()
          && ist.getUTCDate() === nowIst.getUTCDate();
        const dayPrefix = sameDay ? '' : `${String(ist.getUTCDate()).padStart(2, '0')}.${String(ist.getUTCMonth() + 1).padStart(2, '0')} `;
        return { txt: `${dayPrefix}${hh}:${mm}`, live: false, finished: false, notStarted: true };
      }
    }
    return { txt: TR.NOT_STARTED, live: false, finished: false, notStarted: true };
  }
  // Dakika formatı ("40'", "90+3'") → canlı maç
  if (/^\d+(\+\d+)?'?$/.test(eps)) return { txt: eps.endsWith("'") ? eps : `${eps}'`, live: true, finished: false, notStarted: false };
  // İngilizce durum kodları → Türkçe
  const EN_STATUS: Record<string, string> = {
    'POSTP': 'ERTELENDİ', 'POSTP.': 'ERTELENDİ', 'POSTPONED': 'ERTELENDİ',
    'CANC': 'İPTAL', 'CANC.': 'İPTAL', 'CANCELLED': 'İPTAL', 'CANCELED': 'İPTAL',
    'AW': 'HÜKMEN', 'AWARDED': 'HÜKMEN',
    'SUSP': 'ASKIDA', 'SUSP.': 'ASKIDA', 'SUSPENDED': 'ASKIDA',
    'INT': 'DURDURULDU', 'INT.': 'DURDURULDU', 'INTERRUPTED': 'DURDURULDU',
    'ABAND': 'YARIDA KALDI', 'ABAND.': 'YARIDA KALDI', 'ABANDONED': 'YARIDA KALDI',
    'DELAYED': 'GECİKMELİ', 'DEL.': 'GECİKMELİ',
    'TBA': 'BELİRLENECEK', 'TBD': 'BELİRLENECEK',
    'BREAK': 'ARA', 'BREAK TIME': 'ARA',
  };
  const tr = EN_STATUS[eps.toUpperCase()];
  if (tr) return { txt: tr, live: false, finished: false, notStarted: false };
  return { txt: eps || '—', live: false, finished: false, notStarted: false };
};

export default function MatchCenter({ initialStages }: { initialStages: Stage[] }) {
  const [stages, setStages] = useState<Stage[]>(initialStages);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  // Sol kolon kompakt liste — başlangıçta 8, "TÜM MAÇLARI GÖR" ile artar
  const [visibleCount, setVisibleCount] = useState(6);
  // Filter değişince visibleCount sıfırla — kullanıcı farklı lige geçtiğinde başa dön
  useEffect(() => { setVisibleCount(6); }, [filter]);
  // Lig şeridi (LeagueStrip) tıklamaları — bb:set-filter event'i
  useEffect(() => {
    const onSet = (e: Event) => {
      const id = (e as CustomEvent)?.detail?.id;
      if (id && FILTERS.some((f) => f.id === id)) setFilter(id);
    };
    window.addEventListener('bb:set-filter', onSet as EventListener);
    return () => window.removeEventListener('bb:set-filter', onSet as EventListener);
  }, []);
  const stagesRef = useRef<Stage[]>(initialStages);
  // Sayfa (page.tsx) veriyi sonradan getirirse state'e yansıt
  useEffect(() => {
    if (initialStages && initialStages.length) { stagesRef.current = initialStages; setStages(initialStages); }
  }, [initialStages]);

  // Mount-once polling — stages değişimi effect'i tetiklemez. Canlı maç varsa 30s, yoksa 60s.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (!alive) return;
      try {
        setLoading(true);
        const d = await getClient<{ Stages?: Stage[] }>('/api/livescore/today');
        if (!alive) return;
        if (d?.Stages) {
          stagesRef.current = d.Stages;
          setStages(d.Stages);
        }
      } finally {
        if (alive) {
          setLoading(false);
          const anyLive = stagesRef.current.some((s) => (s.Events || []).some((e) => ['1H', '2H', 'HT', 'ET', 'PEN'].includes(e.Eps || '')));
          timer = setTimeout(tick, anyLive ? 30_000 : 60_000);
        }
      }
    };
    // İlk fetch hemen (initialStages boş gelirse skoreboard hızlı dolar)
    // P3 #91: 3 component aynı endpoint'i 500ms'de çekiyordu → IP-ban riski.
    // Stagger: Scoreboard 500ms, MatchCenter 900ms (farklı endpoint zaten), MatchBanner anlık.
    const firstDelay = initialStages.length === 0 ? 900 : 30_000;
    timer = setTimeout(tick, firstDelay);
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, []);

  const cleaned = useMemo(() => stages.filter(ALL_MAJOR), [stages]);
  const visible = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter) || FILTERS[0];
    if (filter === 'all') {
      const order = [isTRSuperLig, isWorldCup, isEuro, isNations, isFriendly, isUCL, isUEL, isUECL, isTRCup, isPremier, isLaLiga, isBundesliga, isSerieA, isLigue1];
      return [...cleaned].sort((a, b) => {
        const ai = order.findIndex((t) => t(a));
        const bi = order.findIndex((t) => t(b));
        return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
      });
    }
    return cleaned.filter(f.test);
  }, [cleaned, filter]);

  const flatMatches = useMemo(() => {
    const out: { home: string; away: string; league: string; status: string; live: boolean; finished: boolean; notStarted: boolean; score1: number; score2: number; pen1?: number | null; pen2?: number | null; slug: string }[] = [];
    // Preserve Turkish/unicode letters in slug (only collapse whitespace and special punctuation to _)
    const cleanName = (s: string) => s.replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '');
    // Smart league label: "Group A/B/C/D" gibi grup adlarını ana turnuvaya çevir
    const smartLeague = (s: Stage): string => {
      const snm = (s.Snm || '').trim();
      const cnm = (s.Cnm || '').trim();
      const combined = `${cnm} ${snm}`;
      const tournament = (): string => {
        if (/world cup|wc|dünya/i.test(combined)) return 'DÜNYA KUPASI';
        if (/euro|european championship/i.test(combined)) return 'AVRUPA ŞAMP.';
        if (/champions league/i.test(combined)) return 'ŞAMPİYONLAR LİGİ';
        if (/europa league/i.test(combined)) return 'AVRUPA LİGİ';
        if (/conference league/i.test(combined)) return 'KONFERANS LİGİ';
        if (/nations league/i.test(combined)) return 'ULUSLAR LİGİ';
        if (/africa|afcon/i.test(combined)) return 'AFRİKA KUPASI';
        if (/asia|afc/i.test(combined)) return 'ASYA KUPASI';
        if (/copa america/i.test(combined)) return 'COPA AMERİKA';
        return '';
      };
      // Grup adı (Group A, Grup B, Hazırlık Grubu...) → ana turnuvaya çevir
      const isGroup = /^(group|grup|gr\.?)\s*[a-z]\d*$/i.test(snm) || /^(group|grup)\s*[a-z]/i.test(snm);
      if (isGroup) {
        const t = tournament();
        if (t) return t;
        // Genel fallback: ülke + "GRUP"
        if (cnm) return cnm.toUpperCase();
      }
      // Aşama adı (Third Place Play-Off, Final, Semi-finals...) → "TURNUVA · AŞAMA"
      if (/^(third[\s-]?place|3rd[\s-]?place|finals?$|semi|quarter|round of|knockout|play[\s-]?offs?$)/i.test(snm)) {
        const t = tournament();
        const stage = trLeagueName(snm);
        return t ? `${t} · ${stage}` : stage;
      }
      // "International" + boş → HAZIRLIK
      if (/international/i.test(cnm) && (/friendl(y|ies)|exhibition/i.test(snm) || !snm)) return 'HAZIRLIK';
      // "Club Friendly / Club Friendlies" → HAZIRLIK
      if (/friendl(y|ies)/i.test(snm)) return 'HAZIRLIK';
      // Standart liga adı — İngilizce aşama kalıplarını Türkçe'ye çevir
      return trLeagueName(snm || cnm) || 'FUTBOL';
    };
    visible.forEach((s) => {
      const qualifierStage = isUefaClubQualifier(s);
      const friendlyStage = isFriendly(s);
      (s.Events || []).forEach((e) => {
        const t1 = e.T1?.[0]?.Nm || '—';
        const t2 = e.T2?.[0]?.Nm || '—';
        // Çöp filtresi: UEFA kulüp elemesi ise SADECE büyük Türk kulübü olan maçları göster
        if (qualifierStage && !(BIG_CLUB_RE.test(t1) || BIG_CLUB_RE.test(t2))) return;
        // Hazırlık süzgeci (UEFA-eleme ile aynı desen): milli takım veya
        // team_translations.py'de tanımlı takım yoksa kart gösterilmez.
        if (friendlyStage && !(isKnownTeam(t1) || isKnownTeam(t2))) return;
        const ep = epsToLabel(e);
        const esd = String(e.Esd || '');
        const date = esd.length >= 8 ? esd.slice(0, 8) : '';
        const slug = `${cleanName(t1)}__${cleanName(t2)}${date ? '__' + date : ''}`;
        out.push({
          home: t1, away: t2,
          league: smartLeague(s),
          status: ep.txt, live: ep.live, finished: ep.finished, notStarted: ep.notStarted,
          score1: ep.notStarted ? -1 : (e.Tr1 ?? 0),
          score2: ep.notStarted ? -1 : (e.Tr2 ?? 0),
          pen1: e.Trp1 ?? null, pen2: e.Trp2 ?? null,
          slug,
        });
      });
    });
    return out;
  }, [visible]);

  // Kullanıcının seçtiği filtre için bağlama özel mesaj
  const emptyMessage = filter === 'all' ? TR.NO_MATCHES_TODAY : TR.NO_MATCHES_FILTER;

  return (
    <div className="pnl" data-testid="match-center">
      <div className="pnl-head">
        <span className="pnl-title t-pink">{TR.MATCH_CENTER}</span>
        {loading && <span style={{ fontSize: 10, color: 'var(--ink-low)', letterSpacing: 2 }}>&#8635;</span>}
      </div>
      <div className="mc2-filters" data-testid="league-filter">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`mc2-filter ${filter === f.id ? 'active' : ''}`}
            data-testid={`filter-${f.id}`}
          >
            {f.img
              ? <img src={`${f.img}?v=2`} alt={f.label} />
              : <span className="mc2-filter-dot" aria-hidden />}
            <span>{f.label}</span>
          </button>
        ))}
      </div>
      <div className="mc2-sub">YAKLAŞAN MAÇLAR</div>
      <div className="mc2-list" data-testid="matches-grid">
        {flatMatches.length === 0 ? (
          <div className="mc2-empty" data-testid="matches-empty">
            <div style={{ fontSize: 28, marginBottom: 8 }} aria-hidden>⚽</div>
            {emptyMessage}
          </div>
        ) : flatMatches.slice(0, visibleCount).map((m, i) => (
          <Link
            key={`${m.home}-${m.away}-${i}`}
            href={`/match/${m.slug}`}
            className={`mc2-card ${m.live ? 'is-live' : ''}`}
            data-testid={`match-row-${i}`}
            title="Maç detayı"
          >
            <div className="mc2-top">
              <span className="mc2-league">
                {leagueLogo(m.league) && <img src={`${leagueLogo(m.league)!}?v=2`} alt="" aria-hidden="true" loading="lazy" />}
                <span>{m.league.toUpperCase()}</span>
              </span>
              <span className="mc2-detay" data-testid={`match-detail-link-${i}`}>DETAY</span>
            </div>
            <div className="mc2-row">
              <div className="mc2-side home">
                <TeamLogo name={m.home} size={20} />
                <span className="mc2-name">{m.home}</span>
              </div>
              <div className="mc2-mid">
                {m.notStarted
                  ? <span className="mc2-vs">VS</span>
                  : <span className="mc2-scoreline">{m.score1} - {m.score2}</span>}
                {(m.pen1 !== null && m.pen1 !== undefined) && (
                  <span className="mc2-pen">PEN {m.pen1}-{m.pen2}</span>
                )}
              </div>
              <div className="mc2-side away">
                <span className="mc2-name">{m.away}</span>
                <TeamLogo name={m.away} size={20} />
              </div>
            </div>
            <div className="mc2-bottom">
              <span className={`mc2-time ${m.live ? 'is-live' : m.finished ? 'is-fin' : ''}`}>
                {m.live && <span className="mc2-livedot" />}
                {m.status}
              </span>
            </div>
          </Link>
        ))}
      </div>
      {flatMatches.length > visibleCount && (
        <div className="mc2-more">
          <button
            type="button"
            onClick={() => setVisibleCount((c) => c + 16)}
            data-testid="matches-show-more"
            className="btn-neon"
          >
            TÜM MAÇLARI GÖR ({flatMatches.length - visibleCount})
          </button>
        </div>
      )}
    </div>
  );
}
