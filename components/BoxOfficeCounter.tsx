'use client';
import { useEffect, useRef, useState } from 'react';
import { getClient } from '@/lib/api';

type LocalEntry = { label: string; gross_usd: number; rate_per_sec_usd: number; viewers: number; viewers_per_sec: number };

type BoxOfficeData = {
  ok: boolean;
  movie: { id: string; title: string; title_en: string; release_date: string };
  gross_usd: { domestic: number; international: number; worldwide: number };
  rate_per_sec_usd: number;
  viewers: { domestic: number; international: number; total: number; per_sec: number };
  local?: Record<string, LocalEntry>;
  imdb: { rating: number; votes: number } | null;
  fx: Record<string, number | null>;
  fx_metadata?: { active_source?: string };
  plot: string;
  credits?: string;
  fetched_at: string;
  age_sec: number;
  refresh_sec: number;
  source: string;
};

const CURRENCIES: { code: string; symbol: string; flag: string }[] = [
  { code: 'USD', symbol: '$', flag: '🇺🇸/🇨🇦' },
  { code: 'TRY', symbol: '₺', flag: '🇹🇷' },
  { code: 'EUR', symbol: '€', flag: '🇪🇺' },
  { code: 'GBP', symbol: '£', flag: '🇬🇧' },
  { code: 'JPY', symbol: '¥', flag: '🇯🇵' },
];

const POLL_MS = 60_000; // backend zaten 15/20/30dk aralıkla scrape eder; bu sadece cache okur

type Vals = { w: number; i: number; l: number; wv: number; iv: number; lv: number };
const ZERO: Vals = { w: 0, i: 0, l: 0, wv: 0, iv: 0, lv: 0 };

