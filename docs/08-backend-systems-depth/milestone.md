# Milestone 08 — Backend Systems Depth + Reframe

> SPEC direction: PROJECT.md §10 `[RE-DECIDE]` resolved — make the backend genuinely load-bearing, then make it legible.
> Design spec: `docs/superpowers/specs/2026-07-07-capychem-backend-depth-and-reframe-design.md`
> Execution plan: `docs/superpowers/plans/2026-07-07-capychem-milestone-08-backend-depth.md`

## Goal

Convert CapyChem's single-process, in-memory run execution into a durable Postgres-backed producer → queue → out-of-process-worker system (with a persistent oracle-score cache, backpressure, the missing REST-contract pieces, and ops maturity), then reframe the repo to lead with the backend engineering. Every existing claim stays honest.

## Scope

- **Durable job queue + out-of-process worker** — `SELECT … FOR UPDATE SKIP LOCKED` claim, lease/heartbeat/reclaim, a separate `apps/runner/` process drives the existing LangGraph loop; the DB becomes the source of truth.
- **Cross-process live events** — Postgres `LISTEN/NOTIFY`; the WS layer subscribes so live updates work when a *different* process drives the run.
- **Persistent shared oracle-score cache** — `OracleScoreCache` keyed on `(oracle_key, objective_key, canonical_smiles)`; RDKit canonicalization; version invalidation; a hit costs $0.
- **Backpressure + REST gaps** — bounded concurrency/pools, `GET /runs` pagination, `POST /runs` `Idempotency-Key`.
- **Ops** — Dockerfile(s) for API + runner, a compose that stands the whole system up, `/readyz` vs `/healthz`, `pool_pre_ping`.
- **Reframe** — README leads with the backend + a 10-second domain ELI5; `docs/architecture.md` with a "hard problems + tradeoffs I solved" section.
- **Credibility** — `apps/api` conftest skip-guards (green on a bare clone), FIGURE-CANON results framing, README GIF trim.

## Non-goals

- No Redis / Kafka / RabbitMQ / Celery / k8s. The queue is Postgres `SKIP LOCKED`; the event bus is `LISTEN/NOTIFY`. (Deliberately rejected as cargo-cult at this scale; the decision trail is itself a defend-your-architecture asset.)
- No docking / expensive oracle in committed scope (documented stretch — S8, needs operator re-approval).
- No multi-tenant / auth (PRD N8 stands). No new ML work — the loop's behavior is unchanged.

## Slices (execution order · single branch `m08-backend-systems-depth` · no per-agent worktrees)

1. **01 green-on-clone + credibility** — `apps/api/tests/conftest.py` skip-guards; FIGURE-CANON results framing; GIF trim. *(S, independent)* — **shipped** (7cd100e)
2. **02 durable queue + out-of-process worker** — lease/heartbeat/`SKIP LOCKED` claim/reclaim; `POST /runs` enqueues; new `apps/runner/` drives; DB is source of truth. *(L — the core)* — **shipped** (66e5764) · HARD GATE reviewed ✓
2b. **02b lease fencing** (operator-approved at the S2 gate) — `UNIQUE(run_id, index)` structural backstop; `finalize_run`/`release_run` owner-fenced; `renew_lease` returns rowcount>0 → stop-on-lost-lease. *(S)* — **shipped** (a3f253d)
3. **03 cross-process live events** — `LISTEN/NOTIFY`; WS subscribes; DB-snapshot path becomes normal. *(M, depends S2)* — **planned**
4. **04 persistent shared oracle cache** — table + canonicalization + version invalidation + budget integration; **G1/eval path untouched**. *(M, depends S2)* — **planned**
5. **05 backpressure + REST gaps** — concurrency caps, bounded pools, pagination, idempotency. *(M, depends S2)* — **planned**
6. **06 ops** — Dockerfile(s) + compose + `/readyz` + `pool_pre_ping`. *(S–M, depends S2–S5)* — **planned** · **HARD GATE after (before S7)**
7. **07 reframe & docs** — README lead-with-backend + ELI5; `docs/architecture.md` + hard-problems narrative. *(S–M, depends all)* — **planned**
8. **08 docking on the worker pool** — STRETCH, uncommitted, DO NOT BUILD without operator re-approval.

