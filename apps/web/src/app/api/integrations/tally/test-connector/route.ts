import { NextResponse } from "next/server";

interface TallyConnectorTestBody {
  connectorUrl?: string;
  token?: string;
  mode?: "health" | "tally";
}

function jsonResponse(
  body: Record<string, unknown>,
  status = 200,
) {
  return NextResponse.json(body, { status });
}

function connectorHeaders(token?: string) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const cleanToken = token?.trim();
  if (cleanToken) {
    headers.set("Authorization", `Bearer ${cleanToken}`);
    headers.set("X-EZ-Connector-Token", cleanToken);
  }
  return headers;
}

async function connectorFetch(
  url: string,
  init: RequestInit,
) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    return await fetch(url, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  let body: TallyConnectorTestBody;
  try {
    body = (await request.json()) as TallyConnectorTestBody;
  } catch {
    return jsonResponse(
      { success: false, message: "Invalid connector test request." },
      400,
    );
  }

  const connectorUrl = (body.connectorUrl || "").trim().replace(/\/$/, "");
  const mode = body.mode === "tally" ? "tally" : "health";
  if (!connectorUrl) {
    return jsonResponse(
      { success: false, message: "Connector URL is required." },
      400,
    );
  }

  const path = mode === "tally" ? "/connector/test-tally" : "/health";
  const method = mode === "tally" ? "POST" : "GET";
  try {
    const response = await connectorFetch(`${connectorUrl}${path}`, {
      method,
      headers: connectorHeaders(body.token),
      body: method === "POST" ? JSON.stringify({}) : undefined,
    });
    const payload = (await response.json().catch(() => ({}))) as Record<
      string,
      unknown
    >;
    const success = Boolean(payload.success) && response.ok;
    return jsonResponse(
      {
        ...payload,
        success,
        message:
          typeof payload.message === "string"
            ? payload.message
            : success
              ? "Connector responded successfully."
              : `Connector returned HTTP ${response.status}.`,
      },
      response.ok ? 200 : response.status,
    );
  } catch (error) {
    const message =
      (error as Error).name === "AbortError"
        ? "Connector request timed out. Confirm the local connector window is running."
        : `Connector request failed: ${(error as Error).message}`;
    return jsonResponse({ success: false, message }, 502);
  }
}
