'use client';
/**
 * Stream Token V2.1 istemci katmanı — Access JWT bellekte, refresh HttpOnly cookie'de (tarayıcı taşır).
 * Tüm /api/stream-auth çağrıları buradan geçer; 401'de bir kez sessiz refresh dener.
 */

export type Track = 'dub' | 'sub';
export type HlsMode = 'js' | 'native';
export type HlsParams = Record<string, string>;

type Access = { token: string; exp: number; sid: string; did: string };

const API = '/api/stream-auth';
const DID_KEY = 'bb_did';
const REFRESH_BEFORE_S = 8 * 60; // access bitimine 8 dk kala (22. dk) yenile

let access: Access | null = null;
let refreshing: Promise<boolean> | null = null;

export class StreamAuthError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

const nowS = () => Math.floor(Date.now() / 1000);

export function getDeviceId(): string {
  try { return localStorage.getItem(DID_KEY) || ''; } catch { return ''; }
}

function apply(d: any): void {
  access = { token: d.access_token, exp: nowS() + Number(d.expires_in || 0), sid: d.sid, did: d.did };
  try { if (d.did) localStorage.setItem(DID_KEY, d.did); } catch { /* noop */ }
}

export const hasAccess = (): boolean => !!access && access.exp > nowS();
export const accessExp = (): number => access?.exp || 0;
export const shouldRefresh = (): boolean => !!access && access.exp - nowS() < REFRESH_BEFORE_S;

export async function login(username: string, password: string, turnstile_token: string): Promise<{ ok: boolean; status: number; detail: string }> {
  const r = await fetch(`${API}/login`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, turnstile_token, device_id: getDeviceId() }),
  });
  const d = await r.json().catch(() => null);
  if (!r.ok || !d?.ok) return { ok: false, status: r.status, detail: d?.detail || '' };
  apply(d);
  return { ok: true, status: r.status, detail: '' };
}

/** Cookie ile sessiz yenileme — aynı anda tek istek (rotation yarışı olmaz). */
export function refresh(): Promise<boolean> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    try {
      const r = await fetch(`${API}/refresh`, { method: 'POST', credentials: 'include', cache: 'no-store' });
      const d = await r.json().catch(() => null);
      if (!r.ok || !d?.ok) { if (r.status === 401) access = null; return false; }
      apply(d);
      return true;
    } catch { return false; } finally { refreshing = null; }
  })();
  return refreshing;
}

export async function logout(): Promise<void> {
  try { await fetch(`${API}/logout`, { method: 'POST', credentials: 'include', headers: authHeaders() }); } catch { /* noop */ }
  access = null;
}

function authHeaders(): Record<string, string> {
  return access ? { Authorization: `Bearer ${access.token}` } : {};
}

async function post<T = any>(path: string, body: unknown, retry = true): Promise<T> {
  if (!hasAccess() && !(await refresh())) throw new StreamAuthError(401, 'oturum yok');
  const r = await fetch(`${API}${path}`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  });
  if (r.status === 401 && retry && (await refresh())) return post<T>(path, body, false);
  const d = await r.json().catch(() => null);
  if (!r.ok) throw new StreamAuthError(r.status, d?.detail || `HTTP ${r.status}`);
  return d as T;
}

export type SignedUrl = { url: string; base_url: string; params: HlsParams; mode: HlsMode; expires_in: number; expires_at: number };
export const getStreamUrl = (stream_id: string, source: Track, mode: HlsMode) =>
  post<SignedUrl>('/url', { stream_id, source, mode });

export type Lease = { lease_id: string; heartbeat_interval: number; ttl: number };
export const startLease = (stream_id: string, source: Track) => post<Lease>('/start', { stream_id, source });
export const heartbeat = (lease_id: string) => post<{ ok: boolean }>('/heartbeat', { lease_id });

/** Sekme kapanışında Bearer taşınamaz → lease_id ile beacon. Normalde Bearer ile POST. */
export function stopLease(lease_id: string, beacon = false): void {
  if (!lease_id) return;
  const body = JSON.stringify({ lease_id });
  if (beacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    try { navigator.sendBeacon(`${API}/stop`, new Blob([body], { type: 'application/json' })); return; } catch { /* fallthrough */ }
  }
  fetch(`${API}/stop`, { method: 'POST', credentials: 'include', keepalive: true, headers: { 'Content-Type': 'application/json', ...authHeaders() }, body }).catch(() => {});
}

export type CastToken = { cast_session_id: string; media_url: string; content_type: string; expires_in: number };
export const getCastToken = (stream_id: string, source: Track) => post<CastToken>('/cast-token', { stream_id, source });

/** Bir URL'e imzalı param setini basar (eski auth param'larını temizler). */
export function applyParams(url: string, params?: HlsParams): string {
  if (!params) return url;
  const u = new URL(url, typeof window !== 'undefined' ? window.location.href : 'https://localhost/');
  for (const k of ['token', 'exp', 'sid', 'did', 'm', 'st', 'cs', 'sig']) u.searchParams.delete(k);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return u.toString();
}
