/**
 * TR sözlük + UX mesajları.
 * Eski reponun `public/app.js` (3140 satır) içindeki LANG sözlüğünden
 * damıtıldı. Vanilla JS'ten kurtulduk ama UX kararları korundu.
 */
export const TR = {
  // Genel
  LOADING: 'Yükleniyor…',
  ERROR_GENERIC: 'Bir hata oluştu, lütfen tekrar deneyin.',
  RETRY: 'TEKRAR DENE',

  // Maç merkezi
  MATCH_CENTER: 'MAÇ MERKEZİ',
  ALL: 'TÜMÜ',
  LIVE: 'CANLI',
  FINISHED: 'BİTTİ',
  UPCOMING: 'YAKLAŞAN',
  MATCH_ENDED: 'MAÇ SONU',
  MATCH_BEFORE: 'MAÇ ÖNÜ',
  NOT_STARTED: 'BAŞLAMADI',
  HALF_TIME: 'DEVRE ARASI',
  EXTRA_TIME: 'UZATMA',
  PENALTIES: 'PENALTILAR',
  FIRST_HALF: '1. YARI',
  SECOND_HALF: '2. YARI',
  NO_MATCHES_LEAGUE: 'Bugün bu ligde maç yok',
  NO_MATCHES_FILTER: 'Bu filtreye uygun maç yok',
  NO_MATCHES_TODAY: 'Bugün gösterilecek önemli maç bulunamadı',
  LOADING_MATCHES: 'Maçlar yükleniyor…',

  // Maç detay / istatistik
  MATCH_DETAIL: 'MAÇ DETAYI',
  STATS_LOADING: 'İstatistikler yükleniyor…',
  STATS_PRE_MATCH_TITLE: 'MAÇ HENÜZ BAŞLAMADI',
  STATS_PRE_MATCH_SUB: 'İstatistikler maç başladığında otomatik olarak güncellenecek',
  STATS_UNAVAILABLE_TITLE: 'BU MAÇ İÇİN İSTATİSTİK YOK',
  STATS_UNAVAILABLE_SUB: 'Veri sağlayıcılarımızda bu karşılaşma için detay bulunamadı.',
  EVENTS_TITLE: 'MAÇ OLAYLARI',
  NO_EVENTS: 'Henüz olay yok',
  STATS_SOURCES: 'KAYNAK',

  // Skorbord
  SCOREBOARD_EMPTY_TITLE: 'ŞU AN GÖSTERİLECEK MAÇ YOK',
  SCOREBOARD_EMPTY_SUB: 'Birazdan tekrar bakacağız — canlı veya yaklaşan maçlar çıkınca burada görünecek.',

  // Yayın / video player
  WATCH_LIVE: 'CANLI İZLE',
  UNMUTE: 'SESİ AÇ',
  MUTE: 'SESİ KAPAT',
  CAST: 'CAST',
  PIP: 'Küçük Pencere',
  FULLSCREEN: 'Tam Ekran',
  PLAY: 'Oynat',
  PAUSE: 'Duraklat',
  QUALITY: 'KALİTE',
  AUTO: 'AUTO',
  AD_RUNNING: 'REKLAM OYNUYOR',
  AD_WAIT: 'Reklamın bitmesini bekleyin.',
  AD_SKIP: 'REKLAMI ATLA',
  AD_SKIP_IN: 'ATLA',
  BROADCAST_STARTING: 'YAYIN BAŞLIYOR…',
  STREAM_UNAVAILABLE: 'Yayın şu anda aktif değil',
  CHANNEL_MAINTENANCE: 'Yayın şu anda aktif değil',
  CHANNEL_COMING_SOON: 'YAKINDA — takipte kal',
  CHANNEL_NO_SOURCE: 'Yayın şu anda aktif değil',

  // Bildirim
  NOTIFICATIONS: 'BİLDİRİMLER',
  NOTIF_ON: 'AÇIK',
  NOTIF_OFF: 'KAPALI',
  NOTIF_DENIED: 'REDDEDİLDİ',
  NEW: 'YENİ',

  // Olaylar
  EVENTS: 'OLAYLAR',
  GOALS: 'GOLLER',
  YELLOW_CARD: 'SARI KART',
  RED_CARD: 'KIRMIZI KART',
  SECOND_YELLOW: '2. SARI = KIRMIZI',
  PENALTY: 'PENALTI',
  OWN_GOAL: 'KENDİ KALESİNE GOL',
  SUBSTITUTION: 'DEĞİŞİKLİK',

  // Sunucular
  SERVERS: 'SUNUCULAR',

  // Tahmin oyunu
  PREDICTIONS: 'TAHMİN OYUNU',
  PREDICTIONS_SUB: 'SKOR TAHMİNİ · TAM SKOR 5p · GOL FARKI 3p · SONUÇ 1p',
  PREDICTIONS_NO_MATCHES: 'Şu anda açık tahmin maçı yok.',
  PREDICTIONS_SAVE: 'KAYDET',
  PREDICTIONS_SAVED: 'Tahmin kaydedildi ✓',
  PREDICTIONS_LOGIN_REQUIRED: 'Tahmin yapmak için giriş yap',
  PREDICTIONS_NEED_SCORE: 'Skor gir',
  LEADERBOARD: 'PUAN TABLOSU',
  LEADERBOARD_EMPTY: 'Henüz tahmin yapılmadı',

  // Sohbet
  CHAT: 'SOHBET',
  CHAT_SUB: 'MAÇ HAKKINDA KONUŞ — KÜFÜR YOK, SAYGI VAR',
  CHAT_EMPTY: 'Henüz mesaj yok — ilk mesajı sen yaz!',
  CHAT_PLACEHOLDER_AUTH: 'Mesajını yaz…',
  CHAT_PLACEHOLDER_GUEST: 'Yazmak için giriş yap',
  CHAT_SEND: 'GÖNDER',

  // Auth
  AUTH_LOGIN: 'GİRİŞ YAP',
  AUTH_REGISTER: 'KAYIT OL',
  AUTH_LOGOUT: 'ÇIKIŞ',
  AUTH_EMAIL: 'E-POSTA',
  AUTH_PASSWORD: 'PAROLA',
  AUTH_NAME: 'AD',
  AUTH_GOOGLE: 'Google ile giriş',
} as const;

