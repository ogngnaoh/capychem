import type { RunSnapshot, TopMolecule } from "./api";

export type RunEvent =
  | { type: "ping" }
  | {
      type: "generation.complete";
      generation_index: number;
      best_score: number;
      top10_mean: number;
      oracle_calls_used: number;
      top_k: TopMolecule[];
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
        auc_curve: [
          ...snap.auc_curve,
          { oracle_calls: ev.oracle_calls_used, top10_mean: ev.top10_mean },
        ],
      };
    case "run.complete":
      return { ...snap, status: ev.status };
    default:
      return snap;
  }
}
