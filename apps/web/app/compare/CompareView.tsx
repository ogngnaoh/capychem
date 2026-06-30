"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getCompare, type CompareRun, type ComparePayload } from "@/lib/api";
import { HypothesisSection } from "../runs/[id]/HypothesisSection";

const RUN_A_COLOR = "#2563eb"; // blue-600
const RUN_B_COLOR = "#e11d48"; // rose-600

function runLabel(r: CompareRun): string {
  return `#${r.run_id} · ${r.task}`;
}

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "errored") return "destructive";
  if (status === "running") return "default";
  return "secondary";
}

export function CompareView({ a, b }: { a: number; b: number }) {
  const [payload, setPayload] = useState<ComparePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const valid = Number.isFinite(a) && Number.isFinite(b);

  useEffect(() => {
    if (!valid) return;
    let closed = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPayload(null);
    setError(null);
    getCompare(a, b)
      .then((p) => {
        if (!closed) setPayload(p);
      })
      .catch((e: unknown) => {
        if (!closed) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      closed = true;
    };
  }, [a, b, valid]);

  if (!valid) {
    return (
      <main className="mx-auto max-w-6xl p-8">
        <p className="text-sm text-muted-foreground">
          Select two runs to compare from the{" "}
          <Link href="/runs" className="underline hover:text-foreground">
            runs list
          </Link>
          .
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Compare runs</h1>
        <Link href="/runs" className="text-sm text-muted-foreground hover:text-foreground">
          ← Runs
        </Link>
      </header>

      {error ? (
        <p className="text-sm text-red-600">Failed to load comparison: {error}</p>
      ) : !payload ? (
        <p className="text-sm text-muted-foreground">Loading comparison…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            <RunSummary run={payload.a} color={RUN_A_COLOR} />
            <RunSummary run={payload.b} color={RUN_B_COLOR} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Top-10 mean vs oracle calls</CardTitle>
            </CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={payload.auc_overlay}>
                  <XAxis
                    dataKey="oracle_calls"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    allowDecimals={false}
                  />
                  <YAxis domain={[0, 1]} />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="a"
                    name={runLabel(payload.a)}
                    stroke={RUN_A_COLOR}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="b"
                    name={runLabel(payload.b)}
                    stroke={RUN_B_COLOR}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4">
            <TopKCard run={payload.a} color={RUN_A_COLOR} />
            <TopKCard run={payload.b} color={RUN_B_COLOR} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <HypothesisColumn run={payload.a} />
            <HypothesisColumn run={payload.b} />
          </div>
        </>
      )}
    </main>
  );
}

function RunSummary({ run, color }: { run: CompareRun; color: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block size-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            {runLabel(run)}
          </span>
          <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-4">
        <Stat label="Best score" value={run.best_score?.toFixed(4) ?? "—"} />
        <Stat label="Oracle calls" value={`${run.oracle_calls} / ${run.budget}`} />
        <Stat label="Cost ($)" value={run.cost_so_far_usd.toFixed(4)} />
      </CardContent>
    </Card>
  );
}

function TopKCard({ run, color }: { run: CompareRun; color: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <span
            aria-hidden
            className="inline-block size-3 rounded-full"
            style={{ backgroundColor: color }}
          />
          Top molecules · {runLabel(run)}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">#</TableHead>
              <TableHead>SMILES</TableHead>
              <TableHead className="text-right">Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {run.top_k.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  No molecules.
                </TableCell>
              </TableRow>
            ) : (
              run.top_k.map((m, i) => (
                <TableRow key={m.smiles}>
                  <TableCell className="tabular-nums text-muted-foreground">{i + 1}</TableCell>
                  <TableCell className="font-mono text-xs break-all">{m.smiles}</TableCell>
                  <TableCell className="tabular-nums text-right">{m.score.toFixed(4)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function HypothesisColumn({ run }: { run: CompareRun }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-muted-foreground">
        Analyzer hypotheses · {runLabel(run)}
      </h2>
      {run.hypotheses.length === 0 ? (
        <p className="rounded-xl border border-dashed border-foreground/10 px-4 py-3 text-sm text-muted-foreground">
          No analyzer hypotheses (Graph-GA run).
        </p>
      ) : (
        <HypothesisSection hypotheses={run.hypotheses} />
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
