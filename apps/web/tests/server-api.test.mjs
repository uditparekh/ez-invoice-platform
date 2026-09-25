import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";

// Execute the actual server module with only its Next request boundary mocked.
// No browser, production credentials, or live backend is involved.
const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(
  readFileSync(new URL("../src/lib/server/api.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText;
const secret = "test-gateway-secret-0123456789abcdef012345";

function harness(replies, ip = "2001:0DB8:0:0:0:0:0:1") {
  const requests = [];
  const writes = [];
  class NextResponse extends Response {
    cookies = { set: (...args) => writes.push(args) };
  }
  const exports = {};
  runInNewContext(compiled, {
    exports, Response, Headers, FormData,
    process: { env: { NODE_ENV: "production", EZ_WEB_GATEWAY_SHARED_SECRET: ` ${secret} ` } },
    require: (name) => {
      if (name === "server-only") return {};
      if (name === "next/server") return { NextResponse };
      if (name === "next/headers") return {
        cookies: async () => ({ get: (name) => ({ value: name === "ez_access" ? "expired-access" : "valid-refresh" }) }),
        headers: async () => new Headers({ "x-real-ip": ip }),
      };
      return require(name);
    },
    fetch: async (url, init) => {
      requests.push({ url, ...init });
      assert.ok(replies.length, "unexpected upstream request");
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return reply;
    },
  });
  return { api: exports, requests, writes };
}
const json = (status, body = {}, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json", ...headers },
});

for (const status of [429, 500, 503]) {
  test(`refresh ${status} preserves session cookies and returns a retryable response`, async () => {
    const h = harness([json(401), json(status, {}, { "Retry-After": "17" })]);
    const response = await h.api.authenticatedApiRequest("/api/v1/auth/me");
    assert.equal(response.status, status === 429 ? 429 : 503);
    assert.equal(response.headers.get("Retry-After"), "17");
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(h.writes.length, 0);
  });
}

test("network failure during refresh preserves cookies", async () => {
  const h = harness([json(401), new Error("network unavailable")]);
  assert.equal((await h.api.authenticatedApiRequest("/api/v1/auth/me")).status, 503);
  assert.equal(h.writes.length, 0);
});

test("invalid refresh credentials clear the session", async () => {
  const h = harness([json(401), json(401)]);
  assert.equal((await h.api.authenticatedApiRequest("/api/v1/auth/me")).status, 401);
  assert.equal(h.writes.length, 2);
  assert.ok(h.writes.every(([, value, options]) => value === "" && options.maxAge === 0));
});

test("successful refresh retries with the new access token and updates cookies", async () => {
  const h = harness([json(401), json(200, { access_token: "new-access", refresh_token: "new-refresh", expires_in: 900 }), json(200, { id: "user" })]);
  const response = await h.api.authenticatedApiRequest("/api/v1/auth/me");
  assert.equal(response.status, 200);
  assert.equal(h.requests[2].headers.get("Authorization"), "Bearer new-access");
  assert.equal(h.writes.length, 2);
  assert.equal(h.writes[0][1], "new-access");
});

test("gateway replaces supplied attestations and signs the original IPv6 text", async () => {
  const h = harness([json(200)]);
  await h.api.publicApiRequest("/api/v1/auth/login", { headers: { "X-Siftentry-Client-Ip": "attacker", "X-Siftentry-Client-Signature": "forged" } });
  const headers = h.requests[0].headers;
  const ip = headers.get("X-Siftentry-Client-Ip");
  const [seconds, digest] = headers.get("X-Siftentry-Client-Signature").split(".");
  assert.equal(ip, "2001:0DB8:0:0:0:0:0:1");
  assert.equal(digest, createHmac("sha256", secret).update(`${seconds}|${ip}`).digest("hex"));
});

for (const ip of ["invalid", "fe80::1%eth0", "203.0.113.1, 198.51.100.1"]) {
  test(`gateway refuses malformed observed address: ${ip}`, async () => {
    const h = harness([json(200)], ip);
    await h.api.publicApiRequest("/api/v1/auth/login", { headers: { "X-Siftentry-Client-Ip": "attacker", "X-Siftentry-Client-Signature": "forged" } });
    assert.equal(h.requests[0].headers.has("X-Siftentry-Client-Ip"), false);
    assert.equal(h.requests[0].headers.has("X-Siftentry-Client-Signature"), false);
  });
}
