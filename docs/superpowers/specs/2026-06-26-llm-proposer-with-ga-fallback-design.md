# Design — LLM proposer with Graph-GA fallback (milestone-02 slice 04)

**Status:** Approved
**Date:** 2026-06-26
**Milestone:** 02 `end-to-end-loop` (SPEC Phase 2)
**Slice:** `04-llm-proposer-with-ga-fallback` (build order: `01 ∥ 02 ∥ 03 → 04 → 05 → 06`; deps: 03)
**Consumes:** slice 03 `proposer.py::propose_batch_async` (FROZEN)
**Consumed by:** slice 05 (cost ledger + unique-call budget), slice 06 (beat-Graph-GA run)

## Context & goal

Slice 04 wires the slice-03 proposer adapter into the optimization loop behind a **Proposer
abstraction** selected by `Run.mutation_strategy`, with a **deterministic Graph-GA fallback** so a
generation's throughput never drops when the LLM emits invalid SMILES (FR-005). The abstraction must
be reachable from **both** the `apps/api` product loop (`loop/graph.py`) and the headless eval runner
(`packages/core/capychem/eval/runner.py`) so G6 reproducibility holds on the LLM path. This is the
heaviest slice in the milestone: abstraction + dual-reachability + LLM wiring + GA fallback + pinned
determinism + the >80% valid-SMILES gate + LLM-call spans.

Per the slice scope and the two decisions confirmed at brainstorm:
- **Stub-only this slice.** All slice-04 code + tests run against the network-free `stub` proposer
  backend. The real DeepSeek `direct` run that measures the actual jnk3 validity rate + the beat
  verdict are **slice 06**.
- **The gate observes, it does not enforce.** It computes the rate and records a pass/fail verdict;
  it never halts a run (the Graph-GA fallback already guarantees throughput).

## Key decisions

1. **One new node, not a fatter propose node.** The loop becomes
   `propose → validate → fallback → score → persist → stop_check`. The `validate` node stays the
   **sole owner** of the frozen `valid_smiles` stat and only ever sees the proposer's *direct* output
   (`state["proposed"]`). Fallback fillers are produced *after* validate and **never enter
   `proposed`/`_validation_stats`**, so the gate measures the true LLM validity rate with **zero
   change to `validate`'s frozen contract**. Placing fallback after validate also lets it size its
   gap from the already-deduped `state["validated"]` — so the LLM batch is validated exactly once
   (no double-validation).
   - *Rejected — fold fallback into propose:* forces the propose node to validate the LLM batch
     itself to size the gap (double-validation) and makes one node do two jobs.
   - *Rejected — a single `propose_with_fallback` helper driving both paths:* would bypass the
     `validate` node and break its frozen gate-stat ownership.

2. **A shared strategy module for the G6-sensitive pieces.** `packages/core/capychem/loop/strategy.py`
   holds the small pieces that **must be byte-identical** in the product graph and the headless
   runner: the prompt builder, the LLM-call wrapper (+ a sync bridge), and the GA-fill wrapper. Both
   paths import the same functions, so same task + same seed + same model reproduce (G6).

3. **Temperature is a pinned module constant**, not a per-run config field. The milestone requires
   temperature *pinned* (deterministic), not *configurable*; a constant is the minimal surface that
   satisfies G6. Seed is `run_seed + gen_index`, mirroring the existing Graph-GA seed scheme.

4. **Per-candidate provenance via an additive `ValidCandidate.proposer` field.** Mixed batches
   (LLM-valid + GA fillers) need per-candidate origin so "which molecules did the LLM actually find"
   stays answerable and the data model's `Generation.proposer_used ∈ {…,mixed}` + per-`Candidate.proposer`
   hold. A `proposer: str = "graph_ga"` default keeps the eval + existing graph_ga paths correct with
   no ripple; the `validate` node re-tags from `_proposer`; fillers keep the default.

5. **No cost ledger this slice.** Slice 04 records LLM token/cost only in the Langfuse span metadata.
   Populating `RunCost.llm_cost_usd` + rewiring the per-gen cost gate is **slice 05**.

## Components

### Shared strategy module — `packages/core/capychem/loop/strategy.py` (new)
- `build_prompt(task, population, n) -> str` — MOLLEO-style mutation prompt: the task name, the
  current top-K SMILES + scores, and an instruction to output **exactly one** valid SMILES (the
  `direct` backend fans out `n` single-choice requests, and `_clean_smiles` takes the first token, so
  one SMILES per completion). **No analyzer hypothesis** — that conditioning arrives in milestone 03.
- `propose_llm_async(task, population, *, n, seed) -> list[ProposalResult]` — wraps
  `proposer.propose_batch_async(build_prompt(...), n, temperature=LLM_TEMPERATURE, seed=seed)`.
- `propose_llm_sync(...)` — `asyncio.run(...)` bridge for the synchronous headless path. Safe because
  `capychem-eval` is a sync entrypoint with no running event loop.
- `ga_fill(population, n, *, mutation_rate, seed) -> list[tuple[str, tuple[int,int] | None]]` — wraps
  `oracle.propose_offspring`; serves **both** the `graph_ga` strategy and the LLM fallback.
- `LLM_TEMPERATURE = 0.7` (pinned constant).

### Loop nodes — `packages/core/capychem/loop/graph.py`
- **`propose`** (strategy-aware): gen 0 unchanged (seed pop, `_proposer="starting"`, both strategies).
  Gen ≥1: `graph_ga` → `proposed = ga_fill(pop, offspring, …)`, `_proposer="graph_ga"`; `llm` →
  `results = propose_llm_async(…, n=offspring)`, `proposed=[(r.smiles, None) …]`, `_proposer="llm"`,
  wrapped in `trace.span("llm:propose", …)`.
