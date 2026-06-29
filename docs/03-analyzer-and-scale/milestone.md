# Milestone 03 — analyzer-and-scale

> SPEC Phase 3 — the differentiator. Single source of truth for this milestone. Synthesized 2026-06-28
> at milestone kickoff (milestone 02 complete). Per-slice docs (`NN-<slice>.md`) are written when that
> slice's work starts; this file stays high-level.

## Goal

Ship the **analyzer agent** — the closed-loop step MOLLEO lacks — so the loop forms a per-generation
hypothesis from each generation's results and conditions the next proposal on it (SPEC §6.4b); then
prove it across the full **23-task PMO surface** and clear the **Week-8 bar** (beat vanilla Graph-GA on
**≥3/23** by AUC-of-top-10 → on track; <3 → pivot to analyzer-only narrative, do not abandon).

## Scope

- **`AnalyzerHypothesis` entity + the first additive schema migration** (models.py docstring already
  reserves it; "Alembic lands with the first additive change"). Fields per SPEC §6.2; add
  `Generation.analyzer_hypothesis_id` (nullable on gen 0).
- **`analyze` LangGraph step** (gen ≥1) forming a hypothesis from top-k / bottom-k + recent score deltas
  + the prior hypothesis (SPEC §6.4b); Langfuse-spanned (no silent loop steps); persisted.
- **Both-paths parity (G6):** the analyzer reaches the `apps/api` product loop AND the headless
  `eval/runner.py` — mirroring the milestone-02 proposer abstraction (shared in `loop/strategy.py`) — so
  the with/without comparison is apples-to-apples.
- **Analyzer LLM adapter** on the SAME DeepSeek-v4-pro model with a **conscious reasoning-mode decision**
  (proposer forces `thinking:disabled` + a 128-token cap; the analyzer is a *separate* call needing a
  larger output budget and its own on/off choice — [[project_deepseek_v4_reasoning_default]]).
- **Next-generation prompt conditioning:** `strategy.build_prompt` threads the structured hypothesis
  (focus/avoid) + prose; the no-hypothesis path (gen 1) keeps working.
- **Analyzer-output fallback:** malformed/empty/off-topic → last-good or neutral hypothesis with a "no
  new signal" note; the loop never stalls (FR-007, edge case 3).
- **Hypothesis surface:** WS `analyzer.hypothesis` event (FR-009); watch-live "latest analyzer
  hypothesis" (Story 2); run-detail full per-generation hypothesis sequence (Story 3, FR-011).
- **Full 23-task PMO surface:** canonical task registry + published Graph-GA baselines (extend
  `eval/baselines.py` from agent_docs/pmo-auc-and-baselines.md); widen the launch schema/UI selector from
  {qed, jnk3} to all 23 (FR-001, G3); an all-23 sweep runner (`capychem-eval --all`).
- **Cost gate at sweep scale:** analyzer LLM spend flows into the existing `RunCost.total_usd`; the
  milestone-02 hard `cost.cost_cap_usd()` gate fires on the combined total; consider SPEC §8.3's
  1.5×-budget projection refinement.
- **Two head-to-head verdicts:** (a) with-analyzer vs the milestone-02 without-analyzer LLM control on a
  single task (the differentiator kill-switch); (b) the 23-task Week-8 bar (with-analyzer LLM vs
  Graph-GA, ≥3/23 beat).

## Non-goals

1. **Compare-runs view** (Story 4, FR-012) — milestone 04.
2. **Multi-objective / Pareto optimization** — PMO single-objective only.
3. **Expensive oracles (ADMET-AI / Vina / DiffDock)** — stretch; backend architected, not exercised.
4. **Multi-agent planner/executor/critic split** — the single-LLM proposer+analyzer carries the
   narrative (SPEC Alt C, deferred).
5. **Beating SOTA** (Genetic GFN 16.213) or matching MOLLEO's 9/12 — the honest bar is beat vanilla
   Graph-GA on ≥3/23 (Week-8); ≥6/23 is the G1 target (milestone 04 / 2026-09-15).
6. **Memory/RAG over past successful mutations** (the ExLLM angle) — stretch.

## Slices

Build order: `01 → {02 ∥ 03 ∥ 04} → 06 → 05`. Slice **06** was inserted after slice 02's clean NULL as
the analyzer-iteration response to the kill-switch — it precedes the slice-05 sweep (which would also null
on an unimproved analyzer). Each is an independently shippable vertical slice; per-slice docs are written
when that slice's work starts.

01. `analyzer-agent` — `AnalyzerHypothesis` entity + first migration; `analyze` node (gen ≥1) forming a
    hypothesis + conditioning the next proposer prompt; analyzer LLM adapter (reasoning decision);
    malformed-output fallback; reaches product loop + headless eval. — shipped (2026-06-28) — deps: none
