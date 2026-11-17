import { enqueue, queueOwnerId, readQueue, removeQueued, updateQueueError } from "./offline-queue";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const AUTH_MODE = process.env.NEXT_PUBLIC_AUTH_MODE || "supabase";
const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
export const SUPABASE_CONFIGURED = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const DEMO_SESSION_KEY = "terravanta-session-v1";
const ACCOUNT_KEY = "terravanta-account-id-v1";
let currentAccessToken = "";
export type Session = { access_token: string; refresh_token?: string; expires_at?: number; user: { id: string; name: string; role: string; email?: string } };

export async function loginDemo(role: string): Promise<Session> {
  const response = await fetch(`${API_URL}/api/v1/auth/demo-login?role=${encodeURIComponent(role)}`, { method: "POST", cache: "no-store" });
  if (!response.ok) throw new Error("Could not reach the API. Start the local services and retry.");
  return response.json();
}

async function createTerravantaSession(auth: any, fallbackEmail = ""): Promise<Session> {
  if (!auth?.access_token || !auth?.user?.id) throw new Error("Supabase did not return a valid sign-in session.");
  const response = await fetch(`${API_URL}/api/v1/auth/onboard`, {
    method: "POST", cache: "no-store", headers: { Authorization: `Bearer ${auth.access_token}` },
  });
  const profile = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(profile.detail || "Could not create your Terravanta account.");
  return {
    access_token: auth.access_token,
    refresh_token: auth.refresh_token,
    expires_at: auth.expires_at || Math.floor(Date.now() / 1000) + Number(auth.expires_in || 3600),
    user: { id: profile.id, name: profile.name || fallbackEmail, email: profile.email || fallbackEmail, role: profile.role },
  };
}

export async function loginSupabase(email: string, password: string): Promise<Session> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) throw new Error("Supabase sign-in is not configured for this deployment.");
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST", cache: "no-store", headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const auth = await response.json().catch(() => ({}));
  if (!response.ok || !auth.access_token) throw new Error(auth.msg || auth.message || "Email or password was not accepted.");
  return createTerravantaSession(auth, email);
}

export async function loginAccessCode(name: string, email: string, code: string): Promise<Session> {
  const response = await fetch(`${API_URL}/api/v1/auth/access-code-login`, {
    method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, code }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.access_token) throw new Error(result.detail || "Name, email, or access code was not accepted.");
  return {
    access_token: result.access_token,
    expires_at: Math.floor(Date.now() / 1000) + Number(result.expires_in || 43200),
    user: result.user,
  };
}

export async function requestAccessCode(name: string, email: string): Promise<string> {
  const response = await fetch(`${API_URL}/api/v1/auth/request-access-code`, {
    method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || "Could not send a verification code.");
  return result.message || "If these details can be registered, a verification code has been emailed. It expires in 10 minutes.";
}

export async function signUpSupabase(name: string, email: string, password: string): Promise<Session | null> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) throw new Error("Farmer registration is not configured for this deployment.");
  const redirectTo = typeof window === "undefined" ? undefined : window.location.origin;
  const endpoint = `${SUPABASE_URL}/auth/v1/signup${redirectTo ? `?redirect_to=${encodeURIComponent(redirectTo)}` : ""}`;
  const response = await fetch(endpoint, {
    method: "POST", cache: "no-store", headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, data: { full_name: name } }),
  });
  const auth = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(auth.msg || auth.message || "Could not create the account.");
  if (!auth.access_token || !auth.user?.id) return null;
  return createTerravantaSession(auth, email);
}

export async function consumeSupabaseRedirect(): Promise<Session | null> {
  if (typeof window === "undefined" || AUTH_MODE !== "supabase" || !window.location.hash) return null;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const accessToken = params.get("access_token");
  if (!accessToken && !params.has("error_description")) return null;
  const cleanUrl = `${window.location.pathname}${window.location.search}`;
  window.history.replaceState({}, document.title, cleanUrl);
  const error = params.get("error_description");
  if (error) throw new Error(error.replaceAll("+", " "));
  const refreshToken = params.get("refresh_token");
  if (!refreshToken) throw new Error("The confirmation link did not include a session. Return to sign in and try again.");
  const expiresIn = Number(params.get("expires_in") || 3600);
  const session = await createTerravantaSession({
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_in: expiresIn,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    user: { id: "confirmed" },
  });
  await persistSession(session);
  return session;
}

export async function persistSession(session: Session): Promise<void> {
  if (typeof window === "undefined") return;
  currentAccessToken = session.access_token;
  if (AUTH_MODE === "demo" || AUTH_MODE === "access_code") {
    localStorage.setItem(ACCOUNT_KEY, session.user.id);
    (AUTH_MODE === "access_code" ? sessionStorage : localStorage).setItem(DEMO_SESSION_KEY, JSON.stringify(session));
    return;
  }
  if (!session.refresh_token) throw new Error("Supabase did not return a refresh token. Sign in again.");
  const response = await fetch("/api/session", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }), cache: "no-store",
  });
  if (!response.ok) throw new Error("Could not secure the session in this browser. Check the web service and sign in again.");
  localStorage.setItem(ACCOUNT_KEY, session.user.id);
}

