"use client";

// Data-flow shell for the cockpit: GET /runs/{id} for the snapshot, then open the WS for
// non-terminal runs (terminal statuses skip the socket). The `applyEvent` reducer folds
// generation.complete / analyzer.hypothesis / run.complete into the snapshot. The server
// streams only NEW events and does NOT replay per-generation history on connect, so any
// reconnect (after a dropped socket) MUST re-fetch GET /runs/{id} and replace the snapshot
// before resuming the stream — otherwise a generation.complete / analyzer.hypothesis
// emitted during the outage is silently lost. Rendering lives in Cockpit; this component
// owns the socket, the Stop action, and the plateau notice.

import { useEffect, useRef, useState } from "react";
import { getRun, resumeRun, stopRun, wsUrl, type RunSnapshot } from "@/lib/api";
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
  "paused", // recoverable pause on a sustained oracle fault — no more WS events coming
]);

// WS connection state (06-07 + 07-08 resilience):
//  connecting   — fetching the snapshot / opening the socket (also the cold-start window)
//  live         — socket open, events flowing
//  reconnecting — the socket dropped on a still-running run; backing off to retry
//  lost         — reconnect attempts exhausted; the operator can retry manually
//  done         — the run is terminal (no more events are coming)
export type ConnState = "connecting" | "live" | "reconnecting" | "lost" | "done";

const MAX_RECONNECT_ATTEMPTS = 5;
const backoffMs = (attempt: number) => Math.min(15_000, 1_000 * 2 ** attempt);

export function LiveRun({ runId }: { runId: number }) {
  const [snap, setSnap] = useState<RunSnapshot | null>(null);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [stopErr, setStopErr] = useState<string | null>(null);
  const [resumeErr, setResumeErr] = useState<string | null>(null);
  // Bumped after a successful resume OR a manual reconnect retry to re-run the
  // fetch+subscribe effect below (the effect only re-fires on its dep list).
  const [reloadKey, setReloadKey] = useState(0);
  const snapRef = useRef<RunSnapshot | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    let disposed = false;

    // Reset view state for the incoming runId so a dep change never shows stale data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSnap(null); setLoadErr(null); setConn("connecting");

    function openSocket() {
      ws = new WebSocket(wsUrl(runId));
      ws.onopen = () => {
        if (disposed) return;
        attempts = 0; // a clean open resets the backoff ladder
        setConn("live");
      };
      ws.onmessage = (e) => {
        if (disposed) return;
        const ev: RunEvent = JSON.parse(e.data as string) as RunEvent;
        if (ev.type === "ping") return;
        const next = applyEvent(snapRef.current!, ev);
        snapRef.current = next;
        setSnap(next);
        if (ev.type === "run.complete") setConn("done");
      };
      ws.onclose = () => {
        if (disposed) return;
        // The run finished (run.complete flipped status terminal) — no reconnect.
        if (snapRef.current && TERMINAL.has(snapRef.current.status)) {
          setConn("done");
          return;
        }
        // A non-terminal run dropped its socket: back off and retry a few times, then
        // surface a manual retry rather than silently claiming the run is done.
        attempts += 1;
        if (attempts > MAX_RECONNECT_ATTEMPTS) {
          setConn("lost");
          return;
        }
        setConn("reconnecting");
        timer = setTimeout(reconnect, backoffMs(attempts - 1));
      };
    }

    // A reconnect (any socket-open after the first) re-fetches the snapshot BEFORE
    // reopening the socket, so generations completed during the outage are recovered —
    // the server does not replay them over the fresh subscription. A failed re-fetch
    // keeps climbing the same backoff ladder rather than folding onto a stale snapshot.
    function reconnect() {
      if (disposed) return;
      getRun(runId)
        .then((s) => {
          if (disposed) return;
          snapRef.current = s;
          setSnap(s);
          if (TERMINAL.has(s.status)) {
            setConn("done");
            return;
          }
          openSocket();
        })
        .catch(() => {
          if (disposed) return;
          attempts += 1;
          if (attempts > MAX_RECONNECT_ATTEMPTS) {
            setConn("lost");
            return;
          }
          setConn("reconnecting");
          timer = setTimeout(reconnect, backoffMs(attempts - 1));
        });
    }

    getRun(runId)
      .then((s) => {
        if (disposed) return;
        snapRef.current = s;
        setSnap(s);
        if (TERMINAL.has(s.status)) {
          setConn("done");
          return;
        }
        openSocket();
      })
      .catch((e: unknown) => {
        if (disposed) return;
        setLoadErr(String(e instanceof Error ? e.message : e));
      });

    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [runId, reloadKey]);

  if (loadErr) {
    return (
      <p role="alert" className="text-destructive">
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

  function onResume() {
    setResumeErr(null);
    resumeRun(runId)
      .then(() => setReloadKey((k) => k + 1)) // re-fetch + re-open the WS
      .catch((e: unknown) => setResumeErr(String(e instanceof Error ? e.message : e)));
  }

  // Manual reconnect after the backoff ladder gives up (conn === "lost"): re-fetch the
  // snapshot and re-open the socket from scratch.
  function onRetry() {
    setReloadKey((k) => k + 1);
  }

  return (
    <Cockpit
      snap={snap}
      running={running}
      conn={conn}
      onStop={onStop}
      stopErr={stopErr}
      onResume={onResume}
      resumeErr={resumeErr}
      onRetry={onRetry}
      notice={notice}
    />
  );
}
