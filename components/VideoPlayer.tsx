'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import { TR } from '@/lib/i18n';
import MoviePlayer, { type Movie } from './MoviePlayer';
import { smoothFps, measureRefreshHz, getRefreshHz, fpsClass } from '@/lib/fps';
import MaintenanceScreen from '@/components/player/MaintenanceScreen';
import PlayerChrome from '@/components/player/PlayerChrome';
import { CHANNELS, CHANNEL_SOURCES, type Channel } from '@/lib/channels';

// CORS bypass — m3u8'leri backend proxy üzerinden ver (eski repo davranışı)
// Not: Yeni kanallar (trt1/tv8/trtspor/ssport) /api/stream/{ch}/stream.m3u8 üzerinden token+tms ile gelir.
const proxify = (url: string) => `/api/stream/proxy?url=${encodeURIComponent(url)}`;
void proxify; // backward-compat — özel kullanım için bırakıldı



const AD_LIBRARY = [
  { name: 'eFootball',    src: '/ad_efootball.mp4', store: 'https://play.google.com/store/apps/details?id=jp.konami.pesam',                       color: '#0066FF' },
  { name: 'PUBG Mobile',  src: '/ad_pubg.mp4',      store: 'https://play.google.com/store/apps/details?id=com.tencent.ig',                       color: '#FF6600' },
  { name: 'Call of Duty', src: '/ad_cod.mp4',       store: 'https://play.google.com/store/apps/details?id=com.activision.callofduty.shooter',    color: '#00CC44' },
  { name: 'Lords Mobile', src: '/ad_lords.mp4',     store: 'https://play.google.com/store/apps/details?id=com.igg.android.lordsmobile',          color: '#CC0000' },
];

const MID_ROLL_INTERVAL_SEC = 17 * 60; // 17 dk — eski repodaki MIDROLL_INTERVAL
const AD_MAX_DURATION_MS = 60_000;     // 60sn güvenlik limiti

// Ad rotation — sessionStorage'de queue tut, her seferinde sıradakini ver
function nextAdIndex(): number {
  if (typeof window === 'undefined') return 0;
  try {
    const i = parseInt(sessionStorage.getItem('bb_adi') || '0', 10);
    const next = (i + 1) % AD_LIBRARY.length;
    sessionStorage.setItem('bb_adi', String(next));
    return i % AD_LIBRARY.length;
  } catch { return 0; }
}

