import { NextResponse } from "next/server";

import { publicApiRequest, setAuthCookies } from "@/lib/server/api";
import type { AuthTokens } from "@/lib/types";

export async function POST() {
  const upstream = await publicApiRequest("/api/v1/auth/demo", {
    method: "POST",
  });
  const payload = await upstream.json();
  const response = NextResponse.json(payload, { status: upstream.status });
  const diagnostic = upstream.headers.get("X-SiftEntry-Demo-Error");
  if (diagnostic) {
    response.headers.set("X-SiftEntry-Demo-Error", diagnostic);
  }
  const sqlstate = upstream.headers.get("X-SiftEntry-Demo-SQLState");
  if (sqlstate) {
    response.headers.set("X-SiftEntry-Demo-SQLState", sqlstate);
  }

  if (upstream.ok) setAuthCookies(response, payload as AuthTokens);
  return response;
}
