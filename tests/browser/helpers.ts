import { expect, type Page } from "@playwright/test";

export async function registerFreshUser(page: Page): Promise<void> {
  const email = `browser-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const password = "Browser-Test-2026!";

  await page.goto("/register");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();

  if (page.url().includes("/login")) {
    await page.locator('input[name="email"]').fill(email);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('button[type="submit"]').click();
  }
  await expect(page).toHaveURL(/\/dashboard/);
}

export function captureBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().toLowerCase().includes("favicon")) {
      errors.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}
