"use client";

// LOW-FI PROTOTYPE — Hybrid intent launcher (the front door). Four layers:
// (1) possibility space = the 23-task objective catalog, grouped in plain language;
// (2) intent = an NL box, MOCK-resolved against the catalog (no backend);
// (3) mirror = editable resolved plan shown before launch;
// (4) guardrails = FR-015 refusals, each naming which input and why.
// `?state=nomatch` renders the low-confidence / no-benchmark resolution.

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { CATALOG, CATALOG_COUNT, lookupObjective } from "../_mock";
import { InSilicoTag } from "../_ui";

const RESOLVED_TASK = "troglitazone_rediscovery";

export default function LauncherProto() {
  return (
    <Suspense fallback={null}>
      <LauncherInner />
    </Suspense>
  );
}

function LauncherInner() {
  const params = useSearchParams();
  const noMatch = params.get("state") === "nomatch";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-2xl font-normal">Start a run</h1>
        <p className="text-sm text-muted-foreground">
          Describe an objective in plain language, or pick one from the catalog.
          Every objective maps to a standardized in-silico PMO oracle.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.5fr_1fr]">
        {/* LEFT: intent + possibility space */}
        <div className="flex flex-col gap-6">
          {/* NL intent */}
          <Card>
            <CardContent className="flex flex-col gap-2 py-4">
              <label htmlFor="intent" className="text-sm font-medium">
                Describe what you want
              </label>
              <div className="flex gap-2">
                <input
                  id="intent"
                  defaultValue={
                    noMatch
                      ? "make it dissolve well in water"
                      : "recover a molecule like troglitazone"
                  }
                  className="h-9 flex-1 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
                />
                <button className="rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                  Resolve
                </button>
              </div>
              {noMatch ? (
                <p className="text-xs text-muted-foreground">
                  Resolved against the 23 PMO objectives — we won&apos;t invent an
                  oracle that doesn&apos;t exist.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Matched{" "}
                  <span className="font-mono text-foreground">{RESOLVED_TASK}</span>{" "}
                  with high confidence. Review the plan on the right before launch.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Possibility space: the catalog */}
          <div className="flex flex-col gap-4">
            <div className="flex items-baseline justify-between">
              <h2 className="font-heading text-lg font-normal">
                Objective catalog
              </h2>
              <span className="text-xs text-muted-foreground">
                {CATALOG_COUNT} PMO tasks · scores 0–1, higher is better (in-silico)
              </span>
            </div>
            {CATALOG.map((g) => (
              <div key={g.key} className="flex flex-col gap-2">
                <div className="flex items-baseline gap-2">
                  <h3 className="text-sm font-medium">{g.label}</h3>
                  <span className="text-xs text-muted-foreground">{g.hint}</span>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {g.objectives.map((o) => {
                    const selected = !noMatch && o.task === RESOLVED_TASK;
                    return (
                      <button
                        key={o.task}
                        className={[
                          "rounded-lg p-3 text-left ring-1 transition-colors",
                          selected
                            ? "bg-primary/5 ring-primary/40"
                            : "bg-card ring-foreground/10 hover:bg-muted/50",
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs text-foreground">
                            {o.task}
                          </span>
                          {selected && (
                            <span className="rounded-full bg-primary/12 px-1.5 py-0.5 text-[0.65rem] text-primary ring-1 ring-primary/30">
                              selected
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {o.blurb}
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
        <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
          {noMatch ? <NoMatchMirror /> : <ResolvedMirror />}
          <GuardrailGallery />
        </div>
      </div>
    </div>
  );
}

function ResolvedMirror() {
  const obj = lookupObjective(RESOLVED_TASK);
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-normal">Resolved plan</h2>
          <InSilicoTag />
        </div>

        <Field label="Objective">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm">{RESOLVED_TASK}</span>
            <button className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
              change
            </button>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{obj?.blurb}</p>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Oracle-call budget">
            <input
              defaultValue={10000}
              className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </Field>
          <Field label="Plateau window (gens)">
            <input
              defaultValue={5}
              className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </Field>
        </div>

        <Field label="Strategy">
          <select className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm">
            <option>LLM proposer (+ Graph-GA fallback)</option>
            <option>Graph-GA baseline</option>
          </select>
        </Field>

        <Field label="Seed molecules (SMILES, optional)">
          <input
            placeholder="default population"
            className="h-8 w-full rounded-md border border-input bg-transparent px-2 font-mono text-xs"
          />
        </Field>

        <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <div className="font-medium text-foreground">Projected envelope</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
            <span>≤ 10,000 oracle calls</span>
            <span>~$2 compute (in-silico)</span>
            <span>~20–30 generations</span>
          </div>
        </div>

        <button className="mt-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          Start run
        </button>
      </CardContent>
    </Card>
  );
}

function NoMatchMirror() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-normal">Resolved plan</h2>
          <InSilicoTag />
        </div>
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm">
          <div className="font-medium text-destructive">
            No benchmark matches that objective
          </div>
          <p className="mt-1 text-foreground">
            &ldquo;make it dissolve well in water&rdquo; isn&apos;t one of the 23 PMO
            oracles. The closest available objective is{" "}
            <span className="font-mono">albuterol_similarity</span> — but it measures
            structural similarity, not solubility, so confirm before you launch.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <button className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">
            Use albuterol_similarity instead
          </button>
          <button className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">
            Pick from the catalog
          </button>
        </div>
        <button
          disabled
          className="mt-1 cursor-not-allowed rounded-lg bg-primary/40 px-4 py-2 text-sm font-medium text-primary-foreground"
          title="Resolve to a real objective first"
        >
          Start run
        </button>
        <p className="text-xs text-muted-foreground">
          Runs only start against a real PMO oracle — this keeps every score
          benchmark-comparable.
        </p>
      </CardContent>
    </Card>
  );
}

function GuardrailGallery() {
  const rules: { input: string; msg: string }[] = [
    {
      input: "Objective",
      msg: "Pick or describe an objective — a run can't start without one.",
    },
    {
      input: "Objective",
      msg: 'No benchmark exists for "dissolves in water". Closest is albuterol_similarity.',
    },
    {
      input: "Seed SMILES",
      msg: '"C1CC1(" is invalid — RDKit couldn\'t parse it. Fix or remove it.',
    },
    {
      input: "Budget",
      msg: "Budget must be a positive number — enter at least 1 oracle call.",
    },
  ];
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 py-4">
        <div className="flex items-center gap-2">
          <h2 className="font-heading text-base font-normal">
            Guardrails
          </h2>
          <span className="text-xs text-muted-foreground">FR-015 · mock states</span>
        </div>
        <ul className="flex flex-col gap-2">
          {rules.map((r, i) => (
            <li
              key={i}
              className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs"
            >
              <span aria-hidden="true" className="text-destructive">
                ⚠
              </span>
              <span className="text-foreground">
                <span className="font-medium">{r.input}:</span> {r.msg}
              </span>
            </li>
          ))}
        </ul>
        <Link
          href="/proto/launcher?state=nomatch"
          className="mt-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Preview the no-match resolution →
        </Link>
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs tracking-wide text-muted-foreground uppercase">
        {label}
      </span>
      {children}
    </div>
  );
}
