export type Channel = { id: string; name: string; status: 'online' | 'maintenance' | 'checking' | 'coming_soon'; premium?: boolean; src?: string; badge?: string; logo?: string; accent?: string; short?: string };

// Her kanal için yedek sunucu listesi — 1. seçenek başarısız olursa otomatik 2., 3. denenir
export const CHANNEL_SOURCES: Record<string, string[]> = {
  tivibuspor: ['/api/stream/tivibuspor/stream.m3u8'],
  trt1:       ['/api/stream/trt1/stream.m3u8'],
  trtspor:    ['/api/stream/trtspor/stream.m3u8'],
  trthaber:   ['/api/stream/trthaber/stream.m3u8'],
  tv8:        ['/api/stream/tv8/stream.m3u8'],
  ssport:     [
    '/api/stream/ssport/stream.m3u8',
    '/api/ssport/stream.m3u8',
    '/api/stream/ssport/stream.m3u8?via=tivibu',
  ],
  atv:        ['/api/stream/atv/stream.m3u8'],
};

// Doğrudan HLS kanalları (backend services/direct_channels.py ile aynı id'ler)
const D = (id: string, name: string, short: string, accent: string, premium?: boolean): Channel => ({
  id, name, short, status: 'online', premium, src: `/api/stream/${id}/stream.m3u8`, accent,
});

export const CHANNELS: Channel[] = [
  { id: 'tivibuspor', name: 'TİVİBU SPOR',     short: 'TİVİBU\nSPOR', status: 'online',       src: CHANNEL_SOURCES.tivibuspor[0], logo: '/logos/channels/tivibuspor.png', accent: '#00a0e3' },
  { id: 'ssport',    name: 'S SPORT',            short: 'S SPORT',   status: 'online',       premium: true, src: CHANNEL_SOURCES.ssport[0], logo: '/logos/channels/ssport.png', accent: '#c0223a' },
  { id: 'bein1',     name: 'beIN SPORTS 1',      short: 'beIN 1',    status: 'maintenance',  premium: true,                       logo: '/logos/channels/bein1.png',      accent: '#8b4d9e' },
  D('beinxtra',  'beIN SPORTS XTRA',  'beIN\nXTRA',  '#8b4d9e', true),
  D('aspor',     'A SPOR',            'A SPOR',      '#e2001a'),
  D('htspor',    'HT SPOR',           'HT SPOR',     '#f39200'),
  D('ekolsport', 'EKOL SPORTS',       'EKOL\nSPORTS','#00b3a4'),
  { id: 'trtspor',   name: 'TRT SPOR',           short: 'TRT SPOR',  status: 'maintenance',  src: CHANNEL_SOURCES.trtspor[0],     logo: '/logos/channels/trtspor.png',    accent: '#7cd400' },
  D('tracesport','TRACE SPORT STARS', 'TRACE\nSPORT','#ff3d00'),
  D('ktvsport',  'KTV SPORT PLUS',    'KTV\nSPORT',  '#0072ce'),
  { id: 'trt1',      name: 'TRT 1',              short: 'TRT 1',     status: 'online',       src: CHANNEL_SOURCES.trt1[0],        logo: '/logos/channels/trt1.png',       accent: '#e30a17' },
  { id: 'trthaber',  name: 'TRT HABER',          short: 'TRT HABER', status: 'online',       src: CHANNEL_SOURCES.trthaber[0],    logo: '/logos/channels/trthaber.png',   accent: '#1f6feb' },
  { id: 'tv8',       name: 'TV 8',               short: 'TV 8',      status: 'online',       src: CHANNEL_SOURCES.tv8[0],         logo: '/logos/channels/tv8.png',        accent: '#cfcfcf' },
  D('tv85',      'TV 8.5',            'TV 8.5',      '#9aa0a6'),
  { id: 'atv',       name: 'ATV',                short: 'ATV',       status: 'online',       src: CHANNEL_SOURCES.atv[0],         logo: '/logos/channels/atv.png',        accent: '#ff7a00' },
  D('showtv',    'SHOW TV',           'SHOW',        '#e4002b'),
  D('startv',    'STAR TV',           'STAR',        '#ffcc00'),
  D('kanald',    'KANAL D',           'KANAL D',     '#005bbb'),
  D('nowtv',     'NOW (FOX)',         'NOW',         '#7a3cff'),
  D('kanal7',    'KANAL 7',           'KANAL 7',     '#0aa64f'),
  D('cnnturk',   'CNN TÜRK',          'CNN\nTÜRK',   '#cc0000'),
  D('trtmuzik',  'TRT MÜZİK',         'TRT\nMÜZİK',  '#ff2d95'),
  D('powertv',   'POWER TV',          'POWER',       '#ff0090'),
  D('powerturk', 'POWER TÜRK',        'POWER\nTÜRK', '#00c2ff'),
  D('kraltv',    'KRAL TV',           'KRAL',        '#ffb400'),
  D('number1',   'NUMBER 1',          'NUMBER 1',    '#00e5ff'),
  D('dreamturk', 'DREAM TÜRK',        'DREAM\nTÜRK', '#a64dff'),
];

// ---- 112 kanal kataloğu (önceki oturum) — mevcut listedeki id'ler korunur, eksikler eklenir ----
import { CATALOG } from './channelCatalog';
const _known = new Set(CHANNELS.map((c) => c.id));
for (const c of CATALOG) {
  if (_known.has(c.id)) {
    const ex = CHANNELS.find((x) => x.id === c.id)!;
    if (!ex.logo) ex.logo = c.logo;
    (ex as any).cat = c.cat;
    continue;
  }
  CHANNELS.push({ id: c.id, name: c.name, short: c.short, status: 'checking', premium: c.premium, src: `/api/stream/${c.id}/stream.m3u8`, logo: c.logo, accent: c.accent, ...( { cat: c.cat } as any) });
}
export const CHANNEL_CAT: Record<string, string> = Object.fromEntries(CATALOG.map((c) => [c.id, c.cat]));
