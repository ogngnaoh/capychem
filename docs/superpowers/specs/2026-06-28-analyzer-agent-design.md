# Design — Analyzer agent (milestone-03 slice 01)

**Status:** Approved
**Date:** 2026-06-28
**Milestone:** 03 `analyzer-and-scale` (SPEC Phase 3 — the differentiator)
**Slice:** `01-analyzer-agent` (build order: `01 → {02 ∥ 03 ∥ 04} → 05`; deps: none)
**Consumes:** milestone-02 `proposer.py` (DeepSeek transport), `loop/strategy.py` (shared seam),
`loop/graph.py` (the loop), `eval/runner.py` (headless parity path) — all FROZEN at milestone-02 close.
**Consumed by:** slice 02 (with/without value verdict), slice 03 (live WS surface), slice 05 (sweep + cost gate at scale).

## Context & goal

This slice ships the **analyzer agent** — the closed-loop step MOLLEO lacks and the milestone's
differentiator (SPEC §6.4b). After every generation ≥1, the analyzer reads that generation's results,
forms a hypothesis about what is improving the score, and **conditions the next proposal on it**. It
must reach **both** the `apps/api` product loop (`loop/graph.py`) and the headless eval runner
(`eval/runner.py`) so the slice-02 with/without verdict is apples-to-apples (G6 parity), mirroring the
milestone-02 proposer abstraction.

Scope is the analyzer **engine** end-to-end: the `AnalyzerHypothesis` schema, the analyzer LLM adapter,
the `analyze` node + prompt conditioning, the malformed-output fallback, and dual-path reachability.
It is **not** the live WS surface (slice 03), the value verdict (slice 02), or the 23-task scale (slice 04).

Four decisions confirmed at brainstorm:
- **Reasoning ON.** The analyzer's DeepSeek call runs with chain-of-thought enabled (the proposer forces
  it OFF for short SMILES; the analyzer is a separate analysis call where reasoning is the point). Generous
  `max_tokens` (~2048); reads post-reasoning `message.content`. This is exit-criterion #4's conscious decision.
- **Keep `create_all`, recreate dev DB.** Adding `AnalyzerHypothesis` (new table) + `Generation.analyzer_hypothesis_id`
  (new column) is the first additive schema change. `create_all` makes the new table on fresh DBs; the new
  column won't auto-apply to an already-persisted `generations` table, so dev DBs are dropped+recreated.
  Alembic deferred until a real DB is worth migrating.
- **Hypothesis = `{focus: str, avoid: list[str]}` + prose.** Minimal, MOLLEO-gap-shaped, matches SPEC §6.4b.
- **stub + direct backends; Modal `llm.analyze` deferred.** stub (deterministic, free — CI/dev/reproducible
  verdict runs) + direct (real DeepSeek for verdicts). Mirrors the proposer's already-unexercised-in-dev Modal path.

## Key decisions

1. **One new node, gated, mirroring `fallback`.** The loop becomes
   `propose → validate → fallback → score → persist → analyze → stop_check`. The `analyze` node
   early-returns `{}` unless `mutation_strategy == "llm" and gen_index >= 1` — exactly the no-op pattern
   `fallback` already uses for non-llm strategies. This keeps the **graph_ga control analyzer-free**
   (essential for a clean head-to-head) and skips gen 0 (the seed population, `_proposer="starting"`, no
   proposal strategy to analyze yet). The hypothesis formed after gen N conditions gen N+1.
   - *Rejected — a conditional edge `persist → (analyze | stop_check)`:* the in-node no-op is simpler,
     needs no extra graph wiring, and matches the established `fallback`/`validate` no-op idiom.
   - *Rejected — analyze after gen 0:* SPEC §6.4a ("if not at gen 0"); gen 0 is seeds, gen 1 is the first
     real proposal (run with `hypothesis=None`), gen 2 is the first conditioned proposal.

2. **No operator-facing analyzer toggle.** The product `llm` loop **always** analyzes — it *is* the
   closed-loop-with-analyzer differentiator; there is no product reason to run llm-without-analyzer in the
   UI. The on/off axis is a headless-eval concern: `run_reproduction(..., analyzer: bool = False)`. So
   `RunConfig` / `CreateRunRequest` / the launch UI are **untouched** this slice. Slice 02 flips the headless
   flag for the control arm.

