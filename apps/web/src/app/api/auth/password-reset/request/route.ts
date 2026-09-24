import { NextResponse } from "next/server";

import { publicApiRequest } from "@/lib/server/api";

export async function POST(request: Request) {
  const upstream = await publicApiRequest(
    "/api/v1/auth/password-reset/request",
    {
      method: "POST",
      body: await request.text(),
      headers: { "Content-Type": "application/json" },
    },
  );
  const payload = await upstream.json();
  // Never relay credential material, even from an older upstream deployment.
  return NextResponse.json(
    upstream.ok
      ? {
          message:
            "If an account exists, password reset instructions have been prepared.",
        }
      : { detail: payload.detail ?? "Unable to request a password reset." },
    {
      status: upstream.status,
      headers: {
        "Cache-Control": "no-store",
        ...(upstream.headers.get("Retry-After")
          ? { "Retry-After": upstream.headers.get("Retry-After")! }
          : {}),
      },
    },
  );
}
