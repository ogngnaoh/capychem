# Handoff — 03-analyzer-and-scale

## Completed this session

- **Slice 04 `twenty-three-task-surface` SHIPPED** (subagent-driven, 6 TDD tasks + final review).
  Commits `bd177b1..82a0f2b` on branch `slice-04-twenty-three-task-surface` (+ planning docs `244b2d5`,
  `ff002c4`). Pure plumbing, NO eval cost:
  - `eval/tasks.py::PMO_TASKS` — the 23-task registry, single source of truth.
  - `eval/baselines.py` — all 23 published Graph-GA baselines.
  - `apps/api/.../schemas.py` — `task: str` + `field_validator` vs PMO_TASKS (FR-015 → 422).
  - `eval/sweep.py` — mode-pluggable `run_sweep` (reproduce|head_to_head|analyzer_verdict; per-task error isolation).
  - `eval/cli.py` — `capychem-eval --all` (mode from `--head-to-head`/`--analyzer-verdict`; default reproduce).
  - `apps/web/app/page.tsx` — launch-page task `<select>` (all 23, default jnk3).
- Gates green: **207 pytest**, mypy clean (36), ruff clean; web **vitest 13**, typecheck + lint clean.
- Final whole-branch review (opus): **READY TO MERGE**, 0 Critical / 0 Important; the slice-05 primitive
  signatures were hand-verified clean.
- **Baseline-sum fact:** the 23 verbatim Table-2 values sum to **13.742**; the paper's reported Sum row is
  **13.751** (display-rounding gap). So the sweep's computed `published_sum` = 13.742; prose may cite 13.751.

## Slice status across milestone

- 01 `analyzer-agent` → **shipped** (2026-06-28)
- 02 `analyzer-value-verdict` → **shipped** (2026-06-28) — trustworthy clean NULL (original conditioning)
- 06 `analyzer-conditioning` → **shipped** (2026-06-29) — WIN, replicated seeds 42 (+0.090) & 7 (+0.108)
- 04 `twenty-three-task-surface` → **shipped** (2026-06-29) — registry + baselines + schema/UI + `--all` sweep
- 03 `analyzer-live-surface` → planned (dep 01 ✓ — unblocked; no eval cost)
- 05 `week-8-sweep-and-gate` → planned (deps 01 ✓, 04 ✓, 06 ✓ — ALL shipped → unblocked; needs balance top-up)

## Current state

- Branch `slice-04-twenty-three-task-surface` at `82a0f2b`, ready to merge. **Not yet merged to main** (the
  finish-branch step follows this handoff). Pattern (per slice 06): ff-merge to main locally, do NOT push.
- DeepSeek balance ≈ **$1.38** (unchanged — slice 04 spent $0). Slice 05's 23-task LLM sweep needs a top-up.
- Analyzer = reasoning-OFF + 3A conditioning (unchanged this slice).

## Next session start here

- **Two unblocked options:**
  - **03 `analyzer-live-surface`** (recommended if avoiding cost): WS `analyzer.hypothesis` event +
    watch-live latest hypothesis + run-detail full sequence (FR-009/FR-011, Story 2/3). No eval cost, dep 01 ✓.
  - **05 `week-8-sweep-and-gate`** (the milestone headline): run `capychem-eval --all --analyzer-verdict`
    across 23 (with `CAPYCHEM_PROPOSER_BACKEND=direct` + `CAPYCHEM_ANALYZER_BACKEND=direct`, source
    .env.local). **TOP UP the DeepSeek balance first** — a 23-task dual-arm LLM sweep far exceeds $1.38.
- Either way: fresh planning cycle (design spec → plan → slice doc → execute).

## Active concerns

- **`--all` sweep cost (slice 05):** a 23-task dual-arm `--analyzer-verdict` run is large. Confirm-before-invoke
  (CLAUDE.md command note). Check balance: `GET https://api.deepseek.com/user/balance` (key in .env.local).
- **`--analyzer-verdict` two-failure-mode read (carried):** always confirm BOTH `parse_rate_healthy` AND both
  `*_valid_rate` ≥ ~0.8 — a $0-balance mid-run silently degrades the LLM arm to Graph-GA with parse-rate healthy.
- **Non-blocking Minors from slice-04 final review (optional future cleanup):** `test_baseline_spot_values`
  duplicates the jnk3 assertion + the `1e-2` sum tolerance is thin (could pin the exact 13.742 sum);
  `eval/sweep.py::_run_one` has an unreachable `ValueError` (dead code); 2 pre-existing `cli.py` Minors
  (fake_run kwargs assertion; module-level `trace_to_dict` import); no automated web↔core `PMO_TASKS` drift
  guard; `--all` silently ignores `--mutation-strategy`/`--capture-analyzer-traces`.
- Frozen docs (do NOT edit): slice-01, slice-06, **slice-04** docs + their specs/plans.

## Slice log

- 2026-06-28 — Slice 01 `analyzer-agent` SHIPPED (`015e7d1..2a84d46`).
- 2026-06-28 — Slice 02 `analyzer-value-verdict` SHIPPED (`ee86685..33da829`). Trustworthy clean NULL.
- 2026-06-29 — Slice 06 `analyzer-conditioning` SHIPPED (`3fee112..6a4bda3` + docs). WIN +0.090; hardened
  seed-7 +0.108. Exit-criterion #5 MET. Pushed (`origin/main` → `cfef635`); main HEAD `507326e`.
- 2026-06-29 — **Slice 04 `twenty-three-task-surface` SHIPPED** (`bd177b1..82a0f2b`, branch
  `slice-04-twenty-three-task-surface`). Registry + 23 baselines + schema/UI selector + mode-pluggable
  `--all` sweep. All gates green; final review READY-TO-MERGE. Exit-criterion #6 MET. NO eval cost.
