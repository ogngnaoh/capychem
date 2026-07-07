import { test } from "@playwright/test";

// Live-run capture (Step 2 — proof-of-authenticity). UNLIKE the other e2e specs, this hits
// the REAL FastAPI backend + real WebSocket (no mocks): it records the cockpit of an actual
// running DeepSeek loop so the analyzer hypotheses + 2D structures + climbing curve stream
// in for real. Complementary to the deterministic docs/assets/demo.gif — it does not replace
// it. Skipped unless LIVE_RUN_ID is set, so it never runs in CI / the mocked suite.
//
//   1. boot the stack (Postgres + API with CAPYCHEM_{PROPOSER,ANALYZER}_BACKEND=direct + DEEPSEEK_API_KEY)
//   2. launch a short run, note its id
//   3. LIVE_RUN_ID=<id> pnpm --filter web exec playwright test e2e/live-run.spec.ts
//   4. scripts/convert-demo-clips.sh-style ffmpeg → docs/assets/live-run.gif

const RUN_ID = process.env.LIVE_RUN_ID;

test.use({
  viewport: { width: 1280, height: 800 },
  video: { mode: "on", size: { width: 1280, height: 800 } },
});

test("live-run", async ({ page }) => {
  test.skip(!RUN_ID, "set LIVE_RUN_ID to capture a real running run");
  test.setTimeout(120_000);

  // Honest in-frame label so the clip is never mistaken for the deterministic demo.
  await page.addInitScript(() => {
    function mount() {
      if (document.getElementById("__live_badge")) return;
      const b = document.createElement("div");
      b.id = "__live_badge";
      b.textContent = "● LIVE — real DeepSeek run · in-silico";
      Object.assign(b.style, {
        position: "fixed",
        top: "70px",
        right: "18px",
        zIndex: "2147483647",
        background: "rgba(217,119,87,0.96)",
        color: "#fff",
        font: "600 12px Inter, system-ui, sans-serif",
        padding: "6px 11px",
        borderRadius: "6px",
        pointerEvents: "none",
        boxShadow: "0 2px 8px rgba(0,0,0,0.18)",
      });
      document.body.appendChild(b);
    }
    if (document.body) mount();
    else window.addEventListener("DOMContentLoaded", mount);
  });

  await page.goto(`/runs/${RUN_ID}`, { waitUntil: "domcontentloaded" });
  // Watch the analyzer + curve stream live at the top…
  await page.waitForTimeout(18_000);
  // …scroll to the real 2D structures as they update…
  await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight * 0.55, behavior: "smooth" }));
  await page.waitForTimeout(13_000);
  // …then back up to the climbing curve.
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await page.waitForTimeout(14_000);
});
