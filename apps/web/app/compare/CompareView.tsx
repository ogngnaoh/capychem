"use client";

// Compare two runs — ported from app/proto/compare, wired to GET /compare (a, b from the
// URL). Two-row selector (populated from GET /runs) → overlaid AUC (A = chart-1 coral,
// B = chart-2 blue) + per-run stats + side-by-side top-K molecule tiles. Honest framing:
// a Graph-GA run carries no analyzer hypotheses ("no analyzer step"). Every score in-silico.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  getCompare,
  listRuns,
  type CompareRun,
  type ComparePayload,
  type RunListItem,
} from "@/lib/api";
import { CompareChart } from "@/components/workbench/charts";
import { Eyebrow, MoleculeTile } from "@/components/workbench/ui";

const strategyLabel = (s: string) => (s === "llm" ? "LLM proposer" : "Graph-GA");

function strategyFor(runs: RunListItem[], id: number): string | undefined {
  const s = runs.find((r) => r.run_id === id)?.mutation_strategy;
  return s ? strategyLabel(s) : undefined;
}

export function CompareView({ a, b }: { a: number; b: number }) {
  const [payload, setPayload] = useState<ComparePayload | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const valid = Number.isFinite(a) && Number.isFinite(b);

  useEffect(() => {
    let closed = false;
    listRuns({ sort: "started_at", order: "desc" })
      .then((r) => !closed && setRuns(r))
      .catch(() => !closed && setRunsError("Couldn't load runs."));
    return () => {
      closed = true;
    };
  }, []);

  useEffect(() => {
    if (!valid) return;
    let closed = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPayload(null);
    setError(null);
    getCompare(a, b)
      .then((p) => !closed && setPayload(p))
      .catch((e: unknown) => !closed && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      closed = true;
    };
  }, [a, b, valid]);

  if (!valid) {
    return (
      <p className="text-sm text-muted-foreground">
        Select two runs to compare from the{" "}
        <Link href="/runs" className="underline decoration-border underline-offset-4 hover:text-foreground">
          runs list
        </Link>
        .
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Eyebrow>Compare</Eyebrow>
        <h1 className="font-heading text-2xl font-normal tracking-tight">
          Two runs, side by side
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Overlay the sample-efficiency curves and compare top molecules. Every score is an
          in-silico oracle score.
        </p>
      </div>

      {/* Two-row selector */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <RunSelect swatch="bg-chart-1" label="Run A" self={a} other={b} runs={runs} slot="a" />
        <RunSelect swatch="bg-chart-2" label="Run B" self={b} other={a} runs={runs} slot="b" />
      </div>
      {runsError && (
        <p role="alert" className="text-sm text-destructive">
          {runsError}
        </p>
      )}

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          Failed to load comparison: {error}
        </p>
      ) : !payload ? (
        <p className="text-sm text-muted-foreground">Loading comparison…</p>
      ) : (
        <>
          {/* Overlaid AUC */}
          <Card>
            <CardContent className="flex flex-col gap-1 py-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-heading text-base font-normal">Sample efficiency</h2>
                <span className="text-xs text-muted-foreground">
                  {payload.a.task} · single seed · {payload.a.budget.toLocaleString()}-call budget
                </span>
              </div>
              <div className="h-64">
                <CompareChart
                  overlay={payload.auc_overlay}
                  labelA={`Run ${payload.a.run_id} · ${payload.a.task}`}
                  labelB={`Run ${payload.b.run_id} · ${payload.b.task}`}
                />
              </div>
            </CardContent>
          </Card>

          {/* Per-run stats */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <RunColumn run={payload.a} swatch="bg-chart-1" strategy={strategyFor(runs, payload.a.run_id)} />
            <RunColumn run={payload.b} swatch="bg-chart-2" strategy={strategyFor(runs, payload.b.run_id)} />
          </div>
        </>
      )}
    </div>
  );
}

function RunSelect({
  label,
  self,
  other,
  runs,
  slot,
  swatch,
}: {
  label: string;
  self: number;
  other: number;
  runs: RunListItem[];
  slot: "a" | "b";
  swatch: string;
}) {
  const router = useRouter();
  function onChange(next: number) {
    const a = slot === "a" ? next : other;
    const b = slot === "b" ? next : other;
    router.push(`/compare?a=${a}&b=${b}`);
  }
  const options = runs.length > 0 ? runs : ([] as RunListItem[]);
  return (
    <label className="flex items-center gap-3 rounded-xl bg-card px-3.5 py-3 ring-1 ring-foreground/10">
      <span className={`size-2.5 shrink-0 rounded-full ${swatch}`} aria-hidden="true" />
      <span className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        {label}
      </span>
      <select
        aria-label={label}
        value={Number.isFinite(self) ? self : ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className="ml-auto h-8 max-w-[70%] rounded-lg border border-input bg-background px-2.5 text-sm"
      >
        {!options.some((r) => r.run_id === self) && Number.isFinite(self) && (
          <option value={self}>Run {self}</option>
        )}
        {options.map((r) => (
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
  swatch,
  strategy,
}: {
  run: CompareRun;
  swatch: string;
  strategy?: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className={`size-2.5 rounded-full ${swatch}`} aria-hidden="true" />
          <h2 className="font-heading text-base font-normal">Run {run.run_id}</h2>
          <span className="font-mono text-xs text-muted-foreground">{run.task}</span>
          {strategy && (
            <span className="rounded-full border border-border px-2 py-0.5 text-[0.68rem] text-muted-foreground">
              {strategy}
            </span>
          )}
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
                ? `${run.hypotheses.length} analyzer ${run.hypotheses.length === 1 ? "hypothesis" : "hypotheses"}`
                : "no analyzer step"}
            </span>
          </div>
          {run.top_k.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              No molecules.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {run.top_k.map((m, i) => (
                <li
                  key={m.smiles}
                  className="flex items-start gap-3 rounded-lg border border-border p-2.5"
                >
                  <MoleculeTile smiles={m.smiles} size={40} rank={i + 1} />
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
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-card px-3 py-2.5">
      <dd className="text-sm font-semibold tabular-nums">{v}</dd>
      <dt className="mt-0.5 text-[0.68rem] text-muted-foreground">{k}</dt>
    </div>
  );
}
