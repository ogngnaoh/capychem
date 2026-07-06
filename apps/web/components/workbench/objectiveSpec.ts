// Pure builder logic for the composed-objective UI (07-04). Kept framework-free and
// separate from ObjectiveBuilder.tsx so the compose → objective_json mapping is unit
// tested directly. Mirrors packages/core/capychem/objective.py's contract exactly:
// term = { oracle, weight>0, transform{kind,...} → [0,1], oracle_kwargs } and a
// `pmo` term carries oracle_kwargs.task.

import type { ConstraintsJson, ObjectiveJson } from "@/lib/api";

export type TransformKind =
  | "identity"
  | "sigmoid"
  | "reverse_sigmoid"
  | "double_sigmoid"
  | "value_map";

// One term as the UI edits it (denormalized transform fields; serialized on demand).
export type UiTerm = {
  id: string;
  oracle: string; // qed | sa_score | mw | clogp | tpsa | pmo
  task: string | null; // only for the pmo oracle
  weight: number;
  transformKind: TransformKind;
  low: number;
  high: number;
  k: number;
  points: string; // value_map: "x, y" per line
};

export type OraclePreset = {
  name: string;
  label: string;
  help: string;
  needsTask: boolean;
  transform: TransformKind;
  low: number;
  high: number;
};

// The descriptor presets score locally for free; pmo routes through the harness.
// Defaults encode the drug-likeness convention each descriptor is usually composed
// under (a band for MW/cLogP; "lower is better" for SA/TPSA) so a fresh term is
// already sensible.
export const ORACLE_PRESETS: OraclePreset[] = [
  { name: "qed", label: "QED", help: "Overall drug-likeness (0–1, higher is better).", needsTask: false, transform: "identity", low: 0, high: 1 },
  { name: "sa_score", label: "SA score", help: "Synthetic accessibility (1 easy → 10 hard). Lower is better.", needsTask: false, transform: "reverse_sigmoid", low: 2, high: 5 },
  { name: "mw", label: "Molecular weight", help: "g/mol. Drug-like band ≈ 250–500.", needsTask: false, transform: "double_sigmoid", low: 250, high: 500 },
  { name: "clogp", label: "cLogP", help: "Lipophilicity. Drug-like band ≈ 1–4.", needsTask: false, transform: "double_sigmoid", low: 1, high: 4 },
  { name: "tpsa", label: "TPSA", help: "Polar surface area (Å²). ≤ 140 preferred.", needsTask: false, transform: "reverse_sigmoid", low: 60, high: 140 },
  { name: "pmo", label: "PMO benchmark task", help: "A standardized benchmark oracle from the 23-task catalog.", needsTask: true, transform: "identity", low: 0, high: 1 },
];

export const TRANSFORM_KINDS: { kind: TransformKind; label: string; help: string }[] = [
  { kind: "identity", label: "Identity", help: "Use the value as-is (already 0–1)." },
  { kind: "sigmoid", label: "Sigmoid (higher is better)", help: "Rewards values above the band." },
  { kind: "reverse_sigmoid", label: "Reverse sigmoid (lower is better)", help: "Rewards values below the band." },
  { kind: "double_sigmoid", label: "Band (a preferred range)", help: "Rewards values inside [low, high]." },
  { kind: "value_map", label: "Value map (custom points)", help: "Piecewise-linear map through (x, y) points." },
];

export const AGGREGATORS = ["weighted_sum", "weighted_product"] as const;

let _seq = 0;
export function newTerm(oracle = "qed"): UiTerm {
  const preset = ORACLE_PRESETS.find((p) => p.name === oracle) ?? ORACLE_PRESETS[0];
  _seq += 1;
  return {
    id: `t${_seq}-${oracle}`,
    oracle: preset.name,
    task: preset.needsTask ? null : null,
    weight: 1,
    transformKind: preset.transform,
    low: preset.low,
    high: preset.high,
    k: 10,
    points: "0, 0\n1, 1",
  };
}

// Re-seat a term's transform defaults when its oracle changes (so switching to MW
// gives the MW band, not the previous oracle's range).
export function retargetTerm(term: UiTerm, oracle: string): UiTerm {
  const preset = ORACLE_PRESETS.find((p) => p.name === oracle) ?? ORACLE_PRESETS[0];
  return {
    ...term,
    oracle: preset.name,
    task: preset.needsTask ? term.task : null,
    transformKind: preset.transform,
    low: preset.low,
    high: preset.high,
  };
}

function parsePoints(text: string): [number, number][] {
  const pts: [number, number][] = [];
  for (const line of text.split(/\n+/)) {
    const [x, y] = line.split(/[\s,]+/).map((s) => Number(s.trim()));
    if (Number.isFinite(x) && Number.isFinite(y)) pts.push([x, y]);
  }
  return pts.length >= 2 ? pts : [[0, 0], [1, 1]];
}

export function termTransform(term: UiTerm): Record<string, unknown> {
  switch (term.transformKind) {
    case "identity":
      return { kind: "identity" };
    case "sigmoid":
    case "reverse_sigmoid":
    case "double_sigmoid":
      return { kind: term.transformKind, low: term.low, high: term.high, k: term.k };
    case "value_map":
      return { kind: "value_map", points: parsePoints(term.points) };
  }
}

// Compose the UI terms into the exact objective_json the backend expects. A pmo term
// with no task chosen still serializes { task: "" }; the caller gates launch on a
// complete spec (see specComplete).
export function toObjectiveJson(terms: UiTerm[], aggregator: string): ObjectiveJson {
  return {
    terms: terms.map((t) => ({
      oracle: t.oracle,
      weight: t.weight,
      transform: termTransform(t),
      oracle_kwargs: t.oracle === "pmo" ? { task: t.task ?? "" } : {},
    })),
    aggregator,
  };
}

// Only include non-empty keys; return undefined when nothing is constrained (so the
// run stays un-constrained rather than sending an empty object).
export function toConstraintsJson(
  catalogs: string[],
  smartsExclude: string[],
  smartsInclude: string[],
): ConstraintsJson | undefined {
  const c: ConstraintsJson = {};
  if (catalogs.length) c.catalogs = catalogs;
  const exc = smartsExclude.map((s) => s.trim()).filter(Boolean);
  const inc = smartsInclude.map((s) => s.trim()).filter(Boolean);
  if (exc.length) c.smarts_exclude = exc;
  if (inc.length) c.smarts_include = inc;
  return Object.keys(c).length ? c : undefined;
}

// A spec is launchable only when every term is well-formed (positive weight, a task
// chosen for any pmo term). Returns the first blocking reason, or null when ready.
export function specBlocker(terms: UiTerm[]): string | null {
  if (terms.length === 0) return "Add at least one objective term.";
  for (const t of terms) {
    if (!(t.weight > 0)) return `Term weights must be positive (${t.oracle}).`;
    if (t.oracle === "pmo" && !t.task) return "Pick a PMO task for the benchmark term.";
  }
  return null;
}

// The run still needs a valid PMO `task` column even for a composed objective; use the
// first pmo term's task when present, else a harmless valid default.
export function representativeTask(terms: UiTerm[]): string {
  const pmo = terms.find((t) => t.oracle === "pmo" && t.task);
  return pmo?.task ?? "qed";
}
