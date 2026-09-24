'use client';
/* Admin Gate (KALAN_ISLER): ADMIN butonu herkese görünür → "sadece site admini/geliştiricisine özel — 3 sn" uyarısı
   → kullanıcı adı (adminastor) + parola formu → /api/admin-gate/login (backend: 5 hata/10 dk kilit, HttpOnly JWT). */
import { useEffect, useState } from 'react';

export default function AdminGate({ onSuccess }: { onSuccess: () => void }) {
  const [phase, setPhase] = useState<'warn' | 'form'>('warn');
  const [count, setCount] = useState(3);
  const [u, setU] = useState('');
  const [p, setP] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(0);

  useEffect(() => {
    if (phase !== 'warn') return;
    if (count <= 0) { setPhase('form'); return; }
    const t = setTimeout(() => setCount((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [phase, count]);

  useEffect(() => {
    fetch('/api/admin-gate/status', { credentials: 'same-origin' }).then((r) => r.json()).then((d) => { if (d?.locked) setLocked(d.retry_in || 600); }).catch(() => {});
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setErr('');
    try {
      const r = await fetch('/api/admin-gate/login', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
      const d = await r.json().catch(() => null);
      if (r.ok && d?.ok) { onSuccess(); return; }
      if (r.status === 429) setLocked(600);
      setErr(d?.detail || 'Giriş başarısız');
    } catch { setErr('Sunucuya ulaşılamadı'); }
    finally { setBusy(false); }
  };

  return (
    <div className="ag" data-testid="admin-gate">
      <div className="ag-card">
        <div className="ag-brand"><span>banbansports</span><small>ADMIN</small></div>
        {phase === 'warn' ? (
          <div className="ag-warn" data-testid="admin-gate-warn">
            <div className="ag-icon">👑</div>
            <div className="ag-title">Bu alan sadece site admini / geliştiricisine özeldir</div>
            <div className="ag-sub">Yetkisiz giriş denemeleri kayıt altına alınır.</div>
            <div className="ag-count">{count}</div>
          </div>
        ) : (
          <form className="ag-form" onSubmit={submit} data-testid="admin-gate-form">
            <input autoFocus placeholder="Kullanıcı adı" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" data-testid="admin-gate-user" />
            <input type="password" placeholder="Parola" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" data-testid="admin-gate-pass" />
            <button type="submit" disabled={busy || locked > 0} data-testid="admin-gate-submit">{locked > 0 ? 'KİLİTLİ · 10 DK' : busy ? 'DOĞRULANIYOR…' : 'GİRİŞ'}</button>
            {err && <div className="ag-err" data-testid="admin-gate-error">{err}</div>}
            <div className="ag-note">5 hatalı denemede 10 dakika kilitlenir · HttpOnly oturum</div>
          </form>
        )}
      </div>
    </div>
  );
}