export default function BoxOfficeCounter({ onPlot, onImdb, onMeta }: {
  onPlot?: (plot: string, credits?: string) => void;
  onImdb?: (rating: number, votes: string) => void;
  onMeta?: (meta: string) => void;
}) {
  const [data, setData] = useState<BoxOfficeData | null>(null);
  const [currency, setCurrency] = useState('TRY'); // varsayılan yerel: Türkiye
  const [scope, setScope] = useState<'intl' | 'local'>('intl'); // iki sistem: uluslararası / yerel
  const [disp, setDisp] = useState<Vals>(ZERO);
  const dataRef = useRef<BoxOfficeData | null>(null);
  const dispRef = useRef<Vals>(ZERO);
  const fxRef = useRef(1);
  const curRef = useRef(currency);
  const t0Ref = useRef(0);
  curRef.current = currency;

  // Üç kapsamın (dünya / uluslararası / yerel) o anki gerçek hedefleri + hızları
  const targetNow = (): { t: Vals; r: Vals } => {
    const d = dataRef.current;
    if (!d) return { t: ZERO, r: ZERO };
    const off = d.age_sec + (performance.now() - t0Ref.current) / 1000;
    const fx = fxRef.current;
    const ww = d.gross_usd.worldwide || 1;
    const rate = d.rate_per_sec_usd;
    const iR = rate * (d.gross_usd.international / ww);
    const ivR = d.viewers.per_sec * (d.viewers.international / (d.viewers.total || 1));
    const loc = d.local?.[curRef.current];
    return {
      t: {
        w: (ww + rate * off) * fx,
        i: (d.gross_usd.international + iR * off) * fx,
        l: ((loc?.gross_usd ?? 0) + (loc?.rate_per_sec_usd ?? 0) * off) * fx,
        wv: d.viewers.total + d.viewers.per_sec * off,
        iv: d.viewers.international + ivR * off,
        lv: (loc?.viewers ?? 0) + (loc?.viewers_per_sec ?? 0) * off,
      },
      r: {
        w: rate * fx, i: iR * fx, l: (loc?.rate_per_sec_usd ?? 0) * fx,
        wv: d.viewers.per_sec, iv: ivR, lv: loc?.viewers_per_sec ?? 0,
      },
    };
  };

  // Veri çek + tabanı senkronla
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const d = await getClient<BoxOfficeData>('/api/boxoffice');
      if (!alive || !d || !d.ok) return;
      dataRef.current = d;
      t0Ref.current = performance.now();
      setData(d);
      if (d.plot) onPlot?.(d.plot, d.credits);
      if (d.imdb) onImdb?.(d.imdb.rating, d.imdb.votes.toLocaleString('tr-TR'));
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Kaynak satırı kart başlığına taşındı — CinemaSection'a bildir
  useEffect(() => {
    if (!data) return;
    const fxLabel = ({ tradingview: 'TradingView FX', doviz_com: 'Doviz.com FX', crypto_proxy: 'BtcTurk/Paribu FX' } as Record<string, string>)[data.fx_metadata?.active_source || ''] || 'TradingView FX';
    const upd = new Date(data.fetched_at).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    onMeta?.(`Box Office Mojo · IMDb · ${fxLabel} · Son güncelleme ${upd}`);
  }, [data]);

  // Kur oranını ref'te tut
  useEffect(() => {
    if (data) fxRef.current = currency === 'USD' ? 1 : Number(data.fx[currency]) || 1;
  }, [currency, data]);

  // Para birimi değişince ekran değerlerini anında gerçek değere eşitle (ritim değişmez)
  useEffect(() => {
    if (!dataRef.current) return;
    dispRef.current = { ...targetNow().t };
    setDisp({ ...dispRef.current });
  }, [currency]);

  // Odometre sayaç: normalde BİRER BİRER (+1/sn); ilk yükleme / yeni veri gelişinde hızlı sarım
  useEffect(() => {
    if (!data) return;
    const step = (shown: number, target: number, rps: number) => {
      const diff = target - shown;
      // 120sn'den büyük gecikmede küçük ve göze görünmez senkron sarımı;
      // ilk yüklemede (shown=0) tam sarım. Normal akış: birer birer.
      if (shown <= 0 || diff > Math.max(rps * 120, 2000)) {
        return shown + Math.max(diff * 0.22, 1);
      }
      if (diff <= 0) return shown;
      return shown + 1; // birer birer
    };
    const id = setInterval(() => {
      const { t, r } = targetNow();
      const c = dispRef.current;
      dispRef.current = {
        w: step(c.w, t.w, r.w), i: step(c.i, t.i, r.i), l: step(c.l, t.l, r.l),
        wv: step(c.wv, t.wv, r.wv), iv: step(c.iv, t.iv, r.iv), lv: step(c.lv, t.lv, r.lv),
      };
      setDisp({ ...dispRef.current });
    }, 1000);
    return () => clearInterval(id);
  }, [data]);

  // Veri gelene kadar hiçbir şey gösterme — kart hazır olunca otomatik belirir
  if (!data) return null;

  const cur = CURRENCIES.find((c) => c.code === currency) || CURRENCIES[0];
  const localEntry = data.local?.[currency];
  const isLocal = scope === 'local';
  const fmt = (n: number) => Math.floor(n).toLocaleString('tr-TR');
  const votes = data.imdb ? data.imdb.votes.toLocaleString('tr-TR') : null;

  return (
    <div className="bo2" data-testid="boxoffice-card">
      <div className="bo2-tabs-row">
        <div className="bo2-cur-tabs" role="tablist" aria-label="Para birimi">
          {CURRENCIES.map((c) => (
            <button
              key={c.code}
              role="tab"
              aria-selected={currency === c.code}
              className={`bo2-cur-tab ${currency === c.code ? 'active' : ''}`}
              data-testid={`boxoffice-currency-${c.code.toLowerCase()}`}
              onClick={(e) => { e.stopPropagation(); setCurrency(c.code); }}
            >
              {c.flag} {c.code}
            </button>
          ))}
        </div>
        <div className="bo2-scope-tabs" role="tablist" aria-label="Sistem">
          <button
            role="tab"
            aria-selected={!isLocal}
            className={`bo2-scope-tab ${!isLocal ? 'active' : ''}`}
            data-testid="boxoffice-scope-world"
            onClick={(e) => { e.stopPropagation(); setScope('intl'); }}
          >
            🌍 ULUSLARARASI SİSTEM
          </button>
          <button
            role="tab"
            aria-selected={isLocal}
            className={`bo2-scope-tab ${isLocal ? 'active' : ''}`}
            data-testid="boxoffice-scope-local"
            onClick={(e) => { e.stopPropagation(); setScope('local'); }}
          >
            {cur.flag} YEREL SİSTEM · {localEntry?.label ?? ''}
          </button>
        </div>
      </div>

      <div className="bo2-main">
        <div className="bo2-block">
          <div className="bo2-label">
            {isLocal ? <>{cur.flag} {localEntry?.label ?? 'YEREL'} HASILATI</> : <>🌍 DÜNYA GENELİ HASILAT</>}
          </div>
          <div className="bo2-value" data-testid="boxoffice-gross">
            <span className="bo2-cur-symbol">{cur.symbol}</span>{fmt(isLocal ? disp.l : disp.w)}
          </div>
        </div>
        <div className="bo2-block">
          <div className="bo2-label">
            {isLocal ? <>{cur.flag} {localEntry?.label ?? 'YEREL'} SEYİRCİSİ</> : <>SİNEMA SEYİRCİSİ</>}
          </div>
          <div className="bo2-value v-viewers" data-testid="boxoffice-viewers">
            {fmt(isLocal ? disp.lv : disp.wv)}
          </div>
        </div>
      </div>

      <div className="bo2-breakdown">
        {isLocal ? (
          <div className="bo2-bd">
            <span className="bo2-bd-label">🌍 DÜNYA GENELİ</span>
            <span className="bo2-bd-value" data-testid="boxoffice-world-secondary">{cur.symbol}{fmt(disp.w)}</span>
            <span className="bo2-bd-sub" data-testid="boxoffice-world-secondary-viewers">Seyirci: {fmt(disp.wv)}</span>
          </div>
        ) : (
          <div className="bo2-bd">
            <span className="bo2-bd-label">{cur.flag} YEREL · {localEntry?.label ?? '—'}</span>
            <span className="bo2-bd-value" data-testid="boxoffice-local">{cur.symbol}{fmt(disp.l)}</span>
            <span className="bo2-bd-sub" data-testid="boxoffice-local-viewers">Seyirci: {fmt(disp.lv)}</span>
          </div>
        )}
        <div className="bo2-bd">
          <span className="bo2-bd-label">🌐 ULUSLARARASI</span>
          <span className="bo2-bd-value" data-testid="boxoffice-international">{cur.symbol}{fmt(disp.i)}</span>
          <span className="bo2-bd-sub" data-testid="boxoffice-intl-viewers">Seyirci: {fmt(disp.iv)}</span>
        </div>
        <div className="bo2-bd">
          <span className="bo2-bd-label">ARTIŞ HIZI</span>
          <span className="bo2-bd-value v-rate" data-testid="boxoffice-rate">
            ~${Math.floor(data.rate_per_sec_usd * 60).toLocaleString('en-US')}/dk
          </span>
          <span className="bo2-bd-sub">Vizyon: 31 Temmuz 2026</span>
        </div>
      </div>
    </div>
  );
}
