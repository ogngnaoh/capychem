# Handoff — 04-compare-and-polish

## Completed this session

- **Slice 04 `g1-full-23-sweep` SHIPPED** (Track B — the milestone's only spend slice; Exit criterion #5 / G1).
  Authoritative `capychem-eval --all --week8 --budget=10000 --seed=42` head-to-head (with-analyzer-LLM vs
  vanilla Graph-GA), measured via the canonical `eval` module.
  - **G1 MET — decisively: 21 trustworthy beats of 21 comparable PMO tasks** (bar ≥6). Every reproducible task
    beat its same-seed Graph-GA control; none degraded. Verdict: `g1-full23-10k-seed42.json`.
  - **2 of 23 excluded-for-cause (documented):** `sitagliptin_mpo` (PyTDC 0.3.6 oracle emits out-of-[0,1]
    scores) and `valsartan_smarts` (GA control 0.757 vs published 0.000). Valsartan was caught at verdict time
    by a **baseline-reproduction gate** (`|GA_control − published| > 0.15`) — invisible to the valid/parse
    guards because its scores are in-range. Both are pinned-legacy-oracle semantic defects the crash/NaN
    pre-sweep guards can't fix.
  - **Honest margins:** decisive (>0.1) on 9; thin/within single-seed noise (<0.03) on 4 (qed, deco_hop,
    zaleplon, drd2). Truthful headline = "beat or matched vanilla Graph-GA on all 21 reproducible PMO tasks
    (single seed, 10k budget), decisively on 9." No SOTA claim (PROJECT.md thesis).
  - **Cost $18.94** (balance $25.79 → $6.85), **under the operator $20 cap** — metered live via the DeepSeek
    balance API between batched per-task runs; resume-safe across 4 machine-sleep interruptions.
- Gates green (fresh): backend pytest **242** · mypy (exit 0) · ruff clean; harness crossover **2** + drd2 **1**;
  web vitest/tsc/eslint (exit 0). Committed on the branch (ref in git log).

## Slice status across milestone

- 01 `runs-list-and-browse` → **shipped** · 02 `compare-runs` → **shipped** · 03 `web-polish` → **shipped** ·
  04 `g1-full-23-sweep` → **shipped** · 05 `readme-and-langfuse-walkthrough` → **next** (last)

## Current state

- Branch `slice-04-g1-full-23-sweep` — this slice's doc updates + eval artifacts committed. **Not yet merged to
  main; not pushed** (merge + push are the operator's call). `main` is ahead of `origin` (unpushed slice-01/02/03
  + Anthropic re-skin). `docs/milestones.md` stays `04 ← active` — milestone not complete (slice 05 remains).

## Next session start here

- **EXECUTE slice 05 `readme-and-langfuse-walkthrough`** (the LAST slice; $0 spend). Recruiter-legible README +
  ≥1 Langfuse trace walkthrough of the closed loop (propose → score → analyze → redesign), legible without
  chemistry. **Fold in the G1 verdict with its honest denominator:** "beat/matched vanilla Graph-GA on all 21
  reproducible PMO tasks (single seed, 10k), decisively on 9; 2 of 23 excluded-for-cause — sitagliptin_mpo &
  valsartan_smarts oracle defects." Document the now-Anthropic-themed surface. When slice 05 ships, milestone 04
  is complete → flip `docs/milestones.md` to mark 04 shipped (no next milestone; project scope ends here).

## Active concerns

- **Report G1 honestly in the README:** never "22/22" or a SOTA beat. State the 21/21-comparable count, the 2
  documented exclusions, the single-seed caveat, and the thin margins on 4 tasks.
- **Two pinned-oracle defects are env-specific** (PyTDC 0.3.6): sitagliptin out-of-[0,1]; valsartan GA=0.757 vs
  published 0.000. The baseline-repro gate flags them if ever re-run; both are excluded, not fixed.
- **`main` ahead of `origin`** (unpushed): slice-01/02/03 + re-skin + (pending merge) slice-04.
- Slice-03 non-blocking minors carried: run-detail `10000 / 10000` stat wraps in the narrow 4-up card; warm
  plateau notice + browse `bg-accent` selected-row are code-verified, not screenshot-verified.

## Slice log

- 2026-06-30 — Milestone 04 kicked off and planned; DeepSeek topped up for the G1 full-23 sweep.
- 2026-06-30 — Slice 01 `runs-list-and-browse` SHIPPED (`main @ 5ff32c3`).
- 2026-06-30 — Slice 02 `compare-runs` SHIPPED (`main @ b0d6202`); cost-read fix on shared `_run_snapshot`.
- 2026-06-30 — Slice 03 `web-polish` SHIPPED: 1280px demo-responsiveness pass; Exit #4 MET. $0. ff-merged (not pushed).
- 2026-06-30 — **Anthropic/claude.ai design re-skin SHIPPED** (out-of-band, agent-team, 2 PASS rounds, $0).
- 2026-07-01 — **Slice 04 `g1-full-23-sweep` SHIPPED**: authoritative 10k sweep; **G1 MET** — 21 trustworthy
  beats of 21 comparable tasks (≥6 crushed), 2 of 23 excluded-for-cause (sitagliptin, valsartan oracle defects);
  $18.94 under the $20 cap. Committed on `slice-04-g1-full-23-sweep` (not merged/pushed).
