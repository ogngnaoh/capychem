"use client";

// Data-flow shell for the cockpit: GET /runs/{id} for the snapshot, then open the WS for
// non-terminal runs (terminal statuses skip the socket). The `applyEvent` reducer folds
// generation.complete / analyzer.hypothesis / run.complete into the snapshot; the server
// replays the last N events on connect so a reload doesn't lose context. Rendering lives
// in Cockpit; this component owns the socket, the Stop action, and the plateau notice.

import { useEffect, useRef, useState } from "react";
import { getRun, stopRun, wsUrl, type RunSnapshot } from "@/lib/api";
import { applyEvent, type RunEvent } from "@/lib/runEvents";
import { plateauNotice } from "@/lib/plateau";
import { Cockpit } from "./Cockpit";

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
  const [conn, setConn] = useState<"connecting" | "live" | "done">("connecting");
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
      <p className="text-destructive">
        Failed to load run {runId}: {loadErr}
      </p>
    );
  }

  if (!snap) return <p className="text-muted-foreground">Loading run {runId}…</p>;

  const running = !TERMINAL.has(snap.status);
  const notice = plateauNotice(snap.status, snap.plateau_window);

  function onStop() {
    setStopErr(null);
    stopRun(runId).catch((e: unknown) =>
      setStopErr(String(e instanceof Error ? e.message : e)),
    );
  }

  return (
    <Cockpit
      snap={snap}
      running={running}
      conn={conn}
      onStop={onStop}
      stopErr={stopErr}
      notice={notice}
    />
  );
}
