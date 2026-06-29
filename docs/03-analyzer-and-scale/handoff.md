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
- DeepSeek balance ≈ **$2.99** (topped up 2026-06-29; slice 04 spent $0). **Still short of a full 23-task
  budget-10000 LLM sweep** (~$14–23: slice-06's single-task jnk3 dual-arm verdict was ~$1.0) — slice 05 must
  scope the sweep (subset / reduced budget) or top up further before launching.
- Analyzer = reasoning-OFF + 3A conditioning (unchanged this slice).

## Next session start here

- **Recommended: 05 `week-8-sweep-and-gate`** (the milestone headline; balance now topped up). Paste-ready
  handoff prompt saved to the vault:
  `~/Documents/personal-vault/prompts/handoff/2026-06-29-capychem-milestone-03-slice-05-week-8-sweep-handoff.md`.
  Fresh planning cycle (brainstorm → design spec → plan → slice doc → execute). FIRST design decision is the
  cost-vs-scope call (see Current state): $2.99 does not cover all 23 at budget 10000.
  - **Comparator gotcha:** the existing `head_to_head` mode runs llm **without** analyzer; the Week-8 bar is
    **with-analyzer-LLM vs vanilla Graph-GA** — slice 05 must add that comparator (new sweep mode or an
    `analyzer=True` flag on `run_head_to_head`). `--all --analyzer-verdict` is the with/without DIFFERENTIATOR
    axis (already proven on jnk3), NOT the Graph-GA Week-8 bar.
- **Alternative (no cost): 03 `analyzer-live-surface`** — WS `analyzer.hypothesis` event + watch-live latest
  hypothesis + run-detail full sequence (FR-009/FR-011, Story 2/3). Dep 01 ✓.

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
