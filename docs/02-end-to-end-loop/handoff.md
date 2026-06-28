# Handoff — 02-end-to-end-loop (slice 06 SHIPPED: LLM beats Graph-GA on jnk3)

## Completed this session

- **Slice 06 SHIPPED + merged to main.** Funded the run, fixed the proposer for the live DeepSeek
  API, ran the jnk3 LLM-vs-GA head-to-head → **week-7 kill-switch verdict: LLM BEATS Graph-GA**,
  robust across two seeds (every score in-silico, PRD N6).
  - Verdict (`capychem-eval --task=jnk3 --budget=10000 --head-to-head`): seed42 LLM **0.853** vs GA
    0.684 (+0.169); seed7 LLM **0.782** vs GA 0.573 (+0.209); 98–99% valid (gate ✓). LLM hits a
    higher AUC in fewer unique calls (sample-efficiency). Spend ≈ $1.60; ~11–18 min/run.
  - 4 proposer fixes: `094f345` v4-pro rates + 128-tok cap · `20ed4e8` **non-reasoning chat mode**
    (`thinking:disabled` — load-bearing: v4 reasons by default → empty content → silent GA-vs-GA) ·
    `13bc0bf` transient-failure → GA-fallback resilience. Ship-doc commit `d5e6fb4`.

## Slice status across milestone

- 01, 03, 04, 05, **06** → shipped + frozen. **02 `plateau-stop-and-signal` → planned (dep-free,
  LAST slice in m02).** Exit criteria 1–5, 7, **8 met**; **6 (plateau FR-003) → slice 02.**

## Current state

- `main` @ `d5e6fb4` (slice 06 ff-merged; feature branch deleted). **Local-only — `origin/main`
  UNPUSHED by choice.** Tree clean except `.claude/` + ~8 grandfathered ruff-format files.
- Gate green: pytest 130, mypy 31, ruff. DeepSeek ~$2.37 balance; `.env.local` = `direct` /
  `deepseek-v4-pro` / key valid.

## Next session start here

1. Start **slice 02 `plateau-stop-and-signal`** (FR-003): `stop_reason()` reads `plateau_window`,
   add a `plateaued` status, WS signal + `LiveRun.tsx`. It's the LAST m02 slice → completing it
   closes milestone 02 → milestone 03 (the analyzer differentiator). m03's analyzer with/without
   comparison should reuse slice 06's head-to-head harness (this run = the "without-analyzer" control).

## Active concerns

- **G6 ±1% reproducibility:** harness/GA/metric deterministic; the hosted LLM (temp 0.7) is not —
  the two-seed beat shows robustness, not bit-±1% (slice doc states this honestly).
- Headless eval path has **no $50 cost gate**; DeepSeek bills on a delay → balance is not a live
  guardrail (hence the transient resilience). Bounded by the unique-call budget.
- **DeepSeek v4 reasoning gotcha** ([[project_deepseek_v4_reasoning_default]]): the m03 analyzer uses
  the same model and may want reasoning ON — decide consciously, don't copy the proposer's payload.
- Optional: `chore: ruff format` for the ~8 grandfathered files (cosmetic).

## Slice log

- 2026-06-28 — Slice 06 (beat-graph-ga-on-jnk3) shipped: LLM beats Graph-GA on jnk3 (0.853/0.782 vs
  0.684/0.573 @ seeds 42/7); 4 proposer fixes for the live DeepSeek API; week-7 kill-switch PASSED.
- 2026-06-26 — Slices 05 + 01 shipped + merged.
