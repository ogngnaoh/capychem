import type { AnalyzerHypothesis, RunSnapshot, TopMolecule } from "./api";

export type RunEvent =
  | { type: "ping" }
  | {
      type: "generation.complete";
      generation_index: number;
      best_score: number;
      top10_mean: number;
      oracle_calls_used: number;
      cost_so_far_usd?: number;
      top_k: TopMolecule[];
    }
  | {
      type: "analyzer.hypothesis";
      after_generation_index: number;
      text: string;
      structured_json: { focus?: string; avoid?: string[] } | null;
    }
  | { type: "run.complete"; run_id: number; status: string; summary: unknown };

export function applyEvent(snap: RunSnapshot, ev: RunEvent): RunSnapshot {
  switch (ev.type) {
    case "ping":
      return snap;
    case "generation.complete":
      return {
        ...snap,
        generation_index: ev.generation_index,
        oracle_calls_used: ev.oracle_calls_used,
        best_score: ev.best_score,
        top_k: ev.top_k,
        cost_so_far_usd: ev.cost_so_far_usd ?? snap.cost_so_far_usd,
        auc_curve: [
          ...snap.auc_curve,
          { oracle_calls: ev.oracle_calls_used, top10_mean: ev.top10_mean },
        ],
      };
    case "analyzer.hypothesis": {
      const rec: AnalyzerHypothesis = {
        after_generation_index: ev.after_generation_index,
        text: ev.text,
        structured_json: ev.structured_json,
      };
      const kept = (snap.hypotheses ?? []).filter(
        (h) => h.after_generation_index !== ev.after_generation_index,
      );
      return {
        ...snap,
        hypotheses: [...kept, rec].sort(
          (a, b) => a.after_generation_index - b.after_generation_index,
        ),
      };
    }
    case "run.complete":
      return { ...snap, status: ev.status };
    default:
      return snap;
  }
}
