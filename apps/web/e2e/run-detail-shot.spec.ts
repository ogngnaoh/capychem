import { test } from "@playwright/test";

// Capture harness for the frontend-design critic loop: route-mocks GET /runs/5 with
// a TERMINAL snapshot (status `exhausted` => LiveRun takes the no-WS branch, so no
// Postgres / FastAPI / WebSocket needed) and renders /runs/5 at 1280px. Output via
// SHOT_PATH.
//
// Edge cases packed in: a pathologically long SMILES (stresses the column wrap so the
// page never scrolls horizontally), a full top-K, an AUC curve, and analyzer hypotheses.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SHOT_PATH = process.env.SHOT_PATH ?? "/tmp/run-detail-shot.png";

const SNAPSHOT = {
  run_id: 5,
  task: "troglitazone_rediscovery",
  status: "exhausted",
  budget: 10000,
  plateau_window: 5,
  generation_index: 23,
  oracle_calls_used: 10000,
  best_score: 0.8814,
  top_k: [
    // deliberately long, to force the wrap and prove no horizontal scroll
    {
      smiles:
        "CC(C)C[C@H](NC(=O)[C@@H](N)Cc1ccccc1)C(=O)N[C@@H](Cc1ccc(O)cc1)C(=O)N[C@@H](CCCCN)C(=O)O",
      score: 0.8814,
    },
    { smiles: "O=C(Nc1ccc(F)cc1)c1ccc2[nH]ncc2c1", score: 0.8602 },
    { smiles: "COc1ccc(CNc2ncnc3[nH]ccc23)cc1", score: 0.8471 },
    { smiles: "Cc1cc(Nc2ncnc3sccc23)ccc1Cl", score: 0.8359 },
    { smiles: "O=C(Nc1cccnc1)c1ccc2nc[nH]c2c1", score: 0.8201 },
  ],
  auc_curve: [
    { oracle_calls: 100, top10_mean: 0.42 },
    { oracle_calls: 320, top10_mean: 0.58 },
    { oracle_calls: 800, top10_mean: 0.69 },
    { oracle_calls: 2000, top10_mean: 0.78 },
    { oracle_calls: 5000, top10_mean: 0.85 },
    { oracle_calls: 10000, top10_mean: 0.8814 },
  ],
  cost_so_far_usd: 2.4137,
  hypotheses: [
    {
      after_generation_index: 1,
      text: "Polar aromatic cores with an H-bond donor near the hinge lift the score.",
      structured_json: {
        focus: "aminopyrimidine hinge binder",
        avoid: ["long alkyl chains"],
      },
    },
    {
      after_generation_index: 3,
      text: "Fluorinated anilides held the top of the population; push para-substitution.",
      structured_json: {
        focus: "para-F anilide",
        avoid: ["phenol", "free carboxylic acid"],
      },
    },
  ],
};

test("capture /runs/5 (run detail) at 1280px", async ({ page }) => {
  await page.route(`${API}/runs/5`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SNAPSHOT),
    });
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/runs/5", { waitUntil: "networkidle" });
  await page.getByText("troglitazone_rediscovery").waitFor({ timeout: 15_000 });
  await page.getByText("Top molecules").waitFor({ timeout: 5_000 });
  await page.screenshot({ path: SHOT_PATH, fullPage: true });
});
