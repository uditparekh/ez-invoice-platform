import { expect, test } from "@playwright/test";

test("workspace dialog contains keyboard focus and restores it on close", async ({
  page,
  request,
}) => {
  const email = `design-qa-${Date.now()}@example.com`;
  const password = "local-design-qa-only-123";
  const created = await request.post(
    "http://127.0.0.1:8000/api/v1/auth/bootstrap",
    {
      data: {
        email,
        password,
        full_name: "Design QA",
        organization_name: `QA ${Date.now()}`,
        default_currency: "USD",
      },
    },
  );
  expect(created.status()).toBe(201);
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: false }).fill(password);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.waitForURL("**/app");
  const opener = page.getByRole("button", { name: "Create a new workspace" });
  await opener.click();
  await expect(
    page.getByRole("dialog", { name: "New workspace" }),
  ).toBeVisible();
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() =>
        Boolean(document.activeElement?.closest("dialog")),
      ),
    ).toBe(true);
  }
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(
      await page.evaluate(() =>
        Boolean(document.activeElement?.closest("dialog")),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(opener).toBeFocused();
});

for (const theme of ["light", "dark"]) {
  for (const width of [1440, 390, 320]) {
    test(`${theme} ${width}px: reporting and core workflows`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/login");
      await page
        .getByRole("button", {
          name: theme === "dark" ? "Dark" : "Light",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", { name: "Explore demo workspace" })
        .click();
      await page.waitForURL("**/app");
      await expect(page.locator("html")).toHaveClass(
        theme === "dark" ? /dark/ : /^(?!.*\bdark\b).*$/,
      );
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const route of [
        "/app",
        "/app/analytics",
        "/app/history",
        "/app/invoices",
        "/app/integrations",
        "/app/accounting/tally",
        "/app/client-profiles",
        "/app/rules",
        "/app/settings",
        "/app/review",
        "/app/approvals",
        "/app/sift",
      ]) {
        await page.goto(route);
        if (route === "/app" || route === "/app/analytics") {
          await expect(
            page.getByText("Invoices received", { exact: true }),
          ).toBeVisible();
        }
        if (route === "/app/history") {
          await expect(page.getByText(/\d+ recorded events/)).toBeVisible();
          for (const control of [
            page.getByLabel("Search history"),
            page.getByRole("button", { name: "Search", exact: true }),
          ]) {
            const box = await control.boundingBox();
            expect(box).not.toBeNull();
            expect(box!.width).toBeGreaterThanOrEqual(60);
            expect(box!.x).toBeGreaterThanOrEqual(0);
            expect(box!.x + box!.width).toBeLessThanOrEqual(width);
          }
        }
        if (route === "/app/analytics" && width < 768) {
          const values = page.locator("[data-mobile-report] dd");
          expect(await values.count()).toBeGreaterThan(0);
          for (const value of await values.all()) {
            await expect(value).toBeVisible();
            const box = await value.boundingBox();
            expect(box!.x + box!.width).toBeLessThanOrEqual(width);
            expect(
              await value.evaluate(
                (element) => element.scrollWidth <= element.clientWidth + 1,
              ),
            ).toBe(true);
          }
        }
        if (route === "/app/invoices") {
          await expect(
            page.getByText("DEMO-QB-1001", { exact: true }).first(),
          ).toBeVisible();
          const amount = page
            .getByRole("button")
            .filter({ hasText: "DEMO-QB-1001" })
            .getByText("$3,488.00", { exact: true });
          await expect(amount).toBeVisible();
          const box = await amount.boundingBox();
          expect(box).not.toBeNull();
          expect(box!.x).toBeGreaterThanOrEqual(0);
          expect(box!.x + box!.width).toBeLessThanOrEqual(width);
          expect(
            await amount.evaluate(
              (element) => element.scrollWidth <= element.clientWidth + 1,
            ),
          ).toBe(true);
        }
        if (route === "/app/review") {
          await expect(
            page.getByText("DEMO-ZOHO-1002", { exact: true }).first(),
          ).toBeVisible();
        }
        await expect(
          page.getByRole("heading", { level: 1 }).first(),
        ).toBeVisible();
        await expect(
          page.getByText(
            /Loading workspace insights|Loading recorded events|Loading workspace overview/,
          ),
        ).toHaveCount(0);
        const sizes = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          width: window.innerWidth,
        }));
        expect(sizes.scroll, `${route} page overflow`).toBeLessThanOrEqual(
          sizes.width + 1,
        );
        if (
          [
            "/app",
            "/app/analytics",
            "/app/history",
            "/app/invoices",
            "/app/review",
          ].includes(route)
        ) {
          await page.screenshot({
            path: test.info().outputPath(`${route.replaceAll("/", "-")}.png`),
            fullPage: true,
          });
        }
      }
      expect(errors).toEqual([]);
    });
  }
}

test("History shows real events and exports the same filtered records", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await page.waitForURL("**/app");
  await page.goto("/app/history");
  await expect(page.getByText(/\d+ recorded events/)).toBeVisible();
  await page.getByLabel("Event category").selectOption("posting");
  await expect(
    page.getByText("Posting succeeded", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Invoice received", { exact: true })).toHaveCount(
    0,
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toContain("siftentry-history-");
  await page
    .getByRole("button", { name: "View posting result" })
    .first()
    .click();
  await expect(page.getByText(/succeeded ·/i).first()).toBeVisible();
  await page.getByRole("link", { name: "DEMO-QB-1001" }).first().click();
  await expect(
    page.getByText("DEMO-QB-1001", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("This page could not be found.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry posting" })).toHaveCount(
    0,
  );
  await page.goto("/app/review?invoice=missing-invoice-qa");
  await expect(
    page.getByText("This invoice is unavailable or has been removed."),
  ).toBeVisible();
  await expect(page.getByText("DEMO-ZOHO-1002", { exact: true })).toHaveCount(
    0,
  );
});