Each slice is built by the dynamic Workflow (`Builder → Evaluator → repair-once-on-FAIL → re-verify`); the orchestrator owns these milestone doc writes at each gate and independently re-verifies every Builder claim.

## Integration notes (cross-slice coupling, by path — corrected against the code)

- **DB layer is in `packages/core/capychem/db/`**, NOT `apps/api/.../db/` (the plan's contracts guessed wrong). Models: `packages/core/capychem/db/models.py`. Migrations: `packages/core/capychem/db/migrations/versions/` (Alembic; `alembic.ini` at repo root; `capychem.db.migrate.run_migrations`). Engine/sessionmaker: `packages/core/capychem/db/session.py`. Test bootstrap uses `Base.metadata.create_all` (`init_schema`) — a model change is auto-created for tests, but a **matching Alembic revision is still required** for the prod path and gate.
- **The execution core** is `apps/api/capychem/api/runner.py` (`RunRegistry`, `_drive`). `POST/GET /runs` in `apps/api/capychem/api/routes_runs.py`; WS in `apps/api/capychem/api/ws_runs.py`; lifespan + boot-sweep in `apps/api/capychem/api/main.py`.
- **S2 tension (the load-bearing one):** the existing suite drives runs *in-process* — `apps/api/tests/test_api.py` POSTs then expects WS progress (relies on `start_run`'s `create_task`); `test_runner.py`/`test_pause_recover.py` reach into `registry._runs`/`handle.task`. Moving execution out-of-process must NOT silently weaken these guarantees (completes / stop / pause-on-fault / resume / no-double-exec). Reconcile faithfully; the inline-worker-for-dev vs strict-separation choice is reviewed at the S2 hard gate.
- **S4 contamination guard:** the eval/benchmark path (`packages/core/capychem/eval/runner.py`) is fully separate — it uses its own `mol_buffer` + synchronous `score_smiles`, never `build_graph`/`score_batch_async`. The cache MUST live at the async/loop layer (`score` node in `packages/core/capychem/loop/graph.py` and/or `score_batch_async` in `oracle/__init__.py`) and MUST NOT be injected into `score_smiles`. Benchmark-mode API run trajectories (AUC vs oracle calls) must be identical with the cache on vs off (G6). `docs/04-compare-and-polish/g1-full23-10k-seed42.json` is untouched.
- **The unique-call budget invariant** (`calls_used == len(mol_buffer) == #OracleCall` per run) is enforced in the `score` node; S4 preserves it (an exploratory-mode cache hit is $0 and uncounted).
- **Cost:** `RunCost.total_usd = oracle + llm` (`packages/core/capychem/cost.py`); the cost gate (`cost_cap_usd()`, default $50) trips a clean `cost_capped` termination. The reclaim path reuses `reconstruct_state` (`packages/core/capychem/resume.py`).

## Exit criteria (testable)

- A run is enqueued by `POST /runs` and driven end-to-end by a **separate `apps/runner` process**; killing it mid-run lets a second runner reclaim (lease expiry) and reach the same terminal state; no double-execution under contention (no duplicate `Generation.index`).
- Live WS updates work when the run is driven by a **different process** than the one serving the WS (`LISTEN/NOTIFY`); new-generation → client < 2 s p95.
- Re-scoring an identical molecule (same run or across runs) does not re-spend budget in exploratory mode; hit-rate observable; **benchmark AUC/oracle-call trajectory unchanged**.
- Concurrency caps enforced + observable; `GET /runs` paginates; a double `POST` with the same `Idempotency-Key` yields exactly one run.
- `docker compose up` stands up API + runner + Postgres; `/readyz` reflects downstream health; `/healthz` is liveness.
- README leads with the backend within the first screen and ELI5s the domain; `docs/architecture.md` covers the run lifecycle + queue/lease protocol + cache design + hard-problems narrative.
- **FIGURE CANON preserved verbatim; N6 intact; benchmark/exploratory wall preserved.** Full gate green (`ruff` + `mypy -p capychem -p capychem.api` strict + `pytest`; web typecheck/eslint/vitest/axe).
