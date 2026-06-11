# Slice 4 — `03-cloudify`

**Status:** implemented + fully reviewed + locally green on branch `slice4-cloudify` (2026-06-12); **NOT shipped** — the milestone-closing Modal cloud run (deploy + browser QED run) is pending Modal credentials. **Milestone:** `00-walking-skeleton` (final slice — shipping it closes the milestone).
**Design spec:** `../superpowers/specs/2026-06-11-cloudify-design.md` · **Plan:** `../superpowers/plans/2026-06-11-cloudify.md`

## Goal

Score the QED oracle on a **deployed Modal worker** instead of a local subprocess, proven by a browser-driven QED run end to end — with `RunCost.oracle_cost_usd` populated and a dormant-but-real dollar cost gate. This exercises the last unproven walking-skeleton seam (Modal) and closes the milestone.

## Plan

Confirmed design decisions (brainstorm 2026-06-11):
- **Oracle scoring only** moves to Modal; the Graph-GA proposer stays a local subprocess (it's replaced by the Modal LLM endpoint in milestone 02 anyway).
- **Env-selected backend** `CAPYCHEM_ORACLE_BACKEND=local|modal` (default `local`) — CI/pytest stay green with zero Modal. Scoring becomes **async** (`score_batch_async`), which also fixes the event-loop-blocking concern.
- **Minimal real cost gate now**: new `RunCost` table + live `oracle_cost_usd` + a `$`-cap checked per generation in `runner.py` → clean `cost_capped` termination + a WS cost event.
- **Real cloud run closes the slice** (and the milestone).

Files (full detail in the plan):
- `packages/core/capychem/` — `db/models.py` (+`RunCost`), `cost.py` (new: aggregate + cap), `oracle.py` (+`cost_usd`, `score_batch_async`), `loop/state.py` + `loop/graph.py` (thread cost; async score node).
- `apps/api/capychem/api/` — `schemas.py` (+`cost_so_far_usd`), `runner.py` (gate + RunCost upsert); `pyproject.toml` (+`modal`).
- `apps/worker/app.py` — new standalone Modal app (3.10 image = legacy harness env; `score` shells out to the unchanged `harness/.../score.py`).
- `apps/web/` — thin: `lib/api.ts`, `lib/runEvents.ts`, `app/runs/[id]/LiveRun.tsx` (cost counter + `cost_capped` badge).
- `scripts/smoke.sh` — worker parse/import check.

Testing: unit (cost helpers, backend selection, loop cost-threading) + integration (forced-cap gate → `cost_capped`) all on the **local** backend; worker contract reuses the harness JSON contract; the deployed cloud QED run is the milestone-closing manual gate.

## Tasks

- [x] T1 — `RunCost` model + `cost.py` (aggregate/cap helpers) + tests. (`f8be08f`)
- [x] T2 — `OracleResult.cost_usd` + `score_batch_async` backend selection + tests. (`09a158d`)
- [x] T3 — thread per-call cost through `loop/state.py` + `loop/graph.py` (async score node) + test; e2e still green. (`2271f47`)
- [x] T4 — cost gate + RunCost upsert + `cost_so_far_usd` on event/snapshot in `runner.py` + forced-cap test. (`e34cc3b`)
- [x] T5 — `apps/worker/app.py` Modal worker + `modal` dep + smoke.sh check (CODE done, `41552af`); **`modal run`/`deploy` cloud smoke deferred — needs `MODAL_TOKEN_*`.**
- [x] T6 — thin cost UI (counter + `cost_capped` badge) + reducer test. (`cd20ee9`)
- [~] T7 — full **local** gate green (pytest 39 / mypy / ruff check+format / web test+typecheck+lint+build) + ruff format `bab00d7`; **slice-ship doc updates + milestone close still pending the cloud run.**

## Notes / open questions

- **Sub-decisions resolved by recommendation (revisit if wrong):** (a) new `Run.status` value `cost_capped` rather than overloading `exhausted`; (b) thin cost UI lands here (slice 3 deferred "cost display" to slice 4), not pushed to milestone 04.
- **Cost rate / cap are env-driven placeholders** (`CAPYCHEM_ORACLE_USD_PER_SEC`, `CAPYCHEM_COST_CAP_USD` default $50) — dormant on QED; not a real-price claim (PRD N6).
- **SPEC §8.3 "1.5× budget" reconciliation:** the configured budget is *oracle calls*, not dollars; this slice gates on a dollar cap (G2 ~$50). The "1.5× projection" refinement waits for real LLM cost (milestone 02).
- **Boundary-stop gate** stops *before the next* generation, not mid-generation — adequate for a dormant scaffold; strict pre-spend would touch the loop more (rejected for thinness).
- **Loop is no longer "frozen"** — that was a slice-3↔4 worktree guard; slice 4 owns `oracle.py` + the score/persist nodes.
- **Modal prerequisites:** a Modal account + `MODAL_TOKEN_*` in env before T5; `modal setup` once. The API needs the same token to call `.remote.aio`.
- **Carried pre-existing concerns:** `Run.ended_at` still unset; post-restart snapshots read in-memory (RunCost table is the durable cost record); top-10 sort key triplicated.
