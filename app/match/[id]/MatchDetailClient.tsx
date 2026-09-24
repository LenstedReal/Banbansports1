'use client';
import { useEffect, useState } from 'react';
import { getClient } from '@/lib/api';
import { TR, STAT_LABEL, STAT_ORDER, isPreMatchStatus } from '@/lib/i18n';
import { AuthProvider } from '@/components/AuthProvider';

type Stats = any;

const EVENT_ICON: Record<string, string> = {
  goal: '/icons/goal.png',
  yellow: '/icons/yellowcard.png',
  red: '/icons/redcard.png',
  sub: '/icons/info.png',
};

const toNum = (v: any) => {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'number') return v;
  const n = parseFloat(String(v).replace('%', ''));
  return isNaN(n) ? 0 : n;
};

export default function MatchDetailClient({ home, away, date, initial }: { home: string; away: string; date?: string; initial: Stats | null }) {
  return (
    <AuthProvider>
      <MatchDetailInner home={home} away={away} date={date} initial={initial} />
    </AuthProvider>
  );
}

function MatchDetailInner({ home, away, date, initial }: { home: string; away: string; date?: string; initial: Stats | null }) {
  const [data, setData] = useState<Stats | null>(initial);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      // Çakışma fix: slug'daki tarihi de gönder — backend başka günün maçını bulamasın
      const dateQ = date && date.length === 8 ? `&date=${date}` : '';
      const d = await getClient<Stats>(`/api/match/stats?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}${dateQ}`);
      if (alive && d) setData(d);
    };
    tick();
    const eps = String(data?.eps || '');
    const live = ['1H', '2H', 'HT', 'ET', 'PEN'].includes(eps) || /^\d/.test(eps);
    const intervalMs = live ? 15_000 : 60_000;
    const id = setInterval(tick, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [home, away, date]);

  // Pre-match: sadece veri MEVCUT ve eps açıkça pre-match. data yok ya da
  // available=false ise pre-match diyemeyiz — "stats bulunamadı" göstereceğiz.
  const isPreMatch = data?.available ? (
    isPreMatchStatus(data.eps) ||
    data.eps === 'NS' ||
    (!data.score && !data.events?.length)
  ) : false;

  return (
    <div data-testid="match-detail-client">
      {/* PRE-MATCH PANEL */}
      {isPreMatch && (
        <div style={{ padding: 40, textAlign: 'center', background: 'rgba(0,0,0,0.25)', borderRadius: 10, border: '1px solid rgba(255,0,170,0.15)', marginBottom: 20 }} data-testid="match-page-pre-match">
          <div style={{ fontSize: 56, marginBottom: 14, filter: 'drop-shadow(0 0 14px var(--cyan, #00f0ff))' }}>⏱</div>
          <div style={{ fontFamily: 'Orbitron', fontSize: 18, letterSpacing: 3, color: 'var(--cyan)', textShadow: '0 0 12px var(--cyan)', marginBottom: 10 }}>{TR.STATS_PRE_MATCH_TITLE}</div>
          <div style={{ fontFamily: 'VT323', fontSize: 16, color: 'var(--text-dim)', letterSpacing: 1, maxWidth: 500, margin: '0 auto' }}>{TR.STATS_PRE_MATCH_SUB}</div>
        </div>
      )}

      {/* MAÇ OLAYLARI + İSTATİSTİK — geniş ekranda yan yana, darda alt alta */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 460px), 1fr))', gap: 20, alignItems: 'start' }}>
      {/* MAÇ OLAYLARI */}
      {!isPreMatch && data?.events && data.events.length > 0 && (
        <div style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(255,0,170,0.2)', borderRadius: 8, padding: 14 }}>
          <div style={{ fontFamily: 'Orbitron', fontSize: 13, letterSpacing: 3, color: 'var(--pink)', marginBottom: 10 }}>{TR.EVENTS_TITLE}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.events.map((e: any, i: number) => (
              <div key={i} data-testid={`match-page-event-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: 4 }}>
                <img src={EVENT_ICON[e.type]} alt="" style={{ width: 18, height: 18 }} />
                <span style={{ fontFamily: 'VT323', color: 'var(--pink)', minWidth: 35 }}>{e.minute}&apos;</span>
                <span style={{ flex: 1, color: e.team === 'home' ? 'var(--cyan)' : 'var(--pink)', textAlign: e.team === 'home' ? 'left' : 'right' }}>
                  <strong>{e.player}</strong>
                  {e.assist && <span style={{ color: 'var(--text-dim)', marginLeft: 6, fontSize: 11 }}> · {e.assist}</span>}
                </span>
                <span style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1, minWidth: 80, textAlign: 'right' }}>{e.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* İSTATİSTİK */}
      {!isPreMatch && data?.stats && Object.keys(data.stats).length > 0 && (
        <div style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(0,240,255,0.2)', borderRadius: 8, padding: '14px 18px' }} data-testid="match-page-stats">
          {STAT_ORDER.map(({ key, always, icon }) => {
            const raw = data.stats[key];
            const has = raw && raw.home != null && raw.away != null;
            if (!has && !always) return null;
            // Bilinmeyen veri: 0 gibi yanlış değer göstermek yerine '?' göster
            const hv = has ? raw.home : '?';
            const av = has ? raw.away : '?';
            const unknown = hv === '?' || av === '?';
            const total = toNum(hv) + toNum(av) || 1;
            const hp = unknown ? 50 : Math.max(2, Math.min(98, (toNum(hv) / total) * 100));
            return (
              <div key={key} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }} data-testid={`match-page-stat-${key}`}>
                <div style={{ fontFamily: 'Orbitron', color: unknown ? 'var(--text-dim)' : 'var(--cyan)', fontSize: 14, minWidth: 30, textAlign: 'right' }}>{hv}</div>
                <div style={{ textAlign: 'center', fontFamily: 'VT323', fontSize: 12, color: 'var(--text-dim)', letterSpacing: 2 }}>
                  {icon && <img src={icon} alt="" style={{ width: 12, height: 12, marginRight: 6, verticalAlign: 'middle' }} />}
                  {STAT_LABEL[key] || key.toUpperCase()}
                </div>
                <div style={{ fontFamily: 'Orbitron', color: unknown ? 'var(--text-dim)' : 'var(--pink)', fontSize: 14, minWidth: 30 }}>{av}</div>
                <div style={{ gridColumn: '1/-1', display: 'flex', height: 3, borderRadius: 2, overflow: 'hidden', background: 'rgba(255,255,255,0.06)', opacity: unknown ? 0.3 : 1 }}>
                  <div style={{ background: 'var(--cyan)', width: `${hp}%` }} />
                  <div style={{ background: 'var(--pink)', width: `${100 - hp}%` }} />
                </div>
              </div>
            );
          })}
          {(() => {
            const DERIVED = ['goals', 'yellow_cards', 'red_cards', 'substitutions'];
            const keys = Object.keys(data.stats || {});
            const onlyDerived = keys.length > 0 && keys.every((k) => DERIVED.includes(k));
            if (!onlyDerived) return null;
            return (
              <div style={{ marginTop: 12, padding: '8px 10px', borderRadius: 6, background: 'rgba(255,166,0,0.07)', border: '1px solid rgba(255,166,0,0.25)', fontFamily: 'VT323', fontSize: 14, color: 'var(--orange, #ffa600)', textAlign: 'center', letterSpacing: 0.5 }} data-testid="stats-limited-note">
                Bu maç için kaynaklar detaylı istatistik sağlamıyor (hazırlık/alt seviye maçlarda olur) — yalnızca olay bazlı veriler gösteriliyor.
              </div>
            );
          })()}
        </div>
      )}
      </div>

      {!data?.available && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontFamily: 'VT323', fontSize: 15 }} data-testid="match-page-empty">
          <div style={{ fontFamily: 'Orbitron', fontSize: 14, letterSpacing: 3, color: 'var(--orange, #ffa600)', marginBottom: 10 }}>{TR.STATS_UNAVAILABLE_TITLE}</div>
          <div>{data?.message || TR.STATS_UNAVAILABLE_SUB}</div>
        </div>
      )}

      {data?.sources && data.sources.length > 0 && (
        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2 }}>
          {TR.STATS_SOURCES} · SOFASCORE
        </div>
      )}
    </div>
  );
}