3. **Module placement B — new `analyzer.py` that reuses `proposer.py`'s DeepSeek transport via
   same-package import.** `analyzer.py` imports `_deepseek_chat`, `_deepseek_api_key`,
   `ProposerError`/`TransientProposerError`, and the public `llm_model` / rate helpers from `proposer.py`,
   builds its **own** payload (reasoning ON, generous `max_tokens`) + content/usage extraction + parse.
   `proposer.py` is treated as the DeepSeek-client home; the analyzer is a second consumer of its transport.
   - **Why B over A (extract a shared `_deepseek.py`):** discovered during planning that the proposer's
     transport is a **tested monkeypatch seam** — `test_proposer.py` patches `proposer._post_deepseek` /
     `proposer._deepseek_chat` and the internal call chain (`_one_proposal_row → _deepseek_chat →
     _post_deepseek`) resolves those names *in proposer's namespace*. Extracting the transport would break
     those seams and churn ~4 tests on the funded, working proposer for no behavioral gain. B touches
     `proposer.py` and its tests **zero** (lowest regression risk) and gives the analyzer its own clean seam
     (`analyzer._deepseek_chat`). The "reach into `_`-prefixed names" cost is soft (same `capychem` package).
   - *Rejected — A (extract `_deepseek.py`):* breaks proposer's tested monkeypatch seams, churns the funded
     proposer for no behavioral gain (re-decided once the seam coupling was found).
   - *Rejected — C (`analyze_*` inside `proposer.py`):* co-locates two prompts/payloads in an already
     ~300-line file doing two jobs; honors neither separation nor the "change one prompt, sanity-check the
     other" gotcha as well as a separate module.

4. **A shared analyzer seam for the G6-sensitive pieces**, mirroring milestone-02's proposer split.
   `loop/logic.py::build_analyzer_summary` (pure) + `loop/strategy.py::build_analyzer_prompt` +
   `run_analyzer_async`/`run_analyzer_sync` are imported by **both** the product node and the headless
   runner, so the same survivor pool + same prior hypothesis + same seed reproduce a byte-identical
   analyzer input and call. Determinism is best-effort under reasoning (LLM variance), exact under the
   stub backend used for tests + reproducible runs; the G6 ±1% tolerance absorbs the rest.

5. **Analyzer cost flows into the existing cost gate.** The `analyze` node adds its call cost to
   `state["llm_cost_usd"]` (the same field the propose node feeds), so the milestone-02 hard
   `cost.cost_cap_usd()` gate fires on **combined proposer + analyzer** LLM spend with zero change to
   `cost.py` or the API runner's gate logic. Per-hypothesis cost is *also* recorded on
   `AnalyzerHypothesis.compute_cost_usd` (SPEC §6.2 accounting).

6. **Fallback returns an effective hypothesis; the loop never stalls (FR-007, edge case 3).** A
   malformed / empty / off-topic analyzer output yields `structured=None` + `note="no new signal"`. The
   node then resolves the *effective* hypothesis = last-good (from state) or, if none, a **neutral**
   hypothesis (`structured=None`). The persisted row carries the effective text + note (history shows the
   fallback happened); the next propose with a neutral hypothesis takes `build_prompt`'s existing
   `hypothesis=None` path — the proven gen-1 behavior.

## Components

### DeepSeek transport — reused from `packages/core/capychem/proposer.py` (UNCHANGED)
`analyzer.py` imports `_deepseek_chat`, `_deepseek_api_key`, `ProposerError`, `TransientProposerError`, and
the public `llm_model` / `llm_usd_per_1k_in` / `llm_usd_per_1k_out` from `proposer.py`. `proposer.py` and
`test_proposer.py` are **not modified** (Key decision 3). `_deepseek_chat` does the POST + status mapping +
JSON parse; the analyzer does its own content/usage extraction + cost (a separate payload shape).

### Pure data types — `packages/core/capychem/loop/state.py`
- `Hypothesis` (frozen): `structured: dict | None` (`{focus, avoid}`), `text: str`, `note: str | None` —
  threaded through `LoopState` (lives next to `Scored`, so `logic.py`/`strategy.py` reference it without
  importing the adapter module).
