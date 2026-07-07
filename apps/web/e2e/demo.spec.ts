import { test, type Page } from "@playwright/test";
import {
  mockApi,
  stubWebSocketReplay,
  SNAPSHOT_REPLAY_START,
  DEMO_REPLAY_EVENTS,
  SNAPSHOT_COMPLETED,
  SNAPSHOT_EXPLORATORY,
  MANIFEST_EXPLORATORY,
  RESOLUTION_NOMATCH,
  RUNS_LIST,
} from "./_fixtures";

// A single deterministic, backend-free video walking the storyboard. Recorded to
// test-results/**/video.webm (converted to docs/assets/demo.gif by the capture command in
// CLAUDE.md). Honest by construction: real historical in-silico oracle values, the live
// cockpit stays behind the Graph-GA baseline (no live "beat" — that lives in the Compare
// shot), and every mode / in-silico guardrail is on screen. No stabilizeForShot: the point
// is motion.
test.use({
  viewport: { width: 1280, height: 800 },
  video: { mode: "on", size: { width: 1280, height: 800 } },
});

const dwell = (p: Page, ms: number) => p.waitForTimeout(ms);

test("demo click-through (launch → analyzer → beat-GA → compose → seeds → quality/export)", async ({
  page,
}) => {
  test.setTimeout(150_000); // ~60-90s of scripted dwells + navigations
  // One handler for the whole video: benchmark completed on 281, exploratory on 271, and
  // the cold live-replay start on 284. The replay drives 284 only (281/271 are terminal →
  // no socket opens, so no events fire there).
  await mockApi(page, {
    runs: RUNS_LIST,
    // Only shot 4 (typed intent → refusal) calls /intent/resolve; shot 3 resolves a plan by
    // picking from the catalog (no server call), so NOMATCH is the only response needed.
    resolution: RESOLUTION_NOMATCH,
    manifest: MANIFEST_EXPLORATORY,
    snapshotById: {
      284: SNAPSHOT_REPLAY_START,
      281: SNAPSHOT_COMPLETED,
      271: SNAPSHOT_EXPLORATORY,
    },
  });
  await stubWebSocketReplay(page, DEMO_REPLAY_EVENTS, 1100);

  // Shots 1-2 — Overview: the closed loop, resting on Analyze (the differentiator).
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByText("The loop").first().waitFor({ timeout: 15_000 });
  await dwell(page, 1600);
  await page.getByText("The loop").first().scrollIntoViewIfNeeded();
  await dwell(page, 1800);

  // Shot 3 — Launcher: resolve a benchmark objective from the catalog.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await dwell(page, 1600);

  // Shot 4 — FR-015 refusal: an objective with no benchmark is grounded + blocked (feature).
  await page.getByLabel("Describe what you want").fill("make it dissolve well in water");
  await page.getByRole("button", { name: /^Resolve$/ }).click();
  await page.getByText("No benchmark matches that objective").waitFor({ timeout: 5_000 });
  await dwell(page, 1900);

  // Shots 5-6 — Live cockpit, one continuous beat: cold "waking the model" → the analyzer
  // writes hypotheses → the curve climbs, honestly tracking (behind) the Graph-GA baseline.
  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await page.getByText(/Waking the model/).waitFor({ timeout: 5_000 }); // the cold frame
  await dwell(page, 7200); // 6 events @ 1100ms + headroom to read the climbed state

  // Shot 7 — Completed benchmark 281: the finished run beats the GA control (~0.11 AUC).
  await page.goto("/runs/281", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByText("Top molecules").waitFor({ timeout: 5_000 });
  await dwell(page, 2400);

  // Shot 8 — Compare: honest head-to-head; 281 leads GA-268, GA has "no analyzer step".
  await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
  await page.getByText("Two runs, side by side").waitFor({ timeout: 15_000 });
  await page.getByText(/leads by/).waitFor({ timeout: 5_000 });
  await page.getByText("no analyzer step").waitFor({ timeout: 5_000 });
  await dwell(page, 2400);

  // Shot 9 — Overview benchmark strip (the figure canon lives here).
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByText("The loop").first().waitFor({ timeout: 15_000 });
  await dwell(page, 1600);

  // Shot 10 — Compose a custom multi-term objective → flagged exploratory.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Compose custom objective/ }).click();
  await page.getByText("Compose an objective").waitFor({ timeout: 5_000 });
  await page.getByRole("button", { name: /Add term/ }).click();
  await page.getByLabel(/Oracle for term/).nth(1).selectOption("sa_score");
  await dwell(page, 1900);

  // Shot 11 — Bring your own seeds; RDKit validates each server-side.
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.getByLabel("Seed molecules").fill("CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O");
  await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
  await dwell(page, 1900);

  // Shot 12 — Exploratory run-detail 271: quality/trust read-out + lineage export.
  await page.goto("/runs/271", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByRole("link", { name: /Download lineage \(CSV\)/ }).waitFor({ timeout: 5_000 });
  await dwell(page, 2600);

  // Shot 13 — hold on the end frame.
  await dwell(page, 1500);
});
