import { expect, type APIRequestContext } from "@playwright/test";

// Local/CI fixture only. Never point this suite at production.
export const qaEmail = "ui-qa-owner@example.com";
export const qaPassword = "local-design-qa-only-123";
export const qaApi = process.env.SIFT_E2E_API_URL ?? "http://127.0.0.1:8000";

export async function qaOwner(request: APIRequestContext) {
  if (!["127.0.0.1", "localhost"].includes(new URL(qaApi).hostname))
    throw new Error("QA requires an isolated localhost API.");
  const created = await request.post(`${qaApi}/api/v1/auth/bootstrap`, {
    data: {
      email: qaEmail,
      password: qaPassword,
      full_name: "Design QA",
      organization_name: "UI QA",
      default_currency: "USD",
    },
  });
  expect([201, 409]).toContain(created.status());
  const login = await request.post(`${qaApi}/api/v1/auth/login`, {
    data: { email: qaEmail, password: qaPassword },
  });
  expect(login.status()).toBe(200);
  return login.json();
}
