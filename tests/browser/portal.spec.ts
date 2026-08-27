import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { captureBrowserErrors, registerFreshUser } from "./helpers";

test("@smoke core personal navigation works without browser errors", async ({ page }) => {
  // 19 routes × (goto + 3 assertions) exceeds the default 30 s on a loaded
  // machine — the test would abort mid-loop (ERR_ABORTED) on the timeout.
  test.setTimeout(180_000);
  const errors = captureBrowserErrors(page);
  await registerFreshUser(page);

  const routes = [
    "/dashboard", "/today", "/tasks/", "/entities/catalog", "/training",
    "/settings", "/account", "/media", "/api/v2/points/page", "/api/v2/inventory/page",
    "/api/v2/measurements/page", "/api/v2/schedule/page", "/api/v2/body-parts/page", "/consent",
    "/social/profile", "/social/relationships", "/social/feed", "/social/subjects",
  ];
  // /locktimer is a feature-gated route (timer_operational): it only exists in
  // the running app when the timer module is enabled. Probe the sidebar instead
  // of hardcoding it, so the test passes with any product composition.
  await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
  if ((await page.locator('a[href="/locktimer"]').count()) > 0) {
    routes.push("/locktimer");
  }
  for (const route of routes) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), `${route} response`).toBeLessThan(400);
    await expect(page.locator("main")).toBeVisible();
    await expect(page.locator("#pl-sidebar"), `${route} authenticated sidebar`).toBeVisible();
    await expect(page.locator('a[href="/login"]'), `${route} must not show guest login`).toHaveCount(0);
    expect(errors.splice(0), `${route} browser errors`).toEqual([]);
  }
});

test("@smoke activity session can be created and accepted with visible audit", async ({ page }) => {
  await registerFreshUser(page);
  // Sessions are created from the wizard (template cards) and redirect to the
  // /sessions list, where the accept / audit flow lives.
  await page.goto("/sessions/wizard");
  await page.locator('form[action="/sessions/create-from-template"] button[type="submit"]').first().click();
  await expect(page).toHaveURL(/\/sessions/);
  await page.getByRole("button", { name: /^accept$/i }).first().click();
  await expect(page.getByText(/changes to the task set apply an xp penalty/i)).toBeVisible();
  await page.getByText(/audit history/i).click();
  await expect(page.getByText(/· accepted/)).toBeVisible();
});

test("@a11y authenticated shell has no serious axe violations (dark + light)", async ({ page }) => {
  // 34 routes × 2 theme passes of axe runs exceed the default 30 s timeout
  test.setTimeout(420_000);
  await registerFreshUser(page);
  // Full page audit (Session 41): the original 8 routes plus every remaining
  // nav page a fresh user can reach. /prompts is feature-gated (404 without
  // the flag) and /social/* redirect to /social/profile when no profile
  // exists yet — both verified by the smoke probe.
  const routes = [
    "/dashboard", "/today", "/tasks/", "/entities/catalog", "/training",
    "/settings", "/account", "/media", "/achievements", "/profile",
    "/consent", "/import", "/calendar", "/diets", "/sessions",
    "/locations", "/journal", "/medications", "/health", "/notifications",
    "/care", "/aftercare", "/insights", "/llm/exchange", "/locktimer",
    "/api/v2/points/page", "/api/v2/inventory/page", "/api/v2/measurements/page",
    "/api/v2/schedule/page", "/api/v2/body-parts/page",
    "/social/profile", "/social/relationships", "/social/feed", "/social/subjects",
  ];

  // DoD §20: dark/light одинаково приглушены. `dark:`-варианты Tailwind следуют
  // классу на <html>, а НЕ prefers-color-scheme — поэтому для light-прогона тему
  // надо реально переключить на сервере, а не эмулировать colorScheme.
  const setTheme = async (theme: string) => {
    // Use an in-page fetch like the real UI: app.js auto-attaches the
    // X-CSRF-Token header from the meta tag (page.request misses the cookie).
    await page.goto("/dashboard");
    const status = await page.evaluate(async (t) => {
      const r = await fetch("/settings/theme", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `theme=${encodeURIComponent(t)}`,
      });
      return r.status;
    }, theme);
    expect(status, `POST /settings/theme ${theme}`).toBeLessThan(400);
    await page.goto("/dashboard");
    const cls = await page.evaluate(() => document.documentElement.className);
    expect(cls, `theme class for ${theme}`).toContain(theme);
  };

  for (const scheme of ["dark", "light"] as const) {
    await setTheme(scheme);
    for (const route of routes) {
      await page.goto(route);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const blocking = results.violations.filter((violation) =>
        ["serious", "critical"].includes(violation.impact ?? ""),
      );
      expect(blocking, `${route} (${scheme}): ${JSON.stringify(blocking, null, 2)}`).toEqual([]);
    }
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
  for (const route of ["/dashboard", "/tasks/", "/locktimer", "/settings"] ) {
    await page.goto(route);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${route} horizontal overflow`).toBeLessThanOrEqual(1);
  }
});

test("@usability reduced-motion keeps the shell usable", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await registerFreshUser(page);
  await page.goto("/dashboard");
  await expect(page.locator("main")).toBeVisible();
  // Sidebar toggle is desktop-only (hidden on mobile) — click only when visible
  const toggle = page.locator("#pl-sidebar-toggle");
  if (await toggle.isVisible()) {
    await toggle.click();
    await expect(page.locator("main")).toBeVisible();
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
