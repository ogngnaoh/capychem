import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RunListItem } from "@/lib/api";

const listRuns = vi.fn();
vi.mock("@/lib/api", () => ({ listRuns: (...a: unknown[]) => listRuns(...a) }));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { formatRelativeTime, RunsBrowse } from "./RunsBrowse";

const ROWS: RunListItem[] = [
  {
    run_id: 1,
    task: "jnk3",
    mutation_strategy: "llm",
    mode: "benchmark",
    status: "running",
    best_score: 0.51,
    oracle_calls: 120,
    budget: 200,
    started_at: "2026-06-30T12:00:00Z",
  },
  {
    run_id: 2,
    task: "qed",
    mutation_strategy: "graph_ga",
    mode: "exploratory",
    status: "exhausted",
    best_score: 0.88,
    oracle_calls: 200,
    budget: 200,
    started_at: "2026-06-30T10:00:00Z",
  },
];

describe("formatRelativeTime", () => {
  it("pins timezone-naive ISO strings (the API's UTC serialization) to UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-30T14:00:00Z"));
    try {
      // A bare string must read as UTC — identical to the same instant with an
      // explicit Z — in every browser timezone, not as local time.
      expect(formatRelativeTime("2026-06-30T12:00:00")).toBe("2h ago");
      expect(formatRelativeTime("2026-06-30T12:00:00")).toBe(
        formatRelativeTime("2026-06-30T12:00:00Z"),
      );
      // An explicit offset is respected, never double-shifted.
      expect(formatRelativeTime("2026-06-30T09:00:00-04:00")).toBe("1h ago");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("RunsBrowse", () => {
  beforeEach(() => {
    listRuns.mockReset();
    listRuns.mockResolvedValue(ROWS);
    push.mockClear();
  });

  it("fetches with the default sort (started_at desc) and renders a row per run", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    expect(screen.getByText("qed")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(listRuns).toHaveBeenCalledWith(
      expect.objectContaining({ sort: "started_at", order: "desc" }),
    );
  });

  it("re-fetches sorted by best_score when that header is clicked", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    fireEvent.click(screen.getByRole("button", { name: /best score/i }));
    await waitFor(() =>
      expect(listRuns).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "best_score" }),
      ),
    );
  });

  it("re-fetches filtered by status when a status pill is clicked", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    // pills are derived from the statuses seen (running, exhausted) + "all"
    fireEvent.click(screen.getByRole("button", { name: /^running$/i }));
    await waitFor(() =>
      expect(listRuns).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "running" }),
      ),
    );
  });

  it("badges each row's mode; exploratory keeps not-benchmark-comparable in its title", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    expect(screen.getByText(/^Benchmark$/)).toBeInTheDocument(); // run 1
    // The dense table uses the compact badge ("Exploratory"); the full honesty clause
    // stays in its title tooltip so the claim never disappears.
    const exploratory = screen.getByText(/^Exploratory$/); // run 2
    expect(exploratory).toBeInTheDocument();
    expect(exploratory).toHaveAttribute("title", expect.stringMatching(/not benchmark-comparable/i));
  });

  it("navigates to the run detail when a row is clicked", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    fireEvent.click(screen.getByText("jnk3"));
    expect(push).toHaveBeenCalledWith("/runs/1");
  });

  it("enables Compare only when exactly two runs are selected", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    const compare = screen.getByRole("button", { name: /compare/i });
    expect(compare).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/select run 1/i));
    expect(compare).toBeDisabled(); // only one selected
    fireEvent.click(screen.getByLabelText(/select run 2/i));
    expect(compare).not.toBeDisabled(); // exactly two selected
  });

  it("navigates to /compare with both selected run ids when Compare is clicked", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    fireEvent.click(screen.getByLabelText(/select run 1/i));
    fireEvent.click(screen.getByLabelText(/select run 2/i));
    fireEvent.click(screen.getByRole("button", { name: /compare/i }));
    expect(push).toHaveBeenCalledWith("/compare?a=1&b=2");
  });
});
