// LOW-FI PROTOTYPE MOCK DATA — throwaway. Shapes mirror apps/web/lib/api.ts
// (RunSnapshot / TopMolecule / CurvePoint / AnalyzerHypothesis / RunListItem).
// No live API, no WS. Removed or evolved into real routes in slice 03.
//
// Honest figure canon (verbatim, never invent): beats or matches vanilla Graph-GA
// on all 21 comparable PMO tasks by AUC of top-10 (single seed, 10,000-call budget);
// decisive (~0.1 AUC+) on 9; 2 of 23 excluded-for-cause (defective oracles, not
// losses); the bar was >=6/23.

import type {
  AnalyzerHypothesis,
  CurvePoint,
  RunListItem,
  RunSnapshot,
  TopMolecule,
} from "@/lib/api";

// ── Objective catalog ─────────────────────────────────────────────────────
// The 23 PMO tasks, grouped in plain language for a non-chemist. Every oracle
// score is in-silico and normalised 0–1 where 1.0 is best.

export type CatalogObjective = { task: string; blurb: string };
export type CatalogGroup = {
  key: string;
  label: string;
  hint: string;
  objectives: CatalogObjective[];
};

export const CATALOG: CatalogGroup[] = [
  {
    key: "drug-likeness",
    label: "Drug-likeness",
    hint: "How “drug-like” a molecule looks overall.",
    objectives: [
      {
        task: "qed",
        blurb: "Overall drug-likeness — balances size, polarity, and complexity.",
      },
    ],
  },
  {
    key: "target-activity",
    label: "Target activity",
    hint: "Predicted activity against a biological target.",
    objectives: [
      { task: "drd2", blurb: "Predicted activity against the dopamine D2 receptor." },
      { task: "jnk3", blurb: "Predicted activity against the JNK3 kinase." },
      { task: "gsk3b", blurb: "Predicted activity against the GSK-3β kinase." },
    ],
  },
  {
    key: "rediscovery-similarity",
    label: "Rediscovery & similarity",
    hint: "Recover, or resemble, a known drug or scaffold.",
    objectives: [
      {
        task: "celecoxib_rediscovery",
        blurb: "How closely a molecule recovers celecoxib.",
      },
      {
        task: "troglitazone_rediscovery",
        blurb: "How closely a molecule recovers troglitazone.",
      },
      {
        task: "thiothixene_rediscovery",
        blurb: "How closely a molecule recovers thiothixene.",
      },
      {
        task: "albuterol_similarity",
        blurb: "Structural similarity to albuterol.",
      },
      {
        task: "mestranol_similarity",
        blurb: "Structural similarity to mestranol.",
      },
      { task: "deco_hop", blurb: "Keep the core; vary the decorations (R-groups)." },
      { task: "scaffold_hop", blurb: "Keep the decorations; swap the core scaffold." },
    ],
  },
  {
    key: "multi-property",
    label: "Multi-property & composite (MPO)",
    hint: "Balance several properties, or match a formula/pattern, at once.",
    objectives: [
      { task: "zaleplon_mpo", blurb: "Zaleplon-like profile across several properties." },
      { task: "perindopril_mpo", blurb: "Perindopril-like profile across several properties." },
      { task: "amlodipine_mpo", blurb: "Amlodipine-like profile across several properties." },
      { task: "fexofenadine_mpo", blurb: "Fexofenadine-like profile across several properties." },
      { task: "osimertinib_mpo", blurb: "Osimertinib-like profile across several properties." },
      { task: "ranolazine_mpo", blurb: "Ranolazine-like profile across several properties." },
      { task: "sitagliptin_mpo", blurb: "Sitagliptin-like profile across several properties." },
      { task: "median1", blurb: "Be similar to two reference molecules at once." },
      { task: "median2", blurb: "Be similar to a different two references at once." },
      { task: "isomers_c7h8n2o2", blurb: "Match the molecular formula C7H8N2O2." },
      { task: "isomers_c9h10n2o2pf2cl", blurb: "Match the formula C9H10N2O2PF2Cl." },
      { task: "valsartan_smarts", blurb: "Hit a valsartan substructure plus target properties." },
    ],
  },
];

export const CATALOG_COUNT = CATALOG.reduce((n, g) => n + g.objectives.length, 0); // 23

export function lookupObjective(task: string): CatalogObjective | undefined {
  for (const g of CATALOG) {
    const hit = g.objectives.find((o) => o.task === task);
    if (hit) return hit;
  }
  return undefined;
}

// ── Top molecules (long SMILES to stress-test wrapping / no h-scroll) ───────

