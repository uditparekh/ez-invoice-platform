import { expect, test } from "@playwright/test";
import { qaOwner, qaEmail, qaPassword, qaApi } from "./qa-auth";

test("public reset responses never contain recovery credentials; web security headers are set", async ({
  request,
}) => {
  await qaOwner(request);
  const response = await request.post("/api/auth/password-reset/request", {
    data: { email: qaEmail },
  });
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({
    message:
      "If an account exists, password reset instructions have been prepared.",
  });
  expect(response.headers()["cache-control"]).toBe("no-store");
  const login = await request.get("/login");
  expect(login.headers()["x-content-type-options"]).toBe("nosniff");
  expect(login.headers()["content-security-policy"]).toContain(
    "frame-ancestors 'self'",
  );
});

test("demo viewers cannot generate connector credentials", async ({
  request,
}) => {
  const demo = await request.post("/api/auth/demo");
  expect(demo.status()).toBe(200);
  const org = (await demo.json()).user.memberships[0].organization_id;
  const denied = await request.post(
    `/api/organizations/${org}/connector-token`,
  );
  expect(denied.status()).toBe(403);
});

for (const theme of ["Light", "Dark"]) {
  test(`${theme}: connector token setup generates once, saves redacted, and stays within mobile bounds`, async ({
    page,
    request,
  }) => {
    const owner = await qaOwner(request);
    const headers = { Authorization: `Bearer ${owner.access_token}` };
    const created = await request.post(`${qaApi}/api/v1/organizations`, {
      headers,
      data: {
        name: `Security UI ${theme} ${Date.now()}`,
        default_currency: "USD",
      },
    });
    expect(created.status()).toBe(201);
    const org = (await created.json()).id;
    const profile = await request.post(
      `${qaApi}/api/v1/organizations/${org}/client-profiles`,
      {
        headers,
        data: {
          name: "Secure connector",
          accounting_system: "tally",
          settings: {
            company_name: "Test Company",
            connection_settings: {
              workspace_id: "security-ui",
              connector_enabled: true,
            },
          },
        },
      },
    );
    expect(profile.status()).toBe(201);
    const profileId = (await profile.json()).id;
    await page.setViewportSize({ width: 402, height: 874 });
    await page.goto("/login");
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.getByLabel("Work email").fill(qaEmail);
    await page.locator('input[name="password"]').fill(qaPassword);
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.waitForURL("**/app");
    await page.evaluate(
      (id) => localStorage.setItem("siftentry-active-organization", id),
      org,
    );
    await page.goto("/app/client-profiles");
    await page
      .locator("[data-profile-editor]")
      .getByRole("tab", { name: "Connection", exact: false })
      .click();
    await page
      .getByRole("button", { name: "Generate secure token", exact: true })
      .click();
    await expect(
      page.getByText(
        "Copy this token before saving. It cannot be recovered later.",
      ),
    ).toBeVisible();
    const token = await page
      .getByLabel("Connector token", { exact: true })
      .inputValue();
    expect(token).toHaveLength(43);
    await expect(
      page.getByRole("button", { name: "Copy new token" }),
    ).toBeVisible();
    // Test the real save contract without depending on unrelated activation rules.
    const stored = await request.patch(
      `${qaApi}/api/v1/organizations/${org}/client-profiles/${profileId}`,
      {
        headers,
        data: {
          settings: {
            company_name: "Test Company",
            connection_settings: {
              workspace_id: "security-ui",
              connector_enabled: true,
              connector_token: token,
            },
          },
        },
      },
    );
    expect(stored.status()).toBe(200);
    expect(
      (await stored.json()).settings.connection_settings.connector_token,
    ).toBe("");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
