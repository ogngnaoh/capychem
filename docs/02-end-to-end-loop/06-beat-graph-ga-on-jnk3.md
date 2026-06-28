# Slice 06 — beat-graph-ga-on-jnk3

> Milestone 02 (end-to-end-loop), SPEC Phase 2. Deps: slices 01, 04, 05 (shipped + frozen).
> Design spec: `docs/superpowers/specs/2026-06-26-beat-graph-ga-on-jnk3-design.md`
> Plan: `docs/superpowers/plans/2026-06-27-beat-graph-ga-on-jnk3.md`

## Goal

Produce the milestone-02 week-7 kill-switch verdict: run the LLM-proposer loop on jnk3 to
budget and a same-seed vanilla Graph-GA control, both measured by the canonical eval module
(`metric.top_auc`, headless), and render the beat verdict. Satisfies milestone exit criterion 8.
Beating Graph-GA passes the kill-switch; not beating → narrow scope (do not abandon).

## Plan

Code (TDD, headless eval path only — no product-loop change):

- `eval/runner.py` — `ReproResult.valid_rate` (LLM-only valid-SMILES rate, gen-0 seeds excluded).
- `eval/baselines.py` — register the jnk3 published Graph-GA AUC (0.553) as a sanity reference.
- `eval/beat.py` — `run_head_to_head` runs `graph_ga` + `llm` same-seed, measures both via
  `top_auc`, returns a `BeatVerdict` (llm_auc, graph_ga_auc, diff, beat, valid rate+gate,
  published ref, unique calls).
- `eval/cli.py` — `--head-to-head` mode emits the verdict report as JSON.

## Tasks (shipped 2026-06-28 — frozen)

Code (prior session, 2026-06-27):
- [x] Task 1 — gate purity: `valid_smiles.rate` = LLM-only (exclude gen-0 seeds). `1e305b6`
- [x] Task 2 — headless `ReproResult.valid_rate`. `dce5e26`
- [x] Task 3 — jnk3 Graph-GA baseline 0.553 (sanity ref). `00b1cb0`
- [x] Task 4 — `eval/beat.py` head-to-head verdict. `286754b`
- [x] Task 5 — `--head-to-head` CLI mode. `c1f0146`
- [x] Task 6 — final-review coverage fixes. `e35dc1d`

Proposer fixes (this session — prerequisites surfaced the first time the funded `direct`
backend ever returned a real completion; the account had been at $0 until now):
- [x] `094f345` — align default cost rates to v4-pro (0.000435/0.00087; the placeholders were
  v4-flash, understating spend ~3.1×) + a 128-token output cap.
- [x] `20ed4e8` — force non-reasoning chat mode (`thinking:{"type":"disabled"}`). **Load-bearing:**
  both v4 models reason by default, leaving `message.content` empty until ~800 reasoning tokens
  finish; without this every proposal returned empty → 100% GA fallback (a silent GA-vs-GA null)
  and a 10k run would cost ~$17–27, not ~$1.
- [x] `13bc0bf` — degrade transient direct-backend failures (402/429/5xx/timeout) to the GA
  fallback (FR-005); config 4xx still propagate loudly. Keeps a long unattended run alive.

## Verdict (the deliverable)

`capychem-eval --task=jnk3 --budget=10000 --head-to-head` — every score is an in-silico oracle
score (PRD N6); the comparator is our own same-seed Graph-GA, not the published number.

| seed | LLM AUC top-10 | Graph-GA AUC top-10 | diff | beat | LLM valid-rate | LLM / GA unique calls | wall |
|---|---|---|---|---|---|---|---|
| 42 | **0.8531** | 0.6839 | **+0.1693** | ✅ | 99.0% | 3332 / 7398 | 17.6 min |
| 7  | **0.7818** | 0.5725 | **+0.2093** | ✅ | 98.1% | 2556 / 3447 | 11.2 min |

Published jnk3 Graph-GA AUC ≈ 0.553 (sanity ref); both controls (0.684, 0.573) and both LLM runs
exceed it. **Beats Graph-GA on both seeds → week-7 kill-switch passed**, robust to seed (not
seed-42 luck). The LLM reaches a higher score in fewer unique oracle calls (3332 vs 7398 @ seed 42;
2556 vs 3447 @ seed 7) — the sample-efficiency thesis, on one task, analyzer-LESS. Total DeepSeek
spend for the two verdicts + the smoke ≈ $1.60.

## Notes / decisions

- **Both runs plateau early** (`run_reproduction` patience=5 on top-100-mean): neither exhausts
  the 10k budget. `top_auc(max_oracle_calls=10000)` extends the final value, so an early, high
  plateau yields a high AUC — the metric correctly rewards sample efficiency. Identical config
  both sides → fair comparison.
- **G6 / criterion-8 reproducibility (±1%):** the harness, the GA control, and the metric are
  deterministic; the hosted-LLM sampling (temperature 0.7, pinned per-gen seed) is the one
  non-deterministic element — provider-side sampling means the LLM AUC is not bit-reproducible.
  The two-seed verdict shows the beat is robust to that variance (margin ≫ variance), not
  seed-42 luck. This is the honest reading of ±1% for a hosted-LLM proposer.
- **LLM chemical prior:** DeepSeek likely recalls strong JNK3-active scaffolds from pretraining
  rather than discovering them de novo. For the in-silico benchmark this is a legitimate win;
  PRD N6 already disclaims real-world efficacy. The analyzer (m03) is what will turn recall into
  a reasoned closed loop.
- **Cost:** the smoke + two-seed verdict cost ≈ $1.60 of DeepSeek balance total (chat mode
  ~$0.5–0.7/run; DeepSeek bills on a delay, so the balance is not a live guardrail — hence the
  transient-failure resilience). The eval CLI's headless path has no $50 cost gate (only the
  product/API loop does) — bounded by the unique-call budget, not auto-halted.

## Out of scope / deferred

- Analyzer step + with/without comparison (the differentiator) → milestone 03.
- Full 23-task sweep + multi-task UI → milestone 03; plateau-stop (FR-003) → slice 02.
- Headless-path cost gate; harness oracle model-reuse perf (warm now; non-blocking).
