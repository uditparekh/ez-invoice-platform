import { expect, test } from "@playwright/test";

function barrier() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

for (const theme of ["Light", "Dark"]) {
  test(`${theme}: demo handoff never shows empty Home and starts above the sticky header`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 402, height: 650 });
    const session = barrier();
    const invoices = barrier();
    await page.route("**/api/auth/me", async (route) => {
      await session.promise;
      await route.continue();
    });
    await page.route("**/api/invoices?*", async (route) => {
      await invoices.promise;
      await route.continue();
    });
    await page.goto("/login");
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.getByLabel("Work email").focus();
    await page.evaluate(() => window.scrollTo(0, 200));
    await page.getByRole("button", { name: "Explore demo workspace" }).click();
    await page.waitForURL("**/app");
    // Auth revalidation is deliberately still pending. The sign-in result is
    // enough to render the right viewer identity and load workspace data.
    await expect(page.locator("header")).toContainText(
      "SiftEntry Demo Workspace",
    );
    await expect(
      page.getByRole("link", { name: "Browse invoices", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Client Workspace", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("Your latest invoices will appear here."),
    ).toHaveCount(0);
    await expect(page.getByText("Loading recent invoices")).toBeVisible();
    const title = await page
      .getByRole("heading", { name: "Home", exact: true })
      .boundingBox();
    const header = await page.locator("header").boundingBox();
    expect(title!.y).toBeGreaterThanOrEqual(header!.y + header!.height);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    session.release();
    invoices.release();
    await expect(
      page.getByText("DEMO-ZOHO-1002", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath(`entry-${theme}.png`),
      fullPage: true,
    });
  });
}

test("cold entry gates unknown identity; transient auth failure offers retry without fake empty state", async ({
  page,
}) => {
  await page.request.post("/api/auth/demo");
  const session = barrier();
  await page.route("**/api/auth/me", async (route) => {
    await session.promise;
    await route.fulfill({
      status: 503,
      json: { detail: "temporarily unavailable" },
    });
  });
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Opening your workspace" }),
  ).toBeVisible();
  await expect(page.getByText("Client Workspace", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByText("Your latest invoices will appear here."),
  ).toHaveCount(0);
  session.release();
  await expect(
    page.getByRole("heading", { name: "Workspace unavailable" }),
  ).toBeVisible();
  await page.unroute("**/api/auth/me");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(
    page.getByRole("heading", { name: "Home", exact: true }),
  ).toBeVisible();
});

test("return navigation keeps exact-period reports visible while revalidating", async ({
  page,
}) => {
  await page.setViewportSize({ width: 402, height: 874 });
  await page.request.post("/api/auth/demo");
  await page.goto("/app");
  await expect(
    page.getByText("Invoices received", { exact: true }),
  ).toBeVisible();
  const refresh = barrier();
  await page.route("**/api/organizations/*/analytics?*", async (route) => {
    await refresh.promise;
    await route.continue();
  });
  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Insights" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Insights", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Invoices received", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading workspace insights")).toHaveCount(0);
  await expect(
    page.getByText("Updating report… Previous results remain visible."),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Home" })
    .click();
  await expect(
    page.getByText("Invoices received", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading workspace overview")).toHaveCount(0);
  refresh.release();
});

test("historical demo samples have an honest explanation and an actual-date action", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.request.post("/api/auth/demo");
  const queries: string[] = [];
  await page.route("**/api/organizations/*/analytics?*", async (route) => {
    queries.push(new URL(route.request().url()).search);
    await route.fulfill({
      json: {
        start: new URL(route.request().url()).searchParams.get("start"),
        end: new URL(route.request().url()).searchParams.get("end"),
        received_count: 0,
        posting_outcomes: {},
        queue: { posted: 2 },
        currencies: [],
        suppliers: [],
        daily: [],
        available_range: { start: "2026-01-10", end: "2026-01-12" },
      },
    });
  });
  await page.goto("/app");
  await expect(
    page.getByRole("complementary", { name: "About demo reports" }),
  ).toContainText("not a live accounting transaction");
  await page.getByRole("button", { name: "Show sample period" }).click();
  await expect
    .poll(() =>
      queries.some(
        (q) => q.includes("start=2026-01-10") && q.includes("end=2026-01-12"),
      ),
    )
    .toBe(true);
  await expect(
    page.getByText(/Selected period.*2026-01-10.*2026-01-12/),
  ).toBeVisible();
  await expect(page.getByText("Loading workspace overview")).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(320);
});

test("report cache never crosses workspace boundaries", async ({
  page,
  context,
}) => {
  await context.addCookies([
    {
      name: "ez_refresh",
      value: "local-qa-placeholder",
      url: "http://127.0.0.1:3000",
    },
  ]);
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "qa-user",
        email: "qa@example.invalid",
        full_name: "QA",
        is_active: true,
        memberships: ["a", "b"].map((id) => ({
          organization_id: id,
          organization_name: `Workspace ${id}`,
          role: "owner",
        })),
      },
    }),
  );
  await page.route("**/api/invoices?*", (route) => route.fulfill({ json: [] }));
  const other = barrier();
  await page.route("**/api/organizations/*/analytics?*", async (route) => {
    const isOther = route.request().url().includes("/b/");
    if (isOther) await other.promise;
    await route.fulfill({
      json: {
        start: "2026-09-01",
        end: "2026-09-24",
        received_count: isOther ? 999 : 123,
        posting_outcomes: {},
        queue: {},
        currencies: [],
        suppliers: [],
        daily: [],
      },
    });
  });
  await page.goto("/app");
  await expect(page.getByText("123", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "About demo reports" }),
  ).toHaveCount(0);
  await page.getByLabel("Active organization").selectOption("b");
  await expect(page.getByText("Loading workspace overview")).toBeVisible();
  await expect(page.getByText("123", { exact: true })).toHaveCount(0);
  other.release();
  await expect(page.getByText("999", { exact: true })).toBeVisible();
});
