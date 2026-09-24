import './legacy.css';
import './globals.css';
import './neon-touch.css';
import './cinema-v3.css';
import './gate.css';
import './v5-neon.css';
import './grok.css';
import './player-chrome.css';
import './fixes.css';
import type { Metadata, Viewport } from 'next';
import SiteGate from '../components/SiteGate';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://banban.lenstedreal.xyz';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'banbansports — UNDERGROUND HD · Canlı Maç, Skor ve Yayın',
    template: '%s | banbansports',
  },
  description:
    'Canlı maç skorları, beIN Sports 1 / S Sport / TRT 1 / TV8 yayınları, Süper Lig & Avrupa kupaları — banbansports UNDERGROUND HD. Hız, kalite ve gerçek zamanlı skor.',
  keywords: [
    'canlı maç', 'canlı skor', 'bein sports 1', 's sport', 'trt 1', 'tv 8',
    'süper lig', 'şampiyonlar ligi', 'avrupa ligi', 'banbansports', 'futbol yayını',
  ],
  applicationName: 'banbansports',
  authors: [{ name: 'LenstedReal' }],
  openGraph: {
    type: 'website',
    locale: 'tr_TR',
    url: SITE_URL,
    siteName: 'banbansports UNDERGROUND HD',
    title: 'banbansports — Canlı Maç & Skor',
    description: 'Maç · TV · Film & Dizi · Radyo · Şarkı — 185 FPS UNDERGROUND HD. by LenstedReal',
    images: [{ url: '/brand/og.jpg', width: 1200, height: 630, alt: 'banbansports UNDERGROUND HD' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'banbansports — Canlı Maç & Skor',
    description: 'Maç · TV · Film & Dizi · Radyo · Şarkı — 185 FPS UNDERGROUND HD.',
    images: ['/brand/og.jpg'],
  },
  icons: {
    icon: [{ url: '/brand/icon-192.png', sizes: '192x192', type: 'image/png' }, { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' }],
    apple: '/brand/icon-192.png',
    shortcut: '/brand/icon-192.png',
  },
  manifest: '/manifest.json',
  robots: { index: true, follow: true },
};

// Sabit 980px düzen: telefonlar sayfayı masaüstü gibi kurup ekrana SIĞDIRIR (Chrome "masaüstü sitesi" ile aynı davranış).
// initial-scale bilerek yok: yazılırsa telefon 980px'in sadece 390px'ini gösterir (zoom'lu görünüm).
export const viewport: Viewport = {
  themeColor: '#040308',
  width: 980,
  initialScale: 0 as unknown as number,
  viewportFit: 'cover',
  colorScheme: 'dark',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="dns-prefetch" href="https://api.sofascore.com" />
        <link rel="dns-prefetch" href="https://prod-public-api.livescore.com" />
        <script async src="https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1" />
      </head>
      <body className="min-h-screen text-ink-high antialiased" data-testid="app-root">
        <SiteGate>{children}</SiteGate>
      </body>
    </html>
  );
}
