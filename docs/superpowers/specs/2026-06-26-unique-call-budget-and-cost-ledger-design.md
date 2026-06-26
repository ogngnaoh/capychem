# Design — Unique-call budget & cost ledger (milestone 02, slice 05)

**Date:** 2026-06-26
**Slice:** `05-unique-call-budget-and-cost-ledger`
**Milestone:** `02-end-to-end-loop` (SPEC Phase 2)
**Deps:** slices 03, 04 (shipped + frozen)
**Status:** approved (design); pre-implementation

## Problem

The product loop and the headless eval harness disagree on what the oracle-call
budget counts:

- **Product loop** (`packages/core/capychem/loop/graph.py`, `score` node) scores
  every validated candidate and increments `calls_used` by the number scored. A
  molecule scored in generation 1 and re-proposed in generation 5 is scored again
  and counted again — so the budget counts *non-unique* calls.
- **Headless runner** (`packages/core/capychem/eval/runner.py`) keeps a
  `mol_buffer` keyed by canonical SMILES and only scores/counts molecules it has
  not seen — so its budget counts *unique* calls. This is the authoritative path
  for the G1 AUC number.

Two more gaps ride along with closing this one:

- `RunCost.llm_cost_usd` is never populated (`cost.record_oracle_cost` hardwires
  it to 0), so `RunCost.total_usd` reflects oracle spend only.
- The per-generation cost gate in the API runner reads oracle cost only, so the
  ~$50 cap (G2) cannot fire on LLM spend.
- The `llm:propose` Langfuse span opens *after* the await and carries only static
  call params (model/n/temperature/seed) — no latency-wrapping, no token/cost.

This slice makes the product loop count **unique** oracle calls, populates the LLM
cost ledger so `total_usd = llm + oracle`, rewires the cost gate to read
`total_usd`, and enriches the `llm:propose` span — all demonstrated on the cheap
CPU oracle ("designed-for-expensive, shown-on-cheap"; no expensive oracle added).

## Goals

1. The product loop's budget counts **unique** oracle calls — a re-proposed
   molecule is a cache hit: not re-scored, not counted, no new DB rows.
2. `RunCost.llm_cost_usd` is populated; `RunCost.total_usd` sums llm + oracle.
3. The per-generation cost gate reads `total_usd`, so the ~$50 cap fires on LLM
   spend alone even with the near-free jnk3 oracle.
4. The `llm:propose` span wraps the actual await and carries token + cost
   metadata.

These map to milestone-02 exit criteria 4 (unique-call budget) and 5
(`total_usd` sums llm+oracle; $50 gate fires on LLM spend).

## Non-goals (explicitly deferred)

- **valid_smiles gate purity** — `summary_json.valid_smiles.rate` currently
  includes the always-valid gen-0 seed population. Making it LLM-only is the
  **slice-06 BLOCKER**; this slice does not touch `validate.py` /
  `_validation_stats` / `build_summary`'s `valid_smiles` block.
- Analyzer step (milestone 03), the beat-Graph-GA verdict run (slice 06), jnk3
  launch + watch-live UI (slice 01 / 02), plateau-stop (slice 02), expensive
  oracles (stretch).
