// Route-mock fixtures for the backend-free accessibility suite. Molecular SVGs
// preserve the rendered candidate content without requiring the chemistry service.

import type { Page } from "@playwright/test";
import { MOLECULE_SVG_BY_SMILES, MOLECULE_SVG_FALLBACK } from "./_molecule-svgs.generated";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// The full 23-task PMO catalog, mirroring the live GET /catalog
// (apps/api/capychem/api/catalog.py).
export const CATALOG = [
  {
    group: "Drug-likeness",
    tasks: [
      { name: "qed", description: "Overall drug-likeness — balances size, polarity, and complexity." },
    ],
  },
  {
    group: "Target activity",
    tasks: [
      { name: "drd2", description: "Predicted activity against the dopamine D2 receptor." },
      { name: "jnk3", description: "Predicted activity against the JNK3 kinase." },
      { name: "gsk3b", description: "Predicted activity against the GSK-3β kinase." },
    ],
  },
  {
    group: "Rediscovery & similarity",
    tasks: [
      { name: "celecoxib_rediscovery", description: "How closely a molecule recovers celecoxib." },
      { name: "troglitazone_rediscovery", description: "How closely a molecule recovers troglitazone." },
      { name: "thiothixene_rediscovery", description: "How closely a molecule recovers thiothixene." },
      { name: "albuterol_similarity", description: "Structural similarity to albuterol." },
      { name: "mestranol_similarity", description: "Structural similarity to mestranol." },
      { name: "deco_hop", description: "Keep the core; vary the decorations (R-groups)." },
      { name: "scaffold_hop", description: "Keep the decorations; swap the core scaffold." },
    ],
  },
  {
    group: "Multi-property & composite (MPO)",
    tasks: [
      { name: "zaleplon_mpo", description: "Zaleplon-like profile across several properties." },
      { name: "perindopril_mpo", description: "Perindopril-like profile across several properties." },
      { name: "amlodipine_mpo", description: "Amlodipine-like profile across several properties." },
      { name: "fexofenadine_mpo", description: "Fexofenadine-like profile across several properties." },
      { name: "osimertinib_mpo", description: "Osimertinib-like profile across several properties." },
      { name: "ranolazine_mpo", description: "Ranolazine-like profile across several properties." },
      { name: "sitagliptin_mpo", description: "Sitagliptin-like profile across several properties." },
      { name: "median1", description: "Be similar to two reference molecules at once." },
      { name: "median2", description: "Be similar to a different two references at once." },
      { name: "isomers_c7h8n2o2", description: "Match the molecular formula C7H8N2O2." },
      { name: "isomers_c9h10n2o2pf2cl", description: "Match the formula C9H10N2O2PF2Cl." },
      { name: "valsartan_smarts", description: "Hit a valsartan substructure plus target properties." },
    ],
  },
];

const iso = (minsAgo: number) => new Date(Date.UTC(2026, 6, 2, 14, 0, 0) - minsAgo * 60_000).toISOString();

export const RUNS_LIST = [
  { run_id: 284, task: "troglitazone_rediscovery", mutation_strategy: "llm", mode: "benchmark", status: "running", best_score: 0.7431, oracle_calls: 4200, budget: 10000, started_at: iso(3) },
  { run_id: 281, task: "troglitazone_rediscovery", mutation_strategy: "llm", mode: "benchmark", status: "exhausted", best_score: 0.8814, oracle_calls: 10000, budget: 10000, started_at: iso(120) },
  { run_id: 277, task: "jnk3", mutation_strategy: "llm", mode: "benchmark", status: "exhausted", best_score: 0.8812, oracle_calls: 10000, budget: 10000, started_at: iso(300) },
  // one exploratory row so the axe gate exercises the amber (non-primary) badge in light + dark
  { run_id: 271, task: "qed", mutation_strategy: "graph_ga", mode: "exploratory", status: "plateaued", best_score: 0.9377, oracle_calls: 3400, budget: 10000, started_at: iso(1500) },
  { run_id: 268, task: "troglitazone_rediscovery", mutation_strategy: "graph_ga", mode: "benchmark", status: "exhausted", best_score: 0.7719, oracle_calls: 10000, budget: 10000, started_at: iso(2600) },
  { run_id: 264, task: "sitagliptin_mpo", mutation_strategy: "llm", mode: "benchmark", status: "stopped", best_score: 0.5312, oracle_calls: 2100, budget: 10000, started_at: iso(4000) },
  { run_id: 251, task: "deco_hop", mutation_strategy: "graph_ga", mode: "benchmark", status: "errored", best_score: null, oracle_calls: 120, budget: 10000, started_at: iso(9000) },
];

