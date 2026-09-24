'use client';
/* Cloudflare Turnstile (Managed) — sadece korumalı içerik panelinde kullanılır. */
import { useEffect, useRef } from 'react';

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      reset: (id?: string) => void;
      remove: (id?: string) => void;
    };
  }
}

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', () => reject(new Error('turnstile script')));
      return;
    }
    const s = document.createElement('script');
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('turnstile script'));
    document.head.appendChild(s);
  });
}

export default function TurnstileWidget({
  siteKey,
  onToken,
  resetSignal,
}: {
  siteKey: string;
  onToken: (token: string) => void;
  resetSignal: number;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const idRef = useRef<string | null>(null);
  const cbRef = useRef(onToken);
  cbRef.current = onToken;

  useEffect(() => {
    let alive = true;
    loadScript()
      .then(() => {
        if (!alive || !boxRef.current || !window.turnstile || idRef.current) return;
        idRef.current = window.turnstile.render(boxRef.current, {
          sitekey: siteKey,
          theme: 'dark',
          size: 'flexible',
          language: 'tr',
          appearance: 'always',
          callback: (t: string) => cbRef.current(t),
          'expired-callback': () => cbRef.current(''),
          'error-callback': () => cbRef.current(''),
          'timeout-callback': () => cbRef.current(''),
        });
      })
      .catch(() => cbRef.current(''));
    return () => {
      alive = false;
      if (idRef.current && window.turnstile) {
        try { window.turnstile.remove(idRef.current); } catch { /* noop */ }
      }
      idRef.current = null;
    };
  }, [siteKey]);

  useEffect(() => {
    if (resetSignal > 0 && idRef.current && window.turnstile) {
      try { window.turnstile.reset(idRef.current); } catch { /* noop */ }
      cbRef.current('');
    }
  }, [resetSignal]);

  return <div ref={boxRef} className="mp-turnstile" data-testid="lock-turnstile" />;
}
