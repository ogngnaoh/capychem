import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogGroup, ObjectiveValidateResponse } from "@/lib/api";

const validateObjective = vi.fn<
  (spec: unknown, smiles: string[]) => Promise<ObjectiveValidateResponse>
>();
vi.mock("@/lib/api", () => ({
  validateObjective: (...a: [unknown, string[]]) => validateObjective(...a),
}));

import { ObjectiveBuilder, type ObjectiveDraft } from "./ObjectiveBuilder";

const CATALOG: CatalogGroup[] = [
  { group: "Target activity", tasks: [{ name: "jnk3", description: "JNK3" }] },
];

describe("ObjectiveBuilder", () => {
  beforeEach(() => {
    validateObjective.mockReset().mockResolvedValue({
      aggregator: "weighted_sum",
      n_terms: 1,
      results: [{ smiles: "CCO", score: 0.5 }],
    });
  });

  it("emits a single-term draft on mount (blocker null)", async () => {
    const onChange = vi.fn<(d: ObjectiveDraft) => void>();
    render(<ObjectiveBuilder catalog={CATALOG} onChange={onChange} />);
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const draft = onChange.mock.calls.at(-1)![0];
    expect(draft.blocker).toBeNull();
    expect(draft.objectiveJson.terms).toHaveLength(1);
    expect(draft.objectiveJson.terms[0].oracle).toBe("qed");
  });

  it("composes a second term with a reverse_sigmoid transform into objective_json", async () => {
    const onChange = vi.fn<(d: ObjectiveDraft) => void>();
    render(<ObjectiveBuilder catalog={CATALOG} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Add term/i }));
    const oracleSelects = screen.getAllByLabelText(/Oracle for term/i);
    expect(oracleSelects).toHaveLength(2);
    // Switch the second term to SA score → it re-seats to reverse_sigmoid (lower is better).
    fireEvent.change(oracleSelects[1], { target: { value: "sa_score" } });

    await waitFor(() => {
      const draft = onChange.mock.calls.at(-1)![0];
      expect(draft.objectiveJson.terms).toHaveLength(2);
      expect(draft.objectiveJson.terms[1]).toMatchObject({
        oracle: "sa_score",
        transform: { kind: "reverse_sigmoid" },
        oracle_kwargs: {},
      });
      expect(draft.blocker).toBeNull();
    });
  });

  it("blocks launch until a PMO term gets a task, then carries oracle_kwargs.task", async () => {
    const onChange = vi.fn<(d: ObjectiveDraft) => void>();
    render(<ObjectiveBuilder catalog={CATALOG} onChange={onChange} />);
    const oracleSelect = screen.getAllByLabelText(/Oracle for term/i)[0];
    fireEvent.change(oracleSelect, { target: { value: "pmo" } });
    await waitFor(() => {
      expect(onChange.mock.calls.at(-1)![0].blocker).toMatch(/pmo task/i);
    });
    fireEvent.change(screen.getByLabelText(/PMO task for term 1/i), {
      target: { value: "jnk3" },
    });
    await waitFor(() => {
      const draft = onChange.mock.calls.at(-1)![0];
      expect(draft.blocker).toBeNull();
      expect(draft.objectiveJson.terms[0].oracle_kwargs).toEqual({ task: "jnk3" });
      expect(draft.representativeTask).toBe("jnk3");
    });
  });
});
