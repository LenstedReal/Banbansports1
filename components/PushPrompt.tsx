'use client';
/**
 * PushPrompt — kullanıcıya browser push notification onayı al ve VAPID subscription
 * oluştur. NotificationCenter'da gösterilebilir ufak bir buton/popup.
 */
import { useEffect, useState } from 'react';
import { getClient, postClient } from '@/lib/api';

type VapidInfo = { public_key: string | null; configured: boolean };

function urlBase64ToUint8Array(base64: string): BufferSource {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  // Use ArrayBuffer-backed Uint8Array (PushManager.subscribe expects BufferSource)
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

export default function PushPrompt() {
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [vapid, setVapid] = useState<VapidInfo | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const ok = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    setSupported(ok);
    if (!ok) return;
    setPermission(Notification.permission);
    // VAPID public key
    getClient<VapidInfo>('/api/push/vapid-key').then((v) => { if (v) setVapid(v); });
    // Mevcut subscription
    navigator.serviceWorker.ready.then(async (reg) => {
      const sub = await reg.pushManager.getSubscription();
      setSubscribed(!!sub);
    }).catch(() => {});
  }, []);

  const subscribe = async () => {
    if (!vapid?.public_key) {
      alert('Push servisi yapılandırılmamış. Yönetici, VAPID anahtarlarını ayarlamalı.');
      return;
    }
    setBusy(true);
    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== 'granted') return;
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
      });
      const json = sub.toJSON();
      await postClient('/api/push/subscribe', {
        endpoint: json.endpoint,
        keys: json.keys,
      });
      setSubscribed(true);
    } catch (e) {
      console.error('push subscribe', e);
    } finally {
      setBusy(false);
    }
  };

  const unsubscribe = async () => {
    setBusy(true);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await postClient('/api/push/unsubscribe', { endpoint: sub.endpoint });
        await sub.unsubscribe();
      }
      setSubscribed(false);
    } finally {
      setBusy(false);
    }
  };

  if (!supported) return null;
  if (!vapid?.configured) return null;  // VAPID yoksa butonu hiç gösterme

  const label = subscribed ? 'BİLDİRİMLERİ KAPAT' : 'BİLDİRİM AÇIK';
  const action = subscribed ? unsubscribe : subscribe;

  return (
    <button
      type="button"
      onClick={action}
      disabled={busy}
      data-testid="push-toggle"
      className="btn-neon-cyan"
      style={{
        position: 'fixed', bottom: 16, right: 16, zIndex: 200,
        padding: '8px 14px', fontSize: 11, fontFamily: 'Orbitron, sans-serif', letterSpacing: 2,
        opacity: busy ? 0.6 : 1,
      }}
    >
      {busy ? '...' : label}
    </button>
  );
}
