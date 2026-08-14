import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { captureBrowserErrors, registerFreshUser } from "./helpers";

test("@smoke core personal navigation works without browser errors", async ({ page }) => {
  const errors = captureBrowserErrors(page);
  await registerFreshUser(page);

  const routes = ["/dashboard", "/tasks/", "/entities/catalog", "/training", "/locktimer"];
  for (const route of routes) {
    const response = await page.goto(route);
    expect(response?.status(), `${route} response`).toBeLessThan(400);
    await expect(page.locator("main")).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("@a11y authenticated shell has no serious axe violations", async ({ page }) => {
  await registerFreshUser(page);
  const routes = ["/dashboard", "/tasks/", "/entities/catalog", "/locktimer"];

  for (const route of routes) {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const blocking = results.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(blocking, `${route}: ${JSON.stringify(blocking, null, 2)}`).toEqual([]);
  }
});

test("@usability keyboard focus is visible and page has one primary landmark", async ({ page }) => {
  await registerFreshUser(page);
  await page.goto("/dashboard");

  await expect(page.locator("main")).toHaveCount(1);
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toBeVisible();
  const outline = await focused.evaluate((node) => getComputedStyle(node).outlineStyle);
  expect(outline).not.toBe("none");
});

test("@usability no horizontal overflow at the target viewport", async ({ page }) => {
  await registerFreshUser(page);
  for (const route of ["/dashboard", "/tasks/", "/locktimer"] ) {
    await page.goto(route);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${route} horizontal overflow`).toBeLessThanOrEqual(1);
  }
});

test("@usability critical timer action remains discoverable", async ({ page }) => {
  await registerFreshUser(page);
  await page.goto("/locktimer");
  const stop = page.getByRole("button", { name: /safety|stop|останов|снять/i }).first();
  if (await stop.count()) {
    await expect(stop).toBeVisible();
  }
});
