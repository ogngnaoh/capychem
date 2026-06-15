# Handoff — 01-harness-reproducibility (ACTIVE)

## Completed this session

- **Slices 1 & 2 SHIPPED to `main`** (orchestrated via superpowers subagent teams: TDD implementers + fresh-context spec/code-quality reviewers + fix rounds + integration review).
  - **Slice 1 `01-reproduce-graph-ga`** — canonical `packages/core/capychem/eval/` (faithful PMO `top_auc`, headless memoized unique-call runner, baselines, `capychem-eval` CLI). Merge `236fbc4`, docs `667af3b`. **Full 10k QED repro: AUC 0.9384 vs published 0.940 (diff −0.16%, within ±0.02).**
  - **Slice 2 `02-langfuse-end-to-end`** — `.env.local` auto-load, `parent_observation_id` nesting + per-generation span registry, gen-span leak fix. Merge `5d05c18`, docs (this commit). **Real trace run 259: run→generation:0–4→node:5, 0 orphans (FR-014).**
- Both verified together on a throwaway integration branch BEFORE merge (both touch `graph.py` — auto-merged clean, gate green): `pytest` 57 passed · `mypy` clean (28 files) · `ruff` clean. Confirmed shipped code == gated code (byte-identical).

## Slice status across milestone

- `01-reproduce-graph-ga` → **shipped (2026-06-16)** — frozen
- `02-langfuse-end-to-end` → **shipped (2026-06-16)** — frozen
- `03-valid-smiles-measurement` → planned (NOT yet planned) — Track A, next

## Current state

- `main` clean, ahead of `origin/main` (not pushed). Worktrees + `integration-m01` cleaned up.
- Langfuse v2 on `:3001` (keys in `.env.local`, auto-loaded). Postgres on `:5432` (`capychem-postgres`). `CAPYCHEM_ORACLE_BACKEND` unset (local harness).
- Eval authority lives in `packages/core/capychem/eval/`; `loop/logic.py` running curve stays a UI estimate only.

## Next session start here — SLICE 3 (Phase D), full loop

Run the FULL slice loop for `03-valid-smiles-measurement` (Track A, after slice 1):
`superpowers:brainstorming` (ask clarifying Qs; Explore subagent maps the `validate` node first) → `superpowers:writing-plans` → orchestrator writes `docs/01-harness-reproducibility/03-valid-smiles-measurement.md` → ⏸ PLAN CHECKPOINT → implement (TDD + 2 reviewers) → verify → ship.
**Scope:** plumb RDKit validation-rate tracking into the `validate` node; surface a per-run valid-SMILES rate; exercise on Graph-GA. The **>80% GATE CHECK is milestone 02** — measure only here. Keep the field stable (it's the exact input the milestone-02 LLM-proposer gate compares against).

## Active concerns

- Slice 3 touches the shared loop/`validate` surface that slices 1 & 2 also modified — read merged `graph.py` + `validate.py` before planning.
- Deferred to milestone 02 (do NOT do here): product-loop memoization / unique-call budget (G1 beat attempt); the >80% valid-SMILES gate check; LLM proposer.
- FastAPI `_drive` gen-span cleanup now covered by `end_all_gen_spans` in `finally`; LLM-call generation spans still milestone 02.
- Carried from 00: `GET /runs/{id}` cost_so_far_usd=0.0 fallback; top-10 sort triplicated; `Run.ended_at` unset — milestone-04 polish.

## Slice log

- 2026-06-12 — Milestone 01 scoped.
- 2026-06-15 — Slices 1 & 2 PLAN complete (specs + plans + slice docs).
- 2026-06-16 — **Slice 1 shipped** (`236fbc4`/`667af3b`; AUC 0.9384). **Slice 2 shipped** (`5d05c18`; FR-014 nested trace verified).
