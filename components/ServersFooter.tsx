'use client';
import { useEffect, useState } from 'react';
import { getClient } from '@/lib/api';

type Server = { id: string; label: string; region: string; status: 'online'|'checking'|'offline' };

const SERVERS: Server[] = [
  { id: 's1', label: 'Sunucu 1', region: 'TR',     status: 'online' },
  { id: 's2', label: 'Sunucu 2', region: 'Yedek',  status: 'online' },
  { id: 's3', label: 'Sunucu 3', region: 'EU',     status: 'online' },
  { id: 's4', label: 'Sunucu 4', region: 'US',     status: 'checking' },
  { id: 's5', label: 'Sunucu 5', region: 'Asia',   status: 'checking' },
  { id: 's6', label: 'Sunucu 6', region: 'Edge',   status: 'checking' },
];

export default function ServersFooter() {
  const [healthy, setHealthy] = useState(true);

  // Probe backend health every 60s — affects "Sunucu 1 (TR)" indicator
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const h = await getClient<{ status?: string }>('/api/health');
      if (alive) setHealthy(h?.status === 'ok');
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="mt-8 border-t border-[var(--line-soft)]" data-testid="servers-footer">
      <div className="mx-auto max-w-7xl px-4 py-4">
        <div className="text-center text-[10px] uppercase tracking-[0.4em] text-ink-low mb-3">SUNUCULAR</div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {SERVERS.map((s, i) => {
            // First server reflects real backend status
            const status = i === 0 ? (healthy ? 'online' : 'offline') : s.status;
            const dot = status === 'online' ? 'var(--green)' : status === 'checking' ? 'var(--amber)' : 'var(--red)';
            return (
              <div key={s.id}
                   className="glass rounded-lg px-3 py-2 flex items-center justify-between gap-2"
                   data-testid={`server-${s.id}`}>
                <div className="min-w-0 leading-tight">
                  <div className="font-mono text-xs text-ink-high">{s.label}</div>
                  <div className="text-[10px] text-ink-low uppercase tracking-widest">({s.region})</div>
                </div>
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dot, boxShadow: `0 0 8px ${dot}` }}/>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
