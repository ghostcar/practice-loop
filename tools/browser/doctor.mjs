import { chromium, firefox, webkit } from "@playwright/test";

const browsers = { chromium, firefox, webkit };
let failed = false;

console.log(`Node ${process.version}`);
for (const [name, type] of Object.entries(browsers)) {
  try {
    const browser = await type.launch({ headless: true });
    const page = await browser.newPage();
    await page.setContent("<main><h1>PracticeLoop browser doctor</h1></main>");
    console.log(`OK ${name}: ${await page.locator("h1").textContent()}`);
    await browser.close();
  } catch (error) {
    failed = true;
    console.error(`FAIL ${name}: ${error.message}`);
  }
}
process.exitCode = failed ? 1 : 0;
