'use client';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { getClient, postClient, deleteClient } from '@/lib/api';
import { AuthProvider, useAuth } from '@/components/AuthProvider';
import ChatModeration from '@/components/admin/ChatModeration';

type Stats = {
  users: { total: number; banned: number };
  predictions: { total: number; pending: number; settled: number };
  chat: { messages_24h: number };
};

type PendingPrediction = {
  id: string; user_id: string; user_name: string; match_id: string;
  team1: string; team2: string; kickoff: string;
  score1: number; score2: number; submitted_at: string;
};

type AdminUser = {
  id: string; email: string; name: string; role: string;
  provider: string; banned: boolean; test: boolean; created_at: string;
};

type AdminMessage = {
  id: string; user_id: string; name: string; role: string; text: string; ts: string;
};

type SponsorClick = {
  sponsor_id: string; name: string; count: number; last_click_at: string | null;
};

export default function AdminPage() {
  return (
    <AuthProvider>
      <AdminInner />
    </AuthProvider>
  );
}

function AdminInner() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<'overview' | 'predictions' | 'users' | 'chat' | 'moderation' | 'sponsors'>('overview');
  const [stats, setStats] = useState<Stats | null>(null);
  const [predictions, setPredictions] = useState<PendingPrediction[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [messages, setMessages] = useState<AdminMessage[]>([]);
  const [sponsorClicks, setSponsorClicks] = useState<{ items: SponsorClick[]; total: number }>({ items: [], total: 0 });
  const [msg, setMsg] = useState('');

  const reloadStats = useCallback(async () => {
    const d = await getClient<Stats>('/api/admin/stats');
    if (d) setStats(d);
  }, []);

  const reloadPredictions = useCallback(async () => {
    const d = await getClient<{ items: PendingPrediction[] }>('/api/admin/predictions/pending');
    if (d?.items) setPredictions(d.items);
  }, []);

  const reloadUsers = useCallback(async () => {
    const d = await getClient<{ items: AdminUser[] }>('/api/admin/users?limit=200');
    if (d?.items) setUsers(d.items);
  }, []);

  const reloadMessages = useCallback(async () => {
    const d = await getClient<{ items: AdminMessage[] }>('/api/admin/chat/messages?limit=200');
    if (d?.items) setMessages(d.items);
  }, []);

  const reloadSponsorClicks = useCallback(async () => {
    const d = await getClient<{ items: SponsorClick[]; total: number }>('/api/admin/sponsors/clicks');
    if (d) setSponsorClicks({ items: d.items || [], total: d.total || 0 });
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== 'admin') return; // AdminGate gösterilir (yönlendirme yok)
    reloadStats(); reloadPredictions(); reloadUsers(); reloadMessages(); reloadSponsorClicks();
  }, [user, loading, router, reloadStats, reloadPredictions, reloadUsers, reloadMessages, reloadSponsorClicks]);

  const settle = async (id: string) => {
    const home = prompt('Gerçek ev sahibi skoru:');
    const away = prompt('Gerçek deplasman skoru:');
    if (home == null || away == null) return;
    const r = await postClient(`/api/admin/predictions/${id}/settle`, { final_home: parseInt(home, 10), final_away: parseInt(away, 10) });
    if (r?.ok) {
      setMsg(`Settled: +${r.points}p (${r.final_score?.join('-')})`);
      reloadPredictions(); reloadStats();
    } else {
      setMsg('Hata: ' + (r?.detail || 'unknown'));
    }
    setTimeout(() => setMsg(''), 3000);
  };

  const cancelPred = async (id: string) => {
    if (!confirm('Tahmin iptal edilecek. Emin misin?')) return;
    await postClient(`/api/admin/predictions/${id}/cancel`, {});
    setMsg('Tahmin iptal edildi');
    reloadPredictions(); reloadStats();
    setTimeout(() => setMsg(''), 2500);
  };

  const banUser = async (id: string) => {
    await postClient(`/api/admin/users/${id}/ban`, {});
    reloadUsers();
  };
  const unbanUser = async (id: string) => {
    await postClient(`/api/admin/users/${id}/unban`, {});
    reloadUsers();
  };

  const deleteMsg = async (id: string) => {
    await deleteClient(`/api/chat/message/${id}`);
    reloadMessages();
  };
  const clearChat = async () => {
    if (!confirm('TÜM SOHBET GEÇMİŞİ SİLİNECEK. Emin misin?')) return;
    await deleteClient('/api/admin/chat/clear');
    reloadMessages(); reloadStats();
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>Yükleniyor…</div>;
  }
  if (!user || user.role !== 'admin') {
    // Admin olmayan → uyarı + 3 sn içinde ana sayfaya yönlendirme. Admin girişi: header GİRİŞ → kullanıcı adı "adminastor" + parola.
    return <AdminRedirect />;
  }

  return (
    <div className="app-container" data-testid="admin-page">
      <div className="scanlines" />
      <header style={{ borderBottom: '1px solid rgba(255,0,170,0.2)', padding: '14px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link href="/" style={{ fontFamily: 'Orbitron', textDecoration: 'none', color: 'var(--cyan)', letterSpacing: 3, fontSize: 16 }}>
          ← banbansports
        </Link>
        <div style={{ fontFamily: 'Orbitron', color: 'var(--pink)', letterSpacing: 4, textShadow: '0 0 8px var(--pink)' }}>ADMIN PANEL</div>
        <div style={{ fontFamily: 'VT323', color: 'var(--text-dim)' }}>{user.name || user.email}</div>
      </header>

      {/* Tab nav */}
      <nav style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '0 20px' }} data-testid="admin-tabs">
        {(['overview', 'predictions', 'users', 'chat', 'moderation', 'sponsors'] as const).map((t) => (
          <button
            key={t} onClick={() => setTab(t)}
            data-testid={`admin-tab-${t}`}
            style={{
              padding: '14px 24px', background: 'none', border: 'none',
              fontFamily: 'Orbitron', fontSize: 12, letterSpacing: 3, cursor: 'pointer',
              color: tab === t ? 'var(--cyan)' : 'var(--text-dim)',
              borderBottom: tab === t ? '2px solid var(--cyan)' : '2px solid transparent',
              textShadow: tab === t ? '0 0 8px var(--cyan)' : 'none',
            }}
          >
            {t === 'overview' ? 'GENEL' : t === 'predictions' ? 'TAHMİNLER' : t === 'users' ? 'KULLANICILAR' : t === 'chat' ? 'SOHBET' : t === 'moderation' ? 'SOHBET MODERASYON' : 'SPONSORLAR'}
          </button>
        ))}
      </nav>

      {msg && (
        <div style={{ padding: '10px 20px', background: 'rgba(0,240,255,0.1)', color: 'var(--cyan)', fontFamily: 'VT323', textAlign: 'center', letterSpacing: 2 }} data-testid="admin-msg">{msg}</div>
      )}

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: 24 }}>
        {tab === 'overview' && stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }} data-testid="admin-overview">
            <Card label="TOPLAM KULLANICI" value={stats.users.total} sub={`${stats.users.banned} banlı`} />
            <Card label="TAHMİN (TOPLAM)" value={stats.predictions.total} sub={`${stats.predictions.pending} bekleyen`} />
            <Card label="TAHMİN (PUANLANDI)" value={stats.predictions.settled} />
            <Card label="SOHBET MESAJ (24h)" value={stats.chat.messages_24h} />
          </div>
        )}

        {tab === 'predictions' && (
          <div data-testid="admin-predictions" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ color: 'var(--text-dim)', marginBottom: 8 }}>Bekleyen tahminler ({predictions.length}) — settlement loop 5dk&apos;da bir otomatik puanlar, manuel zorlamak için aşağıdan settle/iptal.</div>
            {predictions.length === 0 && <div style={{ color: 'var(--text-dim)', textAlign: 'center', padding: 30 }}>Bekleyen tahmin yok</div>}
            {predictions.map((p) => (
              <div key={p.id} data-testid={`admin-pred-${p.id}`} style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(255,0,170,0.15)', borderRadius: 6, padding: 12, display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12, alignItems: 'center' }}>
                <div>
                  <div style={{ fontFamily: 'VT323', fontSize: 16 }}>{p.team1} <span style={{ color: 'var(--cyan)' }}>{p.score1}–{p.score2}</span> {p.team2}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: 1 }}>{p.user_name} · {new Date(p.submitted_at).toLocaleString('tr-TR')}</div>
                </div>
                <button className="btn-neon-cyan" onClick={() => settle(p.id)} style={{ padding: '6px 12px' }} data-testid={`settle-${p.id}`}>SETTLE</button>
                <button onClick={() => cancelPred(p.id)} style={{ padding: '6px 12px', background: 'transparent', color: 'var(--text-dim)', border: '1px solid var(--text-dim)', cursor: 'pointer', fontFamily: 'Orbitron', letterSpacing: 2, fontSize: 11 }} data-testid={`cancel-${p.id}`}>İPTAL</button>
              </div>
            ))}
          </div>
        )}

        {tab === 'users' && (
          <div data-testid="admin-users" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ color: 'var(--text-dim)', marginBottom: 8 }}>Kullanıcılar ({users.length})</div>
            {users.map((u) => (
              <div key={u.id} style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, padding: 10, display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: 10, alignItems: 'center' }} data-testid={`admin-user-${u.id}`}>
                <div>
                  <div style={{ fontFamily: 'VT323', fontSize: 15 }}>
                    {u.name || u.email}
                    {u.role === 'admin' && <span style={{ marginLeft: 8, padding: '1px 5px', border: '1px solid var(--orange, #ffa600)', color: 'var(--orange, #ffa600)', fontSize: 9, letterSpacing: 1 }}>ADMIN</span>}
                    {u.test && <span style={{ marginLeft: 6, padding: '1px 5px', border: '1px solid #888', color: '#888', fontSize: 9 }}>TEST</span>}
                    {u.banned && <span style={{ marginLeft: 6, padding: '1px 5px', border: '1px solid #ff4040', color: '#ff4040', fontSize: 9 }}>BAN</span>}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{u.email} · {u.provider}</div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', textAlign: 'right' }}>{new Date(u.created_at).toLocaleDateString('tr-TR')}</div>
                {u.banned ? (
                  <button onClick={() => unbanUser(u.id)} style={{ padding: '4px 10px', background: 'rgba(0,255,127,0.1)', border: '1px solid var(--green, #00ff7f)', color: 'var(--green, #00ff7f)', cursor: 'pointer', fontFamily: 'Orbitron', fontSize: 10, letterSpacing: 1 }} data-testid={`unban-${u.id}`}>UNBAN</button>
                ) : (
                  <button onClick={() => banUser(u.id)} style={{ padding: '4px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid #ff4040', color: '#ff4040', cursor: 'pointer', fontFamily: 'Orbitron', fontSize: 10, letterSpacing: 1 }} data-testid={`ban-${u.id}`}>BAN</button>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'chat' && (
          <div data-testid="admin-chat">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ color: 'var(--text-dim)' }}>Son {messages.length} mesaj</div>
              <button onClick={clearChat} style={{ padding: '6px 14px', background: 'rgba(255,0,0,0.1)', border: '1px solid #ff4040', color: '#ff4040', cursor: 'pointer', fontFamily: 'Orbitron', fontSize: 11, letterSpacing: 2 }} data-testid="admin-clear-chat">TÜMÜNÜ SİL</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 600, overflowY: 'auto' }}>
              {messages.map((m) => (
                <div key={m.id} style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 5, padding: '6px 10px', display: 'grid', gridTemplateColumns: '1fr auto', gap: 10 }} data-testid={`admin-msg-${m.id}`}>
                  <div style={{ minWidth: 0 }}>
                    <span style={{ color: 'var(--cyan)', fontFamily: 'VT323', marginRight: 6 }}>{m.name}</span>
                    <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{new Date(m.ts).toLocaleString('tr-TR')}</span>
                    <div style={{ color: '#fff', fontFamily: 'VT323', fontSize: 14, wordBreak: 'break-word' }}>{m.text}</div>
                  </div>
                  <button onClick={() => deleteMsg(m.id)} style={{ padding: '2px 8px', background: 'transparent', border: '1px solid var(--text-dim)', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 10 }} data-testid={`del-msg-${m.id}`}>SİL</button>
                </div>
              ))}
            </div>
          </div>
        )}
        {tab === 'moderation' && <ChatModeration notify={setMsg} />}

        {tab === 'sponsors' && (
          <div data-testid="admin-sponsors">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ color: 'var(--text-dim)' }}>Sponsor tıklamaları — toplam <span style={{ color: 'var(--cyan)' }}>{sponsorClicks.total}</span> tıklama</div>
              <button onClick={reloadSponsorClicks} className="btn-neon-cyan" style={{ padding: '5px 14px', fontSize: 11 }} data-testid="sponsors-refresh">YENİLE</button>
            </div>
            {sponsorClicks.items.length === 0 && (
              <div style={{ color: 'var(--text-dim)', textAlign: 'center', padding: 30 }}>Henüz sponsor tıklaması yok</div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {sponsorClicks.items.map((s, idx) => {
                const max = sponsorClicks.items[0]?.count || 1;
                const pct = Math.max(4, Math.round((s.count / max) * 100));
                return (
                  <div key={s.sponsor_id} style={{ background: 'rgba(15,8,24,0.5)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, padding: '10px 14px', display: 'grid', gridTemplateColumns: '28px 1fr auto', gap: 12, alignItems: 'center' }} data-testid={`sponsor-click-${s.sponsor_id}`}>
                    <div style={{ fontFamily: 'Orbitron', fontSize: 13, color: idx < 3 ? 'var(--pink)' : 'var(--text-dim)' }}>#{idx + 1}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontFamily: 'VT323', fontSize: 17, color: '#fff' }}>{s.name}</div>
                      <div style={{ height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.06)', marginTop: 5, overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 3, background: 'linear-gradient(90deg, var(--cyan), var(--pink))' }} />
                      </div>
                      {s.last_click_at && (
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 3 }}>Son tıklama: {new Date(s.last_click_at).toLocaleString('tr-TR')}</div>
                      )}
                    </div>
                    <div style={{ fontFamily: 'Orbitron', fontSize: 22, color: 'var(--cyan)', textShadow: '0 0 8px var(--cyan)' }} data-testid={`sponsor-count-${s.sponsor_id}`}>{s.count}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function AdminRedirect() {
  const router = useRouter();
  const [count, setCount] = useState(3);
  useEffect(() => {
    if (count <= 0) { router.replace('/'); return; }
    const t = setTimeout(() => setCount((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [count, router]);
  return (
    <div className="ag ag-redirect" data-testid="admin-redirect">
      <div className="ag-card">
        <div className="ag-brand"><span>banbansports</span><small>ADMIN</small></div>
        <div className="ag-warn" data-testid="admin-gate-warn">
          <div className="ag-icon">👑</div>
          <div className="ag-title">Bu alan site admini / geliştiricisine yöneliktir</div>
          <div className="ag-sub">Yetkisiz erişim kayıt altına alınır. Ana sayfaya yönlendiriliyorsunuz…</div>
          <div className="ag-count" data-testid="admin-redirect-count">{count}</div>
        </div>
      </div>
    </div>
  );
}

function Card({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div style={{ background: 'linear-gradient(135deg, rgba(0,240,255,0.06), rgba(255,0,170,0.04))', border: '1px solid rgba(0,240,255,0.2)', borderRadius: 8, padding: 18 }} data-testid={`admin-card-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <div style={{ fontFamily: 'Orbitron', fontSize: 11, letterSpacing: 3, color: 'var(--text-dim)', marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: 'Orbitron', fontSize: 32, color: 'var(--cyan)', textShadow: '0 0 10px var(--cyan)' }}>{value}</div>
      {sub && <div style={{ fontFamily: 'VT323', fontSize: 13, color: 'var(--text-dim)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
