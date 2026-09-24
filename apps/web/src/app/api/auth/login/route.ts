import { NextResponse } from "next/server";

import { publicApiRequest, setAuthCookies } from "@/lib/server/api";
import type { AuthTokens } from "@/lib/types";

export async function POST(request: Request) {
  const upstream = await publicApiRequest("/api/v1/auth/login", {
    method: "POST",
    body: await request.text(),
    headers: { "Content-Type": "application/json" },
  });
  const payload = await upstream.json();
  const response = NextResponse.json(payload, { status: upstream.status });
  response.headers.set("Cache-Control", "no-store");
  const retryAfter = upstream.headers.get("Retry-After");
  if (retryAfter) response.headers.set("Retry-After", retryAfter);

  if (upstream.ok) setAuthCookies(response, payload as AuthTokens);
  return response;
}
