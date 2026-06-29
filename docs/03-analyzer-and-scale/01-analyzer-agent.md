# Slice 01 — analyzer-agent

> Milestone 03 `analyzer-and-scale`, slice 01 (build order `01 → {02 ∥ 03 ∥ 04} → 05`; deps: none).
> Design: `docs/superpowers/specs/2026-06-28-analyzer-agent-design.md` · Plan: `docs/superpowers/plans/2026-06-28-analyzer-agent.md`.

## Goal

Ship the analyzer agent — the closed-loop step MOLLEO lacks. After every generation ≥1 of an **LLM** run,
form a `{focus, avoid}` hypothesis from that generation's results and condition the next proposal on it,
in **both** the product loop and the headless eval path (G6 parity). Engine only — not the live surface
(slice 03), the value verdict (slice 02), or the 23-task scale (slice 04).

## Plan

**New files:** `packages/core/capychem/analyzer.py` (DeepSeek adapter, reasoning ON, stub+direct; reuses
proposer's transport via import — option B); `tests/test_analyzer.py`, `tests/test_loop_analyze.py`,
`tests/test_models_analyzer.py`.

**Touched files:** `loop/state.py` (`Hypothesis`, `AnalyzerSummary`, 2 LoopState keys) · `loop/logic.py`
(`build_analyzer_summary`) · `loop/strategy.py` (`build_analyzer_prompt`, `run_analyzer_async/sync`,
`build_prompt(hypothesis=…)` + `propose_llm_async/sync(hypothesis=…)`) · `loop/graph.py` (`analyze` node
after `persist`, gen ≥1 & llm-only; persist returns `gen_db_id`; propose reads the hypothesis) ·
`db/models.py` (`AnalyzerHypothesis` + `Generation.analyzer_hypothesis_id`) + `db/session.py` (docstring) ·
`eval/runner.py` (`run_reproduction(analyzer=…)`) · `apps/api/.../runner.py` (recursion comment) · 8 test
fakes gain `hypothesis=None`.

**Integration points:** loop becomes `propose→validate→fallback→score→persist→analyze→stop_check`;
analyzer cost flows into `state["llm_cost_usd"]` (existing cost gate, unchanged); `proposer.py` +
`test_proposer.py` untouched.

**Testing:** TDD per task. `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
`uv run ruff check .`. Dev/tests use the **stub** analyzer backend (free, deterministic); **direct** only
for real verdicts (slices 02/05). Recreate the dev/CI **Postgres** for the new column (`create_all` won't
ALTER it).

## Tasks

- [x] T1 — `Hypothesis`/`AnalyzerSummary` types + `build_analyzer_summary` (pure). — `015e7d1`
- [x] T2 — `analyzer.py`: stub backend + `parse_hypothesis` matrix. — `b543812`
- [x] T3 — `analyzer.py`: direct DeepSeek backend (reasoning ON, cost, transient degrade). — `7a0723b`
- [x] T4 — strategy seam: analyzer prompt + `run_analyzer_*` + `build_prompt`/`propose_llm_*` conditioning + 8 fake updates. — `8dcb32d`
- [x] T5 — `AnalyzerHypothesis` schema + `Generation` link (create_all; recreate dev/CI DB). — `75cfa76`
- [x] T6 — `analyze` node wired into the product loop (persist→analyze→stop_check; persist `gen_db_id`). — `4aa4b2e`
- [x] T7 — headless parity: `run_reproduction(analyzer=…)`, default off unchanged. — `2a84d46`

> **Shipped 2026-06-28** (commits `015e7d1..2a84d46`, 7 TDD tasks via subagent-driven-development; full
> suite 179 passed, mypy + ruff clean; final whole-branch review: ready to merge). FROZEN — see handoff.
> One approved deviation: the effective-hypothesis resolution was extracted into
> `strategy.resolve_effective_hypothesis`, called by both the `analyze` node and the headless runner (DRY + G6).

## Notes

- **Reasoning ON** for the analyzer (exit-criterion #4, made consciously): omit `thinking:disabled`,
  `max_tokens≈2048`, read post-reasoning `content`. The proposer stays reasoning-OFF —
  [[project_deepseek_v4_reasoning_default]].
- **Module placement B** (not the spec's original A): the proposer's transport is a tested monkeypatch
  seam; extracting it would churn 4 proposer tests for no gain. Analyzer reuses it via same-package import.
- **Known minor (documented, deferred):** the API runner records `RunCost` on persist (curve-growth)
  yields, so an analyzer call's cost lands one generation late and the final gen's analyzer cost (sub-cent)
  isn't re-persisted. Gate still fires within one generation. Out of scope to fix here.
- **G6 parity fixes from review:** headless analyzer seed = `seed + generations - 1` (matches the node's
  `seed + gen_index`); `score_history` = top-10 mean of the **survivor pool** in both paths.
- **DeepSeek balance ≈ $2.37** — keep verdict spend tiny; dev/tests on stub.
