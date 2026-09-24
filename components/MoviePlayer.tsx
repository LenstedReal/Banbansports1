'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import TurnstileWidget from './TurnstileWidget';
import * as sa from '../lib/streamAuth';

export type Movie = {
  id: string;
  title: string;
  title_en?: string;
  badge?: string;
  poster?: string;
  backdrop?: string;
  lang?: string;
  release_date?: string;
  stream_dub?: string;
  stream_sub?: string;
  stream_dub_label?: string;
  stream_dub_quality?: string;
  stream_sub_label?: string;
  stream_sub_quality?: string;
};

type Phase = 'lock' | 'splash' | 'adImage' | 'adVideo' | 'notice' | 'film';
type Track = 'dub' | 'sub';

const AD_IMAGE_S = 10;   // reklam görseli (1/2) süresi
const AD_SAFETY_S = 90;  // güvenlik: reklam asılı kalırsa filmi başlat
const SKIP_AFTER_S = 6;  // görsel reklamda atla butonu çıkma süresi (5-7 sn arası)
const NOTICE_S = 3;      // "reklama tabidir" uyarı süresi
const DP_URL = 'https://drpepper.store/';
const MC_URL = 'https://www.mcdonalds.com.tr/';
const HEARTBEAT_FALLBACK_S = 45;
const ENV_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '';

// hls.js destekliyse m=js (30 dk, xhrSetup her istekte güncel param basar); Safari native ise m=native (3 saat, URL yenilenemez)
const hlsMode = (): sa.HlsMode => (Hls.isSupported() ? 'js' : 'native');

