# Handoff — milestone 07 objective-ownership

## Next session start here
Branch off `main` (branch-first), then execute slice **07-07 lineage export** (plan
Task 07-07). Build:
1. `GET /runs/{id}/export.csv` and `GET /runs/{id}/export.sdf` — the full lineage:
   per-candidate gen index, parent id, proposer, score, hypothesis-at-birth, + the
   07-05 `quality_json` fields flattened into columns. Read the persisted rows
   (`Candidate` join `Generation`, `AnalyzerHypothesis` by after-generation-index).
   - CSV: `csv.writer` over an in-memory buffer → `StreamingResponse`/`Response` with
     `text/csv` + a `Content-Disposition` filename.
   - SDF: build an RDKit mol per candidate (`Chem.MolFromSmiles`), attach props
     (`SetProp`) for score/gen/parent/quality, write via `Chem.SDWriter`. **RDKit must
     round-trip it** — the acceptance test parses the SDF back with `Chem.SDMolSupplier`.
2. Bundle the manifest (07-06) reference in the export (a header comment / a prop), so an
   exported file is self-describing.
3. Test `test_export.py`: CSV has lineage + quality columns; SDF is RDKit-parseable and
   carries the props.

Then 07-08 (the UI slice — the last one): objective builder + seed-import + quality/
diversity DISPLAY + novelty seed_pop wiring + manifest/export download buttons + cockpit
per-component reasoning + WS reconnect. **07-08 closes the milestone.**

## Current state
- Slice **07-06 shipped** (merged to `main`): provenance manifest (OD-5). Harness
  `score.py` `_emit` now carries `pytdc_version` (real `importlib.metadata.version("PyTDC")`
  = "0.3.6"); `oracle.pytdc_version()` reads it via a cached fast probe (`_run_scorer([],
  "qed")`, 15s timeout, `lru_cache` → one harness spawn per process). `Run.manifest_json`
  (git SHA + model id + PyTDC pin + config + trace URL) + `OracleCall.oracle_version`
  (migration `38f369ef45a6`); `run.build_manifest`; `finalize_run` persists the manifest +
  backfills oracle_version in one UPDATE; `runner._drive` builds it at finalize
  (`_git_sha()` via `git rev-parse`, `proposer.llm_model()`). `GET /runs/{id}/manifest`.
- **Alembic head `38f369ef45a6`** (dev DB upgraded). New revisions chain from it.
- Gate all green: mypy (66 files) · ruff · **391** backend (+5, incl. a real-run e2e
  asserting the manifest carries the real pin + git SHA + model id) · migration drift · web
  untouched.
- `main` ahead of `origin/main` (unpushed) + m07-02..06 commits.

## Active concerns
- **`score_smiles` refactor is byte-identical:** it now delegates to `_run_scorer`
  (extracted subprocess+parse); all existing oracle/eval tests pass unchanged — keep it
  that way (07-07 reads persisted rows, doesn't touch scoring).
- **Manifest is best-effort:** any field may be None (harness down → pytdc None; not a git
  checkout → git_sha None). The export/UI must tolerate nulls.
- **07-07 SDF must round-trip:** assert `Chem.SDMolSupplier` re-reads what `SDWriter` wrote.
- **07-08 is the milestone closer** — it also does the deferred **novelty seed_pop wiring**
  and surfaces quality/diversity/manifest. After 07-08 ships, the milestone is complete:
  flip `docs/milestones.md` (07 → shipped, 08 → active) and STOP for a fresh session.
- Test basenames unique across the two roots; `.gitignore` `oracle/` root-anchored.
