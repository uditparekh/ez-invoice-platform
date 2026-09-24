import { expect, test, type Locator, type Page } from "@playwright/test";
import { qaApi, qaEmail, qaOwner, qaPassword } from "./qa-auth";

async function contained(control: Locator, width: number, minimum = 24) {
  await expect(control).toBeVisible();
  const box = await control.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(minimum);
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
}

async function demo(page: Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await page.waitForURL("**/app");
}

for (const width of [320, 375, 390, 768, 1024, 1440]) {
  test(`sign-in controls fit at ${width}px in both themes`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/login");
    for (const theme of ["Light", "Dark"]) {
      await page.getByRole("button", { name: theme, exact: true }).click();
      for (const control of [
        page.getByLabel("Work email"),
        page.getByLabel("Password", { exact: false }),
        page.getByRole("button", { name: "Continue", exact: true }),
        page.getByRole("button", { name: "Explore demo workspace" }),
        page.getByRole("button", { name: "Dark", exact: true }),
      ])
        await contained(control, width);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: test.info().outputPath(`login-${theme}.png`),
      });
    }
  });
}

test("theme selection is shared, persists, and follows device changes only in System", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await demo(page);
  await page.goto("/app/settings");
  await page.getByRole("button", { name: "Appearance", exact: false }).click();
  const pane = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Appearance", exact: true }),
  });
  const header = page.locator("header");
  await pane.getByRole("button", { name: "Light", exact: true }).click();
  await expect(
    header.getByRole("button", { name: "Light", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await header.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(
    pane.getByRole("button", { name: "Dark", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await pane.getByRole("button", { name: "System", exact: true }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveClass(/dark/);
  await pane.getByRole("button", { name: "Light", exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect(
    header.getByRole("button", { name: "Light", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.goto("/app/sift");
  await expect(page.locator(".product-shell .dark")).toHaveCount(0);
});

test("mobile drawer is modal, restores focus, and the header stays visible while scrolling", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await demo(page);
  const opener = page.getByRole("button", { name: "Menu", exact: true });
  await opener.click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await expect(drawer).toBeVisible();
  for (const key of ["Tab", "Shift+Tab"]) {
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press(key);
      expect(
        await page.evaluate(() =>
          document.activeElement?.closest("dialog")?.getAttribute("aria-label"),
        ),
      ).toBe("Navigation");
    }
  }
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(opener).toBeFocused();
  await page.goto("/app/settings");
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect
    .poll(async () => (await page.locator("header").boundingBox())!.y)
    .toBe(0);
});

test("public demo explains posting restrictions without requesting a posting plan", async ({
  page,
}) => {
  await demo(page);
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/posting-preview"))
      requests.push(request.url());
  });
  await page.goto("/app/review");
  await expect(
    page.getByText("Demo · read-only accounting preview"),
  ).toBeVisible();
  expect(requests).toEqual([]);
  await expect(
    page.getByRole("heading", { name: "Invoice review", exact: true }),
  ).toBeVisible();
});

test("long profile names, compact sections and mobile fields retain usable geometry", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const auth = await qaOwner(request);
  const headers = { Authorization: `Bearer ${auth.access_token}` };
  const createdOrg = await request.post(`${qaApi}/api/v1/organizations`, {
    headers,
    data: { name: `Layout QA ${Date.now()}`, default_currency: "USD" },
  });
  expect(createdOrg.status()).toBe(201);
  const org = (await createdOrg.json()).id;
  for (const name of [
    "North American Industrial Components and Manufacturing — Purchasing Division",
    "European Distribution and Wholesale Operations — Accounting",
  ]) {
    const profile = await request.post(
      `${qaApi}/api/v1/organizations/${org}/client-profiles`,
      {
        headers,
        data: {
          name,
          accounting_system: "tally",
          settings: {
            company_name: name,
            purchase_ledger: "Raw materials and consumables",
            posting_mode: "accounting_voucher",
            default_currency: "USD",
            connection_settings: { connector_enabled: false },
          },
        },
      },
    );
    expect(profile.status()).toBe(201);
  }
  await page.addInitScript(
    (id) => localStorage.setItem("siftentry-active-organization", id),
    org,
  );
  await page.goto("/login");
  await page.getByLabel("Work email").fill(qaEmail);
  await page.getByLabel("Password", { exact: false }).fill(qaPassword);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.waitForURL("**/app");
  for (const width of [320, 390, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/app/rules");
    const selector = page.getByRole("combobox", {
      name: "Profile",
      exact: true,
    });
    await contained(selector, width, 120);
    const heading = page.getByRole("heading", { level: 1 });
    const titleBox = (await heading.boundingBox())!;
    const selectBox = (await selector.boundingBox())!;
    expect(titleBox.width).toBeGreaterThan(200);
    expect(
      selectBox.y >= titleBox.y + titleBox.height ||
        selectBox.x >= titleBox.x + titleBox.width,
    ).toBe(true);
    await page.screenshot({
      path: test.info().outputPath(`rules-${width}.png`),
    });
  }
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/app/client-profiles");
  const editor = page.locator("[data-profile-editor]");
  await editor.getByRole("tab", { name: "Posting rules" }).click();
  const ledger = editor.getByLabel("Purchase ledger", { exact: true });
  // Expand the relevant configuration group if it starts collapsed.
  while (
    await editor
      .getByRole("tabpanel")
      .locator("details:not([open]) > summary")
      .count()
  ) {
    await editor
      .getByRole("tabpanel")
      .locator("details:not([open]) > summary")
      .first()
      .click();
  }
  await contained(ledger, 320, 200);
  await editor.getByRole("tab", { name: "Samples & checks" }).click();
  await expect(
    editor.getByText(/structured, scored regression test set will follow/),
  ).toHaveCount(0);
  await editor.getByRole("button", { name: "Add confirmed sample" }).click();
  await contained(
    editor.locator('form input[name="invoice_number"]'),
    320,
    230,
  );
  await editor
    .locator('form input[name="invoice_number"]')
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: test.info().outputPath("sample-fields-320.png"),
  });
  await page.getByRole("button", { name: "Create a new workspace" }).click();
  const dialog = page.getByRole("dialog", { name: "New workspace" });
  await contained(dialog.getByText(/Keep each client’s invoices/), 320, 230);
  await page.screenshot({ path: test.info().outputPath("workspace-320.png") });
  await page.keyboard.press("Escape");
  await page.goto("/app/settings");
  const currency = page.getByRole("combobox", {
    name: "Default currency",
    exact: true,
  });
  await expect(currency).toBeEnabled();
  await currency.selectOption("EUR");
  await expect(
    page.getByText("✓ Saved — synced to every workspace member."),
  ).toBeVisible();
  const saved = await request.get(
    `${qaApi}/api/v1/organizations/${org}/settings`,
    { headers },
  );
  expect((await saved.json()).default_currency).toBe("EUR");
  const imported = await request.post(`${qaApi}/api/v1/invoices/import`, {
    headers,
    data: {
      organization_id: org,
      source_file: "ui-layout-large-value.pdf",
      parser: "QA",
      invoice_number: "LAYOUT-QA-104",
      invoice_date: "2026-09-21",
      currency: "USD",
      subtotal: 10000000,
      tax_total: 1800000,
      total: 11800000,
      supplier: {
        name: "International Industrial Materials and Engineering Supplies Incorporated",
      },
      customer: { name: "Layout QA" },
      lines: [
        {
          line_number: 1,
          description: "Industrial material",
          quantity: 1000,
          uom: "EA",
          unit_price: 10000,
          net_amount: 10000000,
          tax_amount: 1800000,
          total_amount: 11800000,
        },
      ],
    },
  });
  expect(imported.status()).toBe(201);
  const invoice = await imported.json();
  expect(
    (
      await request.post(`${qaApi}/api/v1/invoices/${invoice.id}/validate`, {
        headers,
      })
    ).ok(),
  ).toBe(true);
  for (const theme of ["Light", "Dark"]) {
    await page
      .locator("header")
      .getByRole("button", { name: theme, exact: true })
      .click();
    await page.goto("/app/sift");
    const amount = page.getByRole("heading", {
      name: "$11,800,000.00",
      exact: true,
    });
    await contained(amount, 320, 200);
    expect(
      await amount.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    for (const name of [/Approve & next/, /Edit invoice/, /^Skip/]) {
      await contained(page.getByRole("button", { name }), 320, 200);
    }
    await page
      .getByRole("button", { name: /Edit invoice/ })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: test.info().outputPath(`sift-320-${theme}.png`),
    });
  }
});

test("read-only workspace settings never offer rejected mutations", async ({
  page,
}) => {
  await demo(page);
  await page.goto("/app/settings");
  for (const name of [
    "Default currency",
    "Default country / tax",
    "Primary accounting system",
  ]) {
    await expect(
      page.getByRole("combobox", { name, exact: true }),
    ).toBeDisabled();
  }
  await expect(
    page.getByRole("button", { name: "New workspace", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Notifications", exact: false })
    .click();
  const checkboxes = page.getByRole("checkbox");
  await expect(checkboxes).toHaveCount(3);
  for (const checkbox of await checkboxes.all())
    await expect(checkbox).toBeDisabled();
  await page
    .getByRole("button", { name: "Data retention", exact: false })
    .click();
  await expect(
    page.getByRole("button", { name: /Delete after review window/ }),
  ).toBeDisabled();
});

for (const width of [375, 768, 1024]) {
  test(`all product routes reflow at ${width}px in both themes`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    await demo(page);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const theme of ["Light", "Dark"]) {
      await page
        .locator("header")
        .getByRole("button", { name: theme, exact: true })
        .click();
      for (const route of [
        "/app",
        "/app/invoices",
        "/app/review",
        "/app/history",
        "/app/analytics",
        "/app/approvals",
        "/app/integrations",
        "/app/accounting/tally",
        "/app/accounting/quickbooks",
        "/app/accounting/zoho-books",
        "/app/accounting/netsuite",
        "/app/accounting/coupa",
        "/app/accounting/sap",
        "/app/client-profiles",
        "/app/rules",
        "/app/settings",
        "/app/sift",
        "/app/exceptions",
        "/app/vendors",
        "/app/roadmap",
      ]) {
        await page.goto(route);
        await expect(
          page.getByRole("heading", { level: 1 }).first(),
        ).toBeVisible();
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
          `${theme} ${route}`,
        ).toBeLessThanOrEqual(width + 1);
        const header = page.locator("header");
        for (const button of await header.getByRole("button").all()) {
          if (await button.isVisible()) await contained(button, width);
        }
      }
    }
    expect(errors).toEqual([]);
  });
}

test("review cards stay bounded with wider system fallback fonts", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await demo(page);
  await page.goto("/app/review");
  const cards = page.locator("[data-review-field]");
  await expect(cards.first()).toBeVisible();
  for (const font of ["system-ui", "Arial", "Verdana"]) {
    await page.addStyleTag({
      content: `body { font-family: ${font}, sans-serif !important; }`,
    });
    for (const card of await cards.all()) {
      await contained(card, 320, 200);
      expect(
        await card.evaluate(
          (element) => element.scrollWidth <= element.clientWidth + 1,
        ),
      ).toBe(true);
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(321);
  }
});
