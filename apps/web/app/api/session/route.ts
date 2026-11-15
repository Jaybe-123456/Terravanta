import { NextRequest, NextResponse } from "next/server";

const refreshCookie = "terravanta_refresh";
const cookieLifetime = 60 * 60 * 24 * 30;

function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return !origin || origin === new URL(request.url).origin;
}

function cookieOptions(request: NextRequest) {
  return {
    httpOnly: true,
    secure: new URL(request.url).protocol === "https:",
    sameSite: "lax" as const,
    path: "/api/session",
    maxAge: cookieLifetime,
  };
}

function configuredAuth() {
  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  return url && anonKey ? { url, anonKey } : null;
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Request origin is not allowed" }, { status: 403 });
  if (!configuredAuth()) return NextResponse.json({ detail: "Supabase Auth is not configured" }, { status: 503 });
  const body = await request.json().catch(() => null);
  if (typeof body?.refresh_token !== "string" || body.refresh_token.length < 20 || body.refresh_token.length > 4096) {
    return NextResponse.json({ detail: "A valid session refresh token is required" }, { status: 422 });
  }
  const response = NextResponse.json({ stored: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(refreshCookie, body.refresh_token, cookieOptions(request));
  return response;
}

export async function GET(request: NextRequest) {
  const auth = configuredAuth();
  const refreshToken = request.cookies.get(refreshCookie)?.value;
  if (!auth) return NextResponse.json({ detail: "Supabase Auth is not configured" }, { status: 503 });
  if (!refreshToken) return NextResponse.json({ detail: "No active session" }, { status: 401, headers: { "Cache-Control": "no-store" } });

  let authResponse: Response;
  try {
    authResponse = await fetch(`${auth.url}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: { apikey: auth.anonKey, "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    return NextResponse.json({ detail: "Supabase Auth is temporarily unavailable" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }

  const refreshed = await authResponse.json().catch(() => ({}));
  if (!authResponse.ok || !refreshed.access_token) {
    const response = NextResponse.json({ detail: "Session expired" }, { status: 401, headers: { "Cache-Control": "no-store" } });
    response.cookies.set(refreshCookie, "", { ...cookieOptions(request), maxAge: 0 });
    return response;
  }

  const response = NextResponse.json({
    access_token: refreshed.access_token,
    expires_at: refreshed.expires_at,
    user: {
      id: refreshed.user?.id,
      email: refreshed.user?.email,
      name: refreshed.user?.user_metadata?.full_name || refreshed.user?.email || "",
    },
  }, { headers: { "Cache-Control": "no-store" } });
  if (refreshed.refresh_token) response.cookies.set(refreshCookie, refreshed.refresh_token, cookieOptions(request));
  return response;
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Request origin is not allowed" }, { status: 403 });
  const response = NextResponse.json({ cleared: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(refreshCookie, "", { ...cookieOptions(request), maxAge: 0 });
  return response;
}
