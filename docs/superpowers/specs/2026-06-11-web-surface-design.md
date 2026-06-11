# Web Surface (Slice 3 `02-web-surface`) — Design Spec

**Status:** Approved scope (4 design decisions confirmed 2026-06-11); pending user review of this written spec.
**Milestone:** `00-walking-skeleton`, slice 3. **Parent SPEC:** `../../../SPEC.md` §6.1, §6.3. **Predecessor:** slice 2 `01-local-loop` (shipped).

## 1. Goal

A **browser-driven local run**: launch a QED optimization from a Next.js form, watch it advance live over a WebSocket, and stop it early — backed by a FastAPI REST + WS layer that hosts the (already-built) slice-2 LangGraph loop as an in-process background task. This proves the last unproven seams of the walking skeleton: FastAPI REST + WS, the Next.js client, and the in-process background-loop runtime. The oracle stays the local harness subprocess (Modal is slice 4).

## 2. Scope (confirmed decisions)

- **Stop control** — `POST /runs/{id}/stop` + a Stop button. Cooperative cancellation at generation boundaries; the run ends with `status="stopped"`, partial state persisted.
- **Reconnect** — snapshot-on-load: the live page fetches `GET /runs/{id}` for the current state, renders it, then subscribes to the WebSocket for new events. No server-side replay buffer.
- **Molecule display** — top molecules shown as SMILES + oracle score; plus a live best-score / AUC-so-far line chart and generation / oracle-call counters. No 2D depiction (→ milestone 04).
- **Frontend fidelity** — shadcn/ui installed now; a clean-but-minimal launch form + live panel.
- **WS heartbeat** — server-side periodic ping per the milestone integration note (infrastructure for slice-4 Modal cold-start tolerance), even though the local oracle is fast.

## 3. Non-goals (deferred)

- Run-**list** view + filtering/sorting (FR-010), run-**detail** browse page with 2D structures (FR-011), **compare** view (FR-012) → milestone 04.
- `RunCost` table + cost display (FR-013), Modal-hosted oracle, cost gate → slice 4.
- Analyzer hypothesis in the live view (FR-007) → milestone 03 (no analyzer exists yet).
- Plateau signal in watch-live (FR-003 still unenforced).
- Auth, multi-user (PRD N8/§9).

## 4. Architecture

```
 Next.js (apps/web)                         FastAPI (apps/api)
  /            launch form  ── POST /runs ──▶ create Run, spawn bg task ─▶ run_id
  /runs/[id]   live view    ── GET /runs/{id} ▶ snapshot (status/config/topK/curve)
               (on load)    ── WS /ws/runs/{id} ◀── generation.complete / run.complete
               Stop button  ── POST /runs/{id}/stop ▶ set cancel event
                                                   │
                                       in-process RunRegistry
                                       { run_id → {task, broadcaster, cancel_event} }
                                                   │
                                   build_graph(sessionmaker).astream(...)  ← slice-2 loop, unchanged
                                                   │
                                          local harness subprocess (QED)
```

### 4.1 Backend (`apps/api/capychem/api/`)

