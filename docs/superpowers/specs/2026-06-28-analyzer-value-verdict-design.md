# Design — Analyzer value verdict (milestone-03 slice 02)

**Status:** Approved
**Date:** 2026-06-28
**Milestone:** 03 `analyzer-and-scale` (SPEC Phase 3 — the differentiator)
**Slice:** `02-analyzer-value-verdict` (build order: `01 → {02 ∥ 03 ∥ 04} → 05`; deps: 01 ✓ shipped)
**Consumes:** slice-01 analyzer engine — `eval/runner.py::run_reproduction(analyzer=…)` (the with/without
axis), `analyzer.py` (`direct` DeepSeek backend, reasoning ON), `loop/strategy.py::{run_analyzer_sync,
resolve_effective_hypothesis}`, `eval/metric.top_auc` (canonical AUC), `eval/beat.py` (the head-to-head
template). All frozen except `analyzer.py`'s `_ANALYZER_MAX_OUTPUT_TOKENS` (sanctioned bump, see below).
**Consumed by:** slice 05 (Week-8 23-task sweep reuses the verdict shape).

## Context & goal

Slice 01 shipped the analyzer engine and the with/without axis (`run_reproduction(analyzer: bool)`), but
ran it only on the **stub** backend. This slice runs the **first real `direct` analyzer calls** and renders
the **differentiator kill-switch** (SPEC §9 / PROJECT §9): does the analyzer add **AUC-of-top-10** value on
jnk3 — with-analyzer LLM vs without-analyzer LLM, same seed? If it does → the closed-loop differentiator is
confirmed. If it does not → pivot to the analyzer-only narrative; **do not abandon**. Either outcome ships.

**Load-bearing risk this slice exists to neutralize.** The analyzer runs reasoning-ON with
`max_tokens≈2048`. If DeepSeek-v4's chain-of-thought crowds out the `{focus, avoid}` JSON tail,
`parse_hypothesis` returns `None`, the loop falls back to "no new signal" **every generation**, and the
verdict reads "analyzer adds no value" — a **false null no test catches** (it degrades safely; the stub
backend never hits it). Therefore the verdict is only trustworthy once the real-run `parse_hypothesis`
success rate is **measured and confirmed healthy**. A null result under truncation is invalid by
construction.

Scope is **headless `eval/` only**: parse-rate instrumentation, a verdict module + CLI flag, and the real
single-seed jnk3 run. It is **not** the live WS surface (slice 03), the 23-task scale (slice 04), the
Week-8 sweep (slice 05), or multi-seed robustness (consciously descoped — see Decision 6).

## Decisions confirmed at brainstorm

1. **Verdict scope = one seed (42).** The Week-8 kill-switch needs ≥1 task; a single clean data point
   satisfies it, and ~$1.2–2.0 fits the ~$2.37 prepaid DeepSeek balance with margin for the parse smoke.
   Two-seed robustness (as m02 did) would risk the balance hitting $0 mid-run, which the `direct` backend
   degrades to Graph-GA — silently corrupting the LLM arm. Descoped consciously; revisit if balance allows.
2. **New module `eval/verdict.py`, mirroring `beat.py`.** The analyzer on/off axis is a distinct comparison
   from `beat.py`'s graph_ga-vs-llm axis; folding it in would conflate two axes in one verdict type. The new
   module reuses the same primitives (`run_reproduction`, `top_auc`) and the same CLI idiom (`--head-to-head`
   → `--analyzer-verdict`). `beat.py` is untouched.
3. **Parse-rate floor = 0.8**, reusing the valid-SMILES-gate threshold (`loop/logic.valid_smiles_gate`). A
   with-arm parse-rate `< 0.8` marks the verdict INVALID (bump `max_tokens`, rerun); `≥ 0.8` makes a null
   trustworthy.
4. **Count on the RAW `AnalyzerResult.structured`, not the effective hypothesis.** `run_analyzer_sync`
   returns the raw result *before* `resolve_effective_hypothesis` re-injects the last-good hypothesis on
   fallback. Counting `result.structured is not None` measures genuine parse success; counting the effective
   hypothesis would mask every failure as a success.