const LONG_SMILES = "CC(C)C[C@H](NC(=O)[C@@H](N)Cc1ccccc1)C(=O)N[C@@H](Cc1ccc(O)cc1)C(=O)N[C@@H](CCCCN)C(=O)O";

const TOP_K = [
  { smiles: LONG_SMILES, score: 0.8814 },
  { smiles: "O=C(Nc1ccc(F)cc1)c1ccc2[nH]ncc2c1", score: 0.8602 },
  { smiles: "COc1ccc(CNc2ncnc3[nH]ccc23)cc1", score: 0.8471 },
  { smiles: "Cc1cc(Nc2ncnc3sccc23)ccc1Cl", score: 0.8359 },
  { smiles: "O=C(Nc1cccnc1)c1ccc2nc[nH]c2c1", score: 0.8201 },
  { smiles: "COc1ccc2nc(N)sc2c1C(=O)Nc1ccccc1", score: 0.8098 },
];

// Per-candidate quality reports (07-05/07-08), populated at finalize — honest in-silico
// values (N6). One row trips Veber + a Brenk alarm and one trips Lipinski + PAINS so the
// warn chips render; `quality` stays null on live snapshots (QualityBadges → "computing…").
const QUALITY = [
  { valid: true, qed: 0.62, sa_score: 2.91, mw: 495.6, logp: 3.1, hbd: 3, hba: 6, rotatable_bonds: 11, tpsa: 121.4, lipinski_pass: true, veber_pass: true, pains: false, brenk: false },
  { valid: true, qed: 0.71, sa_score: 2.38, mw: 271.2, logp: 2.7, hbd: 2, hba: 4, rotatable_bonds: 3, tpsa: 66.2, lipinski_pass: true, veber_pass: true, pains: false, brenk: false },
  { valid: true, qed: 0.68, sa_score: 2.55, mw: 268.3, logp: 2.4, hbd: 2, hba: 5, rotatable_bonds: 4, tpsa: 63.1, lipinski_pass: true, veber_pass: true, pains: false, brenk: false },
  { valid: true, qed: 0.54, sa_score: 3.12, mw: 318.8, logp: 4.2, hbd: 1, hba: 3, rotatable_bonds: 3, tpsa: 51.0, lipinski_pass: true, veber_pass: false, pains: false, brenk: true },
  { valid: true, qed: 0.60, sa_score: 2.73, mw: 254.2, logp: 1.9, hbd: 2, hba: 5, rotatable_bonds: 3, tpsa: 68.9, lipinski_pass: true, veber_pass: true, pains: false, brenk: false },
  { valid: true, qed: 0.49, sa_score: 3.41, mw: 341.4, logp: 2.2, hbd: 2, hba: 6, rotatable_bonds: 5, tpsa: 89.3, lipinski_pass: false, veber_pass: true, pains: true, brenk: false },
];

const TOP_K_SCORED = TOP_K.map((m, i) => ({ ...m, quality: QUALITY[i] }));

const HYPS = [
  {
    after_generation_index: 1,
    text: "Polar aromatic cores with an H-bond donor near the hinge lift the score; small, flat scaffolds cluster near the bottom.",
    structured_json: { focus: "aminopyrimidine hinge binder", avoid: ["long alkyl chains"] },
  },
  {
    after_generation_index: 8,
    text: "Fluorinated anilides held the top of the population; para-substitution correlated with the largest gen-over-gen gains.",
    structured_json: { focus: "para-F anilide", avoid: ["phenol", "free carboxylic acid"] },
  },
  {
    after_generation_index: 15,
    text: "Fused bicyclic heteroaromatics (benzimidazole, azaindole) outperformed single rings; concentrating there.",
    structured_json: { focus: "fused bicyclic heteroaromatic core", avoid: ["flexible linkers"] },
  },
];

