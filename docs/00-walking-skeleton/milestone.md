# Milestone 00 — Walking Skeleton

## Goal

Ship a thin end-to-end CapyChem run on one PMO task (QED), browser-launched, with live updates and a full Langfuse trace — proving every integration seam (harness env, subprocess bridge, Postgres, FastAPI WS, Next.js, Modal, Langfuse) before SPEC §9 phases dig in for rigor.

## Scope

- Monorepo scaffold (pnpm + uv workspaces).
- Isolated `harness/` uv env (PyTDC 0.3.6 / Python 3.10 / `mol_opt`) — own venv + lockfile, excluded from the modern workspace — with a subprocess + JSON bridge as the only seam to modern code.
- LangGraph loop: propose (Graph-GA via harness) → validate (RDKit) → score → persist.
- Minimal Postgres schema (Run, Generation, Candidate, OracleCall).
- FastAPI REST + WebSocket; minimal Next.js launch + watch-live pages.
- Modal-hosted oracle worker.
- Langfuse spans on every loop step; `RunCost.oracle_cost_usd` wired.

## Non-goals

- No real LLM proposer — defer to milestone 02.
- No analyzer step — defer to milestone 03.
- No beat-Graph-GA performance bar — defer to milestone 02.
- No managed Postgres picker (Neon vs Supabase) — defer to milestone 02 or 03 at infra-setup.
- No compare view, run-list filtering, or auth — defer to milestone 04.
- No multi-task UI — QED only.

## Slices

1. `00-foundation` — shipped (2026-05-30). Monorepo, isolated harness uv env, subprocess QED bridge, Docker (Postgres + Langfuse), hello-world web + api.
2. `01-local-loop` — shipped (2026-06-11). LangGraph propose→validate→score→persist→stop with Graph-GA proposer; `capychem-run` CLI runs QED for a small budget end-to-end locally (Postgres + Langfuse no-op).
3. `02-web-surface` — planned (next). FastAPI REST + WS + Next.js launch/live view; browser-driven local run.
4. `03-cloudify` — planned. Modal-hosted oracle worker; API swaps local subprocess for Modal; RunCost wiring. (WS cold-start heartbeat owned by slice 3, not here — see Integration notes.)

## Integration notes

- The harness ↔ modern seam (CLAUDE.md gotcha: subprocess only, never `import`) is exercised in slices 1, 2, and 4 — treat its contract as load-bearing from slice 1.
- LangGraph runtime lives in `packages/core` and is hosted in-process by `apps/api`; slice 2 builds it standalone via CLI, slice 3 grafts it into the API as a background task.
- WebSocket served from FastAPI's absolute origin, not proxied through Next.js (CLAUDE.md gotcha).
- Postgres schema is additive across slices (introduced in slice 2; read by slice 3 for WS replay; `RunCost` added in slice 4).
- WS cold-start heartbeat lives in slice 3 (not slice 4) so the two parallel worktrees own non-overlapping code.

### Parallelizability

- Slices 1 and 2 are sequential and must precede everything else.
- Slices 3 and 4 are parallelizable in separate worktrees once slice 2 ships:
  - Slice 3 worktree: `apps/api/`, `apps/web/`, `packages/core/capychem/schemas.py`.
  - Slice 4 worktree: `apps/worker/`, `packages/core/capychem/oracle.py`, `apps/api/capychem/api/runner.py` (cost gate), DB migration adding `RunCost`.

## Exit criteria

- Browser-driven QED run completes end-to-end via Modal-hosted oracle.
- Live updates arrive in the watch view within ~2 s of each generation event (SPEC G5).
- Persisted run shows top-K, generations, candidates, oracle calls in Postgres.
- Langfuse shows a nested trace: per-run → per-generation → per-node.
- `RunCost.oracle_cost_usd` is populated.
- No `import` from `harness/` anywhere in `packages/` or `apps/`.
