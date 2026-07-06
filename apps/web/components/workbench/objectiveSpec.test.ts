import { describe, expect, it } from "vitest";
import {
  newTerm,
  representativeTask,
  retargetTerm,
  specBlocker,
  toConstraintsJson,
  toObjectiveJson,
  type UiTerm,
} from "./objectiveSpec";

describe("toObjectiveJson", () => {
  it("composes a two-term weighted-sum objective into the backend shape", () => {
    const qed: UiTerm = { ...newTerm("qed"), weight: 2 };
    const sa: UiTerm = {
      ...newTerm("sa_score"),
      weight: 1,
      transformKind: "reverse_sigmoid",
      low: 2,
      high: 5,
      k: 10,
    };
    const spec = toObjectiveJson([qed, sa], "weighted_sum");
    expect(spec.aggregator).toBe("weighted_sum");
    expect(spec.terms).toEqual([
      { oracle: "qed", weight: 2, transform: { kind: "identity" }, oracle_kwargs: {} },
      {
        oracle: "sa_score",
        weight: 1,
        transform: { kind: "reverse_sigmoid", low: 2, high: 5, k: 10 },
        oracle_kwargs: {},
      },
    ]);
  });

  it("carries oracle_kwargs.task for a pmo term", () => {
    const pmo = retargetTerm(newTerm("qed"), "pmo");
    const spec = toObjectiveJson([{ ...pmo, task: "jnk3" }], "weighted_product");
    expect(spec.aggregator).toBe("weighted_product");
    expect(spec.terms[0]).toMatchObject({ oracle: "pmo", oracle_kwargs: { task: "jnk3" } });
  });

  it("emits value_map points parsed from the text field", () => {
    const t: UiTerm = { ...newTerm("clogp"), transformKind: "value_map", points: "0, 0\n2, 1\n5, 0" };
    const spec = toObjectiveJson([t], "weighted_sum");
    expect(spec.terms[0].transform).toEqual({
      kind: "value_map",
      points: [
        [0, 0],
        [2, 1],
        [5, 0],
      ],
    });
  });
});

describe("toConstraintsJson", () => {
  it("returns undefined when nothing is constrained", () => {
    expect(toConstraintsJson([], [""], ["  "])).toBeUndefined();
  });

  it("includes only the non-empty keys", () => {
    expect(toConstraintsJson(["PAINS"], ["[N+](=O)[O-]", ""], [])).toEqual({
      catalogs: ["PAINS"],
      smarts_exclude: ["[N+](=O)[O-]"],
    });
  });
});

describe("specBlocker", () => {
  it("blocks an empty term list", () => {
    expect(specBlocker([])).toMatch(/at least one/i);
  });

  it("blocks a non-positive weight", () => {
    expect(specBlocker([{ ...newTerm("qed"), weight: 0 }])).toMatch(/positive/i);
  });

  it("blocks a pmo term with no task chosen", () => {
    const pmo = retargetTerm(newTerm("qed"), "pmo");
    expect(specBlocker([pmo])).toMatch(/pmo task/i);
  });

  it("passes a well-formed spec", () => {
    expect(specBlocker([newTerm("qed")])).toBeNull();
  });
});

describe("representativeTask", () => {
  it("uses the first pmo term's task, else a safe default", () => {
    expect(representativeTask([newTerm("qed")])).toBe("qed");
    const pmo = { ...retargetTerm(newTerm("qed"), "pmo"), task: "drd2" };
    expect(representativeTask([newTerm("qed"), pmo])).toBe("drd2");
  });
});

describe("retargetTerm", () => {
  it("re-seats transform defaults when the oracle changes", () => {
    const t = retargetTerm(newTerm("qed"), "mw");
    expect(t.oracle).toBe("mw");
    expect(t.transformKind).toBe("double_sigmoid");
    expect(t.low).toBe(250);
    expect(t.high).toBe(500);
  });
});
