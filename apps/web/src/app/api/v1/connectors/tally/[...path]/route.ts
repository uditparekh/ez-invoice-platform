import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const allowedPaths = new Set(["diagnostics", "heartbeat", "jobs/claim", "jobs/results", "masters/begin", "masters/submit"]);
const maxBytes = 4 * 1024 * 1024;

function error(message: string, status: number) {
  return NextResponse.json({ success: false, message }, {
    status, headers: { "Cache-Control": "no-store" },
  });
}

// Native connectors authenticate to the API directly. Never attach browser
// cookies, refresh web sessions, forward redirects, or proxy arbitrary paths.
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!allowedPaths.has(path)) return error("Unknown connector endpoint.", 404);
  const base = process.env.EZ_WEB_API_BASE_URL?.replace(/\/$/, "")
    ?? (process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8000");
  if (!base) return error("Connector gateway is not configured. Contact SiftEntry support.", 503);
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return error("Use application/json.", 415);
  }
  const headers = new Headers({ "Content-Type": "application/json" });
  for (const name of ["authorization", "x-siftentry-connector-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Bound streamed bodies as well as declared lengths.
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        return error("Connector request is too large.", 413);
      }
      chunks.push(chunk.value);
    }
  }
  const body = Buffer.concat(chunks);
  try { JSON.parse(body.toString("utf8")); }
  catch { return error("Connector request must contain valid JSON.", 400); }
  try {
    const upstream = await fetch(`${base}/api/v1/connectors/tally/${path}`, {
      method: "POST", headers, body, redirect: "manual", cache: "no-store",
      signal: AbortSignal.timeout(25000),
    });
    if (upstream.status >= 300 && upstream.status < 400) {
      return error("Unexpected connector gateway redirect. Contact SiftEntry support.", 502);
    }
    if (!upstream.headers.get("content-type")?.includes("application/json")) {
      return error("SiftEntry could not complete the connector request. Contact support if this persists.",
        upstream.ok ? 502 : upstream.status);
    }
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return error("SiftEntry is temporarily unreachable. Your connector can retry safely.", 502);
  }
}
