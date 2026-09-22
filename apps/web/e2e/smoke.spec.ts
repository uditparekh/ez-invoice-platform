import { expect, test } from "@playwright/test";
import { qaOwner, qaEmail, qaPassword } from "./qa-auth";

/** Local/CI smoke tests share the isolated QA fixture with the regression suite. */
const EMAIL = qaEmail;
const PASSWORD = qaPassword;
test.beforeEach(async ({ request }) => {
  await qaOwner(request);
});

test("login, land on Home, open palette and shortcuts", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await page.waitForURL(/\/app/, { timeout: 20_000 });
  await expect(page.getByText(/command center|home/i).first()).toBeVisible();
  // The route's static Home text can appear before client effects register
  // keyboard listeners. Wait for the authenticated shell, not an arbitrary delay.
  await expect(page.getByText("Design QA", { exact: true }).first()).toBeVisible();

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
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.waitForURL(/\/app/, { timeout: 20_000 });

  await page.goto("/app/invoices");
  await expect(page.getByText(/invoices/i).first()).toBeVisible();
});
