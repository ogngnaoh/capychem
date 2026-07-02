// LOW-FI PROTOTYPE — Overview (home). The "what is this" surface: a newcomer
// should grasp what CapyChem is and name the loop's steps within ~15s.

import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import {
  CATALOG,
  CATALOG_COUNT,
  RECENT_RUNS,
} from "../_mock";
import { InSilicoTag, LoopDiagram } from "../_ui";

export default function OverviewProto() {
  return (
    <div className="flex flex-col gap-10">
      {/* Hero */}
      <section className="flex flex-col gap-4">
        <div className="text-xs tracking-widest text-muted-foreground uppercase">
          In-silico benchmark · PMO
        </div>
        <h1 className="max-w-3xl font-heading text-4xl leading-tight font-normal">
          An agent that designs, scores, and{" "}
          <span className="text-primary">reasons about</span> molecules — to hit an
          objective in as few oracle calls as possible.
        </h1>
        <p className="max-w-2xl text-base text-muted-foreground">
          CapyChem runs a closed optimization loop over standardized in-silico
          oracles from the PMO benchmark, and is measured against a strong Graph-GA
          baseline. It reads SMILES and 2D structures; every number here is a
          benchmark oracle score, never a real-world efficacy claim.
        </p>
        <div className="mt-1 flex items-center gap-3">
          <Link
            href="/proto/launcher"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Start a run
          </Link>
          <Link
            href="/proto/runs"
            className="rounded-lg border border-border px-4 py-2 text-sm text-foreground hover:bg-muted"
          >
            Browse runs
          </Link>
          <InSilicoTag className="ml-1" />
        </div>
      </section>

      {/* The loop */}
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-heading text-xl font-normal">The loop</h2>
          <span className="text-sm text-muted-foreground">
            Analyze is the step a plain mutation loop (Graph-GA / MOLLEO) skips.
          </span>
        </div>
        <Card>
          <CardContent className="py-5">
            <LoopDiagram />
            <p className="mt-4 max-w-3xl text-sm text-muted-foreground">
              Each generation, the agent <strong>proposes</strong> candidates,{" "}
              <strong>scores</strong> them against the oracle,{" "}
              <strong className="text-primary">analyzes</strong> what moved the
              score into a written hypothesis, then <strong>redesigns</strong> the
              next batch conditioned on it — <strong>stopping</strong> at budget or
              plateau.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Rigor strip + recent runs */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardContent className="flex flex-col gap-3 py-5">
            <div className="flex items-center gap-2">
              <h2 className="font-heading text-xl font-normal">
                Benchmark result
              </h2>
              <InSilicoTag />
            </div>
            <p className="text-sm text-foreground">
              Beats or matches vanilla Graph-GA on{" "}
              <strong>all 21 comparable PMO tasks</strong> by AUC of top-10 (single
              seed, 10,000-call budget); the margin is{" "}
              <strong>decisive (~0.1 AUC+) on 9</strong> of them. 2 of 23 tasks are
              excluded for cause (defective oracles, not losses). The bar was ≥6/23.
            </p>
            <div className="mt-1 flex flex-wrap gap-2 text-xs">
              <Figure k="Comparable tasks" v="21" />
              <Figure k="Decisive wins" v="9" />
              <Figure k="Excluded for cause" v="2" />
              <Figure k="Bar" v="≥6/23" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-2 py-5">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-xl font-normal">Recent runs</h2>
              <Link
                href="/proto/runs"
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                All runs →
              </Link>
            </div>
            <ul className="flex flex-col divide-y divide-border">
              {RECENT_RUNS.map((r) => (
                <li
                  key={r.run_id}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm">{r.task}</div>
                    <div className="text-xs text-muted-foreground">
                      Run {r.run_id} ·{" "}
                      {r.mutation_strategy === "llm" ? "LLM" : "Graph-GA"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <span
                      className={
                        r.status === "running"
                          ? "text-primary"
                          : "text-muted-foreground"
                      }
                    >
                      {r.status}
                    </span>
                    <span className="tabular-nums font-medium">
                      {r.best_score?.toFixed(4) ?? "—"}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-1 rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
              Your investigations — grouping runs into campaigns lands later.
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Objective catalog peek */}
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-heading text-xl font-normal">What can I ask for?</h2>
          <Link
            href="/proto/launcher"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            See all {CATALOG_COUNT} objectives →
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {CATALOG.map((g) => (
            <Card key={g.key}>
              <CardContent className="flex flex-col gap-2 py-4">
                <div className="text-sm font-medium">{g.label}</div>
                <div className="text-xs text-muted-foreground">{g.hint}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {g.objectives.slice(0, 3).map((o) => (
                    <span
                      key={o.task}
                      className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.7rem] text-foreground"
                    >
                      {o.task}
                    </span>
                  ))}
                  {g.objectives.length > 3 && (
                    <span className="text-[0.7rem] text-muted-foreground">
                      +{g.objectives.length - 3} more
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

function Figure({ k, v }: { k: string; v: string }) {
  return (
    <span className="rounded-md bg-muted px-2 py-1">
      <span className="font-semibold tabular-nums">{v}</span>{" "}
      <span className="text-muted-foreground">{k}</span>
    </span>
  );
}