export async function restoreSession(): Promise<Session | null> {
  if (typeof window === "undefined") return null;
  if (AUTH_MODE === "demo" || AUTH_MODE === "access_code") {
    try {
      const store = AUTH_MODE === "access_code" ? sessionStorage : localStorage;
      const session = JSON.parse(store.getItem(DEMO_SESSION_KEY) || "null") as Session | null;
      if (session?.expires_at && session.expires_at <= Math.floor(Date.now() / 1000)) {
        store.removeItem(DEMO_SESSION_KEY);
        return null;
      }
      if (session?.access_token) currentAccessToken = session.access_token;
      return session;
    } catch { return null; }
  }
  const response = await fetch("/api/session", { cache: "no-store" }).catch(() => null);
  if (!response?.ok) return null;
  const restored = await response.json().catch(() => null);
  if (!restored?.access_token) return null;
  currentAccessToken = restored.access_token;
  return {
    access_token: restored.access_token,
    expires_at: restored.expires_at,
    user: restored.user || { id: localStorage.getItem(ACCOUNT_KEY) || "", name: "", role: "loading" },
  };
}

export async function clearSession(): Promise<void> {
  if (typeof window === "undefined") return;
  currentAccessToken = "";
  localStorage.removeItem(ACCOUNT_KEY);
  if (AUTH_MODE === "demo" || AUTH_MODE === "access_code") {
    (AUTH_MODE === "access_code" ? sessionStorage : localStorage).removeItem(DEMO_SESSION_KEY);
    return;
  }
  await fetch("/api/session", { method: "DELETE", cache: "no-store" }).catch(() => undefined);
}

let refreshInFlight: Promise<string | null> | null = null;
async function refreshSession(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = refreshSessionOnce();
  try { return await refreshInFlight; } finally { refreshInFlight = null; }
}

async function refreshSessionOnce(): Promise<string | null> {
  if (typeof window === "undefined" || AUTH_MODE !== "supabase") return null;
  const response = await fetch("/api/session", { cache: "no-store" }).catch(() => null);
  if (!response?.ok) return null;
  const refreshed = await response.json().catch(() => ({}));
  if (!refreshed.access_token) return null;
  currentAccessToken = refreshed.access_token;
  return currentAccessToken;
}

export async function logoutSupabase(token: string): Promise<void> {
  if (SUPABASE_URL && SUPABASE_ANON_KEY && token) {
    await fetch(`${SUPABASE_URL}/auth/v1/logout`, { method: "POST", headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}` } }).catch(() => undefined);
  }
  await clearSession();
}

export async function api<T = any>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const request = (accessToken: string) => fetch(`${API_URL}${path}`, { ...init, cache: "no-store", signal: init.signal || AbortSignal.timeout(20000), headers: { Authorization: `Bearer ${accessToken}`, ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init.headers } });
  let response: Response;
  try {
    response = await request(currentAccessToken || token);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Network request failed";
    throw new Error(`Could not reach the Terravanta API for ${path}. ${detail}`);
  }
  if (response.status === 401 && AUTH_MODE === "supabase") {
    const refreshedToken = await refreshSession();
    if (refreshedToken) {
      try { response = await request(refreshedToken); }
      catch (error) {
        const detail = error instanceof Error ? error.message : "Network request failed";
        throw new Error(`Could not reach the Terravanta API for ${path}. ${detail}`);
      }
    }
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(`${error.detail || "Request failed"} (HTTP ${response.status} · ${path})`);
  }
  return response.json();
}

export async function writeApi<T = any>(path: string, token: string, body: Record<string, unknown>): Promise<T | { queuedOffline: true }> {
  try {
    return await api<T>(path, token, { method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": crypto.randomUUID() } });
  } catch (error) {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      await enqueue(path, "POST", JSON.stringify(body), queueOwnerId());
      window.dispatchEvent(new Event("terravanta-queue-change"));
      return { queuedOffline: true };
    }
    throw error;
  }
}

export async function flushOfflineQueue(token: string): Promise<{ synced: number; pending: number }> {
  if (typeof navigator === "undefined" || !navigator.onLine) return { synced: 0, pending: 0 };
  const queued = await readQueue(queueOwnerId());
  let synced = 0;
  for (const item of queued) {
    try {
      await api(item.path, token, { method: item.method, body: item.body, headers: { "Idempotency-Key": item.id } });
      await removeQueued(item.id);
      synced += 1;
    } catch (error) {
      await updateQueueError(item.id, error instanceof Error ? error.message : "Sync failed");
      break;
    }
  }
  window.dispatchEvent(new Event("terravanta-queue-change"));
  return { synced, pending: (await readQueue(queueOwnerId())).length };
}

export async function uploadDocument(path: string, token: string, file: File, allowExternalProcessing: boolean): Promise<any> {
  const form = new FormData();
  form.append("file", file);
  form.append("allow_external_processing", String(allowExternalProcessing));
  return api(path, token, { method: "POST", body: form });
}