5. **`_ANALYZER_MAX_OUTPUT_TOKENS` is the only frozen-engine knob this slice may turn**, and only if the
   parse smoke shows CoT truncating the JSON (explicitly sanctioned by the milestone integration notes).
6. **One data point, stated honestly.** The hosted LLM proposer is provider-sampled (temperature 0.7,
   pinned per-gen seed) → not bit-reproducible, same as the m02 verdict. The slice doc records this as a
   single seed-42 observation, not a robustness claim.

## Key decisions (design-level)

1. **Instrument the headless path, not the product loop.** The product `analyze` node already persists
   `AnalyzerHypothesis.structured_json` (NULL ⟺ parse failure), so product-loop parse health is already
   queryable from Postgres. The *verdict* runs through `run_reproduction` (no DB), so that path needs
   explicit counters. Adding product-loop instrumentation is out of scope (no consumer this slice).

2. **The verdict is a clean A/B with the analyzer as the only treatment.** In `run_reproduction`,
   `analyzer=False` keeps `hypothesis=None` throughout → `build_prompt(hypothesis=None)` every generation.
   `analyzer=True` keeps `hypothesis=None` for gen 1 (the analyzer first fires *after* gen 1) and conditions
   gen 2 onward. Same seed, same gen-0 seeds, same gen-1 proposals → divergence begins at gen 2 and is
   attributable solely to analyzer conditioning. This is what makes the AUC delta interpretable.

3. **Budget = the cap, plateau = the stop.** `--budget=10000` matches the m02 verdict's `max_oracle_calls`
   so AUCs are comparable; both arms plateau early (patience=5 on top-100 mean) at a few thousand unique
   calls. `top_auc(max_oracle_calls=budget)` extends the final plateau value, correctly rewarding sample
   efficiency. Identical config both sides → fair comparison even with early plateaus.

## Components

### Parse-rate instrumentation — `packages/core/capychem/eval/runner.py`
`ReproResult` gains three fields (all default to the analyzer-off values, so existing callers and
`beat.py` are byte-unchanged):
- `analyzer_calls: int = 0`
- `analyzer_parsed: int = 0`
- `analyzer_parse_rate: float | None = None`

In the `analyzer and mutation_strategy == "llm"` branch of `run_reproduction`, after
`result = run_analyzer_sync(...)`: increment `analyzer_calls`; increment `analyzer_parsed` when
`result.structured is not None`. At return, `analyzer_parse_rate = analyzer_parsed / analyzer_calls`
when `analyzer_calls > 0`, else `None`. The counting happens before `resolve_effective_hypothesis`
(Decision 4).

### Verdict module — `packages/core/capychem/eval/verdict.py` (new, mirrors `beat.py`)
- `AnalyzerVerdict` (frozen dataclass): `task, seed, budget, with_auc, without_auc, diff` (with−without),
  `helps` (with_auc > without_auc), `analyzer_parse_rate, analyzer_calls, analyzer_parsed,
  parse_rate_healthy` (`analyzer_parse_rate is not None and analyzer_parse_rate >= _PARSE_RATE_FLOOR`),
  `with_valid_rate, without_valid_rate, with_unique_calls, without_unique_calls`.
- `run_analyzer_verdict(task, budget, seed, *, pop_size=120, offspring=70, mutation_rate=0.067)
  -> AnalyzerVerdict`: runs `run_reproduction(mutation_strategy="llm", analyzer=True)` and
  `(…, analyzer=False)` same-seed, measures both via `top_auc(top_n=10, max_oracle_calls=budget)`,
  assembles the verdict.
- `_PARSE_RATE_FLOOR = 0.8` (module constant, Decision 3).

### CLI — `packages/core/capychem/eval/cli.py`
- New `--analyzer-verdict` flag (store_true), a sibling branch to `--head-to-head`. When set: import +
  call `run_analyzer_verdict`, dump a JSON report with all verdict fields plus `wall_seconds` and a
  `verdict` string interpreting the three-way outcome:
  - `parse_rate_healthy == False` → `"INVALID — parse-rate <0.8; raise analyzer max_tokens and rerun"`.
  - healthy & `helps` → `"analyzer ADDS value (diff > 0)"`.
  - healthy & not `helps` → `"analyzer NULL (diff <= 0) — pivot to analyzer-only narrative, do not abandon"`.
