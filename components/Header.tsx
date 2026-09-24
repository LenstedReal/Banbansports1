'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from './AuthProvider';
import AuthButton from './AuthButton';


const ANNOUNCEMENT = '👉 Bir sonraki alan adımız bir artacaktır; erişim engellendiğinde yeni adresten devam edilir.\u00A0\u00A0\u00A0\u00A0';

export default function Header() {
  const { user } = useAuth();
  const [notifOn, setNotifOn] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (typeof Notification !== 'undefined') setNotifOn(Notification.permission === 'granted');
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const toggleNotif = async () => {
    if (typeof Notification === 'undefined') return showToast('Bu tarayıcı bildirim desteklemiyor.');
    if (Notification.permission === 'granted') {
      setNotifOn((v) => !v);
      return;
    }
    if (Notification.permission === 'denied') {
      return showToast('Bildirim izni reddedilmiş. Tarayıcı ayarlarından "site izinleri" üzerinden açabilirsiniz.');
    }
    const p = await Notification.requestPermission();
    setNotifOn(p === 'granted');
    if (p === 'granted') {
      try { new Notification('banbansports', { body: 'Bildirimler açık — yaklaşan maçlar ve canlı skor güncellemeleri push olarak gelecek.', icon: '/icons/info.png' }); } catch { /* noop */ }
    } else if (p === 'denied') {
      showToast('Bildirim reddedildi. İzin vermek için tarayıcı çubuğundaki kilit ikonuna tıklayın.');
    }
  };

  return (
    <header className="hd2" data-testid="header">
      <div className="hd2-in">
        <Link href="/" className="hd2-logo" data-testid="logo">
          <img src="/brand/logo_mark.png" alt="banbansports" className="hd2-logo-img" draggable={false} />
          <span className="hd2-logo-txt">
            <span className="hd2-logo-main">banbansports</span>
            <span className="hd2-logo-sub">UNDERGROUND HD</span>
          </span>
        </Link>
        <span className="hd2-live" data-testid="status-badge">
          <span className="hd2-live-dot" />CANLI
        </span>
        <div className="hd2-ticker" data-testid="header-announcement" aria-label="Duyuru">
          <div className="hd2-ticker-wrap">
            <div className="hd2-ticker-track">
              <span>{ANNOUNCEMENT}</span>
              <span aria-hidden="true">{ANNOUNCEMENT}</span>
            </div>
          </div>
          <span className="hd2-ticker-label" aria-hidden="true">
            <span className="hd2-ticker-emoji">📢</span>
          </span>
        </div>
        <div className="hd2-right">
          <Link href="/admin" className="hd2-admin" data-testid="admin-link">ADMIN</Link>
          <span className="hd2-acct" data-testid="nav-account"><AuthButton /></span>
          <button
            type="button"
            className="hd2-notif"
            onClick={toggleNotif}
            data-testid="notif-toggle"
            title="Maç bildirimleri"
            data-active={notifOn ? 'on' : 'off'}
          >
            <svg viewBox="0 0 24 24"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>
            <span>BİLDİRİM</span>
            <span className="hd2-notif-state">{notifOn ? 'AÇIK' : 'KAPALI'}</span>
          </button>
        </div>
      </div>
      {toast && (
        <div
          data-testid="header-toast"
          role="status"
          aria-live="polite"
          style={{
            position: 'fixed', top: 70, right: 20, zIndex: 9999, maxWidth: 360,
            padding: '12px 18px',
            background: 'linear-gradient(135deg, rgba(20,12,28,0.96), rgba(8,4,16,0.96))',
            border: '1px solid var(--cyan)', borderRadius: 8, color: 'var(--cyan)',
            fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.4, letterSpacing: 0.5,
            boxShadow: '0 8px 32px rgba(0,0,0,0.7), 0 0 16px rgba(0,229,255,0.35)',
            animation: 'bb-toast-in 0.25s ease-out',
          }}
        >
          {toast}
        </div>
      )}
    </header>
  );
}
