'use client';
/* =====================================================================
   PlayerChrome — Grok/JW tarzı hafif oynatma katmanı (yalnız GÖRÜNÜM)
   Üst şerit (Cast · CANLI · kalite pili), orta halka Play, SESİ AÇ pili,
   alt bar: ilerleme, oynat/duraklat, ses, süre, bağlantı, CC/SES/HD menüleri,
   GENİŞ BANT, PiP, Tam ekran. Format rozeti yalnızca gerçekten algılanan bilgi.
   Tüm davranış (motor, reklam, failover) VideoPlayer'da kalır; burası saf UI.
   ===================================================================== */
import { useEffect, useRef, useState } from 'react';

export type ChromeLevel = { index: number; height: number; bitrate: number };
export type ChromeTrack = { id: number; name: string; lang: string };

export type PlayerChromeProps = {
  visible: boolean;
  started: boolean;
  isPlaying: boolean;
  muted: boolean;
  volume: number;
  isLive: boolean;
  currentTime: number;
  duration: number;
  buffered: number;
  levels: ChromeLevel[];
  currentLevel: number;          // -1 = AUTO
  activeHeight: number;          // şu an oynayan seviyenin yüksekliği (AUTO · 1080 için)
  subtitleTracks: ChromeTrack[];
  currentSubtitle: number;       // -1 = kapalı
  audioTracks: ChromeTrack[];
  currentAudio: number;
  netType: string;
  fps: number;
  formatBadge: string;           // '1080p · AAC' | ''
  hqMode: boolean;
  batteryLow: boolean;
  isPip: boolean;
  isFullscreen: boolean;
  channelName: string;
  onTogglePlay: () => void;
  onToggleMute: () => void;
  onUnmute: () => void;
  onVolume: (v: number) => void;
  onSeek: (t: number) => void;
  onQuality: (idx: number) => void;
  onSubtitle: (id: number) => void;
  onAudio: (id: number) => void;
  onToggleHq: () => void;
  onPip: () => void;
  onFullscreen: () => void;
  onCast: () => void;
};

const fmt = (t: number) => {
  if (!isFinite(t) || t < 0) return '00:00';
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60);
  const p = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${p(h)}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
};

export const heightLabel = (h: number): string => {
  if (!h) return '';
  if (h >= 2000) return '4K';
  if (h >= 1400) return '1440p';
  if (h >= 1000) return '1080p';
  if (h >= 700) return '720p';
  if (h >= 460) return '480p';
  return `${h}p`;
};

const Icon = {
  play: <svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21" /></svg>,
  pause: <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>,
  volHi: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 5.5a9 9 0 0 1 0 13" /></svg>,
  volLo: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /></svg>,
  volOff: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><line x1="23" y1="9" x2="17" y2="15" /><line x1="17" y1="9" x2="23" y2="15" /></svg>,
  cast: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8V5a1 1 0 0 1 1-1h18a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-6" /><path d="M2 13a9 9 0 0 1 8 8" /><path d="M2 17a5 5 0 0 1 4 4" /><circle cx="3" cy="21" r="1" /></svg>,
  pip: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2" /><rect x="12" y="11" width="8" height="6" rx="1" fill="currentColor" /></svg>,
  fs: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M21 8V5a2 2 0 0 0-2-2h-3" /><path d="M3 16v3a2 2 0 0 0 2 2h3" /><path d="M16 21h3a2 2 0 0 0 2-2v-3" /></svg>,
  fsExit: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3" /><path d="M21 8h-3a2 2 0 0 1-2-2V3" /><path d="M3 16h3a2 2 0 0 1 2 2v3" /><path d="M16 21v-3a2 2 0 0 1 2-2h3" /></svg>,
  wifi: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z" /></svg>,
  cell: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 22h2v-4H2v4zm4 0h2v-8H6v8zm4 0h2v-12h-2v12zm4 0h2V6h-2v16zm4 0h2V2h-2v20z" /></svg>,
  off: <svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.64 7c-.45-.34-4.93-4-11.64-4-1.5 0-2.89.19-4.15.48L18.18 13.8 23.64 7zM3.41 1.31L2 2.72l2.05 2.05C1.91 5.76.59 6.82.36 7L12 21.5l3.91-4.87 3.32 3.32 1.41-1.41L3.41 1.31z" /></svg>,
};

type MenuKey = 'cc' | 'hd' | 'audio' | null;