const TOP_K: TopMolecule[] = [
  {
    smiles:
      "CC(C)C[C@H](NC(=O)[C@@H](N)Cc1ccccc1)C(=O)N[C@@H](Cc1ccc(O)cc1)C(=O)N[C@@H](CCCCN)C(=O)O",
    score: 0.8814,
  },
  { smiles: "O=C(Nc1ccc(F)cc1)c1ccc2[nH]ncc2c1", score: 0.8602 },
  { smiles: "COc1ccc(CNc2ncnc3[nH]ccc23)cc1", score: 0.8471 },
  { smiles: "Cc1cc(Nc2ncnc3sccc23)ccc1Cl", score: 0.8359 },
  { smiles: "O=C(Nc1cccnc1)c1ccc2nc[nH]c2c1", score: 0.8201 },
  { smiles: "COc1ccc2nc(N)sc2c1C(=O)Nc1ccccc1", score: 0.8098 },
  { smiles: "Clc1ccc(-c2nc3ccccc3[nH]2)cc1", score: 0.7955 },
  { smiles: "O=C(Nc1ccc(Cl)cc1)c1cc2ccccc2[nH]1", score: 0.7841 },
  { smiles: "CN1CCN(c2ccc(NC(=O)c3ccncc3)cc2)CC1", score: 0.7712 },
  { smiles: "OCc1ccc(-c2cnc3[nH]ccc3c2)cc1", score: 0.7603 },
];

// running-state top-K: fewer improvements settled, lower scores
const TOP_K_RUNNING: TopMolecule[] = [
  { smiles: "COc1ccc(CNc2ncnc3[nH]ccc23)cc1", score: 0.7431 },
  { smiles: "O=C(Nc1ccc(F)cc1)c1ccc2[nH]ncc2c1", score: 0.7218 },
  { smiles: "Cc1cc(Nc2ncnc3sccc23)ccc1Cl", score: 0.7104 },
  { smiles: "O=C(Nc1cccnc1)c1ccc2nc[nH]c2c1", score: 0.6890 },
  { smiles: "Clc1ccc(-c2nc3ccccc3[nH]2)cc1", score: 0.6742 },
  { smiles: "COc1ccc2nc(N)sc2c1C(=O)Nc1ccccc1", score: 0.6633 },
  { smiles: "CN1CCN(c2ccc(NC(=O)c3ccncc3)cc2)CC1", score: 0.6501 },
  { smiles: "OCc1ccc(-c2cnc3[nH]ccc3c2)cc1", score: 0.6398 },
  { smiles: "O=C(Nc1ccc(Cl)cc1)c1cc2ccccc2[nH]1", score: 0.6287 },
  { smiles: "CCOc1ccc(Nc2ncnc3cc[nH]c23)cc1", score: 0.6154 },
];

// index (0-based) of rows that improved this generation — mark with a badge
export const IMPROVED_ROWS_COMPLETED = new Set([0, 1, 4]);
export const IMPROVED_ROWS_RUNNING = new Set([0, 2]);

const AUC_COMPLETED: CurvePoint[] = [
  { oracle_calls: 100, top10_mean: 0.42 },
  { oracle_calls: 320, top10_mean: 0.58 },
  { oracle_calls: 800, top10_mean: 0.69 },
  { oracle_calls: 2000, top10_mean: 0.78 },
  { oracle_calls: 3600, top10_mean: 0.82 },
  { oracle_calls: 5000, top10_mean: 0.85 },
  { oracle_calls: 7200, top10_mean: 0.868 },
  { oracle_calls: 10000, top10_mean: 0.8814 },
];

const AUC_RUNNING: CurvePoint[] = [
  { oracle_calls: 100, top10_mean: 0.41 },
  { oracle_calls: 320, top10_mean: 0.55 },
  { oracle_calls: 800, top10_mean: 0.64 },
  { oracle_calls: 1600, top10_mean: 0.70 },
  { oracle_calls: 2800, top10_mean: 0.726 },
  { oracle_calls: 4200, top10_mean: 0.7431 },
];

