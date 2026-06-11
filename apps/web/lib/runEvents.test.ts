import { describe, expect, it } from "vitest";
import { applyEvent } from "./runEvents";
import type { RunSnapshot } from "./api";

const base: RunSnapshot = {
  run_id: 1, task: "qed", status: "running", budget: 100,
  generation_index: 0, oracle_calls_used: 0, best_score: null,
  top_k: [], auc_curve: [],
};

describe("applyEvent", () => {
  it("ping is a no-op", () => {
    expect(applyEvent(base, { type: "ping" })).toBe(base);
  });
  it("generation.complete updates counters/best_score/top_k and appends a top10_mean curve point", () => {
    const next = applyEvent(base, {
      type: "generation.complete", generation_index: 1, best_score: 0.7,
      top10_mean: 0.55, oracle_calls_used: 20, top_k: [{ smiles: "CCO", score: 0.7 }],
    });
    expect(next.generation_index).toBe(1);
    expect(next.oracle_calls_used).toBe(20);
    expect(next.best_score).toBe(0.7);
    expect(next.top_k).toEqual([{ smiles: "CCO", score: 0.7 }]);
    // The curve point's top10_mean uses ev.top10_mean (0.55), NOT best_score (0.7).
    expect(next.auc_curve).toEqual([{ oracle_calls: 20, top10_mean: 0.55 }]);
  });
  it("run.complete sets terminal status", () => {
    const next = applyEvent(base, { type: "run.complete", run_id: 1, status: "stopped", summary: null });
    expect(next.status).toBe("stopped");
  });
  it("generation.complete carries cost_so_far_usd into the snapshot", () => {
    const next = applyEvent(base, {
      type: "generation.complete", generation_index: 1, best_score: 0.7,
      top10_mean: 0.55, oracle_calls_used: 20, cost_so_far_usd: 0.42,
      top_k: [{ smiles: "CCO", score: 0.7 }],
    });
    expect(next.cost_so_far_usd).toBe(0.42);
  });
  it("run.complete carries a cost_capped terminal status", () => {
    const next = applyEvent(base, { type: "run.complete", run_id: 1, status: "cost_capped", summary: null });
    expect(next.status).toBe("cost_capped");
  });
  it("generation.complete without cost preserves the prior snapshot cost", () => {
    const seeded = { ...base, cost_so_far_usd: 0.5 };
    const next = applyEvent(seeded, {
      type: "generation.complete", generation_index: 2, best_score: 0.8,
      top10_mean: 0.6, oracle_calls_used: 40, top_k: [],
    });
    expect(next.cost_so_far_usd).toBe(0.5);
  });
  it("does not mutate the input snapshot (purity)", () => {
    const snapshot = { ...base, auc_curve: [] as RunSnapshot["auc_curve"] };
    applyEvent(snapshot, {
      type: "generation.complete", generation_index: 1, best_score: 0.7,
      top10_mean: 0.55, oracle_calls_used: 20, top_k: [],
    });
    expect(snapshot.auc_curve).toEqual([]); // original untouched
    expect(snapshot.generation_index).toBe(0);
  });
});