// İstatistik etiket sözlüğü (eski repo `app.js` 2724-2780'den port)
export const STAT_LABEL: Record<string, string> = {
  shots_on_goal:        'İSABETLİ ŞUT',
  shots_off_goal:       'İSABETSİZ ŞUT',
  blocked_shots:        'ENGELLENEN ŞUT',
  shots_woodwork:       'DİREKTEN DÖNEN ŞUT',
  shots_inside_box:     'CEZA SAHASI İÇİ ŞUT',
  shots_outside_box:    'CEZA SAHASI DIŞI ŞUT',
  big_chances:          'NET POZİSYON',
  big_chances_missed:   'KAÇAN NET POZİSYON',
  touches_in_opp_box:   'RAKİP CEZA SAHASINDA TOPLA BULUŞMA',
  total_shots:          'TOPLAM ŞUT',
  xg:                   'GOL BEKLENTİSİ (xG)',
  xgot:                 'İSABETLİ ŞUT BEKLENTİSİ (xGOT)',
  goal_kicks:           'KALE VURUŞU',
  corner_kicks:         'KORNER',
  offsides:             'OFSAYT',
  throw_ins:            'TAÇ ATIŞI',
  fouls:                'FAUL',
  goalkeeper_saves:     'KALECİ KURTARIŞI',
  total_passes:         'TOPLAM PAS',
  passes_accurate:      'İSABETLİ PAS',
  'passes_%':           'PAS İSABET %',
  accurate_crosses:     'İSABETLİ ORTA',
  long_balls:           'İSABETLİ UZUN TOP',
  tackles:              'TOP ÇALMA',
  interceptions:        'PAS ARASI',
  clearances:           'UZAKLAŞTIRMA',
  duels_won:            'KAZANILAN İKİLİ MÜCADELE',
  aerial_duels:         'KAZANILAN HAVA TOPU',
  dribbles:             'BAŞARILI ÇALIM',
  ball_possession:      'TOP HÂKİMİYETİ %',
  attacks:              'ATAK',
  dangerous_attacks:    'TEHLİKELİ ATAK',
  // Sayım bazlı (Incs)
  goals:                'GOLLER',
  penalty_goals:        'PENALTI GOLÜ',
  own_goals:            'KENDİ KALESİNE GOL',
  yellow_cards:         'SARI KART',
  second_yellow:        '2. SARIDAN KIRMIZI',
  red_cards:            'KIRMIZI KART',
  substitutions:        'DEĞİŞİKLİK',
};

