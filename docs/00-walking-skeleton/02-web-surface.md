# Slice 02 — Web Surface

**Status:** shipped (2026-06-11). Frozen.
**Design spec:** `docs/superpowers/specs/2026-06-11-web-surface-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-06-11-web-surface.md`

## Goal

A browser-driven local run: launch a QED optimization from a Next.js form, watch it
advance live over a WebSocket (counters, AUC chart, top-K table), and stop it early —
backed by a FastAPI REST + WS layer that hosts the shipped slice-2 LangGraph loop as an
in-process background task. Proves the last unproven walking-skeleton seams: FastAPI
REST + WS, the Next.js client, and the in-process background-loop runtime. Oracle stays
the local harness subprocess (Modal is slice 4).

## Plan (files touched)

Core (`packages/core/capychem/`):
- `run.py` — NEW: `RunConfig` + `create_run`/`finalize_run`, shared by CLI + API (DRY).
- `cli.py` — refactored onto `run.py` helpers (behavior unchanged).

Backend (`apps/api/capychem/api/`):
- `schemas.py` — `CreateRunRequest` (constrained), `RunSnapshot`, `GenerationCompleteEvent`
  (carries `top10_mean`), `RunCompleteEvent`.
- `runner.py` — `RunRegistry` + `astream`-driven background driver: per-run snapshot,
  generation/run events, cooperative stop, `errored` terminal path, stored `terminal_event`.
- `routes_runs.py` — `POST /runs`, `GET /runs/{id}` (live snapshot → DB fallback), `POST /runs/{id}/stop`.
- `ws_runs.py` — `GET /ws/runs/{id}`: 15 s heartbeat, terminal replay, Origin allowlist (CSWSH), disconnect-safe sends.
- `main.py` — lifespan (engine/sessionmaker/init_schema + registry), stranded-row sweep, `shutdown()` before dispose, `/healthz` DB check.
- `config.py` — `ALLOWED_ORIGINS`.

Frontend (`apps/web/`):
- `lib/api.ts` — typed REST client + `wsUrl`; readable 422 errors; `stopRun` propagates failures.
- `lib/runEvents.ts` — pure `applyEvent` reducer (curve uses `top10_mean`, not `best_score`).
- `components/ui/*` + `lib/utils.ts` — shadcn/ui (New York) primitives.
- `app/page.tsx` — launch form. `app/runs/[id]/{page,LiveRun}.tsx` — live view (snapshot + WS + recharts + stop).
- `vitest.config.ts`, `lib/runEvents.test.ts`, `playwright.config.ts`, `e2e/launch.spec.ts`.

Infra/gate:
- root `pyproject.toml` (httpx, httpx-ws dev deps; pytest `testpaths`); `apps/web/package.json` (recharts, test tooling).
- `CLAUDE.md` + `scripts/smoke.sh` — mypy gate fixed to `-p capychem -p capychem.api`; smoke gains api-import + web-build checks.

## Tasks

- [x] 1 — `capychem.run` helpers (`RunConfig`/`create_run`/`finalize_run`); CLI refactored onto them.
- [x] 2 — FastAPI lifespan (engine/sessionmaker/init_schema) + `/healthz` DB check; httpx/httpx-ws dev deps.
- [x] 3 — Pydantic schemas (`CreateRunRequest` constrained: task `Literal["qed"]`, budget>0, pop_size>1, mutation_rate (0,1]).
- [x] 4 — `RunRegistry` + `astream` background driver (events, cooperative stop, errored path, durable stopped summary).
- [x] 5 — REST routes (POST/GET/stop) + registry lifespan wiring + stranded-row startup sweep + shutdown-before-dispose.
- [x] 6 — WS `/ws/runs/{id}` (heartbeat, terminal replay, Origin allowlist) + REST+WS integration tests.
- [x] 7 — shadcn/ui setup + typed API client + event reducer.
- [x] 8 — launch form (`app/page.tsx`): validate → `POST /runs` → redirect.
- [x] 9 — live view: snapshot-on-load → WS subscribe → reducer → AUC chart + top-K + stop.
- [x] 10 — vitest reducer tests (incl. `top10_mean` regression guard + purity) + Playwright launch smoke.
- [x] 11 — smoke-script extension + full green gate + ship docs.

## Exit criteria (verified at ship)

- Launch → live page → counters/top-K/chart update live → terminal state: Playwright e2e ran green end-to-end (real 40-call QED loop, browser-driven).
- Stop halts a run → `status="stopped"`, partial state durable via `GET /runs/{id}` (backend test asserts).
- Loop code byte-unchanged since slice-2 ship: `git diff d85e9db..HEAD -- packages/core/capychem/loop/` empty.
- No `import` from `harness/` in `apps/`: grep clean.
- Gates green: 30 pytest (23 core + 7 api, real harness + Postgres), mypy strict (20 files), ruff check+format (28 files), web typecheck/lint/build, vitest 4/4. `scripts/smoke.sh` → 11 passed, 0 failed.

## Notes (deferrals + carried concerns)

Out of scope / deferred (per design §3):
- Run-list view + filter/sort (FR-010), run-detail browse with 2D structures (FR-011), compare view (FR-012) → milestone 04.
- `RunCost` table + cost display (FR-013), Modal-hosted oracle, cost gate → slice 4 (`03-cloudify`).
- Analyzer hypothesis in live view (FR-007) → milestone 03 (no analyzer exists yet).
- `plateau_window` configurable per run (FR-001): backend accepts it (default 5) but the launch form does not yet expose it → milestone 04 (form polish).

Gotchas surfaced (carry to slice 4 / later):
- The synchronous harness oracle subprocess blocks the API event loop during scoring, so WS
  heartbeat pings can gap >15 s. No client staleness logic is keyed to ping cadence. Fix is a
  `to_thread` wrapper (oracle.py) or Modal offload in `03-cloudify`.
- `Run.ended_at` is never set; errored runs show zeroed snapshots after a process restart
  (summary is null). The top-10 sort key is triplicated (loop, runner, route) — consolidate in
  `loop/logic.py` when the loop freeze lifts.
- Web dev server MUST run on `http://localhost:3000` — the WS Origin allowlist
  (`apps/api/capychem/api/config.py`) rejects other origins with close code 4403.
- Langfuse enabled-path trace still unverified (no keys set; slice-2 deferred criterion).
- `summary.auc_curve` is the live/un-authoritative curve, not the canonical PMO AUC.
