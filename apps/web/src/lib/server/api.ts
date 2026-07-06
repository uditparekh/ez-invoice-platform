import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import type { AuthTokens } from "@/lib/types";

const ACCESS_COOKIE = "ez_access";
const REFRESH_COOKIE = "ez_refresh";
const API_BASE_URL =
  process.env.EZ_WEB_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

const secure = process.env.NODE_ENV === "production";

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
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

async function refreshTokens(refreshToken: string) {
  const response = await apiRequest("/api/v1/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return null;
  return (await response.json()) as AuthTokens;
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

  if (upstream.status === 401 && refreshToken) {
    tokens = await refreshTokens(refreshToken);
    if (tokens) upstream = await apiRequest(path, init, tokens.access_token);
  }

  const body =
    upstream.status === 204 || upstream.status === 304
      ? null
      : await upstream.arrayBuffer();
  const response = new NextResponse(body, { status: upstream.status });
  const contentType = upstream.headers.get("Content-Type");
  if (contentType && body !== null) {
    response.headers.set("Content-Type", contentType);
  }
  const contentDisposition = upstream.headers.get("Content-Disposition");
  if (contentDisposition && body !== null) {
    response.headers.set("Content-Disposition", contentDisposition);
  }

  if (tokens) setAuthCookies(response, tokens);
  if (upstream.status === 401 && !tokens) clearAuthCookies(response);
  return response;
}

export async function publicApiRequest(path: string, init: RequestInit = {}) {
  return apiRequest(path, init);
}

export async function readRefreshToken() {
  return (await cookies()).get(REFRESH_COOKIE)?.value;
}
