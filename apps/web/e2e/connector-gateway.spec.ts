import { expect, test } from "@playwright/test";

test("native connector gateway works without a browser session", async ({ request }) => {
  for (const path of ["diagnostics", "heartbeat", "jobs/claim", "jobs/results"]) {
    const response = await request.post(`/api/v1/connectors/tally/${path}`, {
      data: { workspace_id: "qa-no-credentials", results: [] },
    });
    expect(response.status()).toBe(401);
    expect(response.headers()["cache-control"]).toBe("no-store");
    expect((await response.json()).detail).toContain("token");
  }
});

test("gateway rejects arbitrary routes, methods and malformed bodies", async ({ request }) => {
  expect((await request.post("/api/v1/connectors/tally/admin", { data: {} })).status()).toBe(404);
  expect((await request.get("/api/v1/connectors/tally/diagnostics")).status()).toBe(405);
  expect((await request.post("/api/v1/connectors/tally/diagnostics", {
    data: Buffer.from("not json"), headers: { "Content-Type": "application/json" },
  })).status()).toBe(400);
  expect((await request.post("/api/v1/connectors/tally/diagnostics", {
    data: "text", headers: { "Content-Type": "text/plain" },
  })).status()).toBe(415);
  expect((await request.post("/api/v1/connectors/tally/diagnostics", {
    data: { oversized: "x".repeat(4 * 1024 * 1024) },
  })).status()).toBe(413);
});
