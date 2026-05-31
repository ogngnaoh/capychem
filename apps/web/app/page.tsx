"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Health = { status: string };
type State =
  | { kind: "loading" }
  | { kind: "ok"; status: string }
  | { kind: "error"; detail: string };

export default function Home() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch(`${API_URL}/healthz`)
      .then((r) => r.json() as Promise<Health>)
      .then((d) => setState({ kind: "ok", status: d.status }))
      .catch((e) => setState({ kind: "error", detail: String(e) }));
  }, []);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 font-sans">
      <h1 className="text-2xl font-semibold tracking-tight">CapyChem</h1>
      <p className="text-sm text-zinc-500">Walking skeleton — backend health</p>
      <div className="rounded-lg border px-6 py-4 font-mono text-sm">
        {state.kind === "loading" && <span>Checking {API_URL}/healthz…</span>}
        {state.kind === "ok" && (
          <span className="text-green-600">● API {state.status}</span>
        )}
        {state.kind === "error" && (
          <span className="text-red-600">● API unreachable: {state.detail}</span>
        )}
      </div>
    </main>
  );
}
