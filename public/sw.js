/**
 * banbansports — Service Worker
 * — Offline cache (static assets)
 * — Push notification handler
 */
const SW_VERSION = 'v8-sync';
const CACHE_NAME = `banbansports-${SW_VERSION}`;

const STATIC_ASSETS = [
    '/',
    '/manifest.json',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => null))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    // Never cache: API, streams, videos, large media
    if (url.pathname.startsWith('/api/') ||
        url.pathname.endsWith('.m3u8') ||
        url.pathname.endsWith('.ts') ||
        url.pathname.endsWith('.mp4') ||
        url.pathname.endsWith('.webm') ||
        url.hostname !== self.location.hostname) {
        return;
    }

    // Cache-first for static assets (images, logos)
    if (url.pathname.startsWith('/logos/') ||
        url.pathname.endsWith('.png') ||
        url.pathname.endsWith('.jpg') ||
        url.pathname.endsWith('.svg')) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) =>
                cache.match(req).then((cached) => cached || fetch(req).then((resp) => {
                    if (resp.ok) cache.put(req, resp.clone());
                    return resp;
                }))
            )
        );
        return;
    }

    // Network-first for HTML/JS/CSS (fresh content) with cache fallback
    if (url.pathname.endsWith('.html') ||
        url.pathname.endsWith('.js') ||
        url.pathname.endsWith('.css') ||
        url.pathname === '/') {
        event.respondWith(
            fetch(req).then((resp) => {
                if (resp.ok) {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(req, clone));
                }
                return resp;
            }).catch(() => caches.match(req))
        );
    }
});

self.addEventListener('push', (event) => {
    if (!event.data) return;
    let payload = {};
    try { payload = event.data.json(); } catch { payload = { title: event.data.text() }; }
    const title = payload.title || 'banbansports';
    const opts = {
        body: payload.body || '',
        icon: '/logos/banbansports_logo.png',
        badge: '/logos/banbansports_logo.png',
        tag: payload.tag || 'banbansports-notif',
        data: payload.data || {},
        vibrate: [80, 40, 80],
    };
    event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        self.clients.matchAll({ type: 'window' }).then((all) => {
            for (const c of all) {
                if ('focus' in c) return c.focus();
            }
            return self.clients.openWindow('/');
        })
    );
});
