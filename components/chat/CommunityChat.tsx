'use client';
/* Topluluk Sohbeti (proto/chat.html + PRD-D): anonim kimlik otomatik (device_id + HttpOnly anon JWT),
   kurallar KAYAN YAZI + tıkla → tam liste/onay, 75 canlı mesaj, 2.5s artımlı polling (since cursor),
   mod/admin mesaj silme, ban metni, Google/e-posta/Discord(yakında) yükseltme. Tüm yetki backend'de. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/components/AuthProvider';

type Msg = { id: string; text: string; name: string; role: string; kind: string; identity_id: string; created_at: string; bot: boolean };
type Me = { id: string; name: string; role: string; kind: string; accepted_rules: boolean; banned: boolean; ban_reason: string; ban_until: string | null };

function deviceId(): string {
  try {
    let d = localStorage.getItem('bb_device');
    if (!d) { d = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/-/g, '').slice(0, 32); localStorage.setItem('bb_device', d); }
    return d;
  } catch { return ''; }
}

const fmtTime = (iso: string) => { try { return new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }); } catch { return ''; } };

const TT_ICON = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5c-1.42 0-2.6-1.16-2.6-2.6 0-1.72 1.66-3.01 3.37-2.48V9.66c-3.45-.46-6.47 2.22-6.47 5.64 0 3.33 2.76 5.7 5.69 5.7 3.14 0 5.69-2.55 5.69-5.7V9.01a7.35 7.35 0 0 0 4.3 1.38V7.3s-1.88.09-3.24-1.48z"/></svg>;
const X_ICON = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M18.9 2H22l-7.6 8.7L23 22h-6.8l-5.3-6.9L4.8 22H1.7l8.1-9.3L0 2h7l4.8 6.3L18.9 2zm-1.2 18h1.9L6.4 3.9H4.4L17.7 20z"/></svg>;
const BOT_ICON = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M12 2a1 1 0 0 1 1 1v1.1A6 6 0 0 1 18 10v1h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-1.1A6 6 0 0 1 12 22a6 6 0 0 1-5.9-4H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h1v-1a6 6 0 0 1 5-5.9V3a1 1 0 0 1 1-1zm-3 9.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zm6 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM9 17a3 3 0 0 0 6 0H9z"/></svg>;

/* Bot mesajı: "Bizi takip et ;" + Logo:URL satırları (TikTok / X). Başka açıklama yok. */
function BotBody({ text }: { text: string }) {
  const lines = text.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  return (
    <div className="cc-bot-lines" data-testid="chat-bot-body">
      {lines.map((l, i) => {
        const url = l.match(/https?:\/\/\S+/)?.[0];
        if (!url) return <div className="cc-bot-head" key={i}>{l}</div>;
        const tt = /tiktok\.com/i.test(url);
        const x = /(^|\/\/)(www\.)?(x\.com|twitter\.com)/i.test(url);
        return (
          <a key={i} className="cc-bot-link" href={url} target="_blank" rel="noopener noreferrer" data-testid={tt ? 'chat-bot-tiktok' : x ? 'chat-bot-x' : 'chat-bot-link'}>
            <span className={`cc-bot-logo ${tt ? 'tt' : x ? 'x' : ''}`}>{tt ? TT_ICON : x ? X_ICON : '↗'}</span>
            <span>{url}</span>
          </a>
        );
      })}
    </div>
  );
}

