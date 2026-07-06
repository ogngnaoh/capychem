# Slice 07-03 — pluggable ScoringOracle + registry + presets

**Goal:** A `ScoringOracle` protocol + registry + bundled preset oracles (PMO,
RDKit descriptors, ADMET-AI) so a run can eventually score against something other
than a single PMO task — proven at **parity** so the benchmark path is unchanged.

## Scope decision (dependency order)
- 07-03 ships the oracle **library**: protocol, registry, `PmoOracle`, descriptor
  oracles, ADMET (import-guarded), + `direction` threading (default `maximize` =
  byte-identical). It is proven at parity but does **not** rewire the loop/route.
- The loop/route **consuming** a custom oracle (with the unified score+valid+cost
  contract, OD-2 budget) + `mode=exploratory` enforcement lands in **07-04**, where
  the objective boundary defines how score/validity/cost compose. Wiring it now would
  need a throwaway PMO-specific method before that contract exists.
- "Existing benchmark path routes through `PmoOracle`" is satisfied by a **parity
  test**: `PmoOracle(task).score(smiles) == [r.score for r in score_smiles(...)]`.
  eval/runner.py (the authoritative G1 path) is untouched.

## Design
- `oracle.py` → `oracle/` package: move to `oracle/bridge.py`, `oracle/__init__.py`
  re-exports the bridge's public names (`score_smiles`, `score_batch_async`,
  `HarnessError`, `OracleResult`, `Offspring`, `propose_offspring`, …) so all 4
  importers + tests keep working unchanged. Pure move — existing oracle tests are the net.
- `protocol.py`: `ScoringOracle` Protocol — `name`, `version`, `direction`
  (`maximize`|`minimize`), `score(smiles: list[str]) -> list[float | None]` (None =
  can't score), optional `applicability_domain(smiles) -> list[float]`.
- `registry.py`: name→factory registry; `register_oracle`, `get_oracle(name, **kw)`,
  `available_oracles()`.
- `pmo.py`: `PmoOracle(task)` — `name=f"pmo:{task}"`, `direction="maximize"`,
  `score()` delegates to `score_smiles`; registered as `"pmo"`.
- `descriptors.py`: zero-new-dep RDKit oracles — `qed` (max), `sa_score` (min, via
  `Contrib/SA_Score`), `mw`/`clogp`/`tpsa` (band-oriented; direction is a documented
  convention, real objectives compose transforms in 07-04). Invalid SMILES → None.
- `admet.py`: ADMET-AI, **import-guarded** (registered only if `admet_ai` imports; the
  stub/benchmark path never needs it).
- `direction` threading: `logic._sort_key`/`merge_and_truncate`/`build_summary`/
  `build_analyzer_summary` + `eval.metric.top_auc` gain `direction="maximize"`
  (default byte-identical); `minimize` ranks ascending.

## Task checklist (TDD)
- [x] 1. Convert `oracle.py` → `oracle/` package (bridge + re-export `__init__`).
      Verify existing oracle tests + importers green (refactor safety net).
- [x] 2. `protocol.py` `ScoringOracle` Protocol + `Direction` type.
- [x] 3. `registry.py` register/get/available + test (round-trip, unknown → error).
- [x] 4. `pmo.py` `PmoOracle` + **parity test** (byte-identical to `score_smiles`).
- [x] 5. `descriptors.py` qed/sa_score/mw/clogp/tpsa + test (values sane, invalid→None).
- [x] 6. `admet.py` import-guarded + test (skips cleanly when `admet_ai` absent).
- [x] 7. `direction` threading in logic + metric + test (minimize flips ranking;
      maximize path byte-identical).
- [x] 8. Gate: mypy · ruff · pytest · web unaffected.

## Acceptance
The existing benchmark path scores byte-identically via `PmoOracle` (parity test); a
descriptor oracle scores a batch with no new dependency; a `minimize` oracle ranks
correctly; `maximize` default leaves the live loop byte-identical.

## Notes / deferrals
- Loop/route consumption of custom oracles + `mode=exploratory` enforcement → 07-04.
- `PmoOracle.version` is a static pin (`pytdc-0.3.6`) now; OD-5/07-06 makes the harness
  emit the real version dynamically.
