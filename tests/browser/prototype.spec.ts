import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const prototypeURL = process.env.DESIGN_PROTOTYPE_URL;

test("@a11y @usability Design v2 prototype shell", async ({ page }, testInfo) => {
  test.skip(!prototypeURL, "Set DESIGN_PROTOTYPE_URL to test the static Design v2 prototype");
  await page.goto(prototypeURL!);

  const viewport = testInfo.project.use.viewport;
  if (viewport && viewport.width <= 900) {
    await expect(page.getByRole("button", { name: "Открыть навигацию" })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: "Раскрыть меню" })).toBeVisible();
    await page.getByRole("button", { name: "Раскрыть меню" }).click();
    await expect(page.getByRole("button", { name: "Свернуть меню" })).toBeVisible();
  }

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking = results.violations.filter((violation) =>
    ["serious", "critical"].includes(violation.impact ?? ""),
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});
