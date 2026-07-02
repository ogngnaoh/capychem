"use client";

// Hybrid intent launcher (the front door). Four layers, ported from app/proto/launcher
// and wired to the live backend:
//  (1) possibility space  — the 23-task catalog from GET /catalog, grouped in plain language;
//  (2) intent             — an NL box resolved by POST /intent/resolve;
//  (3) mirror             — the editable resolved plan shown before launch;
//  (4) guardrails         — FR-015 refusals (each naming the input + why) + the grounded
//                           no-match refusal (matched_task null → closest_task + rationale).
// On Start → POST /runs → route to the run's cockpit. Strategy defaults to the LLM
// proposer (+ Graph-GA fallback), per the approved design.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import {
  createRun,
  getCatalog,
  resolveIntent,
  type CatalogGroup,
  type IntentResolution,
  type Refusal,
} from "@/lib/api";
import { Eyebrow, InSilicoTag } from "@/components/workbench/ui";

type Plan = {
  task: string | null;
  budget: number;
  plateau_window: number;
  mutation_strategy: string;
  seed_smiles: string;
};

const DEFAULT_PLAN: Plan = {
  task: null,
  budget: 10000,
  plateau_window: 5,
  mutation_strategy: "llm",
  seed_smiles: "",
};

export function Launcher() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<CatalogGroup[]>([]);
  const [intentText, setIntentText] = useState("");
  const [resolving, setResolving] = useState(false);
  const [resolution, setResolution] = useState<IntentResolution | null>(null);
  const [plan, setPlan] = useState<Plan>(DEFAULT_PLAN);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let closed = false;
    getCatalog()
      .then((g) => !closed && setCatalog(g))
      .catch(() => {});
    return () => {
      closed = true;
    };
  }, []);

  const taskCount = catalog.reduce((n, g) => n + g.tasks.length, 0) || 23;
  const noMatch = !!resolution && resolution.matched_task === null;

  async function resolve() {
    if (!intentText.trim()) return;
    setResolving(true);
    setError(null);
    try {
      const res = await resolveIntent({
        text: intentText,
        budget: plan.budget,
        seed_smiles: plan.seed_smiles.trim() || undefined,
      });
      setResolution(res);
      if (res.matched_task && res.resolved_plan) {
        const rp = res.resolved_plan;
        setPlan((p) => ({
          ...p,
          task: rp.task,
          budget: rp.budget,
          plateau_window: rp.plateau_window,
          mutation_strategy: "llm", // approved design default (resolver returns graph_ga)
          seed_smiles: rp.seed_smiles ?? p.seed_smiles,
        }));
      } else {
        setPlan((p) => ({ ...p, task: null }));
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setResolving(false);
    }
  }

  function pickTask(name: string) {
    setResolution(null);
    setPlan((p) => ({ ...p, task: name }));
  }

  // FR-015 guardrails: live client checks + the backend's seed-SMILES verdict.
  const liveRefusals: Refusal[] = [];
  if (!plan.task && !noMatch) {
    liveRefusals.push({
      field: "Objective",
      reason: "Pick or describe an objective — a run can't start without one.",
    });
  }
  if (plan.task && (!Number.isFinite(plan.budget) || plan.budget <= 0)) {
    liveRefusals.push({
      field: "Budget",
      reason: "Budget must be a positive number — enter at least 1 oracle call.",
    });
  }
  const seedRefusals = (resolution?.refusals ?? []).filter(
    (r) => r.field.toLowerCase().includes("seed") && plan.seed_smiles.trim() !== "",
  );
  const refusals = [...liveRefusals, ...seedRefusals];
  const canStart = !!plan.task && !noMatch && refusals.length === 0 && !starting;

  async function start() {
    if (!canStart || !plan.task) return;
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await createRun({
        task: plan.task,
        budget: plan.budget,
        seed: 42,
        pop_size: 100,
        offspring: 32,
        mutation_rate: 0.01,
        plateau_window: plan.plateau_window,
        max_generations: 100,
        mutation_strategy: plan.mutation_strategy,
      });
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setStarting(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <Eyebrow>Start a run</Eyebrow>
        <h1 className="font-heading text-2xl font-normal tracking-tight">
          What do you want to optimize?
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Describe an objective in plain language, or pick one from the catalog. Every
          objective maps to a standardized in-silico PMO oracle.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.5fr_1fr]">
        {/* LEFT: intent + possibility space */}
        <div className="flex flex-col gap-6">
          {/* NL intent */}
          <Card>
            <CardContent className="flex flex-col gap-2.5 py-4">
              <label htmlFor="intent" className="text-sm font-medium">
                Describe what you want
              </label>
              <div className="flex gap-2">
                <input
                  id="intent"
                  value={intentText}
                  onChange={(e) => setIntentText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") resolve();
                  }}
                  placeholder="e.g. recover a molecule like troglitazone"
                  className="h-9 flex-1 rounded-lg border border-input bg-background px-3 text-sm shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                />
                <button
                  type="button"
                  onClick={resolve}
                  disabled={resolving || !intentText.trim()}
                  className="rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {resolving ? "Resolving…" : "Resolve"}
                </button>
              </div>
              {resolution ? (
                noMatch ? (
                  <p className="text-xs text-muted-foreground">
                    Resolved against the {taskCount}{" "}PMO objectives — we won&apos;t invent an
                    oracle that doesn&apos;t exist.
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Matched{" "}
                    <span className="font-mono text-foreground">{resolution.matched_task}</span>{" "}
                    with {resolution.confidence ?? "—"} confidence. Review the plan on the right
                    before launch.
                  </p>
                )
              ) : (
                <p className="text-xs text-muted-foreground">
                  Resolves against the {taskCount}{" "}PMO objectives — or pick one directly below.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Possibility space: the catalog */}
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-heading text-lg font-normal tracking-tight">
                Objective catalog
              </h2>
              <span className="text-xs text-muted-foreground">
                {taskCount}{" "}PMO tasks · scores 0–1, higher is better (in-silico)
              </span>
            </div>
            {catalog.map((g) => (
              <div key={g.group} className="flex flex-col gap-2.5">
                <h3 className="text-sm font-medium">{g.group}</h3>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {g.tasks.map((t) => {
                    const selected = t.name === plan.task;
                    return (
                      <button
                        key={t.name}
                        type="button"
                        onClick={() => pickTask(t.name)}
                        aria-pressed={selected}
                        className={[
                          "rounded-xl p-3 text-left ring-1 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          selected
                            ? "bg-primary/[0.06] ring-primary/40"
                            : "bg-card ring-foreground/10 hover:bg-muted/60",
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs text-foreground">{t.name}</span>
                          {selected && (
                            <span className="rounded-full bg-primary/12 px-1.5 py-0.5 text-[0.62rem] font-medium text-primary ring-1 ring-primary/30">
                              selected
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          {t.description}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT: resolved-plan mirror + guardrails (sticky) */}
        <div className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
          {noMatch ? (
            <NoMatchMirror resolution={resolution!} onUseClosest={pickTask} />
          ) : plan.task ? (
            <ResolvedMirror
              plan={plan}
              setPlan={setPlan}
              canStart={canStart}
              starting={starting}
              onStart={start}
              blurb={findBlurb(catalog, plan.task)}
            />
          ) : (
            <EmptyMirror />
          )}
          <GuardrailCard refusals={refusals} />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      </div>
    </div>
  );
}

function findBlurb(catalog: CatalogGroup[], task: string): string | undefined {
  for (const g of catalog) {
    const hit = g.tasks.find((t) => t.name === task);
    if (hit) return hit.description;
  }
  return undefined;
}

function ResolvedMirror({
  plan,
  setPlan,
  canStart,
  starting,
  onStart,
  blurb,
}: {
  plan: Plan;
  setPlan: React.Dispatch<React.SetStateAction<Plan>>;
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  blurb?: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3.5 py-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-normal">Resolved plan</h2>
          <InSilicoTag />
        </div>

        <Field label="Objective">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm">{plan.task}</span>
            <button
              type="button"
              onClick={() => setPlan((p) => ({ ...p, task: null }))}
              className="text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
            >
              change
            </button>
          </div>
          {blurb && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{blurb}</p>
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Oracle-call budget">
            <input
              type="number"
              min={1}
              aria-label="Oracle-call budget"
              value={plan.budget}
              onChange={(e) => setPlan((p) => ({ ...p, budget: Number(e.target.value) }))}
              className="h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm tabular-nums"
            />
          </Field>
          <Field label="Plateau window">
            <input
              type="number"
              min={1}
              aria-label="Plateau window"
              value={plan.plateau_window}
              onChange={(e) =>
                setPlan((p) => ({ ...p, plateau_window: Number(e.target.value) }))
              }
              className="h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm tabular-nums"
            />
          </Field>
        </div>

        <Field label="Strategy">
          <select
            aria-label="Strategy"
            value={plan.mutation_strategy}
            onChange={(e) => setPlan((p) => ({ ...p, mutation_strategy: e.target.value }))}
            className="h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
          >
            <option value="llm">LLM proposer (+ Graph-GA fallback)</option>
            <option value="graph_ga">Graph-GA baseline</option>
          </select>
        </Field>

        <Field label="Seed molecules (SMILES, optional)">
          <input
            aria-label="Seed molecules"
            value={plan.seed_smiles}
            onChange={(e) => setPlan((p) => ({ ...p, seed_smiles: e.target.value }))}
            placeholder="default population"
            className="h-8 w-full rounded-lg border border-input bg-background px-2.5 font-mono text-xs"
          />
          <p className="text-[0.7rem] leading-relaxed text-muted-foreground">
            Validated here — MVP runs start from the standard population.
          </p>
        </Field>

        <div className="rounded-lg border border-border bg-muted/40 px-3 py-2.5">
          <div className="text-xs font-medium text-foreground">Projected envelope</div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>
              ≤ {Number.isFinite(plan.budget) ? plan.budget.toLocaleString() : "—"} oracle calls
            </span>
            <span>~20–30 generations</span>
            <span>in-silico compute</span>
          </div>
        </div>

        <button
          type="button"
          onClick={onStart}
          disabled={!canStart}
          className="mt-0.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {starting ? "Starting…" : "Start run"}
        </button>
      </CardContent>
    </Card>
  );
}

function NoMatchMirror({
  resolution,
  onUseClosest,
}: {
  resolution: IntentResolution;
  onUseClosest: (name: string) => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-normal">Resolved plan</h2>
          <InSilicoTag />
        </div>
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-3 text-sm">
          <div className="font-medium text-destructive">
            No benchmark matches that objective
          </div>
          <p className="mt-1.5 leading-relaxed text-foreground">{resolution.rationale}</p>
        </div>
        <div className="flex flex-col gap-2">
          {resolution.closest_task && (
            <button
              type="button"
              onClick={() => onUseClosest(resolution.closest_task!)}
              className="rounded-lg border border-border px-3 py-2 text-sm transition-colors hover:bg-muted"
            >
              Use{" "}
              <span className="font-mono">{resolution.closest_task}</span> instead
            </button>
          )}
        </div>
        <button
          type="button"
          disabled
          className="mt-0.5 cursor-not-allowed rounded-lg bg-primary/40 px-4 py-2 text-sm font-medium text-primary-foreground"
          title="Resolve to a real objective first"
        >
          Start run
        </button>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Runs only start against a real PMO oracle — this keeps every score
          benchmark-comparable.
        </p>
      </CardContent>
    </Card>
  );
}

function EmptyMirror() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-normal">Resolved plan</h2>
          <InSilicoTag />
        </div>
        <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          Describe an objective above, or pick one from the catalog, to build a run plan.
        </p>
      </CardContent>
    </Card>
  );
}

function GuardrailCard({ refusals }: { refusals: Refusal[] }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2.5 py-4">
        <div className="flex items-center gap-2">
          <h2 className="font-heading text-base font-normal">Guardrails</h2>
          <span className="text-xs text-muted-foreground">FR-015</span>
        </div>
        {refusals.length === 0 ? (
          <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Objective set · budget positive · seed SMILES valid — ready to launch.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {refusals.map((r, i) => (
              <li
                key={`${r.field}-${i}`}
                className="flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs"
              >
                <span aria-hidden="true" className="text-destructive">
                  ⚠
                </span>
                <span className="leading-relaxed text-foreground">
                  <span className="font-medium">{r.field}:</span> {r.reason}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        {label}
      </span>
      {children}
    </div>
  );
}
