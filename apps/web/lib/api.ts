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

export async function stopRun(id: number): Promise<void> {
  const r = await fetch(`${API_URL}/runs/${id}/stop`, { method: "POST" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export function wsUrl(id: number): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/runs/${id}`;
}
