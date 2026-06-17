# Handoff — 02-end-to-end-loop (IN PROGRESS — slice 03)

## Completed this session

- **Milestone 02 scoped** via an agent-team planning run (3 read-only dimension planners —
  agent-loop / backend / eval-web — + an adversarial verifier; 2 rounds; clean SIGN-OFF).
- Synthesized `docs/02-end-to-end-loop/milestone.md` + this handoff. User decisions locked:
  **task = jnk3**; **baseline = our own same-seed Graph-GA control**; **G6 honored for the LLM path**
  (pinned temp/seed + abstraction reachable from product loop *and* headless eval); **plateau-stop
  included** in m02 (the 6th slice).
- **Slice 03 `modal-llm-propose-endpoint` started:** brainstorm → design spec
  (`docs/superpowers/specs/2026-06-17-modal-llm-propose-endpoint-design.md`) → implementation plan
  (`docs/superpowers/plans/2026-06-17-modal-llm-propose-endpoint.md`, 6 TDD tasks) → slice doc. Awaiting
  execution-mode choice before code lands. Decisions: wrap DeepSeek API in Modal; prove the real path once.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → in-progress (spec + plan written; pre-code)
- `04-llm-proposer-with-ga-fallback` → planned
- `05-unique-call-budget-and-cost-ledger` → planned
- `06-beat-graph-ga-on-jnk3` → planned

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- `main` clean. No code changes this session — only the two milestone docs added under
  `docs/02-end-to-end-loop/`. `docs/milestones.md` already shows `02-end-to-end-loop ← active`.
- Carried infra (from milestone 01): Langfuse v2 on `:3001`, Postgres on `:5432`, `CAPYCHEM_ORACLE_BACKEND`
  unset (local harness). Eval authority is `packages/core/capychem/eval/`.

## Next session start here

**Execute the slice-03 plan** (`docs/superpowers/plans/2026-06-17-modal-llm-propose-endpoint.md`)
task-by-task via subagent-driven-development or executing-plans, then run the one-time manual real-API
smoke (Task 6: `deepseek-api-key` Modal secret + `modal run apps/worker/app.py::propose_smoke`). On
ship, freeze the slice doc and flip status to shipped. Slices 01 and 02 are dependency-free and can be
picked up in any order afterward.

## Active concerns

- **Slice 04 is the heaviest** (abstraction + dual-reachability + LLM wiring + GA fallback + pinned
  determinism + valid-SMILES gate + spans). Watch its size during its session; if it exceeds 2 pages,
  reconsider splitting (the verifier endorsed keeping it whole for now).
- **Async/sync seam** (slice 04): async LLM client vs synchronous headless eval path — needs a sync
  bridge or sync client path for G6 reproducibility.
- **`valid_smiles {proposed, valid, rate}`** is a frozen contract (slice 04 reads, never reshapes).
- **Beat risk:** without the analyzer (m03), this is the MOLLEO-minus-analysis config; the LLM may not
  beat Graph-GA on jnk3. That IS the week-7 kill-switch — on failure, narrow scope, don't abandon.
- **Doc hygiene (non-blocking):** SPEC §9 Phase 2 prose says "first ≥6/23 … on a single task" — treat
  as known-stale; m02's bar is ONE task.

## Slice log

- 2026-06-16 — Milestone 02 scoped (agent-team planning; 6 slices, clean verifier sign-off).
- 2026-06-17 — Slice 03 design spec + implementation plan + slice doc written (pre-code).
