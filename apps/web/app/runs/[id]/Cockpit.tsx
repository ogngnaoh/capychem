"use client";

// Workbench cockpit (the star) — one run, live → completed. Ported from app/proto/_cockpit
// and wired to the live run snapshot. Analyzer REASONING is the hero (left, 1.5fr); AUC vs
// the Graph-GA baseline is co-primary (right, 1fr). Generation-level granularity only (the
// WS carries no per-candidate stream). Presentational: LiveRun owns the data-flow.

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { RunSnapshot } from "@/lib/api";
import { AucPanel } from "@/components/workbench/charts";
import {
  Eyebrow,
  LoopDiagram,
  Meter,
  MoleculeTile,
  StatTile,
  StatusChip,
} from "@/components/workbench/ui";

export function Cockpit({
  snap,
  running,
  conn,
  onStop,
  stopErr,
  notice,
}: {
  snap: RunSnapshot;
  running: boolean;
  conn: "connecting" | "live" | "done";
  onStop: () => void;
  stopErr: string | null;
  notice: string | null;
}) {
  const validRate = snap.valid_smiles_rate ?? null;
  const baseline = snap.graph_ga_baseline ?? null;
  const hyps = [...(snap.hypotheses ?? [])].sort(
    (a, b) => b.after_generation_index - a.after_generation_index,
  );
  const current = hyps[0];
  const prior = hyps.slice(1);
  const costSub =
    snap.llm_cost_usd != null && snap.oracle_cost_usd != null
      ? `LLM $${snap.llm_cost_usd.toFixed(2)} · oracle $${snap.oracle_cost_usd.toFixed(2)}`
      : "compute equiv.";

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="font-heading text-2xl font-normal tracking-tight">Run {snap.run_id}</h1>
          <span className="font-mono text-sm text-muted-foreground">{snap.task}</span>
          <StatusChip status={snap.status} />
          <span className="text-xs text-muted-foreground">{conn}</span>
          <div className="ml-auto flex items-center gap-3">
            {snap.trace_url && (
              <a
                href={snap.trace_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
              >
                View trace ↗
              </a>
            )}
            {running ? (
              <Button size="sm" variant="destructive" onClick={onStop}>
                Stop
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled title="Lands in a later slice">
                Spawn follow-up run
              </Button>
            )}
          </div>
        </div>
        {stopErr && <span className="text-xs text-destructive">{stopErr}</span>}
        {notice && (
          <div className="rounded-lg border border-chart-4/40 bg-chart-4/10 px-4 py-3 text-sm text-foreground">
            {notice}
          </div>
        )}
        {/* Live loop-step indicator (cockpit only) */}
        <LoopDiagram activeStep={running ? "analyze" : "stop"} compact />
      </div>

      {/* Vitals */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile label="Generation" value={String(snap.generation_index)} />
        <div className="rounded-xl bg-card px-3.5 py-3 ring-1 ring-foreground/10">
          <div className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
            Oracle calls
          </div>
          <div className="mt-1 text-2xl leading-none font-semibold tabular-nums">
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
          sub={costSub}
        />
        <StatTile
          label="Valid SMILES"
          value={validRate != null ? `${Math.round(validRate * 100)}%` : "—"}
          sub="RDKit-validated"
        />
      </div>

      {/* Reasoning (hero) + AUC (co-primary) */}
      <section className="grid gap-4 lg:h-[430px] lg:grid-cols-[1.5fr_1fr]">
        {/* Analyzer reasoning — prime real estate */}
        <Card className="flex h-full flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 pb-1">
            <div className="flex items-center gap-2">
              <h2 className="font-heading text-base font-normal">Analyzer reasoning</h2>
              <span className="rounded-full bg-primary/12 px-2 py-0.5 text-[0.68rem] font-medium text-primary ring-1 ring-primary/30">
                the differentiator
              </span>
            </div>
            <span className="text-xs text-muted-foreground">per generation</span>
          </div>

          {current ? (
            <div className="mx-4 rounded-lg border border-primary/40 bg-primary/[0.06] p-3.5">
              <Eyebrow>Current hypothesis · after gen {current.after_generation_index}</Eyebrow>
              <p className="mt-2 text-sm leading-relaxed text-foreground">{current.text}</p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {current.structured_json?.focus && (
                  <Badge variant="secondary">focus: {current.structured_json.focus}</Badge>
                )}
                {(current.structured_json?.avoid ?? []).map((a, i) => (
                  <Badge key={`${i}-${a}`} variant="outline">
                    avoid: {a}
                  </Badge>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-4 rounded-lg border border-dashed border-border p-3.5 text-sm text-muted-foreground">
              No hypothesis yet — the analyzer runs after generation 1.
            </div>
          )}

          <div className="mt-4 flex min-h-0 flex-1 flex-col px-4 pb-4">
            <Eyebrow>Earlier hypotheses</Eyebrow>
            <ol className="mt-2.5 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {prior.length === 0 && (
                <li className="text-xs text-muted-foreground">
                  Prior hypotheses stack here as generations complete.
                </li>
              )}
              {prior.map((h) => (
                <li
                  key={h.after_generation_index}
                  className="rounded-lg border border-border px-3 py-2.5"
                >
                  <div className="text-[0.7rem] font-medium tracking-wide text-muted-foreground">
                    AFTER GEN {h.after_generation_index}
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-foreground">{h.text}</p>
                  {h.structured_json?.focus && (
                    <div className="mt-1.5 text-xs text-muted-foreground">
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
          <div className="px-4 pb-2">
            <h2 className="font-heading text-base font-normal">
              Sample efficiency vs Graph-GA
            </h2>
          </div>
          <div className="min-h-0 flex-1 px-4 pb-4">
            <AucPanel curve={snap.auc_curve} baseline={baseline} running={running} />
          </div>
        </Card>
      </section>

      {/* Top molecules */}
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-heading text-base font-normal">Top molecules</h2>
          <span className="text-xs text-muted-foreground">
            2D structure · SMILES · in-silico oracle score
          </span>
        </div>
        {snap.top_k.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            No molecules scored yet.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {snap.top_k.map((m, i) => (
              <div
                key={m.smiles}
                className="flex items-start gap-3 rounded-xl bg-card p-3 ring-1 ring-foreground/10"
              >
                <MoleculeTile smiles={m.smiles} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular-nums text-muted-foreground">#{i + 1}</span>
                    <span className="text-sm font-semibold tabular-nums">{m.score.toFixed(4)}</span>
                  </div>
                  <div className="mt-1.5 font-mono text-xs leading-relaxed break-all text-muted-foreground">
                    {m.smiles}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        Every score above is an in-silico oracle / benchmark score.{" "}
        <Link href="/" className="underline decoration-border underline-offset-4">
          What is this?
        </Link>
      </p>
    </div>
  );
}
