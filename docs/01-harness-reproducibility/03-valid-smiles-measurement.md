# Slice 03 — Valid-SMILES Measurement

> Milestone 01-harness-reproducibility, final slice. Phase D (Track A, after slice 1).
> Design: `docs/superpowers/specs/2026-06-16-valid-smiles-measurement-design.md` ·
> Plan: `docs/superpowers/plans/2026-06-16-valid-smiles-measurement.md`

## Goal

Measure a per-run **valid-SMILES rate** (RDKit parse-validity) in the loop's
`validate` node, accumulate it across generations, persist it in `summary_json`,
and print it from the CLI — exercised against the Graph-GA proposer. **Measurement
only**; the >80% pass/fail gate check rides with the LLM proposer in milestone 02.

## Plan

Files to touch (all under `packages/core/capychem`, headless — no API/web, no DB migration):

- `validate.py` — add `ValidationStats` (`proposed`, `valid`, `.rate`) + `validate_batch_with_stats`; refactor `validate_batch` to delegate (behavior unchanged). Parse-validity counted **before** dedup.
- `loop/state.py` — add transient `_validation_stats: dict[str, int]` cumulative counter (mirrors `auc_curve` idiom).
- `loop/graph.py` — `validate` node accumulates stats; `stop_check` passes them to `build_summary`.
- `loop/logic.py` — `build_summary` gains optional `validation_stats` kwarg → stable `valid_smiles` block `{proposed, valid, rate}`.
- `cli.py` — print the rate at run end. `GET /runs/{id}` already returns `summary_json`, so the API surface is free.

Testing: TDD per task — `test_validate.py` (parse-validity math), `test_loop_logic.py` (summary block), `test_validate_node.py` (node accumulation), `test_loop_valid_smiles.py` (fake-scorer mini-run, no harness). Then a real Graph-GA run records the measured rate.

## Tasks

- [x] Task 1 — `ValidationStats` + `validate_batch_with_stats` in `validate.py` (TDD) — `5f3276f`
- [x] Task 2 — `build_summary` emits stable `valid_smiles` block (TDD) — `ed7a970`
- [x] Task 3 — `_validation_stats` field + `validate` node accumulation (TDD) — `66cd020`
- [x] Task 4 — `stop_check` passes stats to summary + in-suite integration guard (TDD) — `b8a5a99`
- [x] Task 5 — CLI prints the per-run valid-SMILES rate — `dbfa998`
- [x] Verify — `pytest` 65 passed · `mypy` clean (28 files) · `ruff` clean (real output)
- [x] Verify — real Graph-GA run (Run 269, QED, budget 200): valid SMILES **100.0% (228/228)**, persisted to `summary_json`
- [x] Review — fresh-context code review: **Ready to merge: Yes** (no Critical/Important)
- [x] Ship — milestone/handoff status flips, this file frozen, `docs/milestones.md` advanced to milestone 02

> **FROZEN** — slice shipped 2026-06-16. Status lives in `handoff.md`.

## Notes

- **Parse-validity, not dedup.** `validate_batch` drops invalid AND collapses dupes in one pass; a repeated molecule is still valid. The rate counts RDKit-parseable / proposed — duplicates count as valid. This matches what the milestone-02 gate means by "valid-SMILES rate from the LLM."
- **Keep the field stable.** `summary_json.valid_smiles = {proposed, valid, rate}` is the exact input milestone 02's >80% gate reads. Do not rename/reshape.
- **Graph-GA rate ≈ 100%** (deterministic graph edits; starting-pop SMILES all valid). Expected — the plumbing is the deliverable, not the number.

### Out of scope / Deferred

- >80% valid-SMILES **gate check** → milestone 02 (rides with the LLM proposer).
- LLM proposer → milestone 02. Product-loop memoization / unique-call budget → milestone 02. Do not touch `eval/`.
- Per-generation rate series → not needed (Graph-GA rate is flat).
- API response field / web run-detail surface → milestone 04 polish.
- Seed-population exclusion from the rate → not needed; measure whatever flows through `validate`.
