# Slice 05 — week8-sweep-and-gate

> Milestone 03 headline. Design spec: `docs/superpowers/specs/2026-06-29-week8-sweep-and-gate-design.md`.
> Implementation plan: `docs/superpowers/plans/2026-06-29-week8-sweep-and-gate.md`. Deps 01 ✓, 04 ✓, 06 ✓.

## Goal

Run the **with-analyzer-LLM vs vanilla-Graph-GA** sweep across a 9-task high-headroom PMO subset and
render the **Week-8 bar** (beat Graph-GA on ≥3 of 23 by AUC-of-top-10 → on track; <3 → pivot to
analyzer-only, do not abandon), validating the existing cost gate fires on combined
proposer+analyzer+oracle spend. Every score is an in-silico oracle score (PRD N6).

## Plan

- **Comparator (Approach A — extend, not fork).** `eval/beat.py`: `run_head_to_head` gains `analyzer:
  bool = False`, threaded into the LLM arm; `BeatVerdict` gains analyzer-health fields
  (`analyzer`, `analyzer_parse_rate`, `analyzer_calls`, `analyzer_parsed`, `parse_rate_healthy`).
  `run_reproduction(mutation_strategy="llm", analyzer=True)` already produces the arm.
- **Sweep + reader.** `eval/sweep.py`: `week8` mode (calls `run_head_to_head(..., analyzer=True)`) +
  `week8_verdict(report)` guarded reader (a beat counts only if the valid-SMILES gate passed AND parse
  rate healthy; ≥3 trustworthy → on track).
- **CLI.** `eval/cli.py`: `--week8` + `--tasks t1,t2,…` (subset, validated vs `PMO_TASKS`), both require
  `--all`; week8 verdict merged into the sweep JSON.
- **Cost gate.** `apps/api/tests/test_cost_gate.py`: focused test proving the analyzer term is inside the
  gated `total_usd` (likely already wired — graph.py folds analyzer `cost_usd` into `llm_cost_usd`).
- **Real run.** 9 tasks @ budget=10000, seed=42, both `direct` backends, background/detached, two-guard
  read on every arm. Tasks: `jnk3, median1, median2, sitagliptin_mpo, zaleplon_mpo,
  troglitazone_rediscovery, perindopril_mpo, scaffold_hop, thiothixene_rediscovery`.
- Testing: TDD on the free stub for all new code; `uv run pytest`, `mypy -p capychem -p capychem.api`,
  `ruff check .`. No web surface this slice.

## Tasks

- [ ] T1 — `run_head_to_head(analyzer=…)` + analyzer-health on `BeatVerdict` (TDD, stub).
- [ ] T2 — `week8` sweep mode (TDD, stub).
- [ ] T3 — `week8_verdict` guarded reader (≥3 trustworthy gate) (TDD).
- [ ] T4 — CLI `--week8` + `--tasks` subset wiring + verdict in output (TDD).
- [ ] T5 — cost-gate verification test: analyzer spend is in the gated total.
- [ ] T6 — full local gate → CHECKPOINT (balance ≥ ~$7) → real 9-task sweep (background) → two-guard read → verdict.
- [ ] T7 — ship: milestone/handoff status flip, freeze this doc, dated log line, ff-merge to main.

## Notes

- **Verdict asymmetry (the crux).** A 9-task subset can clear the bar **cleanly** (≥3 trustworthy beats
  among the 23 *is* ≥3/23), but **cannot cleanly trigger a pivot** — <3 on a subset is *inconclusive*,
  not "<3/23". `week8_verdict` and this doc say so explicitly. (Operator approved this framing.)
- **Only jnk3 is a proven beat** (slice 06: +0.090 @ seed 42, +0.108 @ seed 7; m02 finale beat Graph-GA
  on jnk3). The other 8 are bets — the analyzer's value has only been shown on jnk3's single-property
  objective, never on multi-property tasks. 9 tasks banks jnk3 + needs ~2 of 8 more → robust to a
  mediocre transfer rate.
- **Two-guard read on every arm** (`llm_valid_gate.passed` AND `parse_rate_healthy`): a $0-balance
  mid-run silently degrades the LLM arm to Graph-GA (slice-02 failure mode) — the guards catch it; any
  guard-failed arm lands in `degraded_tasks` and is excluded from the count.
- **Cost scope (operator decision, 2026-06-29):** top up to ~$8–10, run the 9-task subset (~$6). Does
  not bank G1 (≥6/23, milestone 04). Real spend tolerance is near-free up to ~$50 total
  ([[project_eval_compute_budget]]).
- **Both backends `direct`** for the paid run (`.env.local` sets only the proposer one;
  [[project_deepseek_v4_reasoning_default]]). The beat is vs our **own same-seed** Graph-GA control,
  never the published number (23 baselines sum to 13.742).
