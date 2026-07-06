# Slice 07-06 — provenance / reproducibility manifest (OD-5)

**Goal:** Every run exports a **citable manifest** — real PyTDC version + LLM model id
+ git SHA + config + trace URL — so a result is reproducible/auditable. The harness
JSON gains the version field it never had (OD-5).

## Design
- **Harness emits the version (OD-5):** `harness/capychem_harness/score.py` `_emit` adds
  `pytdc_version = importlib.metadata.version("PyTDC")` ("0.3.6") to the success payload.
  Runs in the isolated Python-3.10 harness venv — verified via `harness/.venv`.
  Mirror in `apps/worker/app.py` (Modal path).
- `oracle/__init__.py` — refactor the subprocess call into `_run_scorer(smiles, task) ->
  payload dict` (shared by `score_smiles`); add `pytdc_version() -> str | None`
  (a fast probe: `_run_scorer([], "qed")` — qed is analytic, no model load — read
  `payload["pytdc_version"]`; best-effort, None on any harness failure).
- Alembic (chain from head `0cc25e46d571`): `Run.manifest_json` (nullable JSON) +
  `OracleCall.oracle_version` (nullable String).
- `run.py` — `build_manifest(config, *, git_sha, model_id, pytdc_version, trace_url) ->
  dict`; `finalize_run` accepts a `manifest` + sets `Run.manifest_json` AND backfills
  `OracleCall.oracle_version` for the run in one UPDATE (avoids a per-call/at-start tax).
- `runner._drive` finalize path — gather `git_sha` (`git rev-parse HEAD` via subprocess,
  best-effort), `model_id` (`proposer.llm_model()`), `pytdc_version` (`oracle.pytdc_version()`,
  once per run at the end), `trace_url` (`config.trace_url(trace_id)`); build the manifest,
  pass to `finalize_run`.
- `GET /runs/{id}/manifest` — return the persisted manifest (404 if run unknown).

## Task checklist (TDD)
- [x] 1. Harness `score.py` emits `pytdc_version`. (harness-venv test). NOTE: no
      `apps/worker` mirror needed — `pytdc_version()` probes the LOCAL harness directly
      via `_run_scorer`, independent of `CAPYCHEM_ORACLE_BACKEND`, so the Modal worker
      path never supplies it.
- [x] 2. `oracle.pytdc_version()` returns "0.3.6"; `_run_scorer` refactor keeps
      `score_smiles` byte-identical. (test)
- [x] 3. `Run.manifest_json` + `OracleCall.oracle_version` columns + Alembic (drift-verified).
- [x] 4. `run.build_manifest` (pure) + `finalize_run` sets manifest + backfills
      oracle_version. (test)
- [x] 5. `GET /runs/{id}/manifest` round-trips model id + PyTDC pin + git SHA. (API test)
- [x] 6. Gate: mypy · ruff · pytest (benchmark unchanged) · web unaffected.

## Acceptance
A run exports a citable manifest with a real PyTDC version and model id; the harness JSON
carries the version field; `GET /runs/{id}/manifest` returns git SHA + model id + PyTDC pin.

## Notes / deferrals
- Manifest **display** / download button → 07-08 (+ 07-07 export bundles it).
- `OracleCall.oracle_version` = the harness PyTDC pin (dominant oracle); per-term oracle
  versioning for composed objectives is out of scope.
