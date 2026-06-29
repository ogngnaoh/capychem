# Design — week-8-sweep-and-gate (milestone 03, slice 05)

**Date:** 2026-06-29
**Status:** approved (brainstorming)
**Milestone:** `03-analyzer-and-scale` (SPEC Phase 3) · slice 05 · the milestone headline
**Related:** `docs/03-analyzer-and-scale/milestone.md` (Exit criteria #8 + #9), the FROZEN slice docs
`01-analyzer-agent.md` / `02-analyzer-value-verdict.md` / `06-analyzer-conditioning.md`,
`agent_docs/pmo-auc-and-baselines.md`.

## Goal

Run the **with-analyzer-LLM vs vanilla-Graph-GA** sweep across a high-headroom PMO subset and render the
**Week-8 bar**: beat Graph-GA on **≥3 of 23 tasks** by AUC-of-top-10 → on track; <3 → pivot to
analyzer-only narrative (do **not** abandon). Validate the existing cost gate fires on combined
proposer+analyzer+oracle spend and a real run stays far under it. Every score is an in-silico oracle score
(PRD N6).

## Scope decision — 9-task subset under a small top-up (approved)

The prepaid balance ($2.99) does not cover all 23 at budget=10000. After weighing options the operator
chose to **top up to ~$8–10 and run the 9-task high-headroom subset** at the standard budget=10000
(~$6 of paid arms). Rationale:

- **Verdict asymmetry.** The Week-8 bar is "≥3 of **23**." Three demonstrated beats among the 23 *is*
  ≥3/23 — running all 23 is not required to prove three exist. So the subset **can clear the bar cleanly**
  (≥3 trustworthy beats → on track). It **cannot cleanly trigger a pivot**: <3 beats on a subset is
  *inconclusive*, not "<3/23". The render + slice doc state this explicitly.
- **Why 9 and not 4.** Only **jnk3** is a proven beat (slice 06: +0.090 @ seed 42, +0.108 @ seed 7; m02
  finale beat Graph-GA on jnk3). The other tasks are bets — the analyzer's value has only ever been shown
  on jnk3's single-property objective, never on multi-property (MPO) tasks. A 9-task set banks jnk3 and
  needs only ~2 more of 8 to clear ≥3, robust to a mediocre MPO transfer rate; it also gives a credible
  denominator both ways. A 4-task set bets the whole verdict on 3 unproven coin-flips, and a 2/4 result
  spends real money for an inconclusive answer that forces a re-run.
- Does **not** bank G1 (≥6/23, milestone 04) — that needs the full 23. Cost ≈ $6, trivially inside the
  ~$50-total tolerance.

**Tasks (9):** `jnk3`, `median1`, `median2`, `sitagliptin_mpo`, `zaleplon_mpo`,
`troglitazone_rediscovery`, `perindopril_mpo`, `scaffold_hop`, `thiothixene_rediscovery`
(the `agent_docs/pmo-auc-and-baselines.md` high-headroom list).

## The comparator — the one bit of new code (Approach A: extend, not fork)

`run_reproduction(task, budget, seed, mutation_strategy="llm", analyzer=True)` already produces the
with-analyzer arm and exposes the guard fields (`valid_rate`, `analyzer_parse_rate`, `analyzer_calls`,
`analyzer_parsed`). The only gap: `eval/beat.py::run_head_to_head` runs the LLM arm **without** the
analyzer and `BeatVerdict` carries no analyzer-health. So:

- **`eval/beat.py`** — add `analyzer: bool = False` to `run_head_to_head`; thread it into the LLM arm
  (`run_reproduction(..., mutation_strategy="llm", analyzer=analyzer)`). Add analyzer-health fields to
  `BeatVerdict`: `analyzer: bool`, `analyzer_parse_rate: float | None`, `analyzer_calls: int`,
  `analyzer_parsed: int`, `parse_rate_healthy: bool`. Populated only when `analyzer=True`
  (`None`/`0`/`False` otherwise). Backward-compatible → the existing `head_to_head` mode is untouched.
- **`eval/sweep.py`** — add a `week8` mode to `_run_one` (calls `run_head_to_head(..., analyzer=True)`)
  and to the `run_sweep` mode-validation tuple. `headline_auc = llm_auc`, `beat = v.beat`.
- **`eval/cli.py`** — add `--week8` (→ mode `week8`) and `--tasks t1,t2,…` (override the sweep task list;
  defaults to all 23 `PMO_TASKS`). Render a **guarded** week8 verdict string (see below).

Rejected — **Approach B (new `run_week8` module):** duplicates the head-to-head scaffold for no benefit.

## Two-guard read = the verdict's integrity + the $0-balance safety net

A per-task beat counts toward the verdict **only if both** `with_valid_rate ≥ 0.8` **and**
`parse_rate_healthy` (parse_rate ≥ 0.8). A balance hitting $0 mid-run silently degrades the LLM arm to
Graph-GA (the slice-02 failure mode) — which the guards catch (valid/parse rate craters). So:

- `trustworthy_beats` = count of rows where `beat` **and** both guards pass.
- **Verdict:** `trustworthy_beats ≥ 3` → "Week-8 bar CLEARED → on track"; `< 3` → "INCONCLUSIVE on an
  N-task subset — cannot conclude <3/23; not a pivot trigger; resolve with more budget." Any guard-failed
  arm is excluded from the count and reported honestly (degraded).

Balance is checked **before launch** (`GET https://api.deepseek.com/user/balance`); margin is real but
thin, so the guard is load-bearing, not decorative.

## Cost gate (Exit #9 / done-bar #4) — verification, not new plumbing

The gate already fires on combined spend: `loop/graph.py` folds the analyze node's `cost_usd` into
`state["llm_cost_usd"]`; `apps/api/.../runner.py` gates `total = oracle + llm` against `cost.cost_cap_usd()`
(=$50). So this is structurally done. Deliverables: (a) a focused test asserting the analyzer's `cost_usd`
is inside the gated `total_usd` (check `apps/api/tests/test_cost_gate.py` first; add only if not covered);
(b) the real run's actual spend (~$0.65/arm, measured via DeepSeek balance delta) demonstrably ≪ $50.

## Run discipline (paid runs)

- Need **both** `CAPYCHEM_PROPOSER_BACKEND=direct` **and** `CAPYCHEM_ANALYZER_BACKEND=direct` (both default
  `stub`/network-free; `.env.local` sets only the proposer one). Source `.env.local` for `DEEPSEEK_API_KEY`.
- Confirm balance covers the planned spend **first**; two-guard read on **every** arm.
- A 9-task sweep is **hours** — run it **detached in the background**; per-task error isolation is already
  built into `run_sweep`.
- Measure only via `eval/metric.top_auc`; the beat is vs our **own same-seed** Graph-GA control, not the
  published number (which is a sanity reference; the 23 verbatim Table-2 values sum to **13.742**).

## Testing

TDD, stub backend (free, deterministic) for all new code:
- `run_head_to_head(analyzer=True)` populates analyzer-health fields; `analyzer=False` unchanged.
- `week8` sweep mode dispatches correctly; mode validation rejects unknown modes.
- CLI `--week8` selects the mode; `--tasks` overrides the task list; the guarded verdict string is correct
  for ≥3 / <3 / guard-failed cases.
- Cost-gate test asserts analyzer cost is in the gated total.
- Gates green: `uv run pytest`, `uv run mypy -p capychem -p capychem.api`, `uv run ruff check .`
  (no web surface touched this slice).

## Non-goals (defer — do NOT build)

Live WS `analyzer.hypothesis` surface / watch-live / run-detail sequence (slice 03) · compare-runs view
(milestone 04) · the ≥6/23 G1 push (m04) · multi-objective / Pareto · expensive oracles (ADMET-AI/Vina) ·
adding dollar-cost tracking to the headless eval path (balance-delta suffices).

## Done bar (= milestone Exit criteria #8 + #9)

1. The with-analyzer-LLM vs Graph-GA comparator exists, is TDD-tested on the stub, and runs via the
   canonical `capychem-eval` / `run_sweep` path (`top_auc`, our own same-seed control).
2. The 9-task subset is run for real; both guards green on every arm (or degraded arms reported honestly).
3. The Week-8 verdict is rendered: trustworthy-beats count + per-task table; ≥3 → on track, <3 →
   inconclusive (not a clean pivot on a subset), decision recorded.
4. The cost gate is shown to fire on combined proposer+analyzer+oracle spend and a run stays under it.
5. Gates green (pytest, mypy ×2, ruff). Ship docs: milestone status flip, handoff overwrite, slice-doc
   freeze, dated "Slice 05 shipped" log line.