- Backends remain env-selected; the CLI never sets a backend.

### `analyzer.py` (conditional, frozen-engine knob)
`_ANALYZER_MAX_OUTPUT_TOKENS` is raised **only if** the parse smoke (Step A) shows the JSON truncated.
No other analyzer change. `proposer.py` / `test_proposer.py` stay untouched.

## Experiment protocol (the deliverable — recorded in the slice doc, run on `direct`)

- **Step A — parse smoke (~$0.01–0.05).** One `direct` analyzer call on a realistic jnk3 generation
  summary (built via `build_analyzer_summary` + `build_analyzer_prompt` from a small real/synthetic
  population). Confirm `parse_hypothesis` lifts `{focus, avoid}` and inspect `tokens_out` against the 2048
  cap. Truncated → bump `_ANALYZER_MAX_OUTPUT_TOKENS`, re-smoke.
- **Step B — verdict (~$1.2–2.0).**
  `CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct DEEPSEEK_API_KEY=… \
   uv run capychem-eval --task=jnk3 --budget=10000 --seed=42 --analyzer-verdict`.
  Verify the balance covers the run before starting (a $0 balance mid-run degrades the LLM arm to GA).
  Record with/without AUC, diff, parse-rate, calls.
- **Step C — interpret** (the three-way outcome above). Record the verdict + the kill-switch decision in
  the slice doc and the handoff.

## Error handling / honesty

- **Parse-rate < 0.8** → verdict explicitly INVALID; never reported as a null. Bump `max_tokens`, rerun.
- **Mid-run balance exhaustion** → `direct` degrades 402 to GA fallback (FR-005). Mitigation: confirm
  balance before Step B; a degraded run shows up as a depressed with/without `valid_rate` in the report.
- **Provider sampling** → one seed-42 data point, documented as such (Decision 6); not a robustness claim.
- **Transient analyzer blip** → `_direct_analyze` already degrades to `structured=None` → counts as a
  parse failure (conservative; if blips are frequent the rate drops and flags the run, which is correct).

## Observability

The headless path has no Langfuse (no DB, no spans) — by design (`run_reproduction` docstring). The
verdict's observability is the JSON report (parse-rate, valid-rates, AUCs, unique calls) + the slice-doc
record. Product-loop analyzer spans already exist from slice 01.

## Testing (TDD — stub/monkeypatched, free, deterministic, harness-free)

- **`test_eval_runner.py`:** with `analyzer=True` on stub, `analyzer_parse_rate == 1.0` and
  `analyzer_calls == analyzer_parsed ==` the gen-≥2 count; with `analyzer=False`, the three fields are at
  defaults (`parse_rate is None`); a monkeypatched `run_analyzer_sync` returning a `structured=None` result
  drops `analyzer_parse_rate` below 1.0 (proves the counter tracks *failures* — the load-bearing path).
- **`test_eval_verdict.py` (new):** `run_analyzer_verdict` shape + same-seed determinism on stub; both
  AUCs computed; `diff`/`helps` internally consistent; `parse_rate_healthy` boundary at 0.8 (e.g. a
  monkeypatched runner returning parse_rate 0.79 vs 0.80). Mirrors `test_eval_beat.py::_stub` (monkeypatch
  `score_smiles`, `propose_llm_sync`, `run_analyzer_sync`, `starting_population` on `runner_mod`).
- **`test_eval_cli.py`:** `--analyzer-verdict` emits the report keys (`analyzer_parse_rate`,
  `parse_rate_healthy`, `diff`, `helps`, `verdict`).
- **Regression:** `--head-to-head` and default reproduction paths unchanged; `analyzer=False` default
  leaves the `beat.py` numbers byte-identical (new `ReproResult` fields default to off-values).

Quality gate before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
`uv run ruff check .`.

## Out of scope (deferred, explicit)

Product-loop parse-rate instrumentation (DB `structured_json` NULL already records it) · live WS
`analyzer.hypothesis` surface (slice 03) · 23-task registry + baselines + UI selector + `--all` sweep
(slice 04) · Week-8 23-task with-analyzer-vs-Graph-GA sweep (slice 05) · multi-seed robustness (Decision 6)
· Modal `llm.analyze` worker · Alembic.
