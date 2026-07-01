"use client";

import { useEffect, useRef, useState } from "react";
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getRun, stopRun, wsUrl, type RunSnapshot } from "@/lib/api";
import { applyEvent, type RunEvent } from "@/lib/runEvents";
import { plateauNotice } from "@/lib/plateau";
import { HypothesisSection } from "./HypothesisSection";

const TERMINAL = new Set([
  "exhausted",
  "max_generations",
  "no_progress",
  "stopped",
  "errored",
  "cost_capped",
  "plateaued",
]);

export function LiveRun({ runId }: { runId: number }) {
  const [snap, setSnap] = useState<RunSnapshot | null>(null);
  const [conn, setConn] = useState<"connecting" | "live" | "done">(
    "connecting",
  );
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [stopErr, setStopErr] = useState<string | null>(null);
  const snapRef = useRef<RunSnapshot | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    // Reset view state for the incoming runId so a dep change never shows stale data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSnap(null); setLoadErr(null); setConn("connecting");
    getRun(runId)
      .then((s) => {
        if (closed) return;
        snapRef.current = s;
        setSnap(s);
        if (TERMINAL.has(s.status)) {
          setConn("done");
          return;
        }
        ws = new WebSocket(wsUrl(runId));
        ws.onopen = () => { if (closed) return; setConn("live"); };
        ws.onmessage = (e) => {
          if (closed) return;
          const ev: RunEvent = JSON.parse(e.data as string) as RunEvent;
          if (ev.type === "ping") return;
          const next = applyEvent(snapRef.current!, ev);
          snapRef.current = next;
          setSnap(next);
          if (ev.type === "run.complete") setConn("done");
        };
        ws.onclose = () => { if (closed) return; setConn((c) => (c !== "done" ? "done" : c)); };
      })
      .catch((e: unknown) => {
        if (closed) return;
        setLoadErr(String(e instanceof Error ? e.message : e));
      });

    return () => {
      closed = true;
      ws?.close();
    };
  }, [runId]);

  if (loadErr) {
    return (
      <main className="p-8">
        <p className="text-destructive">Failed to load run {runId}: {loadErr}</p>
      </main>
    );
  }

  if (!snap) return <main className="p-8">Loading run {runId}…</main>;

  const running = !TERMINAL.has(snap.status);
  const notice = plateauNotice(snap.status, snap.plateau_window);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-heading font-normal">
          Run {snap.run_id} · {snap.task}
        </h1>
        <div className="flex items-center gap-3">
          <Badge variant={running ? "default" : "secondary"}>
            {snap.status}
          </Badge>
          <span className="text-xs text-muted-foreground">{conn}</span>
          {snap.trace_url && (
            <a
              href={snap.trace_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              View trace ↗
            </a>
          )}
          {running && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                setStopErr(null);
                stopRun(runId).catch((e: unknown) =>
                  setStopErr(
                    String(e instanceof Error ? e.message : e),
                  ),
                );
              }}
            >
              Stop
            </Button>
          )}
          {stopErr && (
            <span className="text-xs text-destructive">{stopErr}</span>
          )}
        </div>
      </div>

      {notice && (
        <div className="rounded-md border border-chart-4/40 bg-chart-4/10 px-4 py-3 text-sm text-foreground">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-4 gap-4">
        <Stat label="Generation" value={String(snap.generation_index)} />
        <Stat
          label="Oracle calls"
          value={`${snap.oracle_calls_used} / ${snap.budget}`}
        />
        <Stat
          label="Best score"
          value={snap.best_score?.toFixed(4) ?? "—"}
        />
        <Stat
          label="Cost ($)"
          value={(snap.cost_so_far_usd ?? 0).toFixed(4)}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Top-10 mean vs oracle calls
          </CardTitle>
        </CardHeader>
        <CardContent className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={snap.auc_curve}>
              <XAxis
                dataKey="oracle_calls"
                type="number"
                domain={["dataMin", "dataMax"]}
                allowDecimals={false}
              />
              <YAxis domain={[0, 1]} />
              <Line
                type="monotone"
                dataKey="top10_mean"
                stroke="#cc785c"
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Top molecules</CardTitle>
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
              {snap.top_k.map((m, i) => (
                <TableRow key={m.smiles}>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {i + 1}
                  </TableCell>
                  <TableCell className="font-mono text-xs whitespace-normal break-all">
                    {m.smiles}
                  </TableCell>
                  <TableCell className="tabular-nums text-right">
                    {m.score.toFixed(4)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <HypothesisSection hypotheses={snap.hypotheses ?? []} />
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
