# Handoff — milestone 06 production-hardening

## Completed this session
- Resolved spec §13 open decisions; ran a verified 6-agent code map; wrote the Phase-1 plan (`docs/superpowers/plans/2026-07-03-capychem-production-v1.md`); stood up this milestone.
- Shipped 6 slices on branch `milestone-06-production-hardening` (each independently verified; adversarial Critic on the honesty-sensitive + reliability slices):
  - 06-01 repo hygiene + honest docs + env origins + cost-gate reconciliation (`bc74fb2`)
  - 06-02 GitHub Actions CI, backend + web, key-free path (`5cc7acd`)
  - 06-03 WCAG-AA a11y remediation (`ef6c171`) + 06-04 axe-core CI gate, 10/10 green (`02a1ade`)
  - 06-05 Alembic baseline replaces drop-recreate (`8039544`)
  - 06-06 recoverable pause + transient retry (score + Graph-GA) + Modal n>1 fix (`79e3217`)
  - 06-07 in-process durable resume — reconstruct-from-rows, resume endpoint + web control, sweep → paused, `Run.max_generations` migration (commit pending)
- Verification highlights: pytest green (302+ with harness), axe 10/10, mypy 49 clean, ruff clean, web 30 vitest green. Adversarial Critics fixed a 06-06 finding (propose_offspring lacked retry) and TWO 06-07 findings (resume of an already-terminal run drove an extra generation; concurrent-resume duplicated Generation.index) — all with regression tests.

## Slice status across milestone
- 06-01 repo-hygiene-and-docs → shipped
- 06-02 ci-pipeline → shipped
- 06-03 a11y-remediation → shipped
- 06-04 axe-ci-gate → shipped
- 06-05 alembic-baseline → shipped
- 06-06 reliability-patches → shipped
- 06-07 durable-resume → shipped
- **Milestone 06 COMPLETE — all 7 slices shipped.**

## Current state
- Branch: `main` (clean except the untracked design spec + this session's new docs). No feature code changed yet.
- Nothing deployed/mid-flight. Engine is the shipped m05 build.
- Key verified facts: harness JSON has no version field (`score.py:102`); cost gate flat `$50` at `cost.py:16`; no LICENSE/`.github`/Alembic; `ALLOWED_ORIGINS` hardcoded `config.py:15`; a11y failures confirmed (coral `--primary` 3.57/3.28:1, `ring-ring/50`, no `aria-live`); seed-SMILES bug sinks at `graph.py:48-50`.

## Next session start here
**Milestone 06 is complete.** Begin **milestone 07 objective-ownership** (Phase 1 Tier 1 — the "make-it-yours + trust" capability). Stand up `docs/07-objective-ownership/` (milestone.md + handoff.md). Start with **07-01 run-mode-split** — the load-bearing benchmark/exploratory invariant that every other 07 feature depends on: add `Run.mode` (`benchmark`|`exploratory`, default benchmark) + `objective_json`/`constraints_json` columns via an Alembic revision (chain from `f4251d568ae6`); enforce in the API (refuse to tag a run `benchmark` if any exploratory feature is present) and eval ingestion (only `benchmark` feeds `top_auc`/baselines); add a `figure_canon` single-source module (states "21 comparable, 2 excluded", never "21/23"); a prominent mode badge on every run surface. Then per the plan: 07-02 seed-SMILES plumbing (FR-001, custom seed ⇒ exploratory), 07-03 pluggable ScoringOracle + presets, 07-04 objective composition + constraints, 07-05 quality/trust layer, 07-06 provenance manifest (OD-5), 07-07 export, 07-08 objective-authoring UI. Plan: `docs/superpowers/plans/2026-07-03-capychem-production-v1.md` (milestone-07 tasks). Alembic is live — all new columns go through migrations chained from the current head.

## Active concerns
- **Mode-split coupling:** milestone 07's seed-import/objective/oracle features each set `mode=exploratory` and need the `Run.mode` column — so 07-01 (mode) must precede them and every schema change waits on 06-05 (Alembic). Do NOT ship seed-import in 06.
- **Figure canon:** every new doc/badge must state "21 comparable, 2 excluded" from `figure_canon`, never a naive `excluded_rows`-length read of the g1 JSON (which says "1"). Never "21/23".
- **Two budget impls:** `eval/runner.py` (dict) and `loop/graph.py` (set) must stay byte-identical for G6 — any reliability edit to the score node must not diverge them.
- **Resume + plateau:** `auc_curve` is not persisted mid-run — the resume path must *recompute* it by replaying generations, not reset, or FR-003 plateau mis-fires after restart.
- **Execution discipline (repo learning):** run build subagents via file-write handoff / synchronously; independently re-verify every self-reported check; orchestrator owns all doc writes; reuse existing agents, create none.
