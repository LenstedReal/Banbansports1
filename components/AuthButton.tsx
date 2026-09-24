'use client';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from './AuthProvider';

declare global { interface Window { google?: any; } }

export default function AuthButton() {
  const { user, loading, login, register, googleLogin, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'login'|'register'>('login');
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [name, setName] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);

  const [prov, setProv] = useState<{ google: boolean; google_client_id: string; discord: boolean; password_reset: boolean }>({ google: false, google_client_id: '', discord: false, password_reset: false });
  const [forgot, setForgot] = useState(false); const [code, setCode] = useState(''); const [info, setInfo] = useState('');
  useEffect(() => { fetch('/api/auth/providers').then((r) => r.ok ? r.json() : null).then((d) => { if (d) setProv(d); }).catch(() => {}); }, []);
  const GCID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || prov.google_client_id || '';

  useEffect(() => {
    if (!open || !GCID) return;
    const exists = document.querySelector('script[data-google-gsi]');
    const setup = () => {
      if (!window.google?.accounts) return;
      try {
        window.google.accounts.id.initialize({
          client_id: GCID,
          callback: async (resp: any) => {
            setBusy(true);
            const r = await googleLogin(resp.credential);
            setBusy(false);
            if (r.ok) setOpen(false); else setError(r.error || 'Google girişi başarısız');
          },
        });
        const el = document.getElementById('g-btn');
        if (el) window.google.accounts.id.renderButton(el, { theme:'filled_black', size:'large', text:'continue_with', shape:'pill', width:280 });
      } catch { /* Google GSI script kullanılamıyorsa sessizce atla — kullanıcı email+şifre ile giriş yapabilir */ }
    };
    if (!exists) {
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true; s.defer = true; s.setAttribute('data-google-gsi','1');
      document.body.appendChild(s);
      s.onload = setup;
    } else setup();
  }, [open, GCID, googleLogin]);

  const submit = async () => {
    setError(''); setBusy(true);
    const res = mode === 'login' ? await login(email, password) : await register(email, password, name || email.split('@')[0]);
    setBusy(false);
    if (res.ok) { setOpen(false); setEmail(''); setPassword(''); setName(''); }
    else setError(res.error || 'Hata oluştu');
  };

  if (loading) return <span className="notif-toggle" data-testid="auth-loading" style={{opacity:0.5}}>…</span>;

  if (user) {
    return (
      <div style={{display:'flex', alignItems:'center', gap:8}} data-testid="user-pill">
        <span className="notif-toggle" title={user.email} style={{cursor:'default'}}>
          {user.picture && <img src={user.picture} style={{width:18, height:18, borderRadius:'50%', objectFit:'cover'}} alt=""/>}
          <span>{user.name}</span>
        </span>
        <button onClick={logout} className="notif-toggle" data-testid="logout-btn">ÇIKIŞ</button>
      </div>
    );
  }

  return (
    <>
      <button onClick={() => { setOpen(true); setError(''); }} className="auth2-open" data-testid="open-auth">GİRİŞ</button>
      {open && typeof document !== 'undefined' && createPortal(
        <div onClick={e => { if (e.target === e.currentTarget) setOpen(false); }} className="auth2-backdrop" data-testid="auth-modal">
          <div className="auth2-card">
            <div className="auth2-head">
              <div>
                <div className="auth2-brand">banbansports</div>
                <h3 className="auth2-title">{forgot ? 'ŞİFRE SIFIRLA' : mode === 'login' ? 'GİRİŞ YAP' : 'KAYIT OL'}</h3>
              </div>
              <button onClick={() => setOpen(false)} className="auth2-close" aria-label="Kapat" data-testid="auth-close">✕</button>
            </div>

            {!forgot && (
              <div className="auth2-providers">
                {prov.discord ? (
                  <a className="auth2-prov auth2-discord" href="/api/auth/discord/login" data-testid="discord-btn">
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.4a13.4 13.4 0 0 1 3.3 1.7 15.6 15.6 0 0 0-13 0 13.4 13.4 0 0 1 3.4-1.7L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9 0 13.4.3 17.8a19.9 19.9 0 0 0 6 3l1.3-2.1a12.7 12.7 0 0 1-2-1l.5-.4a14.3 14.3 0 0 0 11.8 0l.5.4a12.7 12.7 0 0 1-2 1l1.3 2.1a19.9 19.9 0 0 0 6-3c.4-5-.9-9.4-3.4-13.4zM8.7 15.2c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.1 1.1 2.1 2.4-.9 2.4-2.1 2.4zm6.6 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.1 1.1 2.1 2.4-.9 2.4-2.1 2.4z"/></svg>
                    Discord ile devam et
                  </a>
                ) : (
                  <button type="button" className="auth2-prov auth2-discord auth2-soon" onClick={() => setInfo('Discord girişi yakında — DISCORD_CLIENT_ID / SECRET tanımlanınca otomatik aktif olur.')} data-testid="discord-btn-soon">
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.4a13.4 13.4 0 0 1 3.3 1.7 15.6 15.6 0 0 0-13 0 13.4 13.4 0 0 1 3.4-1.7L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9 0 13.4.3 17.8a19.9 19.9 0 0 0 6 3l1.3-2.1a12.7 12.7 0 0 1-2-1l.5-.4a14.3 14.3 0 0 0 11.8 0l.5.4a12.7 12.7 0 0 1-2 1l1.3 2.1a19.9 19.9 0 0 0 6-3c.4-5-.9-9.4-3.4-13.4zM8.7 15.2c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.1 1.1 2.1 2.4-.9 2.4-2.1 2.4zm6.6 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.1 1.1 2.1 2.4-.9 2.4-2.1 2.4z"/></svg>
                    Discord ile devam et <span className="auth2-soon-tag">YAKINDA</span>
                  </button>
                )}
                {GCID ? <div id="g-btn" className="auth2-google" data-testid="google-btn" /> : (
                  <button type="button" className="auth2-prov auth2-google-ph auth2-soon" onClick={() => setInfo('Google girişi yakında — GOOGLE_CLIENT_ID tanımlanınca otomatik aktif olur.')} data-testid="google-btn-soon">
                    <svg viewBox="0 0 24 24" aria-hidden><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.8-5.5 3.8-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.9 1.5l2.6-2.6C16.9 3.1 14.7 2 12 2 6.5 2 2 6.5 2 12s4.5 10 10 10c5.8 0 9.6-4.1 9.6-9.8 0-.7-.1-1.2-.2-1.7H12z"/></svg>
                    Google ile devam et <span className="auth2-soon-tag">YAKINDA</span>
                  </button>
                )}
                {info && <div className="auth2-info" data-testid="auth-info">{info}</div>}
                <div className="auth2-or">— YA DA E-POSTA İLE —</div>
              </div>
            )}

            {forgot ? (
              <div className="auth2-form">
                <input type="email" placeholder="E-posta" value={email} onChange={e=>setEmail(e.target.value)} className="auth2-input" data-testid="auth-email"/>
                {info && <div className="auth2-info" data-testid="auth-info">{info}</div>}
                {info && (
                  <>
                    <input type="text" inputMode="numeric" placeholder="6 haneli kod" value={code} onChange={e=>setCode(e.target.value)} className="auth2-input" data-testid="auth-code"/>
                    <input type="password" placeholder="Yeni parola (min 6)" value={password} onChange={e=>setPassword(e.target.value)} className="auth2-input" data-testid="auth-newpass"/>
                  </>
                )}
                {error && <div className="auth2-error" data-testid="auth-error">{error}</div>}
                {!info ? (
                  <button className="auth2-submit" disabled={busy || !email} data-testid="auth-forgot-send" onClick={async () => {
                    setBusy(true); setError('');
                    try { const r = await fetch('/api/auth/forgot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) }); const d = await r.json(); if (d.ok) setInfo(d.message || 'Kod gönderildi'); else setError(d.error || 'Gönderilemedi'); } catch { setError('Sunucuya ulaşılamadı'); } finally { setBusy(false); }
                  }}>{busy ? '...' : 'KOD GÖNDER'}</button>
                ) : (
                  <button className="auth2-submit" disabled={busy || !code || password.length < 6} data-testid="auth-reset-submit" onClick={async () => {
                    setBusy(true); setError('');
                    try { const r = await fetch('/api/auth/reset', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, code, password }) }); const d = await r.json(); if (d.ok) { window.location.reload(); } else setError(d.error || 'Sıfırlanamadı'); } catch { setError('Sunucuya ulaşılamadı'); } finally { setBusy(false); }
                  }}>{busy ? '...' : 'ŞİFREYİ DEĞİŞTİR'}</button>
                )}
                <button type="button" className="auth2-link" onClick={() => { setForgot(false); setInfo(''); setError(''); }}>← Girişe dön</button>
              </div>
            ) : (
              <div className="auth2-form">
                {mode === 'register' && (
                  <input type="text" placeholder="Kullanıcı adın" value={name} onChange={e=>setName(e.target.value)} className="auth2-input" data-testid="auth-name"/>
                )}
                <input type="email" placeholder="E-posta" value={email} onChange={e=>setEmail(e.target.value)} className="auth2-input" data-testid="auth-email"/>
                <input type="password" placeholder="Parola (min 6)" value={password} onChange={e=>setPassword(e.target.value)}
                       onKeyDown={e => { if (e.key === 'Enter') submit(); }} className="auth2-input" data-testid="auth-password"/>
                {error && <div className="auth2-error" data-testid="auth-error">{error}</div>}
                <button onClick={submit} disabled={busy || !email || !password} className="auth2-submit" data-testid="auth-submit">
                  {busy ? '...' : (mode === 'login' ? 'GİRİŞ YAP' : 'KAYIT OL')}
                </button>
                <div className="auth2-links">
                  <button type="button" className="auth2-link" onClick={() => { setMode(m => m === 'login' ? 'register' : 'login'); setError(''); }} data-testid="auth-toggle">
                    {mode === 'login' ? 'Hesabın yok mu? Kayıt ol' : 'Zaten üye misin? Giriş yap'}
                  </button>
                  {mode === 'login' && <button type="button" className="auth2-link" onClick={() => { setForgot(true); setError(''); }} data-testid="auth-forgot">Şifremi unuttum</button>}
                </div>
                <div className="auth2-note">Sohbet için giriş zorunlu değil — misafir olarak yazabilirsin. Hesap açarsan adın ve favorilerin kalıcı olur.</div>
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