export default function PlayerChrome(p: PlayerChromeProps) {
  const [menu, setMenu] = useState<MenuKey>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  // Menüleri dış tıklamada kapat
  useEffect(() => {
    if (!menu) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (!t?.closest('.pc-menu-wrap')) setMenu(null);
    };
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [menu]);
  useEffect(() => { if (!p.visible) setMenu(null); }, [p.visible]);

  const toggleMenu = (k: MenuKey) => (e: React.MouseEvent) => { e.stopPropagation(); setMenu((m) => (m === k ? null : k)); };

  const activeLabel = heightLabel(p.activeHeight);
  const qualityPill = p.currentLevel === -1
    ? (activeLabel ? `AUTO · ${activeLabel.replace('p', '')}` : 'AUTO')
    : (heightLabel(p.levels.find((l) => l.index === p.currentLevel)?.height || 0) || 'HD');

  const pct = p.isLive ? 100 : (p.duration > 0 ? Math.min(100, (p.currentTime / p.duration) * 100) : 0);
  const bufPct = p.isLive ? 100 : (p.duration > 0 ? Math.min(100, (p.buffered / p.duration) * 100) : 0);

  const seek = (e: React.MouseEvent) => {
    if (p.isLive || !progressRef.current || !p.duration) return;
    const r = progressRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    p.onSeek(ratio * p.duration);
  };

  const volIcon = p.muted || p.volume === 0 ? Icon.volOff : p.volume < 0.5 ? Icon.volLo : Icon.volHi;
  const shown = p.visible || !p.isPlaying;

  return (
    <>
      <div className="pc-fade pc-fade-top" aria-hidden />
      <div className="pc-fade pc-fade-bottom" aria-hidden />

      {/* ÜST ŞERİT */}
      <div className={`pc-top ${shown ? 'is-shown' : ''}`} data-testid="player-top-strip">
        <div className="pc-top-left">
          <button className="pc-icon" onClick={p.onCast} data-testid="cast-btn" title="Chromecast / AirPlay / Smart TV" aria-label="Yayını cihaza aktar">{Icon.cast}</button>
          {p.isLive && p.isPlaying && (
            <span className="pc-badge pc-live" data-testid="live-badge"><span className="pc-live-dot" />CANLI</span>
          )}
          <span className="pc-badge pc-chan" data-testid="player-channel-name">{p.channelName}</span>
        </div>
        <div className="pc-top-right">
          {p.isPlaying && p.fps > 0 && (
            <span className="pc-badge pc-fps" data-testid="fps-indicator">{p.fps} <small>FPS</small></span>
          )}
          <span className="pc-badge pc-quality" data-testid="quality-pill">{qualityPill}</span>
        </div>
      </div>

      {/* SESİ AÇ pili */}
      {p.muted && p.started && (
        <button className="pc-unmute" onClick={p.onUnmute} data-testid="unmute-btn">
          <span className="pc-unmute-ic">{Icon.volHi}</span> SESİ AÇ
        </button>
      )}

      {/* ORTA — duraklatıldığında büyük halka Play */}
      {p.started && !p.isPlaying && (
        <button className="pc-center" onClick={p.onTogglePlay} data-testid="center-play" aria-label="Oynat">
          <span className="pc-ring">{Icon.play}</span>
        </button>
      )}

      {/* FORMAT ROZETİ — yalnız algılanan */}
      {p.formatBadge && shown && (
        <div className="pc-format" data-testid="format-badge">{p.formatBadge}</div>
      )}

      {/* ALT KONTROL BARI */}
      <div className={`pc-controls ${shown ? 'is-shown' : ''}`} data-testid="video-controls">
        <div className={`pc-progress ${p.isLive ? 'is-live' : ''}`} ref={progressRef} onClick={seek} data-testid="progress-bar">
          <div className="pc-buffered" style={{ width: `${bufPct}%` }} />
          <div className="pc-played" style={{ width: `${pct}%` }} />
          {!p.isLive && <div className="pc-knob" style={{ left: `${pct}%` }} />}
        </div>

        <div className="pc-row">
          <div className="pc-grp">
            <button className="pc-btn" onClick={p.onTogglePlay} data-testid="playpause-btn" aria-label={p.isPlaying ? 'Duraklat' : 'Oynat'} title={p.isPlaying ? 'Duraklat' : 'Oynat'}>
              {p.isPlaying ? Icon.pause : Icon.play}
            </button>
            <div className="pc-vol">
              <button className="pc-btn" onClick={p.onToggleMute} data-testid="mute-btn" aria-label={p.muted ? 'Sesi aç' : 'Sessiz'} title={p.muted ? 'Sesi aç' : 'Sessiz'}>{volIcon}</button>
              <div className="pc-vol-slider">
                <input type="range" min={0} max={100} value={p.muted ? 0 : Math.round(p.volume * 100)}
                  onChange={(e) => p.onVolume(Number(e.target.value) / 100)} aria-label="Ses seviyesi" data-testid="volume-slider" />
              </div>
            </div>
            <div className="pc-time" data-testid="time-display">
              {p.isLive ? <><span className="pc-live-tag">CANLI</span> yayın</> : `${fmt(p.currentTime)} / ${fmt(p.duration)}`}
            </div>
          </div>

          {/* BAĞLANTI — ortada */}
          <div className={`pc-net ${p.netType === 'OFFLINE' ? 'is-off' : ''}`} data-testid="connection-indicator" title={`Bağlantı: ${p.netType}`}>
            <span className="pc-net-ic">{p.netType === 'WIFI' ? Icon.wifi : p.netType === 'OFFLINE' ? Icon.off : Icon.cell}</span>
            {p.netType === '5G' ? <span className="pc-5g" data-testid="net-5g-glyph">5G</span> : p.netType}
          </div>

          <div className="pc-grp pc-grp-right">
            {/* SES parçası (yalnız çoklu ses varsa) */}
            {p.audioTracks.length > 1 && (
              <div className="pc-menu-wrap" data-testid="audio-selector">
                <button className={`pc-btn pc-label ${menu === 'audio' ? 'is-on' : ''}`} onClick={toggleMenu('audio')} data-testid="audio-btn">SES</button>
                {menu === 'audio' && (
                  <div className="pc-menu" data-testid="audio-dropdown">
                    <div className="pc-menu-title">Ses</div>
                    {p.audioTracks.map((t) => (
                      <button key={t.id} className={`pc-menu-item ${p.currentAudio === t.id ? 'is-active' : ''}`} onClick={(e) => { e.stopPropagation(); p.onAudio(t.id); setMenu(null); }} data-testid={`audio-${t.id}`}>
                        <span>{t.name}</span><span className="pc-dot" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* CC */}
            <div className="pc-menu-wrap" data-testid="subtitle-selector">
              <button className={`pc-btn pc-label ${p.currentSubtitle !== -1 ? 'is-on' : ''}`} onClick={toggleMenu('cc')} data-testid="subtitle-btn" title="Altyazı">CC</button>
              {menu === 'cc' && (
                <div className="pc-menu" data-testid="subtitle-dropdown">
                  <div className="pc-menu-title">Altyazı</div>
                  {p.subtitleTracks.length === 0 ? (
                    <div className="pc-menu-note" data-testid="subtitle-none">Yayında altyazı yok</div>
                  ) : (
                    <>
                      <button className={`pc-menu-item ${p.currentSubtitle === -1 ? 'is-active' : ''}`} onClick={(e) => { e.stopPropagation(); p.onSubtitle(-1); setMenu(null); }} data-testid="subtitle-off"><span>Kapalı</span><span className="pc-dot" /></button>
                      {p.subtitleTracks.map((t) => (
                        <button key={t.id} className={`pc-menu-item ${p.currentSubtitle === t.id ? 'is-active' : ''}`} onClick={(e) => { e.stopPropagation(); p.onSubtitle(t.id); setMenu(null); }} data-testid={`subtitle-${t.id}`}>
                          <span>{t.name}</span><span className="pc-dot" />
                        </button>
                      ))}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* HD */}
            <div className="pc-menu-wrap" data-testid="quality-selector">
              <button className={`pc-btn pc-label ${menu === 'hd' ? 'is-on' : ''}`} onClick={toggleMenu('hd')} data-testid="quality-btn" title="Kalite">
                {p.currentLevel === -1 ? 'AUTO' : (heightLabel(p.levels.find((l) => l.index === p.currentLevel)?.height || 0) || 'HD')}
              </button>
              {menu === 'hd' && (
                <div className="pc-menu" data-testid="quality-dropdown">
                  <div className="pc-menu-title">Kalite</div>
                  {p.levels.length === 0 ? (
                    <div className="pc-menu-note" data-testid="quality-single">Yayında tek kalite</div>
                  ) : (
                    <>
                      <button className={`pc-menu-item ${p.currentLevel === -1 ? 'is-active' : ''}`} onClick={(e) => { e.stopPropagation(); p.onQuality(-1); setMenu(null); }} data-testid="quality-auto"><span>Otomatik{activeLabel ? ` · ${activeLabel}` : ''}</span><span className="pc-dot" /></button>
                      {[...p.levels].sort((a, b) => b.height - a.height).map((l) => (
                        <button key={l.index} className={`pc-menu-item ${p.currentLevel === l.index ? 'is-active' : ''}`} onClick={(e) => { e.stopPropagation(); p.onQuality(l.index); setMenu(null); }} data-testid={`quality-${l.height}`}>
                          <span>{heightLabel(l.height)}{l.bitrate ? <small> · {Math.round(l.bitrate / 1000)} kbps</small> : null}</span><span className="pc-dot" />
                        </button>
                      ))}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* GENİŞ BANT */}
            <button
              className={`pc-btn pc-label pc-hq ${p.hqMode ? 'is-on' : ''}`}
              onClick={(e) => { e.stopPropagation(); if (p.batteryLow && !p.hqMode) return; p.onToggleHq(); }}
              disabled={p.batteryLow && !p.hqMode}
              data-testid="hq-btn"
              title={p.batteryLow ? 'Düşük batarya → Geniş Bant kullanılamaz' : p.hqMode ? 'Geniş Bant AÇIK' : 'Geniş Bant kapalı'}
              aria-label="Geniş Bant Modu"
            >
              ⚡ {p.hqMode ? 'GENİŞ BANT' : 'HQ'}
            </button>

            <button className={`pc-btn ${p.isPip ? 'is-on' : ''}`} onClick={p.onPip} data-testid="pip-btn" title="Küçük pencere" aria-label="Küçük pencere">{Icon.pip}</button>
            <button className="pc-btn" onClick={p.onFullscreen} data-testid="fullscreen-btn" title="Tam ekran" aria-label="Tam ekran">{p.isFullscreen ? Icon.fsExit : Icon.fs}</button>
          </div>
        </div>
      </div>
    </>
  );
}
