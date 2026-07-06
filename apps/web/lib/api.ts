const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type MoleculeQuality = {
  valid: boolean;
  sa_score?: number;
  qed?: number;
  mw?: number;
  logp?: number;
  hbd?: number;
  hba?: number;
  rotatable_bonds?: number;
  tpsa?: number;
  lipinski_pass?: boolean;
  veber_pass?: boolean;
  pains?: boolean;
  brenk?: boolean;
};
// quality is populated at finalize (07-05/07-08); null on a live snapshot.
export type TopMolecule = { smiles: string; score: number; quality?: MoleculeQuality | null };
export type CurvePoint = { oracle_calls: number; top10_mean: number };
export type AnalyzerHypothesis = {
  after_generation_index: number;
  text: string;
  structured_json: { focus?: string; avoid?: string[] } | null;
};
export type RunSnapshot = {
  run_id: number;
  task: string;
  mode: string; // "benchmark" | "exploratory" (07-01); server-derived, gates graph_ga_baseline
  status: string;
  budget: number;
  plateau_window: number;
  generation_index: number;
  oracle_calls_used: number;
  best_score: number | null;
  top_k: TopMolecule[];
  auc_curve: CurvePoint[];
  cost_so_far_usd?: number;
  hypotheses?: AnalyzerHypothesis[];
  trace_url?: string | null;
  // Workbench read-fields (milestone 05 slice 03a), all nullable/additive.
  valid_smiles_rate?: number | null;
  graph_ga_baseline?: number | null;
  llm_cost_usd?: number | null;
  oracle_cost_usd?: number | null;
  // Run-level trust metrics (07-08); populated at finalize.
  diversity?: number | null;
  novelty?: number | null;
};
export type RunListItem = {
  run_id: number;
  task: string;
  mutation_strategy: string;
  mode: string; // "benchmark" | "exploratory" (07-01)
  status: string;
  best_score: number | null;
  oracle_calls: number;
  budget: number;
  started_at: string;
};
export type CompareRun = {
  run_id: number;
  task: string;
  mode: string; // "benchmark" | "exploratory" (07-01)
  status: string;
  best_score: number | null;
  oracle_calls: number;
  budget: number;
  cost_so_far_usd: number;
  top_k: TopMolecule[];
  hypotheses: AnalyzerHypothesis[];
};
export type AucOverlayPoint = {
  oracle_calls: number;
  a: number | null;
  b: number | null;
};
export type ComparePayload = {
  a: CompareRun;
  b: CompareRun;
  auc_overlay: AucOverlayPoint[];
};
export type CatalogTask = { name: string; description: string };
export type CatalogGroup = { group: string; tasks: CatalogTask[] };

export type Refusal = { field: string; reason: string };
export type ResolvedPlan = {
  task: string;
  budget: number;
  plateau_window: number;
  mutation_strategy: string;
  seed_smiles?: string | null;
};
export type IntentResolution = {
  matched_task: string | null;
  confidence: "high" | "medium" | "low" | null;
  closest_task: string | null;
  rationale: string;
  resolved_plan: ResolvedPlan | null;
  refusals: Refusal[];
  cost_usd: number;
};

// Composed multi-term objective (07-04). Mirrors packages/core ObjectiveSpec.to_json:
// each term = an oracle + positive weight + a [0,1] transform + oracle_kwargs (pmo
// needs {task}). A non-null objective_json marks the run exploratory server-side.
export type ObjectiveTermJson = {
  oracle: string;
  weight: number;
  transform: Record<string, unknown>;
  oracle_kwargs: Record<string, unknown>;
};
export type ObjectiveJson = { terms: ObjectiveTermJson[]; aggregator: string };
// Hard constraints (07-04b), all optional. Present ⇒ exploratory.
export type ConstraintsJson = {
  catalogs?: string[];
  smarts_exclude?: string[];
  smarts_include?: string[];
};
export type ObjectiveValidateResult = { smiles: string; score: number | null };
export type ObjectiveValidateResponse = {
  aggregator: string;
  n_terms: number;
  results: ObjectiveValidateResult[];
};

