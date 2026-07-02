import { expect, test } from "@playwright/test";
import { forceDark, mockApi, stabilizeForShot } from "./_fixtures";

// Capture harness for the REAL Compare route (/compare?a=&b=) at 1280px, light + dark.
// Route-mocks GET /compare (LLM run with analyzer hypotheses vs Graph-GA run with none
// → "no analyzer step") and GET /runs (selector options + shell). Molecule tiles resolve
// via the mocked /molecule/svg. Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

type Shot = { name: string; dark?: boolean };
const SHOTS: Shot[] = [
  { name: "compare-light" },
  { name: "compare-dark", dark: true },
];

for (const s of SHOTS) {
  test(`capture ${s.name} at 1280px (no h-scroll)`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (s.dark) await forceDark(page);
    await mockApi(page);
    await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
    await page.getByText("Two runs, side by side").waitFor({ timeout: 15_000 });
    await page.getByText("no analyzer step").waitFor({ timeout: 5_000 });
    await page.waitForTimeout(500);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(`[shot] ${s.name}: scrollWidth=${scrollWidth} (<= 1280)`);
    expect(scrollWidth, `${s.name} must not scroll horizontally`).toBeLessThanOrEqual(1280);

    await stabilizeForShot(page);
    await page.screenshot({ path: `${SHOT_DIR}/${s.name}.png`, fullPage: true });
  });
}
