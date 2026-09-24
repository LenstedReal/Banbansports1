'use client';
/* Sağ kolon — SUNUCULAR. VideoPlayer'ın window.bbSwitchServer API'siyle konuşur. */
import { useEffect, useState } from 'react';

declare global {
  interface Window {
    bbSwitchServer?: (idx: number) => void;
    bbServerIndex?: number;
    bbServerCount?: number;
  }
}

const SERVER_NAMES = [
  'Sunucu 1 (TR)', 'Sunucu 2 (Yedek)', 'Sunucu 3 (EU)',
  'Sunucu 4 (US)', 'Sunucu 5 (Asia)', 'Sunucu 6 (Edge)',
];

export default function ServerPanel() {
  const [activeServer, setActiveServer] = useState(0);
  const [serverCount, setServerCount] = useState(1);

  useEffect(() => {
    const tick = () => {
      setActiveServer(window.bbServerIndex ?? 0);
      setServerCount(window.bbServerCount ?? 1);
    };
    tick();
    const onChange = () => tick();
    window.addEventListener('bb:server-changed', onChange);
    const id = setInterval(tick, 3000);
    return () => {
      window.removeEventListener('bb:server-changed', onChange);
      clearInterval(id);
    };
  }, []);

  const handleClick = (i: number) => {
    if (i >= serverCount) return;
    if (typeof window.bbSwitchServer === 'function') window.bbSwitchServer(i);
  };

  return (
    <div className="pnl" id="sunucular" data-testid="server-selector">
      <div className="pnl-head">
        <span className="pnl-title">SUNUCULAR</span>
      </div>
      <div className="srv-list">
        {SERVER_NAMES.map((name, i) => {
          const usable = i < serverCount;
          const isActive = usable && i === activeServer;
          return (
            <div
              key={i}
              className={`srv-row ${isActive ? 'active' : ''} ${usable ? '' : 'disabled'}`}
              data-testid={`server-${i}`}
              onClick={() => handleClick(i)}
              role="button"
              aria-disabled={!usable}
            >
              <span className="srv-name">{name}</span>
              <span className={`srv-state ${usable ? 'on' : 'off'}`}>{usable ? 'AKTİF' : 'DEVRE DIŞI'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