// Analyzer hypotheses (an edited "highlights" view — the analyzer runs after every
// generation, but the UI surfaces the milestone ones). Each state's latest entry
// aligns with its current generation: running is at gen 10 (latest after gen 9),
// completed ran to gen 23 (latest after gen 22).
const HYP_TEXT = {
  hinge: {
    text: "Polar aromatic cores with an H-bond donor near the hinge lift the score; small, flat scaffolds cluster near the bottom.",
    structured_json: {
      focus: "aminopyrimidine hinge binder",
      avoid: ["long alkyl chains"],
    },
  },
  anilide: {
    text: "Fluorinated anilides held the top of the population; para-substitution correlated with the largest gen-over-gen gains.",
    structured_json: {
      focus: "para-F anilide",
      avoid: ["phenol", "free carboxylic acid"],
    },
  },
  bicyclic: {
    text: "Fused bicyclic heteroaromatics (benzimidazole, azaindole) outperformed single rings; the analyzer proposes concentrating there.",
    structured_json: {
      focus: "fused bicyclic heteroaromatic core",
      avoid: ["flexible linkers", "phenol"],
    },
  },
  halogen: {
    text: "Chloro/fluoro on the distal ring plus a basic amine tail is the current winning motif; exploration budget is shrinking as scores converge.",
    structured_json: {
      focus: "halogenated distal ring + basic amine",
      avoid: ["free carboxylic acid", "long alkyl chains"],
    },
  },
};

const HYPOTHESES_RUNNING: AnalyzerHypothesis[] = [
  { after_generation_index: 1, ...HYP_TEXT.hinge },
  { after_generation_index: 4, ...HYP_TEXT.anilide },
  { after_generation_index: 7, ...HYP_TEXT.bicyclic },
  { after_generation_index: 9, ...HYP_TEXT.halogen },
];

const HYPOTHESES_COMPLETED: AnalyzerHypothesis[] = [
  { after_generation_index: 1, ...HYP_TEXT.hinge },
  { after_generation_index: 8, ...HYP_TEXT.anilide },
  { after_generation_index: 15, ...HYP_TEXT.bicyclic },
  { after_generation_index: 22, ...HYP_TEXT.halogen },
];

// ── The two cockpit snapshots ───────────────────────────────────────────────

export const RUN_COMPLETED: RunSnapshot = {
  run_id: 281,
  task: "troglitazone_rediscovery",
  status: "exhausted",
  budget: 10000,
  plateau_window: 5,
  generation_index: 23,
  oracle_calls_used: 10000,
  best_score: 0.8814,
  top_k: TOP_K,
  auc_curve: AUC_COMPLETED,
  cost_so_far_usd: 2.4137,
  hypotheses: HYPOTHESES_COMPLETED,
  trace_url: "https://langfuse.example/trace/281",
};

export const RUN_RUNNING: RunSnapshot = {
  run_id: 284,
  task: "troglitazone_rediscovery",
  status: "running",
  budget: 10000,
  plateau_window: 5,
  generation_index: 10,
  oracle_calls_used: 4200,
  best_score: 0.7431,
  top_k: TOP_K_RUNNING,
  auc_curve: AUC_RUNNING,
  cost_so_far_usd: 1.0362,
  hypotheses: HYPOTHESES_RUNNING,
  trace_url: "https://langfuse.example/trace/284",
};

// Graph-GA reference (in-silico) baseline AUC of top-10 for this task — the
// locked product decision (b) renders this as a horizontal reference line + a
// live "beating by +X / behind by X" delta badge (NOT a GA curve).
export const GA_BASELINE_AUC = 0.7712;

// mock strategy + valid-SMILES rate (not carried in RunSnapshot payload today)
export const RUN_STRATEGY = "LLM proposer";
export const VALID_SMILES_RATE_RUNNING = 0.91;
export const VALID_SMILES_RATE_COMPLETED = 0.93;

// ── Recent runs stub for the Overview rigor strip ──────────────────────────

export const RECENT_RUNS: RunListItem[] = [
  {
    run_id: 284,
    task: "troglitazone_rediscovery",
    mutation_strategy: "llm",
    status: "running",
    best_score: 0.7431,
    oracle_calls: 4200,
    budget: 10000,
    started_at: "",
  },
  {
    run_id: 281,
    task: "troglitazone_rediscovery",
    mutation_strategy: "llm",
    status: "exhausted",
    best_score: 0.8814,
    oracle_calls: 10000,
    budget: 10000,
    started_at: "",
  },
  {
    run_id: 277,
    task: "jnk3",
    mutation_strategy: "llm",
    status: "exhausted",
    best_score: 0.8812,
    oracle_calls: 10000,
    budget: 10000,
    started_at: "",
  },
  {
    run_id: 271,
    task: "qed",
    mutation_strategy: "graph_ga",
    status: "plateaued",
    best_score: 0.9377,
    oracle_calls: 3400,
    budget: 10000,
    started_at: "",
  },
];

// The 5 loop steps; `analyze` is the differentiator (MOLLEO lacks it).
export const LOOP_STEPS = [
  { key: "propose", label: "Propose" },
  { key: "score", label: "Score" },
  { key: "analyze", label: "Analyze" },
  { key: "redesign", label: "Redesign" },
  { key: "stop", label: "Stop" },
] as const;
