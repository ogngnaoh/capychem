import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComparePayload, RunListItem } from "@/lib/api";

const getCompare = vi.fn();
const listRuns = vi.fn();
vi.mock("@/lib/api", () => ({
  getCompare: (...a: unknown[]) => getCompare(...a),
  listRuns: (...a: unknown[]) => listRuns(...a),
  moleculeSvgUrl: (s: string) => `svg:${s}`,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

// recharts needs a real width/height (0 in jsdom) — stub to render children only.
vi.mock("recharts", () => {
  const Pass = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Null = () => null;
  return {
    ResponsiveContainer: Pass,
    LineChart: Pass,
    Line: Null,
    XAxis: Null,
    YAxis: Null,
    CartesianGrid: Null,
    ReferenceLine: Null,
  };
});

import { CompareView } from "./CompareView";

const RUNS: RunListItem[] = [
  {
    run_id: 11,
    task: "jnk3",
    mutation_strategy: "llm",
    status: "exhausted",
    best_score: 0.8812,
    oracle_calls: 10000,
    budget: 10000,
    started_at: "2026-06-30T12:00:00Z",
  },
  {
    run_id: 9,
    task: "qed",
    mutation_strategy: "graph_ga",
    status: "plateaued",
    best_score: 0.9377,
    oracle_calls: 3400,
    budget: 10000,
    started_at: "2026-06-30T10:00:00Z",
  },
];

const PAYLOAD: ComparePayload = {
  a: {
    run_id: 11,
    task: "jnk3",
    status: "exhausted",
    best_score: 0.8812,
    oracle_calls: 10000,
    budget: 10000,
    cost_so_far_usd: 1.2345,
    top_k: [{ smiles: "CCOc1ccccc1", score: 0.8812 }],
    hypotheses: [
      {
        after_generation_index: 2,
        text: "refine amide scaffold",
        structured_json: { focus: "amide", avoid: ["phenol"] },
      },
    ],
  },
  b: {
    run_id: 9,
    task: "qed",
    status: "plateaued",
    best_score: 0.9377,
    oracle_calls: 3400,
    budget: 10000,
    cost_so_far_usd: 0.0,
    top_k: [{ smiles: "c1ccccc1O", score: 0.9377 }],
    hypotheses: [],
  },
  auc_overlay: [
    { oracle_calls: 32, a: 0.5, b: null },
    { oracle_calls: 64, a: 0.7, b: 0.4 },
  ],
};

describe("CompareView", () => {
  beforeEach(() => {
    getCompare.mockReset().mockResolvedValue(PAYLOAD);
    listRuns.mockReset().mockResolvedValue(RUNS);
    push.mockClear();
  });

  it("fetches the two runs and renders both identities, top-K, cost, and the analyzer split", async () => {
    render(<CompareView a={11} b={9} />);
    await waitFor(() => expect(screen.getAllByText(/jnk3/).length).toBeGreaterThan(0));
    expect(getCompare).toHaveBeenCalledWith(11, 9);
    // both runs identified
    expect(screen.getAllByText(/qed/).length).toBeGreaterThan(0);
    // side-by-side top-K
    expect(screen.getByText("CCOc1ccccc1")).toBeInTheDocument();
    expect(screen.getByText("c1ccccc1O")).toBeInTheDocument();
    // per-run cost surfaced (FR-013), now formatted to 2dp
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    // the analyzer story: LLM run has a hypothesis, GA run shows "no analyzer step"
    expect(screen.getByText(/1 analyzer hypothesis/i)).toBeInTheDocument();
    expect(screen.getByText(/no analyzer step/i)).toBeInTheDocument();
  });

  it("routes to a new comparison when a run selector changes", async () => {
    render(<CompareView a={11} b={9} />);
    await waitFor(() => expect(screen.getAllByText(/jnk3/).length).toBeGreaterThan(0));
    const selectA = screen.getByRole("combobox", { name: /Run A/i });
    // change Run A to run 9 → /compare?a=9&b=9
    fireEvent.change(selectA, { target: { value: "9" } });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/compare?a=9&b=9"));
  });

  it("guards against missing run ids without fetching", () => {
    render(<CompareView a={Number.NaN} b={9} />);
    expect(getCompare).not.toHaveBeenCalled();
    expect(screen.getByText(/select two runs/i)).toBeInTheDocument();
  });
});
