import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogGroup, IntentResolution } from "@/lib/api";

const getCatalog = vi.fn();
const resolveIntent = vi.fn();
const createRun = vi.fn();
vi.mock("@/lib/api", () => ({
  getCatalog: (...a: unknown[]) => getCatalog(...a),
  resolveIntent: (...a: unknown[]) => resolveIntent(...a),
  createRun: (...a: unknown[]) => createRun(...a),
  moleculeSvgUrl: (s: string) => `svg:${s}`,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { Launcher } from "./Launcher";

const CATALOG: CatalogGroup[] = [
  { group: "Drug-likeness", tasks: [{ name: "qed", description: "Overall drug-likeness." }] },
  {
    group: "Rediscovery & similarity",
    tasks: [
      {
        name: "troglitazone_rediscovery",
        description: "How closely a molecule recovers troglitazone.",
      },
    ],
  },
];

function resolution(over: Partial<IntentResolution>): IntentResolution {
  return {
    matched_task: "troglitazone_rediscovery",
    confidence: "high",
    closest_task: null,
    rationale: "matched",
    resolved_plan: {
      task: "troglitazone_rediscovery",
      budget: 10000,
      plateau_window: 5,
      mutation_strategy: "graph_ga",
      seed_smiles: null,
    },
    refusals: [],
    cost_usd: 0.0001,
    ...over,
  };
}

describe("Launcher", () => {
  beforeEach(() => {
    getCatalog.mockReset().mockResolvedValue(CATALOG);
    resolveIntent.mockReset();
    createRun.mockReset().mockResolvedValue({ run_id: 42 });
    push.mockClear();
  });

  it("picks a task from the catalog and starts a run with the LLM strategy default", async () => {
    render(<Launcher />);
    // catalog renders from getCatalog()
    await waitFor(() => screen.getByText("troglitazone_rediscovery"));
    fireEvent.click(screen.getByText("troglitazone_rediscovery"));
    // mirror strategy defaults to the LLM proposer
    const strategy = screen.getByLabelText(/^Strategy$/i) as HTMLSelectElement;
    expect(strategy.value).toBe("llm");
    fireEvent.click(screen.getByRole("button", { name: /^Start run$/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        task: "troglitazone_rediscovery",
        mutation_strategy: "llm",
        budget: 10000,
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/42"));
  });

  it("resolves an NL intent and mirrors the matched objective (strategy overridden to llm)", async () => {
    resolveIntent.mockResolvedValue(resolution({}));
    render(<Launcher />);
    await waitFor(() => screen.getByText("Objective catalog"));
    fireEvent.change(screen.getByLabelText(/Describe what you want/i), {
      target: { value: "recover a molecule like troglitazone" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Resolve$/i }));
    await waitFor(() => expect(resolveIntent).toHaveBeenCalledTimes(1));
    // matched confidence line + mirror objective
    await screen.findByText(/with high confidence/i);
    const strategy = screen.getByLabelText(/^Strategy$/i) as HTMLSelectElement;
    expect(strategy.value).toBe("llm");
  });

  it("parses the seed field into a list and includes it in the run body (FR-001)", async () => {
    render(<Launcher />);
    await waitFor(() => screen.getByText("troglitazone_rediscovery"));
    fireEvent.click(screen.getByText("troglitazone_rediscovery"));
    fireEvent.change(screen.getByLabelText(/Seed molecules/i), {
      target: { value: "CCO, CCN c1ccccc1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Start run$/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ seed_smiles: ["CCO", "CCN", "c1ccccc1"] }),
    );
  });

  it("omits seed_smiles when the seed field is empty", async () => {
    render(<Launcher />);
    await waitFor(() => screen.getByText("troglitazone_rediscovery"));
    fireEvent.click(screen.getByText("troglitazone_rediscovery"));
    fireEvent.click(screen.getByRole("button", { name: /^Start run$/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun.mock.calls[0][0].seed_smiles).toBeUndefined();
  });

  it("renders a grounded no-match refusal with the Start action disabled (FR-015)", async () => {
    resolveIntent.mockResolvedValue(
      resolution({
        matched_task: null,
        confidence: null,
        closest_task: "albuterol_similarity",
        rationale: "'dissolves in water' isn't a PMO oracle. Closest is albuterol_similarity.",
        resolved_plan: null,
      }),
    );
    render(<Launcher />);
    await waitFor(() => screen.getByText("Objective catalog"));
    fireEvent.change(screen.getByLabelText(/Describe what you want/i), {
      target: { value: "make it dissolve well in water" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Resolve$/i }));
    await screen.findByText(/No benchmark matches that objective/i);
    expect(screen.getByText(/isn't a PMO oracle/i)).toBeInTheDocument();
    // Start is disabled until a real objective resolves
    const start = screen.getByRole("button", { name: /^Start run$/i });
    expect(start).toBeDisabled();
    expect(createRun).not.toHaveBeenCalled();
  });
});
