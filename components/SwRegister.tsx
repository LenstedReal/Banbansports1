'use client';
/**
 * Service Worker register — eski repodaki PWA mantığını geri getirir.
 * sw.js zaten /public/'ta var, sadece register edilmiyordu.
 */
import { useEffect } from 'react';

export default function SwRegister() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator)) return;
    // Sadece production'da register et — dev'de HMR ile çakışıyor
    if (window.location.hostname === 'localhost' || window.location.hostname.startsWith('127.')) return;
    const timer = setTimeout(() => {
      navigator.serviceWorker
        .register('/sw.js', { scope: '/' })
        .then(() => {
          console.info('[banbansports] Service Worker registered');
        })
        .catch(() => {
          /* sessiz fallback — sw.js eksikse umursama */
        });
    }, 1500);
    return () => clearTimeout(timer);
  }, []);
  return null;
}
