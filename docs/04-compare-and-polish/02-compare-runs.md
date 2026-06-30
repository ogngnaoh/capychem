# Slice 02 — compare-runs

> Milestone 04, Track A, slice 02. FR-012 / FR-013 / Story 4. Read-only; REST + frontend; **$0 eval**.
> Build order `01 → 02 → 03`; this slice consumes slice-01's two-run selection seam.

## Goal

`GET /compare?a=&b=` returns both runs' top-K, their AUC series **resampled to a common oracle-call
x-axis**, hypothesis sequences, and per-run oracle-call + compute-cost stats — and a `/compare` web view
overlays the two AUC curves, shows side-by-side top-K, and surfaces per-run cost. The browse page's
disabled Compare button (slice-01 seam) flips to navigate here. Read-only aggregation of two existing
runs: no new loop, scoring, LLM/oracle call, WS, or DB schema change.

## Plan

**Backend** (`apps/api/capychem/api/`)
- `schemas.py` — add `CompareRun` (the per-run subset of `RunSnapshot` the compare view shows:
  `run_id, task, status, best_score, oracle_calls, budget, cost_so_far_usd, top_k, hypotheses`),
  `AucOverlayPoint { oracle_calls, a: float|None, b: float|None }`, and
  `ComparePayload { a: CompareRun, b: CompareRun, auc_overlay: list[AucOverlayPoint] }`.
- `routes_runs.py` — **factor** `async _run_snapshot(session, registry, run_id) -> RunSnapshot | None`
  out of `get_run_endpoint` (live registry-snapshot path OR the `_db_fields` DB path → 404 source is a
  `None` return). `get_run_endpoint` becomes a thin caller (404 if `None`). Add `GET /compare?a=&b=`:
  build both snapshots, 404 if either is `None`, return `build_compare_payload(a, b)`.
  - **Cost fix (serves FR-013):** the DB path currently leaves `cost_so_far_usd` at its `0.0` default, so
    a completed run read from the DB shows `$0`. `_run_snapshot`'s DB path now reads
    `RunCost.total_usd` (new `cost.run_cost_total(session, run_id)` read helper). This also corrects
    run-detail cost for completed/post-restart runs. Live path unchanged (already carries real cost).
- `compare.py` (new, pure) — `resample_auc_to_common_axis(curve_a, curve_b) -> list[AucOverlayPoint]`
  and `build_compare_payload(a, b) -> ComparePayload` (+ `_compare_run`, `_value_at`). Kept out of the
  eval module on purpose: this resamples the **display** curve for overlay; it computes **no AUC scalar**
  (see Notes), so the "AUC only via eval" gotcha doesn't apply.
- `cost.py` — add `async def run_cost_total(session, run_id) -> float` (reads `RunCost.total_usd`, `0.0`
  if no row). Centralizes the cost read next to `oracle_cost_so_far` / `record_oracle_cost`.

**Frontend** (`apps/web/`)
- `lib/api.ts` — `CompareRun`, `AucOverlayPoint`, `ComparePayload` types + `getCompare(a, b)` (mirrors
  `getRun` base + error handling).
- `app/compare/page.tsx` server shell reading `?a`/`?b` searchParams → `CompareView` client (mirror the
  `runs/page.tsx → RunsBrowse` / `runs/[id] → LiveRun` splits). Invalid/missing `a`/`b` → a "pick two
  runs" message linking `/runs`.
- `app/compare/CompareView.tsx` — fetch `getCompare`; render a per-run **stat strip** (2 cols: `#id · task`,
  status badge, best score, oracle-calls/budget, cost — mirror run-detail `Stat`), one recharts
  `LineChart` overlaying both runs' AUC (`dataKey="a"`/`"b"`, `Legend`, distinct strokes), **side-by-side
  top-K tables** (2 cols), and hypothesis sequences (2 cols, reuse `HypothesisSection`). Header cross-links
  `/runs`. `max-w-6xl`, clean at 1280px.
- `RunsBrowse.tsx` — flip the Compare button: drop the placeholder `title`, add
  `onClick → router.push('/compare?a='+selected[0]+'&b='+selected[1])` (reuse the stable `[idA, idB]`
  shape). Disabled-until-exactly-2 logic is unchanged.

**Testing**
- Backend pure (fast, pattern of `test_runs_list.py`): `resample_auc_to_common_axis` — offset/
  different-length curves → shared union grid, endpoints align, carry-forward between sparse points,
  null before a run's first point, empty curve, single point; `build_compare_payload` field mapping.
