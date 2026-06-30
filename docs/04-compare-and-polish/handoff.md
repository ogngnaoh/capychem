# Handoff — 04-compare-and-polish

## Completed this session

- **Slice 01 `runs-list-and-browse` SHIPPED** (build + frontend-design critic loop). TDD throughout;
  all gates green.
  - *Backend:* `RunListItem` schema (`apps/api/capychem/api/schemas.py`); pure `_db_fields(row)` +
    `run_list_item(row, live)` + `build_run_list(...)` and `GET /runs` (merge live-overlay→`summary_json`,
    filter `status`/`task`, sort `started_at`/`best_score`/`oracle_calls`/`status` in Python, **best_score
    nulls-last**) in `routes_runs.py`; `get_run_endpoint` refactored to reuse `_db_fields` (**list == detail**
    invariant). 12 pure-function tests in `apps/api/tests/test_runs_list.py`.
  - *Frontend:* `listRuns()` + `RunListItem` in `lib/api.ts`; `app/runs/page.tsx` server shell +
    `app/runs/RunsBrowse.tsx` client table (locked columns; native-select status filter; sortable headers;
    two-run checkboxes + disabled Compare placeholder `[idA,idB]` shape for slice 02); `/ ↔ /runs` cross-links;
    `formatRelativeTime` (no `date-fns`). 5 vitest cases in `RunsBrowse.test.tsx`. **No new shadcn installs.**
  - *Critic loop:* Playwright capture harness `apps/web/e2e/runs-shot.spec.ts` (route-mock fixtures, 1280px
    PNG); Builder↔Critic agent team (Critic invoked `frontend-design`, fresh context per round) **APPROVED at
    round 2** (cap N=10). Round-1 fixes: card surface around the table, outline strategy badges (vs filled
    status), right-aligned numeric columns, sort-header affordance, styled checkbox.
- Gates green: pytest (12 new + 7 api) · mypy strict (`-p capychem -p capychem.api`) · ruff · web vitest (23) ·
  tsc · eslint.

## Slice status across milestone

- 01 `runs-list-and-browse` → **shipped**
- 02 `compare-runs` → next (deps: 01 met) · 03 `web-polish` → planned
- 04 `g1-full-23-sweep` → planned (Track-A-independent; before 05) · 05 `readme-and-langfuse-walkthrough` → planned (last)

## Current state

- Branch `main` — slice-01 code + these doc updates are **in the working tree, NOT yet committed** (operator
  confirms the ship commit). `origin/main` at `7950ba3` (local ahead by the 2 prior planning commits + the
  pending ship commit; push when the operator asks). `docs/milestones.md` still marks `04 ← active` (correct —
  milestone not complete). This slice spent **$0**; DeepSeek top-up reserved for slice 04's G1 sweep.

## Next session start here

- **EXECUTE slice 02 `compare-runs`** — write the slice doc `docs/04-compare-and-polish/02-compare-runs.md`
  first (per conventions), then build: `GET /compare?a=&b=` (both runs' top-K, **AUC resampled to a common
  oracle-call x-axis** — name + test it; compute AUC only via `packages/core/capychem/eval`), hypothesis
  sequences, per-run oracle-call + cost stats; a `/compare` web view overlaying AUC + side-by-side top-K. Flip
  the browse-page Compare placeholder (`RunsBrowse.tsx`) from disabled → navigate `/compare?a=&b=` using the
  stable `[idA,idB]` selection shape. Read-only aggregation of two `RunSnapshot`s — no new loop/scoring/WS.

## Active concerns

- **list == detail invariant** is load-bearing — both derive best_score/oracle_calls/status via `_db_fields`
  (DB path) or the live snapshot; keep them sharing the derivation in slice 02 if compare touches it.
- **Deferred (decided, not built):** cursor/`limit` pagination (YAGNI); cost column on the list (cost is on
  detail/compare per FR-013); WS on browse.
- **Track B (slice 04) pre-sweep guards stay mandatory** when that slice runs (median2 `IndexError`;
  sitagliptin NaN). **Carried m03 minors** (opportunistic): run-detail GET→WS subscribe gap (self-heals).

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; DeepSeek topped up for the G1 full-23 sweep.
- 2026-06-30 — Slice 01 `runs-list-and-browse` PLANNED (slice doc written; 3 design choices locked).
- 2026-06-30 — Slice 01 `runs-list-and-browse` SHIPPED: `GET /runs` + browse page; frontend-design critic loop
  APPROVED at round 2. Gates green. Ship commit pending operator confirmation.
