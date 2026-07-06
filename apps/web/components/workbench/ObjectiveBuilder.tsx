"use client";

// Structured composer for a custom (exploratory) objective (07-04 / 07-04b). Builds the
// exact objective_json + constraints_json the backend expects (see objectiveSpec.ts),
// and previews the composite score on a probe set via POST /objective/validate. Emits
// the derived payload + a launch blocker to the parent via onChange; the parent owns
// launch. Coral stays reserved for the primary action — this surface is warm neutrals.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  type ObjectiveJson,
  type ConstraintsJson,
  type ObjectiveValidateResult,
  type CatalogGroup,
  validateObjective,
} from "@/lib/api";
import {
  AGGREGATORS,
  ORACLE_PRESETS,
  TRANSFORM_KINDS,
  newTerm,
  retargetTerm,
  representativeTask,
  specBlocker,
  toConstraintsJson,
  toObjectiveJson,
  type TransformKind,
  type UiTerm,
} from "./objectiveSpec";
import { Eyebrow } from "./ui";

const DEFAULT_PROBES = ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "O=C(O)c1ccccc1O"];
const CATALOG_OPTIONS = ["PAINS", "Brenk"] as const;

export type ObjectiveDraft = {
  objectiveJson: ObjectiveJson;
  constraintsJson: ConstraintsJson | undefined;
  blocker: string | null;
  representativeTask: string;
};

