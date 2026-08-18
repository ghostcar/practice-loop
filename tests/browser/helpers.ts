import { expect, type Page } from "@playwright/test";

export async function registerFreshUser(page: Page): Promise<void> {
  const email = `browser-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const password = "Browser-Test-2026!";

  await page.goto("/register");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();

  // Registration redirects to /login?registered=1 (no auto-login). Wait for the
  // redirect to settle before branching — page.url() right after click() can
  // still be the register page (race, observed on WebKit).
  await page.waitForURL(/(\/login|\/dashboard|\/consent\/setup)/, { timeout: 10_000 });
  if (page.url().includes("/login")) {
    await page.locator('input[name="email"]').fill(email);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('form[action="/consent/setup"] button[type="submit"]').click();
  }
  if (page.url().includes("/consent/setup")) {
    const consentBoxes = page.locator('input[name="consent_types"]');
    for (let index = 0; index < await consentBoxes.count(); index += 1) {
      await consentBoxes.nth(index).check();
    }
    await page.locator('button[type="submit"]').click();
  }
  await expect(page).toHaveURL(/\/dashboard/);
}

export function captureBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  // WebKit warns when a report-only CSP lacks a report-to endpoint. The CSP is
  // intentionally report-only until Gate C (enforcing), so this is a benign
  // engine-specific console message, not an app error.
  const knownBenign = (text: string) =>
    text.toLowerCase().includes("favicon") ||
    (text.includes("Content Security Policy") && text.includes("report-only mode"));
  page.on("console", (message) => {
    if (message.type() === "error" && !knownBenign(message.text())) {
      errors.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}