02. `analyzer-value-verdict` — extend the head-to-head to a with/without-analyzer axis; prove the
    analyzer adds AUC value on ≥1 task (jnk3) — the differentiator kill-switch (SPEC risk "analyzer may
    not help"). **Required before the verdict is trustworthy:** this slice runs the first real `direct`
    analyzer calls, so it MUST instrument the analyzer `parse_hypothesis` success rate — reasoning-ON CoT
    can crowd out the `{focus, avoid}` JSON past `max_tokens≈2048`, which degrades to "no new signal" every
    generation and would fake a "no value" verdict that no test catches (see Integration notes,
    reasoning-budget risk). A null result is only valid once parse-success is confirmed healthy. —
    **shipped (2026-06-28)** — verdict: trustworthy **clean NULL** (parse-rate 1.0; analyzer does NOT add
    value on jnk3 @ seed 42, with 0.678 < without 0.743). The reasoning-budget risk materialized and was
    fixed by reversing the analyzer to reasoning-OFF (exit-criterion #4 reversed). Kill-switch → pivot
    signal; strategic response in handoff.
    — deps: 01
03. `analyzer-live-surface` — WS `analyzer.hypothesis` event + watch-live latest hypothesis + run-detail
    full hypothesis sequence (FR-009/FR-011, Story 2/3). — planned — deps: 01
04. `twenty-three-task-surface` — full PMO task registry + published Graph-GA baselines + launch
    schema/UI selector for all 23 + all-23 sweep runner (`capychem-eval --all`). — **shipped (2026-06-29)**
    — verdict: pure plumbing, all gates green (207 pytest, mypy, ruff; web vitest+tsc+eslint), final
    whole-branch review READY-TO-MERGE (0 Critical/Important). `eval/tasks.py::PMO_TASKS` is the single
    source of truth; `--all` is mode-pluggable (reproduce|head_to_head|analyzer_verdict). NOTE: the 23
    verbatim Table-2 values sum to **13.742** (paper's reported Sum row is 13.751 — display-rounding gap),
    so the sweep's computed `published_sum` is 13.742. NO eval cost incurred. — deps: none
06. `analyzer-conditioning` — redesign how the analyzer hypothesis conditions the proposer (the slice-02
    null was value-negative). Evidence-first: capture real hypotheses (`trace_sink` + `--capture-analyzer-traces`)
    → diagnose (Application: accurate hypotheses, over-constraining `avoid` + whole-batch directive) → fix
    (Approach 3A: soften focus to optional inspiration, DROP `avoid`, condition ~half the batch) → re-verify.
    — **shipped (2026-06-29)** — verdict: **WIN** on jnk3 @ seed 42 (with 0.764 > without 0.674, **+0.090**,
    flips slice-02's −0.066; parse 1.0, valid-rates 0.99/0.99). Single-seed/non-deterministic-backend caveat
    noted. — deps: 01, 02
05. `week-8-sweep-and-gate` — run the 23-task with-analyzer-LLM vs Graph-GA sweep; validate the cost gate
    at scale; render the ≥3/23 Week-8 verdict + kill-switch decision. — planned — deps: 01 ✓, 04 ✓, 06 ✓
    (ALL deps now shipped → unblocked; run via `capychem-eval --all --analyzer-verdict`. Needs a DeepSeek
    balance top-up first — a 23-task dual-arm LLM sweep far exceeds the ≈$1.38 balance.)

## Integration notes

- **Analyzer node placement.** Loop today: `propose → validate → fallback → score → persist →
  stop_check`. `persist` already computes survivors + top10. Insert `analyze` after `persist`, before
  `stop_check`; store the hypothesis in `LoopState`; the next `propose` reads it via `build_prompt`.
  Skip on gen 0; first hypothesis after gen ≥1 (SPEC §6.4a "if not at gen 0"). Nest its Langfuse span
  under the generation span.
- **Both-paths parity (G6).** `eval/runner.py::run_reproduction` has no analyze step today; add a sync
  analyzer bridge in `loop/strategy.py` (like `propose_llm_sync`) so the headless with/without verdict is
  byte-identical to the product loop.
- **Entity + first migration.** SPEC §6.2 fields: `id, run_id, after_generation_index, text,
  structured_json, tokens_in, tokens_out, compute_cost_usd`. models.py is bootstrapped via
  `metadata.create_all`; adding this table is the first additive change — decide create_all vs Alembic in
  slice 01.
- **Prompt conditioning.** `strategy.build_prompt(task, population, n)` has no hypothesis param yet
  (docstring: "no analyzer hypothesis yet — that arrives in milestone 03"). Slice 01 adds an optional
  hypothesis arg threaded from state.
- **Analyzer adapter / reasoning.** Same model via `proposer.llm_model()`. The `direct` proposer forces
  `thinking:{type:disabled}` + `_MAX_OUTPUT_TOKENS=128`; the analyzer is a separate call — do NOT copy
  the proposer payload. Cost → `RunCost.llm_cost_usd` (already summed into `total_usd`) +
  `AnalyzerHypothesis.compute_cost_usd`.
- **Reasoning-budget risk — RESOLVED in slice 02 (the risk materialized).** The analyzer ran reasoning
  ON with `max_tokens≈2048`; the first real `direct` verdict scored parse-rate **0/3** — v4's CoT runs
  2.5–3.9k tokens (variable), overran the cap, and left `content` empty → `parse_hypothesis` None every
  gen. The slice-02 parse-rate instrumentation caught it (no test could). **Fix:** analyzer reversed to
  reasoning-OFF (`thinking:{type:disabled}`, `max_tokens 2048→1024`), mirroring the proposer — parse-rate
  then 1.0. This **reverses slice-01 exit-criterion #4** (reasoning ON) on evidence; the slice-01 design
  spec's reasoning-ON rationale is superseded. Analyzer reasoning is now OFF for the rest of the milestone.
- **Cost gate already exists.** Milestone-02 slice 05 wired the hard `cost.cost_cap_usd()` gate in
  `apps/api/.../runner.py` (`total_usd` = llm+oracle). Milestone 03 only adds analyzer spend into that
  total and validates the gate holds across the sweep.
- **Task surface.** `CreateRunRequest` allow-lists only {qed, jnk3} (test_task_surface.py). The harness
  oracle is already task-agnostic (`Oracle(name=task)`) — slice 04 widens only the modern-side
  registry/schema/UI + baselines; no harness change.
- **Head-to-head reuse.** `eval/beat.py::run_head_to_head` (graph_ga vs llm) is the template. Slice 02
  adds an analyzer-on/off axis; slice 05 runs with-analyzer-llm vs graph_ga across 23 tasks. Always
  measure with `eval/metric.top_auc` — never ad-hoc AUC.
- **Frontend.** `LiveRun.tsx` gains a latest-hypothesis panel; `runs/[id]/page.tsx` gains the full
  hypothesis sequence. Add `analyzer.hypothesis` to `ws_runs.py` + schemas; broadcast from `runner.py`
  (mirror `GenerationCompleteEvent`).
- **Carried in from milestone 02 (deferred):** manual live-UI plateau-callout check (small
  `plateau_window`, large budget so it converges before exhausting); optional `plateauNotice` double-call
  hoist in `LiveRun.tsx` (Minor, only if touched).

## Exit criteria

1. `analyze` runs after every generation ≥1 in BOTH the product loop and the headless eval path; each
   hypothesis is persisted (`AnalyzerHypothesis`) with `Generation.analyzer_hypothesis_id` linked.
2. The next generation's proposer prompt is demonstrably conditioned on the prior hypothesis.
3. Malformed/empty/off-topic analyzer output falls back to last-good/neutral with a "no new signal" note;
   the loop never stalls (edge case 3).
4. The analyzer reasoning-mode decision is made consciously and documented (not copied from the proposer).
5. With-analyzer beats without-analyzer (the milestone-02 LLM control) on ≥1 task (jnk3) by AUC-of-top-10,
   head-to-head, via the canonical eval module — the analyzer adds value. → **MET on jnk3, replicated across
   2 seeds** (slice 06 Approach 3A: seed 42 with 0.764 > without 0.674 **+0.090**; hardened seed 7 on
   2026-06-29 with 0.773 > without 0.666 **+0.108**; both parse 1.0, valid-rates ≥0.97). Slice 02 first found
   a trustworthy null (−0.066) with the original `{focus,avoid}` directive conditioning; the evidence-first
   slice-06 redesign (soften focus, DROP `avoid`, half-batch) flipped it positive. Cross-seed replication
   (+0.090, +0.108; both exceed the ~0.07 backend day-drift) retires the single-seed-noise caveat; still
   single-task, so the authoritative multi-task bar remains the slice-05 23-task sweep. **Kill-switch did NOT
   need to fire — analyzer-as-value-add stands** (no pivot).
6. All 23 PMO tasks are launchable from the web (multi-task selector) and scored end-to-end; published
   Graph-GA baselines registered. → **MET (slice 04, 2026-06-29):** `eval/tasks.py::PMO_TASKS` registry
   (single source of truth) feeds the API `field_validator`, the launch-page `<select>` (all 23, default
   jnk3), and all 23 published Graph-GA baselines (`eval/baselines.py`). Per-task end-to-end scoring across
   23 is exercised by slice 05's `capychem-eval --all` sweep (the harness oracle is already task-agnostic).
7. The hypothesis is surfaced live (watch-live latest) and in run-detail (full sequence).
8. The 23-task with-analyzer-LLM vs Graph-GA sweep is run via the canonical eval module; the Week-8
   verdict is rendered — ≥3/23 beat → on track; <3 → pivot to analyzer-only narrative (do not abandon).
9. The cost gate fires on combined LLM (proposer + analyzer) + oracle spend; a full run stays under it.
10. Gates green: pytest, mypy strict (both `-p`), ruff; web vitest, tsc, eslint.
