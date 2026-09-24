'use client';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getClient } from '@/lib/api';
import { useAuth } from './AuthProvider';
import { TR, STAT_LABEL, STAT_ORDER, isPreMatchStatus } from '@/lib/i18n';
import AIPrediction from './AIPrediction';
import TeamLogo from './TeamLogo';

type Ev = { minute: number; type: 'goal' | 'yellow' | 'red' | 'sub'; label: string; team: 'home' | 'away'; player: string; assist?: string };
type Stats = {
  available: boolean;
  home: string; away: string;
  league?: string;
  score?: { home: number; away: number; pen_home?: number | null; pen_away?: number | null };
  venue?: string;
  events: Ev[];
  stats: Record<string, { home: string | number; away: string | number }>;
  message?: string;
  sources?: string[];
  eps?: string;
  start_date?: string | number;
};

type MyPrediction = {
  score1: number;
  score2: number;
  final_score: [number, number] | null;
  settled: boolean;
  points: number;
  submitted_at: string;
};

const EVENT_ICON: Record<string, string> = {
  goal: '/icons/goal.png',
  yellow: '/icons/yellowcard.png',
  red: '/icons/redcard.png',
  sub: '/icons/info.png',
};

const toNum = (v: string | number | null | undefined): number => {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'number') return v;
  const n = parseFloat(String(v).replace('%', ''));
  return isNaN(n) ? 0 : n;
};

