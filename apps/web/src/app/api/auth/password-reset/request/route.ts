import { NextResponse } from "next/server";

import { publicApiRequest } from "@/lib/server/api";

export async function POST(request: Request) {
  const upstream = await publicApiRequest("/api/v1/auth/password-reset/request", {
    method: "POST",
    body: await request.text(),
    headers: { "Content-Type": "application/json" },
  });
  const payload = await upstream.json();
  return NextResponse.json(payload, { status: upstream.status });
}
