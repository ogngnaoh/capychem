import { expect, test } from "@playwright/test";

// Capture harness for the low-fi wireframe critic loop (slice 05.01). Renders each
// throwaway /proto/* route at 1280px, asserts NO horizontal overflow, and writes a
// screenshot. Static mock data => no Postgres / FastAPI / WebSocket needed.
//
// One shot per route into SHOT_DIR (default /tmp). Run all:
//   SHOT_DIR=/path pnpm --filter web exec playwright test e2e/proto-shot.spec.ts
// Or one:  ... -g overview

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

const ROUTES: { name: string; path: string; ready: string }[] = [
  { name: "overview", path: "/proto/overview", ready: "The loop" },
  { name: "workbench-running", path: "/proto/workbench", ready: "Analyzer reasoning" },
  {
    name: "workbench-completed",
    path: "/proto/workbench/completed",
    ready: "Analyzer reasoning",
  },
  { name: "launcher", path: "/proto/launcher", ready: "Objective catalog" },
  {
    name: "launcher-refusal",
    path: "/proto/launcher?state=nomatch",
    ready: "No benchmark matches that objective",
  },
];

for (const r of ROUTES) {
  test(`capture ${r.name} at 1280px (no h-scroll)`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(r.path, { waitUntil: "networkidle" });
    await page.getByText(r.ready).first().waitFor({ timeout: 15_000 });
    // Let recharts settle its layout before measuring / shooting.
    await page.waitForTimeout(400);

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
