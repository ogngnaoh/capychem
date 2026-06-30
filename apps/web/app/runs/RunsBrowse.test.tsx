import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RunListItem } from "@/lib/api";

const listRuns = vi.fn();
vi.mock("@/lib/api", () => ({ listRuns: (...a: unknown[]) => listRuns(...a) }));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { RunsBrowse } from "./RunsBrowse";

const ROWS: RunListItem[] = [
  {
    run_id: 1,
    task: "jnk3",
    mutation_strategy: "llm",
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
    status: "exhausted",
    best_score: 0.88,
    oracle_calls: 200,
    budget: 200,
    started_at: "2026-06-30T10:00:00Z",
  },
];

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

  it("re-fetches filtered by status when the status select changes", async () => {
    render(<RunsBrowse />);
    await waitFor(() => screen.getByText("jnk3"));
    fireEvent.change(screen.getByLabelText(/status filter/i), {
      target: { value: "running" },
    });
    await waitFor(() =>
      expect(listRuns).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "running" }),
      ),
    );
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
