'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getClient, postClient } from '@/lib/api';

export type User = { id: string; email: string; name: string; role: string; picture?: string } | null;

type AuthCtx = {
  user: User;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  register: (email: string, password: string, name: string) => Promise<{ ok: boolean; error?: string }>;
  googleLogin: (idToken: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const d = await getClient<{ user?: User }>('/api/auth/me');
    setUser(d?.user ?? null);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email: string, password: string) => {
    const id = email.trim();
    // "adminastor" gibi @ içermeyen kullanıcı adı → admin kapısı (JWT ile aynı oturum cookie'leri)
    if (id && !id.includes('@')) {
      try {
        const r = await fetch('/api/admin-gate/login', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: id, password }) });
        const d = await r.json().catch(() => null);
        if (r.ok && d?.ok && d.user) { setUser(d.user); return { ok: true }; }
        return { ok: false, error: d?.detail || 'Geçersiz kullanıcı adı veya parola' };
      } catch { return { ok: false, error: 'Sunucuya ulaşılamadı' }; }
    }
    const res = await postClient<{ ok: boolean; user?: User; error?: string }>('/api/auth/login', { email: id, password });
    if (res?.ok && res.user) { setUser(res.user); return { ok: true }; }
    return { ok: false, error: res?.error || 'Giriş başarısız' };
  };

  const register = async (email: string, password: string, name: string) => {
    const res = await postClient<{ ok: boolean; user?: User; error?: string }>('/api/auth/register', { email, password, name });
    if (res?.ok && res.user) { setUser(res.user); return { ok: true }; }
    return { ok: false, error: res?.error || 'Kayıt başarısız' };
  };

  const googleLogin = async (idToken: string) => {
    const res = await postClient<{ ok: boolean; user?: User; error?: string }>('/api/auth/google', { id_token: idToken });
    if (res?.ok && res.user) { setUser(res.user); return { ok: true }; }
    return { ok: false, error: res?.error || 'Google girişi başarısız' };
  };

  const logout = async () => {
    await postClient('/api/auth/logout', {});
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, loading, refresh, login, register, googleLogin, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used within <AuthProvider>');
  return v;
}
