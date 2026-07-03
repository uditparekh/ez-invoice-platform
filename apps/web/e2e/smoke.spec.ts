import { expect, test } from "@playwright/test";

/** Login → Home → command palette → shortcuts overlay.
 *  Credentials default to the `make bootstrap` demo owner. */
const EMAIL = process.env.SIFT_E2E_EMAIL ?? "udit@example.com";
const PASSWORD = process.env.SIFT_E2E_PASSWORD ?? "local-demo-password-123";

test("login, land on Home, open palette and shortcuts", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|log in/i }).click();

  await page.waitForURL(/\/app/, { timeout: 20_000 });
  await expect(page.getByText(/command center|home/i).first()).toBeVisible();

  // ⌘K command palette
  await page.keyboard.press("ControlOrMeta+k");
  const paletteInput = page.getByLabel("Command palette search");
  await expect(paletteInput).toBeVisible();
  await paletteInput.fill("sift");
  await expect(page.getByText("Start Sift mode")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(paletteInput).not.toBeVisible();

  // "?" shortcuts overlay
  await page.keyboard.press("?");
  await expect(page.getByText("Keyboard shortcuts")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("invoices queue renders with saved views strip", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|log in/i }).click();
  await page.waitForURL(/\/app/, { timeout: 20_000 });

  await page.goto("/app/invoices");
  await expect(page.getByText(/invoices/i).first()).toBeVisible();
});
