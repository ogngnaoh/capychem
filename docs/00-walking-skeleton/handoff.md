# Handoff — 00-walking-skeleton

## Completed this session

- **Slice 3 (`02-web-surface`) backend complete — plan Tasks 1–6 of 11** via subagent-driven
  development (fresh implementer + spec review + quality review per task, fix loops re-reviewed).
  Commits `1302027..2404a97` (12 commits). Full green gate: **30 pytest** (23 core + 7 api,
  real harness + Postgres), mypy strict clean (20 files), ruff clean.
- Shipped: `capychem.run` helpers (CLI refactored onto them); FastAPI lifespan + healthz;
  pydantic schemas (constrained: task Literal["qed"], mutation_rate (0,1]); RunRegistry +
  astream-driven background runner (cooperative stop, errored path, stored terminal_event,
  durable stopped-run summary via build_summary); REST POST/GET/stop + stranded-row startup
  sweep + shutdown-before-dispose; WS `/ws/runs/{id}` (15 s heartbeat, terminal replay,
  Origin allowlist vs CSWSH, disconnect-safe sends) + 7 integration tests.
- **Gate fix:** `mypy -p capychem` never covered `apps/api` (namespace `-p` resolves only the
  first mypy_path root). Canonical gate is now `uv run mypy -p capychem -p capychem.api`
  (CLAUDE.md + smoke.sh updated, commit `bc57c56`).

## Slice status across milestone

- `00-foundation` → shipped (2026-05-30)
- `01-local-loop` → shipped (2026-06-11)
- `02-web-surface` → **in-progress (backend done; frontend Tasks 7–11 remain)**
- `03-cloudify` → planned

## Current state

- Branch `main`, clean tree at `2404a97`. Loop dir byte-unchanged since slice 2 (verified per task).
- Postgres + Langfuse up via docker compose. API boots: `uv run uvicorn capychem.api.main:app`.

## Next session start here

Execute plan Tasks 7–11 of `docs/superpowers/plans/2026-06-11-web-surface.md` (design spec
`docs/superpowers/specs/2026-06-11-web-surface-design.md`) via subagent-driven development:
Task 7 (shadcn setup + `lib/api.ts` + `lib/runEvents.ts`), 8 (launch form), 9 (live view),
10 (vitest + Playwright), 11 (smoke.sh + final gate + ship docs). Frontend contract notes
from backend reviews — fold into Tasks 7/9:
- Reducer needs a `default: return snap` (future event types: analyzer.hypothesis etc.).
- `run.complete.summary` is nullable (errored runs persist null).
- WS close semantics: 4404 unknown run / 4403 foreign Origin (pre-accept, surfaces as HTTP 403);
  normal close after run.complete → don't reconnect; web dev server MUST be on localhost:3000
  (`apps/api/capychem/api/config.py` ALLOWED_ORIGINS).
- Heartbeat pings can gap >15 s (sync oracle subprocess blocks the event loop) — no client
  staleness logic keyed to ping cadence.
- `POST /runs/{id}/stop` on a terminal run returns the run's real status, not "stopping".

## Active concerns

- Task 11 slice-doc deferrals must record: sync harness subprocess blocks the API event loop
  (to_thread wrapper at oracle.py or Modal offload in 03-cloudify); `ended_at` never set;
  errored runs show zeroed snapshots after restart (summary null); top-10 sort key triplicated
  (consolidate in loop/logic.py when the loop freeze lifts).
- Langfuse enabled-path trace still unverified (no keys set; slice-2 deferred criterion).
- Plateau (FR-003) configured but not enforced; `summary.auc_curve` ≠ canonical PMO AUC.

## Slice log

- 2026-06-11 — Slice 3 backend (plan Tasks 1–6) done; frontend pending.
- 2026-06-11 — Slice 2 (`01-local-loop`) shipped.
- 2026-05-30 — Slice 1 (`00-foundation`) shipped.