const fmt = (s: number): string => {
  if (!isFinite(s) || s < 0) return '00:00';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const mm = String(m).padStart(2, '0');
  const ss = String(sec).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

export default function MoviePlayer({ movie, onClose }: { movie: Movie; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const adVideoRef = useRef<HTMLVideoElement>(null);
  const preloadVideoRef = useRef<HTMLVideoElement>(null);
  const dpRef = useRef<HTMLButtonElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const preSubHlsRef = useRef<Hls | null>(null);
  const adTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pointerRef = useRef<{ x: number; y: number; t: number } | null>(null);
  const lastTickRef = useRef(0);
  const dpAlphaRef = useRef<CanvasRenderingContext2D | null>(null);
  const urlsRef = useRef<Partial<Record<Track, sa.SignedUrl>>>({});
  const leaseRef = useRef<string>('');
  const hbTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const trackRef = useRef<Track>('dub');
  const phaseRef = useRef<Phase>('lock');

  const [phase, setPhaseState] = useState<Phase>('lock');
  const [authU, setAuthU] = useState('');
  const [authP, setAuthP] = useState('');
  const [authErr, setAuthErr] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [credsOpen, setCredsOpen] = useState(false);
  const [siteKey, setSiteKey] = useState(ENV_SITE_KEY);
  const [tsToken, setTsToken] = useState('');
  const [tsReset, setTsReset] = useState(0);
  const [copied, setCopied] = useState<'user' | 'pass' | null>(null);
  const [adElapsed, setAdElapsed] = useState(0);
  const [adVideoDur, setAdVideoDur] = useState(20);
  const [adVideoLeft, setAdVideoLeft] = useState(20);
  const [track, setTrack] = useState<Track>('dub');
  const [askVisible, setAskVisible] = useState(false);
  const [trackMenuOpen, setTrackMenuOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffering, setBuffering] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);

  const dubUrl = movie.stream_dub || 'https://stream.lenstedreal.xyz/stream.m3u8';
  const subUrl = movie.stream_sub || 'https://stream1.lenstedreal.xyz/stream.m3u8';
  void dubUrl; void subUrl; // imzalı URL /url'den gelir; bunlar yalnızca tip uyumluluğu için

  const setPhase = (p: Phase) => { phaseRef.current = p; setPhaseState(p); };

  // Oturum düştü (refresh de başarısız) → kilit ekranına dön
  const onAuthLost = useCallback(() => {
    if (hbTimerRef.current) { clearInterval(hbTimerRef.current); hbTimerRef.current = null; }
    leaseRef.current = '';
    try { hlsRef.current?.stopLoad(); } catch { /* noop */ }
    try { videoRef.current?.pause(); } catch { /* noop */ }
    setErrorMsg('');
    setPhase('lock');
  }, []);

  // /url → HMAC imzalı m3u8 (param seti urlsRef'te; tokenXhr her istekte basar)
  const fetchUrl = useCallback(async (t: Track): Promise<string | null> => {
    try {
      const d = await sa.getStreamUrl(movie.id, t, hlsMode());
      urlsRef.current[t] = d;
      return d.url;
    } catch (e: any) {
      if (e instanceof sa.StreamAuthError && e.status === 401) onAuthLost();
      else setErrorMsg('YAYIN ADRESİ ALINAMADI — TEKRAR DENEYİN');
      return null;
    }
  }, [movie.id, onAuthLost]);

  // Lease: /start → 45 sn heartbeat → unmount/beforeunload'da /stop. Family başına eşzamanlı sınır 409 döner.
  const endLease = useCallback((beacon = false) => {
    if (hbTimerRef.current) { clearInterval(hbTimerRef.current); hbTimerRef.current = null; }
    const id = leaseRef.current;
    leaseRef.current = '';
    if (id) sa.stopLease(id, beacon);
  }, []);

  const beginLease = useCallback(async (t: Track): Promise<boolean> => {
    try {
      const d = await sa.startLease(movie.id, t);
      leaseRef.current = d.lease_id;
      if (hbTimerRef.current) clearInterval(hbTimerRef.current);
      hbTimerRef.current = setInterval(async () => {
        if (!leaseRef.current) return;
        try { await sa.heartbeat(leaseRef.current); } catch (e: any) {
          if (e instanceof sa.StreamAuthError && e.status === 404) { leaseRef.current = ''; beginLease(trackRef.current); }
          else if (e instanceof sa.StreamAuthError && e.status === 401) onAuthLost();
        }
      }, (d.heartbeat_interval || HEARTBEAT_FALLBACK_S) * 1000);
      return true;
    } catch (e: any) {
      if (e instanceof sa.StreamAuthError && e.status === 409) {
        setErrorMsg('EŞ ZAMANLI İZLEME SINIRI — DİĞER SEKMEYİ KAPATIP TEKRAR DENEYİN');
        try { hlsRef.current?.stopLoad(); } catch { /* noop */ }
        try { videoRef.current?.pause(); } catch { /* noop */ }
      } else if (e instanceof sa.StreamAuthError && e.status === 401) onAuthLost();
      return false;
    }
  }, [movie.id, onAuthLost]);

  // Açılışta cookie ile /refresh denenir → oturum varsa kilit ekranı atlanır
  useEffect(() => {
    let alive = true;
    (sa.hasAccess() ? Promise.resolve(true) : sa.refresh()).then((ok) => {
      if (alive && ok && phaseRef.current === 'lock') setPhase('splash');
    });
    return () => { alive = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Turnstile site key — backend config'ten (secret asla frontend'e gelmez)
  useEffect(() => {
    if (ENV_SITE_KEY) return;
    let alive = true;
    fetch('/api/stream-auth/config', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d?.turnstile_site_key) setSiteKey(d.turnstile_site_key); })
      .catch(() => { /* noop */ });
    return () => { alive = false; };
  }, []);

  // Sessiz yenileme — 22. dakikada access yenilenir, ardından yeni /url param seti alınır.
  // hls.js source DEĞİŞMEZ; xhrSetup bir sonraki segmentten itibaren yeni param'ı basar → film kesilmez.
  useEffect(() => {
    if (phase !== 'film' && phase !== 'adImage' && phase !== 'adVideo' && phase !== 'notice') return;
    const tick = async () => {
      if (!sa.shouldRefresh()) return;
      if (!(await sa.refresh())) { if (!sa.hasAccess()) onAuthLost(); return; }
      if (hlsMode() !== 'js') return; // native: 3 saatlik URL, yenilenemez
      for (const t of Object.keys(urlsRef.current) as Track[]) await fetchUrl(t);
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [phase, fetchUrl, onAuthLost]);

  // Kopyalama geri bildirimi — görsel çip + titreşim
  const doCopy = (what: 'user' | 'pass', text: string) => {
    try {
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text);
      else {
        const ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
      }
    } catch { /* noop */ }
    try { navigator.vibrate?.(60); } catch { /* noop */ }
    setCopied(what);
    window.setTimeout(() => setCopied(null), 1600);
  };

  // Korumalı içerik doğrulaması — üyelik DEĞİLDİR; oturum (refresh cookie) + 30 dk Access JWT (bellek)
  const handleLogin = async () => {
    if (!tsToken) { setAuthErr('Bot doğrulaması (Turnstile) tamamlanmadı'); return; }
    setAuthBusy(true);
    setAuthErr('');
    try {
      const res = await sa.login(authU, authP, tsToken);
      if (!res.ok) {
        // Turnstile token tek kullanımlık — her başarısız denemede widget sıfırlanır
        setTsToken(''); setTsReset((n) => n + 1);
        if (res.status === 401) setAuthErr('Erişim bilgileri hatalı — ŞİFRE AL ile bilgileri görüntüleyin');
        else if (res.status === 429) setAuthErr('Çok fazla deneme — birkaç dakika sonra tekrar deneyin');
        else setAuthErr(res.detail || 'Bot doğrulaması başarısız — tekrar deneyin');
        return;
      }
      setPhase('splash');
    } catch {
      setAuthErr('Doğrulama sunucusuna ulaşılamadı');
    } finally {
      setAuthBusy(false);
    }
  };

  // === HLS.js — .m3u8 tarayıcıda indirme değil, doğrudan video olarak oynasın ===
  // Her m3u8 + .ts isteğine güncel HMAC param seti basılır (exp,sid,did,m,st,sig) — segmentler imzasız ASLA istenmez
  const tokenXhr = useCallback((key: Track) => (xhr: XMLHttpRequest, url: string) => {
    const p = urlsRef.current[key]?.params;
    if (!p) return;
    try {
      xhr.open('GET', sa.applyParams(url, p), true);
    } catch { /* noop */ }
  }, []);

  const createHls = useCallback((video: HTMLVideoElement, url: string, key: Track): Hls | null => {
    if (Hls.isSupported()) {
      // Sınırlı buffer: ~2 segment ileri, 40 MB tavan — filmin tamamı asla indirilmez
      const hls = new Hls({
        startPosition: 0,
        maxBufferLength: 20,
        maxMaxBufferLength: 30,
        maxBufferSize: 40 * 1000 * 1000,
        backBufferLength: 20,
        startFragPrefetch: false,
        xhrSetup: tokenXhr(key),
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      let mediaRecoveries = 0;
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR && mediaRecoveries < 3) { mediaRecoveries += 1; hls.recoverMediaError(); }
        else { try { hls.stopLoad(); } catch { /* noop */ } setErrorMsg('YAYIN YÜKLENEMEDİ — TEKRAR DENEYİN'); } // sonsuz recover döngüsü = boşa segment isteği (R2 maliyeti)
      });
      return hls;
    }
    video.src = url; // Safari — native HLS (Worker manifest'i token'lı yeniden yazar)
    return null;
  }, [tokenXhr]);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v || phaseRef.current !== 'film') return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  }, []);

  // Body scroll kilidi + klavye
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.fullscreenElement) onClose();
      if (e.key === ' ' && phaseRef.current === 'film') { e.preventDefault(); togglePlay(); }
    };
    window.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener('keydown', onKey); };
  }, [onClose, togglePlay]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  // Unmount temizliği — lease bırakılır (/stop)
  useEffect(() => () => {
    if (adTimerRef.current) clearInterval(adTimerRef.current);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    endLease();
    try { hlsRef.current?.destroy(); } catch { /* noop */ }
    try { preSubHlsRef.current?.destroy(); } catch { /* noop */ }
  }, [endLease]);

  const showControls = useCallback(() => {
    setControlsVisible(true);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      const v = videoRef.current;
      if (v && !v.paused) setControlsVisible(false);
    }, 3000);
  }, []);

  // === PLAY → REKLAM 1/2 başlar + TR DUBLAJ arka planda PRELOAD edilir (/url + /start) ===
  const handleStart = () => {
    setPhase('adImage');
    setAdElapsed(0);
    trackRef.current = 'dub';
    (async () => {
      const url = await fetchUrl('dub');
      const v = videoRef.current;
      if (!url || !v || phaseRef.current === 'lock') return;
      if (!(await beginLease('dub'))) return;
      v.muted = true; // preload sırasında sessiz
      hlsRef.current = createHls(v, url, 'dub');
      if (!hlsRef.current) { try { v.load(); } catch { /* noop */ } }
    })();
    lastTickRef.current = Date.now();
    adTimerRef.current = setInterval(() => {
      // Sekme gizliyken (reklamdan siteye gidildiğinde) sayaç DURUR — reklam asla kendiliğinden atlanmaz
      if (document.hidden) return;
      // Dönüşte tarayıcının biriktirdiği tick'ler PATLAMAZ — saniyede en fazla 1 artış
      const now = Date.now();
      if (now - lastTickRef.current < 900) return;
      lastTickRef.current = now;
      setAdElapsed((s) => s + 1);
    }, 1000);
  };

  // R2 MALİYET KALKANI: sekme gizlenince reklam + HLS indirmesi ANINDA durur, dönünce devam eder
  useEffect(() => {
    const onVis = () => {
      const av = adVideoRef.current;
      const p = phaseRef.current;
      if (document.hidden) {
        if (p === 'adImage' || p === 'adVideo') { try { av?.pause(); } catch { /* noop */ } }
        try { videoRef.current?.pause(); } catch { /* noop */ }
        try { hlsRef.current?.stopLoad(); } catch { /* noop */ }
        try { preSubHlsRef.current?.stopLoad(); } catch { /* noop */ }
      } else {
        lastTickRef.current = Date.now(); // dönüşte sayaç sıfır referansla devam eder — reklam atlanmış gibi olmaz
        if (p === 'adVideo') av?.play().catch(() => {});
        try { hlsRef.current?.startLoad(); } catch { /* noop */ }
        try { preSubHlsRef.current?.startLoad(); } catch { /* noop */ }
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  // Hard reset: sekme/tarayıcı kapanışında kaynak boşaltılır, lease beacon ile bırakılır — süre hatırlama YOK
  useEffect(() => {
    const onUnload = () => {
      endLease(true);
      try { hlsRef.current?.destroy(); } catch { /* noop */ }
      try { preSubHlsRef.current?.destroy(); } catch { /* noop */ }
      const v = videoRef.current;
      if (v) { try { v.removeAttribute('src'); v.load(); } catch { /* noop */ } }
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, [endLease]);

  // === Reklam biter/atlanır → 3 sn uyarı + ALTYAZILI yayın arka planda PRELOAD ===
  const endAd = useCallback(() => {
    const p = phaseRef.current;
    if (p !== 'adImage' && p !== 'adVideo') return;
    if (adTimerRef.current) { clearInterval(adTimerRef.current); adTimerRef.current = null; }
    const av = adVideoRef.current;
    if (av) { try { av.pause(); } catch { /* noop */ } }
    setPhase('notice');
    // 3 sn'lik uyarı esnasında stream1 (orijinal ses / TR altyazı) hazırlanır — kendi imzalı /url'i ile
    const pv = preloadVideoRef.current;
    if (pv && Hls.isSupported() && !preSubHlsRef.current) {
      fetchUrl('sub').then((url) => {
        if (!url || preSubHlsRef.current || phaseRef.current === 'lock') return;
        // Yalnızca başlangıç segmentleri (~1 segment, 20 MB tavan) — imzalı, bypass yok
        const h = new Hls({ startPosition: 0, maxBufferLength: 10, maxMaxBufferLength: 10, maxBufferSize: 20 * 1000 * 1000, startFragPrefetch: false, xhrSetup: tokenXhr('sub') });
        h.loadSource(url);
        h.attachMedia(pv);
        h.on(Hls.Events.ERROR, (_e, d) => { if (d.fatal) { try { h.destroy(); } catch { /* noop */ } if (preSubHlsRef.current === h) preSubHlsRef.current = null; } });
        preSubHlsRef.current = h;
      });
    }
    setTimeout(() => {
      // film durmadan/donmadan varsayılan TR DUBLAJ ile başlar
      setPhase('film');
      const v = videoRef.current;
      if (v) { v.muted = false; v.volume = volume; v.play().catch(() => {}); }
      setAskVisible(true);
      showControls();
      setTimeout(() => setAskVisible(false), 14000);
    }, NOTICE_S * 1000);
  }, [volume, showControls, tokenXhr, fetchUrl]);

  // Reklam faz geçişleri
  useEffect(() => {
    if (phase === 'adImage' && adElapsed >= AD_IMAGE_S) {
      setPhase('adVideo');
      const av = adVideoRef.current;
      if (av) { av.muted = false; av.play().catch(() => { av.muted = true; av.play().catch(() => {}); }); }
      return;
    }
    if ((phase === 'adImage' || phase === 'adVideo') && adElapsed >= AD_SAFETY_S) endAd();
  }, [adElapsed, phase, endAd]);

  // Görsel reklamı (1/2) atla → atlanamaz video reklama (2/2) geç
  const skipToVideo = () => {
    if (phaseRef.current !== 'adImage') return;
    setAdElapsed(AD_IMAGE_S);
  };

  // Kutu görselinin alfa haritası — sadece GÖRÜNÜR piksele tıklama geçerli
  useEffect(() => {
    const img = new Image();
    img.src = '/ads/ad_cans.png';
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext('2d', { willReadFrequently: true });
      if (ctx) { ctx.drawImage(img, 0, 0); dpAlphaRef.current = ctx; }
    };
  }, []);

  // === Dr Pepper — kasıtlı tıklama algısı (kaydırma/yanlış dokunma sayılmaz) ===
  const onDpDown = (e: React.PointerEvent) => {
    pointerRef.current = { x: e.clientX, y: e.clientY, t: Date.now() };
  };
  const onDpUp = (e: React.PointerEvent) => {
    const p = pointerRef.current;
    pointerRef.current = null;
    if (!p) return;
    const dx = Math.abs(e.clientX - p.x);
    const dy = Math.abs(e.clientY - p.y);
    const dt = Date.now() - p.t;
    if (dx > 12 || dy > 12 || dt > 600) return; // hassasiyet filtresi — yanlışlıkla dokunma sayılmaz
    const el = dpRef.current;
    if (!el) return;
    // Piksel-hassas kontrol: kutuların ETRAFINDAKİ şeffaf boşluğa dokunmak SAYILMAZ
    const ctx = dpAlphaRef.current;
    if (ctx) {
      const r = el.getBoundingClientRect();
      const cw = ctx.canvas.width;
      const ch = ctx.canvas.height;
      const px = Math.max(0, Math.min(cw - 1, Math.floor(((e.clientX - r.left) / r.width) * cw)));
      const py = Math.max(0, Math.min(ch - 1, Math.floor(((e.clientY - r.top) / r.height) * ch)));
      try {
        if (ctx.getImageData(px, py, 1, 1).data[3] < 20) return; // şeffaf piksel → yok say
      } catch { /* canvas erişilemezse eski davranış */ }
    }
    el.classList.remove('dp-clicked');
    void el.offsetWidth;
    el.classList.add('dp-clicked');
    setTimeout(() => el.classList.remove('dp-clicked'), 650);
    // Sayfa yeni sekmede açılır — reklam ATLANMAZ, kaldığı yerden devam eder
    setTimeout(() => { try { window.open(DP_URL, '_blank', 'noopener'); } catch { /* noop */ } }, 220);
  };

  // === KAYNAK DEĞİŞİMİ — TV kanalı gibi: yeni imzalı /url, süre SIFIRDAN başlar ===
  const switchTrack = async (t: Track) => {
    setTrackMenuOpen(false);
    if (t === track) { setAskVisible(false); return; }
    const v = videoRef.current;
    if (!v) return;
    setTrack(t);
    trackRef.current = t;
    setAskVisible(false);
    if (hlsRef.current) { try { hlsRef.current.destroy(); } catch { /* noop */ } hlsRef.current = null; }
    v.removeAttribute('src');
    const url = urlsRef.current[t]?.url || await fetchUrl(t);
    if (!url) return;
    beginLease(t);
    if (t === 'sub' && preSubHlsRef.current) {
      const h = preSubHlsRef.current;
      preSubHlsRef.current = null;
      try { h.detachMedia(); h.attachMedia(v); hlsRef.current = h; }
      catch { try { h.destroy(); } catch { /* noop */ } hlsRef.current = createHls(v, url, t); }
    } else {
      hlsRef.current = createHls(v, url, t);
      if (!hlsRef.current) { try { v.load(); } catch { /* noop */ } }
    }
    try { v.currentTime = 0; } catch { /* noop */ }
    setCurrent(0);
    setDuration(0);
    v.muted = false;
    v.play().catch(() => {});
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };

  const onVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    const v = videoRef.current;
    if (v) { v.volume = val; v.muted = val === 0; setMuted(val === 0); }
  };

  const onSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = parseFloat(e.target.value);
    const v = videoRef.current;
    if (v) { v.currentTime = t; setCurrent(t); }
  };

  const toggleFullscreen = () => {
    const wrap = wrapRef.current as any;
    const v = videoRef.current as any;
    const doc = document as any;
    if (document.fullscreenElement || doc.webkitFullscreenElement) {
      if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
      else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
      return;
    }
    if (wrap?.requestFullscreen) wrap.requestFullscreen().catch(() => {});
    else if (wrap?.webkitRequestFullscreen) wrap.webkitRequestFullscreen();
    else if (v?.webkitEnterFullscreen) v.webkitEnterFullscreen();
  };

  const togglePip = async () => {
    const v = videoRef.current as any;
    if (!v) return;
    try {
      if (typeof v.webkitSetPresentationMode === 'function') {
        v.webkitSetPresentationMode(v.webkitPresentationMode === 'picture-in-picture' ? 'inline' : 'picture-in-picture');
        return;
      }
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else if (v.requestPictureInPicture) await v.requestPictureInPicture();
    } catch { /* noop */ }
  };

  const retryVideo = async () => {
    const v = videoRef.current;
    setErrorMsg('');
    if (!v) return;
    if (hlsRef.current) { try { hlsRef.current.destroy(); } catch { /* noop */ } hlsRef.current = null; }
    v.removeAttribute('src');
    const url = await fetchUrl(track);   // her denemede taze imzalı URL
    if (!url) return;
    if (!leaseRef.current && !(await beginLease(track))) return;
    hlsRef.current = createHls(v, url, track);
    if (!hlsRef.current) { try { v.load(); } catch { /* noop */ } }
    if (phaseRef.current === 'film') v.play().catch(() => {});
  };

  // Cast: Chromecast → /cast-token (cs'e bağlı, m=native, 3 saat) → loadMedia; remote.prompt() AirPlay için kalır
  const toggleCast = useCallback(async () => {
    const v = videoRef.current;
    if (!v) return;
    try {
      const w = window as any;
      if (w.cast && w.cast.framework && w.chrome && w.chrome.cast) {
        try {
          const ctx = w.cast.framework.CastContext.getInstance();
          try {
            ctx.setOptions({
              receiverApplicationId: w.chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
              autoJoinPolicy: w.chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
            });
          } catch { /* zaten init */ }
          await ctx.requestSession();
          const session = ctx.getCurrentSession();
          if (session) {
            const ct = await sa.getCastToken(movie.id, trackRef.current);
            const info = new w.chrome.cast.media.MediaInfo(ct.media_url, ct.content_type || 'application/x-mpegURL');
            info.streamType = w.chrome.cast.media.StreamType.BUFFERED;
            info.metadata = new w.chrome.cast.media.MovieMediaMetadata();
            info.metadata.title = movie.title_en || movie.title;
            const req = new w.chrome.cast.media.LoadRequest(info);
            req.currentTime = Math.max(0, v.currentTime || 0);
            await session.loadMedia(req);
            try { v.pause(); } catch { /* noop */ }
          }
          return;
        } catch (err: any) {
          if (err && (err.code === 'cancel' || err === 'cancel')) return;
          if (err instanceof sa.StreamAuthError && err.status === 401) { onAuthLost(); return; }
        }
      }
      const remote = (v as any).remote;
      if (remote && typeof remote.prompt === 'function') {
        try { await remote.prompt(); return; } catch (err: any) {
          if (err && (err.name === 'NotAllowedError' || err.name === 'AbortError')) return;
        }
      }
      if ((v as any).webkitShowPlaybackTargetPicker) {
        (v as any).webkitShowPlaybackTargetPicker();
        return;
      }
    } catch { /* noop */ }
    const div = document.createElement('div');
    div.setAttribute('data-testid', 'movie-cast-toast');
    div.textContent = '📺 Yakında yayın cihazı bulunamadı. TV ile aynı WiFi ağında olduğundan emin olun.';
    Object.assign(div.style, {
      position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)',
      zIndex: '9999', maxWidth: '90vw', padding: '12px 18px',
      background: 'linear-gradient(135deg, rgba(20,12,28,0.96), rgba(8,4,16,0.96))',
      border: '1.5px solid var(--cyan, #00f0ff)', borderRadius: '8px',
      color: 'var(--cyan, #00f0ff)', fontFamily: 'VT323, monospace', fontSize: '13px',
      boxShadow: '0 8px 32px rgba(0,0,0,0.7), 0 0 16px rgba(0,240,255,0.4)',
    });
    document.body.appendChild(div);
    setTimeout(() => { try { div.remove(); } catch { /* noop */ } }, 4000);
  }, [movie.id, movie.title, movie.title_en, onAuthLost]);

  const handleClose = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    const v = videoRef.current;
    if (v) { try { v.pause(); } catch { /* noop */ } }
    onClose();
  };

  const started = phase !== 'splash';
  const inAd = phase === 'adImage' || phase === 'adVideo';
  const adRemaining = phase === 'adImage'
    ? Math.max(0, AD_IMAGE_S - adElapsed) + Math.ceil(adVideoDur)
    : adVideoLeft;
  void started;

  return (
    <div className="movie-modal-backdrop" data-testid="movie-player-modal" onClick={handleClose}>
      <div className={`movie-modal${isFullscreen ? ' is-fs' : ''}`} onClick={(e) => e.stopPropagation()}>
        <button className="movie-close-btn" data-testid="movie-close-btn" onClick={handleClose} aria-label="Kapat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
          </svg>
        </button>

        <div
          ref={wrapRef}
          className="movie-video-wrap"
          onMouseMove={showControls}
          onTouchStart={showControls}
          onClick={() => { if (phase === 'film' && !errorMsg) togglePlay(); }}
        >
          {/* ANA FİLM VİDEOSU — reklam sırasında arka planda preload edilir */}
          <video
            ref={videoRef}
            className="movie-video"
            data-testid="movie-video"
            playsInline
            preload="auto"
            onPlay={() => { setPlaying(true); showControls(); }}
            onPause={() => { setPlaying(false); setControlsVisible(true); }}
            onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
            onDurationChange={(e) => setDuration(e.currentTarget.duration || 0)}
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
            onWaiting={() => { if (phaseRef.current === 'film') setBuffering(true); }}
            onPlaying={() => setBuffering(false)}
            onError={() => { if (phaseRef.current === 'film') setErrorMsg('VİDEO YÜKLENEMEDİ — SAYFAYI YENİLEYİP TEKRAR DENEYİN'); }}
          />

          {/* Gizli preload video — altyazılı yayın (stream1) hazırlığı */}
          <video ref={preloadVideoRef} style={{ display: 'none' }} muted playsInline preload="auto" aria-hidden data-testid="movie-preload-video" />

          {/* CRT scanline efekti */}
          <div className="movie-crt" aria-hidden="true" />

          {/* 🔒 KORUMALI / ŞİFRELİ İÇERİK — üyelik değil, yayın erişim doğrulaması */}
          {phase === 'lock' && (
            <div className="mp-lock" data-testid="movie-lock-panel" onClick={(e) => e.stopPropagation()}>
              <div className="mp-lock-bg" aria-hidden="true" style={{ backgroundImage: `url('${movie.backdrop || movie.poster || '/spiderman_backdrop.jpg'}')` }} />
              <div className="mp-lock-card">
                <div className="mp-lock-icon" aria-hidden="true">
                  <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" />
                  </svg>
                </div>
                <div className="mp-lock-kicker" data-testid="lock-kicker">BANBANSPORTS · ORİJİNAL YAYIN</div>
                <div className="mp-lock-title">KORUMALI / ŞİFRELİ İÇERİK</div>
                <div className="mp-lock-sub" data-testid="lock-subtitle">{movie.title} · erişim için yayın şifresi gereklidir</div>
                <input className="mp-lock-input" data-testid="lock-user-input" placeholder="Kullanıcı Adı / ID" value={authU} onChange={(e) => setAuthU(e.target.value)} autoComplete="off" />
                <input className="mp-lock-input" data-testid="lock-pass-input" type="password" placeholder="Şifre" value={authP} onChange={(e) => setAuthP(e.target.value)} autoComplete="off" />
                {siteKey ? (
                  <TurnstileWidget siteKey={siteKey} onToken={setTsToken} resetSignal={tsReset} />
                ) : (
                  <div className="mp-turnstile mp-turnstile-wait" data-testid="lock-turnstile-wait">BOT DOĞRULAMASI YÜKLENİYOR…</div>
                )}
                {authErr && <div className="mp-lock-err" data-testid="lock-error">{authErr}</div>}
                <div className="mp-lock-btns">
                  <button className="mp-lock-btn mp-lock-primary" data-testid="lock-login-btn" onClick={handleLogin} disabled={authBusy || !tsToken}>
                    {authBusy ? 'DOĞRULANIYOR…' : tsToken ? 'GİRİŞ YAP' : 'DOĞRULAMA BEKLENİYOR…'}
                  </button>
                </div>
                <div className="mp-lock-note">Bu bir üyelik girişi değildir — korumalı yayına erişim doğrulamasıdır. Erişim 30 dakika geçerlidir.</div>
              </div>
              {/* ŞİFRE AL — player'ın sol alt köşesi */}
              <button className="mp-getpass-btn" data-testid="lock-getpass-btn" onClick={() => setCredsOpen((s) => !s)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <path d="M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z" />
                </svg>
                ŞİFRE AL
              </button>
              {credsOpen && (
                <div className="mp-lock-creds mp-creds-float" data-testid="lock-creds">
                  <div className="mp-creds-head">ERİŞİM BİLGİLERİ</div>
                  <div>Kullanıcı Adı / ID: <b>lenstedreal_marka</b> <button className={`mp-copy${copied === 'user' ? ' copied' : ''}`} data-testid="copy-user-btn" onClick={() => doCopy('user', 'lenstedreal_marka')}>{copied === 'user' ? '✓' : '⧉'}</button></div>
                  <div>Şifre: <b>zirvedeyiz</b> <button className={`mp-copy${copied === 'pass' ? ' copied' : ''}`} data-testid="copy-pass-btn" onClick={() => doCopy('pass', 'zirvedeyiz')}>{copied === 'pass' ? '✓' : '⧉'}</button></div>
                  {copied && <div className="mp-copied-toast" data-testid="copied-toast">KOPYALANDI ✓</div>}
                </div>
              )}
            </div>
          )}

          {/* SPLASH — filmin poster'ı + PRESS PLAY */}
          {phase === 'splash' && (
            <div className="overlay start-overlay movie-splash" data-testid="movie-splash" onClick={(e) => e.stopPropagation()}>
              <div className="shelby-scene">
                <div
                  className="shelby-bg"
                  style={{
                    backgroundImage: `url('${movie.backdrop || movie.poster || '/spiderman_backdrop_v2.jpg'}')`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    filter: 'brightness(0.95) contrast(1.06) saturate(1.08)',
                  }}
                />
                <div className="shelby-overlay" />
                <div className="shelby-grain" />
                <button className="shelby-play-btn" data-testid="movie-play-btn" onClick={handleStart} aria-label="Filmi başlat">
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="currentColor" style={{ marginLeft: 4 }}>
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>
                <div className="shelby-cta">BAŞLATMAK İÇİN TIKLA · PRESS PLAY</div>
                <div className="shelby-quote">{movie.title}</div>
                <div className="shelby-credit">— {movie.lang || 'TÜRKÇE DUBLAJ · TÜRKÇE ALTYAZI'} · HD{movie.release_date ? ` · ${movie.release_date}` : ''}</div>
              </div>
            </div>
          )}

          {/* ===== REKLAM SAHNESİ (1/2 görsel → 2/2 video) ===== */}
          {inAd && (
            <div className="mp-ad-stage" data-testid="movie-ad-stage" onClick={(e) => e.stopPropagation()}>
              {phase === 'adImage' && (
                <div className="mp-ad-imgwrap">
                  <div className="mp-ad-imginner">
                    <img
                      className="mp-ad-img"
                      data-testid="movie-ad-image"
                      src="/ads/ad_base.png"
                      alt="Reklam"
                      draggable={false}
                    />
                    {/* Dr Pepper kutuları — fotoğraftan ayrık katman, yukarıdan sahneye iner, SADECE bu tıklanabilir */}
                    <button
                      ref={dpRef}
                      className="mp-dp-cans"
                      data-testid="movie-dp-cans"
                      aria-label="Dr Pepper"
                      onPointerDown={onDpDown}
                      onPointerUp={onDpUp}
                      onPointerCancel={() => { pointerRef.current = null; }}
                    >
                      <img src="/ads/ad_cans.png" alt="" draggable={false} />
                      <span className="mp-dp-cta" data-testid="movie-ad-cta" aria-hidden="true">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="#fff">
                          <path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z" />
                        </svg>
                      </span>
                    </button>
                  </div>
                </div>
              )}
              <video
                ref={adVideoRef}
                className="mp-ad-video"
                data-testid="movie-ad-video"
                src="/ads/ad_video.mp4"
                preload="auto"
                playsInline
                controls={false}
                // @ts-ignore — non-standard but widely supported
                disableRemotePlayback
                disablePictureInPicture
                controlsList="nodownload nofullscreen noremoteplayback"
                style={{ display: phase === 'adVideo' ? 'block' : 'none' }}
                onLoadedMetadata={(e) => {
                  const d = e.currentTarget.duration;
                  if (isFinite(d) && d > 0) { setAdVideoDur(d); setAdVideoLeft(Math.ceil(d)); }
                }}
                onTimeUpdate={(e) => setAdVideoLeft(Math.max(0, Math.ceil((e.currentTarget.duration || 0) - e.currentTarget.currentTime)))}
                onEnded={() => {
                  // McDonald's reklamı DOĞAL sonuna geldi → reklam verenin sitesi açılır, uyarı ekranına geçilir
                  try { window.open(MC_URL, '_blank', 'noopener'); } catch { /* noop */ }
                  endAd();
                }}
                onError={() => { if (phaseRef.current === 'adVideo') endAd(); }}
              />
              <div className="mp-ad-badge" data-testid="movie-ad-badge">
                <span className="mp-ad-dot" aria-hidden="true" />
                {phase === 'adImage' ? 'REKLAM 1/2 · DR PEPPER' : "REKLAM 2/2 · McDONALD'S"}
              </div>
              <div className="mp-ad-count" data-testid="movie-ad-count">
                <span className="mp-ad-count-label">FİLM HAZIRLANIYOR</span>
                <span className="mp-ad-count-time">Reklam {adRemaining} sn</span>
              </div>
              {phase === 'adImage' && (
                adElapsed >= SKIP_AFTER_S ? (
                  <button className="mp-skip-btn" data-testid="movie-ad-skip" onClick={skipToVideo}>
                    REKLAMI ATLA
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
                  </button>
                ) : (
                  <div className="mp-skip-wait" data-testid="movie-ad-skip-wait">Reklamı atla · {SKIP_AFTER_S - adElapsed}</div>
                )
              )}
            </div>
          )}

          {/* ===== 3 SN UYARI — dublaj izlemek reklama tabidir ===== */}
          {phase === 'notice' && (
            <div className="mp-notice" data-testid="movie-ad-notice">
              <div className="mp-notice-glow" aria-hidden="true" />
              <div className="mp-notice-card">
                <span className="mp-notice-icon" aria-hidden="true">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
                  </svg>
                </span>
                <span className="mp-notice-kicker"><i aria-hidden="true" />UYARI<i aria-hidden="true" /></span>
                <span className="mp-notice-text">Türkçe dublaj olarak izlemek reklama tabiidir</span>
              </div>
            </div>
          )}

          {/* ===== ŞEFFAF KAYAN BİLDİRİM — Filmi nasıl izlemek istiyorsunuz? ===== */}
          {phase === 'film' && askVisible && (
            <div className="mp-ask-panel" data-testid="movie-ask-panel" onClick={(e) => e.stopPropagation()}>
              <div className="mp-ask-title">FİLMİ NASIL İZLEMEK İSTİYORSUNUZ?</div>
              <div className="mp-ask-btns">
                <button
                  className={`mp-ask-btn${track === 'dub' ? ' active' : ''}`}
                  data-testid="movie-track-dub"
                  onClick={() => switchTrack('dub')}
                >
                  TÜRKÇE DUBLAJ<small>ENGLISH ALTYAZI · 720p</small>
                </button>
                <button
                  className={`mp-ask-btn${track === 'sub' ? ' active' : ''}`}
                  data-testid="movie-track-sub"
                  onClick={() => switchTrack('sub')}
                >
                  ORİJİNAL SES<small>TÜRKÇE ALTYAZI · 1080p</small>
                </button>
              </div>
              <button className="mp-ask-close" data-testid="movie-ask-close" onClick={() => setAskVisible(false)} aria-label="Kapat">✕</button>
            </div>
          )}

          {/* Ses/Altyazı seçim menüsü — birincil player'daki cc-menu paterni */}
          {phase === 'film' && trackMenuOpen && (
            <div className="cc-selector open mp-cc" data-testid="movie-track-menu" onClick={(e) => e.stopPropagation()}>
              <div className="cc-menu" style={{ display: 'flex', position: 'static' }}>
                <div className="cc-menu-title">SES / ALTYAZI</div>
                <button
                  className={`cc-btn${track === 'dub' ? ' active' : ''}`}
                  data-testid="movie-cc-dub"
                  onClick={() => switchTrack('dub')}
                >
                  Türkçe Dublaj · 720p
                </button>
                <button
                  className={`cc-btn${track === 'sub' ? ' active' : ''}`}
                  data-testid="movie-cc-sub"
                  onClick={() => switchTrack('sub')}
                >
                  Türkçe Altyazı · 1080p
                </button>
              </div>
            </div>
          )}

          {/* BUFFERING */}
          {phase === 'film' && buffering && !errorMsg && (
            <div className="movie-buffering" data-testid="movie-buffering"><span className="movie-spinner" /></div>
          )}

          {/* HATA */}
          {errorMsg && (
            <div className="overlay" data-testid="movie-error" style={{ zIndex: 45 }}>
              <div className="movie-preparing">
                <span className="movie-preparing-title">{errorMsg}</span>
                <button
                  data-testid="movie-retry-btn"
                  onClick={(e) => { e.stopPropagation(); retryVideo(); }}
                  style={{
                    marginTop: 14, padding: '10px 26px', cursor: 'pointer',
                    background: 'rgba(0,240,255,0.12)', border: '1.5px solid var(--cyan, #00f0ff)',
                    color: 'var(--cyan, #00f0ff)', fontFamily: 'VT323, monospace',
                    fontSize: 16, letterSpacing: 2, borderRadius: 6,
                  }}
                >
                  ↻ TEKRAR DENE
                </button>
              </div>
            </div>
          )}

          {/* 📺 YANSITMA — sol üst */}
          {phase === 'film' && !errorMsg && (
            <button
              onClick={(e) => { e.stopPropagation(); toggleCast(); }}
              data-testid="movie-cast-btn"
              aria-label="Yayını cihaza aktar"
              title="Chromecast / AirPlay / Smart TV — cihaz seç"
              style={{
                position: 'absolute', top: 12, left: 12, zIndex: 40,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 38, height: 32, padding: 0, borderRadius: 6,
                background: 'linear-gradient(135deg, rgba(8,4,14,0.78), rgba(20,8,30,0.78))',
                border: '1px solid rgba(0,240,255,0.45)',
                color: 'var(--cyan, #00f0ff)', cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(0,0,0,0.45), 0 0 14px rgba(0,240,255,0.25)',
                backdropFilter: 'blur(6px)', touchAction: 'manipulation',
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M21 3H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.93-11-11-11z" />
              </svg>
            </button>
          )}

          {/* SAĞ ÜST BAŞLIK */}
          {phase === 'film' && (
            <div className="movie-title-tag" style={{ opacity: controlsVisible ? 1 : 0 }}>
              <span className="movie-title-dot" />
              {movie.title_en || movie.title}
            </div>
          )}

          {/* KONTROL BARI */}
          {phase === 'film' && (
            <div
              className="movie-controls"
              data-testid="movie-controls"
              style={{ opacity: controlsVisible ? 1 : 0, pointerEvents: controlsVisible ? 'auto' : 'none' }}
              onClick={(e) => e.stopPropagation()}
            >
              <input
                type="range"
                className="movie-seek"
                data-testid="movie-seek"
                min={0}
                max={duration || 0}
                step={0.1}
                value={Math.min(current, duration || 0)}
                onChange={onSeek}
                aria-label="İlerleme"
              />
              <div className="movie-controls-row">
                <div className="movie-controls-left">
                  <button className="control-btn movie-ctl" data-testid="movie-playpause-btn" onClick={togglePlay} aria-label={playing ? 'Duraklat' : 'Oynat'}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                      {playing
                        ? <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                        : <path d="M8 5v14l11-7z" />}
                    </svg>
                  </button>
                  <button className="control-btn movie-ctl" data-testid="movie-mute-btn" onClick={toggleMute} aria-label={muted ? 'Sesi aç' : 'Sesi kapat'}>
                    {muted
                      ? <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" /></svg>
                      : <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" /></svg>}
                  </button>
                  <input
                    type="range"
                    className="movie-volume"
                    data-testid="movie-volume"
                    min={0}
                    max={1}
                    step={0.05}
                    value={muted ? 0 : volume}
                    onChange={onVolume}
                    aria-label="Ses seviyesi"
                  />
                  <span className="movie-time" data-testid="movie-time">{fmt(current)} / {fmt(duration)}</span>
                </div>
                <div className="movie-controls-right">
                  <button
                    className="control-btn movie-ctl mp-track-btn"
                    data-testid="movie-track-btn"
                    onClick={() => setTrackMenuOpen((s) => !s)}
                    aria-label="Ses / Altyazı seçimi"
                    title="Ses / Altyazı"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zM4 12h4v2H4v-2zm10 6H4v-2h10v2zm6 0h-4v-2h4v2zm0-4H10v-2h10v2z" />
                    </svg>
                  </button>
                  <span className="movie-hd-tag" data-testid="movie-quality-tag">{track === 'dub' ? '720p' : '1080p'}</span>
                  <button className="control-btn movie-ctl" data-testid="movie-pip-btn" onClick={togglePip} aria-label="Pencere içinde pencere" title="Pencere içinde pencere (PiP)">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M19 7h-8v6h8V7zm2-4H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16.01H3V4.98h18v14.03z" />
                    </svg>
                  </button>
                  <button className="control-btn movie-ctl" data-testid="movie-fullscreen-btn" onClick={toggleFullscreen} aria-label="Tam ekran">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
