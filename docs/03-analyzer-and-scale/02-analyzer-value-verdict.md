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

- [x] T1 — `eval/runner.py`: `ReproResult` parse-rate fields + raw-`structured` counting; 3 tests. — `ee86685` (review clean)
- [x] T2 — `eval/verdict.py`: `AnalyzerVerdict` + `run_analyzer_verdict` + `_PARSE_RATE_FLOOR=0.8`; 3 tests. — `be8e646` (review clean)
- [x] T3 — `eval/cli.py`: `--analyzer-verdict` mode + three-way verdict string; report + INVALID + NULL-branch tests. — `82d90f9` + `c45a011` (review clean)
- [x] T3b — **(unplanned, user-approved) analyzer reasoning OFF.** The first real `direct` calls exposed the reasoning-budget risk: v4's chain-of-thought runs 2.5–3.9k tokens (variable), overran `max_tokens` and left `content` empty → parse-rate 0/3 on the budget-300 dry run (the instrumentation caught it). Fix: `thinking:{type:disabled}` + `max_tokens 2048→1024`, mirroring the proposer. Reverses slice-01 **exit-criterion #4** (reasoning ON) on empirical evidence. — `74eab91` (+ `33da829` stale-comment cleanup; review clean)
- [x] T4 — Real `direct` jnk3 verdict (seed 42): smoke → budget-300 dry run (caught the reasoning bug → T3b) → re-dry-run (parse 1.0) → full `--budget=10000` verdict → recorded below. Real spend ≈ $1.0 (full run) + ≈ $0.3 (smoke + 2 dry runs + diagnostics).

> **Shipped 2026-06-28** (commits `ee86685..33da829` on `slice/03-02-analyzer-value-verdict`; T1–T3 via
> subagent-driven-development + a final whole-branch review READY-TO-MERGE; T3b reasoning-OFF fix; T4 verdict
> a trustworthy clean NULL). Full suite green, mypy + ruff clean. FROZEN — strategic response in `handoff.md`.

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
## Verdict (the deliverable)

`CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct capychem-eval --task=jnk3 --budget=10000 --seed=42 --analyzer-verdict`
— every score is an in-silico oracle score (PRD N6); reasoning OFF for the analyzer (T3b), reasoning OFF for the proposer.

| seed | with-analyzer AUC | without-analyzer AUC | diff | helps | parse-rate | with/without valid-rate | with/without unique calls | wall |
|---|---|---|---|---|---|---|---|---|
| 42 | 0.6776 | **0.7434** | **−0.0657** | ❌ no | **1.0 (70/70)** | 0.989 / 0.890 | 2729 / 2457 | 19.6 min |

**Decision — clean NULL (the differentiator kill-switch fired honestly).** The analyzer does **not** add AUC
value on jnk3 @ seed 42 — it slightly **hurts** (−0.0657). The verdict is **trustworthy**, not an artifact:
parse-rate is 1.0 (all 70 hypotheses parsed, after the T3b reasoning-OFF fix) and both valid-rates are ≥0.8
(the LLM arm did not silently degrade to Graph-GA). Consistent with the budget-300 dry run (−0.022). Both arms
still clear the published jnk3 Graph-GA baseline (0.553) — the milestone-02 finding (LLM proposer beats GA)
holds; what fails is the *analyzer conditioning* on top of it. Per SPEC §9 / PROJECT §9 this is the
**pivot-to-analyzer-only-narrative** signal — **do not abandon**.

- **Milestone exit-criterion #5 (analyzer adds value on ≥1 task) is NOT met** on jnk3. This is an early,
  one-task, one-seed signal — the authoritative Week-8 bar is the 23-task with-analyzer-vs-Graph-GA sweep
  (slice 05). The milestone's strategic response (continue to the 23-task sweep / iterate the
  `{focus,avoid}` prompt, which may over-constrain the proposer / formally adopt the analyzer-only
  narrative) is a milestone-level decision recorded in `handoff.md`, not made in this slice.
- The slice's **own** goal — render a *trustworthy* verdict, guarded against the CoT false-null — is met.
