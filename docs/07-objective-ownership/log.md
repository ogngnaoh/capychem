# Log — milestone 07 objective-ownership

Append-only. Dated rationale/findings a diff can't show. Git records what shipped.

## 2026-07-06 — Slice 07-01 run-mode-split shipped

The benchmark/exploratory invariant carrier. Findings worth keeping:

- **Eval ingestion needs no mode gate.** The plan (Task 07-01) listed "eval/* ingestion (only `mode==benchmark` feeds top_auc/baselines)". On inspection the eval pipeline (`eval/runner.py`, `beat.py`, `verdict.py`) runs its own in-process loops with **no DB-run ingestion** — it never reads `Run` rows. So the contamination risk is purely on the **API presentation side** (a run's snapshot showing a Graph-GA "beat"). The single gate is `_gated_baseline(mode, task)` in `routes_runs.py`, applied on both the live and DB snapshot paths. No eval code changed.

- **`figure_canon` states the prose canon, not a raw row count.** The g1 sweep JSON banks 21 comparable rows + 1 excluded row (`valsartan_smarts`); the second excluded task (`sitagliptin_mpo`) was pre-excluded before the sweep and never banked. The honest framing (matching the shipped README) is **23 denominator, 21 comparable, 21/21 beat-or-matched, 2 excluded-for-cause, decisive on 9, bar ≥6**. `verify_against_report()` cross-checks the derivable subset (comparable=21) against the JSON without coupling import to file IO. Not yet consumed by README/manifest — that wiring lands in 07-06/07-08; the 07-01 deliverable is the module + the "never 21/23" test.

- **`RunSnapshot.mode` / `RunListItem.mode` are REQUIRED (no default).** A dangerous silent default would be "benchmark" (it shows a baseline). Making mode required means any construction site that forgets it fails loudly. Mode is server-derived via `derive_mode()`, never client-set. Resume threads `mode=row.mode` so a resumed run keeps its gate.

- **Local Postgres schema drift gotcha.** `init_schema` is `create_all` (no ALTER); the shared dev DB (571 runs) had a stale `runs` table. The dev DB is Alembic-managed (stamped `f4251d568ae6`), so `alembic upgrade head` applied `f8342ecfc066` non-destructively — backfilled all 571 rows to `mode="benchmark"`. CI uses a fresh Postgres, so the migration drift test (`test_migrations.py`) passes there by construction; locally it passed after the upgrade.

- Gate: mypy clean · ruff clean · 325 backend tests · web typecheck + ESLint clean · 38 vitest · axe 10/10 (amber exploratory badge exercised on /runs·/overview·/compare in light+dark, clears AA).
