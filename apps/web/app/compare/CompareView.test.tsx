import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComparePayload } from "@/lib/api";

const getCompare = vi.fn();
vi.mock("@/lib/api", () => ({ getCompare: (...a: unknown[]) => getCompare(...a) }));

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
    Legend: Null,
    Tooltip: Null,
  };
});

import { CompareView } from "./CompareView";

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
    getCompare.mockReset();
    getCompare.mockResolvedValue(PAYLOAD);
  });

  it("fetches the two runs and renders both identities, top-K, cost, and hypotheses", async () => {
    render(<CompareView a={11} b={9} />);
    await waitFor(() => expect(screen.getAllByText(/jnk3/).length).toBeGreaterThan(0));
    expect(getCompare).toHaveBeenCalledWith(11, 9);
    // both runs identified
    expect(screen.getAllByText(/qed/).length).toBeGreaterThan(0);
    // side-by-side top-K
    expect(screen.getByText("CCOc1ccccc1")).toBeInTheDocument();
    expect(screen.getByText("c1ccccc1O")).toBeInTheDocument();
    // per-run cost surfaced (FR-013)
    expect(screen.getByText("1.2345")).toBeInTheDocument();
    // hypothesis sequence for run a
    expect(screen.getByText("refine amide scaffold")).toBeInTheDocument();
    expect(screen.getByText("focus: amide")).toBeInTheDocument();
  });

  it("guards against missing run ids without fetching", () => {
    render(<CompareView a={Number.NaN} b={9} />);
    expect(getCompare).not.toHaveBeenCalled();
    expect(screen.getByText(/select two runs/i)).toBeInTheDocument();
  });
});