export default function MatchStatsModal({ home, away, onClose }: { home: string; away: string; onClose: () => void }) {
  const { user } = useAuth();
  const [data, setData] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [myPred, setMyPred] = useState<MyPrediction | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const dataRef = { current: null as Stats | null };
    const fetchStats = async () => {
      const d = await getClient<Stats>(`/api/match/stats?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`);
      if (alive) {
        dataRef.current = d;
        setData(d);
        setLoading(false);
      }
    };
    const fetchMyPred = async () => {
      if (!user) { setMyPred(null); return; }
      // Tahminim getir (deprecated route artık dead kod değil — login varsa kullanılır)
      const r = await getClient<{ items: any[] }>(`/api/predictions/me`);
      if (alive && r?.items) {
        const match = r.items.find((p) =>
          p.team1?.toLowerCase() === home.toLowerCase() &&
          p.team2?.toLowerCase() === away.toLowerCase()
        );
        if (match) setMyPred(match as MyPrediction);
        else setMyPred(null);
      }
    };
    fetchStats();
    fetchMyPred();
    const tick = () => {
      // dataRef üzerinden canlı kontrol — stale closure fix
      const cur = dataRef.current;
      const live = !!(cur && cur.eps && ['1H', '2H', 'HT', 'ET', 'PEN'].includes(cur.eps));
      // User talebi: canlı maçta anlık güncelleme. 15sn → 10sn (her gol/kart 10sn içinde modal'a düşer).
      // Backend stats endpoint zaten LRU benzeri 5dk cache'liyor, ekstra yük yok.
      timer = setTimeout(async () => {
        if (!alive) return;
        await fetchStats();
        await fetchMyPred();
        if (alive) tick();
      }, live ? 10_000 : 60_000);
    };
    tick();
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener('keydown', onKey);
    };
  }, [home, away, user?.id]);

  // Pre-match: sadece veri MEVCUT ama maç başlamamışsa.
  // Veri yoksa (available=false) pre-match değil "stats yok" durumudur.
  const isPreMatch = data?.available ? (
    isPreMatchStatus(data.eps) ||
    data.eps === 'NS' ||
    (!data.score && !data.events?.length) ||
    (data.score && Number(data.score.home) === 0 && Number(data.score.away) === 0 &&
     !data.events?.length && isPreMatchStatus(data.eps))
  ) : false;

  // Render via portal so the modal escapes any parent's `contain` / `transform` ancestor.
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setPortalEl(document.body);
  }, []);

  const modalContent = (
    <div
      className="match-detail-overlay"
      data-testid="match-stats-modal"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="md-title"
    >
      <div className="match-detail-modal">
        {/* HEADER */}
        <div className="match-detail-header">
          <div className="match-detail-league" id="md-title">
            {data?.league ? data.league.toUpperCase() : TR.MATCH_DETAIL}
          </div>
          <button
            className="match-detail-close"
            onClick={onClose}
            data-testid="modal-close"
            aria-label="Kapat"
          >✕</button>
        </div>

        {/* LOADING */}
        {loading && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontFamily: 'VT323, monospace', fontSize: 18, letterSpacing: 2 }} data-testid="stats-loading">
            {TR.STATS_LOADING}
          </div>
        )}

        {/* TAHMİN ROZETİ — kullanıcı giriş yaptıysa + tahmini varsa */}
        {!loading && myPred && (
          <div
            data-testid="my-prediction-badge"
            style={{
              padding: '12px 24px',
              background: myPred.settled
                ? (myPred.points >= 5
                    ? 'linear-gradient(90deg, rgba(0,255,127,0.18), rgba(0,240,255,0.12))'
                    : myPred.points >= 3
                      ? 'linear-gradient(90deg, rgba(0,240,255,0.15), rgba(170,0,255,0.10))'
                      : myPred.points >= 1
                        ? 'linear-gradient(90deg, rgba(255,170,0,0.15), rgba(255,0,170,0.08))'
                        : 'linear-gradient(90deg, rgba(120,120,120,0.15), rgba(60,60,60,0.08))')
                : 'linear-gradient(90deg, rgba(255,0,170,0.12), rgba(0,240,255,0.08))',
              borderTop: '1px solid rgba(255,255,255,0.08)',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{
                fontFamily: 'Orbitron, sans-serif', fontSize: 10, letterSpacing: 3,
                color: 'var(--text-dim)', textTransform: 'uppercase',
              }}>Tahminin</span>
              <span style={{
                fontFamily: 'Orbitron, sans-serif', fontSize: 22, fontWeight: 700,
                color: 'var(--cyan, #00f0ff)', textShadow: '0 0 12px rgba(0,240,255,0.5)',
                letterSpacing: 2,
              }}>
                {myPred.score1}–{myPred.score2}
              </span>
              {myPred.settled && myPred.final_score && (
                <>
                  <span style={{ color: 'var(--text-dim)', fontSize: 11, letterSpacing: 2 }}>vs SONUÇ</span>
                  <span style={{
                    fontFamily: 'Orbitron, sans-serif', fontSize: 18, fontWeight: 600,
                    color: '#fff', letterSpacing: 1,
                  }}>
                    {myPred.final_score[0]}–{myPred.final_score[1]}
                  </span>
                </>
              )}
            </div>
            {myPred.settled ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {myPred.points >= 5 ? (
                  <span style={{
                    fontFamily: 'Orbitron, sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: 2,
                    color: '#00ff7f', textShadow: '0 0 12px rgba(0,255,127,0.7)',
                  }} data-testid="pred-badge-exact">★ TAM SKOR · +5p</span>
                ) : myPred.points >= 3 ? (
                  <span style={{
                    fontFamily: 'Orbitron, sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: 2,
                    color: 'var(--cyan, #00f0ff)', textShadow: '0 0 10px rgba(0,240,255,0.6)',
                  }} data-testid="pred-badge-diff">✓ GOL FARKI · +3p</span>
                ) : myPred.points >= 1 ? (
                  <span style={{
                    fontFamily: 'Orbitron, sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: 2,
                    color: 'var(--orange, #ffa600)', textShadow: '0 0 10px rgba(255,166,0,0.6)',
                  }} data-testid="pred-badge-result">✓ SONUÇ · +1p</span>
                ) : (
                  <span style={{
                    fontFamily: 'Orbitron, sans-serif', fontSize: 13, fontWeight: 700, letterSpacing: 2,
                    color: 'var(--text-dim)',
                  }} data-testid="pred-badge-miss">✗ KAÇIRDIN · 0p</span>
                )}
              </div>
            ) : (
              <div style={{
                fontFamily: 'VT323, monospace', fontSize: 13, letterSpacing: 2,
                color: 'var(--text-dim)',
              }} data-testid="pred-badge-pending">⏳ MAÇ BİTİNCE PUANLANACAK</div>
            )}
          </div>
        )}

        {/* SCOREBOARD (her durumda göster — takım ismi + skor) */}
        {!loading && (
          <div className="match-detail-scoreboard">
            <div className="md-teams">
              <div className="md-team-name left"><TeamLogo name={data?.home || home} size={30} className="tl-md" />{data?.home || home}</div>
              <div className="md-score" data-testid="stats-score">
                {data?.score
                  ? `${data.score.home}–${data.score.away}`
                  : <span style={{ color: 'var(--text-dim)' }}>vs</span>}
                {(data?.score?.pen_home != null) && (
                  <div style={{ fontSize: 13, color: 'var(--orange, #ffa600)', marginTop: 6, letterSpacing: 2 }}>
                    PEN {data.score.pen_home}-{data.score.pen_away}
                  </div>
                )}
              </div>
              <div className="md-team-name right">{data?.away || away}<TeamLogo name={data?.away || away} size={30} className="tl-md" /></div>
            </div>
            {data?.eps && <div className="md-status">{data.eps}</div>}
                {data?.venue && <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginTop: 6 }}>· {typeof data.venue === 'string' ? data.venue : (data.venue as any)?.Vnm || ''} ·</div>}
          </div>
        )}

        {/* PRE-MATCH PANEL — eski repodan port edilmiş */}
        {!loading && isPreMatch && (
          <div className="md-pre-match" data-testid="md-pre-match" style={{
            padding: '40px 30px', textAlign: 'center',
            background: 'rgba(0,0,0,0.25)', borderTop: '1px solid rgba(255,0,170,0.15)',
            borderBottom: '1px solid rgba(255,0,170,0.15)',
          }}>
            <div className="md-pre-match-icon" style={{ fontSize: 48, marginBottom: 14, filter: 'drop-shadow(0 0 12px var(--cyan, #00f0ff))' }} aria-hidden>⏱</div>
            <div className="md-pre-match-title" style={{
              fontFamily: 'Orbitron, sans-serif', fontSize: 16, letterSpacing: 3,
              color: 'var(--cyan, #00f0ff)', textShadow: '0 0 12px var(--cyan, #00f0ff)',
              marginBottom: 8,
            }}>{TR.STATS_PRE_MATCH_TITLE}</div>
            <div className="md-pre-match-sub" style={{
              fontFamily: 'VT323, monospace', fontSize: 15, color: 'var(--text-dim)',
              letterSpacing: 1, maxWidth: 460, margin: '0 auto',
            }}>{TR.STATS_PRE_MATCH_SUB}</div>
          </div>
        )}

        {/* MAÇ OLAYLARI */}
        {!loading && !isPreMatch && data?.events && data.events.length > 0 && (
          <div className="md-events">
            <div className="md-events-title">{TR.EVENTS_TITLE}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {data.events.map((e, i) => (
                <div
                  key={i}
                  className={`md-event-row ${e.type === 'red' ? 'redcard' : e.type === 'yellow' ? 'yellowcard' : e.type}`}
                  data-testid={`event-${i}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '8px 12px', background: 'rgba(255,255,255,0.03)',
                    borderLeft: '3px solid transparent', borderRadius: 4,
                  }}
                >
                  <img src={EVENT_ICON[e.type]} alt="" style={{ width: 18, height: 18 }} />
                  <span style={{ fontFamily: 'VT323, monospace', color: 'var(--pink)', minWidth: 35, letterSpacing: 1 }}>
                    {e.minute}&apos;
                  </span>
                  <span style={{ flex: 1, color: e.team === 'home' ? 'var(--cyan)' : 'var(--pink)', textAlign: e.team === 'home' ? 'left' : 'right' }}>
                    <strong>{e.player}</strong>
                    {e.assist && <span style={{ color: 'var(--text-dim)', marginLeft: 6, fontSize: 11 }}> · {e.assist}</span>}
                  </span>
                  <span style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1, minWidth: 80, textAlign: 'right' }}>
                    {e.label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && !isPreMatch && data?.events && data.events.length === 0 && (
          <div className="md-events">
            <div className="md-events-title">{TR.EVENTS_TITLE}</div>
            <div style={{ padding: '14px 12px', textAlign: 'center', color: 'var(--text-dim)', fontFamily: 'VT323, monospace', fontSize: 15 }}>
              {TR.NO_EVENTS}
            </div>
          </div>
        )}

        {/* İSTATİSTİK TABLOSU — eski repodan 25+ stat row */}
        {!loading && !isPreMatch && data?.stats && Object.keys(data.stats).length > 0 && (
          <div className="md-stats-grid" data-testid="md-stats-grid">
            {STAT_ORDER.map(({ key, always, icon }) => {
              const raw = data.stats[key];
              const has = raw && (raw.home !== null && raw.home !== undefined) && (raw.away !== null && raw.away !== undefined);
              if (!has && !always) return null;
              const hv = has ? raw.home : 0;
              const av = has ? raw.away : 0;
              const hN = toNum(hv);
              const aN = toNum(av);
              const total = hN + aN || 1;
              const hp = Math.max(2, Math.min(98, (hN / total) * 100));
              return (
                <div key={key} className="md-stat-row" data-testid={`stat-${key}`}>
                  <div className="md-stat-h">{has ? hv : 0}</div>
                  <div className="md-stat-label">
                    {icon && <img src={icon} alt="" style={{ width: 14, height: 14, marginRight: 6, verticalAlign: 'middle' }} />}
                    {STAT_LABEL[key] || key.toUpperCase()}
                  </div>
                  <div className="md-stat-a">{has ? av : 0}</div>
                  <div style={{ gridColumn: '1/-1', display: 'flex', height: 3, borderRadius: 2, overflow: 'hidden', background: 'rgba(255,255,255,0.06)', marginTop: 4 }}>
                    <div style={{ background: 'var(--cyan)', width: `${hp}%`, boxShadow: '0 0 6px var(--cyan)' }} />
                    <div style={{ background: 'var(--pink)', width: `${100 - hp}%`, boxShadow: '0 0 6px var(--pink)' }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* HİÇBİR ŞEY YOK ama maç başlamış (rare case) */}
        {!loading && !isPreMatch && (!data?.events?.length) && (!data?.stats || Object.keys(data.stats).length === 0) && (
          <div style={{
            padding: '30px', textAlign: 'center',
            color: 'var(--text-dim)', fontFamily: 'VT323, monospace', fontSize: 15,
          }} data-testid="stats-unavailable">
            <div style={{ fontFamily: 'Orbitron, sans-serif', fontSize: 13, letterSpacing: 3, color: 'var(--orange, #ffa600)', marginBottom: 8 }}>
              {TR.STATS_UNAVAILABLE_TITLE}
            </div>
            <div>{data?.message || TR.STATS_UNAVAILABLE_SUB}</div>
          </div>
        )}

        {/* AI TAHMİN (3-MODEL HARMAN) — Hemen modal'ın üstünde */}
        <AIPrediction home={home} away={away} league={data?.league} />

        {/* KAYNAK ROZETLERİ — backend'in döndürdüğü gerçek source listesini göster (Bug #20 fix) */}
        {!loading && data?.sources && data.sources.length > 0 && (
          <div style={{
            padding: '10px 30px 20px', textAlign: 'center',
            fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, fontFamily: 'VT323, monospace',
          }} data-testid="stats-sources">
            {TR.STATS_SOURCES} · {data.sources
              .map((s) => s.replace('_statistics', '').toUpperCase())
              .filter((s, i, arr) => arr.indexOf(s) === i)
              .join(' + ')}
          </div>
        )}
      </div>
    </div>
  );

  return portalEl ? createPortal(modalContent, portalEl) : modalContent;
}
