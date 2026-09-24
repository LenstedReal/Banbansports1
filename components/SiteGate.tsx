'use client';
/* Site giriş kapısı — Cloudflare Turnstile "ben robot değilim" (site açılmadan önce).
   Çerez (bb_gate, 12 sa) geçerliyse hiç görünmez. Yayın yetkisi vermez; player katmanı ayrıdır. */
import { useEffect, useState } from 'react';
import TurnstileWidget from './TurnstileWidget';

const ENV_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '';
type GateState = 'checking' | 'gate' | 'ok';

export default function SiteGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>('checking');
  const [siteKey, setSiteKey] = useState(ENV_SITE_KEY);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [reset, setReset] = useState(0);

  useEffect(() => {
    let alive = true;
    fetch('/api/site-gate/status', { cache: 'no-store', credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!alive) return;
        if (!d || d.ok) { setState('ok'); return; }
        if (d.turnstile_site_key) setSiteKey(d.turnstile_site_key);
        setState('gate');
      })
      .catch(() => { if (alive) setState('ok'); });
    return () => { alive = false; };
  }, []);

  const onToken = async (t: string) => {
    if (!t || busy) return;
    setBusy(true);
    setErr('');
    try {
      const r = await fetch('/api/site-gate/verify', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ turnstile_token: t }),
      });
      if (r.ok) { setState('ok'); return; }
      const d = await r.json().catch(() => null);
      setErr(d?.detail || 'Doğrulama başarısız — tekrar deneyin');
      setReset((n) => n + 1);
    } catch {
      setErr('Doğrulama sunucusuna ulaşılamadı');
      setReset((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  if (state === 'ok') return <>{children}</>;

  return (
    <div className="sg" data-testid="site-gate">
      <div className="sg-card">
        <div className="sg-brand"><span className="sg-brand-main">banbansports</span><span className="sg-brand-sub">UNDERGROUND HD</span></div>
        <div className="sg-title">{state === 'checking' ? 'BAĞLANTI KONTROL EDİLİYOR' : 'GÜVENLİK DOĞRULAMASI'}</div>
        <p className="sg-text">
          {state === 'checking'
            ? 'Bağlantınızın güvenliği doğrulanıyor, lütfen bekleyin…'
            : 'Devam etmek için robot olmadığınızı doğrulayın. Bu kontrol siteyi otomatik trafikten korur.'}
        </p>
        {state === 'gate' && siteKey && (
          <div className="sg-widget">
            <TurnstileWidget siteKey={siteKey} onToken={onToken} resetSignal={reset} />
          </div>
        )}
        {state === 'gate' && !siteKey && <div className="sg-err" data-testid="site-gate-nokey">Doğrulama yapılandırılmamış — yönetici ile iletişime geçin</div>}
        {busy && <div className="sg-status" data-testid="site-gate-busy">DOĞRULANIYOR…</div>}
        {err && <div className="sg-err" data-testid="site-gate-error">{err}</div>}
        <div className="sg-foot"><span className="sg-dot" />Cloudflare Turnstile · banbansports güvenlik katmanı</div>
      </div>
    </div>
  );
}
