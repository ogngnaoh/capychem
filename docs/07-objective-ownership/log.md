# Log — milestone 07 objective-ownership

Append-only. Dated rationale/findings a diff can't show. Git records what shipped.

## 2026-07-06 — Slice 07-02 seed-SMILES plumbing shipped

FR-001: an operator's bring-your-own compounds now reach the gen-0 population. Findings:

- **`seed_smiles` is a `list[str]`, never the RNG `seed`.** The integer RNG `seed` (G6
  reproducibility) and the seed *population* are distinct concepts; the plan flagged the
  hazard of overloading one for the other. A dedicated `list[str]` column + LoopState key
  keeps them orthogonal — a test asserts `cfg.seed == 42` is untouched by a custom seed.

- **Gen-0 tops up from the shipped pool.** The plan's "GA-filled from the shipped pool or
  truncated to exactly pop_size" resolves to: canon+dedup operator seeds (they lead), then
  fill remaining slots from the shipped starting pool (skipping dups) up to `pop_size`
  (truncate if the operator gives more). Top-up guarantees the ≥2 parents crossover needs.
  Trade-off: a tiny custom seed set is diluted by generic fill — acceptable for a GA that
  needs diversity, and it's exploratory-only anyway.

- **The `/runs` boundary validator is authoritative.** The intent-preview already validated
  a *single* seed, but a client can POST `/runs` directly, so the Pydantic `field_validator`
  on `CreateRunRequest.seed_smiles` RDKit-checks each entry, drops empties, and collapses an
  all-empty/`[]` list to `None` (so it stays `benchmark` via `derive_mode`). The intent
  preview stays best-effort; the Launcher only sends a seed to it when exactly one is parsed,
  so a valid multi-seed list is never falsely refused there.

- **Two test roots, one rootdir, no `__init__.py`** → test file basenames must be unique
  across `packages/core/tests` and `apps/api/tests`, or pytest errors on an import-file
  mismatch. Renamed the API test to `test_seed_plumbing_route.py`.

- **Single-line `<input>` strips newlines** (DOM), so the 07-02 seed field is space/comma
  separated; multi-line SDF/CSV paste with an accepted/rejected list is deferred to 07-08.

- Gate: mypy (53 files) · ruff · **336** backend (was 325; +6 core, +5 API incl. a real-app
  end-to-end drive) · web typecheck + ESLint · 40 vitest · migration drift gate. Alembic head
  `b4ea6a051441`; dev DB upgraded (571 rows backfilled `seed_source="default"`).

## 2026-07-06 — Slice 07-01 run-mode-split shipped

The benchmark/exploratory invariant carrier. Findings worth keeping:

- **Eval ingestion needs no mode gate.** The plan (Task 07-01) listed "eval/* ingestion (only `mode==benchmark` feeds top_auc/baselines)". On inspection the eval pipeline (`eval/runner.py`, `beat.py`, `verdict.py`) runs its own in-process loops with **no DB-run ingestion** — it never reads `Run` rows. So the contamination risk is purely on the **API presentation side** (a run's snapshot showing a Graph-GA "beat"). The single gate is `_gated_baseline(mode, task)` in `routes_runs.py`, applied on both the live and DB snapshot paths. No eval code changed.

- **`figure_canon` states the prose canon, not a raw row count.** The g1 sweep JSON banks 21 comparable rows + 1 excluded row (`valsartan_smarts`); the second excluded task (`sitagliptin_mpo`) was pre-excluded before the sweep and never banked. The honest framing (matching the shipped README) is **23 denominator, 21 comparable, 21/21 beat-or-matched, 2 excluded-for-cause, decisive on 9, bar ≥6**. `verify_against_report()` cross-checks the derivable subset (comparable=21) against the JSON without coupling import to file IO. Not yet consumed by README/manifest — that wiring lands in 07-06/07-08; the 07-01 deliverable is the module + the "never 21/23" test.

- **`RunSnapshot.mode` / `RunListItem.mode` are REQUIRED (no default).** A dangerous silent default would be "benchmark" (it shows a baseline). Making mode required means any construction site that forgets it fails loudly. Mode is server-derived via `derive_mode()`, never client-set. Resume threads `mode=row.mode` so a resumed run keeps its gate.

- **Local Postgres schema drift gotcha.** `init_schema` is `create_all` (no ALTER); the shared dev DB (571 runs) had a stale `runs` table. The dev DB is Alembic-managed (stamped `f4251d568ae6`), so `alembic upgrade head` applied `f8342ecfc066` non-destructively — backfilled all 571 rows to `mode="benchmark"`. CI uses a fresh Postgres, so the migration drift test (`test_migrations.py`) passes there by construction; locally it passed after the upgrade.

- Gate: mypy clean · ruff clean · 325 backend tests · web typecheck + ESLint clean · 38 vitest · axe 10/10 (amber exploratory badge exercised on /runs·/overview·/compare in light+dark, clears AA).