export type CreateRunBody = {
  task: string;
  budget: number;
  seed: number;
  pop_size: number;
  offspring: number;
  mutation_rate: number;
  plateau_window: number;
  max_generations: number;
  mutation_strategy: string;
  // Operator bring-your-own starting compounds (07-02, FR-001). A non-empty list
  // marks the run exploratory server-side. Distinct from the integer RNG `seed`.
  seed_smiles?: string[];
  // Composed objective + hard constraints (07-04/07-04b). Either present ⇒ the
  // server derives mode=exploratory (never client-set).
  objective_json?: ObjectiveJson;
  constraints_json?: ConstraintsJson;
};

export async function createRun(
  body: CreateRunBody,
): Promise<{ run_id: number }> {
  const r = await fetch(`${API_URL}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    // Pydantic v2 prefixes field-validator failures with "Value error, " — noise on an
    // operator surface. Strip it; the named-SMILES remainder that parseRejectedSeeds
    // reads ("…did not parse: […]") is untouched.
    const strip = (m: string) => m.replace(/^Value error, /, "");
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e: { msg?: string }) => strip(e.msg ?? JSON.stringify(e))).join("; ")
        : typeof detail === "string"
          ? strip(detail)
          : (detail ?? `HTTP ${r.status}`),
    );
  }
  return r.json();
}

export async function getRun(id: number): Promise<RunSnapshot> {
  const r = await fetch(`${API_URL}/runs/${id}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Live preview of a composed objective (07-04). POST /objective/validate scores each
// probe SMILES to a single composite [0,1] (null = the objective couldn't score it).
// A malformed spec is a 422 — surfaced to the builder as an error.
export async function validateObjective(
  spec: ObjectiveJson,
  smiles: string[],
): Promise<ObjectiveValidateResponse> {
  const r = await fetch(`${API_URL}/objective/validate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ spec, smiles }),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${r.status}`);
  }
  return r.json();
}

// Reproducibility manifest (07-06, OD-5): git SHA + model id + PyTDC pin + full launch
// config + trace URL. Empty object while a run is still live (written at finalize).
export async function getManifest(id: number): Promise<Record<string, unknown>> {
  const r = await fetch(`${API_URL}/runs/${id}/manifest`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Download URLs (07-06/07-07) — used as anchor hrefs so the browser streams the file
// body directly (manifest JSON + per-candidate lineage CSV/SDF).
export function manifestUrl(id: number): string {
  return `${API_URL}/runs/${id}/manifest`;
}
export function exportCsvUrl(id: number): string {
  return `${API_URL}/runs/${id}/export.csv`;
}
export function exportSdfUrl(id: number): string {
  return `${API_URL}/runs/${id}/export.sdf`;
}

export async function listRuns(
  params: { sort?: string; order?: string; status?: string; task?: string } = {},
): Promise<RunListItem[]> {
  const q = new URLSearchParams();
  if (params.sort) q.set("sort", params.sort);
  if (params.order) q.set("order", params.order);
  if (params.status) q.set("status", params.status);
  if (params.task) q.set("task", params.task);
  const qs = q.toString();
  const r = await fetch(`${API_URL}/runs${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function getCompare(a: number, b: number): Promise<ComparePayload> {
  const r = await fetch(`${API_URL}/compare?a=${a}&b=${b}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function stopRun(id: number): Promise<void> {
  const r = await fetch(`${API_URL}/runs/${id}/stop`, { method: "POST" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export async function resumeRun(id: number): Promise<void> {
  const r = await fetch(`${API_URL}/runs/${id}/resume`, { method: "POST" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export function wsUrl(id: number): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/runs/${id}`;
}

export async function getCatalog(): Promise<CatalogGroup[]> {
  const r = await fetch(`${API_URL}/catalog`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function resolveIntent(body: {
  text: string;
  budget?: number;
  seed_smiles?: string;
}): Promise<IntentResolution> {
  const r = await fetch(`${API_URL}/intent/resolve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function moleculeSvgUrl(smiles: string, w?: number, h?: number): string {
  const q = new URLSearchParams({ smiles });
  if (w) q.set("w", String(w));
  if (h) q.set("h", String(h));
  return `${API_URL}/molecule/svg?${q.toString()}`;
}
