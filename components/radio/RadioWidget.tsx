'use client';
/* BANBAN LIVE RADIO (radio_*.jpg + PRD-B): durumlar RADYO ARANIYOR/BAĞLANILIYOR/🔴 CANLI/DURAKLATILDI/YAYIN DEĞİŞTİRİLİYOR/
   YAYIN BULUNAMADI; timeout 12s, stall 15s, fallback max 8 hop; autoplay yok; request-id ile stale sonuç yoksayılır (Strict Mode fix). */
import { useCallback, useEffect, useRef, useState } from 'react';

type Station = { uuid: string; name: string; url: string; codec: string; bitrate: number; country: string; tags: string; clicks: number };
type Status = 'search' | 'connecting' | 'live' | 'paused' | 'switching' | 'notfound' | 'idle';
const CHIPS = [['', 'TÜRKİYE'], ['pop', 'POP'], ['rock', 'ROCK'], ['jazz', 'JAZZ'], ['news', 'HABER'], ['sports', 'SPOR'], ['dance', 'DANCE']];
const LABEL: Record<Status, string> = { search: 'RADYO ARANIYOR', connecting: 'BAĞLANILIYOR', live: '🔴 CANLI', paused: 'DURAKLATILDI', switching: 'YAYIN DEĞİŞTİRİLİYOR', notfound: 'YAYIN BULUNAMADI', idle: 'DİNLEMEK İÇİN PLAY' };

export default function RadioWidget() {
  const [stations, setStations] = useState<Station[]>([]);
  const [cur, setCur] = useState<Station | null>(null);
  const [status, setStatus] = useState<Status>('search');
  const [tag, setTag] = useState('');
  const [q, setQ] = useState('');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const reqRef = useRef(0);
  const hopRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (t: string, query: string) => {
    const id = ++reqRef.current;
    setStatus((s) => (s === 'live' || s === 'paused' ? s : 'search'));
    try {
      const r = await fetch(`/api/radio?country=TR&tag=${encodeURIComponent(t)}&q=${encodeURIComponent(query)}&limit=40`, { cache: 'no-store' });
      const d = await r.json();
      if (id !== reqRef.current) return; // stale
      const list: Station[] = d.stations || [];
      setStations(list);
      setCur((c) => c || list[0] || null);
      setStatus((s) => (list.length ? (s === 'live' || s === 'paused' ? s : 'idle') : 'notfound'));
    } catch (e: any) {
      if (e?.name === 'AbortError' || id !== reqRef.current) return;
      setStatus('notfound');
    }
  }, []);

  useEffect(() => { load(tag, q); }, [tag, q, load]);
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); audioRef.current?.pause(); }, []);

  const clearT = () => { if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; } };

  const tryNext = useCallback((from: Station | null) => {
    if (hopRef.current >= 8) { setStatus('notfound'); return; }
    hopRef.current += 1;
    const i = stations.findIndex((s) => s.uuid === from?.uuid);
    const nxt = stations[(i + 1) % Math.max(stations.length, 1)];
    if (!nxt || nxt.uuid === from?.uuid) { setStatus('notfound'); return; }
    setStatus('switching');
    play(nxt, true); // eslint-disable-line @typescript-eslint/no-use-before-define
  }, [stations]); // eslint-disable-line react-hooks/exhaustive-deps

  const play = useCallback((s: Station, auto = false) => {
    if (!auto) hopRef.current = 0;
    clearT();
    let a = audioRef.current;
    if (!a) { a = new Audio(); a.preload = 'none'; (a as any).crossOrigin = null; audioRef.current = a; }
    const el = a;
    el.onplaying = () => { clearT(); setStatus('live'); fetch(`/api/radio/click/${s.uuid}`, { method: 'POST' }).catch(() => {}); timerRef.current = setTimeout(() => { if (el.paused === false && el.readyState < 3) tryNext(s); }, 15000); };
    el.onstalled = () => { clearT(); timerRef.current = setTimeout(() => tryNext(s), 15000); };
    el.onerror = () => tryNext(s);
    el.onpause = () => setStatus((st) => (st === 'switching' || st === 'connecting' ? st : 'paused'));
    setCur(s); setStatus('connecting');
    el.src = s.url; el.load();
    timerRef.current = setTimeout(() => { if (el.readyState < 3) tryNext(s); }, 12000);
    el.play().catch(() => { clearT(); setStatus('idle'); });
  }, [tryNext]);

  const toggle = () => {
    const a = audioRef.current;
    if (status === 'live' && a) { a.pause(); setStatus('paused'); return; }
    if (status === 'paused' && a && cur) { a.play().then(() => setStatus('live')).catch(() => play(cur)); return; }
    if (cur) play(cur);
  };

  return (
    <div className="pnl rw" id="radyo" data-testid="radio-widget">
      <div className="rw-head"><span className="rw-ico">📻</span><span className="rw-title">BANBAN LIVE RADIO</span></div>
      <div className="rw-now">
        <div className="rw-art">{cur ? cur.name.slice(0, 2).toUpperCase() : '·'}</div>
        <div className="rw-meta">
          <div className="rw-name" data-testid="radio-station-name">{cur?.name || 'İstasyon seçilmedi'}</div>
          <div className="rw-sub">{cur ? `${cur.country} · ${cur.codec || '—'} · ${cur.bitrate ? cur.bitrate + 'K' : '—'}` : 'Şu anda kullanılabilir istasyon aranıyor…'}</div>
          <div className={`rw-status ${status}`} data-testid="radio-status">{LABEL[status]}{status === 'live' && <span className="rw-eq" aria-hidden="true"><i /><i /><i /><i /></span>}</div>
        </div>
        <button className={`rw-play ${status === 'live' ? 'on' : ''}`} onClick={toggle} aria-label="Oynat/Duraklat" data-testid="radio-play">
          {status === 'live' ? <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z" /></svg> : <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>}
        </button>
      </div>
      <div className="rw-search">
        <input placeholder="İstasyon ara (Power, Kral, Metro…)" value={q} onChange={(e) => setQ(e.target.value)} data-testid="radio-search" />
        <button onClick={() => cur && tryNext(cur)} title="Sonraki istasyon" aria-label="Sonraki" data-testid="radio-next"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6h2v12h-2z" /></svg></button>
      </div>
      <div className="rw-chips">{CHIPS.map(([v, l]) => (<button key={v} className={`rw-chip ${tag === v ? 'on' : ''}`} onClick={() => setTag(v)} data-testid={`radio-chip-${l}`}>{l}</button>))}</div>
      <div className="rw-list" data-testid="radio-list">
        {stations.map((s, i) => (
          <button key={s.uuid} className={`rw-item ${cur?.uuid === s.uuid ? 'on' : ''}`} onClick={() => play(s)} data-testid="radio-item">
            <span className="rw-n">{String(i + 1).padStart(2, '0')}</span>
            <span className="rw-item-name">{s.name}</span>
            <span className="rw-item-meta">{s.codec || '—'} {s.bitrate ? `${s.bitrate}K` : ''}</span>
          </button>
        ))}
        {!stations.length && <div className="rw-empty">{status === 'search' ? 'Aranıyor…' : 'Şu anda kullanılabilir canlı istasyon bulunamadı.'}</div>}
      </div>
      <div className="rw-foot"><span>{stations.length} İSTASYON</span><span>RADIO BROWSER</span></div>
    </div>
  );
}
