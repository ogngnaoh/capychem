# Handoff — milestone 06 production-hardening

## Completed this session
- Resolved spec §13 open decisions; ran a verified 6-agent code map; wrote the Phase-1 plan (`docs/superpowers/plans/2026-07-03-capychem-production-v1.md`); stood up this milestone.
- Shipped 6 slices on branch `milestone-06-production-hardening` (each independently verified; adversarial Critic on the honesty-sensitive + reliability slices):
  - 06-01 repo hygiene + honest docs + env origins + cost-gate reconciliation (`bc74fb2`)
  - 06-02 GitHub Actions CI, backend + web, key-free path (`5cc7acd`)
  - 06-03 WCAG-AA a11y remediation (`ef6c171`) + 06-04 axe-core CI gate, 10/10 green (`02a1ade`)
  - 06-05 Alembic baseline replaces drop-recreate (`8039544`)
  - 06-06 recoverable pause + transient retry (score + Graph-GA) + Modal n>1 fix (commit pending)
- Verification highlights: pytest 294 green (harness present), axe 10/10, mypy 47 clean, ruff clean, web 30 vitest green; a Critic finding on 06-06 (propose_offspring lacked retry) was fixed.

## Slice status across milestone
- 06-01 repo-hygiene-and-docs → shipped
- 06-02 ci-pipeline → shipped
- 06-03 a11y-remediation → shipped
- 06-04 axe-ci-gate → shipped
- 06-05 alembic-baseline → shipped
- 06-06 reliability-patches → shipped
- 06-07 durable-resume → planned (start here — last slice of milestone 06)

## Current state
- Branch: `main` (clean except the untracked design spec + this session's new docs). No feature code changed yet.
- Nothing deployed/mid-flight. Engine is the shipped m05 build.
- Key verified facts: harness JSON has no version field (`score.py:102`); cost gate flat `$50` at `cost.py:16`; no LICENSE/`.github`/Alembic; `ALLOWED_ORIGINS` hardcoded `config.py:15`; a11y failures confirmed (coral `--primary` 3.57/3.28:1, `ring-ring/50`, no `aria-live`); seed-SMILES bug sinks at `graph.py:48-50`.

## Next session start here
Execute slice **06-07 durable-resume** (last slice of milestone 06). Build in-process durable resume so a `paused` run (from an oracle fault or a crash) can continue where it left off. Steps: new `packages/core/capychem/resume.py` `reconstruct_state(session, run_id) -> dict` rebuilding the initial `LoopState` seed from persisted rows — `mol_buffer` = set of distinct scored `Candidate.smiles`; `calls_used` = its length; `gen_index` = `max(Generation.index)+1`; `population` = top `pop_size` by `(-score, smiles)` (matches `logic._sort_key`); effective hypothesis = last `AnalyzerHypothesis`; `auc_curve` **recomputed by replaying generations in call order** (it is NOT persisted mid-run — recompute, don't reset, or FR-003 plateau mis-fires after restart). Add a resume entry to `RunRegistry` that seeds `_drive`'s initial state from `reconstruct_state` instead of the hardcoded zeroed dict (`runner.py:144-162`); a `POST /runs/{id}/resume` endpoint + a web "Resume" control on a paused run; flip the startup sweep (`main.py:39`) from orphan `running → stopped` to `running → paused` (resumable) and optionally auto-resume. Test: a run paused by a HarnessError, then resumed, reaches the SAME terminal state a fault-free run would (budget accounting identical, G6-safe). After 06-07, milestone 06 is complete → advance `docs/milestones.md` (06 shipped, 07-objective-ownership ← active) and begin milestone 07 (mode split first).

## Active concerns
- **Mode-split coupling:** milestone 07's seed-import/objective/oracle features each set `mode=exploratory` and need the `Run.mode` column — so 07-01 (mode) must precede them and every schema change waits on 06-05 (Alembic). Do NOT ship seed-import in 06.
- **Figure canon:** every new doc/badge must state "21 comparable, 2 excluded" from `figure_canon`, never a naive `excluded_rows`-length read of the g1 JSON (which says "1"). Never "21/23".
- **Two budget impls:** `eval/runner.py` (dict) and `loop/graph.py` (set) must stay byte-identical for G6 — any reliability edit to the score node must not diverge them.
- **Resume + plateau:** `auc_curve` is not persisted mid-run — the resume path must *recompute* it by replaying generations, not reset, or FR-003 plateau mis-fires after restart.
- **Execution discipline (repo learning):** run build subagents via file-write handoff / synchronously; independently re-verify every self-reported check; orchestrator owns all doc writes; reuse existing agents, create none.