export const SNAPSHOT_COMPLETED = {
  run_id: 281,
  task: "troglitazone_rediscovery",
  mode: "benchmark",
  status: "exhausted",
  budget: 10000,
  plateau_window: 5,
  generation_index: 23,
  oracle_calls_used: 10000,
  best_score: 0.8814,
  top_k: TOP_K_SCORED,
  auc_curve: [
    { oracle_calls: 100, top10_mean: 0.42 },
    { oracle_calls: 800, top10_mean: 0.69 },
    { oracle_calls: 2000, top10_mean: 0.78 },
    { oracle_calls: 5000, top10_mean: 0.85 },
    { oracle_calls: 7200, top10_mean: 0.868 },
    { oracle_calls: 10000, top10_mean: 0.8814 },
  ],
  cost_so_far_usd: 2.4137,
  hypotheses: HYPS,
  trace_url: "http://localhost:3001/project/p/traces/281",
  valid_smiles_rate: 0.93,
  graph_ga_baseline: 0.7712,
  llm_cost_usd: 1.8342,
  oracle_cost_usd: 0.5795,
  diversity: 0.58,
  novelty: 0.41,
};

// A completed exploratory run (composed objective + a seed) — exercises the mode badge,
// the analyzer "composed objective" note, and the objective-composition legend built from
// the manifest. Never carries a Graph-GA baseline (07-01 G1-contamination guard).
export const SNAPSHOT_EXPLORATORY = {
  ...SNAPSHOT_COMPLETED,
  run_id: 271,
  task: "qed",
  mode: "exploratory",
  status: "stopped",
  graph_ga_baseline: null,
  diversity: 0.66,
  novelty: 0.52,
};

// POST /objective/validate preview (07-04): one composite [0,1] per probe; null = the
// objective couldn't score it.
export const VALIDATE_RESPONSE = {
  aggregator: "weighted_sum",
  n_terms: 2,
  results: [
    { smiles: "CCO", score: 0.34 },
    { smiles: "c1ccccc1", score: 0.47 },
    { smiles: "CC(=O)Oc1ccccc1C(=O)O", score: 0.62 },
    { smiles: "O=C(O)c1ccccc1O", score: 0.55 },
  ],
};

// GET /runs/{id}/manifest (07-06): benchmark run — no composed objective.
export const MANIFEST = {
  git_sha: "6dc34c9",
  model_id: "deepseek-v4-pro",
  pytdc_version: "0.3.6",
  trace_url: "http://localhost:3001/project/p/traces/281",
  config: {
    task: "troglitazone_rediscovery",
    budget: 10000,
    seed: 42,
    mutation_strategy: "llm",
    mode: "benchmark",
    seed_source: "default",
    objective_json: null,
    constraints_json: null,
  },
};

// GET /runs/{id}/manifest for the exploratory run — carries the composed objective so the
// downloads panel renders the term legend.
export const MANIFEST_EXPLORATORY = {
  git_sha: "6dc34c9",
  model_id: "deepseek-v4-pro",
  pytdc_version: "0.3.6",
  trace_url: null,
  config: {
    task: "qed",
    budget: 10000,
    seed: 42,
    mutation_strategy: "llm",
    mode: "exploratory",
    seed_source: "custom",
    objective_json: {
      terms: [
        { oracle: "qed", weight: 2, transform: { kind: "identity" }, oracle_kwargs: {} },
        { oracle: "sa_score", weight: 1, transform: { kind: "reverse_sigmoid", low: 2, high: 5, k: 10 }, oracle_kwargs: {} },
      ],
      aggregator: "weighted_sum",
    },
    constraints_json: { catalogs: ["PAINS"] },
  },
};