// İstatistik satır sırası (Maçkolik tarzı: önce şutlar, sonra pas, sonra olay sayımları)
export const STAT_ORDER: { key: string; always?: boolean; icon?: string }[] = [
  { key: 'ball_possession' },
  { key: 'xg' },
  { key: 'xgot' },
  { key: 'total_shots' },
  { key: 'shots_on_goal' },
  { key: 'shots_off_goal' },
  { key: 'blocked_shots' },
  { key: 'shots_woodwork' },
  { key: 'shots_inside_box' },
  { key: 'shots_outside_box' },
  { key: 'big_chances' },
  { key: 'big_chances_missed' },
  { key: 'touches_in_opp_box' },
  { key: 'goal_kicks' },
  { key: 'corner_kicks' },
  { key: 'offsides' },
  { key: 'throw_ins' },
  { key: 'fouls' },
  { key: 'goalkeeper_saves' },
  { key: 'total_passes' },
  { key: 'passes_accurate' },
  { key: 'passes_%' },
  { key: 'accurate_crosses' },
  { key: 'long_balls' },
  { key: 'tackles' },
  { key: 'interceptions' },
  { key: 'clearances' },
  { key: 'duels_won' },
  { key: 'aerial_duels' },
  { key: 'dribbles' },
  { key: 'attacks' },
  { key: 'dangerous_attacks' },
  // Sayım bazlı — 0-0 da göster (always: true)
  { key: 'goals',          always: true, icon: '/icons/goal.png' },
  { key: 'penalty_goals',  icon: '/icons/goal.png' },
  { key: 'own_goals' },
  { key: 'yellow_cards',   always: true, icon: '/icons/yellowcard.png' },
  { key: 'second_yellow',  icon: '/icons/redcard.png' },
  { key: 'red_cards',      always: true, icon: '/icons/redcard.png' },
  { key: 'substitutions',  always: true, icon: '/icons/info.png' },
];

// Lig / turnuva aşaması adlarındaki İngilizce kalıpları Türkçe'ye çevir
// (ör. "Third Place Play-off" → "ÜÇÜNCÜLÜK MAÇI")
const LEAGUE_PHRASES: [RegExp, string][] = [
  [/third[\s-]?place[\s-]?(play[\s-]?off|match)?/gi, 'ÜÇÜNCÜLÜK MAÇI'],
  [/3rd[\s-]?place[\s-]?(play[\s-]?off|match)?/gi, 'ÜÇÜNCÜLÜK MAÇI'],
  [/semi[\s-]?finals?/gi, 'YARI FİNAL'],
  [/quarter[\s-]?finals?/gi, 'ÇEYREK FİNAL'],
  [/round of 16/gi, 'SON 16 TURU'],
  [/round of 32/gi, 'SON 32 TURU'],
  [/knockout[\s-]?stage/gi, 'ELEME AŞAMASI'],
  [/group[\s-]?stage/gi, 'GRUP AŞAMASI'],
  [/\bgroup\s+([a-h])\b/gi, '$1 GRUBU'],
  [/\bgrand\s+final\b/gi, 'BÜYÜK FİNAL'],
  [/\bfinals?\b/gi, 'FİNAL'],
  [/play[\s-]?offs?/gi, 'PLAY-OFF'],
  [/qualif(ication|ying|iers?)?/gi, 'ELEMELER'],
  [/1st round/gi, '1. TUR'],
  [/2nd round/gi, '2. TUR'],
  [/3rd round/gi, '3. TUR'],
  [/\bround\s+(\d+)\b/gi, '$1. HAFTA'],
  [/international friendl(y|ies)/gi, 'ULUSLARARASI HAZIRLIK'],
  [/club friendl(y|ies)/gi, 'KULÜP HAZIRLIK'],
  [/friendl(y|ies)/gi, 'HAZIRLIK'],
  [/\bwomen\b/gi, 'KADINLAR'],
  [/world cup/gi, 'DÜNYA KUPASI'],
  [/european championship/gi, 'AVRUPA ŞAMPİYONASI'],
  [/champions league/gi, 'ŞAMPİYONLAR LİGİ'],
  [/europa league/gi, 'AVRUPA LİGİ'],
  [/conference league/gi, 'KONFERANS LİGİ'],
  [/nations league/gi, 'ULUSLAR LİGİ'],
];

