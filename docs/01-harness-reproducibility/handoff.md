# Handoff — 01-harness-reproducibility (COMPLETE ✅)

## Completed this session

- **Slice 3 `03-valid-smiles-measurement` SHIPPED to `main`** (full slice loop: brainstorm → plan → inline TDD → verify → fresh-context review → ship).
  - Plumbed RDKit **parse-validity** tracking: `validate_batch_with_stats` + `ValidationStats` (parse-valid counted BEFORE dedup, so a repeated-but-valid molecule still counts valid). Cumulative `_validation_stats` accumulates across generations in the `validate` node (mirrors the `auc_curve` idiom); `build_summary` emits a stable `valid_smiles {proposed, valid, rate}` block into `summary_json`; CLI prints the rate.
  - Code commits `5f3276f` · `ed7a970` · `66cd020` · `b8a5a99` · `dbfa998`. Planning docs `8ec59d3` (design spec) · `42e0025` (plan + slice doc).
  - **Gate green (real output):** `pytest` 65 passed · `mypy` clean (28 files) · `ruff` clean. Real Graph-GA run **Run 269** (QED, budget 200, 5 gens): `valid SMILES: 100.0% (228/228 parseable)`, persisted `summary_json.valid_smiles = {"proposed": 228, "valid": 228, "rate": 1.0}` (confirmed in Postgres; surfaced via existing `GET /runs/{id}`).
  - ~100% is expected (deterministic graph edits); the plumbing is the deliverable. `228 proposed > 200 calls` is intentional — rate measures everything proposed, pre-budget-trim.

## Slice status across milestone

- `01-reproduce-graph-ga` → **shipped (2026-06-16)** — frozen
- `02-langfuse-end-to-end` → **shipped (2026-06-16)** — frozen
- `03-valid-smiles-measurement` → **shipped (2026-06-16)** — frozen

**Milestone 01 exit criteria all met** → milestone COMPLETE. `docs/milestones.md` advanced: 01 shipped, **02-end-to-end-loop ← active**.

## Current state

- `main` clean, ahead of `origin/main` by 30 commits (not pushed — same posture as slices 1 & 2).
- Langfuse v2 on `:3001` (keys in `.env.local`, auto-loaded). Postgres on `:5432` (`capychem-postgres`, healthy). `CAPYCHEM_ORACLE_BACKEND` unset (local harness).
- Eval authority lives in `packages/core/capychem/eval/`; `loop/logic.py`'s running curve stays a UI estimate only.

## Next session start here — MILESTONE 02 (`02-end-to-end-loop`, SPEC Phase 2)

Milestone 01 is done. Begin milestone 02: **synthesize** `docs/02-end-to-end-loop/milestone.md` + `handoff.md` (do not pre-create slice files until each slice starts). Scope per `docs/milestones.md`: Modal LLM endpoint + oracle worker pool, FastAPI REST + WS, Postgres-backed launch + watch-live on one PMO task, and the **first beat-Graph-GA attempt** — which carries the deferred **>80% valid-SMILES gate check** (reads `summary_json.valid_smiles.rate`, now stable) and the **product-loop memoization / unique-call budget** (G1). Pick a task with headroom (e.g. `jnk3`, `zaleplon_mpo`), NOT QED.

## Active concerns

- The `valid_smiles` field shape is now the stable contract the milestone-02 >80% gate reads — do not rename/reshape `{proposed, valid, rate}`. Gate must account for pre-trim semantics (proposed ≥ oracle_calls).
- Deferred into milestone 02: LLM proposer; >80% gate check; product-loop memoization / unique-call budget; LLM-call generation spans.
- Carried from 00 (milestone-04 polish): `GET /runs/{id}` cost_so_far_usd=0.0 fallback; top-10 sort triplicated; `Run.ended_at` unset.

## Slice log

- 2026-06-12 — Milestone 01 scoped.
- 2026-06-16 — **Slice 1 shipped** (`236fbc4`/`667af3b`; AUC 0.9384). **Slice 2 shipped** (`5d05c18`; FR-014 nested trace). **Slice 3 shipped** (`dbfa998`; valid-SMILES 100.0% 228/228, Run 269). **Milestone 01 COMPLETE.**