- Backend DB (in-memory sqlite, pattern of `test_hypotheses_for`): `_run_snapshot` surfaces
  `RunCost.total_usd` for a completed run (the cost-fix regression) and returns `None` for an unknown id.
- Backend integration (`test_api.py`, real lifespan): `GET /compare?a=&b=` 200 + both `run_id`s +
  `auc_overlay` is a list; missing run → 404.
- Frontend: vitest on `CompareView` (mock `getCompare` + `recharts`; both run labels, top-K SMILES, cost,
  hypotheses render) + a `RunsBrowse` case asserting the Compare click navigates `/compare?a=1&b=2`.
- Critic loop: `e2e/compare-shot.spec.ts` route-mocks `/compare` with an edge-case fixture (offset curves,
  long task names, null-tail line, hypotheses), 1280px PNG → Builder↔Critic `frontend-design` loop (cap N=10).

## Tasks

- [x] `CompareRun` / `AucOverlayPoint` / `ComparePayload` schemas in `schemas.py`
- [x] Failing tests: `resample_auc_to_common_axis` + `build_compare_payload` (pure) in `test_compare.py`
- [x] `compare.py`: resampling (union grid, step-hold, null-before-start) + payload assembly
- [x] `cost.run_cost_total` + failing `_run_snapshot` cost/404 test (in-memory sqlite)
- [x] Factor `_run_snapshot` out of `get_run_endpoint` (cost-read fix on DB path); thin endpoint
- [x] `GET /compare?a=&b=` endpoint (404 if either run missing) + integration test in `test_api.py`
- [x] `getCompare` + compare types in `lib/api.ts`
- [x] `app/compare/page.tsx` shell + `CompareView.tsx` (stat strip · AUC overlay · side-by-side top-K · hypotheses)
- [x] Flip `RunsBrowse.tsx` Compare button → navigate `/compare?a=&b=`; update its vitest
- [x] `CompareView.test.tsx` vitest (mock `getCompare` + `recharts`)
- [x] Gates green: pytest · mypy strict (`-p capychem -p capychem.api`) · ruff · web vitest · tsc · eslint
- [x] Frontend-design critic loop: APPROVED (Builder↔Critic, cap N=10); `compare-shot.spec.ts` harness

## Notes

**Design choices (decided — per the handoff, don't agonize):**
1. **AUC resampling = union-of-x grid + step-hold carry-forward**, not linear interp. The `auc_curve` is the
   running-best top-10 mean, monotone non-decreasing; at grid point `x` a run's value is its most recent
   point at `oracle_calls <= x` (carry forward — incl. flat past its last point, since "best-so-far by N
   calls" doesn't decrease once the run stops). `None` **only before** a run's first scored generation (no
   top-10 yet) — never fabricate a leading value. Shared grid = sorted union of both curves' `oracle_calls`.
2. **Layout at 1280px = stacked:** per-run stat strip (2 col) → AUC overlay (full width) → top-K
   side-by-side (2 col) → hypotheses side-by-side (2 col). `max-w-6xl`. Two columns is why it's wider than
   run-detail's `max-w-3xl`; the overlaid chart + two top-K tables is the tight horizontal case.
3. **Per-run cost/calls in a stat strip above the chart** (mirror run-detail `Stat` cards).

**No AUC scalar is computed.** `eval.metric.top_auc` needs the full scored buffer
(`{smiles: (score, call_order)}`), which `RunSnapshot` does not carry — only `top_k` + the sparse
`auc_curve`. So compare **only resamples the existing display curve** for overlay and shows
`best_score` / `oracle_calls` / `cost` as the per-run scalars. We never recompute an AUC number, so the
"compute AUC only via the canonical eval module" gotcha is honored by not computing one at all.

**Cost-read fix is intentional and tested.** Before this slice the DB path returned `cost_so_far_usd = 0.0`
for completed runs; `_run_snapshot` now reads `RunCost.total_usd`. Surgical, serves FR-013/Exit #3, and
incidentally fixes run-detail cost after a process restart. Regression-tested via `_run_snapshot`.

**Decided non-goals (not built):** no `mutation_strategy` badge on compare (runs identified by `#id · task`;
slice-03 polish may add it) · no DB schema change (`RunSnapshot`/`RunCost` carry every field) · no
scoring/loop/LLM/oracle call · no WS (completed runs → REST only) · compare only on completed runs ·
multi-objective/Pareto out · no real-world efficacy claim (PRD N6, every score is an in-silico oracle score).

**Seam consumed:** slice-01's `selected: number[]` (`[idA, idB]`) two-run shape + disabled-until-2 Compare
button — this slice changes the button from placeholder → navigate and adds the `/compare` page.