- `AnalyzerSummary` (frozen): top-k + bottom-k survivors, recent deltas, prior hypothesis (the analyzer's input).

### Analyzer adapter — `packages/core/capychem/analyzer.py` (new, mirrors `proposer.py`)
- `AnalyzerResult` (frozen): `text`, `structured`, `tokens_in`, `tokens_out`, `cost_usd`, `note` — the
  adapter's raw output (the node converts it into an effective `Hypothesis`).
- `analyze_async(prompt, *, seed) -> AnalyzerResult` — backend-dispatched (`CAPYCHEM_ANALYZER_BACKEND`,
  default `stub`):
  - `stub`: deterministic structured hypothesis from a fixed pool keyed by (seed, prompt); cost 0.
  - `direct`: one DeepSeek chat request, **reasoning ON** (omit `thinking:disabled`),
    `max_tokens = _ANALYZER_MAX_OUTPUT_TOKENS` (~2048), pinned `_ANALYZER_TEMPERATURE`, `seed`; reads
    post-reasoning `content`; transient errors degrade to an empty result → `structured=None` (fallback).
  - `modal`: deferred — raises a clear "not implemented this slice" error if selected.
- `analyze_sync(prompt, *, seed)` — `asyncio.run` bridge for the headless path.
- `parse_hypothesis(text) -> dict | None` — extract the last `{…}` JSON block; require `focus: str` +
  `avoid: list[str]`; return `None` on any failure (empty / non-JSON / missing keys / wrong types).
- Cost via the proposer rate helpers (`proposer.llm_usd_per_1k_in/out`, `proposer.llm_model`).

### Summary builder — `packages/core/capychem/loop/logic.py`
- `build_analyzer_summary(population, score_history, prior) -> AnalyzerSummary` (pure, deterministic):
  top-k + bottom-k survivors (smiles, score), recent top-10-mean deltas (the last 3 `score_history`
  points), prior hypothesis (structured + prose). Returns the `AnalyzerSummary` defined in `state.py`.
  Built identically in both paths → byte-identical analyzer input (G6).

### Shared seam — `packages/core/capychem/loop/strategy.py`
- `build_analyzer_prompt(summary) -> str` — templates the summary; asks for prose + a JSON `{focus, avoid}` block.
- `run_analyzer_async(summary, *, seed)` / `run_analyzer_sync(...)` — `analyze_*(build_analyzer_prompt(summary), seed=…)`.
- `build_prompt(task, population, n, hypothesis: Hypothesis | None = None)` — **extended**: when
  `hypothesis` and `hypothesis.structured`, append a "Guidance from last-generation analysis: focus on
  {focus}; avoid {avoid}. {prose}" block; **unchanged when `None`** (gen-1 path). Threaded via
  `propose_llm_async/sync(..., hypothesis=…)`.

### Loop node — `packages/core/capychem/loop/graph.py`
- **`persist`** (small change): return `gen_db_id = gen.id` in state so `analyze` can link the row.
- **`analyze`** (new node, edge `persist → analyze → stop_check`): no-op `{}` unless
  `mutation_strategy=="llm" and gen_index>=1`. When active:
  - `node:analyze` span (nested `llm:analyze` with model / tokens / cost / reasoning-preview).
  - summary from `state["population"]` + `auc_curve` (deltas) + `state.get("analyzer_hypothesis")` (prior);
    `seed = state["seed"] + state["gen_index"]`.
  - `run_analyzer_async` → `AnalyzerResult`; resolve effective hypothesis (new, else last-good, else neutral).
  - persist `AnalyzerHypothesis(run_id, after_generation_index=gen_index, text, structured_json, tokens_in,
    tokens_out, compute_cost_usd)`; link `Generation.analyzer_hypothesis_id` (by `gen_db_id`).
  - return `analyzer_hypothesis` (→ next propose) + `llm_cost_usd += cost_usd`.

### State + headless parity
- `LoopState` += `analyzer_hypothesis: Hypothesis | None`, `gen_db_id: int`.
- `propose` reads `state.get("analyzer_hypothesis")` → `propose_llm_async(..., hypothesis=…)`.
- `eval/runner.py::run_reproduction(..., analyzer: bool = False)`: default `False` leaves `eval/beat.py`'s
  existing graph_ga-vs-llm numbers unchanged (slice 02 opts in). When `True` + llm strategy: thread
  `hypothesis` into `propose_llm_sync`, then `run_analyzer_sync` after each gen with the same
  summary/prompt/parse/fallback as the node. No DB; threads the hypothesis dict forward like `population`.
  Maintains a small `score_history` list for the summary's deltas.

### DB — `packages/core/capychem/db/models.py` (create_all path)
- New `AnalyzerHypothesis`: `id`, `run_id` (FK runs, CASCADE), `after_generation_index`, `text` (Text),
  `structured_json` (JSON, nullable), `tokens_in`, `tokens_out`, `compute_cost_usd` (default 0.0); index
  `(run_id, after_generation_index)`.
- `Generation.analyzer_hypothesis_id: Mapped[int | None]` (FK analyzer_hypotheses, SET NULL, nullable —
  null on gen 0 / graph_ga). One-way FK (`Generation → AnalyzerHypothesis`); no cycle (the hypothesis
  references `runs`, not `generations`).
- Docstring: table is here now; create_all bootstraps; **recreate dev DB for the new column**; Alembic deferred.

## Data flow (one `llm` run)

```
gen 0  propose=starting → validate → fallback → score → persist → analyze SKIP (gen 0) → stop_check
gen 1  propose=llm(hyp=None) → … → persist → analyze → H′₁ (persist row + link Generation₁) → stop_check
gen 2  propose=llm(hyp=H′₁) → … → persist → analyze → H′₂ → stop_check
…
```

`H′ₙ` is the *effective* hypothesis: the parsed analyzer output, or (on malformed) the last-good / neutral
fallback. `analyze` for gen N feeds `state["analyzer_hypothesis"]`, which gen N+1's `propose` reads.

## Error handling

- **Malformed / empty / off-topic analyzer output** → `parse_hypothesis` returns `None` →
  `structured=None`, `note="no new signal"` → effective = last-good (or neutral); loop continues (FR-007,
  edge case 3). Persisted row records the fallback.
- **Transient DeepSeek error** (`direct` backend) → degrade to empty result → `structured=None` → same
  fallback (mirrors the proposer's transient-degrade discipline; never crashes a long run).
- **Analyzer config error** (bad model/auth, non-degradable 4xx) → `ProposerError` propagates; the product
  runner's existing try/except marks the run `errored` and ends spans cleanly.
- **Neutral first hypothesis** (gen 1 malformed, no prior) → `hypothesis=None`'s proven path; gen 2 proposes
  exactly as today.

## Observability

`analyze` opens `node:analyze` under the generation span; the LLM call nests `llm:analyze`
(`metadata={model, seed, max_tokens, tokens_in, tokens_out, cost_usd, reasoning_preview}`). No silent loop
step (CLAUDE.md). Analyzer cost surfaces in the span metadata **and** `RunCost.total_usd` (via `llm_cost_usd`).

## Testing (TDD)

- **proposer untouched:** `proposer.py` + `test_proposer.py` unchanged (Key decision 3); the analyzer reuses
  the transport via import, so the existing proposer suite is the regression guard for the transport itself.
- **`analyzer.py`:** stub determinism; `direct` payload (reasoning ON, big `max_tokens`, reads `content`) via
  monkeypatched transport; `parse_hypothesis` matrix (valid / empty / non-JSON / missing-keys / wrong-types /
  off-topic); cost maths; transient-error degrade.
- **`build_analyzer_summary`:** top-k/bottom-k/deltas/prior shape; determinism.
- **strategy:** `build_analyzer_prompt` includes the summary; `build_prompt(hypothesis=…)` appends guidance;
  `build_prompt(hypothesis=None)` byte-identical to today (gen-1 regression).
- **`analyze` node:** runs for llm gen≥1; skips gen 0 and graph_ga; persists `AnalyzerHypothesis` + links
  `Generation.analyzer_hypothesis_id`; threads hypothesis to next propose; malformed→fallback continues;
  analyzer cost added to `llm_cost_usd` (gate sees it).
- **headless:** `run_reproduction(analyzer=True, mutation_strategy="llm")` runs to budget on stub, threads
  the hypothesis; `analyzer=False` (default) leaves the beat.py path byte-unchanged (regression).
- **regression:** existing graph_ga product + eval paths unchanged (analyze no-op).

Quality gate before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
`uv run ruff check .`.

## Out of scope (deferred, explicit)

With/without value verdict on jnk3 (slice 02) · WS `analyzer.hypothesis` event + watch-live latest +
run-detail hypothesis sequence (slice 03) · 23-task registry + baselines + UI selector + `--all` sweep
(slice 04) · Week-8 sweep + cost gate at scale (slice 05) · Modal `llm.analyze` worker (deploy-time) ·
Alembic (until a persisted DB needs it) · operator-facing analyzer toggle (no product need) · multi-objective.