- Resumability / rebuilding the memo buffer from the DB after a crash — out of
  scope for this milestone (a run is one in-process task; edge-case "oracle pool
  unavailable → recoverable pause" is not in this slice).

## Key decision (resolved)

**Cross-generation cache hits are skipped entirely.** When a molecule a prior
generation already scored is re-proposed: it is not re-scored, not counted against
the budget, and **no new `Candidate` / `OracleCall` row is written**. Its score
already lives in its first generation's rows. The survivor pool for the next
prompt is unaffected — a current survivor is already present; one that fell out
stays out.

Consequences:

- Clean invariant: **`#OracleCall rows == calls_used == unique calls consumed`**.
- Because a memo *score* is never re-read into the pool, the product loop needs
  only a **`set[str]` of seen canonical SMILES**, not a score-cache dict.
- The no-progress / plateau signal is more correct: a generation of only repeats
  reads as zero forward progress (`made_progress == False`).

Rejected alternatives:

- *Mirror headless exactly* (dict cache; cached score re-enters the pool): only
  marginally closer to byte-identical headless semantics, at the cost of a
  molecule occupying two pool slots and a weaker no-progress signal.
- *Keep dup for provenance* (persist a `Candidate` with no `OracleCall`): most
  complete FR-006 provenance but breaks the tidy one-Candidate-per-oracle-call
  shape for low-value duplicate provenance.

**Memo mechanism:** in-memory `set[str]` threaded through `LoopState`, mirroring
the headless `mol_buffer`. A run is a single in-process asyncio task, so in-memory
is sufficient and simplest; a DB-query dedup would add a per-generation round-trip
for no benefit and no resumability requirement this milestone. The headless runner
is **not modified** — it already memoizes; this brings the product loop into line.

## Design

### 1. Unique-call budget in the product loop

`packages/core/capychem/loop/state.py` — add to `LoopState`:

- `mol_buffer: set[str]` — canonical SMILES already scored this run.
- `llm_cost_usd: float` — cumulative LLM spend this run (see §2).

`packages/core/capychem/loop/graph.py` — `score` node:

```
candidates = [*validated, *fallback]      # canonical, already intra-batch unique
buffer  = state.get("mol_buffer", set())
unseen  = [c for c in candidates if c.smiles not in buffer]
room    = max(budget - len(buffer), 0)    # remaining UNIQUE headroom
batch   = unseen[:room]
if not batch:
    return {"_scored": [], "calls_used": len(buffer), "mol_buffer": buffer}
results = await score_batch_async([c.smiles for c in batch], task)
scored  = [(c, r.score, r.cost_usd) for c, r in zip(batch, results, strict=True)
           if r.valid and r.score is not None]
new_buffer = buffer | {c.smiles for c, _, _ in scored}
return {"_scored": scored, "calls_used": len(new_buffer), "mol_buffer": new_buffer}
```

- `calls_used = len(new_buffer)` is the unique-call count.
- Only newly-scored unique candidates reach `_scored`, so `persist` writes a
  `Candidate` + `OracleCall` only for them; cache hits are dropped from
  persistence and from the population merge. The `_persist` node is unchanged.
- The `room` cap replaces the node's `trim_to_budget(...)` call (equivalent,
  since `calls_used == len(buffer)` after this change, but applied to `unseen`
  only). `trim_to_budget` stays in `logic.py` for the headless/tests; its import
  is dropped from `graph.py` if orphaned.
- `validated` + `_fallback_validated` are each canonicalized and intra-batch
  deduped by `validate_batch`, and `fallback_fill` already dedups fillers against
  the validated set — so the concatenated batch carries no intra-batch duplicate;
  the only duplicates are cross-generation (against `buffer`).
- Gen 0 (seed population) flows through `score` as today: seeds are added to the
  buffer and counted as unique calls, exactly as the headless runner counts its
  gen-0 seeds. No change to gen-0 accounting beyond dedup (seeds are unique).
- `state.get("mol_buffer", set())` defaults the buffer on gen 0, so neither the
  API runner's initial state nor the two CLIs need to construct it.

Determinism (G6): `unseen` preserves candidate order; `scored` is in `batch`
order; `persist` iterates `scored` in order; `merge_and_truncate` sorts
deterministically. The authoritative G6 path remains the headless runner.

### 2. LLM cost ledger

`packages/core/capychem/loop/graph.py` — `propose` node, llm branch: after the
await, `gen_llm_cost = sum(r.cost_usd for r in results)`; return cumulative
`llm_cost_usd = state.get("llm_cost_usd", 0.0) + gen_llm_cost`. graph_ga and gen-0
generations contribute 0; the `stub` proposer backend reports `cost_usd == 0`, so
CI/test runs keep `llm_cost_usd == 0`.

`packages/core/capychem/cost.py` — record **both** costs into `RunCost` so
`total_usd = llm + oracle`. The recorder keeps its name and gains an additive
keyword: `record_oracle_cost(session, run_id, oracle_usd, *, llm_usd=0.0)`,
setting `row.llm_cost_usd = llm_usd` and `row.total_usd = oracle_usd + llm_usd`.
The name is retained (surgical change): its two positional call sites — the API
runner and `test_cost.py::test_record_oracle_cost_upserts` — stay valid, and that
test stays green (it passes no `llm_usd`, so `total_usd == oracle_usd`); the
docstring is updated to reflect the llm term. `RunCost.llm_cost_usd` already
exists — no migration. The only production caller (the API runner) passes
`llm_usd=llm`.

There is no per-generation DB column for LLM cost (AnalyzerHypothesis cost is
milestone 03), so the cumulative LLM spend is sourced from `LoopState`
(`state["llm_cost_usd"]`), which the API runner reads at each generation boundary.
Oracle cost remains DB-sourced (`OracleCall.compute_cost_usd` via
`oracle_cost_so_far`) — the source of truth for oracle spend.

