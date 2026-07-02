import { expect, test } from "@playwright/test";
import { forceDark, mockApi, RUNS_LIST, stabilizeForShot } from "./_fixtures";

// Capture harness for the REAL Runs route (/runs) at 1280px, light + dark + empty.
// Route-mocks GET /runs with edge-case fixtures (long task name, null best_score,
// errored/stopped/plateaued statuses). Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

type Shot = { name: string; dark?: boolean; empty?: boolean };
const SHOTS: Shot[] = [
  { name: "runs-light" },
  { name: "runs-dark", dark: true },
  { name: "runs-empty", empty: true },
];

for (const s of SHOTS) {
  test(`capture ${s.name} at 1280px (no h-scroll)`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (s.dark) await forceDark(page);
    await mockApi(page, { runs: s.empty ? [] : RUNS_LIST });
    await page.goto("/runs", { waitUntil: "networkidle" });
    await page.getByText("All optimization runs").waitFor({ timeout: 15_000 });
    await page.waitForTimeout(400);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(`[shot] ${s.name}: scrollWidth=${scrollWidth} (<= 1280)`);
    expect(scrollWidth, `${s.name} must not scroll horizontally`).toBeLessThanOrEqual(1280);

    await stabilizeForShot(page);
    await page.screenshot({ path: `${SHOT_DIR}/${s.name}.png`, fullPage: true });
  });
}
