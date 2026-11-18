import { useEffect, useState } from "react";
import { request } from "./api";

export type RunEvent = {
  seq: number;
  type: string;
  created_at: string;
  payload: Record<string, unknown>;
};

const stageNames: Record<string, string> = {
  prepare: "Prepare receptor and parent",
  baseline: "Evaluate parent baseline",
  generate: "Collect candidate proposals",
  evaluate: "Evaluate candidate poses",
  review: "Assemble review evidence",
};
function eventLabel(event: RunEvent) {
  const stage =
    typeof event.payload.stage === "string" ? event.payload.stage : "";
  if (event.type.startsWith("stage.") && stage)
    return `${stageNames[stage] ?? stage.replaceAll("_", " ")} · ${event.type.slice(6)}`;
  return event.type.replaceAll(".", " · ").replaceAll("_", " ");
}

/** Durable server events, loaded only while a run's details are open. */
export function RunActivity({
  experimentId,
  active,
  recordedEvents,
}: {
  experimentId: string;
  active: boolean;
  recordedEvents?: RunEvent[];
}) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (recordedEvents) {
      setEvents(recordedEvents);
      setError("");
      return;
    }
    let alive = true;
    let cursor = 0;
    async function refresh() {
      try {
        const result = await request<{
          events: RunEvent[];
          next_sequence: number;
        }>(`/experiments/${experimentId}/events?after=${cursor}&limit=500`);
        if (!alive) return;
        cursor = result.next_sequence;
        setEvents((previous) => [
          ...new Map(
            [...previous, ...result.events].map((event) => [event.seq, event]),
          ).values(),
        ]);
        setError("");
      } catch (e) {
        if (alive)
          setError(
            e instanceof Error ? e.message : "Activity could not be loaded.",
          );
      }
    }
    setEvents([]);
    void refresh();
    const timer = active ? setInterval(() => void refresh(), 3000) : undefined;
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [experimentId, active, recordedEvents]);
  return (
    <details className="resolved-spec run-activity" open>
      <summary>
        Calculation activity <span>{events.length} events</span>
      </summary>
      {error && <p role="alert">{error}</p>}
      {!events.length && !error && (
        <p className="muted">Waiting for saved activity…</p>
      )}
      <ol>
        {events.map((event) => (
          <li key={event.seq}>
            <time dateTime={event.created_at}>
              {new Date(event.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </time>
            <details>
              <summary>{eventLabel(event)}</summary>
              {typeof event.payload.message === "string" && (
                <p className="activity-message">{event.payload.message}</p>
              )}
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ol>
    </details>
  );
}