### 3. Cost gate reads `total_usd`

`apps/api/capychem/api/runner.py` — at each generation boundary (where the run's
cost is currently aggregated):

```
oracle = await cost.oracle_cost_so_far(session, run_id)
llm    = state.get("llm_cost_usd", 0.0)
row    = await cost.record_oracle_cost(session, run_id, oracle, llm_usd=llm)
snap["cost_so_far_usd"] = row.total_usd
...
if row.total_usd >= cost.cost_cap_usd():
    cost_capped = True
    break
```

The gate now fires on llm + oracle. `test_cost_gate.py` (graph_ga, llm=0) still
passes: `total_usd == oracle == 999.0`.

### 4. `llm:propose` span enrichment

`span()`'s yielded value is a contractual `str | None` (the span id):
`test_trace.py::test_span_yields_id_and_ends_when_enabled` asserts `sid ==
"span-123"`, and the disabled test asserts `is None or isinstance(str)`. So the
yield type must **not** change. Instead, add a span registry mirroring the
existing `_gen_spans` pattern in the same module:

`packages/core/capychem/loop/trace.py`:

- `span()` (enabled branch only) registers its live span object in a module dict
  `_live_spans[str(sp.id)] = sp` on entry and `pop`s it on exit. The yield is
  unchanged (`str(sp.id)` / `None`) — existing `test_trace.py` stays green.
- New `update_span(span_id: str | None, **metadata) -> None`: no-op when disabled,
  `span_id is None`, or the id is not live; otherwise
  `_live_spans[span_id].update(metadata=metadata)` (v2 SDK), wrapped in
  try/except so tracing never breaks the loop.

`packages/core/capychem/loop/graph.py` — `propose` node, llm branch: open the
`llm:propose` span around the await so it wraps the actual call latency, then
attach token + cost via `update_span`:

```
with trace.span("llm:propose", trace_id=..., parent_observation_id=gen_span_id,
                model=proposer.llm_model(), n=offspring,
                temperature=strategy.LLM_TEMPERATURE, seed=seed) as llm_span_id:
    results = await strategy.propose_llm_async(task, pop, n=offspring, seed=seed)
    trace.update_span(llm_span_id,
                      tokens_in=sum(r.tokens_in for r in results),
                      tokens_out=sum(r.tokens_out for r in results),
                      cost_usd=sum(r.cost_usd for r in results))
```

This is the milestone's "nicety to fold in," not a hard exit criterion; it is
included because the cost ledger lands here.

## Testing (TDD — a failing test precedes each change)

`packages/core`:

- **Unique-call budget:** a ≥2-generation scenario where gen 2 re-proposes gen-1
  molecules → `calls_used` counts unique only, and `#OracleCall == calls_used`.
- **Cost recorder:** records llm + oracle → `RunCost.total_usd == llm + oracle`.
- **LLM-cost accumulation:** monkeypatch `propose_llm_async` to return nonzero
  `cost_usd` → `LoopState["llm_cost_usd"]` accumulates across generations.

`apps/api`:

- **Gate on LLM spend:** an llm-strategy run with oracle ≈ 0 and nonzero LLM cost
  trips `cost_capped` on `total_usd`; persisted `RunCost.total_usd == llm + oracle`.
- Existing `test_cost_gate.py` continues to pass unchanged.

Span enrichment is exercised lightly (no Langfuse in CI): `update_span` is a safe
no-op when disabled / for an unknown id, and — with a fake client whose span
records `update(...)` calls — `span()` registers a live span and `update_span`
forwards the metadata, leaving `_live_spans` empty after the context exits.

Gate green before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api`
· `uv run ruff check .`.

## Files touched

- `packages/core/capychem/loop/state.py` — `mol_buffer`, `llm_cost_usd` fields.
- `packages/core/capychem/loop/graph.py` — `score` memoization; `propose` llm
  cost + span wrapping.
- `packages/core/capychem/loop/trace.py` — `_live_spans` registry + `update_span`
  (yield contract unchanged).
- `packages/core/capychem/cost.py` — `record_oracle_cost` gains `llm_usd=0.0`;
  sets llm + oracle.
- `apps/api/capychem/api/runner.py` — gate reads `total_usd`.
- Tests under `packages/core/tests/` and `apps/api/tests/`.

Untouched: `eval/runner.py` (already memoizes), `validate.py`, `proposer.py`,
`db/models.py` (no migration), `harness/`.
