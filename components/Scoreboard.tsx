'use client';
import { useEffect, useRef, useState } from 'react';
import { getClient } from '@/lib/api';
import type { Match } from '@/lib/api';
import { TR, isPreMatchStatus } from '@/lib/i18n';
import TeamLogo from './TeamLogo';

type Props = { initialMatches: Match[] };

const fmtScoreParts = (m: Match) => {
  const preMatch = isPreMatchStatus(m.status) || m.score1 === null || m.score1 === undefined;
  if (preMatch) {
    return { a: 'vs', sep: '', b: '', pre: true };
  }
  return { a: String(m.score1 ?? 0), sep: '–', b: String(m.score2 ?? 0), pre: false };
};

export default function Scoreboard({ initialMatches }: Props) {
  const [matches, setMatches] = useState<Match[]>(initialMatches);
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matchesRef = useRef<Match[]>(initialMatches);

  // Auto-cycle every 8s (sadece >1 maç ve duraklatılmadıysa)
  useEffect(() => {
    if (paused || matches.length <= 1) return;
    const id = setInterval(() => setIdx((i) => (i + 1) % matches.length), 8_000);
    return () => clearInterval(id);
  }, [matches.length, paused]);

  // Auto-refresh — canlı maç varsa 30s, yoksa 90s. Mount-once, [matches] dep YOK.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (!alive) return;
      try {
        const d = await getClient<{ matches?: Match[] }>('/api/scores/top?n=5');
        if (!alive) return;
        if (d?.matches?.length) {
          matchesRef.current = d.matches;
          setMatches(d.matches);
          setError(null);
        }
      } catch {
        if (alive) setError(TR.ERROR_GENERIC);
      } finally {
        if (alive) {
          const anyLive = matchesRef.current.some((m) => m.isLive);
          timer = setTimeout(tick, anyLive ? 30_000 : 90_000);
        }
      }
    };
    // İlk fetch hızlı — initialMatches boşsa 500ms, doluysa 30s
    const firstDelay = initialMatches.length === 0 ? 500 : 30_000;
    timer = setTimeout(tick, firstDelay);
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, []);

  // EMPTY STATE — kaliteli, anlamlı mesaj
  if (!matches.length) {
    return (
      <section id="live" className="mx-auto max-w-7xl px-4 mt-6" data-testid="scoreboard-empty">
        <div className="glass rounded-2xl p-8 text-center">
          <div className="text-3xl mb-2" aria-hidden>⚽</div>
          <div className="font-display text-lg text-ink-high tracking-widest mb-1">
            {TR.SCOREBOARD_EMPTY_TITLE}
          </div>
          <div className="text-ink-mid text-sm">{TR.SCOREBOARD_EMPTY_SUB}</div>
          {error && <div className="mt-3 text-xs text-amber-400">{error}</div>}
        </div>
      </section>
    );
  }

  const safeIdx = Math.min(idx, matches.length - 1);
  const m = matches[safeIdx];
  // Bug #6 fix: regex /^\d+/ kaldırıldı (false positive — "19:00" saatte digit prefix → yanlış CANLI)
  // Sadece backend'in isLive flag'ine güven.
  const live = !!m.isLive;
  const { a, sep, b, pre } = fmtScoreParts(m);

  return (
    <section id="live" className="mx-auto max-w-7xl px-4 mt-6" data-testid="scoreboard"
             onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="relative glass rounded-2xl overflow-hidden">
        {/* Top strip — Bug #7 fix: status boşken DAIMA centered, dolu olduğunda yine centered ama yan yana */}
        <div className="flex flex-col items-center px-5 pt-4">
          <div className="flex items-center gap-3" style={{ width: '100%', justifyContent: 'center' }}>
            <div className="flex items-center gap-2">
              {live ? <span className="pulse-dot" aria-hidden /> : <span className="w-2 h-2 rounded-full bg-amber-400/70" aria-hidden />}
              <span className="font-display text-sm tracking-widest text-ink-mid" data-testid="scoreboard-state">
                {live ? TR.LIVE : (pre ? TR.UPCOMING : TR.FINISHED)} · {m.league || 'FUTBOL'}
              </span>
            </div>
            {m.status && (
              <span className="font-mono text-ink-low text-sm" data-testid="scoreboard-status">· {m.status}</span>
            )}
          </div>
        </div>

        {/* Match line */}
        <div className="px-5 py-6 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="text-right">
            <div className="font-display text-2xl sm:text-3xl text-ink-high truncate flex items-center justify-end gap-3" data-testid="scoreboard-team1"><TeamLogo name={m.team1} size={34} className="tl-sb" /><span className="truncate">{m.team1}</span></div>
          </div>
          <div className="text-center font-display leading-none">
            <div className="text-4xl sm:text-6xl text-neon-cyan flex items-end justify-center gap-2" data-testid="scoreboard-score">
              <span>{a}</span>
              {sep && <span className="text-ink-low text-3xl mb-1">{sep}</span>}
              {b !== '' && <span>{b}</span>}
            </div>
            {(m.pen1 !== null && m.pen1 !== undefined) && (
              <div className="mt-1 text-xs text-amber-400">PEN {m.pen1}-{m.pen2}</div>
            )}
          </div>
          <div className="text-left">
            <div className="font-display text-2xl sm:text-3xl text-ink-high truncate flex items-center justify-start gap-3" data-testid="scoreboard-team2"><span className="truncate">{m.team2}</span><TeamLogo name={m.team2} size={34} className="tl-sb" /></div>
          </div>
        </div>

        {/* Dots — tıklanabilir, görsel olarak da gezilebilir */}
        {matches.length > 1 && (
          <div className="flex gap-1.5 justify-center pb-3" data-testid="scoreboard-dots">
            {matches.map((_, i) => (
              <button
                key={i}
                onClick={() => setIdx(i)}
                aria-label={`Maç ${i + 1}`}
                className={`h-1.5 rounded-full transition-all ${i === safeIdx ? 'w-6 bg-[var(--cyan)]' : 'w-2.5 bg-white/15 hover:bg-white/30'}`}
                data-testid={`scoreboard-dot-${i}`}
              />
            ))}
          </div>
        )}

        {/* Accent bar */}
        <div className="h-1 w-full bg-gradient-to-r from-[var(--cyan)] via-[var(--pink)] to-[var(--cyan)]" />
      </div>
    </section>
  );
}
