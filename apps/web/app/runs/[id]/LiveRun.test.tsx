import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { RunSnapshot } from "@/lib/api";

const getRun = vi.fn();
vi.mock("@/lib/api", () => ({
  getRun: (...a: unknown[]) => getRun(...a),
  stopRun: vi.fn(),
  wsUrl: (id: number) => `ws://test/ws/runs/${id}`,
}));

// recharts needs ResizeObserver (absent in jsdom); stub it so we test the header.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

import { LiveRun } from "./LiveRun";

function terminalSnap(over: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    run_id: 271,
    task: "qed",
    status: "max_generations", // terminal → no WebSocket opened
    budget: 120,
    plateau_window: 5,
    generation_index: 8,
    oracle_calls_used: 80,
    best_score: 0.9455,
    top_k: [{ smiles: "CCO", score: 0.9455 }],
    auc_curve: [{ oracle_calls: 80, top10_mean: 0.94 }],
    cost_so_far_usd: 0.0149,
    hypotheses: [],
    ...over,
  };
}

describe("LiveRun trace link (FR-014)", () => {
  it("links out to the Langfuse trace when trace_url is present", async () => {
    getRun.mockResolvedValue(
      terminalSnap({ trace_url: "http://localhost:3001/project/p/traces/t" }),
    );
    render(<LiveRun runId={271} />);
    const link = await screen.findByRole("link", { name: /view trace/i });
    expect(link).toHaveAttribute("href", "http://localhost:3001/project/p/traces/t");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows no trace link when trace_url is absent", async () => {
    getRun.mockResolvedValue(terminalSnap({ trace_url: null }));
    render(<LiveRun runId={271} />);
    await screen.findByText(/Run 271/);
    expect(screen.queryByRole("link", { name: /view trace/i })).toBeNull();
  });
});
