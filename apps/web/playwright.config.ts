import { defineConfig } from "@playwright/test";

/** SiftEntry E2E smoke tests.
 *  Prereqs (three terminals or background):
 *    make api        # FastAPI on :8000
 *    make bootstrap  # creates the demo owner if DB is empty
 *    make web        # Next.js on :3000
 *  Then: pnpm e2e   (first time: pnpm exec playwright install chromium) */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  retries: 0,
  use: {
    baseURL: process.env.SIFT_E2E_BASE_URL ?? "http://127.0.0.1:3000",
    screenshot: "only-on-failure",
  },
});
