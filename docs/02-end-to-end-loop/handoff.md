# Handoff — 02-end-to-end-loop (PLANNED — not yet started)

## Completed this session

- **Milestone 02 scoped** via an agent-team planning run (3 read-only dimension planners —
  agent-loop / backend / eval-web — + an adversarial verifier; 2 rounds; clean SIGN-OFF). No code.
- Synthesized `docs/02-end-to-end-loop/milestone.md` (Goal / Scope / Non-goals / 6-slice index /
  Integration notes / Exit criteria) and this handoff.
- User decisions locked: **task = jnk3**; **baseline = our own same-seed Graph-GA control** (not the
  published number); **G6 honored for the LLM path** (pinned temp/seed + abstraction reachable from
  product loop *and* headless eval); **plateau-stop included** in m02 (the 6th slice).

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned
- `02-plateau-stop-and-signal` → planned
- `03-modal-llm-propose-endpoint` → planned
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

Start **slice 03 `modal-llm-propose-endpoint`** — front-loads the biggest integration risk (net-new
Modal LLM serving + cold-start) and is the longest critical path (03→04→05→06). Begin its slice session
by writing `docs/02-end-to-end-loop/03-modal-llm-propose-endpoint.md` (brainstorm → design spec → plan →
slice doc), then implement. Slices 01 and 02 are dependency-free and can be picked up in any order
alongside it.

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
