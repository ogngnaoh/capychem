# Slice 01 — runs-list-and-browse

> Milestone 04, Track A, slice 01. FR-010 / Story 3. Read-only; REST + frontend; **$0 eval**.
> Build order `01 → 02 → 03`; this slice is the surface you pick two runs to compare *from*.

## Goal

`GET /runs` returns the run list — sortable/filterable by status · best_score · oracle_calls ·
started_at — and a web browse page (`/runs`) lists all runs, links each to run-detail, and lets the
operator select **two** runs (the entry point slice 02's compare flow navigates from).

## Plan

**Backend** (`apps/api/capychem/api/`)
- `schemas.py` — add `RunListItem { run_id, task, mutation_strategy, status, best_score: float|None,
  oracle_calls: int, budget: int, started_at: datetime }`. Distinct, lighter than `RunSnapshot`
  (which carries no `started_at`).
- `routes_runs.py` — add `GET /runs` (query: `status?`, `task?`, `sort?`, `order?`). One
  `SELECT * FROM runs`; for each row, **merge live-overlay then DB** to derive `best_score` /
  `oracle_calls` / `status`: prefer `registry.snapshot(run_id)` (live or this-session-terminal),
  else `summary_json` (`oracle_calls`, `top_k[0].score`), else zeros. Extract a pure helper
  `run_list_item(row, live_snapshot) -> RunListItem` so **list and detail share the exact
  derivation** (handoff mandate: list == detail). Optionally have `get_run_endpoint` reuse the same
  derivation for the best_score/oracle_calls/status fields — keep surgical, don't rewrite working detail.
- **Sort + filter run in Python over the merged list, not SQL** — a live run's best_score/oracle_calls
  come from the registry, not the DB, so a SQL `ORDER BY` would order live runs by stale/null values.
  Sort keys: `started_at` (default, desc), `best_score`, `oracle_calls`, `status`; **best_score nulls
  last**. Filters: `status`, `task` (exact match, optional). N is single-user-small → cost negligible.

**Frontend** (`apps/web/`)
- `lib/api.ts` — add `RunListItem` type + `listRuns(params)` (builds the `?sort/order/status/task`
  query string; same `API_URL` base + error handling as `getRun`).
- `app/runs/page.tsx` — browse page (server-shell + client table, mirror `runs/[id]/page.tsx` →
  `LiveRun` split). shadcn `Table`: Run #, task, **strategy badge (GA/LLM)**, status badge, best
  score, **oracle-calls / budget**, started (relative time). Sortable column headers → set
  `?sort/order` + refetch. Status filter `select` ("All" + statuses present). Row → `/runs/{id}`.
  Row **checkboxes select up to 2 runs**; a **Compare button** enables only when exactly 2 are
  selected and is a **non-navigating placeholder this slice** (tooltip "Compare ships next") — slice
  02 flips it to navigate `/compare?a=&b=`. Cross-link `/ ↔ /runs` (launch ↔ browse).

**Testing** — backend: fast sqlite-seeded test (pattern of `test_hypotheses_for`) seeding completed
rows (with `summary_json`) + a running row (with a fake registry snapshot); assert merge, each sort,
nulls-last, and `status`/`task` filters. Frontend: vitest on the browse page (mock `listRuns`; rows
render, sort header changes query, status filter, row link, two-checkbox selection enables Compare).

## Tasks

- [x] `RunListItem` schema in `schemas.py`
- [x] Pure `run_list_item(row, live_snapshot)` derivation helper (shared list/detail via `_db_fields`)
- [x] `GET /runs` endpoint: merge → filter (`status`, `task`) → sort (`sort`/`order`, nulls-last)
- [x] Backend test: pure-function merge + every sort + nulls-last + filters + list==detail invariant
- [x] `listRuns(params)` + `RunListItem` type in `lib/api.ts`
- [x] `app/runs/page.tsx` server shell + `RunsBrowse.tsx` table (columns above, sortable headers, status filter, row links)
- [x] Two-run selection state + disabled-until-2 Compare placeholder (seam for slice 02)
- [x] `/ ↔ /runs` cross-links; relative-time formatter for `started_at`
- [x] Frontend vitest for the browse page
- [x] Gates green: pytest · mypy strict (`-p capychem -p capychem.api`) · ruff · web vitest · tsc · eslint
- [x] Frontend-design critic loop: APPROVED at round 2 (Builder↔Critic, cap N=10) — card surface, outline strategy badges, right-aligned numerics

## Notes

- **Decided defaults (not built):** cursor/`limit` pagination **deferred** (YAGNI at single-user
  scale — SPEC lists it; revisit only if run count grows); no cost column on the list (cost is on
  detail + compare per FR-013); no WS on browse (completed-run REST only).
- **Seam for slice 02:** the two-run selection state + Compare button is the *only* compare-aware
  thing here; slice 02 adds `GET /compare?a=&b=` + the `/compare` page and changes the button from
  placeholder → navigate. Keep the selection shape (`[idA, idB]`) stable so slice 02 reuses it.
- **List == detail agreement** is the load-bearing invariant: both derive best_score/oracle_calls
  from the same live-overlay-then-`summary_json` rule. Test that a live run and a completed run both
  read correctly through the shared helper.
- **Carried m03 minors** (opportunistic only, don't force): the run-detail GET→WS subscribe gap
  (self-heals); cosmetic follow-ups.
