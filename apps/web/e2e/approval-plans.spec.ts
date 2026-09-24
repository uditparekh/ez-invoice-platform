import { expect, test } from "@playwright/test";
import { qaOwner, qaApi, qaEmail, qaPassword } from "./qa-auth";

for (const theme of ["light", "dark"]) {
  for (const width of [1440, 390, 320]) {
    test(`${theme} ${width}px: review, freeze and reapprove a Tally entry`, async ({
      page,
      request,
    }) => {
      test.setTimeout(120_000);
      const auth = await qaOwner(request);
      const headers = { Authorization: `Bearer ${auth.access_token}` };
      const orgResponse = await request.post(`${qaApi}/api/v1/organizations`, {
        headers,
        data: {
          name: `Approval QA ${theme}-${width}-${Date.now()}`,
          default_currency: "USD",
        },
      });
      expect(orgResponse.status()).toBe(201);
      const org = (await orgResponse.json()).id;
      const profileResponse = await request.post(
        `${qaApi}/api/v1/organizations/${org}/client-profiles`,
        {
          headers,
          data: {
            name: "Pilot purchase workflow",
            accounting_system: "tally",
            is_default: true,
            settings: {
              company_name: "NEEL ENTERPRISE — LONG COMPANY NAME",
              default_currency: "USD",
              country_code: "US",
              country_name: "United States",
              posting_mode: "voucher_with_inventory",
              purchase_ledger: "PURCHASES — RAW MATERIALS AND CONSUMABLES",
              tax_ledger: "INPUT TAX",
              stock_item_name: "Industrial material",
              stock_item_uom: "EA",
              godown_name: "Main Stores",
              connection_settings: {
                connector_enabled: true,
                workspace_id: `qa-${org}`,
                connector_token: "qa-only-not-a-real-secret-0123456789abcdef",
                tally_url: "http://localhost:9000",
              },
            },
          },
        },
      );
      expect(profileResponse.status()).toBe(201);
      const profile = await profileResponse.json();
      const connectorHeaders = { Authorization: "Bearer qa-only-not-a-real-secret-0123456789abcdef" };
      const sync = await request.post(`${qaApi}/api/v1/connectors/tally/masters/begin`, {
        headers: connectorHeaders, data: { workspace_id: `qa-${org}` },
      });
      expect(sync.status()).toBe(200);
      const synced = await request.post(`${qaApi}/api/v1/connectors/tally/masters/submit`, {
        headers: connectorHeaders, data: {
          workspace_id: `qa-${org}`, ticket: (await sync.json()).ticket,
          company: { name: profile.settings.company_name, guid: "qa-company-guid" },
          masters: { ledgers: [], stock_items: [], units: [], godowns: [], voucher_types: [] },
        },
      });
      expect(synced.status()).toBe(200);
      const imported = await request.post(`${qaApi}/api/v1/invoices/import`, {
        headers,
        data: {
          organization_id: org,
          source_file: "QA-104.pdf",
          parser: "QA",
          invoice_number: "INV-104",
          invoice_date: "2026-09-21",
          currency: "USD",
          subtotal: 10000000,
          tax_total: 1800000,
          total: 11800000,
          supplier: { name: "Example Supplier" },
          customer: { name: "QA Customer" },
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
      const invoice = (await imported.json()).id;
      expect(
        (
          await request.post(`${qaApi}/api/v1/invoices/${invoice}/validate`, {
            headers,
          })
        ).status(),
      ).toBe(200);
      await page.addInitScript(
        (id) => localStorage.setItem("siftentry-active-organization", id),
        org,
      );
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/login");
      await page
        .getByRole("button", {
          name: theme === "dark" ? "Dark" : "Light",
          exact: true,
        })
        .click();
      await page.getByLabel("Work email").fill(qaEmail);
      await page.getByLabel("Password", { exact: false }).fill(qaPassword);
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page.waitForURL("**/app");
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/app/approvals");
      const preview = page.getByRole("region", {
        name: "Proposed accounting entry",
      });
      await expect(
        preview.getByText("NEEL ENTERPRISE — LONG COMPANY NAME", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Approve", exact: true }),
      ).toBeDisabled();
      await expect(
        preview.getByText("Godown: Main Stores", { exact: true }),
      ).toBeVisible();
      await expect(
        preview.getByText("$11,800,000.00", { exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      expect(
        await page
          .locator("[data-approval-total]")
          .evaluate((element) => element.scrollWidth <= element.clientWidth),
      ).toBe(true);
      for (const value of await preview.locator("dd, p").all()) {
        if (!(await value.isVisible())) continue;
        const box = await value.boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
      }
      await preview.getByLabel(/I reviewed the company/).check();
      await page.screenshot({
        path: `test-results/pkg35c-${theme}-${width}.png`,
        fullPage: true,
      });
      await page.getByRole("button", { name: "Approve", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "All approvals done" }),
      ).toBeVisible();
      const frozen = await request.post(
        `${qaApi}/api/v1/invoices/${invoice}/posting-preview`,
        { headers, data: {} },
      );
      const plan = (await frozen.json()).plan;
      expect(plan.version).toBe(1);
      expect(plan.xml).toContain("PURCHASES — RAW MATERIALS AND CONSUMABLES");
      await page.goto(`/app/review?invoice=${invoice}`);
      await expect(
        page.getByRole("heading", { name: "Approved entry · version 1" }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      profile.settings.purchase_ledger = "REVISED PURCHASES";
      expect(
        (
          await request.patch(
            `${qaApi}/api/v1/organizations/${org}/client-profiles/${profile.id}`,
            { headers, data: { settings: profile.settings } },
          )
        ).status(),
      ).toBe(200);
      await page.goto("/app/approvals");
      await expect(
        preview.getByText(/This entry needs a new approval/),
      ).toBeVisible();
      await expect(
        preview.getByText("REVISED PURCHASES", { exact: true }),
      ).toBeVisible();
      await preview.getByLabel(/I reviewed the company/).check();
      await page.getByRole("button", { name: "Approve", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "All approvals done" }),
      ).toBeVisible();
      const revised = await request.post(
        `${qaApi}/api/v1/invoices/${invoice}/posting-preview`,
        { headers, data: {} },
      );
      expect((await revised.json()).plan.version).toBe(2);
      const claim = await request.post(`${qaApi}/api/v1/connectors/tally/jobs/claim`, {
        headers: connectorHeaders, data: { workspace_id: `qa-${org}`, reconciliation_protocol: 1 },
      });
      expect(claim.status()).toBe(200);
      expect((await claim.json()).jobs).toHaveLength(1);
      await page.goto(`/app/review?invoice=${invoice}`);
      await expect(page.getByText(/If this attempt is not completing/)).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      await page.screenshot({ path: `test-results/pkg36b-recovery-${theme}-${width}.png`, fullPage: true });
      expect(errors).toEqual([]);
    });
  }
}
