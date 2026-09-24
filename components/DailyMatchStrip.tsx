'use client';
/* GÜNÜN MAÇI — /api/featured/status polling; İZLE → bb:select-channel */
import { useEffect, useState } from 'react';
import TeamLogo from './TeamLogo';
import { CHANNELS } from '@/lib/channels';

type Featured = { live: boolean; channel: string; status: string; match: any };

export default function DailyMatchStrip() {
  const [featured, setFeatured] = useState<Featured>({ live: false, channel: '', status: 'none', match: null });

  useEffect(() => {
    let cancelled = false;
    const fetchFeatured = async () => {
      try {
        const r = await fetch('/api/featured/status', { cache: 'no-store' });
        if (!r.ok || cancelled) return;
        const d = await r.json();
        if (cancelled) return;
        setFeatured((prev) => ({
          live: !!d.live,
          channel: d.channel || '',
          status: d.status || 'none',
          match: d.match || prev.match,
        }));
      } catch { /* sessiz */ }
    };
    fetchFeatured();
    const id = setInterval(fetchFeatured, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!featured.match) return null;
  const fm = featured.match;
  const fch = fm.app_channel ? CHANNELS.find((x) => x.id === fm.app_channel) : null;
  const isUp = fm.status === 'upcoming';
  const cd = (() => {
    const n = fm?.starts_in_min ?? 0;
    if (!isUp || n <= 0) return '';
    if (n < 60) return `${n} DK SONRA`;
    const h = Math.floor(n / 60); const mm = n % 60;
    return mm ? `${h} SA ${mm} DK SONRA` : `${h} SA SONRA`;
  })();

  const watch = () => {
    try {
      window.dispatchEvent(new CustomEvent('bb:select-channel', { detail: { id: fm.app_channel } }));
      document.getElementById('canli-yayin')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch { /* noop */ }
  };

  return (
    <div className={`pnl fd2 ${isUp ? 'upcoming' : 'live'}`} data-testid="featured-match-box">
      <span className="fd2-kicker">GÜNÜN MAÇI</span>
      {fch?.logo
        ? <img className="fd2-chlogo" src={fch.logo} alt={fch.name} loading="lazy" />
        : (fm.channel_name ? <span className="fd2-meta">{fm.channel_name}</span> : null)}
      <div className="fd2-mid">
        <div className="fd2-teams">
          <span className="fd2-t"><TeamLogo name={fm.home} size={22} className="tl-fd" />{fm.home}</span>
          <span className="fd2-vs">{(fm.score1 !== null && fm.score1 !== undefined && fm.score2 !== null && fm.score2 !== undefined) ? `${fm.score1} - ${fm.score2}` : 'VS'}</span>
          <span className="fd2-t">{fm.away}<TeamLogo name={fm.away} size={22} className="tl-fd" /></span>
        </div>
        <div className="fd2-meta">
          {[
            fch ? fch.name : (fm.channel_name || null),
            fm.league || null,
            fm.time || fm.status_label || null,
          ].filter(Boolean).join(' · ')}
          {cd && <> · <span className="fd2-cd">{cd}</span></>}
        </div>
      </div>
      <div className="fd2-right">
        <span className={`fd2-badge ${isUp ? 'upcoming' : 'live'}`}>
          <span className="fd2-badge-dot" />{isUp ? 'YAKINDA' : 'CANLI'}
        </span>
        {fm.watchable && fm.app_channel && (
          <button className="btn-neon b-pink" data-testid="featured-watch-btn" onClick={watch}>
            ▶ İZLE
          </button>
        )}
      </div>
    </div>
  );
}
