import { expect, test } from "@playwright/test";
import { qaApi, qaOwner, qaEmail, qaPassword } from "./qa-auth";

function fixturePdf() {
  const lines = [
    "ACME Supplies",
    "Invoice No: INV-QA-101",
    "Invoice Date: 2026-09-22",
    "Due Date: 2026-09-22",
    "Bill To: Pilot Client",
    "Currency: USD",
    "Description Quantity Unit Price Amount",
    "Widgets 2 50.00 100.00",
    "Subtotal: 100.00",
    "Tax: 0.00",
    "Total: USD 100.00",
  ];
  const stream = `BT /F1 10 Tf 72 770 Td ${lines.map((line, i) => `${i ? "0 -15 Td " : ""}(${line}) Tj`).join("\n")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, i) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((n) => `${String(n).padStart(10, "0")} 00000 n \n`)
    .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf);
}

for (const theme of ["light", "dark"]) {
  for (const width of [1440, 390, 320]) {
    test(`${theme} ${width}px: confirm and replay an extraction sample`, async ({
      page,
      request,
    }) => {
      test.setTimeout(120_000);
      const auth = await qaOwner(request);
      const headers = { Authorization: `Bearer ${auth.access_token}` };
      const orgResponse = await request.post(`${qaApi}/api/v1/organizations`, {
        headers,
        data: {
          name: `Evidence QA ${theme} ${width} ${Date.now()}`,
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
            name: "Extraction evidence QA",
            accounting_system: "excel",
            is_default: true,
          },
        },
      );
      expect(profileResponse.status()).toBe(201);
      const profile = (await profileResponse.json()).id;
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
      await page.getByRole("tab", { name: "Samples & checks" }).click();
      const section = page.getByRole("region", {
        name: "Extraction quality checks",
      });
      await expect(
        section.getByRole("button", { name: "Run extraction checks" }),
      ).toBeDisabled();
      await section
        .getByRole("button", { name: "Add confirmed sample" })
        .click();
      const form = section.locator("form").first();
      await form.getByLabel("Original PDF", { exact: true }).setInputFiles({
        name: "benchmark-long-supplier-name-invoice.pdf",
        mimeType: "application/pdf",
        buffer: fixturePdf(),
      });
      const expected = {
        invoice_number: "INV-QA-101",
        invoice_date: "2026-09-22",
        due_date: "2026-09-22",
        supplier_name: "ACME Supplies",
        supplier_tax_id: "",
        currency: "USD",
        subtotal: "100",
        tax_total: "0",
        total: "999",
      };
      for (const [name, value] of Object.entries(expected))
        await form.locator(`[name="${name}"]`).fill(value);
      const line = {
        description: "Widgets",
        quantity: "2",
        uom: "EA",
        unit_price: "50",
        net_amount: "100",
        tax_amount: "0",
        total_amount: "100",
        hsn_sac: "",
      };
      for (const [name, value] of Object.entries(line))
        await form.locator(`[name="line-0-${name}"]`).fill(value);
      await form
        .getByRole("checkbox", { name: /I checked every value/ })
        .check();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      for (const input of await form
        .locator("input:not([type=checkbox]), select")
        .all()) {
        const box = await input.boundingBox();
        expect(box!.width).toBeGreaterThan(100);
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
      }
      await section.screenshot({
        path: test.info().outputPath(`evidence-form-${theme}-${width}.png`),
      });
      await form.getByRole("button", { name: "Save confirmed sample" }).click();
      await expect(
        section.getByText("Confirmed sample saved.", { exact: false }),
      ).toBeVisible();
      await section
        .getByRole("button", { name: "Run extraction checks" })
        .click();
      await expect(section.getByText(/Parser: corrections needed/)).toBeVisible(
        { timeout: 60_000 },
      );
      await section.getByText(/Parser: corrections needed/).click();
      await expect(
        section.getByText("Expected: 999", { exact: true }),
      ).toBeVisible();
      await expect(
        section.getByText("Observed: 100", { exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      await section.screenshot({
        path: test.info().outputPath(`evidence-result-${theme}-${width}.png`),
      });
      const view = await (
        await request.get(
          `${qaApi}/api/v1/organizations/${org}/client-profiles/${profile}/extraction-evidence`,
          { headers },
        )
      ).json();
      expect(view.job.status).toBe("done");
      expect(view.job.result.include_ai).toBe(false);
      const invoices = await (
        await request.get(`${qaApi}/api/v1/invoices?organization_id=${org}`, {
          headers,
        })
      ).json();
      expect(invoices).toHaveLength(0);
      await section.getByRole("button", { name: /Delete sample/ }).click();
      await section.getByRole("button", { name: "Keep it" }).click();
      await expect(
        section.getByRole("button", { name: /Delete sample/ }),
      ).toBeVisible();
      await page.goto("/app/rules");
      await page
        .getByRole("button", { name: "Extraction checks", exact: true })
        .click();
      const rulesEvidence = page.getByRole("region", {
        name: "Extraction quality checks",
      });
      await expect(
        rulesEvidence.getByRole("button", { name: /Delete sample/ }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
    });
  }
}
