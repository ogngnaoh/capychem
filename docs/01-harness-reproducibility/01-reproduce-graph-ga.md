# Slice 01 — reproduce-graph-ga

> Status: **planned** (ready to implement). Track A (sequential before slice 3).
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

- [ ] Task 1 — `eval/metric.py` pure `top_auc` port + unit tests (4 hand-computed cases)
- [ ] Task 2 — `eval/baselines.py` published table + `compare_to_baseline`
- [ ] Task 3 — `eval/runner.py` headless memoized GA runner (memoization unit test + harness smoke)
- [ ] Task 4 — `eval/cli.py` + `[project.scripts]` + report-shape test
- [ ] Task 5 — full `--budget 10000` QED reproduction; assert 0.92–0.96; record the number (orchestrator-run)
- [ ] Gate — `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` green with real output
- [ ] Reviews — spec-compliance (vs the reference note) + code-quality, fresh context

## Notes

- Reconciliation points the implementer must confirm against source (flagged in the plan, not blockers): exact `ValidCandidate` / `Scored` fields, `merge_and_truncate` signature, `load_starting_pop` import path. Adapt the adapter lines only — never the memoization logic.
- Worktree/env: harness-backed. If run in a worktree, set `CAPYCHEM_HARNESS_PYTHON=…/harness/.venv/bin/python`; leave `CAPYCHEM_ORACLE_BACKEND` unset (local).
- QED is a degenerate smoke target (near-zero beat-headroom) — fine for reproduction; the beat attempt + a higher-headroom task (jnk3/zaleplon) are milestone 02.