// App store yönlendirme — Android Play Store / iOS App Store / Desktop yeni sekme
function redirectToStore(url: string) {
  if (!url) return;
  try {
    const ua = (navigator.userAgent || '').toLowerCase();
    const isMobile = /android|iphone|ipad|ipod/.test(ua);
    if (isMobile) {
      // Mobil cihazda doğrudan store linkine git (browser tarafı app açar)
      window.location.href = url;
    } else {
      // Desktop: yeni sekmede aç
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  } catch { /* noop */ }
}

type Level = { index: number; height: number; bitrate: number };

const qualityLabel = (h: number): string => {
  if (h >= 2160) return '4K';
  if (h >= 1440) return '1440p';
  if (h >= 1080) return '1080p';
  if (h >= 720) return '720p';
  if (h >= 480) return '480p';
  return '360p';
};

export default function VideoPlayer() {
  const [selected, setSelected] = useState<Channel>(CHANNELS[0]); // online kanal (tivibuspor) — sadece PLAY'e basınca oynar
  // Kullanıcı henüz kanal seçmedi → sidebar'da hiçbir kutu "active" görünmesin (kullanıcı talebi)
  const [hasPicked, setHasPicked] = useState(false);
  const [serverIndex, setServerIndex] = useState(0);
  // ===== Öne çıkan yayın (tünel kaynak) — hangi kanala map'li + canlı mı =====
  const [featured, setFeatured] = useState<{ live: boolean; channel: string; status: string; match: any }>({ live: false, channel: '', status: 'none', match: null });
  // ===== Canlı kanal sağlığı — backend /api/stream/status polling (30sn) =====
  // Backend cache TTL 60sn — yani gerçek segment check maksimum 60sn'de bir çalışır,
  // aradaki isteklerde cache dönüyor. LED renkleri buna göre dinamik boyanır.
  const [liveStatus, setLiveStatus] = useState<Record<string, { configured: boolean; ok: boolean }>>({});
  const [hasStarted, setHasStarted] = useState(false);
  const [adActive, setAdActive] = useState(false);
  const [adIndex, setAdIndex] = useState(0);
  const [awaitingResume, setAwaitingResume] = useState(false); // Reklam bitti → kullanıcı Play'e basana kadar yayın YOK
  const [adRemainingSec, setAdRemainingSec] = useState(0);
  const [streamError, setStreamError] = useState('');
  // Bakım/aktif olmayan kanal: 5 sn sonra döngü videosu oynar (kullanıcı isteği)
  const [maintLoop, setMaintLoop] = useState(false);
  useEffect(() => {
    if (hasStarted && !adActive && streamError) {
      const t = setTimeout(() => setMaintLoop(true), 5000);
      return () => clearTimeout(t);
    }
    setMaintLoop(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasStarted, adActive, streamError, selected.id]);
  const [muted, setMuted] = useState(true);
  const [levels, setLevels] = useState<Level[]>([]);
  const [currentLevel, setCurrentLevel] = useState(-1); // -1 = AUTO
  const [qualityOpen, setQualityOpen] = useState(false);
  const [isPip, setIsPip] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  // Yeni eski-repo UI state'leri
  const [netType, setNetType] = useState('—');        // '4G' | 'WiFi' | '—'
  const [fps, setFps] = useState(0);                  // gerçek zamanlı fps (ham)
  const [refreshHz, setRefreshHz] = useState(60);     // ekran yenileme hızı (bias için)
  const [subtitleTracks, setSubtitleTracks] = useState<Array<{id: number; name: string; lang: string}>>([]);
  const [currentSubtitle, setCurrentSubtitle] = useState(-1); // -1 = kapalı
  const [subtitleOpen, setSubtitleOpen] = useState(false);
  const [castSupported, setCastSupported] = useState(false);
  // ===== Yeni çekirdek durumları (Grok kabuğu) =====
  const [volume, setVolume] = useState(1);
  const [isLiveStream, setIsLiveStream] = useState(true);
  const [curTime, setCurTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [bufferedEnd, setBufferedEnd] = useState(0);
  const [activeHeight, setActiveHeight] = useState(0);
  const [formatBadge, setFormatBadge] = useState('');
  const [audioTracks, setAudioTracks] = useState<Array<{ id: number; name: string; lang: string }>>([]);
  const [currentAudio, setCurrentAudio] = useState(-1);
  // Kullanıcı bilinçli duraklattı mı? Bayrak AÇIKKEN hiçbir otomatik play() ÇAĞRILMAZ (PiP bug'ı)
  const userPausedRef = useRef(false);
  // 30sn yoklamaları motora DOKUNMASIN: liveStatus ref üzerinden okunur
  const liveStatusRef = useRef<Record<string, { configured: boolean; ok: boolean }>>({});
  useEffect(() => { liveStatusRef.current = liveStatus; }, [liveStatus]);
  // Bug #9: GENİŞ BANT MODU — agresif buffer + max kalite + battery aware
  const [hqMode, setHqMode] = useState(false);
  const [batteryLow, setBatteryLow] = useState(false);
  const [casting, setCasting] = useState(false);
  // FIX: Hover/mouse-move ile controls bar görünürlüğü — eskiden opacity:0 olduğu
  // için kullanıcı bar'ı göremiyor → mouseEnter tetiklenmiyor → HD/PiP butonları
  // tıklanamıyordu. controlsVisible state'i hem mouse move hem hover ile yönetilir.
  const [controlsVisible, setControlsVisible] = useState(true);
  const controlsHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ===== YENİ FİLM — katalog + ayrı film player modal =====
  const [movie, setMovie] = useState<Movie | null>(null);
  const [movieOpen, setMovieOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    fetch('/api/movies', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d?.movies?.length) setMovie(d.movies[0]); })
      .catch(() => { /* noop */ });
    return () => { alive = false; };
  }, []);

  // BOX OFFICE bölümündeki İZLE → film player modalını aç
  useEffect(() => {
    const onOpen = () => setMovieOpen(true);
    window.addEventListener('bb:open-movie', onOpen);
    return () => window.removeEventListener('bb:open-movie', onOpen);
  }, []);

  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const hlsRef = useRef<any>(null);
  const hlsActiveSrcRef = useRef<string | null>(null); // anti Strict-Mode double-init
  const playedTimeRef = useRef(0);
  // Bug #4 fix: hızlı kanal değişiminde race condition önleyici lock + debounce
  const switchLockRef = useRef<number | null>(null);
  const switchPendingRef = useRef<Channel | null>(null);
  const adVideoRef = useRef<HTMLVideoElement>(null);
  const adSafetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fpsFrameCountRef = useRef(0);
  const fpsLastSampleRef = useRef(0);
  const fpsRafIdRef = useRef<number | null>(null);

  // ===== Crash / freeze detection refs (eski repo mantığı) =====
  // STALL_THRESHOLD = 15sn donma → "YAYIN DONDU" overlay göster
  // CRASH_THRESHOLD = 45sn donma → tam çöktü → otomatik yeniden başlat
  const stallCountRef = useRef(0);
  const lastPlaybackTimeRef = useRef(0);
  const crashCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const freezeAutoRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const networkRetryRef = useRef(0);
  const fragErrorCountRef = useRef(0);
  const retryStreamRef = useRef<(() => void) | null>(null);
  const cleanupListenersRef = useRef<(() => void) | null>(null);
  const [freezeOverlay, setFreezeOverlay] = useState(false);
  const STALL_THRESHOLD = 15;
  const CRASH_THRESHOLD = 45;
  const MAX_NETWORK_RETRIES = 3;

  // ===== Pre-roll on channel change — SADECE session içinde her kanal için BİR KEZ (eski repo) =====
  useEffect(() => {
    if (!hasStarted) return;
    // sessionStorage flag — kanal başına 1 kez preroll
    let alreadyShown = false;
    try { alreadyShown = sessionStorage.getItem('bb_pr_' + selected.id) === '1'; } catch { /* noop */ }
    if (alreadyShown) return; // Bu kanal için preroll zaten gösterildi — direkt yayına geç
    try { sessionStorage.setItem('bb_pr_' + selected.id, '1'); } catch { /* noop */ }
    // Yayını TAMAMEN durdur (ses bleed önlemek için)
    if (hlsRef.current) { try { hlsRef.current.destroy(); } catch { /* noop */ } hlsRef.current = null; }
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.muted = true; // arka plan sesi YOK
      videoRef.current.removeAttribute('src');
      videoRef.current.load();
    }
    setAdIndex(nextAdIndex());
    setAdActive(true);
    setAwaitingResume(false);
  }, [selected.id, hasStarted]);

  // ===== Ad countdown + safety timer =====
  useEffect(() => {
    if (!adActive) return;
    const id = setInterval(() => {
      const av = adVideoRef.current;
      if (!av) return;
      const dur = (isFinite(av.duration) && av.duration > 0) ? av.duration : 30;
      const cur = av.currentTime || 0;
      setAdRemainingSec(Math.max(0, Math.ceil(dur - cur)));
    }, 300);
    // Güvenlik timer: video hang olursa 60sn sonra reklamı kapat (store yönlendirme YOK çünkü tamamlanmadı)
    if (adSafetyTimerRef.current) clearTimeout(adSafetyTimerRef.current);
    adSafetyTimerRef.current = setTimeout(() => {
      setAdActive(false);
      setAwaitingResume(true);
    }, AD_MAX_DURATION_MS);
    return () => {
      clearInterval(id);
      if (adSafetyTimerRef.current) { clearTimeout(adSafetyTimerRef.current); adSafetyTimerRef.current = null; }
    };
  }, [adActive, adIndex]);

  // ===== Mid-roll timer — sadece yayın aktifken sayar =====
  useEffect(() => {
    if (!hasStarted) return;
    const id = setInterval(() => {
      if (adActive || awaitingResume) return; // Reklam veya manuel-play bekleme sırasında zamanlayıcı çalışmaz
      // Bug #5 fix: User manuel pause ettiyse timer durmalı — paused iken counter sayma!
      const v = videoRef.current;
      if (v && v.paused) return;
      playedTimeRef.current += 0.5;
      if (playedTimeRef.current >= MID_ROLL_INTERVAL_SEC) {
        playedTimeRef.current = 0;
        // Yayını durdur, reklam başlat
        if (hlsRef.current) { try { hlsRef.current.destroy(); } catch { /* noop */ } hlsRef.current = null; }
        if (videoRef.current) { videoRef.current.pause(); videoRef.current.removeAttribute('src'); videoRef.current.load(); }
        setAdIndex(nextAdIndex());
        setAdActive(true);
      }
    }, 500);
    return () => clearInterval(id);
  }, [adActive, awaitingResume, hasStarted]);

  // ===== Fullscreen state tracker =====
  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  // ===== PiP state tracker =====
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onEnter = () => setIsPip(true);
    const onLeave = () => setIsPip(false);
    v.addEventListener('enterpictureinpicture', onEnter);
    v.addEventListener('leavepictureinpicture', onLeave);
    return () => {
      v.removeEventListener('enterpictureinpicture', onEnter);
      v.removeEventListener('leavepictureinpicture', onLeave);
    };
  }, []);

  // ===== Network connection type detect (Navigator.connection API) =====
  // Kullanıcı talebi: WiFi'deyse "WIFI", mobil veri ise "5G" (sabit), offline ise "OFFLINE"
  useEffect(() => {
    if (typeof navigator === 'undefined') return;
    const conn: any = (navigator as any).connection || (navigator as any).mozConnection || (navigator as any).webkitConnection;
    const update = () => {
      try {
        if (!navigator.onLine) { setNetType('OFFLINE'); return; }
        if (!conn) {
          // Connection API yok (Safari, Firefox eski) — hostname'den tahmin et
          setNetType('WIFI');
          return;
        }
        // conn.type değerleri: 'wifi', 'cellular', 'ethernet', 'bluetooth', 'wimax', 'none', 'unknown', 'other'
        // conn.effectiveType: '4g' | '3g' | '2g' | 'slow-2g' (bandwidth tahmini)
        const type = (conn.type || '').toLowerCase();
        const effType = (conn.effectiveType || '').toLowerCase();
        // 1. Önce gerçek 'type' alanına bak (en güvenilir)
        if (type === 'wifi' || type === 'ethernet' || type === 'wimax') {
          setNetType('WIFI');
        } else if (type === 'cellular') {
          // Mobil veri — kullanıcı talebi: sabit "5G" göster
          setNetType('5G');
        } else if (type === 'none') {
          setNetType('OFFLINE');
        } else {
          // type belli değilse (browser destek yok) → effectiveType ile WiFi mı mobil mi tahmin
          // effectiveType var ama type yok → mobil cihaz kabul et
          if (effType) {
            setNetType('5G');  // kullanıcı talebi: sabit 5G
          } else {
            // Hiçbir bilgi yok → WiFi varsay
            setNetType('WIFI');
          }
        }
      } catch { setNetType('WIFI'); }
    };
    update();
    const onOnline = () => update();
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOnline);
    if (conn && conn.addEventListener) conn.addEventListener('change', update);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOnline);
      if (conn && conn.removeEventListener) conn.removeEventListener('change', update);
    };
  }, []);

  // ===== isPlaying state tracker — MOUNT-ONLY, HLS effect'ten bağımsız =====
  // Bug #3 fix: listener'lar HLS effect IIFE'sinin SONUNDA ekleniyordu →
  // Safari native HLS path'i v.play()'i ÖNCE çağırıyor → 'play' event listener'a düşmüyor →
  // isPlaying SAFARI'DE SÜREKLİ FALSE → buton hep play ikonu gösteriyor.
  // Çözüm: video element mount edildiği an play/pause/playing/waiting listener'larını kalıcı ekle.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onPlay = () => { userPausedRef.current = false; setIsPlaying(true); };
    // 'pause' yalnız kullanıcı/PiP/sistem pause'unda tetiklenir (buffering 'waiting' verir) → bilinçli duraklatma say
    const onPause = () => { if (!v.ended && v.readyState >= 2) userPausedRef.current = true; setIsPlaying(false); };
    const onPlaying = () => { userPausedRef.current = false; setIsPlaying(true); };   // Safari için ek güvence
    const onEnded = () => setIsPlaying(false);
    const onTime = () => {
      setCurTime(v.currentTime || 0);
      const d = v.duration;
      setDuration(Number.isFinite(d) ? d : 0);
      setIsLiveStream(!Number.isFinite(d) || d === Infinity || (v.seekable && v.seekable.length > 0 && v.seekable.end(v.seekable.length - 1) - (v.seekable.start(0) || 0) < 3 * 3600 && !Number.isFinite(d)));
    };
    const onProgress = () => { try { if (v.buffered.length) setBufferedEnd(v.buffered.end(v.buffered.length - 1)); } catch { /* noop */ } };
    const onVol = () => { setVolume(v.volume); };
    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('playing', onPlaying);
    v.addEventListener('ended', onEnded);
    v.addEventListener('timeupdate', onTime);
    v.addEventListener('progress', onProgress);
    v.addEventListener('volumechange', onVol);
    // İlk durum sync — eğer video zaten oynuyorsa state'i ayarla
    setIsPlaying(!v.paused && !v.ended && v.readyState > 2);
    return () => {
      v.removeEventListener('play', onPlay);
      v.removeEventListener('pause', onPause);
      v.removeEventListener('playing', onPlaying);
      v.removeEventListener('ended', onEnded);
      v.removeEventListener('timeupdate', onTime);
      v.removeEventListener('progress', onProgress);
      v.removeEventListener('volumechange', onVol);
    };
  }, []);

  // ===== Cast support detect (Cast SDK + Remote Playback API + iOS AirPlay) =====
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    let cancelled = false;
    const detect = () => {
      if (cancelled) return;
      try {
        const w = window as any;
        // Google Cast Framework — Chromecast/Android TV/Beko Android TV
        const hasCastSdk = !!(w.cast && w.cast.framework && w.chrome && w.chrome.cast);
        if (hasCastSdk) {
          // SDK effect'ten ÖNCE yüklendiyse __onGCastApiAvailable hiç ateşlenmez →
          // setOptions burada garanti edilir (idempotent, requestSession için şart)
          try {
            w.cast.framework.CastContext.getInstance().setOptions({
              receiverApplicationId: w.chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
              autoJoinPolicy: w.chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
            });
          } catch { /* zaten init — sessiz */ }
        }
        // @ts-ignore — W3C Remote Playback API (Chrome Android default)
        const hasRemote = !!(v as any).remote && typeof (v as any).remote.watchAvailability === 'function';
        // @ts-ignore — iOS AirPlay
        const hasAirplay = typeof (v as any).webkitShowPlaybackTargetPicker === 'function';
        setCastSupported(hasCastSdk || hasRemote || hasAirplay);
      } catch { setCastSupported(false); }
    };
    detect();
    // Cast SDK script async yükleniyor → loaded event'i veya 1sn sonra tekrar dene
    const w = window as any;
    const onCastReady = () => detect();
    if (w.__onGCastApiAvailable === undefined) {
      w.__onGCastApiAvailable = (isAvailable: boolean) => {
        if (!isAvailable) return;
        try {
          w.cast.framework.CastContext.getInstance().setOptions({
            receiverApplicationId: w.chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
            autoJoinPolicy: w.chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
          });
        } catch { /* SDK init fail — sessiz */ }
        detect();
      };
    }
    window.addEventListener('cast:ready', onCastReady);
    const tid = setTimeout(detect, 1500);
    return () => {
      cancelled = true;
      window.removeEventListener('cast:ready', onCastReady);
      clearTimeout(tid);
    };
  }, [hasStarted]);

  // ===== Gerçek zamanlı FPS sayacı — requestVideoFrameCallback (Chrome/Edge) + fallback rAF =====
  useEffect(() => {
    if (!hasStarted || adActive || awaitingResume || streamError) {
      setFps(0);
      if (fpsRafIdRef.current) cancelAnimationFrame(fpsRafIdRef.current);
      fpsRafIdRef.current = null;
      return;
    }
    const v = videoRef.current;
    if (!v) return;
    fpsFrameCountRef.current = 0;
    fpsLastSampleRef.current = performance.now();
    // PERF: FPS sample 1s yerine 2s — re-render yarı yarıya, CPU yiyim azalır.
    // Kullanıcı FPS değerinin hızla güncellenmesine ihtiyaç duymaz, smooth indikatör yeter.
    const SAMPLE_MS = 2000;
    // @ts-ignore
    if (typeof v.requestVideoFrameCallback === 'function') {
      const cb = () => {
        fpsFrameCountRef.current += 1;
        const now = performance.now();
        const dt = now - fpsLastSampleRef.current;
        if (dt >= SAMPLE_MS) {
          setFps(Math.round((fpsFrameCountRef.current * 1000) / dt));
          fpsFrameCountRef.current = 0;
          fpsLastSampleRef.current = now;
        }
        // @ts-ignore
        v.requestVideoFrameCallback(cb);
      };
      // @ts-ignore
      v.requestVideoFrameCallback(cb);
      return;
    }
    // Fallback rAF (kesinlik düşük ama çalışır) — düşük güçlü cihazda CPU yutmasın
    // diye setInterval'a düşürdük (her 200ms tick + frame counter window 2sn).
    const tickId = setInterval(() => {
      const now = performance.now();
      const dt = now - fpsLastSampleRef.current;
      if (dt >= SAMPLE_MS) {
        // Best-effort: dt boyunca v.currentTime'in ilerlemesi varsa fps tahmin et
        setFps(Math.round((fpsFrameCountRef.current * 1000) / dt) || 0);
        fpsFrameCountRef.current = 0;
        fpsLastSampleRef.current = now;
      }
    }, 200);
    const rafLoop = () => {
      fpsFrameCountRef.current += 1;
      fpsRafIdRef.current = requestAnimationFrame(rafLoop);
    };
    fpsRafIdRef.current = requestAnimationFrame(rafLoop);
    return () => {
      clearInterval(tickId);
      if (fpsRafIdRef.current) cancelAnimationFrame(fpsRafIdRef.current);
      fpsRafIdRef.current = null;
    };
  }, [hasStarted, adActive, awaitingResume, streamError, selected.id, serverIndex]);

  // Ekran yenileme hızını mount'ta ölç (60 vs 90/120Hz bias kararı için)
  useEffect(() => { measureRefreshHz().then((hz) => setRefreshHz(hz)); }, []);

  // Görsel gösterilecek FPS — ortak smoothFps util (bias + yüksek Hz)
  const displayFps = smoothFps(fps, refreshHz);

  // Site sağındaki FPS rozeti ile SENKRON: player smoothed fps'ini global event ile yayınla
  // (Sağ-üst rozet bu değeri AYNEN kullanır → tek kaynak, çelişki yok)
  useEffect(() => {
    (window as any).__bbVideoFps = { v: displayFps, t: Date.now() };
    window.dispatchEvent(new CustomEvent('bb:videofps', { detail: displayFps }));
  }, [displayFps]);

  // ===== Mevcut yayın URL'i — server failover destekli =====
  const sources = (featured.live && featured.channel === selected.id)
    ? ['/api/featured/stream.m3u8']
    : (CHANNEL_SOURCES[selected.id] || (selected.src ? [selected.src] : []));
  const activeSrc = sources[serverIndex] || sources[0] || selected.src || '';

  // ===== Kanal değişince server index sıfırla =====
  useEffect(() => { setServerIndex(0); }, [selected.id]);

  // ===== Canlı kanal sağlığı — 30sn'de bir /api/stream/status çek =====
  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const r = await fetch('/api/stream/status', { cache: 'no-store' });
        if (!r.ok || cancelled) return;
        const data = await r.json();
        if (data && data.channels && !cancelled) {
          setLiveStatus((prev) => ({ ...prev, ...data.channels }));
        }
      } catch { /* network hata — sessiz, bir sonraki polling'de tekrar dener */ }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ===== Öne çıkan yayın — 30sn polling → map'li kanalın LED'ini otomatik boya =====
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
          // Geçici backend/kaynak hatasında GÜNÜN MAÇI kutusunu silme — son maçı koru
          match: d.match || prev.match,
        }));
        if (d.channel && d.status === 'live') {
          setLiveStatus((prev) => ({
            ...prev,
            [d.channel]: { configured: true, ok: !!d.live },
          }));
        }
      } catch { /* sessiz */ }
    };
    fetchFeatured();
    const id = setInterval(fetchFeatured, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ===== Öne çıkan bölmedeki / sağ rail'deki "İZLE" → o kanalı ana oynatıcıda seç =====
  useEffect(() => {
    const onSelect = (e: Event) => {
      const id = (e as CustomEvent)?.detail?.id;
      if (!id) return;
      const ch = CHANNELS.find((c) => c.id === id);
      if (ch) { setSelected(ch); setHasPicked(true); }
    };
    window.addEventListener('bb:select-channel', onSelect as EventListener);
    return () => window.removeEventListener('bb:select-channel', onSelect as EventListener);
  }, []);

  // ===== Sağ kolondaki ChannelRail'e player durumunu yayınla =====
  useEffect(() => {
    try {
      window.dispatchEvent(new CustomEvent('bb:player-state', {
        detail: { id: selected.id, hasPicked, locked: adActive || awaitingResume },
      }));
    } catch { /* noop */ }
  }, [selected.id, hasPicked, adActive, awaitingResume]);

  // ===== Global window callback — sayfa altındaki ServerSelector buradan tetikler =====
  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.bbServerIndex = serverIndex;
    window.bbServerCount = sources.length;
    window.bbSwitchServer = (idx: number) => {
      if (idx === serverIndex || idx >= sources.length) return;
      networkRetryRef.current = 0;
      stallCountRef.current = 0;
      setFreezeOverlay(false);
      setServerIndex(idx);
    };
    // Sponsors component'ine değişim sinyali yolla (P2 #45 — polling yerine event)
    try { window.dispatchEvent(new CustomEvent('bb:server-changed', { detail: { idx: serverIndex, count: sources.length } })); } catch { /* noop */ }
  }, [serverIndex, sources.length]);

  // ===== Load HLS / fallback — REKLAM YOKKEN VE MANUEL PLAY BEKLEME YOKKEN =====
  useEffect(() => {
    if (adActive || awaitingResume || !hasStarted) return;
    // Eğer pending destroy varsa değerlendir (Strict Mode aynı src ile remount)
    const pending = (hlsRef as any).__pendingDestroy;
    if (pending) {
      clearTimeout(pending.t);
      (hlsRef as any).__pendingDestroy = null;
      if (pending.hls && pending.src === activeSrc && !hlsRef.current) {
        // Aynı src ile remount → mevcut instance'ı aynen geri kullan (yayın kesilmez)
        hlsRef.current = pending.hls;
        hlsActiveSrcRef.current = pending.src;
      } else if (pending.hls && pending.hls !== hlsRef.current) {
        // Farklı src'ye geçiliyor → eski instance'ı hemen ve güvenle kapat
        try { pending.hls.destroy(); } catch { /* noop */ }
      }
    }
    // Strict Mode (Next dev) effect'i 2 kez tetikler — aynı src ise tekrar HLS başlatma
    if (hlsActiveSrcRef.current === activeSrc && hlsRef.current) return;
    hlsActiveSrcRef.current = activeSrc;
    setStreamError(''); setLevels([]); setCurrentLevel(-1); setAudioTracks([]); setCurrentAudio(-1); setActiveHeight(0); setFormatBadge('');
    const v = videoRef.current; if (!v) return;
    if (hlsRef.current) { try { hlsRef.current.destroy(); } catch { /* noop */ }; hlsRef.current = null; }
    // EFFECTIVE STATUS — canlı backend /api/stream/status verisi hardcoded status'u ezer.
    // LED noktası ile aynı kaynak: kanal kayıtlı ama segment fetch başarısız (ok:false) veya
    // configured:false ise → maintenance kabul edilir ve bakım uyarı metni gösterilir (TRT 1 gibi).
    const live = liveStatusRef.current[selected.id];
    const effStatus: Channel['status'] = live
      ? (!live.configured ? 'maintenance' : (live.ok ? 'online' : 'maintenance'))
      : selected.status;
    if (!activeSrc || effStatus === 'maintenance' || effStatus === 'coming_soon') {
      v.removeAttribute('src'); v.load();
      if (effStatus === 'maintenance') setStreamError(TR.CHANNEL_MAINTENANCE);
      else if (effStatus === 'coming_soon') setStreamError(TR.CHANNEL_COMING_SOON);
      else setStreamError(TR.CHANNEL_NO_SOURCE);
      return;
    }
    let cancelled = false;
    (async () => {
      // Native HLS (Safari) → doğrudan src
      if (v.canPlayType('application/vnd.apple.mpegurl')) {
        v.src = activeSrc;
        try { await v.play(); } catch { /* noop */ }
        return;
      }
      try {
        const mod: any = await import('hls.js');
        const Hls = mod.default;
        if (cancelled) return;
        if (Hls.isSupported()) {
          // Featured (Cloudflare tünel) kaynağı yavaş (ev upload'ı) → canlı kenardan
          // daha geride başla ki hep backend cache'inde hazır segmentleri oynat.
          const isFeaturedSrc = featured.live && featured.channel === selected.id;
          const h = new Hls({
            // En yüksek kalite & dayanıklılık (4K destekli)
            enableWorker: true,
            // FIX: lowLatencyMode=true st15.lol gibi standart HLS CDN'lerde
            // live-edge'in ÖNÜNDEKİ (henüz oluşmamış) segment'leri talep edip
            // 404 patlatıyordu. Standart HLS için kapatıyoruz; LL-HLS desteği
            // olan kaynaklarda manuel override edilebilir.
            lowLatencyMode: false,
            liveSyncDurationCount: isFeaturedSrc ? 5 : 3,   // featured: kenardan 5 segment geride (cache'li bölge)
            liveMaxLatencyDurationCount: isFeaturedSrc ? 30 : 10,
            backBufferLength: 30,
            // Hafif tampon — donma/kasma kökü olan 240–480 MB tamponlar kaldırıldı
            maxBufferLength: hqMode ? 60 : 30,
            maxMaxBufferLength: hqMode ? 120 : 60,
            maxBufferSize: hqMode ? 120 * 1000 * 1000 : 60 * 1000 * 1000,
            manifestLoadingTimeOut: 15_000,
            manifestLoadingMaxRetry: 4,
            levelLoadingTimeOut: 15_000,
            fragLoadingTimeOut: isFeaturedSrc ? 45_000 : 20_000,  // featured: yavaş segment için uzun timeout
            // FIX: Segment 404 olursa hls.js otomatik retry yapsın (eski segment
            // expire olduysa yeni manifest fetch ile güncel segment'lere geç).
            fragLoadingMaxRetry: isFeaturedSrc ? 6 : 4,
            fragLoadingRetryDelay: 500,
            levelLoadingMaxRetry: 4,
            startLevel: hqMode ? 0 : -1,     // HQ: en yüksek seviyeden başla
            capLevelToPlayerSize: false,
            abrEwmaDefaultEstimate: hqMode ? 5_000_000 : 1_000_000,
            abrBandWidthFactor: hqMode ? 1.0 : 0.95,
            abrBandWidthUpFactor: hqMode ? 0.9 : 0.7,
            xhrSetup: (xhr: XMLHttpRequest) => {
              xhr.setRequestHeader('Accept', '*/*');
            },
          });
          hlsRef.current = h;
          h.loadSource(activeSrc);
          h.attachMedia(v);
          h.on(Hls.Events.MANIFEST_PARSED, () => {
            const ls: Level[] = (h.levels || []).map((l: any, i: number) => ({
              index: i,
              height: l.height || 0,
              bitrate: l.bitrate || 0,
            })).sort((a: Level, b: Level) => b.height - a.height);
            setLevels(ls);
            // Yayın yüklenmeden placeholder'dan seçilen kalite → manifest hazır, şimdi uygula
            const pendH = (hlsRef as any).__pendingLevelHeight;
            if (typeof pendH === 'number' && (h.levels || []).length) {
              const ti = h.levels.findIndex((lv: any) => Math.abs((lv.height || 0) - pendH) <= 60);
              if (ti !== -1) {
                try { h.nextLevel = ti; h.loadLevel = ti; } catch { /* noop */ }
                setCurrentLevel(ti);
              }
              (hlsRef as any).__pendingLevelHeight = null;
            }
            // Subtitle tracks (altyazı) — HLS subtitle playlist'leri okur
            try {
              const subs: any[] = h.subtitleTracks || [];
              setSubtitleTracks(subs.map((s: any, i: number) => ({
                id: i,
                name: s.name || s.lang || `Altyazı ${i + 1}`,
                lang: s.lang || '',
              })));
              if (typeof h.subtitleTrack === 'number') setCurrentSubtitle(h.subtitleTrack);
              else setCurrentSubtitle(-1);
            } catch { setSubtitleTracks([]); setCurrentSubtitle(-1); }
            // Ses parçaları (gerçek)
            try {
              const auds: any[] = h.audioTracks || [];
              setAudioTracks(auds.map((a: any, i: number) => ({ id: i, name: a.name || a.lang || `Ses ${i + 1}`, lang: a.lang || '' })));
              setCurrentAudio(typeof h.audioTrack === 'number' ? h.audioTrack : -1);
            } catch { setAudioTracks([]); }
            networkRetryRef.current = 0;
            if (!userPausedRef.current) v.play().catch(() => { /* noop */ });
          });
          h.on(Hls.Events.LEVEL_LOADED, (_: any, data: any) => {
            try { setIsLiveStream(!!data?.details?.live); } catch { /* noop */ }
          });
          h.on(Hls.Events.LEVEL_SWITCHED, (_: any, data: any) => {
            if (h.autoLevelEnabled) setCurrentLevel(-1);
            else setCurrentLevel(data.level ?? -1);
            const lvl = (h.levels || [])[data.level];
            if (lvl) {
              setActiveHeight(lvl.height || 0);
              const hh = lvl.height || 0;
              const res = hh >= 2000 ? '4K' : hh ? `${hh}p` : '';
              const ac = String(lvl.audioCodec || '').toLowerCase();
              const acL = ac.includes('ec-3') ? 'EC-3' : ac.includes('ac-3') ? 'AC-3' : ac.includes('mp4a') ? 'AAC' : '';
              const vc = String(lvl.videoCodec || '').toLowerCase();
              const vcL = vc.includes('hvc') || vc.includes('hev') ? 'HEVC' : vc.includes('avc') ? 'H.264' : '';
              setFormatBadge([res, vcL, acL].filter(Boolean).join(' · '));
            }
          });
          h.on(Hls.Events.AUDIO_TRACK_SWITCHED, (_: any, data: any) => {
            setCurrentAudio(data?.id ?? -1);
            // Ses parçası değişince aynı dildeki altyazıyı otomatik seç
            try {
              const a = (h.audioTracks || [])[data.id];
              const subs: any[] = h.subtitleTracks || [];
              if (a?.lang && subs.length) {
                const m = subs.findIndex((s2: any) => (s2.lang || '').toLowerCase() === (a.lang || '').toLowerCase());
                if (m !== -1) { h.subtitleTrack = m; setCurrentSubtitle(m); }
              }
            } catch { /* noop */ }
          });
          // ===== FRAG-LEVEL ERROR SAYICI — non-fatal segment 404'leri takip et =====
          // Kaynak sunucu m3u8'i canlı üretiyor ama segment'ler CDN'de yok → HLS.js
          // sürekli retry loop'a giriyor, kullanıcı SİYAH EKRAN görüyor. Bu durumda
          // 5 ardışık fragLoadError sonrası freeze overlay göster (eski TRT SPOR
          // "Yayın şu anda aktif değil" mantığıyla aynı UX'i sağlar).
          fragErrorCountRef.current = 0;
          // ===== HLS ERROR HANDLING (eski repo mantığı + server failover) =====
          h.on(Hls.Events.ERROR, (_: any, data: any) => {
            // Non-fatal fragLoadError sayacı (segment 404/timeout/net-fail)
            if (!data?.fatal) {
              const det = data?.details || '';
              if (det === 'fragLoadError' || det === 'fragLoadTimeOut' || det === 'fragParsingError') {
                fragErrorCountRef.current += 1;
                if (fragErrorCountRef.current >= 5 && !freezeOverlay) {
                  // Segment gerçekten ölü → bakım overlay göster
                  setFreezeOverlay(true);
                }
              } else if (det === 'fragLoaded' || det === 'levelLoaded') {
                fragErrorCountRef.current = 0;
              }
              return;
            }
            // Fatal errors:
            // CODEC uyumsuzluğu — proxy CODECS attribute'unu zaten kaldırıyor;
            // burada düşersek son çare: sonraki sunucuya geç
            if (data.details === 'manifestIncompatibleCodecsError') {
              if (serverIndex < sources.length - 1) {
                setServerIndex((i) => i + 1);
              } else {
                setFreezeOverlay(true);
              }
              return;
            }
            // NETWORK ERROR — segment yüklenemiyor, recover dene (3 deneme)
            if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
              if (networkRetryRef.current < MAX_NETWORK_RETRIES) {
                networkRetryRef.current += 1;
                try { h.startLoad(); } catch { /* noop */ }
                return;
              }
              // 3 deneme başarısız → sonraki sunucuya geç
              if (serverIndex < sources.length - 1) {
                networkRetryRef.current = 0;
                setServerIndex((i) => i + 1);
                return;
              }
              // Tüm sunucular tükendi → freeze overlay
              setFreezeOverlay(true);
              return;
            }
            // MEDIA ERROR — codec/decoder sorunu, recoverMediaError dene
            if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
              try { h.recoverMediaError(); } catch { /* noop */ }
              return;
            }
            // Diğer fatal hatalar → sonraki sunucuya
            if (serverIndex < sources.length - 1) {
              setServerIndex((i) => i + 1);
              return;
            }
            setFreezeOverlay(true);
          });
        } else {
          v.src = activeSrc;
        }
      } catch {
        v.src = activeSrc;
      }

      // ===== Crash detection — eski repodaki mantık (currentTime advance kontrolü) =====
      stallCountRef.current = 0;
      lastPlaybackTimeRef.current = v.currentTime;
      if (crashCheckRef.current) clearInterval(crashCheckRef.current);
      crashCheckRef.current = setInterval(() => {
        if (!v) return;
        // FIX: v.paused iken erken return YOK — play hiç başlamamış (segment 404
        // yüzünden buffer yok) durumunda da stall counter ilerlesin, böylece 15sn
        // sonra bakım overlay tetiklenir. AMA kullanıcı MANUEL pause etti (yayın
        // başlamıştı, sonra durdurdu) → o zaman stall sayma.
        if (v.paused && v.currentTime > 0.5) {
          // Kullanıcı bilerek pause etti — stall counter reset
          stallCountRef.current = 0;
          return;
        }
        const ct = v.currentTime;
        const stuck = Math.abs(ct - lastPlaybackTimeRef.current) < 0.1;
        // Video henüz hiç oynatılmadıysa (readyState<3) VEYA advance etmediyse stall say
        if (stuck) {
          stallCountRef.current += 1;
          const n = stallCountRef.current;
          // 8sn donma → sessiz HLS recover
          if (n === 8 && hlsRef.current && !userPausedRef.current) {
            try { hlsRef.current.startLoad(); v.play().catch(() => { /* noop */ }); } catch { /* noop */ }
          }
          // 15sn donma → overlay
          if (n >= STALL_THRESHOLD && !freezeOverlay) {
            setFreezeOverlay(true);
          }
          // 45sn donma → tam yeniden başlat
          if (n >= CRASH_THRESHOLD) {
            stallCountRef.current = 0;
            retryStreamRef.current?.();
          }
        } else {
          if (stallCountRef.current > 0) setFreezeOverlay(false);
          stallCountRef.current = 0;
        }
        lastPlaybackTimeRef.current = ct;
      }, 1000);

      // ===== Video element event listener'ları =====
      const onWaiting = () => {
        if (hlsRef.current) { try { hlsRef.current.startLoad(); } catch { /* noop */ } }
      };
      const onStalled = () => {
        // Kullanıcı duraklattıysa ASLA otomatik play yok (PiP'te kendiliğinden başlama bug'ı)
        if (hlsRef.current && !userPausedRef.current) {
          try { hlsRef.current.startLoad(); } catch { /* noop */ }
        }
      };
      const onError = () => {
        const code = v.error?.code;
        if (code === 2 || code === 4) { // NETWORK or SRC_NOT_SUPPORTED
          retryStreamRef.current?.();
        }
      };
      v.addEventListener('waiting', onWaiting);
      v.addEventListener('stalled', onStalled);
      v.addEventListener('error', onError);
      // play/pause listener'ları artık dedicated useEffect'te (mount-only) — Bug #3 fix
      cleanupListenersRef.current = () => {
        v.removeEventListener('waiting', onWaiting);
        v.removeEventListener('stalled', onStalled);
        v.removeEventListener('error', onError);
      };
    })();
    return () => {
      cancelled = true;
      if (crashCheckRef.current) { clearInterval(crashCheckRef.current); crashCheckRef.current = null; }
      if (freezeAutoRetryRef.current) { clearTimeout(freezeAutoRetryRef.current); freezeAutoRetryRef.current = null; }
      cleanupListenersRef.current?.();
      // React 18+ Strict Mode'da hızlı yeniden mount oluşur — gerçek unmount'ı microtask sonrasında doğrula.
      // FIX: Eski "koşulsuz geri diriltme" kaldırıldı — o yol, gerçek unmount/reklam
      // geçişlerinde eski HLS instance'ının arka planda yaşamaya devam etmesine
      // (çift indirme → takılma/crash) yol açıyordu. Artık:
      //  - remount aynı src ile gelirse effect başında instance geri alınır (yayın kesilmez)
      //  - gelmezse timeout'ta kesin destroy edilir (sızıntı yok)
      const prevHls = hlsRef.current;
      const prevSrc = hlsActiveSrcRef.current;
      hlsRef.current = null;
      hlsActiveSrcRef.current = null;
      const willRemount = setTimeout(() => {
        (hlsRef as any).__pendingDestroy = null;
        if (prevHls && prevHls !== hlsRef.current) {
          try { prevHls.destroy(); } catch { /* noop */ }
        }
      }, 0);
      (hlsRef as any).__pendingDestroy = { t: willRemount, hls: prevHls, src: prevSrc };
    };
  // NOT: liveStatus / featured ARTIK bağımlılık DEĞİL — 30sn yoklamalar motoru yeniden başlatmaz (kendini kapatma bug'ı)
  }, [selected.id, serverIndex, activeSrc, adActive, awaitingResume, hasStarted, hqMode]);

  // ===== Battery API — düşük batarya tespit + HQ MODE otomatik kapat (Bug #9 + P2) =====
  useEffect(() => {
    if (typeof navigator === 'undefined') return;
    let battery: any = null;
    const check = () => {
      if (!battery) return;
      const low = !battery.charging && battery.level <= 0.20;
      setBatteryLow(low);
      if (low && hqMode) setHqMode(false);
    };
    // @ts-ignore
    if (typeof (navigator as any).getBattery === 'function') {
      (navigator as any).getBattery().then((b: any) => {
        battery = b;
        check();
        b.addEventListener('levelchange', check);
        b.addEventListener('chargingchange', check);
      }).catch(() => {});
    }
    return () => {
      if (battery) {
        battery.removeEventListener('levelchange', check);
        battery.removeEventListener('chargingchange', check);
      }
    };
  }, [hqMode]);

  // ===== Controls =====
  const handlePlay = useCallback(() => {
    // Yayını ATOMIK olarak başlat — önce reklam state'i, sonra hasStarted
    // Pre-roll effect bu kanal için tekrar fire etmesin diye sessionStorage flag set ediyoruz
    try { sessionStorage.setItem('bb_pr_' + selected.id, '1'); } catch { /* noop */ }
    setHasPicked(true);
    userPausedRef.current = false;
    setAdIndex(nextAdIndex());
    setAdActive(true);
    setMuted(false);
    if (videoRef.current) videoRef.current.muted = false;
    setHasStarted(true);
  }, [selected.id]);

  // Reklam bittikten sonra kullanıcının yayını başlatmak için bastığı manuel Play tuşu
  const handleResume = useCallback(() => {
    userPausedRef.current = false;
    setMuted(false);
    const v = videoRef.current;
    if (v) v.muted = false;
    // State'i değiştir → HLS effect tekrar tetiklenecek
    setAwaitingResume(false);
    // HLS'in attach olup data yüklemesi için 200ms'lik adımlarla 5sn boyunca play dene
    // Bu kullanıcı gesture context'i içinde play çağırmamızı garanti eder (autoplay policy)
    let tries = 0;
    const tryPlay = () => {
      const vv = videoRef.current;
      if (!vv) return;
      vv.muted = false;
      if (vv.readyState >= 2 && vv.paused) {
        vv.play().catch(() => { /* noop */ });
        return;
      }
      if (vv.readyState >= 2 && !vv.paused) {
        return; // zaten oynuyor
      }
      if (tries++ < 25) setTimeout(tryPlay, 200);
    };
    setTimeout(tryPlay, 300);
  }, []);

  // ===== Play/Pause — pause sonrası play'de CANLI YAYIN EDGE'ine atla =====
  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      userPausedRef.current = false;
      // Canlı yayın için (HLS m3u8): seekable.end - 2sn'ye atla
      // Bug #5 fix: HLS recover'a ihtiyaç varsa önce trigger et
      try {
        const h = hlsRef.current;
        if (h && v.seekable && v.seekable.length > 0) {
          const liveEdge = v.seekable.end(v.seekable.length - 1);
          if (Number.isFinite(liveEdge) && liveEdge - v.currentTime > 5) {
            v.currentTime = Math.max(0, liveEdge - 2);
          }
        }
        // Buffer stale ise media error recovery dene
        if (h && (h as any).media && v.error) {
          try { h.recoverMediaError(); } catch { /* noop */ }
        }
      } catch { /* noop */ }
      v.play().catch(() => {
        // Play başarısız → HLS startLoad dene
        try { hlsRef.current?.startLoad(); } catch { /* noop */ }
      });
    } else {
      userPausedRef.current = true;
      v.pause();
    }
  }, []);

  // Reklam doğal sonuna geldi → store'a yönlendir + kullanıcıyı manuel-play ekranına al
  const handleAdEnded = useCallback(() => {
    const ad = AD_LIBRARY[adIndex];
    setAdActive(false);
    setAwaitingResume(true);
    // Doğal bitiş = store yönlendirme (eski repo davranışı)
    if (ad?.store) redirectToStore(ad.store);
  }, [adIndex]);

  // ===== Stream Retry — bir sonraki sunucuya geçer, son sunucuda ise yenileme döngüsü =====
  const retryStream = useCallback(() => {
    setFreezeOverlay(false);
    stallCountRef.current = 0;
    networkRetryRef.current = 0;
    if (freezeAutoRetryRef.current) { clearTimeout(freezeAutoRetryRef.current); freezeAutoRetryRef.current = null; }
    setServerIndex((idx) => {
      // Mevcut sunucu son ise döngünün başına dön (eski repo davranışı)
      const next = idx < sources.length - 1 ? idx + 1 : 0;
      return next;
    });
  }, [sources.length]);

  // retryStream'i ref'e koy — interval ve event listener'lar erişebilsin
  useEffect(() => { retryStreamRef.current = retryStream; }, [retryStream]);

  // ===== Freeze overlay 5sn auto-retry timer (eski repo davranışı) =====
  useEffect(() => {
    if (!freezeOverlay) {
      if (freezeAutoRetryRef.current) { clearTimeout(freezeAutoRetryRef.current); freezeAutoRetryRef.current = null; }
      return;
    }
    if (freezeAutoRetryRef.current) clearTimeout(freezeAutoRetryRef.current);
    freezeAutoRetryRef.current = setTimeout(() => {
      freezeAutoRetryRef.current = null;
      retryStream();
    }, 5000);
    return () => {
      if (freezeAutoRetryRef.current) { clearTimeout(freezeAutoRetryRef.current); freezeAutoRetryRef.current = null; }
    };
  }, [freezeOverlay, retryStream]);

  const setQuality = useCallback((idx: number) => {
    // Bug #1 fix:
    //  - currentLevel anlık ABR'yi kapatır + segment iptal → glitch
    //  - nextLevel ise segment boundary'de seamless switch yapar
    //  - loadLevel da set edilerek HLS.js'in level caching'i temizlenir
    const h = hlsRef.current;
    if (h) {
      try {
        h.nextLevel = idx;          // segment boundary'de switch
        h.loadLevel = idx;           // load decision için de override
        // -1 (auto) durumunda nextLevel reset → ABR tekrar aktif
        if (idx === -1) {
          h.nextLevel = -1;
          h.loadLevel = -1;
          h.startLevel = -1;
        }
      } catch { /* HLS.js sürüm farkı — sessiz geç */ }
    }
    setCurrentLevel(idx);
    setQualityOpen(false);
  }, []);

  // Altyazı seç (id = -1 → kapalı)
  const setSubtitle = useCallback((id: number) => {
    if (hlsRef.current) hlsRef.current.subtitleTrack = id;
    setCurrentSubtitle(id);
    setSubtitleOpen(false);
  }, []);

  const setAudio = useCallback((id: number) => {
    if (hlsRef.current) { try { hlsRef.current.audioTrack = id; } catch { /* noop */ } }
    setCurrentAudio(id);
  }, []);
  const setVol = useCallback((val: number) => {
    const v = videoRef.current; if (!v) return;
    const nv = Math.max(0, Math.min(1, val));
    v.volume = nv;
    const m = nv === 0;
    v.muted = m; setMuted(m); setVolume(nv);
  }, []);
  const unmute = useCallback(() => {
    const v = videoRef.current; if (!v) return;
    v.muted = false; if (v.volume === 0) v.volume = 1;
    setMuted(false); setVolume(v.volume);
  }, []);
  const seekTo = useCallback((t: number) => {
    const v = videoRef.current; if (!v || !Number.isFinite(t)) return;
    try { v.currentTime = t; } catch { /* noop */ }
  }, []);
  // Klavye: Boşluk oynat/duraklat · M sessiz · F tam ekran
  const onKey = useCallback((e: React.KeyboardEvent) => {
    if (!hasStarted || adActive || awaitingResume) return;
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (e.code === 'KeyM') { e.preventDefault(); toggleMute(); }
    else if (e.code === 'KeyF') { e.preventDefault(); toggleFullscreen(); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasStarted, adActive, awaitingResume]);

  // Cast / AirPlay — Google Cast Sender SDK + Remote Playback API + iOS WebKit fallback
  // Bug #2 fix: Önce SDK'dan device picker'ı çağır → yakındaki Beko/Chromecast/Apple TV otomatik listelenir
  const toggleCast = useCallback(async () => {
    const v = videoRef.current;
    if (!v) return;
    let attempted = false;
    try {
      // 1. Google Cast Framework (Chromecast — Android TV, Beko Android TV vs.)
      const w = window as any;
      if (w.cast && w.cast.framework && w.chrome && w.chrome.cast) {
        const ctx = w.cast.framework.CastContext.getInstance();
        attempted = true;
        try {
          await ctx.requestSession();
          return;
        } catch (err: any) {
          // ErrorCode: cancel = user iptal etti, no_devices_available = cihaz yok
          if (err && err.code === 'cancel') return;
        }
      }
      // 2. iOS AirPlay
      // @ts-ignore
      if ((v as any).webkitShowPlaybackTargetPicker) {
        attempted = true;
        // @ts-ignore
        (v as any).webkitShowPlaybackTargetPicker();
        return;
      }
      // 3. W3C Remote Playback API (Chrome Android default)
      // @ts-ignore
      const remote = (v as any).remote;
      if (remote && typeof remote.prompt === 'function') {
        attempted = true;
        await remote.prompt();
        return;
      }
    } catch { /* noop */ }
    // Hiçbir yöntem cihaz bulamadı → kullanıcıya uyarı (alert yerine inline floating message)
    if (!attempted || true) {
      const div = document.createElement('div');
      div.setAttribute('data-testid', 'cast-toast');
      div.textContent = '📺 Yakında yayın cihazı bulunamadı. WiFi/Bluetooth açık olduğundan ve TV ile aynı ağda olduğundan emin olun.';
      Object.assign(div.style, {
        position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)',
        zIndex: '9999', maxWidth: '90vw', padding: '12px 18px',
        background: 'linear-gradient(135deg, rgba(20,12,28,0.96), rgba(8,4,16,0.96))',
        border: '1.5px solid var(--cyan, #00f0ff)', borderRadius: '8px',
        color: 'var(--cyan, #00f0ff)', fontFamily: 'VT323, monospace',
        fontSize: '13px', boxShadow: '0 8px 32px rgba(0,0,0,0.7), 0 0 16px rgba(0,240,255,0.4)',
        animation: 'bb-toast-in 0.25s ease-out',
      });
      document.body.appendChild(div);
      setTimeout(() => { try { div.remove(); } catch { /* noop */ } }, 4000);
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      if (videoRef.current) videoRef.current.muted = next;
      return next;
    });
  }, []);

  const togglePip = useCallback(async () => {
    const v = videoRef.current as any; if (!v) return;
    try {
      // Safari — presentation mode API
      if (typeof v.webkitSetPresentationMode === 'function' && !v.requestPictureInPicture) {
        v.webkitSetPresentationMode(v.webkitPresentationMode === 'picture-in-picture' ? 'inline' : 'picture-in-picture');
        return;
      }
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else if (v.requestPictureInPicture) {
        await v.requestPictureInPicture();
      } else if (typeof v.webkitSetPresentationMode === 'function') {
        v.webkitSetPresentationMode('picture-in-picture');
      }
    } catch { /* noop */ }
  }, []);

  const toggleFullscreen = useCallback(async () => {
    const w = wrapperRef.current as any; if (!w) return;
    const doc = document as any;
    try {
      if (!document.fullscreenElement && !doc.webkitFullscreenElement) {
        if (w.requestFullscreen) await w.requestFullscreen();
        else if (w.webkitRequestFullscreen) w.webkitRequestFullscreen();
        else if ((videoRef.current as any)?.webkitEnterFullscreen) (videoRef.current as any).webkitEnterFullscreen();
      } else {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
      }
    } catch { /* noop */ }
  }, []);

  // Close quality menu on outside click
  useEffect(() => {
    if (!qualityOpen && !subtitleOpen) return;
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (qualityOpen && !t?.closest('[data-testid="quality-selector"]')) setQualityOpen(false);
      if (subtitleOpen && !t?.closest('[data-testid="subtitle-selector"]')) setSubtitleOpen(false);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [qualityOpen, subtitleOpen]);

  const currentLabel = currentLevel === -1
    ? TR.AUTO
    : (qualityLabel(levels.find((l) => l.index === currentLevel)?.height || 0));

  // FIX: Mouse hareket / hover ile controls bar görünürlüğü.
  // Yayın pause iken → DAİMA görünür. Playing iken → mouse move'da 3sn boyunca göster.
  const showControls = useCallback(() => {
    setControlsVisible(true);
    if (controlsHideTimerRef.current) clearTimeout(controlsHideTimerRef.current);
    if (isPlaying) {
      controlsHideTimerRef.current = setTimeout(() => setControlsVisible(false), 2800);
    }
  }, [isPlaying]);

  // pause olursa hide timer iptal + görünür yap; play başlarsa 3sn sonra gizle
  useEffect(() => {
    if (!isPlaying) {
      if (controlsHideTimerRef.current) { clearTimeout(controlsHideTimerRef.current); controlsHideTimerRef.current = null; }
      setControlsVisible(true);
      return;
    }
    // play başladı → 3sn sonra gizle
    if (controlsHideTimerRef.current) clearTimeout(controlsHideTimerRef.current);
    controlsHideTimerRef.current = setTimeout(() => setControlsVisible(false), 2800);
    return () => {
      if (controlsHideTimerRef.current) { clearTimeout(controlsHideTimerRef.current); controlsHideTimerRef.current = null; }
    };
  }, [isPlaying]);

  return (
    <>
    <section className="main-content">
      <div className="player-layout" id="canli-yayin">
        <div
          ref={wrapperRef}
          className={`video-wrapper ${isFullscreen ? 'fullscreen-active' : ''} ${(!controlsVisible && isPlaying) ? 'pc-hide-cursor' : ''}`}
          data-testid="video-wrapper"
          tabIndex={0}
          onKeyDown={onKey}
          onMouseMove={showControls}
          onMouseEnter={showControls}
          onTouchStart={showControls}
        >
          <video
            ref={videoRef}
            className="video-player"
            playsInline
            muted={muted}
            /* TARAYICI NATIVE KONTROLLERİNİ KAPAT — biz kendi play/PiP/fullscreen kontrolümüzü kullanıyoruz.
               Bug #2 fix: disableRemotePlayback ve noremoteplayback KALDIRILDI — Cast SDK + Remote Playback API
               artık çalışıyor. Beko Android TV / Chromecast / AirPlay otomatik discovery yapabilsin. */
            controls={false}
            controlsList="nodownload nofullscreen"
            onClick={() => { if (hasStarted && !adActive && !awaitingResume && !streamError) togglePlay(); }}
            style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000', cursor: hasStarted && !adActive && !awaitingResume ? 'pointer' : 'default' }}
            data-testid="video-player"
          />

          {/* AD OVERLAY — SKIP YOK, kullanıcı sonuna kadar izlemek zorunda */}
          {adActive && (
            <div style={{ position: 'absolute', inset: 0, zIndex: 50 }} data-testid="ad-overlay">
              <video
                ref={adVideoRef}
                src={AD_LIBRARY[adIndex].src}
                autoPlay playsInline muted={muted}
                onEnded={handleAdEnded}
                onError={() => {
                  setAdActive(false);
                  setAwaitingResume(true);
                }}
                /* TARAYICI NATIVE KONTROLLERİNİ KAPAT — cast/play/PiP/fullscreen */
                controls={false}
                // @ts-ignore — non-standard but widely supported
                disableRemotePlayback
                disablePictureInPicture
                controlsList="nodownload nofullscreen noremoteplayback"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
                data-testid="ad-video"
              />
              {/* SOL ÜST — Reklam markası */}
              <div style={{
                position: 'absolute', top: 12, left: 12, padding: '8px 14px',
                borderRadius: 6,
                background: `linear-gradient(135deg, ${AD_LIBRARY[adIndex].color}ee, rgba(170,0,255,0.92))`,
                color: '#fff',
                fontFamily: 'Orbitron, sans-serif', fontSize: 11, fontWeight: 800, letterSpacing: 3,
                border: '1px solid rgba(255,255,255,0.45)',
                boxShadow: `0 4px 18px rgba(0,0,0,0.5), 0 0 24px ${AD_LIBRARY[adIndex].color}80`,
                userSelect: 'none', pointerEvents: 'none',
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <span style={{ width: 7, height: 7, background: '#fff', borderRadius: '50%', boxShadow: '0 0 8px #fff' }} />
                REKLAM · {AD_LIBRARY[adIndex].name.toUpperCase()}
              </div>
              {/* SAĞ ÜST — Geri sayım */}
              <div style={{
                position: 'absolute', top: 12, right: 12, padding: '8px 14px',
                borderRadius: 6,
                background: 'linear-gradient(90deg, rgba(8,4,14,0.88), rgba(20,8,30,0.88))',
                border: '1px solid rgba(0,240,255,0.35)',
                fontFamily: 'Orbitron, sans-serif', fontSize: 10, letterSpacing: 2,
                color: '#b8e8ff',
                display: 'flex', flexDirection: 'column', lineHeight: 1.2,
                backdropFilter: 'blur(6px)',
              }} data-testid="ad-countdown">
                <span style={{ color: 'var(--cyan)', fontSize: 9, opacity: 0.75 }}>YAYIN HAZIRLANIYOR</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#fff', letterSpacing: 1.5 }}>
                  Reklam {adRemainingSec} sn
                </span>
              </div>
              {/* ALT — boş — eski "atlanamaz" yazısı kaldırıldı */}
            </div>
          )}

          {/* MANUEL PLAY — Reklam bitti, kullanıcı yayını başlatmak için butona basmalı.
              FIX: noir_splash.jpg kız görseli KALDIRILDI. Sade siyah arka plan + büyük
              play butonu + "YAYINI BAŞLATMAK İÇİN TIKLA" CTA. */}
          {!adActive && awaitingResume && hasStarted && (
            <div className="overlay start-overlay" data-testid="resume-overlay">
              <div className="shelby-scene">
                {/* Sade siyah arka plan — kız görseli yok */}
                <div style={{
                  position: 'absolute', inset: 0,
                  background: 'radial-gradient(ellipse at center, rgba(20,8,30,0.95), #000 75%)',
                  zIndex: 0,
                }} />
                <div className="shelby-grain" style={{ zIndex: 1, opacity: 0.35 }} />
                <button
                  className="shelby-play-btn"
                  onClick={handleResume}
                  data-testid="resume-play-btn"
                  aria-label="Yayını başlat"
                  style={{ zIndex: 2 }}
                >
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="currentColor" style={{ marginLeft: 4 }}>
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>
                <div className="shelby-cta" style={{ zIndex: 2 }}>YAYINI BAŞLATMAK İÇİN TIKLA</div>
                <div className="shelby-quote" style={{ fontSize: 'clamp(12px, 1vw, 14px)', zIndex: 2 }}>
                  Reklam tamamlandı · {selected.name}
                </div>
              </div>
            </div>
          )}

          {/* FREEZE OVERLAY — yayın dondu / crash → tıklanırsa anında, otomatik 5sn sonra retry */}
          {freezeOverlay && !adActive && (
            <div
              className="overlay freeze-overlay"
              data-testid="freeze-overlay"
              onClick={retryStream}
              style={{ background: 'rgba(7,7,11,0.85)', zIndex: 40, cursor: 'pointer' }}
            >
              <svg width="56" height="56" viewBox="0 0 24 24" fill="var(--cyan)" style={{ filter: 'drop-shadow(0 0 10px var(--cyan))' }}>
                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
              </svg>
              <div style={{
                marginTop: 14, color: '#fff', fontFamily: 'Orbitron, sans-serif',
                fontSize: 16, letterSpacing: 4, textShadow: '0 0 12px var(--cyan)',
              }}>
                YAYIN DONDU
              </div>
              <div style={{
                marginTop: 6, color: 'var(--text-dim)', fontFamily: 'VT323, monospace',
                fontSize: 13, letterSpacing: 2,
              }}>
                Tıkla veya bekle — otomatik yenileniyor...
              </div>
            </div>
          )}

          {/* SHELBY SPLASH */}
          {!hasStarted && (
            <div className="overlay start-overlay" data-testid="start-overlay">
              <div className="shelby-scene">
                <div className="shelby-bg" style={{
                  backgroundImage: "url('/peaky_splash.jpg')", backgroundSize: 'cover',
                  backgroundPosition: 'center 20%', filter: 'brightness(0.95) contrast(1.1) saturate(1.02)',
                }} />
                <div className="shelby-overlay" />
                <div className="shelby-grain" />
                <button className="shelby-play-btn" onClick={handlePlay} data-testid="shelby-play-btn" aria-label="Başlat">
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="currentColor" style={{ marginLeft: 4 }}>
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>
                <div className="shelby-cta" data-testid="shelby-cta">BAŞLATMAK İÇİN TIKLA · PRESS PLAY</div>
                <div className="shelby-quote" data-testid="shelby-quote">&ldquo;VEFA BİLMEYENE VEDA YAKIŞIR&rdquo;</div>
                <div className="shelby-credit" data-testid="shelby-credit">— T. SHELBY</div>
              </div>
            </div>
          )}

          {/* MAINTENANCE / ERROR — bakım ekranı (poster → 5 sn → bakim_loop canvas, CRT, turuncu anahtar) */}
          {hasStarted && !adActive && streamError && (
            <MaintenanceScreen name={selected.name} text={streamError} variant={/yak[ıi]nda/i.test(streamError) ? 'soon' : /kaynak/i.test(streamError) ? 'nosource' : 'maintenance'} />
          )}

          {/* GROK KABUĞU — üst şerit, orta play, SESİ AÇ, alt kontrol barı (yalnız görünüm) */}
          {hasStarted && !adActive && !awaitingResume && !streamError && (
            <PlayerChrome
              visible={controlsVisible}
              started={hasStarted}
              isPlaying={isPlaying}
              muted={muted}
              volume={volume}
              isLive={isLiveStream}
              currentTime={curTime}
              duration={duration}
              buffered={bufferedEnd}
              levels={levels}
              currentLevel={currentLevel}
              activeHeight={activeHeight}
              subtitleTracks={subtitleTracks}
              currentSubtitle={currentSubtitle}
              audioTracks={audioTracks}
              currentAudio={currentAudio}
              netType={netType}
              fps={displayFps}
              formatBadge={formatBadge}
              hqMode={hqMode}
              batteryLow={batteryLow}
              isPip={isPip}
              isFullscreen={isFullscreen}
              channelName={selected.name}
              onTogglePlay={togglePlay}
              onToggleMute={toggleMute}
              onUnmute={unmute}
              onVolume={setVol}
              onSeek={seekTo}
              onQuality={setQuality}
              onSubtitle={setSubtitle}
              onAudio={setAudio}
              onToggleHq={() => { if (batteryLow && !hqMode) return; setHqMode((x) => !x); }}
              onPip={togglePip}
              onFullscreen={toggleFullscreen}
              onCast={toggleCast}
            />
          )}
        </div>
      </div>

      {/* HOVER-SHOW kontrolleri ve kanal kutusu (.sidebar-ch-btn.ch-tile, .ch-soon-banner) stilleri
          globals.css'in sonunda yer alıyor. Daha önce burada <style jsx> bloğu vardı;
          styled-jsx paketinin kaldırılmasıyla CSS global stylesheet'e taşındı. */}
    </section>

      {/* ===== BETZULA SHELBY BANNER — tıklayınca yönlendirir ===== */}
      <a
        className="shelby-strip"
        data-testid="shelby-banner-strip"
        href="https://t2ly.io/betzulacom"
        target="_blank"
        rel="noopener noreferrer sponsored"
        aria-label="Betzula"
      >
        <video src="/shelby_banner.mp4" autoPlay muted loop playsInline aria-hidden="true" />
      </a>

      {/* ===== FİLM PLAYER MODAL — neon çerçeveli ayrı player ===== */}
      {movieOpen && movie && (
        <MoviePlayer movie={movie} onClose={() => setMovieOpen(false)} />
      )}
    </>
  );
}
