import { test, type Page } from "@playwright/test";
import {
  mockApi,
  stubWebSocketReplay,
  installCursor,
  SNAPSHOT_REPLAY_START,
  DEMO_REPLAY_EVENTS,
  SNAPSHOT_COMPLETED,
  SNAPSHOT_EXPLORATORY,
  MANIFEST_EXPLORATORY,
  RESOLUTION_NOMATCH,
  RUNS_LIST,
} from "./_fixtures";

// Six deterministic, backend-free videos → test-results/**/video.webm, converted to
// docs/assets/*.gif by scripts/convert-demo-clips.sh. Honest by construction: real
// historical in-silico oracle values; the live cockpit (284) stays behind the Graph-GA
// baseline 0.7712 (no live "beat" — that lives only in run 281 + Compare); every mode /
// in-silico guardrail is on screen. No stabilizeForShot: the point is motion.
test.use({
  viewport: { width: 1280, height: 800 },
  video: { mode: "on", size: { width: 1280, height: 800 } },
});

const dwell = (p: Page, ms: number) => p.waitForTimeout(ms);

// ---- Hero (~13s): resolve → live climb (behind baseline) → the finished run beats GA ----
test("demo-hero", async ({ page }) => {
  test.setTimeout(60_000);
  await installCursor(page);
  await mockApi(page, {
    runs: RUNS_LIST,
    snapshotById: { 284: SNAPSHOT_REPLAY_START, 281: SNAPSHOT_COMPLETED },
  });
  await stubWebSocketReplay(page, DEMO_REPLAY_EVENTS, 1000);

  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await dwell(page, 1400);

  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await page.getByText(/Waking the model/).waitFor({ timeout: 5_000 });
  await dwell(page, 6600); // climb + 2 analyzer hypotheses, still behind 0.7712

  await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
  await page.getByText(/leads by/).waitFor({ timeout: 10_000 });
  await page.getByText("no analyzer step").waitFor({ timeout: 5_000 });
  await dwell(page, 2600);
});

// ---- Clip 1: launch & resolve, then the FR-015 grounded refusal (a feature) ----
test("demo-clip-1-launch-resolve", async ({ page }) => {
  test.setTimeout(45_000);
  await installCursor(page);
  await mockApi(page, { runs: RUNS_LIST, resolution: RESOLUTION_NOMATCH });

  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await dwell(page, 1800);

  await page.getByLabel("Describe what you want").fill("make it dissolve well in water");
  await page.getByRole("button", { name: /^Resolve$/ }).click();
  await page.getByText("No benchmark matches that objective").waitFor({ timeout: 5_000 });
  await dwell(page, 2400);
});

// ---- Clip 2: live cockpit reasoning — cold start → analyzer writes → curve climbs behind baseline ----
test("demo-clip-2-live-cockpit", async ({ page }) => {
  test.setTimeout(45_000);
  await installCursor(page);
  await mockApi(page, { runs: RUNS_LIST, snapshotById: { 284: SNAPSHOT_REPLAY_START } });
  await stubWebSocketReplay(page, DEMO_REPLAY_EVENTS, 1100);

  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await page.getByText(/Waking the model/).waitFor({ timeout: 5_000 });
  await dwell(page, 8200); // 6 events @ 1100ms + headroom to read the climbed (still-behind) state
});

// ---- Clip 3: beat Graph-GA — finished 281 then the honest head-to-head Compare ----
test("demo-clip-3-beat-graph-ga", async ({ page }) => {
  test.setTimeout(45_000);
  await installCursor(page);
  await mockApi(page, { runs: RUNS_LIST, snapshotById: { 281: SNAPSHOT_COMPLETED } });

  await page.goto("/runs/281", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByText("Top molecules").waitFor({ timeout: 5_000 });
  await dwell(page, 2600);

  await page.goto("/compare?a=281&b=268", { waitUntil: "networkidle" });
  await page.getByText("Two runs, side by side").waitFor({ timeout: 15_000 });
  await page.getByText(/leads by/).waitFor({ timeout: 5_000 });
  await page.getByText("no analyzer step").waitFor({ timeout: 5_000 });
  await dwell(page, 2200);
  // Reveal the side-by-side molecules — real RDKit structures, LLM run vs GA control.
  await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
  await dwell(page, 2800);
});

// ---- Clip 4: make it yours — compose a custom objective (exploratory) + bring your own seeds ----
test("demo-clip-4-make-it-yours", async ({ page }) => {
  test.setTimeout(45_000);
  await installCursor(page);
  await mockApi(page, { runs: RUNS_LIST });

  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Compose custom objective/ }).click();
  await page.getByText("Compose an objective").waitFor({ timeout: 5_000 });
  await page.getByRole("button", { name: /Add term/ }).click();
  await page.getByLabel(/Oracle for term/).nth(1).selectOption("sa_score");
  await dwell(page, 2000);

  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.getByLabel("Seed molecules").fill("CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O");
  await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
  await dwell(page, 2400);
});

// ---- Clip 5: quality/trust read-out + lineage export (exploratory 271) ----
test("demo-clip-5-quality-export", async ({ page }) => {
  test.setTimeout(45_000);
  await installCursor(page);
  await mockApi(page, {
    runs: RUNS_LIST,
    snapshotById: { 271: SNAPSHOT_EXPLORATORY },
    manifest: MANIFEST_EXPLORATORY,
  });

  await page.goto("/runs/271", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByRole("link", { name: /Download lineage \(CSV\)/ }).waitFor({ timeout: 5_000 });
  await dwell(page, 1600);
  // Scroll to the top molecules — real structures + per-candidate quality/trust chips.
  await page.getByText("Top molecules").scrollIntoViewIfNeeded();
  await dwell(page, 2800);
  // Then the lineage export (CSV/SDF).
  await page.getByRole("link", { name: /Download lineage \(CSV\)/ }).scrollIntoViewIfNeeded();
  await dwell(page, 2200);
});
