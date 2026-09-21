import { expect, test } from "@playwright/test";
import { qaOwner, qaEmail, qaPassword, qaApi } from "./qa-auth";

const sections = [
  "Company",
  "Connection",
  "Posting rules",
  "Extraction guidance",
  "Samples & checks",
];

for (const theme of ["light", "dark"]) {
  for (const width of [1440, 390, 320]) {
    test(`${theme} ${width}px: profile sections preserve configuration`, async ({
      page,
      request,
    }) => {
      test.setTimeout(120_000);
      const email = qaEmail;
      const password = qaPassword;
      const base = qaApi;
      const auth = await qaOwner(request);
      const headers = { Authorization: `Bearer ${auth.access_token}` };
      const workspace = await request.post(`${base}/api/v1/organizations`, {
        headers,
        data: {
          name: `Profile QA ${theme}-${width}-${Date.now()}`,
          default_currency: "USD",
        },
      });
      expect(workspace.status()).toBe(201);
      const org = (await workspace.json()).id;
      const url = `${base}/api/v1/organizations/${org}/client-profiles`;
      await page.addInitScript(
        (orgId) =>
          window.localStorage.setItem("siftentry-active-organization", orgId),
        org,
      );
      const created = await request.post(url, {
        headers,
        data: {
          name: "Neel Enterprise — purchase workflow",
          accounting_system: "tally",
          description: "Original description",
          is_default: true,
          settings: {
            company_name: "NEEL ENTERPRISE — LONG COMPANY NAME",
            country_code: "US",
            country_name: "United States",
            default_currency: "USD",
            posting_mode: "voucher_with_inventory",
            purchase_ledger: "PURCHASES — RAW MATERIALS AND CONSUMABLES",
            tax_ledger: "Input tax",
            stock_item_name: "Industrial material",
            stock_item_uom: "KGS",
            godown_name: "Main Stores",
            connection_settings: {
              connector_enabled: true,
              workspace_id: `qa-${theme}-${width}`,
              connector_token: "qa-only-connector-secret",
              tally_url: "http://localhost:9000",
              connector_url: "http://127.0.0.1:8765",
              custom_setting: "preserve",
            },
            training_profile: {
              extraction_instructions:
                "Read the invoice number below Document No.",
              posting_expectations: "Review purchase allocations.",
              exception_examples: "Credit notes need review.",
              sample_invoices: [
                {
                  id: "sample-qa",
                  filename: "invoice-104.pdf",
                  notes: "Invoice INV-104; USD 1,250.00",
                  fields_confirmed: true,
                },
              ],
            },
            metadata: { preserve_me: { nested: true } },
            tax_settings: { custom_tax_setting: "preserve" },
          },
        },
      });
      expect(created.status()).toBe(201);
      const initial = await created.json();
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/login");
      await page
        .getByRole("button", {
          name: theme === "dark" ? "Dark" : "Light",
          exact: true,
        })
        .click();
      await page.getByLabel("Work email").fill(email);
      await page.getByLabel("Password", { exact: false }).fill(password);
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page.waitForURL("**/app");
      await page.goto("/app/client-profiles");
      const editor = page.locator("[data-profile-editor]");
      await expect(
        editor.getByLabel("Profile name", { exact: true }),
      ).toHaveValue(initial.name);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const section of sections) {
        await editor.getByRole("tab", { name: section, exact: false }).click();
        const panel = editor.getByRole("tabpanel");
        await expect(panel).toHaveCount(1);
        await expect(panel).toBeVisible();
        while (await panel.locator("details:not([open]) > summary").count()) {
          await panel.locator("details:not([open]) > summary").first().click();
        }
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBeLessThanOrEqual(width + 1);
        for (const input of await panel
          .locator(
            "input:not([type=checkbox]):not([type=file]), textarea, select",
          )
          .all()) {
          if (!(await input.isVisible())) continue;
          const box = await input.boundingBox();
          expect(box!.width).toBeGreaterThan(100);
          expect(box!.x).toBeGreaterThanOrEqual(0);
          expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
        }
        if (section === "Connection") {
          await expect(
            panel.getByText("No check-in yet", { exact: true }),
          ).toBeVisible();
          await expect(
            panel.getByLabel("Connector token", { exact: true }),
          ).toHaveAttribute("type", "password");
        }
        await page.screenshot({
          path: test
            .info()
            .outputPath(`${section.replaceAll(/[^a-z]/gi, "-")}.png`),
          fullPage: true,
        });
      }
      await editor.getByRole("tab", { name: "Posting rules" }).click();
      await editor
        .getByLabel("Posting mode", { exact: true })
        .selectOption("accounting_voucher");
      await expect(
        editor.getByLabel("Stock item", { exact: true }),
      ).toHaveCount(0);
      await editor
        .getByLabel("Posting mode", { exact: true })
        .selectOption("voucher_with_inventory");
      await expect(
        editor.getByLabel("Stock item", { exact: true }),
      ).toHaveValue("Industrial material");
      await editor.getByRole("tab", { name: "Company" }).click();
      await editor
        .getByLabel("Description", { exact: true })
        .fill("Updated description");
      await editor.getByRole("tab", { name: "Samples & checks" }).click();
      await expect(
        editor.getByRole("button", { name: "Activate profile" }),
      ).toBeDisabled();
      await editor
        .getByRole("button", { name: "Save draft", exact: true })
        .first()
        .click();
      await expect(
        editor.getByText("Client profile saved.", { exact: true }),
      ).toBeVisible();
      const after = await (
        await request.get(`${url}/${initial.id}`, { headers })
      ).json();
      expect(after.description).toBe("Updated description");
      expect(after.settings).toEqual(initial.settings);
      const expectedValues = editor.getByLabel(
        "Expected values — invoice-104.pdf",
        { exact: true },
      );
      await expectedValues.fill("Invoice INV-104; USD 1,275.00");
      const confirmation = editor.getByRole("checkbox", {
        name: /I checked these expected values/,
      });
      await expect(confirmation).not.toBeChecked();
      await confirmation.check();
      await editor
        .getByRole("button", { name: "Save draft", exact: true })
        .first()
        .click();
      await expect(
        editor.getByText(
          "All changes saved. Invoice approval is still required.",
        ),
      ).toBeVisible();
      const reviewed = await (
        await request.get(`${url}/${initial.id}`, { headers })
      ).json();
      expect(
        reviewed.settings.training_profile.sample_invoices[0].fields_confirmed,
      ).toBe(true);
      expect(
        reviewed.settings.training_profile.sample_invoices[0].notes,
      ).toContain("1,275.00");
      // Activation is a separate action and uses the saved profile.
      await editor.getByRole("button", { name: "Activate profile" }).click();
      await expect(
        editor.getByRole("button", { name: "Profile active", exact: true }),
      ).toBeDisabled();
      await expect(
        editor
          .getByRole("button", { name: "Save changes", exact: true })
          .first(),
      ).toBeVisible();
      await editor.getByRole("tab", { name: "Company" }).click();
      await editor
        .getByLabel("Description", { exact: true })
        .fill("Do not lose this edit");
      page.once("dialog", (dialog) => dialog.dismiss());
      await page
        .getByRole("button", { name: "New profile", exact: true })
        .click();
      await expect(
        editor.getByLabel("Description", { exact: true }),
      ).toHaveValue("Do not lose this edit");
      const companyTab = editor.getByRole("tab", { name: "Company" });
      await companyTab.focus();
      await page.keyboard.press("ArrowRight");
      await expect(
        editor.getByRole("tab", { name: "Connection" }),
      ).toBeFocused();
      expect(errors).toEqual([]);
    });
  }
}

test("demo viewer can inspect sections but cannot edit or activate", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await page.waitForURL("**/app");
  await page.goto("/app/client-profiles");
  const editor = page.locator("[data-profile-editor]");
  await expect(
    editor.getByLabel("Profile name", { exact: true }),
  ).toBeDisabled();
  await editor.getByRole("tab", { name: "Samples & checks" }).click();
  await expect(
    editor.getByRole("button", { name: /Activate profile|Profile active/ }),
  ).toBeDisabled();
});