export function ObjectiveBuilder({
  catalog,
  onChange,
}: {
  catalog: CatalogGroup[];
  onChange: (draft: ObjectiveDraft) => void;
}) {
  const [terms, setTerms] = useState<UiTerm[]>(() => [newTerm("qed")]);
  const [aggregator, setAggregator] = useState<string>("weighted_sum");
  const [catalogs, setCatalogs] = useState<string[]>([]);
  const [smartsExclude, setSmartsExclude] = useState("");
  const [smartsInclude, setSmartsInclude] = useState("");
  const [probes, setProbes] = useState(DEFAULT_PROBES.join("\n"));

  const taskNames = useMemo(
    () => catalog.flatMap((g) => g.tasks.map((t) => t.name)),
    [catalog],
  );

  const objectiveJson = useMemo(
    () => toObjectiveJson(terms, aggregator),
    [terms, aggregator],
  );
  const constraintsJson = useMemo(
    () =>
      toConstraintsJson(
        catalogs,
        smartsExclude.split(/\n+/),
        smartsInclude.split(/\n+/),
      ),
    [catalogs, smartsExclude, smartsInclude],
  );
  const blocker = specBlocker(terms);

  // Keep the latest onChange in a ref (updated in an effect, never during render) so an
  // unstable parent callback never re-fires the report effect below.
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });

  // Report the derived payload up whenever it changes (parent owns launch).
  const draftKey = JSON.stringify({ objectiveJson, constraintsJson, blocker });
  useEffect(() => {
    onChangeRef.current({
      objectiveJson,
      constraintsJson,
      blocker,
      representativeTask: representativeTask(terms),
    });
    // draftKey captures the meaningful contents; terms feeds representativeTask.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

  // ── Live preview (debounced) ────────────────────────────────────────────────
  const [preview, setPreview] = useState<ObjectiveValidateResult[] | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const probeList = useMemo(
    () => probes.split(/\n+/).map((s) => s.trim()).filter(Boolean),
    [probes],
  );

  useEffect(() => {
    if (blocker || probeList.length === 0) {
      // Resetting the preview when the spec goes incomplete is a legitimate sync with
      // the (external) validate endpoint's inputs, not a cascading render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPreview(null);
      setPreviewErr(null);
      return;
    }
    let cancelled = false;
    setPreviewing(true);
    const handle = setTimeout(() => {
      validateObjective(objectiveJson, probeList)
        .then((res) => {
          if (cancelled) return;
          setPreview(res.results);
          setPreviewErr(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          setPreview(null);
          setPreviewErr(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!cancelled) setPreviewing(false);
        });
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey, probeList.join("|")]);

  function updateTerm(id: string, patch: Partial<UiTerm>) {
    setTerms((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Terms */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Objective terms</h3>
          <span className="text-xs text-muted-foreground">
            each mapped to 0–1, then combined
          </span>
        </div>

        <div className="flex flex-col gap-3">
          {terms.map((term, i) => {
            const preset = ORACLE_PRESETS.find((p) => p.name === term.oracle);
            const showBand =
              term.transformKind === "sigmoid" ||
              term.transformKind === "reverse_sigmoid" ||
              term.transformKind === "double_sigmoid";
            return (
              <div
                key={term.id}
                className="flex flex-col gap-3 rounded-xl bg-card p-3 ring-1 ring-foreground/10"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs tabular-nums text-muted-foreground">
                    term {i + 1}
                  </span>
                  <label className="sr-only" htmlFor={`oracle-${term.id}`}>
                    Oracle for term {i + 1}
                  </label>
                  <select
                    id={`oracle-${term.id}`}
                    value={term.oracle}
                    onChange={(e) => updateTerm(term.id, retargetTerm(term, e.target.value))}
                    className="h-8 rounded-lg border border-input bg-background px-2 text-sm"
                  >
                    {ORACLE_PRESETS.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.label}
                      </option>
                    ))}
                  </select>

                  {preset?.needsTask && (
                    <>
                      <label className="sr-only" htmlFor={`task-${term.id}`}>
                        PMO task for term {i + 1}
                      </label>
                      <select
                        id={`task-${term.id}`}
                        value={term.task ?? ""}
                        onChange={(e) => updateTerm(term.id, { task: e.target.value || null })}
                        className="h-8 rounded-lg border border-input bg-background px-2 font-mono text-xs"
                      >
                        <option value="">pick a task…</option>
                        {taskNames.map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </>
                  )}

                  <span className="ml-auto flex items-center gap-1.5">
                    <label
                      className="text-[0.68rem] tracking-[0.08em] text-muted-foreground uppercase"
                      htmlFor={`weight-${term.id}`}
                    >
                      weight
                    </label>
                    <input
                      id={`weight-${term.id}`}
                      type="number"
                      min={0.1}
                      step={0.1}
                      value={term.weight}
                      onChange={(e) =>
                        updateTerm(term.id, { weight: Number(e.target.value) })
                      }
                      className="h-8 w-16 rounded-lg border border-input bg-background px-2 text-sm tabular-nums"
                    />
                    <button
                      type="button"
                      onClick={() => setTerms((ts) => ts.filter((t) => t.id !== term.id))}
                      disabled={terms.length === 1}
                      aria-label={`Remove term ${i + 1}`}
                      className="rounded-md px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </span>
                </div>

                {preset && (
                  <p className="text-xs leading-relaxed text-muted-foreground">{preset.help}</p>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <label className="sr-only" htmlFor={`transform-${term.id}`}>
                    Transform for term {i + 1}
                  </label>
                  <select
                    id={`transform-${term.id}`}
                    value={term.transformKind}
                    onChange={(e) =>
                      updateTerm(term.id, { transformKind: e.target.value as TransformKind })
                    }
                    className="h-8 rounded-lg border border-input bg-background px-2 text-xs"
                  >
                    {TRANSFORM_KINDS.map((t) => (
                      <option key={t.kind} value={t.kind}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  {showBand && (
                    <>
                      <NumField
                        id={`low-${term.id}`}
                        label="low"
                        value={term.low}
                        onChange={(v) => updateTerm(term.id, { low: v })}
                      />
                      <NumField
                        id={`high-${term.id}`}
                        label="high"
                        value={term.high}
                        onChange={(v) => updateTerm(term.id, { high: v })}
                      />
                      <NumField
                        id={`k-${term.id}`}
                        label="steepness k"
                        value={term.k}
                        onChange={(v) => updateTerm(term.id, { k: v })}
                      />
                    </>
                  )}
                  {term.transformKind === "value_map" && (
                    <textarea
                      aria-label={`Value-map points for term ${i + 1}`}
                      value={term.points}
                      onChange={(e) => updateTerm(term.id, { points: e.target.value })}
                      rows={2}
                      placeholder="x, y per line"
                      className="h-8 min-h-8 flex-1 rounded-lg border border-input bg-background px-2 py-1 font-mono text-xs"
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setTerms((ts) => [...ts, newTerm("qed")])}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            + Add term
          </button>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Combine with
            <select
              aria-label="Aggregator"
              value={aggregator}
              onChange={(e) => setAggregator(e.target.value)}
              className="h-8 rounded-lg border border-input bg-background px-2 text-xs"
            >
              {AGGREGATORS.map((a) => (
                <option key={a} value={a}>
                  {a === "weighted_sum" ? "weighted sum" : "weighted product"}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* Constraints */}
      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Hard constraints</h3>
          <span className="text-xs text-muted-foreground">optional · filters, not scored</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {CATALOG_OPTIONS.map((c) => {
            const on = catalogs.includes(c);
            return (
              <label key={c} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() =>
                    setCatalogs((cs) => (on ? cs.filter((x) => x !== c) : [...cs, c]))
                  }
                  className="size-4 accent-foreground"
                />
                Exclude {c} alerts
              </label>
            );
          })}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            SMARTS to exclude (one per line)
            <textarea
              value={smartsExclude}
              onChange={(e) => setSmartsExclude(e.target.value)}
              rows={2}
              placeholder="[N+](=O)[O-]"
              className="rounded-lg border border-input bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            SMARTS to require (one per line)
            <textarea
              value={smartsInclude}
              onChange={(e) => setSmartsInclude(e.target.value)}
              rows={2}
              placeholder="c1ccccc1"
              className="rounded-lg border border-input bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
        </div>
        <p className="text-[0.7rem] leading-relaxed text-muted-foreground">
          Constraints are hard filters. For a soft property band (e.g. a preferred weight
          range), add an objective term with a <span className="font-medium">Band</span> or{" "}
          <span className="font-medium">Value map</span> transform instead.
        </p>
      </div>

      {/* Live preview */}
      <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-muted/30 p-3">
        <div className="flex items-center justify-between">
          <Eyebrow>Live preview</Eyebrow>
          <span className="text-xs text-muted-foreground">
            {previewing ? "scoring…" : "composite score per probe (0–1, in-silico)"}
          </span>
        </div>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Probe molecules (SMILES, one per line)
          <textarea
            aria-label="Probe molecules"
            value={probes}
            onChange={(e) => setProbes(e.target.value)}
            rows={3}
            className="rounded-lg border border-input bg-background px-2 py-1 font-mono text-xs"
          />
        </label>
        {blocker ? (
          <p className="text-xs text-muted-foreground">
            Finish the objective to preview — {blocker.toLowerCase()}
          </p>
        ) : previewErr ? (
          <p role="alert" className="text-xs text-destructive">
            {previewErr}
          </p>
        ) : preview ? (
          <ul className="flex flex-col gap-1.5">
            {preview.map((r, i) => (
              <li key={`${r.smiles}-${i}`} className="flex items-center gap-2">
                <span className="w-40 shrink-0 truncate font-mono text-[0.7rem] text-foreground">
                  {r.smiles}
                </span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full bg-muted-foreground/50"
                    style={{ width: `${r.score != null ? Math.round(r.score * 100) : 0}%` }}
                  />
                </span>
                <span className="w-10 shrink-0 text-right text-[0.7rem] tabular-nums text-muted-foreground">
                  {r.score != null ? r.score.toFixed(2) : "n/a"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">Add a probe SMILES to preview.</p>
        )}
      </div>
    </div>
  );
}

function NumField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <span className="flex items-center gap-1">
      <label
        htmlFor={id}
        className="text-[0.66rem] tracking-[0.06em] text-muted-foreground uppercase"
      >
        {label}
      </label>
      <input
        id={id}
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-8 w-16 rounded-lg border border-input bg-background px-1.5 text-xs tabular-nums"
      />
    </span>
  );
}
