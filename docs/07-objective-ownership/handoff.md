# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-04 objective composition +
constraints** (plan Task 07-04). This is where the 07-03 oracle seam gets *consumed*:
1. `packages/core/capychem/objective.py` — objective spec
   `[{oracle, weight, transform}]` + aggregator (`weighted_sum`|`weighted_product`)
   → **one scalar in [0,1]** (preserves AUC comparability by construction).
   Transforms: `sigmoid`, `double_sigmoid`/`step`, `reverse_sigmoid`, `value_map`
   (REINVENT4 parity). A `minimize` oracle is normalized to maximize-in-[0,1] by its
   transform (so the loop/AUC always see maximize — 07-03's `direction` metadata drives
   the default transform choice).
2. `packages/core/capychem/constraints.py` — hard SMARTS include/exclude via RDKit
   `FilterCatalog` (PAINS/Brenk) applied at the validity gate (same path FR-005 uses);
   soft property bands (MW/logP/TPSA) as sigmoid/step components. A **constraint-
   starvation** signal distinct from FR-003 plateau ("no candidate satisfies constraints").
3. **Loop/route consumption (deferred from 07-03):** wire the score node to evaluate the
   objective (default = single `PmoOracle(task)` = today's benchmark path, byte-identical)
   with the unified score+valid+cost contract; budget stays per-candidate (OD-2).
4. `routes_runs.py`/`intent.py` accept an objective spec; `POST /objective/validate`
   previews the composite + what's penalized. Any composed objective/constraint ⇒
   `mode=exploratory` (route through `derive_mode(objective_json=…, constraints_json=…)`).
5. Tests: `test_objective.py` (each transform; weighted-sum/product in [0,1]; single-term
   objective == raw oracle), `test_constraints.py` (SMARTS include/exclude; starvation ≠
   plateau), mode-enforcement test.

Then 07-05…07-08 per `docs/07-objective-ownership/milestone.md` + the plan. **Trust layer
(07-05) ships WITH the pluggable seam** — keep it in view as 07-04 lands.

## Current state
- Slice **07-03 shipped** (merged to `main`): `oracle.py` → `oracle/` package
  (`__init__` = bridge verbatim, so all imports + the monkeypatch test are unchanged) +
  `protocol.py` (`ScoringOracle`, read-only-property members so a frozen oracle satisfies
  it), `registry.py`, `pmo.py` (`PmoOracle`, parity-tested), `descriptors.py`
  (qed/sa_score/mw/clogp/tpsa), `admet.py` (import-guarded). `direction` threaded through
  `logic._sort_key`/`merge_and_truncate`/`build_summary`/`build_analyzer_summary` +
  `eval.metric.top_auc`, default `maximize` = byte-identical.
- Gate all green: mypy (58 files) · ruff · **346** backend · web untouched (backend-only slice).
- Alembic head unchanged (`b4ea6a051441`); no schema change in 07-03.
- `main` ahead of `origin/main` (unpushed) + the m07-02 and m07-03 commits.

## Active concerns
- **07-03 did NOT rewire the loop/route** — the live loop still calls `score_batch_async`
  directly (benchmark byte-identical). 07-04 is where a run consumes a `ScoringOracle` /
  composed objective; that's also where `mode=exploratory` enforcement for a custom
  oracle/objective/constraint lands (route through `derive_mode`).
- **PMO parity is the benchmark guardrail:** any objective wiring in 07-04 must keep a
  single-`PmoOracle(task)` run byte-identical (parity test + the eval suite).
- **`direction` normalizes at the objective, not the loop:** 07-04 transforms flip a
  `minimize` oracle into maximize-in-[0,1], so the loop/AUC stay `maximize`. The threaded
  `direction` params exist for a bare single-oracle exploratory run.
- **Test basenames unique across the two roots** (no `__init__.py`); Alembic revisions chain
  from `b4ea6a051441`; `alembic upgrade head` the dev DB after any model change.
