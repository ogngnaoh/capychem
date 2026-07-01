const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TopMolecule = { smiles: string; score: number };
export type CurvePoint = { oracle_calls: number; top10_mean: number };
export type AnalyzerHypothesis = {
  after_generation_index: number;
  text: string;
  structured_json: { focus?: string; avoid?: string[] } | null;
};
export type RunSnapshot = {
  run_id: number;
  task: string;
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
};
export type RunListItem = {
  run_id: number;
  task: string;
  mutation_strategy: string;
  status: string;
  best_score: number | null;
  oracle_calls: number;
  budget: number;
  started_at: string;
};
export type CompareRun = {
  run_id: number;
  task: string;
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
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join("; ")
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

export function wsUrl(id: number): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/runs/${id}`;
}
