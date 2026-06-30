import { test } from "@playwright/test";

// Capture harness for the frontend-design critic loop: route-mocks the /compare
// API with an edge-case payload, renders /compare at 1280px, and writes a
// screenshot the critic reads. No Postgres / FastAPI needed. Output via SHOT_PATH.
//
// Edge cases packed in: a long task name, run B's AUC line starting later (leading
// null) and held flat after it plateaued (carry-forward tail), run A with analyzer
// hypotheses + run B (Graph-GA) with none, and a $0 vs non-zero cost split.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SHOT_PATH = process.env.SHOT_PATH ?? "/tmp/compare-shot.png";

const PAYLOAD = {
  a: {
    run_id: 11,
    task: "jnk3",
    status: "exhausted",
    best_score: 0.8814,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 2.4137,
    top_k: [
      { smiles: "O=C(Nc1ccc(F)cc1)c1ccc2[nH]ncc2c1", score: 0.8814 },
      { smiles: "COc1ccc(CNc2ncnc3[nH]ccc23)cc1", score: 0.8602 },
      { smiles: "Cc1cc(Nc2ncnc3sccc23)ccc1Cl", score: 0.8471 },
      { smiles: "O=C(Nc1cccnc1)c1ccc2nc[nH]c2c1", score: 0.8359 },
    ],
    hypotheses: [
      {
        after_generation_index: 1,
        text: "Polar aromatic cores with an H-bond donor near the hinge lift the score.",
        structured_json: { focus: "aminopyrimidine hinge binder", avoid: ["long alkyl chains"] },
      },
      {
        after_generation_index: 3,
        text: "Fluorinated anilides held the top of the population; push para-substitution.",
        structured_json: { focus: "para-F anilide", avoid: ["phenol", "free carboxylic acid"] },
      },
    ],
  },
  b: {
    run_id: 9,
    task: "troglitazone_rediscovery",
    status: "plateaued",
    best_score: 0.6402,
    oracle_calls: 3400,
    budget: 10000,
    cost_so_far_usd: 0.0,
    top_k: [
      { smiles: "O=C1NC(=O)SC1Cc1ccc(OCC2(C)Oc3ccccc3CC2)cc1", score: 0.6402 },
      { smiles: "O=C1NC(=O)SC1Cc1ccc(OCCc2ccccc2)cc1", score: 0.6011 },
      { smiles: "O=C1NC(=O)SC1Cc1ccc(OC)cc1", score: 0.5588 },
    ],
    hypotheses: [],
  },
  auc_overlay: [
    { oracle_calls: 100, a: 0.42, b: null },
    { oracle_calls: 200, a: 0.51, b: null },
    { oracle_calls: 320, a: 0.58, b: 0.3 },
    { oracle_calls: 500, a: 0.63, b: 0.38 },
    { oracle_calls: 800, a: 0.69, b: 0.45 },
    { oracle_calls: 1200, a: 0.73, b: 0.5 },
    { oracle_calls: 2000, a: 0.78, b: 0.56 },
    { oracle_calls: 3400, a: 0.82, b: 0.64 },
    { oracle_calls: 5000, a: 0.85, b: 0.64 },
    { oracle_calls: 7000, a: 0.87, b: 0.64 },
    { oracle_calls: 9000, a: 0.881, b: 0.64 },
    { oracle_calls: 10000, a: 0.8814, b: 0.64 },
  ],
};

test("capture /compare at 1280px", async ({ page }) => {
  await page.route(`${API}/compare**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PAYLOAD),
    });
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/compare?a=11&b=9", { waitUntil: "networkidle" });
  await page.getByText("Compare runs").waitFor({ timeout: 15_000 });
  await page.getByText("troglitazone_rediscovery").first().waitFor({ timeout: 5_000 });
  await page.screenshot({ path: SHOT_PATH, fullPage: true });
});
