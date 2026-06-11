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

const TERMINAL = new Set([
  "exhausted",
  "max_generations",
  "no_progress",
  "stopped",
  "errored",
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
        <p className="text-red-600">Failed to load run {runId}: {loadErr}</p>
      </main>
    );
  }

  if (!snap) return <main className="p-8">Loading run {runId}…</main>;

  const running = !TERMINAL.has(snap.status);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">
          Run {snap.run_id} · {snap.task}
        </h1>
        <div className="flex items-center gap-3">
          <Badge variant={running ? "default" : "secondary"}>
            {snap.status}
          </Badge>
          <span className="text-xs text-zinc-500">{conn}</span>
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
            <span className="text-xs text-red-600">{stopErr}</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Generation" value={String(snap.generation_index)} />
        <Stat
          label="Oracle calls"
          value={`${snap.oracle_calls_used} / ${snap.budget}`}
        />
        <Stat
          label="Best score"
          value={snap.best_score?.toFixed(4) ?? "—"}
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
              <XAxis dataKey="oracle_calls" />
              <YAxis domain={[0, 1]} />
              <Line type="monotone" dataKey="top10_mean" dot={false} />
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
                <TableHead>#</TableHead>
                <TableHead>SMILES</TableHead>
                <TableHead>Score</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {snap.top_k.map((m, i) => (
                <TableRow key={m.smiles}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {m.smiles}
                  </TableCell>
                  <TableCell>{m.score.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-xs text-zinc-500">{label}</div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
