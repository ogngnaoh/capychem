# Handoff — 04-compare-and-polish

## Completed this session

- **Slice 02 `compare-runs` SHIPPED** (FR-012/013, Story 4). TDD throughout; build → gate-green →
  frontend-design critic loop (APPROVED, zero blocking, round 1) → ship. Read-only aggregation, **$0 eval**.
  - *Backend:* `GET /compare?a=&b=` (404 if either run missing). Factored
    `_run_snapshot(session, registry, run_id) -> RunSnapshot | None` out of `get_run_endpoint` so detail +
    compare build snapshots one way. **Cost fix:** the DB path now reads `RunCost.total_usd`
    (`cost.run_cost_total`) so completed runs surface real cost (FR-013) — was the 0.0 default; also fixes
    run-detail cost after a restart. Pure `compare.py`: `resample_auc_to_common_axis` (union-of-x grid +
    step-hold carry-forward, null only before a run's first point) + `build_compare_payload`. **No AUC
    scalar computed** (snapshot lacks the buffer `top_auc` needs) — the "AUC only via eval" gotcha is
    honored by not computing one. Schemas `CompareRun`/`AucOverlayPoint`/`ComparePayload`. 8 unit tests in
    `test_compare.py` + 1 integration (`test_api.py::test_compare_two_runs_and_404`).
  - *Frontend:* `getCompare` + compare types in `lib/api.ts`; `app/compare/page.tsx` shell +
    `CompareView.tsx` (per-run stat strip w/ cost · overlaid recharts AUC w/ numeric x-axis + legend ·
    side-by-side top-K · dual hypothesis columns; `max-w-6xl`, clean 1280px). Flipped `RunsBrowse.tsx`
    Compare button placeholder → navigate `/compare?a=&b=`. `CompareView.test.tsx` + a `RunsBrowse` nav case.
  - *Critic loop:* `e2e/compare-shot.spec.ts` (route-mock fixture: offset curves/leading-null, flat
    carry-forward tail, long task name, hypotheses-vs-none, $0-vs-nonzero cost; 1280px PNG). Fresh-context
    Critic invoking `frontend-design` → **APPROVED round 1**; applied 2 non-blocking nits (numeric x-axis,
    empty-state symmetry panel).
- Gates green: pytest **240** · mypy strict (`-p capychem -p capychem.api`) · ruff · web vitest **26** · tsc · eslint.

## Slice status across milestone

- 01 `runs-list-and-browse` → **shipped** · 02 `compare-runs` → **shipped**
- 03 `web-polish` → next (deps: 02 met) · 04 `g1-full-23-sweep` → planned (Track-A-independent; before 05) ·
  05 `readme-and-langfuse-walkthrough` → planned (last)

## Current state

- Branch `main` — slice-02 code + these doc updates shipped in one commit, **merged to main and pushed to
  origin/main**. `docs/milestones.md` still marks `04 ← active` (correct — milestone not complete). This
  slice spent **$0**; DeepSeek top-up still reserved for slice 04's G1 sweep.

## Next session start here

- **EXECUTE slice 03 `web-polish`** — write the slice doc `docs/04-compare-and-polish/03-web-polish.md`
  first, then a demo-responsiveness pass: clean 1280px render with **no horizontal scroll** on run-detail
  AND compare (the tight cases are LiveRun's chart and compare's overlaid-chart + two top-K tables). No new
  endpoints/loop/scoring. Opportunistic: fold the carried m03 cosmetic minors where a polished file touches
  them. Reuse the proven Playwright-1280px capture + `frontend-design` critic loop.

## Active concerns

- **`_run_snapshot` is the shared snapshot seam** (detail + compare). The DB-path cost read
  (`cost.run_cost_total`) is load-bearing for FR-013; keep it if slice 03 touches the snapshot path.
- **Compare x-axis is numeric** (`type="number"`); LiveRun's chart is still ordinal — slice 03 may unify if
  it polishes run-detail (don't force).
- **Deferred (decided, not built):** no `mutation_strategy` badge on compare (runs id'd by `#id · task`;
  slice-03 polish may add it) · no DB schema change · no WS on compare/browse.
- **Track B (slice 04) pre-sweep guards stay mandatory** when that slice runs (median2 `IndexError`;
  sitagliptin NaN).

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; DeepSeek topped up for the G1 full-23 sweep.
- 2026-06-30 — Slice 01 `runs-list-and-browse` SHIPPED (`main @ 5ff32c3`): `GET /runs` + browse page;
  frontend-design critic loop APPROVED at round 2.
- 2026-06-30 — Slice 02 `compare-runs` SHIPPED: `GET /compare` + `/compare` view; cost-read fix on the
  shared `_run_snapshot`; frontend-design critic APPROVED round 1. Gates green (240 / 26).
