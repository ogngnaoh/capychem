"use client";

// Overview (home) — the "what is this" surface: a newcomer should grasp what CapyChem
// is and name the loop's steps within ~15s. Ported from app/proto/overview; the recent
// runs come from GET /runs and the catalog peek from GET /catalog. The benchmark-result
// figure canon is verbatim and honest (N6): in-silico scores, never an efficacy claim.

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ModeBadge } from "@/components/ModeBadge";
import { getCatalog, listRuns, type CatalogGroup, type RunListItem } from "@/lib/api";
import { Eyebrow, InSilicoTag, LoopDiagram, StatusChip } from "@/components/workbench/ui";

export function Overview() {
  const [catalog, setCatalog] = useState<CatalogGroup[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RunListItem[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);

  useEffect(() => {
    let closed = false;
    getCatalog()
      .then((g) => !closed && setCatalog(g))
      .catch(() => !closed && setCatalogError("Couldn't load the task catalog."));
    listRuns({ sort: "started_at", order: "desc" })
      .then((r) => !closed && setRecent(r.slice(0, 4)))
      .catch(() => !closed && setRecentError("Couldn't load runs."));
    return () => {
      closed = true;
    };
  }, []);

  const taskCount = catalog.reduce((n, g) => n + g.tasks.length, 0);

  return (
    <div className="flex flex-col gap-14">
      {/* Hero */}
      <section className="grid grid-cols-1 items-center gap-8 pt-2 lg:grid-cols-[1.5fr_1fr]">
        <div className="flex flex-col gap-5">
          <Eyebrow>In-silico benchmark · PMO</Eyebrow>
          <h1 className="max-w-3xl font-heading text-[2.6rem] leading-[1.08] font-normal tracking-tight">
            An agent that designs, scores, and{" "}
            <span className="text-primary">reasons about</span> molecules — to hit an
            objective in as few oracle calls as possible.
          </h1>
          <p className="max-w-2xl text-base leading-relaxed text-muted-foreground">
            CapyChem runs a closed optimization loop over standardized in-silico oracles
            from the PMO benchmark, measured against a strong Graph-GA baseline. It reads
            SMILES and 2D structures; every number here is a benchmark oracle score, never
            a real-world efficacy claim.
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <Link
              href="/launch"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              Start a run
            </Link>
            <Link
              href="/runs"
              className="rounded-lg border border-border px-4 py-2 text-sm text-foreground transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              Browse runs
            </Link>
            <InSilicoTag className="ml-1" />
          </div>
        </div>
        <LatestRunPeek run={recent[0]} error={recentError} />
      </section>

      {/* The loop */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-heading text-xl font-normal tracking-tight">The loop</h2>
          <span className="text-sm text-muted-foreground">
            Analyze is the step a plain mutation loop (Graph-GA / MOLLEO) skips.
          </span>
        </div>
        <Card>
          <CardContent className="flex flex-col gap-4 py-5">
            <LoopDiagram />
            <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
              Each generation, the agent{" "}
              <strong className="font-medium text-foreground">proposes</strong> candidates,{" "}
              <strong className="font-medium text-foreground">scores</strong> them against the
              oracle, <strong className="font-medium text-foreground">analyzes</strong> what moved
              the score into a written hypothesis, then{" "}
              <strong className="font-medium text-foreground">redesigns</strong> the next batch
              conditioned on it —{" "}
              <strong className="font-medium text-foreground">stopping</strong> at budget or
              plateau.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Rigor strip + recent runs */}
      <section className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardContent className="flex flex-col gap-4 py-5">
            <div className="flex items-center gap-2.5">
              <h2 className="font-heading text-xl font-normal tracking-tight">
                Benchmark result
              </h2>
              <InSilicoTag />
            </div>
            <p className="text-sm leading-relaxed text-foreground">
              Beats or matches vanilla Graph-GA on{" "}
              <strong className="font-medium">all 21 comparable PMO tasks</strong> by AUC of
              top-10 (single seed, 10,000-call budget); the margin is{" "}
              <strong className="font-medium">decisive (&gt;0.1 AUC) on 8</strong> of them. 2 of 23
              tasks are excluded for cause (defective oracles, not losses). The bar was ≥6/23.
            </p>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-border sm:grid-cols-4">
              <Figure k="Comparable" v="21" />
              <Figure k="Decisive wins" v="8" />
              <Figure k="Excluded for cause" v="2" />
              <Figure k="Bar to clear" v="≥6/23" />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-3 py-5">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-xl font-normal tracking-tight">Recent runs</h2>
              <Link href="/runs" className="text-sm text-muted-foreground hover:text-foreground">
                All runs →
              </Link>
            </div>
            {recentError ? (
              <p
                role="alert"
                className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-destructive"
              >
                {recentError}
              </p>
            ) : recent.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
                No runs yet.{" "}
                <Link
                  href="/launch"
                  className="underline decoration-border underline-offset-4 hover:text-foreground"
                >
                  Start one
                </Link>{" "}
                to see it here.
              </p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {recent.map((r) => (
                  <li key={r.run_id}>
                    <Link
                      href={`/runs/${r.run_id}`}
                      className="flex items-center justify-between gap-3 py-2.5 hover:opacity-80"
                    >
                      <div className="min-w-0">
                        <div className="truncate font-mono text-xs text-foreground">{r.task}</div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <span className="shrink-0">
                            Run {r.run_id} · {r.mutation_strategy === "llm" ? "LLM" : "Graph-GA"}
                          </span>
                          {/* Compact badge in this dense list — the full "not
                              benchmark-comparable" clause stays in its tooltip. */}
                          <ModeBadge mode={r.mode} compact />
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <StatusChip status={r.status} />
                        <span className="w-14 text-right text-sm font-semibold tabular-nums">
                          {r.best_score?.toFixed(4) ?? "—"}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Objective catalog peek */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-heading text-xl font-normal tracking-tight">
            What can I ask for?
          </h2>
          <Link href="/launch" className="text-sm text-muted-foreground hover:text-foreground">
            See all {taskCount || 23} objectives →
          </Link>
        </div>
        {catalogError ? (
          <p role="alert" className="text-sm text-destructive">
            {catalogError}
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {catalog.map((g) => (
              <Card key={g.group}>
                <CardContent className="flex h-full flex-col gap-2 py-4">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="text-sm font-medium">{g.group}</div>
                    <span className="shrink-0 text-[0.7rem] tabular-nums text-muted-foreground">
                      {g.tasks.length} {g.tasks.length === 1 ? "objective" : "objectives"}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {g.tasks.slice(0, 3).map((t) => (
                      <span
                        key={t.name}
                        className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.7rem] text-foreground"
                      >
                        {t.name}
                      </span>
                    ))}
                    {g.tasks.length > 3 && (
                      <span className="self-center text-[0.7rem] text-muted-foreground">
                        +{g.tasks.length - 3} more
                      </span>
                    )}
                  </div>
                  <Link
                    href="/launch"
                    className="mt-auto pt-1 text-[0.7rem] text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
                  >
                    Launch one →
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Figure({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-card px-3 py-2.5">
      <dd className="text-lg font-semibold tabular-nums">{v}</dd>
      <dt className="mt-0.5 text-[0.7rem] text-muted-foreground">{k}</dt>
    </div>
  );
}

// Hero right-column peek at the most recent run — dynamic content instead of dead space.
// Falls back to a teaching card (the loop) when there are no runs yet.
function LatestRunPeek({ run, error }: { run?: RunListItem; error: string | null }) {
  if (error || !run) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-3 py-5">
          <Eyebrow>The closed loop</Eyebrow>
          <LoopDiagram compact />
          <p className="text-xs leading-relaxed text-muted-foreground">
            {error
              ? "Couldn't reach the run history — the loop still runs propose → score → analyze → redesign each generation."
              : "No runs yet. Start one to watch a generation land, then the analyzer's hypothesis, live."}
          </p>
          <Link
            href="/launch"
            className="text-sm text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground"
          >
            Start a run →
          </Link>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-5">
        <div className="flex items-center justify-between">
          <Eyebrow>Latest run</Eyebrow>
          <StatusChip status={run.status} />
        </div>
        <Link href={`/runs/${run.run_id}`} className="group flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-foreground group-hover:underline">
              {run.task}
            </span>
            <ModeBadge mode={run.mode} compact />
          </div>
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
                Best score
              </div>
              <div className="mt-0.5 text-2xl leading-none font-semibold tabular-nums">
                {run.best_score?.toFixed(4) ?? "—"}
              </div>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <div className="tabular-nums">
                {run.oracle_calls.toLocaleString()} / {run.budget.toLocaleString()}
              </div>
              <div>oracle calls</div>
            </div>
          </div>
        </Link>
        <Link
          href="/runs"
          className="text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
        >
          All runs →
        </Link>
      </CardContent>
    </Card>
  );
}
