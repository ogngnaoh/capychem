# Slice 01 — reproduce-graph-ga

> Status: **shipped (2026-06-16)** — FROZEN. Track A. Merge `236fbc4`; impl `d594ea2`,`4eda510`,`a099fb5`,`cf3875a`,`3d6ef3b`.
> Design spec: `docs/superpowers/specs/2026-06-15-reproduce-graph-ga-design.md`
> Implementation plan: `docs/superpowers/plans/2026-06-15-reproduce-graph-ga.md`

## Goal

Build `packages/core/capychem/eval/` as the canonical AUC-of-top-10 harness + a `capychem-eval` CLI, and reproduce vanilla Graph-GA on QED to within **±0.02 of the published PMO `0.940`** (i.e. 0.92–0.96) — proving the eval contract before any beat attempt.

## Plan

New `eval/` package, headless and Postgres-free, reusing the existing oracle/validate/merge primitives:
- `eval/metric.py` — pure faithful PMO `top_auc` port (the one authoritative AUC).
- `eval/runner.py` — headless **memoized** GA runner; budget counts **unique** SMILES.
- `eval/baselines.py` — published Graph-GA table (`qed→0.940`) + ±0.02 tolerance.
- `eval/cli.py` — `capychem-eval`; `--budget` feeds both the run stop AND the metric's `max_oracle_calls`.
- `packages/core/pyproject.toml` — add `capychem-eval` to `[project.scripts]` (slice 2 edits `[project.dependencies]` — trivial merge).

**Binding (from `agent_docs/pmo-auc-and-baselines.md`):** `mutation_rate=0.067`; `top_auc` trapezoidal / `freq_log=100` / `finish=True` / `÷max_oracle_calls`; unique-call budget; PMO `pop=120`, `offspring=70`. Product loop untouched (its running curve stays a live-UI estimate). Product-loop memoization deferred to milestone 02.

**Testing:** unit tests for `top_auc` against hand-computed synthetic buffers (the faithfulness proof); harness-backed smoke at `--budget 200`; full `--budget 10000` reproduction run once, recorded.

## Tasks

- [x] Task 1 — `eval/metric.py` pure `top_auc` port + unit tests (verified bit-identical to PMO across 500 fuzz cases)
- [x] Task 2 — `eval/baselines.py` published table + `compare_to_baseline`
- [x] Task 3 — `eval/runner.py` headless memoized GA runner (memoization + patience-stop unit tests + harness smoke)
- [x] Task 4 — `eval/cli.py` + `[project.scripts]` + report-shape test
- [x] Task 5 — full `--budget 10000` QED repro: **AUC 0.9384** (diff −0.0016, within_tolerance), 2118 unique calls / 31 gens / 63.9s
- [x] Gate — `pytest` 57 passed · `mypy` clean (28 files) · `ruff` clean (integrated tree, real output)
- [x] Reviews — spec-compliance APPROVE (all 8 invariants PASS) + code-quality APPROVE-WITH-NITS (fixed) + integration APPROVE-FOR-MERGE

## Notes

- Reconciliation points the implementer must confirm against source (flagged in the plan, not blockers): exact `ValidCandidate` / `Scored` fields, `merge_and_truncate` signature, `load_starting_pop` import path. Adapt the adapter lines only — never the memoization logic.
- Worktree/env: harness-backed. If run in a worktree, set `CAPYCHEM_HARNESS_PYTHON=…/harness/.venv/bin/python`; leave `CAPYCHEM_ORACLE_BACKEND` unset (local).
- QED is a degenerate smoke target (near-zero beat-headroom) — fine for reproduction; the beat attempt + a higher-headroom task (jnk3/zaleplon) are milestone 02.
