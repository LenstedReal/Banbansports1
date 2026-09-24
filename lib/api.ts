/**
 * API client — supports both SSR (server-side) and CSR (browser).
 * On the server we hit the backend URL directly. On the client we use
 * the rewrite proxy (`/api/...`) so cookies + same-origin auth works.
 */

const BACKEND =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.REACT_APP_BACKEND_URL ||
  '';

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) path = '/' + path;
  if (typeof window === 'undefined') {
    // SSR — call backend directly; Vercel'de env yoksa VERCEL_URL'e düş
    const base =
      BACKEND ||
      (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : '');
    return base ? `${base}${path}` : path;
  }
  return path; // browser uses Next.js rewrite proxy
}

export function wsUrl(path: string): string {
  if (typeof window === 'undefined') return '';
  if (!path.startsWith('/')) path = '/' + path;
  if (BACKEND) {
    return BACKEND.replace(/^http/, 'ws') + path;
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}${path}`;
}

async function safeJson<T>(p: Promise<Response>): Promise<T | null> {
  try {
    const r = await p;
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export type Match = {
  type?: string;
  team1: string;
  team2: string;
  score1: number | null;
  score2: number | null;
  league?: string;
  status?: string;
  isLive?: boolean;
  pen1?: number | null;
  pen2?: number | null;
  timestamp?: string;
};

export async function getTopScores(n = 5): Promise<{ matches: Match[] }> {
  const data = await safeJson<{ matches?: Match[] }>(
    fetch(apiUrl(`/api/scores/top?n=${n}`), {
      next: { revalidate: 30 },
      headers: { 'Accept': 'application/json' },
    })
  );
  return { matches: data?.matches || [] };
}

export async function getTodayMatches(): Promise<{ Stages: any[] }> {
  const data = await safeJson<{ Stages?: any[] }>(
    fetch(apiUrl('/api/livescore/today'), {
      next: { revalidate: 60 },
      headers: { 'Accept': 'application/json' },
    })
  );
  return { Stages: data?.Stages || [] };
}

export async function getChannels(): Promise<Record<string, { name: string; status: string; premium?: boolean }>> {
  const data = await safeJson<Record<string, any>>(
    fetch(apiUrl('/api/channels'), { next: { revalidate: 300 } })
  );
  return data || {};
}

export async function postClient<T = any>(path: string, body: any): Promise<T | null> {
  return safeJson<T>(
    fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    })
  );
}

export async function deleteClient<T = any>(path: string): Promise<T | null> {
  return safeJson<T>(
    fetch(apiUrl(path), {
      method: 'DELETE',
      credentials: 'include',
    })
  );
}

export async function getClient<T = any>(path: string): Promise<T | null> {
  return safeJson<T>(
    fetch(apiUrl(path), {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
  );
}

// SSR-only: server'da backend'e doğrudan çağrı yap
export async function getServer<T = any>(path: string): Promise<T | null> {
  return safeJson<T>(
    fetch(apiUrl(path), {
      next: { revalidate: 60 },
      headers: { 'Accept': 'application/json' },
    })
  );
}

export { BACKEND };
