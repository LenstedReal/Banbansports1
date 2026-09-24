import type { Metadata } from 'next';
import Link from 'next/link';
import { getServer } from '@/lib/api';
import { epsToLabel, trLeagueName } from '@/lib/i18n';
import MatchDetailClient from './MatchDetailClient';
import TeamLogo from '@/components/TeamLogo';

export const dynamic = 'force-dynamic';
export const revalidate = 60;

type MatchStats = {
  available: boolean;
  home: string; away: string;
  league?: string;
  score?: { home: number; away: number; pen_home?: number | null; pen_away?: number | null };
  events?: any[];
  stats?: Record<string, { home: any; away: any }>;
  sources?: string[];
  eps?: string;
  venue?: string;
  message?: string;
};

async function fetchMatch(slug: string): Promise<MatchStats | null> {
  try {
    // Slug may arrive percent-encoded; backend expects raw UTF-8 in path
    const decoded = (() => { try { return decodeURIComponent(slug); } catch { return slug; } })();
    return await getServer<MatchStats>(`/api/match/by-slug/${encodeURIComponent(decoded)}`);
  } catch {
    return null;
  }
}

function decodeSlug(slug: string): { home: string; away: string; date: string } {
  // Accept both raw and percent-encoded slugs
  let s = slug;
  try { s = decodeURIComponent(slug); } catch { /* invalid percent-encoding — fall back to raw slug */ }
  const parts = s.split('__');
  return {
    home: (parts[0] || '').replace(/_/g, ' '),
    away: (parts[1] || '').replace(/_/g, ' '),
    date: parts[2] || '',
  };
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const m = await fetchMatch(id);
  const decoded = decodeSlug(id);
  const home = m?.home || decoded.home || 'Maç';
  const away = m?.away || decoded.away || 'banbansports';
  const score = m?.score ? `${m.score.home}-${m.score.away}` : '';
  const title = score
    ? `${home} ${score} ${away} — Detay · banbansports`
    : `${home} vs ${away} — Canlı Detay · banbansports`;
  const desc = m?.league
    ? `${trLeagueName(m.league)} · ${home} - ${away} canlı skor, istatistik ve maç olayları.`
    : 'Canlı skor, istatistik ve maç olayları — banbansports UNDERGROUND HD.';
  const og = `/og/match?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&score=${encodeURIComponent(score)}&league=${encodeURIComponent(m?.league || '')}`;
  return {
    title,
    description: desc,
    openGraph: {
      title, description: desc, type: 'website',
      images: [{ url: og, width: 1200, height: 630, alt: `${home} vs ${away}` }],
    },
    twitter: { card: 'summary_large_image', title, description: desc, images: [og] },
  };
}

export default async function MatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const m = await fetchMatch(id);
  const decoded = decodeSlug(id);
  const home = m?.home || decoded.home || '—';
  const away = m?.away || decoded.away || '—';

  return (
    <div className="bb-shell">
      <div className="scanlines" />
      <header className="md2-header">
        <div className="md2-header-in">
          <Link href="/" className="md2-back" data-testid="match-back-link">← banbansports</Link>
          <div className="md2-tag">MAÇ DETAYI</div>
        </div>
      </header>
      <main className="md2-main" data-testid="match-detail-page">
        {/* SSR hero — instant content, SEO ready */}
        <div className="pnl md2-hero" data-testid="md2-hero">
          {m?.league && (
            <div className="md2-hero-league" data-testid="match-league">
              {trLeagueName(m.league).toUpperCase()}
            </div>
          )}
          <div className="md2-hero-main">
            <div className="md2-team">
              <TeamLogo name={home} size={52} />
              <h1 data-testid="match-home">{home}</h1>
            </div>
            <div className="md2-score" data-testid="match-score">
              {m?.score && !['NS', 'Not Started'].includes(String(m?.eps || '')) ? `${m.score.home}–${m.score.away}` : 'vs'}
              {m?.score?.pen_home != null && (
                <div className="md2-pen">PEN {m.score.pen_home}-{m.score.pen_away}</div>
              )}
            </div>
            <div className="md2-team">
              <TeamLogo name={away} size={52} />
              <h1 data-testid="match-away">{away}</h1>
            </div>
          </div>
          {m?.eps && (
            <div className="md2-eps" data-testid="match-eps">{epsToLabel(m.eps).txt}</div>
          )}
          {m?.venue && (
            <div className="md2-venue" data-testid="match-venue">
              🏟 STADYUM: {(typeof m.venue === 'string' ? m.venue : (m.venue as any)?.Vnm || '').toUpperCase()}
            </div>
          )}
        </div>

        {/* Client-side detail (events + stats) */}
        <MatchDetailClient home={home} away={away} date={decoded.date} initial={m} />
      </main>
    </div>
  );
}
