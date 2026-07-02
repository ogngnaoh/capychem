import { expect, test } from "@playwright/test";

// Capture harness for the hi-fi wireframe critic loop (slice 05.02). Renders each
// /proto/* route at 1280px in LIGHT and DARK, asserts NO horizontal overflow, and
// writes a screenshot. Dark is forced via localStorage (the proto shell reads
// `proto-theme` on mount and toggles `.dark` on <html>). Static mock data => no
// Postgres / FastAPI / WebSocket needed.
//
//   SHOT_DIR=/path pnpm --filter web exec playwright test e2e/proto-shot.spec.ts
//   ... -g overview   (one route)

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

type Shot = { name: string; path: string; ready: string; dark?: boolean };

const ROUTES: Shot[] = [
  { name: "overview-light", path: "/proto/overview", ready: "The loop" },
  { name: "overview-dark", path: "/proto/overview", ready: "The loop", dark: true },
  { name: "workbench-running-light", path: "/proto/workbench", ready: "Analyzer reasoning" },
  { name: "workbench-running-dark", path: "/proto/workbench", ready: "Analyzer reasoning", dark: true },
  { name: "workbench-completed-light", path: "/proto/workbench/completed", ready: "Analyzer reasoning" },
  { name: "workbench-completed-dark", path: "/proto/workbench/completed", ready: "Analyzer reasoning", dark: true },
  { name: "launcher-light", path: "/proto/launcher", ready: "Objective catalog" },
  { name: "launcher-dark", path: "/proto/launcher", ready: "Objective catalog", dark: true },
  { name: "launcher-refusal-light", path: "/proto/launcher?state=nomatch", ready: "No benchmark matches that objective" },
  { name: "runs-light", path: "/proto/runs", ready: "All optimization runs" },
  { name: "runs-dark", path: "/proto/runs", ready: "All optimization runs", dark: true },
  { name: "compare-light", path: "/proto/compare", ready: "Two runs, side by side" },
  { name: "compare-dark", path: "/proto/compare", ready: "Two runs, side by side", dark: true },
];

for (const r of ROUTES) {
  test(`capture ${r.name} at 1280px (no h-scroll)`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (r.dark) {
      await page.addInitScript(() => {
        try {
          localStorage.setItem("proto-theme", "dark");
        } catch {
          /* ignore */
        }
      });
    }
    await page.goto(r.path, { waitUntil: "networkidle" });
    await page.getByText(r.ready).first().waitFor({ timeout: 15_000 });
    // Let recharts + the theme effect settle before measuring / shooting.
    await page.waitForTimeout(500);

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    console.log(`[proto-shot] ${r.name}: scrollWidth=${scrollWidth} (<= 1280)`);
    expect(scrollWidth, `${r.name} must not scroll horizontally`).toBeLessThanOrEqual(
      1280,
    );

    await page.screenshot({ path: `${SHOT_DIR}/${r.name}.png`, fullPage: true });
  });
}
