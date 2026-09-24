'use client';
/* Bakım ekranı: bakim_loop.mp4 ANINDA canvas'ta döner (poster beklemesi yok). Video canvas'a çizilir
   (blob src, kontrolsüz, sağ tık/PiP/cast/indirme yok), sessiz, CRT katmanı.
   5 dakika sonra iPhone bakım/test ekranlarındaki gibi sürekli 1 kHz "bip" tonu (WebAudio) başlar.
   ÜSTTE: turuncu İngiliz anahtarı + kanal adı + metin. "yakında"/"kaynak yok" aynı ekran farklı metin. */
import { useEffect, useRef } from 'react';

type Props = { name: string; text: string; variant?: 'maintenance' | 'soon' | 'nosource' };
const BEEP_AFTER_MS = 5 * 60 * 1000;

export default function MaintenanceScreen({ name, text, variant = 'maintenance' }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let alive = true;
    let raf = 0;
    let url = '';
    const video = document.createElement('video');
    video.muted = true; video.loop = true; video.playsInline = true; (video as any).disablePictureInPicture = true;
    video.setAttribute('disableremoteplayback', '');
    const draw = () => {
      if (!alive) return;
      const c = canvasRef.current;
      if (c && video.readyState >= 2) {
        const ctx = c.getContext('2d');
        if (ctx) {
          if (c.width !== c.clientWidth || c.height !== c.clientHeight) { c.width = c.clientWidth; c.height = c.clientHeight; }
          ctx.drawImage(video, 0, 0, c.width, c.height);
        }
      }
      raf = requestAnimationFrame(draw);
    };
    // Poster'ı hemen çiz (video gelene kadar boş kalmasın)
    const poster = new Image();
    poster.src = '/bakim_poster.jpg';
    poster.onload = () => {
      const c = canvasRef.current;
      if (!c || !alive || video.readyState >= 2) return;
      c.width = c.clientWidth; c.height = c.clientHeight;
      c.getContext('2d')?.drawImage(poster, 0, 0, c.width, c.height);
    };
    (async () => {
      try {
        const r = await fetch('/bakim_loop.mp4');
        const b = await r.blob();
        if (!alive) return;
        url = URL.createObjectURL(b);
        video.src = url;
        await video.play().catch(() => {});
        draw();
      } catch { /* poster kalır */ }
    })();
    return () => { alive = false; cancelAnimationFrame(raf); video.pause(); video.src = ''; if (url) URL.revokeObjectURL(url); };
  }, []);

  // 5 dk sonra sürekli bip (1 kHz) — tarayıcı kısıtı varsa ilk etkileşimde başlar
  useEffect(() => {
    let ctx: AudioContext | null = null;
    let osc: OscillatorNode | null = null;
    let started = false;
    const start = () => {
      if (started) return;
      try {
        const AC = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext | undefined;
        if (!AC) return;
        ctx = new AC();
        osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine'; osc.frequency.value = 1000; gain.gain.value = 0.12;
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        if (ctx.state === 'suspended') { ctx.resume().catch(() => {}); }
        started = true;
      } catch { /* ses yok */ }
    };
    const unlock = () => { if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {}); };
    const t = setTimeout(() => {
      start();
      window.addEventListener('pointerdown', unlock);
      window.addEventListener('keydown', unlock);
    }, BEEP_AFTER_MS);
    return () => {
      clearTimeout(t);
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      try { osc?.stop(); } catch { /* */ }
      try { ctx?.close(); } catch { /* */ }
    };
  }, []);

  const title = variant === 'soon' ? 'YAKINDA' : variant === 'nosource' ? 'KAYNAK YOK' : 'BAKIMDA';
  return (
    <div className="bbm" data-testid="maintenance-screen" onContextMenu={(e) => e.preventDefault()}>
      <canvas ref={canvasRef} className="bbm-media" aria-hidden="true" />
      <div className="bbm-crt" aria-hidden="true" />
      <div className="bbm-top">
        <div className="bbm-wrench" aria-hidden="true">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="currentColor"><path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z" /></svg>
        </div>
        <div className="bbm-txt">
          <div className="bbm-tag">{title}</div>
          <div className="bbm-name" data-testid="maintenance-channel">{name}</div>
          <div className="bbm-sub">{text}</div>
        </div>
      </div>
    </div>
  );
}
