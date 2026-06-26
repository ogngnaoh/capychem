# Handoff — 02-end-to-end-loop (slice 05 shipped + merged; next = slice 01 or 02)

## Completed this session

- **Shipped slice 05 `unique-call-budget-and-cost-ledger`** via subagent-driven TDD (6 tasks, each
  implementer + task review; clean final whole-branch review on opus) → **merged to `main`
  (fast-forward `f1e9aaa → 8add908`)**. Impl commits `dd39aa9..8add908` (+ design `54a86a0`,
  plan/slice-doc `9735c39`).
- Landed: product-loop oracle-call memoization (`mol_buffer: set[str]` in `LoopState`) so the budget
  counts **unique** calls (cross-gen repeats are cache hits — not re-scored/counted/persisted;
  `#OracleCall == calls_used`); `RunCost.llm_cost_usd` populated (propose node accumulates
  `state["llm_cost_usd"]`) so `total_usd = llm+oracle`; per-gen cost gate rewired to read `total_usd`
  (fires on LLM spend); `llm:propose` span now wraps the await + carries token/cost via new
  `trace._live_spans`/`update_span`.
- Gate green: **pytest 108 passed**, mypy strict clean (30 files), ruff clean. `validate.py` /
  `eval/runner.py` / `harness` untouched.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → planned (dep-free)
- `02-plateau-stop-and-signal` → planned (dep-free)
- `03-modal-llm-propose-endpoint` → shipped + real-API confirmed — frozen
- `04-llm-proposer-with-ga-fallback` → shipped 2026-06-26 — frozen
- `05-unique-call-budget-and-cost-ledger` → **shipped 2026-06-26 — frozen**
- `06-beat-graph-ga-on-jnk3` → planned (deps 01, 04, 05)

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`.

## Current state

- `main` @ `8add908` (slice 05 merged; ship-docs commit on top). **`main` is ~25 commits ahead of
  `origin/main` and UNPUSHED** (local-only by choice) — push when ready. Branch
  `slice-05-unique-call-budget-cost-ledger` not yet deleted; working tree clean.
- `mutation_strategy` defaults to `"graph_ga"` → existing graph_ga product + eval paths unchanged
  (llm cost 0, gate behaves as before). Infra (m01): Langfuse v2 :3001, Postgres :5432,
  `CAPYCHEM_ORACLE_BACKEND` unset (local harness).

## Next session start here

**Start slice 01 `launch-and-watch-jnk3`** (dep-free; unblocks the slice-06 finale, which needs
01+04+05). Literal first action: read `docs/02-end-to-end-loop/milestone.md` + this handoff, then
begin the slice-01 brainstorm → spec → plan → TDD loop. (Slice 02 `plateau-stop-and-signal` is also
dep-free and can go first. Slice 06 is the milestone finale — the week-7 beat-Graph-GA kill-switch.)

## Active concerns

- **Gate purity (slice-06 BLOCKER):** `summary_json.valid_smiles.rate` still includes the gen-0 seed
  pop (always valid), so it isn't purely LLM validity. Make it LLM-only (exclude the `"starting"`
  generation / filter `proposer=="llm"`) BEFORE slice 06 reads the ≥80% jnk3 verdict. (Untouched by
  slice 05 by design; also in milestone integration notes + slice-04 doc.)
- **No-progress termination change (slice 05, M3):** with cache hits dropped, an all-duplicate
  generation now yields `_made_progress=False` → run stops on `no_progress` (intended, more-correct).
  Expect early LLM-run logs to stop on `no_progress`.
- **Optional hardening not applied (final-review R1/R2):** the 2 initial `LoopState` literals
  (runner.py, cli.py) rely on `.get()` defaults for `mol_buffer`/`llm_cost_usd` (design chose the lean
  form; both live drivers verified safe). One-line `score()` comment on why oracle-invalid candidates
  aren't memoized is also optional.
- **Modal `propose()` `n=1` latent bug** deferred (no Modal access); mirror the proposer fan-out if Modal returns.

## Slice log

- 2026-06-26 — Slice 04 (`llm-proposer-with-ga-fallback`) shipped + merged (`fd549c3..db3597b`, ship `ecfab36`).
- 2026-06-26 — Slice 05 (`unique-call-budget-and-cost-ledger`) shipped + merged (`dd39aa9..8add908`, docs `54a86a0`/`9735c39`).
