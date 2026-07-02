// Shared route-mock fixtures for the -shot capture harness. Every screenshot spec
// intercepts ALL requests to the FastAPI origin and dispatches by pathname, so no
// Postgres / FastAPI / WebSocket is needed. Fixtures mirror apps/web/lib/api.ts shapes
// including the slice-03a RunSnapshot fields (valid_smiles_rate, graph_ga_baseline,
// llm_cost_usd, oracle_cost_usd) and the /catalog + /intent/resolve + /molecule/svg
// endpoints. Numbers are honest in-silico oracle scores (N6).

import type { Page } from "@playwright/test";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// A tiny deterministic stand-in for the RDKit SVG (real structures come from GET
// /molecule/svg server-side). Kept on-token-neutral so captures don't depend on RDKit.
const MOLECULE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120"><polygon points="60,14 100,37 100,83 60,106 20,83 20,37" fill="none" stroke="#9a8d84" stroke-width="2.5"/><circle cx="60" cy="60" r="17" fill="none" stroke="#9a8d84" stroke-width="2.5"/><line x1="100" y1="37" x2="114" y2="30" stroke="#9a8d84" stroke-width="2.5"/></svg>`;

// The full 23-task PMO catalog, mirroring the live GET /catalog
// (apps/api/capychem/api/catalog.py) so captures read faithfully.
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
  { run_id: 284, task: "troglitazone_rediscovery", mutation_strategy: "llm", status: "running", best_score: 0.7431, oracle_calls: 4200, budget: 10000, started_at: iso(3) },
  { run_id: 281, task: "troglitazone_rediscovery", mutation_strategy: "llm", status: "exhausted", best_score: 0.8814, oracle_calls: 10000, budget: 10000, started_at: iso(120) },
  { run_id: 277, task: "jnk3", mutation_strategy: "llm", status: "exhausted", best_score: 0.8812, oracle_calls: 10000, budget: 10000, started_at: iso(300) },
  { run_id: 271, task: "qed", mutation_strategy: "graph_ga", status: "plateaued", best_score: 0.9377, oracle_calls: 3400, budget: 10000, started_at: iso(1500) },
  { run_id: 268, task: "troglitazone_rediscovery", mutation_strategy: "graph_ga", status: "exhausted", best_score: 0.7719, oracle_calls: 10000, budget: 10000, started_at: iso(2600) },
  { run_id: 264, task: "sitagliptin_mpo", mutation_strategy: "llm", status: "stopped", best_score: 0.5312, oracle_calls: 2100, budget: 10000, started_at: iso(4000) },
  { run_id: 251, task: "deco_hop", mutation_strategy: "graph_ga", status: "errored", best_score: null, oracle_calls: 120, budget: 10000, started_at: iso(9000) },
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
  status: "exhausted",
  budget: 10000,
  plateau_window: 5,
  generation_index: 23,
  oracle_calls_used: 10000,
  best_score: 0.8814,
  top_k: TOP_K,
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
};

export const SNAPSHOT_RUNNING = {
  run_id: 284,
  task: "troglitazone_rediscovery",
  status: "running",
  budget: 10000,
  plateau_window: 5,
  generation_index: 10,
  oracle_calls_used: 4200,
  best_score: 0.7431,
  top_k: TOP_K.slice(0, 5).map((m, i) => ({ ...m, score: m.score - 0.14 + i * 0.01 })),
  auc_curve: [
    { oracle_calls: 100, top10_mean: 0.41 },
    { oracle_calls: 800, top10_mean: 0.64 },
    { oracle_calls: 1600, top10_mean: 0.7 },
    { oracle_calls: 2800, top10_mean: 0.726 },
    { oracle_calls: 4200, top10_mean: 0.7431 },
  ],
  cost_so_far_usd: 1.0362,
  hypotheses: HYPS.slice(0, 2),
  trace_url: "http://localhost:3001/project/p/traces/284",
  valid_smiles_rate: 0.91,
  graph_ga_baseline: 0.7712,
  llm_cost_usd: 0.7913,
  oracle_cost_usd: 0.2449,
};