export const COMPARE_PAYLOAD = {
  a: {
    run_id: 281,
    task: "troglitazone_rediscovery",
    mode: "benchmark",
    status: "exhausted",
    best_score: 0.8814,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 2.4137,
    top_k: TOP_K.slice(0, 4),
    hypotheses: HYPS,
  },
  // b is run 268 — the same benchmark Graph-GA row that appears in RUNS_LIST (same mode
  // badge everywhere, resolving the "no run_id with two mode badges" rule). Both runs are
  // benchmark + same task, so Verdict draws the honest head-to-head: 281 (with an analyzer
  // step) leads the GA control by 0.1095. The GA column shows "no analyzer step" because a
  // Graph-GA run carries no hypotheses.
  b: {
    run_id: 268,
    task: "troglitazone_rediscovery",
    mode: "benchmark",
    status: "exhausted",
    best_score: 0.7719,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 0.4188,
    top_k: [
      { smiles: "O=C(Nc1ccc(Cl)cc1)c1ccc2[nH]ncc2c1", score: 0.7719 },
      { smiles: "Cc1ccc(Nc2ncnc3sccc23)cc1", score: 0.7514 },
      { smiles: "COc1ccc(Nc2ncnc3ccccc23)cc1", score: 0.7331 },
    ],
    hypotheses: [],
  },
  auc_overlay: [
    { oracle_calls: 100, a: 0.42, b: 0.4 },
    { oracle_calls: 800, a: 0.69, b: 0.63 },
    { oracle_calls: 2000, a: 0.78, b: 0.69 },
    { oracle_calls: 5000, a: 0.85, b: 0.755 },
    { oracle_calls: 7200, a: 0.868, b: 0.765 },
    { oracle_calls: 10000, a: 0.8814, b: 0.7719 },
  ],
};

export const RESOLUTION_MATCH = {
  matched_task: "troglitazone_rediscovery",
  confidence: "high",
  closest_task: null,
  rationale: "Matched the rediscovery objective for troglitazone.",
  resolved_plan: {
    task: "troglitazone_rediscovery",
    budget: 10000,
    plateau_window: 5,
    mutation_strategy: "graph_ga",
    seed_smiles: null,
  },
  refusals: [],
  cost_usd: 0.0002,
};

type MockOpts = {
  runs?: unknown;
  snapshot?: unknown;
  compare?: unknown;
  resolution?: unknown;
  validate?: unknown;
  manifest?: unknown;
  // When set, POST /runs 422s naming these SMILES (A3 seed-rejected path) exactly as the
  // RDKit gate in apps/api schemas.py does, so the launcher can mark the offending tokens.
  createReject?: string[];
};

export async function mockApi(page: Page, opts: MockOpts = {}) {
  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname;
    if (p === "/molecule/svg") {
      const smiles = new URL(req.url()).searchParams.get("smiles") ?? "";
      const body = MOLECULE_SVG_BY_SMILES[smiles] ?? MOLECULE_SVG_FALLBACK;
      await route.fulfill({ status: 200, contentType: "image/svg+xml", body });
      return;
    }
    // Lineage exports (07-07) stream file bodies; the page uses plain anchors, but a
    // stray fetch shouldn't 404 in the harness.
    if (/^\/runs\/\d+\/export\.(csv|sdf)$/.test(p)) {
      await route.fulfill({ status: 200, contentType: "text/plain", body: "candidate_id\n1\n" });
      return;
    }
    if (p === "/runs" && req.method() === "POST" && opts.createReject?.length) {
      const named = opts.createReject.map((s) => `'${s}'`).join(", ");
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: [
            { msg: `Value error, Validate seed SMILES via RDKit; these did not parse: [${named}]` },
          ],
        }),
      });
      return;
    }
    let body: unknown = {};
    if (p === "/catalog") body = CATALOG;
    else if (p === "/intent/resolve") body = opts.resolution ?? RESOLUTION_MATCH;
    else if (p === "/objective/validate") body = opts.validate ?? VALIDATE_RESPONSE;
    else if (p === "/compare") body = opts.compare ?? COMPARE_PAYLOAD;
    else if (/^\/runs\/\d+\/manifest$/.test(p)) body = opts.manifest ?? MANIFEST;
    else if (/^\/runs\/\d+$/.test(p)) {
      body = opts.snapshot ?? SNAPSHOT_COMPLETED;
    }
    else if (p === "/runs" && req.method() === "POST") body = { run_id: 999 };
    else if (p === "/runs") body = opts.runs ?? RUNS_LIST;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function forceDark(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("theme", "dark");
    } catch {
      /* ignore */
    }
  });
}
