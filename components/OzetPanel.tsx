'use client';
/* Sağ kolon — ÖZET: filmin GERÇEK konusu (/api/boxoffice plot verisi, yeniden yazılmaz). */
import { useEffect, useState } from 'react';
import { getClient } from '@/lib/api';

type BoData = { ok: boolean; plot: string; credits?: string };

export default function OzetPanel() {
  const [data, setData] = useState<BoData | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const d = await getClient<BoData>('/api/boxoffice');
      if (alive && d?.ok) setData(d);
    };
    load();
    const id = setInterval(load, 300_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!data?.plot) return null;

  return (
    <div className="pnl" data-testid="ozet-panel">
      <div className="pnl-head">
        <span className="pnl-title">ÖZET</span>
      </div>
      <div className="oz-body">
        <p className={`oz-text ${expanded ? '' : 'clamped'}`} data-testid="ozet-plot">{data.plot}</p>
        <button className="oz-toggle" data-testid="ozet-toggle" onClick={() => setExpanded((v) => !v)}>
          {expanded ? '▲ GİZLE' : '▼ DEVAMINI GÖSTER'}
        </button>
        {expanded && data.credits && <div className="oz-credits" data-testid="ozet-credits">{data.credits}</div>}
      </div>
    </div>
  );
}
