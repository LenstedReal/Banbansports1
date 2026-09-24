'use client';
/* SOHBET MODERASYON (KALAN_ISLER): kimlikler (kayıtlı+anonim), MOD yap/çıkar, user/ip/device ban, ban listesi/unban,
   yavaş mod, canlı mesaj limiti, bot (TikTok/X) metin+aralık, 7 günlük güvenlik logu, şifre sıfırlama talepleri, tam kayıt. */
import { useCallback, useEffect, useState } from 'react';

const j = async (url: string, init?: RequestInit) => { const r = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...init }); const d = await r.json().catch(() => null); if (!r.ok) throw new Error(d?.detail || `HTTP ${r.status}`); return d; };

type Ident = { id: string; name: string; role: string; kind: string; accepted_rules: boolean; banned: boolean; ban_reason: string; device_id: string; ip_hash: string; ip?: string; last_seen: string | null };
type Ban = { id: string; type: string; name: string; reason: string; until: string | null; created_at: string; active: boolean };

export default function ChatModeration({ notify }: { notify: (m: string) => void }) {
  const [idents, setIdents] = useState<Ident[]>([]);
  const [bans, setBans] = useState<Ban[]>([]);
  const [settings, setSettings] = useState<any>({});
  const [log, setLog] = useState<any[]>([]);
  const [resets, setResets] = useState<any[]>([]);
  const [msgs, setMsgs] = useState<any[]>([]);
  const [banForm, setBanForm] = useState({ target: '', type: 'user', minutes: 60, reason: 'Topluluk kurallarına aykırı davranış' });
  const [q, setQ] = useState('');

  const reload = useCallback(async () => {
    try {
      const [a, b, c, d, e, f] = await Promise.all([j('/api/community/admin/identities'), j('/api/community/admin/bans'), j('/api/community/admin/settings'), j('/api/community/admin/log'), j('/api/community/admin/reset-requests'), j('/api/community/admin/messages?limit=200')]);
      setIdents(a.identities || []); setBans(b.bans || []); setSettings(c.settings || {}); setLog(d.log || []); setResets(e.requests || []); setMsgs(f.messages || []);
    } catch (err: any) { notify(err.message); }
  }, [notify]);
  useEffect(() => { reload(); }, [reload]);

  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); notify(ok); reload(); } catch (e: any) { notify(e.message); } };
  const saveSettings = () => act(() => j('/api/community/admin/settings', { method: 'POST', body: JSON.stringify({ slow_mode_sec: +settings.slow_mode_sec, live_limit: +settings.live_limit, bot_enabled: !!settings.bot_enabled, bot_interval_min: +settings.bot_interval_min, bot_text: settings.bot_text }) }), 'Ayarlar kaydedildi');
  const filtered = idents.filter((i) => !q || i.name.toLowerCase().includes(q.toLowerCase()) || i.id.startsWith(q));

  return (
    <div className="cm" data-testid="chat-moderation">
      <section className="cm-box">
        <h3>AYARLAR</h3>
        <div className="cm-row">
          <label>Yavaş mod (sn) <input type="number" min={0} max={600} value={settings.slow_mode_sec ?? 0} onChange={(e) => setSettings({ ...settings, slow_mode_sec: e.target.value })} data-testid="cm-slow" /></label>
          <label>Canlı mesaj limiti <input type="number" min={10} max={300} value={settings.live_limit ?? 75} onChange={(e) => setSettings({ ...settings, live_limit: e.target.value })} data-testid="cm-limit" /></label>
          <label>Bot aralığı (dk) <input type="number" min={5} max={1440} value={settings.bot_interval_min ?? 45} onChange={(e) => setSettings({ ...settings, bot_interval_min: e.target.value })} /></label>
          <label className="cm-check"><input type="checkbox" checked={!!settings.bot_enabled} onChange={(e) => setSettings({ ...settings, bot_enabled: e.target.checked })} /> Bot (TikTok/X) açık</label>
        </div>
        <textarea value={settings.bot_text ?? ''} onChange={(e) => setSettings({ ...settings, bot_text: e.target.value })} maxLength={500} rows={2} data-testid="cm-bot-text" />
        <button className="cm-btn" onClick={saveSettings} data-testid="cm-save">KAYDET</button>
      </section>

      <section className="cm-box">
        <h3>KİMLİKLER <small>({idents.length})</small></h3>
        <input className="cm-search" placeholder="İsim / id ara…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="cm-table">
          {filtered.slice(0, 150).map((i) => (
            <div className="cm-tr" key={i.id} data-testid="cm-identity">
              <span className={`cc-badge ${i.kind === 'anon' ? 'guest' : i.role}`}>{i.role === 'admin' ? 'ADMIN' : i.role === 'moderator' ? 'MOD' : i.kind === 'anon' ? 'Misafir' : 'Üye'}</span>
              <span className="cm-name" title={i.id}>{i.name}{i.banned && <em> · BANLI</em>}</span>
              <span className="cm-meta">dev {i.device_id || '—'} · IP {i.ip || i.ip_hash || '—'}{i.last_seen ? ` · ${new Date(i.last_seen).toLocaleString('tr-TR')}` : ''}</span>
              <span className="cm-acts">
                {i.role !== 'admin' && <button onClick={() => act(() => j(`/api/community/admin/mod/${i.id}`, { method: 'POST', body: JSON.stringify({ on: i.role !== 'moderator' }) }), i.role === 'moderator' ? 'MOD alındı' : 'MOD verildi')} data-testid="cm-mod-toggle">{i.role === 'moderator' ? 'MOD ÇIKAR' : 'MOD YAP'}</button>}
                {i.role !== 'admin' && <button className="danger" onClick={() => setBanForm({ ...banForm, target: i.id })} data-testid="cm-ban-pick">BAN</button>}
              </span>
            </div>
          ))}
        </div>
        {banForm.target && (
          <div className="cm-banform" data-testid="cm-ban-form">
            <span>Hedef: <b>{idents.find((x) => x.id === banForm.target)?.name}</b></span>
            <select value={banForm.type} onChange={(e) => setBanForm({ ...banForm, type: e.target.value })}><option value="user">Kullanıcı</option><option value="ip">IP</option><option value="device">Cihaz</option></select>
            <input type="number" min={0} value={banForm.minutes} onChange={(e) => setBanForm({ ...banForm, minutes: +e.target.value })} title="Dakika (0 = kalıcı)" />
            <input value={banForm.reason} onChange={(e) => setBanForm({ ...banForm, reason: e.target.value })} maxLength={200} />
            <button className="cm-btn danger" onClick={() => act(() => j('/api/community/admin/ban', { method: 'POST', body: JSON.stringify(banForm) }), 'Ban uygulandı').then(() => setBanForm({ ...banForm, target: '' }))} data-testid="cm-ban-apply">UYGULA</button>
            <button onClick={() => setBanForm({ ...banForm, target: '' })}>İPTAL</button>
          </div>
        )}
      </section>

      <section className="cm-box">
        <h3>BAN LİSTESİ <small>({bans.filter((b) => b.active).length} aktif)</small></h3>
        <div className="cm-table">
          {bans.map((b) => (
            <div className={`cm-tr ${b.active ? '' : 'off'}`} key={b.id} data-testid="cm-ban">
              <span className="cm-type">{b.type.toUpperCase()}</span><span className="cm-name">{b.name}</span>
              <span className="cm-meta">{b.reason} · {b.until ? `${new Date(b.until).toLocaleString('tr-TR')} kadar` : 'kalıcı'}</span>
              <span className="cm-acts"><button onClick={() => act(() => j(`/api/community/admin/unban/${b.id}`, { method: 'POST' }), 'Ban kaldırıldı')} data-testid="cm-unban">UNBAN</button></span>
            </div>
          ))}
        </div>
      </section>

      <section className="cm-box">
        <h3>ŞİFRE SIFIRLAMA TALEPLERİ <small>(kodu Telegram ile ilet)</small></h3>
        <div className="cm-table">{resets.map((r, i) => (<div className="cm-tr" key={i}><span className="cm-name">{r.email}</span><span className="cm-code">{r.code}</span><span className="cm-meta">{new Date(r.created_at).toLocaleString('tr-TR')} {r.used ? '· kullanıldı' : ''}</span></div>))}{!resets.length && <div className="cm-empty">Talep yok</div>}</div>
      </section>

      <section className="cm-box">
        <h3>GÜVENLİK LOGU <small>(7 gün)</small></h3>
        <div className="cm-table cm-log">{log.map((l) => (<div className="cm-tr" key={l.id}><span className="cm-type">{l.kind}</span><span className="cm-meta">{JSON.stringify(l.detail)}</span><span className="cm-meta">{new Date(l.created_at).toLocaleString('tr-TR')}</span></div>))}</div>
      </section>

      <section className="cm-box">
        <h3>TAM KAYIT <small>(7 gün TTL · silinmez)</small></h3>
        <div className="cm-table cm-log">{msgs.map((m) => (<div className="cm-tr" key={m.id}><span className="cm-type">{m.role}</span><span className="cm-name">{m.name}</span><span className="cm-meta">{m.text}</span><span className="cm-meta">{new Date(m.created_at).toLocaleString('tr-TR')}</span></div>))}</div>
      </section>
    </div>
  );
}
