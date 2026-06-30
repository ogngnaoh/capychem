# Handoff — 04-compare-and-polish

## Completed this session

- **Slice 01 `runs-list-and-browse` PLANNED** (plan-only session — stopped before execute). Wrote
  `docs/04-compare-and-polish/01-runs-list-and-browse.md` (Goal / Plan / 10 Tasks / Notes); re-verified the
  surface (no `GET /runs`, no browse page; `Run.summary_json` carries `oracle_calls` + `top_k`→best_score;
  live runs' fresh values live in the in-memory `RunRegistry`).
- **Three design choices reviewed + locked into the slice doc:** (1) browse columns = Run # · task ·
  **strategy** · status · best score · **calls/budget** · started; (2) sort/filter = **endpoint-owned** via
  `?sort/order/status/task` (page refetches — tested contract); (3) compare seam = **scaffold two-run
  selection now** (checkboxes + disabled Compare button; slice 02 flips it to navigate `/compare?a=&b=`).
- **Load-bearing decision recorded:** list+detail share one `run_list_item(row, live_snapshot)` derivation
  (live-overlay → `summary_json`); sort/filter run in **Python over the merged list, not SQL** — a live run's
  best_score/oracle_calls come from the registry, so a SQL `ORDER BY` would mis-order live runs.

## Slice status across milestone

- 01 `runs-list-and-browse` → planned · **plan locked, ready to execute** (start here)
- 02 `compare-runs` → planned · 03 `web-polish` → planned
- 04 `g1-full-23-sweep` → planned (Track-A-independent; before 05) · 05 `readme-and-langfuse-walkthrough` → planned (last)

## Current state

- Branch `main` — slice doc + this handoff just committed (planning). `origin/main` at `7950ba3` (local
  ahead, NOT pushed — push when the operator asks). `docs/milestones.md` still marks `04 ← active` (slice 01
  not shipped → no status flip). This slice spends **$0**; DeepSeek top-up reserved for slice 04's G1 sweep.

## Next session start here

- **EXECUTE slice 01** against `docs/04-compare-and-polish/01-runs-list-and-browse.md` — TDD; choices are
  locked, do NOT re-brainstorm. First action: `RunListItem` schema in `schemas.py` + the pure
  `run_list_item(row, live_snapshot)` helper + `GET /runs` (merge → filter → sort, best_score nulls-last),
  with a fast sqlite-seeded backend test. Paste-ready prompt: `personal-vault/prompts/handoff/
  2026-06-30-capychem-milestone-04-slice-01-runs-list-and-browse-handoff.md`.

## Active concerns

- **list == detail invariant** is load-bearing — test a live run and a completed run both read correctly
  through the shared derivation helper.
- **Deferred (decided, not built):** cursor/`limit` pagination (YAGNI); cost column on the list (cost is on
  detail/compare per FR-013); no WS on browse.
- **Track B (slice 04) pre-sweep guards stay mandatory** when that slice runs (median2 `IndexError`;
  sitagliptin NaN). **Carried m03 minors** (opportunistic): run-detail GET→WS subscribe gap (self-heals).

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; DeepSeek topped up for the G1 full-23 sweep.
- 2026-06-30 — Slice 01 `runs-list-and-browse` PLANNED (slice doc written; 3 design choices locked); plan-only session, execution deferred.
