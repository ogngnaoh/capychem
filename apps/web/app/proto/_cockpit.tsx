"use client";

// LOW-FI PROTOTYPE — Workbench cockpit (the star). One run, live -> completed.
// Hero decision (spec §8): analyzer REASONING is the hero panel (left, wider);
// AUC-vs-Graph-GA is co-primary (right). Both sit above the top-molecules block.
// Generation-level granularity only (WS carries no per-candidate stream).

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { RunSnapshot } from "@/lib/api";
import { AucPanel } from "./_chart";
import {
  GA_BASELINE_AUC,
  IMPROVED_ROWS_COMPLETED,
  IMPROVED_ROWS_RUNNING,
  RUN_STRATEGY,
  VALID_SMILES_RATE_COMPLETED,
  VALID_SMILES_RATE_RUNNING,
} from "./_mock";
import { LoopDiagram, MoleculeTile, StatTile, Meter } from "./_ui";

export function Cockpit({
  snap,
  running,
}: {
  snap: RunSnapshot;
  running: boolean;
}) {
  const improved = running ? IMPROVED_ROWS_RUNNING : IMPROVED_ROWS_COMPLETED;
  const validRate = running
    ? VALID_SMILES_RATE_RUNNING
    : VALID_SMILES_RATE_COMPLETED;
  const hyps = [...(snap.hypotheses ?? [])].sort(
    (a, b) => b.after_generation_index - a.after_generation_index,
  );
  const current = hyps[0];
  const prior = hyps.slice(1);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="font-heading text-2xl font-normal">
          Run {snap.run_id}
        </h1>
        <span className="font-mono text-sm text-muted-foreground">
          {snap.task}
        </span>
        <Badge variant={running ? "default" : "secondary"}>
          {running && (
            <span
              className="mr-1 inline-block size-1.5 rounded-full bg-primary-foreground motion-safe:animate-pulse"
              aria-hidden="true"
            />
          )}
          {snap.status}
        </Badge>
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {RUN_STRATEGY}
        </span>
        <div className="ml-auto flex items-center gap-3">
          {snap.trace_url && (
            <a
              href={snap.trace_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              View trace ↗
            </a>
          )}
          {running ? (
            <Button size="sm" variant="destructive">
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled title="Lands in a later slice">
              Spawn follow-up run
            </Button>
          )}
        </div>
      </div>

      {/* Live loop-step indicator (cockpit only) */}
      <LoopDiagram activeStep={running ? "analyze" : "stop"} compact />

      {/* Vitals */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile label="Generation" value={String(snap.generation_index)} />
        <div className="rounded-lg bg-card px-3 py-2.5 ring-1 ring-foreground/10">
          <div className="text-[0.7rem] tracking-wide text-muted-foreground uppercase">
            Oracle calls
          </div>
          <div className="mt-0.5 text-xl font-semibold tabular-nums">
            {snap.oracle_calls_used.toLocaleString()}
            <span className="text-sm font-normal text-muted-foreground">
              {" "}
              / {snap.budget.toLocaleString()}
            </span>
          </div>
          <Meter value={snap.oracle_calls_used} max={snap.budget} />
        </div>
        <StatTile
          label="Best score"
          value={snap.best_score?.toFixed(4) ?? "—"}
          sub="in-silico oracle"
          accent
        />
        <StatTile
          label="Cost"
          value={`$${(snap.cost_so_far_usd ?? 0).toFixed(2)}`}
          sub="compute equiv."
        />
        <StatTile
          label="Valid SMILES"
          value={`${Math.round(validRate * 100)}%`}
          sub="RDKit-validated"
        />
      </div>

      {/* Reasoning (hero) + AUC (co-primary) */}
      <section className="grid gap-4 lg:h-[430px] lg:grid-cols-[1.5fr_1fr]">
        {/* Analyzer reasoning — prime real estate */}
        <Card className="flex h-full flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 pb-2">
            <div className="flex items-center gap-2">
              <h2 className="font-heading text-base font-normal">
                Analyzer reasoning
              </h2>
              <span className="rounded-full bg-primary/12 px-2 py-0.5 text-[0.7rem] text-primary ring-1 ring-primary/30">
                the differentiator
              </span>
            </div>
            <span className="text-xs text-muted-foreground">
              per generation
            </span>
          </div>

          {current ? (
            <div className="mx-4 rounded-lg border border-primary/40 bg-primary/5 p-3">
              <div className="text-xs tracking-wide text-primary uppercase">
                Current hypothesis · after gen {current.after_generation_index}
              </div>
              <p className="mt-1.5 text-sm text-foreground">{current.text}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {current.structured_json?.focus && (
                  <Badge variant="secondary">
                    focus: {current.structured_json.focus}
                  </Badge>
                )}
                {(current.structured_json?.avoid ?? []).map((a, i) => (
                  <Badge key={`${i}-${a}`} variant="outline">
                    avoid: {a}
                  </Badge>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-4 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
              No hypothesis yet — the analyzer runs after generation 1.
            </div>
          )}

          <div className="mt-3 flex min-h-0 flex-1 flex-col px-4 pb-4">
            <div className="text-xs tracking-wide text-muted-foreground uppercase">
              Earlier hypotheses
            </div>
            <ol className="mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {prior.length === 0 && (
                <li className="text-xs text-muted-foreground">
                  Prior hypotheses will stack here as generations complete.
                </li>
              )}
              {prior.map((h) => (
                <li
                  key={h.after_generation_index}
                  className="rounded-md border border-border px-3 py-2"
                >
                  <div className="text-xs font-medium text-muted-foreground">
                    after gen {h.after_generation_index}
                  </div>
                  <p className="mt-1 text-sm text-foreground">{h.text}</p>
                  {h.structured_json?.focus && (
                    <div className="mt-1 text-xs text-muted-foreground">
                      focus: {h.structured_json.focus}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </Card>

        {/* AUC vs Graph-GA */}
        <Card className="flex h-full flex-col">
          <div className="px-4 pb-1">
            <h2 className="font-heading text-base font-normal">
              Sample efficiency vs Graph-GA
            </h2>
          </div>
          <div className="min-h-0 flex-1 px-4 pb-4">
            <AucPanel
              curve={snap.auc_curve}
              baseline={GA_BASELINE_AUC}
              running={running}
            />
          </div>
        </Card>
      </section>

      {/* Top molecules */}
      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <h2 className="font-heading text-base font-normal">Top molecules</h2>
          <span className="text-xs text-muted-foreground">
            2D structure · SMILES · in-silico oracle score
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {snap.top_k.map((m, i) => {
            const isImproved = improved.has(i);
            return (
              <div
                key={m.smiles}
                className={[
                  "flex items-start gap-3 rounded-lg bg-card p-3 ring-1 ring-foreground/10",
                  isImproved ? "border-l-2 border-primary" : "",
                ].join(" ")}
              >
                <MoleculeTile />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular-nums text-muted-foreground">
                      #{i + 1}
                    </span>
                    <span className="tabular-nums text-sm font-semibold">
                      {m.score.toFixed(4)}
                    </span>
                    {isImproved && (
                      <span className="rounded-full bg-primary/12 px-1.5 py-0.5 text-[0.65rem] text-primary ring-1 ring-primary/30">
                        ↑ improved
                      </span>
                    )}
                  </div>
                  <div className="mt-1 font-mono text-xs break-all text-muted-foreground">
                    {m.smiles}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <p className="text-xs text-muted-foreground">
        Every score above is an in-silico oracle / benchmark score.{" "}
        <Link href="/proto/overview" className="underline underline-offset-2">
          What is this?
        </Link>
      </p>
    </div>
  );
}
