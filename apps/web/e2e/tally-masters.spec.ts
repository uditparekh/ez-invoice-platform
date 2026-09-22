import { expect, test } from "@playwright/test";
import { qaOwner, qaEmail, qaPassword, qaApi } from "./qa-auth";

for (const theme of ["light", "dark"]) {
  for (const width of [1440, 320]) {
    test(`master discovery ${theme} ${width}px: search, confirm, invalidate`, async ({
      page,
      request,
    }) => {
      test.setTimeout(120000);
      const auth = await qaOwner(request);
      const headers = { Authorization: `Bearer ${auth.access_token}` };
      const createdOrg = await request.post(`${qaApi}/api/v1/organizations`, {
        headers,
        data: {
          name: `Master QA ${theme} ${width} ${Date.now()}`,
          default_currency: "INR",
        },
      });
      expect(createdOrg.status()).toBe(201);
      const org = (await createdOrg.json()).id;
      const workspace = `masters-${org}`;
      const created = await request.post(
        `${qaApi}/api/v1/organizations/${org}/client-profiles`,
        {
          headers,
          data: {
            name: "Tally master discovery QA",
            accounting_system: "tally",
            is_default: true,
            settings: {
              company_name: "QA COMPANY — INDUSTRIAL MATERIALS",
              posting_mode: "voucher_with_inventory",
              purchase_ledger: "Purchases — Raw Materials",
              tax_ledger: "Input GST",
              stock_item_name: "Industrial Material",
              stock_item_uom: "KGS",
              godown_name: "Main Stores",
              default_currency: "INR",
              connection_settings: {
                connector_enabled: true,
                workspace_id: workspace,
                connector_token: "qa-master-token",
                tally_url: "http://localhost:9000",
              },
            },
          },
        },
      );
      expect(created.status()).toBe(201);
      const profile = await created.json();
      const connectorHeaders = { Authorization: "Bearer qa-master-token" };
      const begin = await request.post(
        "/api/v1/connectors/tally/masters/begin",
        { headers: connectorHeaders, data: { workspace_id: workspace } },
      );
      expect(begin.status()).toBe(200);
      const uploaded = await request.post(
        "/api/v1/connectors/tally/masters/submit",
        {
          headers: connectorHeaders,
          data: {
            workspace_id: workspace,
            ticket: (await begin.json()).ticket,
            company: {
              name: profile.settings.company_name,
              guid: "11111111-2222-3333-4444-555555555555",
            },
            masters: Object.fromEntries(
              Object.entries({
                ledgers: [
                  "Purchases — Raw Materials",
                  "Input GST",
                  "Purchase alternate",
                ],
                stock_items: ["Industrial Material"],
                units: ["KGS"],
                godowns: ["Main Stores"],
                voucher_types: ["Purchase"],
              }).map(([kind, names]) => [
                kind,
                names.map((name) => ({ name })),
              ]),
            ),
          },
        },
      );
      expect(uploaded.status()).toBe(200);
      await page.addInitScript(
        (orgId) => localStorage.setItem("siftentry-active-organization", orgId),
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
      await page.goto("/app/client-profiles");
      const editor = page.locator("[data-profile-editor]");
      await expect(
        editor.getByLabel("Profile name", { exact: true }),
      ).toHaveValue(profile.name);
      await editor.getByRole("tab", { name: "Posting rules" }).click();
      const panel = editor.getByRole("tabpanel");
      while (await panel.locator("details:not([open]) > summary").count())
        await panel.locator("details:not([open]) > summary").first().click();
      const snapshot = page.getByRole("region", {
        name: "Tally master snapshot",
      });
      await expect(
        snapshot.getByText("Recent snapshot · not a live guarantee"),
      ).toBeVisible();
      const ledger = panel.getByLabel("Purchase ledger", { exact: true });
      await expect(ledger).toHaveAttribute("list", /.+/);
      await expect(
        ledger.locator("..").getByText("Found in Tally", { exact: true }),
      ).toBeVisible();
      const confirm = snapshot.getByRole("button", {
        name: "Confirm saved mappings",
      });
      await expect(confirm).toBeDisabled();
      await snapshot.getByRole("checkbox").check();
      await confirm.click();
      await expect(snapshot.getByRole("status")).toContainText(
        "Mapping confirmed",
      );
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      await page.screenshot({
        path: test.info().outputPath(`masters-${theme}-${width}.png`),
        fullPage: true,
      });
      await ledger.fill("Unknown ledger");
      await expect(
        ledger.locator("..").getByText("Unverified", { exact: true }),
      ).toBeVisible();
      await expect(
        snapshot.getByRole("button", { name: "Confirm saved mappings" }),
      ).toBeDisabled();
      await editor
        .getByRole("button", { name: "Save draft", exact: true })
        .first()
        .click();
      await expect(
        snapshot.getByText("Saved mapping checks · 1 missing"),
      ).toBeVisible();
      await expect(
        snapshot.getByRole("button", { name: "Confirm saved mappings" }),
      ).toBeDisabled();
      const invoices = await request.get(
        `${qaApi}/api/v1/invoices?organization_id=${org}`,
        { headers },
      );
      expect(invoices.status()).toBe(200);
      expect(await invoices.json()).toEqual([]);
    });
  }
}
