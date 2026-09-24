'use client';
import { useEffect, useRef, useState } from 'react';
import { getClient } from '@/lib/api';

type Ev = { kind: 'goal'|'redcard'|'yellowcard'|'penalty'|'kickoff'|'halftime'|'fulltime'|'info'; title: string; body: string; team?: string };

const ICONS: Record<string,string> = {
  goal: '/icons/goal.png',
  redcard: '/icons/redcard.png',
  yellowcard: '/icons/yellowcard.png',
  penalty: '/icons/penalty.png',
  kickoff: '/icons/kickoff.png',
  halftime: '/icons/halftime.png',
  fulltime: '/icons/fulltime.png',
  info: '/icons/info.png',
};

const ACCENT: Record<string,string> = {
  goal: '#00ff88', redcard: '#ff0040', yellowcard: '#ffd700',
  penalty: '#00d4ff', kickoff: '#00d4ff', halftime: '#ffaa00',
  fulltime: '#aaaaaa', info: '#00d4ff',
};

// Compare watcher: detects score / event changes from /api/scores/top
type Tracked = { key: string; score1: number; score2: number; status: string };

export default function NotificationCenter() {
  const [queue, setQueue] = useState<Ev[]>([]);
  const [showing, setShowing] = useState<Ev | null>(null);
  const tracked = useRef<Record<string, Tracked>>({});
  const initial = useRef(true);

  // Poll top scores every 25s and diff against last snapshot to generate events.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const d = await getClient<{ matches?: any[] }>('/api/scores/top?n=5');
      if (!alive || !d?.matches) return;
      for (const m of d.matches) {
        const key = `${m.team1}__${m.team2}`;
        const prev = tracked.current[key];
        const s1 = (m.score1 === null || m.score1 === undefined) ? 0 : Number(m.score1);
        const s2 = (m.score2 === null || m.score2 === undefined) ? 0 : Number(m.score2);
        const status = String(m.status || '');
        if (!prev) {
          tracked.current[key] = { key, score1: s1, score2: s2, status };
          continue;
        }
        if (!initial.current) {
          // GOAL detect
          if (s1 > prev.score1) push({ kind: 'goal', title: 'GOL!', body: `${m.team1} ${s1}–${s2} ${m.team2}`, team: m.team1 });
          if (s2 > prev.score2) push({ kind: 'goal', title: 'GOL!', body: `${m.team1} ${s1}–${s2} ${m.team2}`, team: m.team2 });
          // Status transitions
          if (prev.status !== status) {
            if (/^\d+/.test(status) && !/^\d+/.test(prev.status)) push({ kind: 'kickoff', title: 'MAÇ BAŞLADI', body: `${m.team1} vs ${m.team2}` });
            if (/devre arasi|halftime|^ht$/i.test(status)) push({ kind: 'halftime', title: 'DEVRE ARASI', body: `${m.team1} ${s1}–${s2} ${m.team2}` });
            if (/mac sonu|fulltime|^ft$/i.test(status)) push({ kind: 'fulltime', title: 'MAÇ SONU', body: `${m.team1} ${s1}–${s2} ${m.team2}` });
          }
        }
        tracked.current[key] = { key, score1: s1, score2: s2, status };
      }
      initial.current = false;
    };
    tick();
    const id = setInterval(tick, 25_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const push = (e: Ev) => {
    setQueue(q => [...q, e]);
    // Optionally fire system notification when permission granted
    try {
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        new Notification(e.title, { body: e.body, icon: ICONS[e.kind], badge: ICONS[e.kind], tag: e.title + e.body });
      }
    } catch { /* tarayıcı Notification API'sini desteklemiyor — in-app toast ile devam */ }
    // POST log (fire-and-forget)
    try { fetch('/api/notifications/log', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(e) }); } catch { /* analytics log opsiyonel — kullanıcı deneyimini etkilemez */ }
  };

  // Show next in queue
  useEffect(() => {
    if (showing || queue.length === 0) return;
    const next = queue[0];
    setQueue(q => q.slice(1));
    setShowing(next);
    const t = setTimeout(() => setShowing(null), 4500);
    return () => clearTimeout(t);
  }, [queue, showing]);

  if (!showing) return null;
  const c = ACCENT[showing.kind] || '#00d4ff';

  return (
    <div
      className="fixed top-3 left-1/2 -translate-x-1/2 z-[99999] w-[92%] max-w-sm glass rounded-xl p-3 animate-rise"
      style={{ borderColor: c+'55', boxShadow: `0 8px 30px rgba(0,0,0,.6), inset 0 0 0 1px ${c}55` }}
      role="status" aria-live="polite"
      data-testid={`notif-${showing.kind}`}
      onClick={() => setShowing(null)}
    >
      <div className="flex items-center gap-3">
        <img src={ICONS[showing.kind]} alt="" className="w-9 h-9 shrink-0" />
        <div className="min-w-0">
          <div className="font-display tracking-wider text-base" style={{ color: c, textShadow: `0 0 12px ${c}55` }}>{showing.title}</div>
          <div className="text-sm text-ink-mid truncate">{showing.body}</div>
        </div>
      </div>
    </div>
  );
}