export const COMPARE_PAYLOAD = {
  a: {
    run_id: 281,
    task: "troglitazone_rediscovery",
    status: "exhausted",
    best_score: 0.8814,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 2.4137,
    top_k: TOP_K.slice(0, 4),
    hypotheses: HYPS,
  },
  b: {
    run_id: 268,
    task: "troglitazone_rediscovery",
    status: "exhausted",
    best_score: 0.7719,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 0.4188,
    top_k: [
      { smiles: "O=C(Nc1ccc(Cl)cc1)c1ccc2[nH]ncc2c1", score: 0.7719 },
      { smiles: "Cc1ccc(Nc2ncnc3sccc23)cc1", score: 0.7514 },
      { smiles: "COc1ccc(Nc2ncnc3cccc23)cc1", score: 0.7331 },
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

export const RESOLUTION_NOMATCH = {
  matched_task: null,
  confidence: null,
  closest_task: "albuterol_similarity",
  rationale:
    "“make it dissolve well in water” isn’t one of the 23 PMO oracles. The closest available objective is albuterol_similarity — but it measures structural similarity, not solubility, so confirm before you launch.",
  resolved_plan: null,
  refusals: [{ field: "Objective", reason: "No benchmark exists for that objective." }],
  cost_usd: 0.0002,
};

type MockOpts = {
  runs?: unknown;
  snapshot?: unknown;
  compare?: unknown;
  resolution?: unknown;
};

export async function mockApi(page: Page, opts: MockOpts = {}) {
  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname;
    if (p === "/molecule/svg") {
      await route.fulfill({ status: 200, contentType: "image/svg+xml", body: MOLECULE_SVG });
      return;
    }
    let body: unknown = {};
    if (p === "/catalog") body = CATALOG;
    else if (p === "/intent/resolve") body = opts.resolution ?? RESOLUTION_MATCH;
    else if (p === "/compare") body = opts.compare ?? COMPARE_PAYLOAD;
    else if (/^\/runs\/\d+$/.test(p)) body = opts.snapshot ?? SNAPSHOT_COMPLETED;
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

// For a deterministic LIVE/running capture: `page.route` cannot intercept ws://, so a
// non-terminal snapshot would otherwise connect to the real backend (if one is up) and
// receive events that mutate the snapshot. Stub WebSocket to open with no traffic, so the
// cockpit renders the "running" state (Stop control, live loop indicator) unperturbed.
export async function stubWebSocket(page: Page) {
  await page.addInitScript(() => {
    const Native = window.WebSocket;
    // Only the app's run socket (/ws/runs/) is faked — Next.js dev HMR uses its own
    // WebSocket, so delegate every other URL to the native implementation.
    function Fake(this: unknown, url: string, protocols?: string | string[]) {
      if (typeof url === "string" && url.includes("/ws/runs/")) {
        const ws = {
          readyState: 1,
          onopen: null as null | ((ev: Event) => void),
          onmessage: null,
          onclose: null,
          onerror: null,
          send() {},
          close() {
            (this as { readyState: number }).readyState = 3;
          },
          addEventListener() {},
          removeEventListener() {},
        };
        setTimeout(() => ws.onopen?.(new Event("open")), 0);
        return ws;
      }
      return new Native(url, protocols);
    }
    Fake.CONNECTING = 0;
    Fake.OPEN = 1;
    Fake.CLOSING = 2;
    Fake.CLOSED = 3;
    Fake.prototype = Native.prototype;
    // @ts-expect-error override the global for the capture only
    window.WebSocket = Fake;
  });
}

// Playwright's fullPage capture mis-paints `position: sticky` elements at a scroll
// offset. At scroll 0 (which a full-page shot represents) the sticky nav header sits at
// the very top, so pin it to `static` for a faithful, artifact-free full-page render.
export async function stabilizeForShot(page: Page) {
  await page.addStyleTag({ content: "header{position:static !important}" });
}
