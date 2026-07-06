# Slice 07-07 — lineage export (CSV / SDF)

**Goal:** A completed run exports its full lineage — per-candidate gen/parent/proposer/
score + 07-05 quality + hypothesis-at-birth — as a **CSV** and an **RDKit-round-trippable
SDF**, so results leave the tool.

## Design
- Add to `routes_runs.py` (reuse `sessionmaker_of`): a shared `_lineage_rows(session,
  run_id) -> list[dict]` — `Candidate` joined with `Generation.index`, ordered by
  `(gen index, candidate id)`; `AnalyzerHypothesis` mapped by `after_generation_index` so
  `hypothesis_at_birth = hyps.get(gen_index - 1)` (the hypothesis that conditioned this
  generation's proposals); `quality_json` flattened into columns.
- `GET /runs/{id}/export.csv` — `csv.DictWriter` over `io.StringIO` → `Response`,
  `text/csv`, `Content-Disposition: attachment; filename="run-{id}-lineage.csv"`. 404 if
  the run is unknown.
- `GET /runs/{id}/export.sdf` — `Chem.SDWriter(StringIO)`; per candidate build a mol
  (`Chem.MolFromSmiles`, skip unparseable), `SetProp` for candidate_id/generation/parent/
  proposer/score/hypothesis + each quality field; **flush before reading** the buffer.
  `chemical/x-mdl-sdfile`. The manifest git-SHA/PyTDC-pin ride as a first-record prop so the
  file is self-describing.
- Test `test_export.py`: CSV header has lineage + quality columns and a data row;
  **SDF is RDKit-parseable** (`Chem.SDMolSupplier`/`ForwardSDMolSupplier` re-reads the mols
  + props). Both 404 on unknown run.

## Task checklist (TDD)
- [x] 1. `_lineage_rows` — candidate lineage + quality + hypothesis-at-birth. (test via
      a seeded sqlite run)
- [x] 2. `GET /runs/{id}/export.csv` — columns + rows; 404. (test)
- [x] 3. `GET /runs/{id}/export.sdf` — RDKit round-trips it (props preserved); 404. (test)
- [x] 4. Gate: mypy · ruff · pytest · web unaffected.

## Acceptance
A completed run exports a valid SDF (RDKit round-trips it) and a CSV with per-candidate
lineage + quality columns.

## Notes / deferrals
- Download buttons in the run-detail UI → 07-08.
