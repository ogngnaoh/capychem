# Handoff — milestone 06 production-hardening

## Completed this session
- Resolved spec §13 open decisions (OD-1 cheap patches · OD-2 per-candidate budget · OD-3 flat cost cap · OD-4 annotate-only-in-benchmark quality gate · OD-5 provenance must be added · OD-6 docking→Phase 2 · OD-7 Python-class oracle plugin first).
- Ran a verified read-only code map of all six Phase-1 subsystems (6-agent workflow, independently re-verified the load-bearing claims against source).
- Wrote the Phase-1 implementation plan: `docs/superpowers/plans/2026-07-03-capychem-production-v1.md` (splits Phase 1 into milestone 06 production-hardening + milestone 07 objective-ownership).
- Stood up `docs/06-production-hardening/` (this milestone + handoff); updated `docs/milestones.md` (06 ← active, 07 planned).

## Slice status across milestone
- 06-01 repo-hygiene-and-docs → shipped
- 06-02 ci-pipeline → shipped
- 06-03 a11y-remediation → shipped
- 06-04 axe-ci-gate → shipped
- 06-05 alembic-baseline → shipped
- 06-06 reliability-patches → planned (start here — last slice of milestone 06)

## Current state
- Branch: `main` (clean except the untracked design spec + this session's new docs). No feature code changed yet.
- Nothing deployed/mid-flight. Engine is the shipped m05 build.
- Key verified facts: harness JSON has no version field (`score.py:102`); cost gate flat `$50` at `cost.py:16`; no LICENSE/`.github`/Alembic; `ALLOWED_ORIGINS` hardcoded `config.py:15`; a11y failures confirmed (coral `--primary` 3.57/3.28:1, `ring-ring/50`, no `aria-live`); seed-SMILES bug sinks at `graph.py:48-50`.

## Next session start here
Execute slice **06-05 alembic-baseline** (enabling gate for milestone 07 — must precede any new schema column). Steps: add `alembic` to `packages/core/pyproject.toml`; `alembic.ini` + `packages/core/capychem/db/migrations/` (env.py wired to `Base.metadata` + `CAPYCHEM_DATABASE_URL`); autogenerate an initial revision that EXACTLY reproduces today's `create_all` schema (6 models, verify autogenerate diff vs metadata is empty); wire startup to `alembic upgrade head` (keep `create_all` only for ephemeral test DBs in `db/session.py`); on an existing dev DB born from `create_all` (no `alembic_version`), `alembic stamp head` must baseline it so a subsequent `upgrade head` is a no-op (does NOT re-create existing tables). Retire the "drop/recreate, Alembic deferred" note in `db/models.py:4-6` + `db/session.py:3-6`; document `alembic upgrade head` in CONTRIBUTING/README. Then **06-06 reliability-patches** (recoverable pause on HarnessError, oracle-fault tolerance, in-process durable resume via a new `resume.py` rebuilding mol_buffer/gen_index/population/auc_curve from rows, startup sweep → paused, Modal propose n>1 + transient parity). 06-05 and 06-06 touch disjoint files (db/migrations vs runner/graph/worker) and could run as parallel worktree Builders.

## Active concerns
- **Mode-split coupling:** milestone 07's seed-import/objective/oracle features each set `mode=exploratory` and need the `Run.mode` column — so 07-01 (mode) must precede them and every schema change waits on 06-05 (Alembic). Do NOT ship seed-import in 06.
- **Figure canon:** every new doc/badge must state "21 comparable, 2 excluded" from `figure_canon`, never a naive `excluded_rows`-length read of the g1 JSON (which says "1"). Never "21/23".
- **Two budget impls:** `eval/runner.py` (dict) and `loop/graph.py` (set) must stay byte-identical for G6 — any reliability edit to the score node must not diverge them.
- **Resume + plateau:** `auc_curve` is not persisted mid-run — the resume path must *recompute* it by replaying generations, not reset, or FR-003 plateau mis-fires after restart.
- **Execution discipline (repo learning):** run build subagents via file-write handoff / synchronously; independently re-verify every self-reported check; orchestrator owns all doc writes; reuse existing agents, create none.
