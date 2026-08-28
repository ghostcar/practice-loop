import { execFileSync } from "node:child_process";

import { expect, type Page } from "@playwright/test";

export async function registerFreshUser(page: Page, emailOverride?: string): Promise<void> {
  const email = emailOverride ?? `browser-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const password = "Browser-Test-2026!";

  await page.goto("/register");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();

  // Registration auto-logs-in and redirects to the /onboarding wizard for new
  // users (skip it), then the consent gate, then /dashboard. Wait for the
  // redirect to settle before branching — page.url() right after click() can
  // still be the register page (race, observed on WebKit).
  await page.waitForURL(/(\/login|\/dashboard|\/consent\/setup|\/onboarding)/, { timeout: 10_000 });
  if (page.url().includes("/onboarding")) {
    // Skip button only appears in the last wizard step (display:hidden until
    // then) — submit the skip form directly, same as the button does via its
    // form= attribute (includes the hidden csrf_token input).
    await page.locator("#skip-form").evaluate((f) => (f as HTMLFormElement).submit());
  }
  if (page.url().includes("/login")) {
    await page.locator('input[name="email"]').fill(email);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('button[type="submit"]').click();
  }
  if (page.url().includes("/consent/setup")) {
    const consentBoxes = page.locator('input[name="consent_types"]');
    for (let index = 0; index < await consentBoxes.count(); index += 1) {
      await consentBoxes.nth(index).check();
    }
    await page.locator('form[action="/consent/setup"] button[type="submit"]').click();
  }
  await expect(page).toHaveURL(/\/dashboard/);
}

/**
 * Promote an already-registered user to role=admin directly in the database.
 *
 * There is no self-service admin promotion endpoint (by design — R2/R6), so
 * the a11y suite flips the role via SQL: `psql $DATABASE_URL` when the client
 * is available (GitHub runners ship one), else `docker exec` into the local
 * dev database container. Test infrastructure only — never used in prod.
 */
export function promoteToAdmin(email: string): void {
  const sql = `UPDATE users SET role='admin' WHERE email='${email}'`;
  const url = process.env.DATABASE_URL;
  if (url) {
    try {
      execFileSync("psql", [url.replace("postgresql+asyncpg://", "postgresql://"), "-c", sql], {
        stdio: "pipe",
      });
      return;
    } catch {
      // no psql client on the host — fall through to docker exec
    }
  }
  const container = process.env.E2E_DB_CONTAINER ?? "tracker-db-1";
  execFileSync(
    "docker",
    ["exec", container, "psql", "-U", "tracker", "-d", "tracker", "-c", sql],
    { stdio: "pipe" },
  );
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