export const trLeagueName = (name?: string | null): string => {
  if (!name) return '';
  let out = String(name);
  for (const [re, tr] of LEAGUE_PHRASES) out = out.replace(re, tr);
  return out.replace(/\s{2,}/g, ' ').trim();
};

// EPS → durum etiketi (UI tarafında, server _zaten_ normalize'liyor ama
// SSR cache'ten ham EPS gelirse fallback olarak burada da var)
export const epsToLabel = (eps: string): { txt: string; live: boolean; finished: boolean; notStarted: boolean } => {
  const e = (eps || '').toString();
  if (e === '1H') return { txt: TR.FIRST_HALF, live: true, finished: false, notStarted: false };
  if (e === '2H') return { txt: TR.SECOND_HALF, live: true, finished: false, notStarted: false };
  if (e === 'HT') return { txt: TR.HALF_TIME, live: true, finished: false, notStarted: false };
  if (e === 'ET') return { txt: TR.EXTRA_TIME, live: true, finished: false, notStarted: false };
  if (e === 'PEN') return { txt: TR.PENALTIES, live: true, finished: false, notStarted: false };
  if (['FT', 'AET', 'AP', 'Pen.'].includes(e)) return { txt: TR.MATCH_ENDED, live: false, finished: true, notStarted: false };
  if (['NS', 'Not Started'].includes(e)) return { txt: TR.NOT_STARTED, live: false, finished: false, notStarted: true };
  // Dakika formatı ("40'", "90+3'") → canlı maç
  if (/^\d+(\+\d+)?'?$/.test(e)) return { txt: e.endsWith("'") ? e : `${e}'`, live: true, finished: false, notStarted: false };
  // İngilizce durum kodları → Türkçe
  const EN_STATUS: Record<string, string> = {
    'POSTP': 'ERTELENDİ', 'POSTP.': 'ERTELENDİ', 'POSTPONED': 'ERTELENDİ',
    'CANC': 'İPTAL', 'CANC.': 'İPTAL', 'CANCELLED': 'İPTAL', 'CANCELED': 'İPTAL',
    'AW': 'HÜKMEN', 'AWARDED': 'HÜKMEN',
    'SUSP': 'ASKIDA', 'SUSP.': 'ASKIDA', 'SUSPENDED': 'ASKIDA',
    'INT': 'DURDURULDU', 'INT.': 'DURDURULDU', 'INTERRUPTED': 'DURDURULDU',
    'ABAND': 'YARIDA KALDI', 'ABAND.': 'YARIDA KALDI', 'ABANDONED': 'YARIDA KALDI',
    'DELAYED': 'GECİKMELİ', 'DEL.': 'GECİKMELİ',
    'TBA': 'BELİRLENECEK', 'TBD': 'BELİRLENECEK',
    'BREAK': 'ARA', 'BREAK TIME': 'ARA',
  };
  const tr = EN_STATUS[e.toUpperCase()];
  if (tr) return { txt: tr, live: false, finished: false, notStarted: false };
  return { txt: e || '—', live: false, finished: false, notStarted: false };
};

// Pre-match heuristic — status string'den
export const isPreMatchStatus = (status?: string | null): boolean => {
  if (!status) return false;
  const s = String(status).toUpperCase();
  return s === 'NS' || s === 'BAŞLAMADI' || s.includes('MAÇ ÖNÜ') ||
         s.startsWith('BUGÜN') || s.startsWith('YARIN') ||
         /^\d{2}\.\d{2}/.test(status) || /^\d{2}:\d{2}/.test(status);
};