- **`validate`** (small change): unchanged stat computation; additionally tags each `validated`
  candidate with `_proposer` (provenance flows downstream).
- **`fallback`** (new node): acts only when `_proposer=="llm"` and `len(validated) < offspring`.
  Computes `gap = offspring - len(validated)`, `fillers = ga_fill(pop, gap, …, seed=run_seed+gen)`,
  validates+dedups the fillers against `validated` → `_fallback_validated` (tagged `"graph_ga"`), and
  sets `_proposer="mixed"` when any filler lands. **Single GA-fill round** (no per-slot LLM retry —
  YAGNI, matches scope). No-op for `graph_ga` and when the population is empty.
- **`score` / `persist`**: score `validated + _fallback_validated` (one `trim_to_budget` over the
  concat); persist writes `Generation.proposer_used = _proposer` and per-`Candidate.proposer = vc.proposer`.

### State + config threading
- `LoopState` += `mutation_strategy: str` (and `_fallback_validated: list[ValidCandidate]`).
- `ValidCandidate` += `proposer: str = "graph_ga"`.
- `RunConfig` += `mutation_strategy: str = "graph_ga"`; `create_run` uses it (drops the `run.py:33`
  hardcode).
- `CreateRunRequest` += `mutation_strategy: Literal["graph_ga","llm"] = "graph_ga"` (FR-001 at the
  API; default preserves behavior).
- `apps/api runner._drive` + `cli.py` initial `LoopState` dicts set `mutation_strategy`.
- `capychem-run` + `capychem-eval` gain `--mutation-strategy`.
- `run_reproduction(..., mutation_strategy="graph_ga")` drives the LLM proposer + fallback headlessly
  (G6 / done-bar #4), via `propose_llm_sync`.

### The gate — `packages/core/capychem/loop/logic.py`
- `valid_smiles_gate(summary, threshold=0.80) -> {"rate", "passed", "threshold"}` — pure helper.
- Surfaced as a `valid_smiles.gate` sub-field in `summary_json` (via `build_summary`) + a structured
  log line at run completion (`capychem-run` already prints the rate; add pass/fail). **Never halts.**

## Data flow (gen ≥ 1, `llm` strategy)

```
propose:  LLM proposes `offspring` raw strings ─────────────► state["proposed"]  (parents=None)
validate: validate_batch_with_stats(proposed) ──────────────► state["validated"] (tagged "llm")
                                                              + _validation_stats (LLM-ONLY → the gate)
fallback: gap = offspring - len(validated)
          if gap>0: ga_fill → validate+dedup ───────────────► state["_fallback_validated"] (tagged "graph_ga")
                    _proposer = "mixed"
score:    trim_to_budget(validated + _fallback_validated) ──► score via oracle
persist:  Generation.proposer_used = _proposer ("llm"|"mixed")
          Candidate.proposer = vc.proposer (per candidate)
```

The gate's honesty is structural: `_validation_stats` is computed only from `state["proposed"]`,
which for the `llm` strategy is exactly the LLM's raw output — fillers are added later and tagged
separately.

## Error handling

- **Invalid LLM SMILES** → dropped by `validate` (RDKit), backfilled by the `fallback` node so the
  generation still presents ~`offspring` valid candidates (FR-005).
- **All-invalid LLM batch** → `gap == offspring`; fallback fills the whole batch from Graph-GA; the
  run sustains full throughput; the gate records a low rate. (Edge case 1.)
- **Empty population at fallback** → cannot crossover; fallback is a no-op (only reachable at gen 0,
  which never runs the LLM).
- **Proposer backend error** (`ProposerError`) → propagates; the product runner already wraps the
  loop in a try/except that marks the run `errored` and ends spans cleanly.
- **Gate failure (<80%)** → recorded in summary + log; the run completes normally.

## Observability

LLM call wrapped in `trace.span("llm:propose", parent=gen_span, metadata={model, n, temperature,
tokens_in, tokens_out, cost_usd})`. Plain span — the Langfuse v2 helper exposes no `generation`
observation type; a richer typed observation is a later nicety. Cost appears in span metadata only
(ledger is slice 05).

## Testing (TDD)

- **strategy module:** prompt determinism; `propose_llm_sync` bridges the async client; `ga_fill`
  wraps `propose_offspring`; seed scheme.
- **fallback node:** invalid LLM → fillers backfill to `offspring`; all-invalid → full GA batch;
  `graph_ga` → no-op; `"mixed"` labeling; fillers deduped against the LLM-valid set.
- **gate honesty:** `_validation_stats.rate` reflects LLM-only output even when fallback fires.
- **gate helper:** pass (≥0.80) and fail (<0.80) cases; fail still completes the run.
- **threading:** `RunConfig → LoopState → persist` carries `mutation_strategy` + per-candidate
  `proposer`; `CreateRunRequest` default preserves graph_ga; CLI/eval-CLI flags parse.
- **headless:** `run_reproduction(mutation_strategy="llm")` runs to budget on the stub backend.
- **provenance:** `Generation.proposer_used="mixed"` + candidate proposers correct in a mixed gen.
- **regression:** existing `graph_ga` product + eval paths unchanged (fallback no-op; `ValidCandidate`
  default).

Quality gate before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` ·
`uv run ruff check .`.

## Out of scope (deferred, explicit)

Cost ledger + unique-call budget (slice 05) · analyzer step + `AnalyzerHypothesis` (milestone 03) ·
jnk3 launch + watch-live + UI strategy selector (slice 01 / later) · real DeepSeek run + beat verdict
(slice 06) · per-slot LLM retry before fallback · the Modal `propose()` `n=1` latent bug (no Modal
access; flagged in code).