export default function CommunityChat() {
  const { user } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [rules, setRules] = useState<string[]>([]);
  const [accepted, setAccepted] = useState(0);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [online, setOnline] = useState(0);
  const [slow, setSlow] = useState(0);
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const [rulesOpen, setRulesOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const sinceRef = useRef('');
  const listRef = useRef<HTMLDivElement>(null);
  const liveLimitRef = useRef(75);

  const identify = useCallback(async () => {
    try {
      const r = await fetch('/api/community/identity', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId() }) });
      const d = await r.json();
      if (d?.identity) { setMe(d.identity); setRules(d.rules || []); setSlow(d.slow_mode_sec || 0); }
    } catch { /* sessiz */ }
    try { const r = await fetch('/api/community/rules'); const d = await r.json(); setAccepted(d.accepted_count || 0); if (d.rules) setRules(d.rules); } catch { /* */ }
  }, []);

  useEffect(() => { identify(); }, [identify, user?.id]);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch(`/api/community/recent${sinceRef.current ? `?since=${encodeURIComponent(sinceRef.current)}` : ''}`, { cache: 'no-store', credentials: 'same-origin' });
        if (!r.ok || !alive) return;
        const d = await r.json();
        if (d.live_limit) liveLimitRef.current = d.live_limit;
        if (Array.isArray(d.messages) && d.messages.length) {
          setMsgs((prev) => {
            const ids = new Set(prev.map((m) => m.id));
            const merged = [...prev, ...d.messages.filter((m: Msg) => !ids.has(m.id))];
            return merged.slice(-liveLimitRef.current);
          });
          sinceRef.current = d.messages[d.messages.length - 1].created_at;
        }
        setOnline(d.online || 0); setSlow(d.slow_mode_sec || 0);
        if (d.me) setMe(d.me);
      } catch { /* sessiz */ }
    };
    poll();
    const id = setInterval(poll, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight; }, [msgs.length]);

  const acceptRules = async () => {
    const r = await fetch('/api/community/rules/accept', { method: 'POST', credentials: 'same-origin' });
    if (r.ok) { const d = await r.json(); setAccepted(d.accepted_count || 0); setMe((m) => (m ? { ...m, accepted_rules: true } : m)); setRulesOpen(false); }
  };

  const send = async () => {
    const t = text.trim();
    if (!t || busy) return;
    if (!me?.accepted_rules) { setRulesOpen(true); return; }
    setBusy(true); setErr('');
    try {
      const r = await fetch('/api/community/send', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t }) });
      const d = await r.json().catch(() => null);
      if (!r.ok) { setErr(d?.detail || 'Gönderilemedi'); }
      else { setText(''); if (d?.message) { setMsgs((p) => [...p, d.message].slice(-liveLimitRef.current)); sinceRef.current = d.message.created_at; } }
    } catch { setErr('Sunucuya ulaşılamadı'); }
    finally { setBusy(false); }
  };

  const del = async (id: string) => {
    const r = await fetch(`/api/community/message/${id}`, { method: 'DELETE', credentials: 'same-origin' });
    if (r.ok) setMsgs((p) => p.filter((m) => m.id !== id));
  };

  const isMod = me?.role === 'admin' || me?.role === 'moderator';
  const banned = !!me?.banned;

  return (
    <div className="pnl cc" id="topluluk" data-testid="community-chat">
      <div className="cc-top">
        <div className="cc-brand"><span className="cc-b1">BANBAN</span><span className="cc-b2">SPORTS</span><span className="cc-b3">COMMUNITY</span></div>
        <div className="cc-actions">
          <span className="cc-online" data-testid="chat-online"><span className="cc-dot" />{online} online</span>
          <button className="cc-info" onClick={() => setRulesOpen(true)} data-testid="chat-rules-btn" title="Topluluk Kuralları" aria-label="Topluluk Kuralları">ⓘ</button>
        </div>
      </div>
      <div className="cc-room">
        <div><div className="cc-room-title">💬 BanbanSports Topluluk</div><div className="cc-room-sub">Herkes aynı odada · sağlıklı ve edepli ortam</div></div>
        <div className="cc-id" data-testid="chat-identity">
          <span className={`cc-badge ${me?.kind === 'anon' ? 'guest' : me?.role}`}>{me?.role === 'admin' ? 'ADMIN' : me?.role === 'moderator' ? 'MOD' : me?.kind === 'anon' ? 'Misafir' : 'Üye'}</span>
          <span className="cc-name">{me?.name || '…'}</span>
        </div>
      </div>
      <div className="cc-msgs" ref={listRef} data-testid="chat-messages">
        <div className="cc-sys">BanbanSports topluluk odasına hoş geldin.</div>
        {msgs.map((m) => (
          <div key={m.id} className={`cc-msg ${m.bot ? 'bot' : ''} ${m.identity_id === me?.id ? 'mine' : ''}`} data-testid={m.bot ? 'chat-bot-message' : 'chat-message'}>
            {m.bot && <span className="cc-bot-avatar" aria-hidden="true">{BOT_ICON}</span>}
            <span className={`cc-role ${m.role}`}>{m.bot ? 'BOT' : m.role === 'admin' ? 'ADMIN' : m.role === 'moderator' ? 'MOD' : m.kind === 'anon' ? 'M' : 'Ü'}</span>
            <span className="cc-author">{m.name}{m.bot && <span className="cc-bot-badge">BOT</span>}</span>
            <span className="cc-time">{fmtTime(m.created_at)}</span>
            {m.bot ? <BotBody text={m.text} /> : <div className="cc-text">{m.text}</div>}
            {isMod && !m.bot && <button className="cc-del" onClick={() => del(m.id)} title="Mesajı sil" data-testid="chat-delete">✕</button>}
          </div>
        ))}
      </div>
      {banned ? (
        <div className="cc-banned" data-testid="chat-banned">Topluluk kurallarına uymadığınız için banlandınız{me?.ban_until ? ` · ${new Date(me.ban_until).toLocaleString('tr-TR')} kadar` : ''}.</div>
      ) : (
        <div className="cc-input">
          <input value={text} maxLength={500} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
            placeholder="Mesajını yaz… (giriş gerekmez)" data-testid="chat-input" />
          <button className="cc-send" onClick={send} disabled={busy || !text.trim()} data-testid="chat-send">Gönder</button>
        </div>
      )}
      <div className="cc-foot">
        <span>{err ? <span className="cc-err" data-testid="chat-error">{err}</span> : slow > 0 ? `Yavaş mod: ${slow} sn` : 'Saygılı olun • Spam yapmayın'}</span>
        <span>{text.length}/500</span>
      </div>
      {rulesOpen && (
        <div className="cc-overlay" onClick={() => setRulesOpen(false)} data-testid="chat-rules-overlay">
          <div className="cc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="cc-drawer-head"><span>📜 TOPLULUK KURALLARI</span><button onClick={() => setRulesOpen(false)} aria-label="Kapat">✕</button></div>
            <div className="cc-rules">
              {rules.map((r, i) => (<div className="cc-rule" key={i}><span className="cc-rule-n">{i + 1}</span><span>{r}</span></div>))}
            </div>
            <div className="cc-drawer-foot">
              <span className="cc-count" data-testid="chat-accepted-count">{accepted.toLocaleString('tr-TR')} kişi onayladı</span>
              {me?.accepted_rules ? <span className="cc-ok">✔ Okudum, Anladım</span> : <button className="cc-accept" onClick={acceptRules} data-testid="chat-accept-rules">Okudum, Anladım ✔</button>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
