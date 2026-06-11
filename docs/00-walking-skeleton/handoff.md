# Handoff — 00-walking-skeleton

## Completed this session

- **Slice 3 (`02-web-surface`) SHIPPED** — frontend Tasks 7–11 (commits `672760d..9bf0758`)
  via subagent-driven development (fresh implementer + spec review + quality review per task,
  fix loops re-reviewed), on top of the backend Tasks 1–6 (`1302027..2404a97`) done earlier.
  Browser-driven local QED run now works end to end: launch form → live WS view → stop.
- Frontend shipped: shadcn/ui + typed API client + pure event reducer (`672760d`, fix `b859587`);
  launch form (`dfaf6cf`); live view — snapshot + WS + recharts AUC + top-K + stop (`637c2c3`,
  fix `dbf80c5`); vitest + Playwright (`b23c0ba`, fixes `302838e`/`9bf0758`).
- **Load-bearing review catch:** the live AUC curve was plotting `best_score` (top-1) under a
  "Top-10 mean" axis — fixed so the `generation.complete` event carries the backend-authoritative
  `top10_mean` (same value the REST snapshot returns); reducer + vitest now guard it (`dbf80c5`).
- Ship gate (this commit): smoke.sh gains api-import + web-build checks; slice doc frozen;
  milestone/handoff flipped.

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → shipped (2026-06-11)
- `02-web-surface` → **shipped (2026-06-11)**
- `03-cloudify` → planned (next)

## Current state

- Branch `main`. Full green gate: 30 pytest (23 core + 7 api, real harness + Postgres),
  mypy strict (20 files), ruff check+format (28 files), web typecheck/lint/build, vitest 4/4;
  `scripts/smoke.sh` → 11 passed, 0 failed. Playwright launch e2e ran green (real 40-call run).
- Loop code byte-unchanged since slice-2 ship (`d85e9db`); no harness imports in `apps/`.
- Run the app: `uv run uvicorn capychem.api.main:app` + `pnpm --filter web dev` (MUST be :3000 — WS Origin allowlist).

## Next session start here

Slice 4 (`03-cloudify`): stand up the Modal-hosted oracle worker (`apps/worker/`); swap the
local harness subprocess in `packages/core/capychem/oracle.py` for the Modal endpoint; wire
`RunCost` (oracle_cost_usd) + the cost gate in `runner.py`. The WS cold-start heartbeat is
already present from slice 3. First action: write the slice-4 design spec + plan.

## Active concerns

- Sync harness subprocess blocks the API event loop during scoring (WS pings gap >15 s) →
  `to_thread` wrapper or Modal offload in slice 4. `Run.ended_at` never set; errored runs show
  zeroed snapshots after restart. top-10 sort key triplicated (consolidate when loop freeze lifts).
- Langfuse enabled-path trace still unverified (no keys set). Plateau (FR-003) configured but
  not enforced; `plateau_window` not yet exposed in the launch form (FR-001 → milestone 04).

## Slice log

- 2026-06-11 — Slice 3 (`02-web-surface`) shipped (backend Tasks 1–6 + frontend Tasks 7–11).
- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
