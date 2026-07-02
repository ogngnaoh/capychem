"use client";

// HI-FI PROTOTYPE — Compare two runs. Two-row selector → overlaid AUC (A = coral /
// chart-1, B = chart-2) + per-run stats + side-by-side top-K. Mock data; slice 03
// wires the live /compare API. Honest framing: same task, LLM (with analyzer) vs
// vanilla Graph-GA — GA carries no hypotheses.

import { Card, CardContent } from "@/components/ui/card";
import type { CompareRun } from "@/lib/api";
import { CompareChart } from "../_chart";
import {
  COMPARE_A,
  COMPARE_B,
  COMPARE_OVERLAY,
  COMPARE_STRATEGY,
  RUNS_LIST,
} from "../_mock";
import { Eyebrow, MoleculeTile } from "../_ui";

export default function CompareProto() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Eyebrow>Compare</Eyebrow>
        <h1 className="font-heading text-2xl font-normal tracking-tight">
          Two runs, side by side
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Overlay the sample-efficiency curves and compare top molecules. Every score is
          an in-silico oracle score.
        </p>
      </div>

      {/* Two-row selector */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <RunSelect swatch="bg-chart-1" label="Run A" selected={COMPARE_A.run_id} />
        <RunSelect swatch="bg-chart-2" label="Run B" selected={COMPARE_B.run_id} />
      </div>

      {/* Overlaid AUC */}
      <Card>
        <CardContent className="flex flex-col gap-1 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-heading text-base font-normal">Sample efficiency</h2>
            <span className="text-xs text-muted-foreground">
              {COMPARE_A.task} · single seed · 10,000-call budget
            </span>
          </div>
          <div className="h-64">
            <CompareChart
              overlay={COMPARE_OVERLAY}
              labelA={`Run ${COMPARE_A.run_id} · ${COMPARE_STRATEGY.a}`}
              labelB={`Run ${COMPARE_B.run_id} · ${COMPARE_STRATEGY.b}`}
            />
          </div>
        </CardContent>
      </Card>

      {/* Per-run stats */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RunColumn run={COMPARE_A} strategy={COMPARE_STRATEGY.a} swatch="bg-chart-1" />
        <RunColumn run={COMPARE_B} strategy={COMPARE_STRATEGY.b} swatch="bg-chart-2" />
      </div>
    </div>
  );
}

function RunSelect({
  label,
  selected,
  swatch,
}: {
  label: string;
  selected: number;
  swatch: string;
}) {
  return (
    <label className="flex items-center gap-3 rounded-xl bg-card px-3.5 py-3 ring-1 ring-foreground/10">
      <span className={`size-2.5 shrink-0 rounded-full ${swatch}`} aria-hidden="true" />
      <span className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        {label}
      </span>
      <select
        defaultValue={selected}
        className="ml-auto h-8 rounded-lg border border-input bg-background px-2.5 text-sm"
      >
        {RUNS_LIST.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            Run {r.run_id} · {r.task} · {r.mutation_strategy === "llm" ? "LLM" : "Graph-GA"}
          </option>
        ))}
      </select>
    </label>
  );
}

function RunColumn({
  run,
  strategy,
  swatch,
}: {
  run: CompareRun;
  strategy: string;
  swatch: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-4">
        <div className="flex items-center gap-2.5">
          <span className={`size-2.5 rounded-full ${swatch}`} aria-hidden="true" />
          <h2 className="font-heading text-base font-normal">Run {run.run_id}</h2>
          <span className="font-mono text-xs text-muted-foreground">{strategy}</span>
        </div>

        <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-lg bg-border">
          <Stat k="Best score" v={run.best_score?.toFixed(4) ?? "—"} />
          <Stat k="Oracle calls" v={run.oracle_calls.toLocaleString()} />
          <Stat k="Cost" v={`$${run.cost_so_far_usd.toFixed(2)}`} />
        </dl>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
              Top molecules
            </span>
            <span className="text-xs text-muted-foreground">
              {run.hypotheses.length > 0
                ? `${run.hypotheses.length} analyzer hypotheses`
                : "no analyzer step"}
            </span>
          </div>
          <ul className="flex flex-col gap-2">
            {run.top_k.map((m, i) => (
              <li
                key={m.smiles}
                className="flex items-start gap-3 rounded-lg border border-border p-2.5"
              >
                <MoleculeTile size={40} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular-nums text-muted-foreground">#{i + 1}</span>
                    <span className="text-sm font-semibold tabular-nums">
                      {m.score.toFixed(4)}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[0.7rem] leading-relaxed break-all text-muted-foreground">
                    {m.smiles}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-card px-3 py-2.5">
      <div className="text-sm font-semibold tabular-nums">{v}</div>
      <div className="mt-0.5 text-[0.68rem] text-muted-foreground">{k}</div>
    </div>
  );
}
