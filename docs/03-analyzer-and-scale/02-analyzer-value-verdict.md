# Slice 02 — analyzer-value-verdict

> Milestone 03 `analyzer-and-scale`, slice 02 (build order `01 → {02 ∥ 03 ∥ 04} → 05`; deps: 01 ✓ shipped).
> Design: `docs/superpowers/specs/2026-06-28-analyzer-value-verdict-design.md` ·
> Plan: `docs/superpowers/plans/2026-06-28-analyzer-value-verdict.md`.

## Goal

Render the differentiator kill-switch (SPEC §9 / PROJECT §9): does the analyzer add **AUC-of-top-10**
value on **jnk3** — with-analyzer LLM vs without-analyzer LLM, same seed — measured via the canonical
`eval/metric.top_auc`? Make the verdict *trustworthy* by instrumenting the analyzer `parse_hypothesis`
success rate, so a reasoning-mode CoT-truncation false null can't pass as "analyzer adds no value." A
clean null (parse-rate healthy, diff ≤ 0) → pivot to the analyzer-only narrative; **do not abandon**.
Either outcome ships.

## Plan

Headless `eval/` only — no product loop / WS / UI / Postgres change. The with/without axis already exists
(`run_reproduction(analyzer=…)` from slice 01); this slice wires the comparison, guards it, and runs it.

- **`eval/runner.py`** — `ReproResult` gains `analyzer_calls` / `analyzer_parsed` / `analyzer_parse_rate`,
  counted on the **raw** `AnalyzerResult.structured` (before `resolve_effective_hypothesis`), so a
  "no new signal" fallback can't mask a parse failure.
- **`eval/verdict.py`** (new, mirrors `eval/beat.py`) — `run_analyzer_verdict(task, budget, seed, …)` runs
  llm-with-analyzer vs llm-without-analyzer same-seed, both via `top_auc`; `AnalyzerVerdict` carries the AUC
  delta + parse-rate + `parse_rate_healthy` (0.8 floor, mirroring the valid-SMILES gate).
- **`eval/cli.py`** — `--analyzer-verdict` flag emits the JSON report + a three-way `verdict` string
  (INVALID if parse-rate <0.8 · ADDS-value if diff>0 · NULL/pivot otherwise).
- **`analyzer.py`** — `_ANALYZER_MAX_OUTPUT_TOKENS` bumped **only if** the real-run smoke shows CoT
  truncating the JSON.
- **Real run (the deliverable):** one-call parse smoke → single-seed (42) jnk3 `direct` verdict → record
  the AUC delta + kill-switch decision. `direct` for the real run only; dev/tests on `stub`.

Testing: TDD per code task on the stub/monkeypatched path (free, deterministic, harness-free). Gate each
task: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`.

## Tasks

- [ ] T1 — `eval/runner.py`: `ReproResult` parse-rate fields + raw-`structured` counting; 3 tests (all-parsed / counts-failures / off→None).
- [ ] T2 — `eval/verdict.py`: `AnalyzerVerdict` + `run_analyzer_verdict` + `_PARSE_RATE_FLOOR=0.8`; shape / determinism / arms-differ / 0.8-boundary tests.
- [ ] T3 — `eval/cli.py`: `--analyzer-verdict` mode + three-way verdict string; report-wiring + INVALID-path tests.
- [ ] T4 — Real `direct` run (single seed 42): balance check → one-call parse smoke (bump max_tokens if truncating) → tiny-budget (`--budget=300`) end-to-end dry run to confirm parse-rate health across several real summaries → full jnk3 verdict → interpret → record verdict table + kill-switch decision; slice-completion doc flips + freeze + ff-merge (ASK before push).

## Notes

- **Scope = one seed (42)** (approved): sized to the ~$2.37 prepaid DeepSeek balance (~$1.2–2.0/verdict);
  documented as a single observation, not a robustness claim ([[project_eval_compute_budget]],
  [[project_deepseek_v4_reasoning_default]]). The m02 jnk3 head-to-head used two seeds — this slice
  consciously does not, to fit the balance.
- **Load-bearing guard:** analyzer reasoning-ON `max_tokens≈2048`; if CoT crowds out `{focus, avoid}`,
  `parse_hypothesis`→None → silent "no new signal" every gen → false null that no test catches (stub never
  hits it). The parse-rate instrumentation + 0.8 floor is the whole reason this slice precedes a verdict.
- **Untouched:** `proposer.py` / `test_proposer.py`, `eval/beat.py`, product loop / WS / UI / DB schema.
- **`direct` balance risk (two distinct failure modes — `parse_rate_healthy` only catches ONE).**
  `parse_rate_healthy` guards the CoT-truncation false-null (analyzer JSON crowded out). It does NOT catch
  the *other* degradation: a $0 balance mid-run → proposer 402s → silent Graph-GA fallback corrupts the LLM
  arm itself, while parse-rate stays healthy and the verdict string would still print "ADDS value"/"NULL".
  So at T5 do NOT read the `verdict` string in isolation: (a) confirm the balance covers the run before
  starting, and (b) cross-check `with_valid_rate`/`without_valid_rate` are ≥~0.8 — a depressed valid-rate
  means the run degraded and the verdict is invalid regardless of `parse_rate_healthy`.
- **Verdict (filled at T5):** _pending the real run._

  | seed | with AUC | without AUC | diff | helps | parse-rate | with/without valid-rate | with/without unique calls | wall | cost |
  |---|---|---|---|---|---|---|---|---|---|
  | 42 | — | — | — | — | — | — | — | — | — |
