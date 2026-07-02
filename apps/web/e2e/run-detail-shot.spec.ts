import { expect, test } from "@playwright/test";
import {
  forceDark,
  mockApi,
  SNAPSHOT_COMPLETED,
  SNAPSHOT_RUNNING,
  stabilizeForShot,
  stubWebSocket,
} from "./_fixtures";

// Capture harness for the REAL Workbench cockpit (/runs/{id}) at 1280px. Covers the
// running and completed states, light + dark. A running snapshot is non-terminal, so
// LiveRun attempts a WebSocket to a (mocked-away) origin; the socket fails fast and the
// snapshot still renders — deterministic for a screenshot. Long SMILES + a Graph-GA
// baseline + molecule SVG tiles are all exercised. Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

type Shot = { name: string; snapshot: unknown; path: string; dark?: boolean; live?: boolean };
const SHOTS: Shot[] = [
  { name: "run-detail-running-light", snapshot: SNAPSHOT_RUNNING, path: "/runs/284", live: true },
  { name: "run-detail-running-dark", snapshot: SNAPSHOT_RUNNING, path: "/runs/284", dark: true, live: true },
  { name: "run-detail-completed-light", snapshot: SNAPSHOT_COMPLETED, path: "/runs/281" },
  { name: "run-detail-completed-dark", snapshot: SNAPSHOT_COMPLETED, path: "/runs/281", dark: true },
];

for (const s of SHOTS) {
  test(`capture ${s.name} at 1280px (no h-scroll)`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (s.dark) await forceDark(page);
    if (s.live) await stubWebSocket(page);
    await mockApi(page, { snapshot: s.snapshot });
    await page.goto(s.path, { waitUntil: "networkidle" });
    await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
    await page.getByText("Top molecules").waitFor({ timeout: 5_000 });
    await page.waitForTimeout(700);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(`[shot] ${s.name}: scrollWidth=${scrollWidth} (<= 1280)`);
    expect(scrollWidth, `${s.name} must not scroll horizontally`).toBeLessThanOrEqual(1280);

    await stabilizeForShot(page);
    await page.screenshot({ path: `${SHOT_DIR}/${s.name}.png`, fullPage: true });
  });
}
