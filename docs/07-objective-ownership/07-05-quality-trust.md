# Slice 07-05 — molecule-quality & trust layer

**Goal:** Every top-K candidate carries a **quality report** (the reward-hacking
defense); a run surfaces **diversity/novelty**; a custom-oracle **canary** flags a
degenerate; the duplicated `_PARSE_RATE_FLOOR` is unified. Benchmark top-10 unchanged
(annotate-only, OD-4).

## Split note (UI)
Quality **display** (badges on tiles, diversity/novelty in the summary) is consolidated
into the UI slice **07-08**. 07-05 is backend: it computes + persists the data. Keeps
this slice backend-only (like 07-03/07-04b).

## Design
- `packages/core/capychem/quality.py` — `molecule_quality(smiles) -> dict`: SA-score,
  QED, MW/HBD/HBA/RotB/TPSA, Lipinski (Ro5) + Veber pass/fail, PAINS/Brenk alarms (reuse
  07-04b `Constraints`/FilterCatalog + 07-03 descriptor oracles). All RDKit-native,
  bounded cost, computed at persistence. Invalid SMILES → a report with `valid: false`.
  Use `rdFingerprintGenerator.GetMorganGenerator` (non-deprecated) for FPs.
- Alembic (chain from head `ed2d80a8ccda`): `Candidate.quality_json` (nullable JSON) —
  one column, not a table (flexible, one migration).
- `loop/graph.py` `_persist` — attach `quality_json = molecule_quality(vc.smiles)` to
  each Candidate.
- `loop/logic.build_summary` — run-level **internal diversity** (1 − mean pairwise
  Tanimoto on Morgan FPs of the population; self-contained) + **novelty vs seed**
  (fraction of population whose canonical SMILES ∉ the gen-0 seed set) into
  `summary_json` (JSON, no migration). Novelty needs the seed set → thread `seed_pop`
  (optional param; omitted ⇒ no novelty, backward-compatible).
- `packages/core/capychem/trust/gates.py` — the single home for `_PARSE_RATE_FLOOR`
  (import it in `eval/beat.py` + `eval/verdict.py`, delete the copies) + re-export
  `valid_smiles_gate`; add `oracle_canary(oracle) -> CanaryResult` (score a fixed
  degenerate probe set — tiny/huge/pathological SMILES — and warn if the oracle scores
  them implausibly high, the classic reward-hacking tell). OD-4 is annotate-only: quality
  is always computed, never drops a candidate (benchmark top-10 untouched); the
  exploratory hard-drop toggle is deferred (not in acceptance).

## Task checklist (TDD)
- [x] 1. `quality.py` `molecule_quality` — fields present; Lipinski/Veber/PAINS flags
      correct on aspirin (clean) + a degenerate; invalid → `valid: false`. (test)
- [x] 2. `Candidate.quality_json` column + Alembic (drift-verified).
- [x] 3. `_persist` attaches quality_json. (covered by an e2e / persist test)
- [x] 4. `build_summary` diversity + novelty-vs-seed. (test: identical pop → diversity 0;
      all-new pop → novelty 1)
- [x] 5. `trust/gates.py` unify `_PARSE_RATE_FLOOR` (beat.py + verdict.py import it);
      `oracle_canary` fires on a degenerate-scoring stub oracle. (test)
- [x] 6. Gate: mypy · ruff · pytest (benchmark top-10 unchanged) · web unaffected.

## Acceptance
Every top-K candidate carries a quality report; benchmark top-10 is unchanged
(annotate-only); the canary flags a known degenerate; the two `_PARSE_RATE_FLOOR`
copies are unified into one.

## Notes / deferrals
- Quality/diversity/novelty **display** → 07-08.
- **Diversity surfaces per run now** (build_summary always computes it). **Novelty** helper
  + the `seed_pop` param exist and are unit-tested, but threading the gen-0 seed set into
  the live runner/stop_check `build_summary` calls is deferred to **07-08** (avoids churn
  across the 4 fallback sites + resume; not in this slice's acceptance).
- Exploratory hard-drop quality toggle → deferred (annotate-only is the shipped default).