- **`runner.py` — the run runtime.** A module-level `RunRegistry` (dict `run_id → RunHandle`). `start_run(config) -> run_id`: inserts the `Run` row (reusing slice-2 `db` + `cli.run`'s setup logic, refactored into a shared helper), creates a `RunHandle` (an `asyncio.Event` cancel flag + an event broadcaster), and schedules an `asyncio.create_task` that drives the loop. The driver consumes `graph.astream(initial, config, stream_mode="values")`: after each generation boundary (detected by a growing `auc_curve` / advancing `gen_index`), it broadcasts a `generation.complete` event and, if the cancel `Event` is set, stops consuming the stream (clean break at a generation boundary — `persist` has committed, `stop_check` has run), finalizes `Run.status="stopped"` + `summary_json`, and broadcasts `run.complete`. On natural termination it finalizes with the loop's `stop_reason`. **The slice-2 loop code (`packages/core/capychem/loop/`) is NOT modified** — the runner observes it via `astream` and cancels by ceasing consumption.
- **Event broadcaster.** Per-run fan-out to connected WS clients (a set of `asyncio.Queue`s, or a simple async pub-sub). Live-only — no historical buffer (snapshot-on-load covers reload).
- **REST routers (`routes_runs.py`):**
  - `POST /runs` — body `{task, budget, seed?, pop_size?, offspring?, mutation_rate?, max_generations?}`; validates (FR-001/FR-015: positive budget, pop_size>1, known task); `start_run`; returns `{run_id, status}`. 202/201.
  - `GET /runs/{id}` — snapshot: `{run_id, task, status, config, calls_used, generations, best_score, top_k:[{smiles,score}], auc_curve:[{oracle_calls,top10_mean}]}`. While running, top_k/curve are computed live from persisted `OracleCall`/`Candidate` rows + the latest generation; when complete, from `Run.summary_json`. 404 if absent.
  - `POST /runs/{id}/stop` — sets the cancel `Event`; returns `{run_id, status:"stopping"}`. Idempotent; 404 if unknown; no-op if already terminal.
  - `GET /healthz` — extend the existing check to shallowly verify Postgres connectivity.
- **WS (`ws_runs.py`):** `GET /ws/runs/{id}` (absolute FastAPI origin; never proxied through Next — CLAUDE.md gotcha). On connect: register a queue with the run's broadcaster (or, if the run is already terminal, send `run.complete` from the DB then close). Push events as the loop emits them. **Heartbeat:** server sends a `ping` frame every ~15 s; a client that misses K pings is dropped. Tolerates a slow first event.
- **App wiring (`main.py`):** mount the routers + WS; create the async engine + sessionmaker at startup (lifespan), `init_schema` once; dispose on shutdown. CORS already locked to `localhost:3000`.

**Event payloads (lean — generation-level, not per-candidate):**
- `generation.complete` `{generation_index, best_score, oracle_calls_used, top_k:[{smiles,score}]}`
- `run.complete` `{run_id, status, summary}`
(SPEC §6.3's finer-grained `candidate.proposed`/`oracle.scored` events are intentionally collapsed to generation granularity for the skeleton.)

### 4.2 Frontend (`apps/web/`)

- **shadcn/ui setup** (components.json, button/input/card/table/form primitives).
- **`/` launch page** — a shadcn form: task (qed, fixed/select), budget, seed, pop-size, offspring, mutation-rate, max-generations, with client + server validation echoing the API's refusal reasons (FR-015). Submit → `POST /runs` → `router.push('/runs/{id}')`.
- **`/runs/[id]` live page** — on mount: `GET /runs/{id}` snapshot → render status badge, config summary, counters (generation, oracle calls used / budget, best score), a top-K table (SMILES + score), and a best-score/AUC line chart (lightweight — `recharts` or a small SVG). Then open `ws://<api-origin>/ws/runs/{id}`; on `generation.complete` update counters/table/chart; on `run.complete` set the terminal status and close. A **Stop** button (visible while running) → `POST /runs/{id}/stop`. Show a small connection indicator (live / reconnecting / done) driven by the heartbeat.
- **API origin** from `NEXT_PUBLIC_API_URL`; WS uses the same absolute origin with `ws://`/`wss://`.

### 4.3 Data model

No new tables. `Run.status` gains the `"stopped"` and (transient, API-only) `"stopping"` states already allowed by the SPEC enum. Live top-K is derived by querying `OracleCall` (top score per run) joined to `Candidate` — no schema change.

## 5. Key flows

1. **Launch** — form → `POST /runs` → Run row + background task → `run_id` → redirect to live page.
2. **Watch** — live page loads snapshot, subscribes WS, updates per generation; heartbeat keeps the socket warm.
3. **Stop** — Stop button → `POST /runs/{id}/stop` → cancel Event set → runner breaks at the next generation boundary → `status="stopped"`, `run.complete` broadcast → button hides.
4. **Concurrent runs** — each run is its own background task + RunHandle in the registry; results are isolated (PRD US-1 acceptance). No cross-run shared mutable state beyond the registry dict.

## 6. Alternatives considered

- **Observe the loop via `astream` (chosen)** vs. **modify `build_graph` to take an `emit`/`should_stop` injection.** Chosen `astream`: it keeps the shipped, frozen slice-2 loop code untouched and uses LangGraph's idiomatic streaming to observe generations; cancellation is a clean break at a generation boundary (persist already committed). The injection approach would thread an async callback + a cancel-callable through `LoopState`/nodes — more invasive, and a callable in a `TypedDict` fights LangGraph's state model. Rejected for invasiveness.
- **Server-side event replay buffer** vs. **snapshot-on-load** (chosen, §2). Rejected: needless for single-user local; snapshot is simpler and always-correct.
- **Driving the loop in a separate worker process** vs. **in-process asyncio background task** (chosen, per SPEC §6.1). In-process is the SPEC's stated model for MVP; a separate worker is slice-4+ (Modal) territory.

## 7. Testing

- **Backend (pytest + httpx ASGI):** `POST /runs` validation + creation; `GET /runs/{id}` snapshot shape (running + completed); `POST /stop` transitions a run to `stopped` with partial state persisted; a WS test (httpx-ws or `websockets`) asserting the `generation.complete` → `run.complete` sequence on a tiny real run; concurrent-runs isolation (two runs, distinct ids/state). Reuse the real harness QED + Postgres as in slice 2.
- **Frontend (vitest):** launch-form validation + submit calls `POST /runs`; live-view reducer applies `generation.complete`/`run.complete` correctly. One **Playwright** smoke: launch → land on live page → run reaches a terminal state (US-1+US-2 happy path).
- **Smoke:** extend `scripts/smoke.sh` with an API-up check (`GET /healthz`) and `pnpm --filter web build`.

## 8. Exit criteria

- Browser: fill the launch form → redirected to the live page → counters/top-K/curve update live within ~2 s of each generation (SPEC G5) → run reaches a terminal state.
- Stop button halts a running run; it ends `status="stopped"` with partial state browseable via `GET /runs/{id}`.
- Reload of the live page mid-run shows correct current state (snapshot) then resumes live updates.
- Two concurrent runs don't interfere.
- WS served from the absolute FastAPI origin; heartbeat keeps an idle socket open.
- No `import` from `harness/` in `apps/`; the loop code in `packages/core/capychem/loop/` is unchanged from slice 2.
- Backend + frontend gates green (`pytest`, `mypy -p capychem`, `ruff`, `pnpm --filter web typecheck/lint/build`).
