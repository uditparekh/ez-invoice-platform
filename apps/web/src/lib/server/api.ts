import "server-only";

import { createHmac } from "node:crypto";
import { isIP } from "node:net";

import { cookies, headers as incomingHeaders } from "next/headers";
import { NextResponse } from "next/server";

import type { AuthTokens } from "@/lib/types";

const ACCESS_COOKIE = "ez_access";
const REFRESH_COOKIE = "ez_refresh";
const API_BASE_URL =
  process.env.EZ_WEB_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

const secure = process.env.NODE_ENV === "production";

// Gateway attestation: the API applies per-address authentication limits only
// to addresses this tier signs. Only x-real-ip is attested: Vercel (or a
// correctly configured reverse proxy in front of `next start`) overwrites it
// from the connection. A bare, publicly exposed `next start` is NOT a trusted
// ingress: its operator must configure that overwrite before enabling signing.
// x-forwarded-for is deliberately not used: Next
// keeps a client-supplied value when one is present. Without the shared secret,
// or without x-real-ip, the API falls back to one budget per ingress hop.
const GATEWAY_SECRET = process.env.EZ_WEB_GATEWAY_SHARED_SECRET?.trim() ?? "";

async function attestClientAddress(headers: Headers) {
  if (GATEWAY_SECRET.length < 32) return;
  let ip = "";
  try {
    ip = (await incomingHeaders()).get("x-real-ip")?.trim() ?? "";
  } catch {
    return; // Not inside a request scope: nothing observed, nothing attested.
  }
  if (ip.length > 45 || ip.includes("%") || !isIP(ip)) return;
  const seconds = Math.floor(Date.now() / 1000).toString();
  const digest = createHmac("sha256", GATEWAY_SECRET)
    .update(`${seconds}|${ip}`)
    .digest("hex");
  headers.set("X-Siftentry-Client-Ip", ip);
  headers.set("X-Siftentry-Client-Signature", `${seconds}.${digest}`);
}

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure,
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}

export function setAuthCookies(response: NextResponse, tokens: AuthTokens) {
  response.cookies.set(
    ACCESS_COOKIE,
    tokens.access_token,
    cookieOptions(tokens.expires_in),
  );
  response.cookies.set(
    REFRESH_COOKIE,
    tokens.refresh_token,
    cookieOptions(60 * 60 * 24 * 14),
  );
}

export function clearAuthCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", cookieOptions(0));
  response.cookies.set(REFRESH_COOKIE, "", cookieOptions(0));
}

async function apiRequest(
  path: string,
  init: RequestInit = {},
  accessToken?: string,
) {
  const headers = new Headers(init.headers);
  headers.delete("X-Siftentry-Client-Ip");
  headers.delete("X-Siftentry-Client-Signature");
  await attestClientAddress(headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

async function refreshTokens(refreshToken: string) {
  return apiRequest("/api/v1/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

function retryableRefreshFailure(response?: Response) {
  return new Response(
    JSON.stringify({
      detail: "Session refresh is temporarily unavailable. Please retry.",
    }),
    {
      status: response?.status === 429 ? 429 : 503,
      headers: {
        "Content-Type": "application/json",
        "Retry-After": response?.headers.get("Retry-After") ?? "5",
      },
    },
  );
}

export async function authenticatedApiRequest(
  path: string,
  init: RequestInit = {},
) {
  const store = await cookies();
  const accessToken = store.get(ACCESS_COOKIE)?.value;
  const refreshToken = store.get(REFRESH_COOKIE)?.value;

  let upstream = await apiRequest(path, init, accessToken);
  let tokens: AuthTokens | null = null;
  let invalidSession = upstream.status === 401 && !refreshToken;

  if (upstream.status === 401 && refreshToken) {
    try {
      const refreshed = await refreshTokens(refreshToken);
      if (refreshed.ok) {
        tokens = (await refreshed.json()) as AuthTokens;
        upstream = await apiRequest(path, init, tokens.access_token);
      } else if (refreshed.status === 401) {
        invalidSession = true;
      } else {
        // A rate limit or service failure is not evidence of an invalid session.
        // Preserve cookies and return a retryable status, not the initial 401.
        upstream = retryableRefreshFailure(refreshed);
      }
    } catch {
      upstream = retryableRefreshFailure();
    }
  }

  const body =
    upstream.status === 204 || upstream.status === 304
      ? null
      : await upstream.arrayBuffer();
  const response = new NextResponse(body, { status: upstream.status });
  response.headers.set("Cache-Control", "no-store");
  const retryAfter = upstream.headers.get("Retry-After");
  if (retryAfter) response.headers.set("Retry-After", retryAfter);
  const contentType = upstream.headers.get("Content-Type");
  if (contentType && body !== null) {
    response.headers.set("Content-Type", contentType);
  }
  const contentDisposition = upstream.headers.get("Content-Disposition");
  if (contentDisposition && body !== null) {
    response.headers.set("Content-Disposition", contentDisposition);
  }

  if (tokens) setAuthCookies(response, tokens);
  if (invalidSession) clearAuthCookies(response);
  return response;
}

export async function publicApiRequest(path: string, init: RequestInit = {}) {
  return apiRequest(path, init);
}

export async function readRefreshToken() {
  return (await cookies()).get(REFRESH_COOKIE)?.value;
}
