# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-06 provenance manifest**
(plan Task 07-06, OD-5). Build:
1. `harness/capychem_harness/score.py:102` `_emit` — add `pytdc_version`
   (`tdc.__version__` or `importlib.metadata.version("PyTDC")`) to the emitted JSON;
   mirror in `apps/worker/app.py`; parse it in `oracle/__init__.py` (`score_smiles`
   maps it onto `OracleResult` or a batch-level field). **This runs in the isolated
   harness venv** — verify with `harness/.venv/bin/python`.
2. Alembic revision (chain from head `0cc25e46d571`): `Run.manifest_json` (git SHA, LLM
   model id from `proposer.llm_model()`, harness/PyTDC pin, Langfuse trace URL, config)
   and `OracleCall.oracle_version`.
3. `run.py`/`runner.py` — populate the manifest at run start/finalize (git SHA via
   `subprocess git rev-parse HEAD`; model id from `proposer.llm_model()`; PyTDC version
   from the harness JSON).
4. `GET /runs/{id}/manifest`. Test `test_manifest.py` (harness emits a version string;
   manifest round-trips model id + PyTDC pin + git SHA).

Then 07-07 (lineage export CSV/SDF) → 07-08 (UI: objective builder + seed-import +
quality/diversity DISPLAY + novelty seed_pop wiring + cockpit + WS reconnect).

## Current state
- Slice **07-05 shipped** (merged to `main`): molecule-quality & trust layer.
  `packages/core/capychem/quality.py` (`molecule_quality` — SA/QED/Lipinski/Veber/PAINS/
  Brenk; `internal_diversity`; `novelty`). `Candidate.quality_json` column (migration
  `0cc25e46d571`) attached at persist (annotate-only, OD-4 — benchmark top-10 unchanged;
  e2e-verified). `build_summary` now emits `diversity` per run (+ optional `novelty`).
  `packages/core/capychem/trust/gates.py` — unified `PARSE_RATE_FLOOR` (eval/beat.py +
  eval/verdict.py import it, copies deleted) + `oracle_canary(oracle)` (flags an oracle
  scoring degenerate probes ≥0.9).
- **Alembic head `0cc25e46d571`** (dev DB upgraded). New revisions chain from it.
- Gate all green: mypy (65 files) · ruff · **386** backend (+9) · migration drift · web untouched.
- `main` ahead of `origin/main` (unpushed) + m07-02..05 commits.

## Active concerns
- **Quality is annotate-only (OD-4):** it's computed at persist and never drops/reorders a
  candidate — a benchmark run's top-10 is unchanged. Keep it that way (no hard-drop in
  benchmark). An exploratory hard-drop toggle is deferred (not built).
- **Novelty is half-wired:** the helper + `build_summary(seed_pop=…)` param exist and are
  tested, but the live runner/stop_check calls don't pass `seed_pop` yet, so real runs show
  `diversity` but not `novelty`. Thread the gen-0 seed set in **07-08** (stash canonical
  gen-0 population in state; pass through the stop_check + 4 runner fallback build_summary
  sites; resume → None). Diversity already surfaces per run.
- **07-06 touches the isolated harness** — modify `score.py` and test via `harness/.venv`
  (never import harness into the modern env; PyTDC 0.3.6 / Python 3.10).
- Test basenames unique across the two roots; `.gitignore` `oracle/` root-anchored.
