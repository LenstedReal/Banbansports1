'use client';
import { useEffect, useRef, useState } from 'react';
import { getClient } from '@/lib/api';
import type { Match } from '@/lib/api';
import TeamLogo from './TeamLogo';

export default function MatchBanner({ initialMatches }: { initialMatches: Match[] }) {
  const [matches, setMatches] = useState<Match[]>(initialMatches);
  const [idx, setIdx] = useState(0);
  useEffect(() => { if (initialMatches && initialMatches.length) setMatches(initialMatches); }, [initialMatches]);
  const touchStartX = useRef<number | null>(null);

  const goTo = (dir: number) =>
    setIdx((i) => (i + dir + matches.length) % matches.length);

  const onTouchStart = (e: React.TouchEvent) => { touchStartX.current = e.touches[0].clientX; };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current == null || matches.length <= 1) { touchStartX.current = null; return; }
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(dx) < 40) return;
    goTo(dx < 0 ? 1 : -1);
  };

  useEffect(() => {
    if (matches.length <= 1) return;
    const id = setInterval(() => setIdx(i => (i + 1) % matches.length), 15_000);
    return () => clearInterval(id);
  }, [matches.length]);

  const polled = useRef(false);
  useEffect(() => {
    if (polled.current) return;
    polled.current = true;
    const tick = async () => {
      const d = await getClient<{ matches?: Match[] }>('/api/scores/top?n=5');
      if (d?.matches?.length) setMatches(d.matches);
    };
    if (initialMatches.length === 0) tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);

  if (!matches.length) {
    return (
      <div className="pnl hero2" data-testid="match-banner">
        <div className="hero2-loading">Maç verisi yükleniyor…</div>
      </div>
    );
  }

  const m = matches[idx];
  const live = !!m.isLive;
  const isNS = m.score1 == null;
  const stateLabel = live ? 'CANLI' : isNS ? 'YAKLAŞAN' : 'MAÇ';

  return (
    <div
      className="pnl hero2"
      data-testid="match-banner"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      style={{ touchAction: 'pan-y' }}
    >
      <div className="hero2-league" data-testid="league-info">
        <b>● {stateLabel}</b> · {m.league || 'FUTBOL'}
      </div>
      <div className="hero2-main">
        <div className="hero2-team">
          <TeamLogo name={m.team1} size={46} className="tl-banner" />
          <span className="hero2-team-name" data-testid="team1">{m.team1}</span>
        </div>
        <div className="hero2-mid">
          {isNS ? (
            <span className="hero2-vs" data-testid="score1">VS</span>
          ) : (
            <span className="hero2-score">
              <span data-testid="score1">{m.score1}</span> - <span data-testid="score2">{m.score2}</span>
            </span>
          )}
          {(m.pen1 !== null && m.pen1 !== undefined) && (
            <span className="hero2-pen">PEN {m.pen1}-{m.pen2}</span>
          )}
          {m.status && <span className="hero2-time" data-testid="match-minute">{m.status}</span>}
        </div>
        <div className="hero2-team">
          <TeamLogo name={m.team2} size={46} className="tl-banner" />
          <span className="hero2-team-name" data-testid="team2">{m.team2}</span>
        </div>
      </div>
      {matches.length > 1 && (
        <div className="hero2-dots" data-testid="banner-dots">
          {matches.map((_, i) => (
            <button
              key={i}
              onClick={() => setIdx(i)}
              aria-label={`Maç ${i + 1}`}
              className={`hero2-dot ${i === idx ? 'active' : ''}`}
              data-testid={`banner-dot-${i}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
