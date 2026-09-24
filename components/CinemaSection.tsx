'use client';
/* BOX OFFICE — KOMPAKT KOMPOZİSYON (v3):
   Üst şerit: YENİ FİLM · IMDb. Gövde: poster | cam panel (başlık + vizyon + etiketler + KONU/İZLE).
   Alt: CANLI GİŞE → KAYNAK → gişe verileri (BoxOfficeCounter). Veriler ve data-testid'ler AYNEN korunur. */
import { useEffect, useState } from 'react';
import type { Movie } from './MoviePlayer';
import BoxOfficeCounter from './BoxOfficeCounter';

export default function CinemaSection() {
  const [movie, setMovie] = useState<Movie | null>(null);
  const [imdb, setImdb] = useState<{ rating: number; votes: string } | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [plot, setPlot] = useState<{ text: string; credits?: string } | null>(null);
  const [plotOpen, setPlotOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch('/api/movies', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d?.movies?.length) setMovie(d.movies[0]); })
      .catch(() => { /* noop */ });
    return () => { alive = false; };
  }, []);

  const openMovie = () => {
    try { window.dispatchEvent(new CustomEvent('bb:open-movie')); } catch { /* noop */ }
  };

  // KONU açıkken: metne veya sayfada herhangi bir yere tıklayınca kapanır (çip toggle olarak kalır)
  useEffect(() => {
    if (!plotOpen) return;
    const close = (e: MouseEvent) => {
      if ((e.target as HTMLElement)?.closest?.('[data-testid="plot-toggle-btn"]')) return;
      setPlotOpen(false);
    };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [plotOpen]);

  return (
    <div className="pnl cin-card" id="filmler" data-testid="movie-tile">
      {movie && (
        <div className={`cin3-hero${plotOpen ? ' expanded' : ''}`} data-testid="boxoffice-hero" id="box-office">
          <img className="cin3-bg" src={movie.backdrop || '/spiderman_backdrop_v2.jpg'} alt="" loading="lazy" decoding="async" draggable={false} aria-hidden="true" />
          <div className="cin3-shade" aria-hidden="true" />

          {/* üst şerit */}
          <div className="cin3-top">
            <div className="bo2-badges" data-testid="boxoffice-badges">
              {movie.badge && <span className="bo2-new-badge" data-testid="boxoffice-new-badge"><span className="cin3-new-dot" />{movie.badge} FİLM</span>}
            </div>
            {imdb && (
              <span className="cin2-imdb" data-testid="boxoffice-imdb-rating" title={`${imdb.votes} oy`}>
                <span className="bo2-imdb-logo">IMDb</span> ★ {imdb.rating.toFixed(1)}
              </span>
            )}
          </div>

          {/* gövde: poster | cam bilgi paneli */}
          <div className="cin3-body">
            <img className="cin3-poster" src={movie.poster || '/spiderman_poster_v2.jpg'} alt={movie.title} loading="lazy" decoding="async" draggable={false} />

            <div className="cin3-mid">
              <div className="cin2-title" data-testid="movie-title">{movie.title.toLocaleUpperCase('tr-TR')}</div>
              <div className="cin3-en">{movie.title_en}</div>
              <div className="cin3-date"><span>VİZYONDA</span> · {movie.release_date}</div>
              <div className="cin2-tags cin3-tags">
                <span className="cin-tag t-dub" data-testid="movie-tag-dub">TÜRKÇE DUBLAJ · 720p</span>
                <span className="cin-tag t-sub" data-testid="movie-tag-sub">TÜRKÇE ALTYAZI · 1080p</span>
              </div>
              <div className="cin3-actions">
                {plot && (
                  <button className="cin3-plot-chip" data-testid="plot-toggle-btn" onClick={() => setPlotOpen((s) => !s)}>
                    KONU <span className="cin3-chev">{plotOpen ? '▲' : '▼'}</span>
                  </button>
                )}
                <button className="btn-neon b-pink cin2-watch cin3-watch" data-testid="movie-shelf-watch" onClick={openMovie}>
                  ▶ İZLE
                </button>
              </div>
            </div>
          </div>

          {plot && plotOpen && (
            <div className="cin2-plot" data-testid="boxoffice-plot">
              <p data-testid="boxoffice-plot-text">{plot.text}</p>
              {plot.credits && <div className="bo2-credits" data-testid="boxoffice-plot-credits">{plot.credits}</div>}
            </div>
          )}
        </div>
      )}

      {/* ===== KOMPAKT GİŞE VERİLERİ — CANLI GİŞE + KAYNAK verilerin üstünde ===== */}
      <div className="cin2-stats">
        <div className="cin3-stats-head">
          <span className="bo2-live-badge" data-testid="boxoffice-live-badge"><span className="bo2-live-dot" />CANLI GİŞE</span>
          <span className="cin3-stats-line" aria-hidden="true" />
        </div>
        {meta && (
          <div className="cin3-source">
            <span className="cin3-source-k" data-testid="boxoffice-source-title">KAYNAK</span>
            <span className="cin-src cin3-source-v" data-testid="boxoffice-sources">{meta}</span>
          </div>
        )}
        <BoxOfficeCounter
          onImdb={(rating, votes) => setImdb({ rating, votes })}
          onMeta={setMeta}
          onPlot={(text, credits) => setPlot({ text, credits })}
        />
      </div>
    </div>
  );
}
