# Slice 06-07 — in-process durable resume

**Status:** shipped (frozen) — completes milestone 06

## Goal
Make a `paused` run (from an oracle fault or a crash) CONTINUE from where it left off, reconstructing loop state from persisted rows so it reaches the SAME terminal state an uninterrupted run would (G6-exact).

## What shipped
- **`packages/core/capychem/resume.py` `reconstruct_state(session, run_id)`** — replays every persisted Generation/Candidate (ordered by index, id) through the exact `merge_and_truncate` → top-10-mean → buffer-union logic the live persist node uses, returning `gen_index`, `population`, `mol_buffer`, `calls_used`, `auc_curve` (replayed, NOT reset — so FR-003 plateau survives resume), `analyzer_hypothesis` (last row), `llm_cost_usd` (from RunCost). Pure DB reads. Because `merge_and_truncate` is monotonic global top-k, the replayed population equals the live one exactly.
- **`RunRegistry.resume_run(run_id)`** — same run_id (no new Run row); reconstructs, flips paused→running, drives `_drive(progress=...)`; a reconstructed `gen_index > 0` takes the propose-from-population branch (gen-0 special case bypassed). `_drive` seeds its initial LoopState progress fields from `progress` and starts `last_curve_len` at the reconstructed curve length so old generations don't re-broadcast.
- **`POST /runs/{id}/resume`** — 404 unknown, 409 non-paused / already-resuming; returns the resulting status. Web: a "Resume run" control on a paused run's cockpit re-opens the live WS.
- **Startup sweep** (`main.py`): orphan `running → paused` (was `stopped`) — a crashed run is now resumable. No auto-resume (explicit operator action).
- **Schema:** `Run.max_generations` column added (RunConfig had it but it was never persisted — a resumed non-default run needs it) via Alembic revision `f4251d568ae6` (server_default backfills existing rows, then dropped). First real use of the 06-05 migration infra.

## Acceptance — met (independently verified)
- **G6 exact match:** pause a run mid-flight (HarnessError at gen 1), resume → reaches the SAME `status`, `oracle_calls`, `generations`, and `top_k` (exact list equality) as an uninterrupted run of the same config+seed.
- `reconstruct_state` unit test: mol_buffer/gen_index/population/auc_curve/hypothesis/cost match hand-computed values (incl. 0-generation edge case).
- Migration: baseline→f4251d568ae6 chains cleanly; dev DB at head; `compare_metadata` clean.
- Full `pytest` green; mypy 49 clean; ruff clean; web typecheck/lint/vitest green.

## Adversarial review + fixes
A Critic pass (the core reconstruction math confirmed exact) found and reproduced TWO defects, both fixed + tested:
- **BLOCKER:** a run that crashed between its last generation's persist and finalize is swept to `paused` while already at a stop condition; resuming drove a spurious extra generation past max_generations/budget/plateau (G6 violation). **Fix:** `resume_run` computes `stop_reason` on the reconstructed state and, if already terminal, finalizes with that reason instead of driving. Test asserts no extra Generation row + the correct terminal status.
- **MAJOR:** two concurrent `POST /resume` calls both passed the paused check and spawned two drivers, corrupting `Generation.index` uniqueness. **Fix:** a synchronous `_resuming` reservation set + live-task check in `resume_run` (before any await) refuses the second call → 409. Test proves exactly one driver runs and indices stay unique.

## Notes
- `made_progress=True` in the terminal pre-check suppresses the per-generation `no_progress` signal (not evaluable from rows); only the hard terminals (budget/plateau/max_generations) short-circuit a resume.
