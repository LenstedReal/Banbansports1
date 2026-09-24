/**
 * Hero / Live ticker — vertical scrolling marquee of upcoming + live matches.
 * Pure SSR-friendly (no client JS needed for content).
 */
type Match = { team1: string; team2: string; league?: string; status?: string; score1?: number|null; score2?: number|null };
export default function HeroTicker({ matches }: { matches: Match[] }) {
  if (!matches?.length) return null;
  const items = [...matches, ...matches]; // double for seamless marquee
  return (
    <section className="relative mx-auto max-w-7xl px-4 pt-4" data-testid="hero-ticker">
      <div className="glass rounded-xl overflow-hidden">
        <div className="flex items-center gap-3 px-3 py-1.5 border-b border-[var(--line-mid)]">
          <span className="pulse-dot"/>
          <span className="font-display tracking-widest text-sm text-neon-cyan">CANLI AKIŞ</span>
          <span className="text-ink-low text-xs font-mono">/ skor & yaklaşan maçlar</span>
        </div>
        <div className="overflow-hidden">
          <div className="marquee-track flex gap-8 py-2 px-3 whitespace-nowrap">
            {items.map((m, i) => (
              <span key={i} className="inline-flex items-center gap-2 font-mono text-sm">
                <span className="text-ink-low">{m.league}</span>
                <span className="text-ink-high">{m.team1}</span>
                <span className="text-[var(--cyan)]">
                  {m.score1 == null ? 'vs' : `${m.score1}–${m.score2}`}
                </span>
                <span className="text-ink-high">{m.team2}</span>
                <span className="text-ink-low">· {m.status}</span>
                <span className="text-ink-low/40">●</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
