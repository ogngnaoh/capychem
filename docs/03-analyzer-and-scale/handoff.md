# Handoff — 03-analyzer-and-scale

## Completed this session

- **Slice 01 `analyzer-agent` IMPLEMENTED end-to-end** via `superpowers:subagent-driven-development` (fresh
  implementer + fresh reviewer per task; controller verified every gate). 7 TDD tasks, commits
  `015e7d1..2a84d46` on `slice/03-01-analyzer-agent`:
  - `015e7d1` types + `build_analyzer_summary` · `b543812` analyzer stub + `parse_hypothesis` ·
    `7a0723b` direct DeepSeek backend (reasoning ON) · `8dcb32d` strategy seam + conditioning + 8 fakes ·
    `75cfa76` `AnalyzerHypothesis` schema + `Generation` link · `4aa4b2e` `analyze` node in the product loop ·
    `2a84d46` headless eval parity (G6).
- **One approved deviation:** the effective-hypothesis resolution was extracted into
  `strategy.resolve_effective_hypothesis(result, prior)`, called by BOTH the `analyze` node and the headless
  runner (removes a duplicated block; strengthens G6 parity). `proposer.py`/`test_proposer.py` untouched.
- **Verification:** full suite **179 passed** (packages/core + apps/api, real Postgres + real oracle);
  `mypy -p capychem -p capychem.api` clean (32 files); `ruff check .` clean. Dev/CI Postgres dropped +
  recreated after the schema task (`create_all` rebuilt all 6 tables incl. `generations.analyzer_hypothesis_id`).
- **Final whole-branch review (opus):** READY TO MERGE — no Critical/Important; G6 dual-path parity verified
  against source; cost flow + graph_ga isolation + FK acyclicity confirmed.

## Slice status across milestone

- 01 `analyzer-agent` → **shipped** (2026-06-28)
- 02 `analyzer-value-verdict` → planned (dep 01 ✓ — now unblocked)
- 03 `analyzer-live-surface` → planned (dep 01 ✓ — now unblocked)
- 04 `twenty-three-task-surface` → planned (deps none)
- 05 `week-8-sweep-and-gate` → planned (deps 01 ✓, 04)

## Current state

- Slice 01 **ff-merged to `main` locally** (this is `main`'s tip); slice branch `slice/03-01-analyzer-agent`
  deleted. **`origin/main` NOT pushed** — origin is source of truth, push deferred by choice (consistent with
  prior milestones). SDD ledger: `.superpowers/sdd/progress.md` (all 7 tasks "review clean").
- DeepSeek balance ≈ $2.37 — dev/tests on the `stub` analyzer backend; real `direct` only for verdicts.

## Next session start here

1. **Start slice 02 `analyzer-value-verdict`** (the differentiator kill-switch: with/without-analyzer AUC on
   jnk3). It runs the first real `direct` analyzer calls — **instrument the `parse_hypothesis` failure rate**
   before trusting any null result (see Active concerns). Slices 03 and 04 are also unblocked.

## Active concerns

- **Reasoning-budget parse risk (slice 02/05).** Analyzer is reasoning-ON, `max_tokens≈2048`. If DeepSeek-v4
  CoT crowds out the `{focus, avoid}` JSON, `parse_hypothesis` → None → silent "no new signal" fallback every
  gen, neutering the differentiator **without failing any test** (degrades safely; stub never hits it). Log
  parse-failure rate on the first `direct` verdict; raise `max_tokens` if CoT truncates the JSON.
- **Direct backend unverified live** — reasoning-ON payload + content/usage extraction are tested only against
  monkeypatched transport; the slice-02 verdict is the first real-API confirmation.
- **Known minor (documented, deferred):** analyzer cost lands in `RunCost` one generation late; the final
  gen's analyzer cost (sub-cent) isn't re-persisted. Gate still fires within one generation.
- **Carried from milestone 02:** manual live-UI plateau-callout check; optional `plateauNotice` double-call
  hoist in `LiveRun.tsx` (Minor).

## Slice log

- 2026-06-28 — Slice 01 designed + planned + reviewed (docs only).
- 2026-06-28 — **Slice 01 `analyzer-agent` SHIPPED** — 7 TDD tasks (`015e7d1..2a84d46`), full suite 179 green,
  final review ready-to-merge. The closed-loop analyzer (the milestone differentiator) now runs in both the
  product loop and headless eval.
