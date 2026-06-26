# Handoff — 02-end-to-end-loop (slice 01 shipped; next = slice 02 or 06)

## Completed this session

- **Shipped slice 01 `launch-and-watch-jnk3`** via subagent-driven TDD (4 tasks, each implementer +
  review; final opus whole-branch review = merge YES) → merged to `main` (ff `c9be38e → f5717ee`).
  Impl `a85d7f5..f5717ee`; design `f52b36b`; plan/slice-doc `cc63701`; ship-docs on top.
- Harness scores **jnk3** (pin `scikit-learn==1.2.2` + `numpy<2` + two `sys.modules` shims for the
  legacy RF pickle; rdkit unchanged → Graph-GA byte-identical); API accepts `task ∈ {qed, jnk3}`
  (FR-015); web form targets jnk3 with a native `mutation_strategy` select + `plateau_window`.
- Verified: full gate green (**pytest 113**, mypy 30, ruff, web vitest 9/9, typecheck, lint) +
  **live browser e2e** (launch → /runs/{id} → terminal, no error) = exit criterion 7.

## Slice status across milestone

- `01-launch-and-watch-jnk3` → **shipped 2026-06-26 — frozen**
- `02-plateau-stop-and-signal` → planned (dep-free)
- `03 / 04 / 05` → shipped — frozen
- `06-beat-graph-ga-on-jnk3` → planned (deps 01+04+05 — all now shipped)

Build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`. No slice in-progress — next is the operator's choice.

## Current state

- `main` @ ship-docs commit (slice 01 merged). **main UNPUSHED** (local-only by choice). slice-01
  branch deleted; `slice-05-...` branch deletable. Working tree clean.
- Harness re-pinned (sklearn 1.2.2 / numpy 1.26.4 / rdkit 2026.03.2; rebuilt via
  `uv sync --project harness`). `oracle/` gitignored (jnk3.pkl ~10 MB, cached locally).
  Infra: Postgres :5432, Langfuse :3001.

## Next session start here

Pick **slice 02 `plateau-stop-and-signal`** (dep-free; hangs the plateau signal on slice 01's
`LiveRun` seam) OR **slice 06 `beat-graph-ga-on-jnk3`** (finale; deps all met). For slice 06, FIRST
fix the valid_smiles gate-purity BLOCKER below.

## Active concerns

- **valid_smiles gate-purity (slice-06 BLOCKER):** `summary_json.valid_smiles.rate` includes the
  always-valid gen-0 seed pop → make it LLM-only before slice 06's verdict.
- **jnk3 minors (non-blocking):** `test_oracle_jnk3.py` skips only on missing venv, not missing model
  (ERRORs if harness-present + offline + uncached); per-batch subprocess reloads the ~10 MB model
  (perf); `score.py` import-error msg omits sklearn; shim comment over-scopes to gsk3b/drd2.

## Slice log

- 2026-06-26 — Slice 05 (`unique-call-budget-and-cost-ledger`) shipped + merged.
- 2026-06-26 — Slice 01 (`launch-and-watch-jnk3`) shipped + merged (`a85d7f5..f5717ee`).
