import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogGroup, RunListItem } from "@/lib/api";

const getCatalog = vi.fn();
const listRuns = vi.fn();
vi.mock("@/lib/api", () => ({
  getCatalog: (...a: unknown[]) => getCatalog(...a),
  listRuns: (...a: unknown[]) => listRuns(...a),
  moleculeSvgUrl: (s: string) => `svg:${s}`,
}));

import { Overview } from "./Overview";

const CATALOG: CatalogGroup[] = [
  { group: "Drug-likeness", tasks: [{ name: "qed", description: "Overall drug-likeness." }] },
  {
    group: "Target activity",
    tasks: [
      { name: "drd2", description: "Dopamine D2." },
      { name: "jnk3", description: "JNK3 kinase." },
      { name: "gsk3b", description: "GSK-3β." },
      { name: "extra", description: "spillover" },
    ],
  },
];

const RECENT: RunListItem[] = [
  {
    run_id: 284,
    task: "troglitazone_rediscovery",
    mutation_strategy: "llm",
    mode: "benchmark",
    status: "running",
    best_score: 0.7431,
    oracle_calls: 4200,
    budget: 10000,
    started_at: "2026-07-02T09:48:00Z",
  },
];

describe("Overview", () => {
  beforeEach(() => {
    getCatalog.mockReset().mockResolvedValue(CATALOG);
    listRuns.mockReset().mockResolvedValue(RECENT);
  });

  it("renders the hero, the loop, and the verbatim benchmark figure canon (in-silico, honest)", async () => {
    render(<Overview />);
    expect(screen.getByText(/in as few oracle calls as possible/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^The loop$/i })).toBeInTheDocument();
    // figure canon must be verbatim + honest (never "21/23", never efficacy)
    expect(screen.getByText(/all 21 comparable PMO tasks/i)).toBeInTheDocument();
    expect(screen.getByText(/decisive \(~0\.1 AUC\+\) on 9/i)).toBeInTheDocument();
    expect(screen.queryByText(/21\/23/)).toBeNull();
  });

  it("lists recent runs from listRuns() and the catalog peek from getCatalog()", async () => {
    render(<Overview />);
    // The task now appears in both the hero latest-run peek and the recent-runs list.
    await waitFor(() => expect(screen.getAllByText("troglitazone_rediscovery").length).toBeGreaterThan(0));
    // catalog peek group + a task chip
    expect(screen.getByText("Drug-likeness")).toBeInTheDocument();
    expect(screen.getByText("qed")).toBeInTheDocument();
    // "See all N objectives" reflects the fetched task count (1 + 4 = 5)
    expect(screen.getByText(/See all 5 objectives/i)).toBeInTheDocument();
  });

  it("badges each recent run's mode", async () => {
    render(<Overview />);
    await waitFor(() => expect(screen.getAllByText("troglitazone_rediscovery").length).toBeGreaterThan(0));
    // Benchmark badge renders in both the hero peek and the recent-runs row.
    expect(screen.getAllByText(/^Benchmark$/).length).toBeGreaterThan(0);
  });
});
