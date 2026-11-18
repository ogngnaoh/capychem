import { displayNumber, failureLabel, type Candidate } from "./data";

/** Stable input order is intentional: this chooses inspectable evidence, not a winner. */
export function defaultCandidate(candidates: Candidate[]) {
  return (
    candidates.find((c) => c.reviewReady && c.structureId) ??
    candidates.find((c) => c.structureId) ??
    candidates[0]
  );
}

export type OutcomeFilter =
  | "all"
  | "ready"
  | "objective"
  | "review"
  | "unevaluated";
export function matchesOutcome(c: Candidate, filter: OutcomeFilter) {
  if (filter === "ready") return Boolean(c.reviewReady && c.structureId);
  if (filter === "objective") return Boolean(c.reviewReady && c.asp86Contact);
  if (filter === "review") return Boolean(c.structureId && !c.reviewReady);
  if (filter === "unevaluated") return !c.structureId;
  return true;
}

export function candidateStatus(c: Candidate) {
  if (c.origin === "observed") return "Observed reference";
  if (c.reviewReady) return "Ready to inspect";
  if (c.structureId) return "Outside design brief";
  return (
    (
      {
        outside_constraints: "Excluded before evaluation",
        duplicate: "Duplicate input",
        invalid: "Invalid input",
        deferred_budget: "Deferred by budget",
        queued: "Awaiting evaluation",
        failed: "Calculation failed",
      } as Record<string, string>
    )[c.status ?? ""] ?? "No evaluated pose"
  );
}

export function objectiveStatus(c: Candidate) {
  if (!c.structureId || c.asp86Contact === undefined) return "Not assessed";
  if (!c.asp86Contact) return "Not detected";
  return c.reviewReady ? "Detected · eligible" : "Detected · outside brief";
}

export function candidateFailure(c: Candidate, failure: string) {
  const match = failure.match(
    /^(molecular_weight|clogp|rotatable_bonds)(>|<|!=)(-?\d+(?:\.\d+)?)$/,
  );
  if (match) {
    const [, key, operator, limit] = match;
    const [label, value, unit] =
      key === "molecular_weight"
        ? (["Molecular weight", c.mw, " g/mol"] as const)
        : key === "clogp"
          ? (["Calculated logP", c.clogp, ""] as const)
          : (["Rotatable bonds", c.rotors, ""] as const);
    return `${label} ${displayNumber(value, key === "rotatable_bonds" ? 0 : 2)}${unit} ${operator === ">" ? "exceeds" : operator === "<" ? "is below" : "differs from"} the limit of ${Number(limit)}${unit}.`;
  }
  if (failure === "parent_scaffold_not_retained")
    return "The required parent scaffold is missing. This molecule is outside this workflow’s scope.";
  if (failure === "modification_outside_declared_para_attachment")
    return "The change is outside the permitted para carbon (C20). This workflow only evaluates growth at that site.";
  if (failure === "modification_outside_declared_attachment")
    return "The change is outside this workflow’s permitted attachment site.";
  return failureLabel(failure);
}

export function candidateExplanation(c: Candidate) {
  if (c.failures.length)
    return c.failures.map((f) => candidateFailure(c, f)).join(" ");
  if (c.status === "duplicate")
    return "This input matches another molecule after preparation and normalization. It was retained in the record and was not evaluated again.";
  if (c.status === "invalid")
    return c.error
      ? `${c.error}. Correct the input in a new round.`
      : "The molecular input could not be parsed or prepared. Correct it in a new round.";
  if (c.status === "deferred_budget")
    return "The candidate was not admitted before the evaluation budget was reached. It has no binding or contact result.";
  if (c.status === "queued") return "This input is waiting for evaluation.";
  if (c.error) return c.error;
  if (!c.structureId)
    return "No evaluated pose was produced. The input and calculation outcome remain in the experiment record.";
  if (!c.reviewReady)
    return "This pose did not satisfy every geometry, scaffold-locality and hinge-contact requirement. A geometry pass alone does not make it eligible for design review.";
  return "This pose satisfies the geometry, scaffold-locality and hinge-contact requirements. Inspect the predicted contact before deciding what to keep.";
}

/** Only engine-provided, same-attempt provenance establishes a duplicate link. */
export function duplicateOriginal(c: Candidate, candidates: Candidate[]) {
  if (c.status !== "duplicate") return undefined;
  if (c.duplicateOfCandidateId)
    return candidates.find(
      (other) => other.id !== c.id && other.id === c.duplicateOfCandidateId,
    );
  return c.duplicateOfSourceId
    ? candidates.find(
        (other) =>
          other.id !== c.id && other.sourceId === c.duplicateOfSourceId,
      )
    : undefined;
}

export function poseIdentity(c: Candidate) {
  const index =
    c.poses?.findIndex((p) => p.structureId === c.structureId) ?? -1;
  const state = c.preparedMoleculeId ?? c.poses?.[index]?.preparedStateId;
  return c.structureId
    ? `Pose ${index >= 0 ? index + 1 : "selected"}${state ? ` · state ${state.slice(0, 8)}` : ""}`
    : "No evaluated pose";
}
