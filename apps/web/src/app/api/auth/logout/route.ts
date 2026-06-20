import { NextResponse } from "next/server";

import {
  authenticatedApiRequest,
  clearAuthCookies,
  readRefreshToken,
} from "@/lib/server/api";

export async function POST() {
  const refreshToken = await readRefreshToken();
  if (refreshToken) {
    await authenticatedApiRequest("/api/v1/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }
  const response = NextResponse.json({ ok: true });
  clearAuthCookies(response);
  return response;
}
