# Design — Walking Skeleton Slice 2: `01-local-loop`

**Date:** 2026-06-08
**Milestone:** `00-walking-skeleton`
**Status:** Approved (design)

## Context

Slice 1 (`00-foundation`) proved the one load-bearing seam: a real QED oracle score
crosses the harness↔modern subprocess + JSON bridge. Slice 2 turns that seam into a
running optimization loop: **propose → validate → score → persist**, driven by a
Graph-GA proposer, terminated by an oracle-call budget, persisted to Postgres, and
traced to Langfuse — runnable end-to-end from a local CLI on the QED task.

This is still the walking skeleton: thin but end-to-end. No LLM proposer (milestone 02),
no analyzer (milestone 03), no web surface (slice 3), no Modal (slice 4), no perf bar.
The point is to exercise every remaining local seam — Graph-GA over the bridge, modern
RDKit validation, the LangGraph runtime, the Postgres schema, the first Langfuse spans —
before rigor phases dig in.

## Decisions

- **Graph-GA proposer = vendored Jensen operators in the harness.** Copy only the
  self-contained `crossover.py` + `mutate.py` operators (RDKit + numpy, **no PyTorch**)
  that `mol_opt` itself vendors from the original Graph-GA, into `harness/`. Expose them
  through a new `propose.py` subprocess entry beside `score.py`. The loop crosses the
  bridge for **both** propose and score — extra skeleton coverage, zero old-PyTorch
  friction. The full `mol_opt` `BaseOptimizer` baseline reproduction stays deferred to
  milestone 01 (per CLAUDE.md). *(Rejected: install full `mol_opt` — drags old PyTorch
  1.10.2 pins now, mostly for unused neural methods. Rejected: reimplement GA in modern
  RDKit — diverges from the documented "mol_opt in harness" intent and milestone-01 still
  needs harness mol_opt anyway.)*
- **Persistence = async SQLAlchemy 2.0 (asyncpg).** Matches slice 3's async FastAPI
  exactly, so the data layer never needs migrating. The CLI wraps the loop in
  `asyncio.run`. *(Rejected: sync engine — simpler now but forces a worker-thread graft
  or an async migration in slice 3.)*
- **Schema bootstrap = `metadata.create_all` now, Alembic later.** Greenfield schema is
  still churning; introduce Alembic when the first genuinely additive change lands (slice
  3 reads the schema, slice 4 adds `RunCost`). Dev resets are drop/recreate.
- **The harness owns the full GA *reproduce* step.** `propose.py` receives the scored
  population and does fitness-weighted parent sampling → crossover → mutate → offspring.
  Modern code owns population management across generations (merge offspring + survivors,
  keep top-K) and budget accounting. This keeps "Graph-GA reproduction" in one place. Each
  offspring is returned **with the indices of the parent(s) it was bred from** so modern
  code can record `parent_candidate_id` provenance (FR-006).
- **Determinism is seeded end to end (G6).** `Run.seed` flows into `propose.py` as a
  **per-generation derived seed (`seed + gen_index`)**, seeding both `random` and `numpy`;
  modern-side survivor selection breaks score ties **deterministically** (by canonical
  SMILES). Same task + same seed → same offspring each generation → identical trajectory.
  (A constant seed reused every generation would make generations correlate; deriving per
  generation keeps each one distinct yet reproducible.)

## Architecture

```
harness/capychem_harness/
  graph_ga/crossover.py     VENDORED Jensen crossover (RDKit + numpy)
  graph_ga/mutate.py        VENDORED Jensen mutation (RDKit + numpy)
  propose.py                NEW bridge entry: scored population -> N offspring SMILES
  score.py                  (exists, unchanged)
  data/starting_pop.smi     small vendored starting population (~100-250 drug-like SMILES)

packages/core/capychem/
  oracle.py                 (exists) + new propose_offspring() bridge client
  validate.py               NEW modern-RDKit canonicalization + validity
  db/models.py              async SQLAlchemy 2.0: Run, Generation, Candidate, OracleCall
  db/session.py             async engine + sessionmaker + create_all bootstrap
  loop/state.py             LoopState
  loop/graph.py             LangGraph: propose -> validate -> score -> persist -> stop_check
  loop/trace.py             Langfuse span helpers (no-op when LANGFUSE_* keys absent)
  cli.py                    `capychem-run --task qed --budget N --seed M`

packages/core/tests/        unit tests + one end-to-end CLI test (real harness QED)
```

New modern deps (`packages/core`): `rdkit`, `langgraph`, `langfuse`,
`sqlalchemy[asyncio]`, `asyncpg`. Pin the modern `rdkit` to the **same major.minor as the
harness RDKit (2026.3.x)** — validation/canonicalization happens modern-side while proposing
canonicalizes harness-side, and canonical-SMILES form (the dedup key) can drift across RDKit
versions, which would break both dedup and G6. `numpy` is already present in the harness env
(transitive via PyTDC); declare it explicitly in `harness/pyproject.toml` for hygiene — it
adds no resolution risk. No PyTorch anywhere.

`capychem` remains a PEP 420 namespace package (no `__init__.py`); the new submodules
(`db`, `loop`) are ordinary sub-packages *under* `capychem` and may carry their own
`__init__.py` without breaking the namespace root.

## The two bridge contracts

`score.py` is unchanged. New **`propose.py`** (the only new crossing of the boundary):

- Request (stdin): `{"population": [{"smiles": "...", "score": 0.61}, ...],
  "n_offspring": 32, "mutation_rate": 0.01, "seed": 42}`. The modern client passes a
  **per-generation seed** (`base_seed + gen_index`) so each generation's RNG is distinct yet
  reproducible.
- Response (stdout): `{"offspring": [{"smiles": "...", "parents": [i, j]}, ...],
  "error": null}` — each offspring carries the **indices (into the request `population`
  array) of the two crossover parents it was bred from**. (Jensen `reproduce` always runs
  crossover; `mutate` is applied probabilistically afterward and does not change parentage —
  so every offspring has exactly two parent indices.) Modern code maps `parents[0]` back to
  the parent's `Candidate` ID to populate `parent_candidate_id` (FR-006); the second parent
  is recoverable from the trace.
- Internals: seed `random` + `numpy` from the request seed; fitness-weighted parent
  selection; `crossover(parent_a, parent_b)` then probabilistic `mutate`; emit offspring
  SMILES **plus parent indices**. Crossover can fail RDKit ring/validity checks and yield
  nothing for a slot, so a generation may return **fewer than `n_offspring`** offspring —
  the loop's validate + zero-progress guards already tolerate a short or empty batch, and
  the determinism test compares the *resulting* offspring list (dropped slots included), not
  a fixed count. Library chatter → stderr; only the final JSON line reaches stdout (same
  discipline as `score.py`). On failure: exit 1 + `{"offspring": [], "error": "<msg>"}`.

Modern client `propose_offspring(population, n_offspring, *, mutation_rate, seed)` in
`oracle.py` mirrors `score_smiles`: shells out to `harness/.venv/bin/python`, parses the
last JSON line, raises `HarnessError` on failure, and returns the structured offspring
(SMILES + parent indices).

## LangGraph loop

**State** (`loop/state.py`): `run_id`, `task`, `budget`, `calls_used`, `gen_index`,
`population: list[Scored]` (the survivor pool, kept at `pop_size`), `seed`, plus
run-config echoes (`pop_size`, `offspring`, `mutation_rate`, `plateau_window`) and the
active Langfuse span IDs (`run_span_id`, `gen_span_id`) threaded explicitly so node spans
nest correctly across `async` boundaries (see Langfuse note below).

**Defaults:** `pop_size=100`, `offspring=32`, `mutation_rate=0.01` (the Jensen Graph-GA
default), `seed=42`. These are the production-ish defaults; the **end-to-end test overrides
them to a small pop** (`pop_size≈20`, `offspring≈10`) with a budget that comfortably covers
gen 0 + ≥2 offspring generations, so the monotonicity assertion is actually exercised
(see Testing). A `max_generations` safety cap (default 100) bounds the loop given no plateau
detection this slice.

Two distinct K's, kept separate to avoid confusion: `pop_size` is the survivor-pool
size carried generation to generation; the reporting top-K (top-10) is computed only
for `summary_json` / the G1 AUC metric.

**Nodes** (each wrapped in a Langfuse span; spans nest run → generation → node):

1. `propose` — **gen 0**: load `data/starting_pop.smi` (truncated to `pop_size`), with no
   parents. **gen ≥1**: `propose_offspring(population, offspring, mutation_rate, seed +
   gen_index)`, yielding offspring SMILES + parent indices.
2. `validate` — modern RDKit: canonicalize, drop invalid + intra-batch duplicates
   **before** spending oracle calls (FR-004). Graph-GA rarely emits invalid, but the gate
   is mandatory per CLAUDE.md. Carry each surviving candidate's parent indices forward.
3. `score` — **trim** the validated batch to `min(len, budget − calls_used)` so a
   generation never overshoots the budget (FR-002); then `score_smiles(trimmed, task)` and
   increment `calls_used` by the oracle calls actually made.
4. `persist` — write the `Generation` row, its `Candidate` rows (`smiles`, `proposer`,
   `valid`, `score`, and **`parent_candidate_id` resolved from the parent indices** —
   crossover stores the first parent; both parents are recoverable from the trace), one
   `OracleCall` per scored candidate (`compute_cost_usd` = 0.0 for the local subprocess
   oracle this slice — see note), then merge offspring + survivors and truncate to the top
   `pop_size` by score with a **deterministic tiebreak (canonical SMILES)**.
5. `stop_check` — terminate when **budget exhausted** (FR-002, partial generation persisted
   and counted), **`max_generations` reached**, or a generation made **zero forward
   progress** (empty validated/scored batch — guards against an infinite loop on a fully
   invalid or fully duplicate batch); else route back to `propose`.

**Langfuse:** SDK wired through `loop/trace.py`. When `LANGFUSE_*` env keys are absent the
helpers degrade to no-ops, so pytest / CI never require a running Langfuse. When enabled,
every node emits a span (CLAUDE.md: "No silent loop steps"). Nesting is maintained by
**threading the parent span IDs explicitly through `LoopState`** (`run_span_id`,
`gen_span_id`) rather than relying on contextvars, which can be lost across `await`
boundaries in the async loop — each node creates its span as a child of the current
`gen_span_id`. The "Langfuse shows a nested trace" exit criterion verifies this end to end.

## Persistence + CLI

**Async SQLAlchemy 2.0**, typed `Mapped[...]` declarative models for the four entities,
shaped per SPEC §6.2 **minus `RunCost`** (slice 4). `OracleCall` keeps `compute_cost_usd`
(SPEC §6.2) but it is `0.0` for the local subprocess oracle this slice — Modal billing
arrives in slice 4. Indexes: `Generation(run_id, index)` and `OracleCall(run_id, score
DESC)` (score lives on `Candidate` and `OracleCall`; the top-K query reads `OracleCall`,
which carries `run_id` directly). `db/session.py` builds the async engine from
`CAPYCHEM_DATABASE_URL` (the Docker Postgres) and runs `Base.metadata.create_all` on first
connect.

**CLI** `capychem-run` (console script): parses `--task qed --budget N --seed M
--pop-size K --offspring K --mutation-rate R`, wraps the loop in `asyncio.run`, and prints
a final summary — top-K SMILES + scores, generation count, oracle calls used. This is the
slice's end-to-end proof.

## Scope calls (the deferrals, signed off)

1. **Plateau detection (FR-003): deferred to milestone 02.** `plateau_window` is stored on
   the `Run` row (config is "from day one" per PRD) but only budget-exhaustion (plus the
   `max_generations` cap and zero-progress guard) stops the loop this slice. Tuning plateau
   needs the real multi-gen runs that arrive in 02.
2. **AUC metric: no authoritative eval harness this slice.** Persist everything AUC needs
   (scored candidates + ordered oracle calls) and write a simple `summary_json` of shape
   `{"top_k": [{"smiles": str, "score": float}, ...], "auc_curve": [{"oracle_calls": int,
   "top10_mean": float}, ...], "generations": int, "oracle_calls": int}`. The `auc_curve`
   here is the **un-authoritative** running top-10-mean; the canonical `packages/core/eval`
   AUC implementation lands in milestone 01/02, and recomputing it ad hoc is explicitly a
   CLAUDE.md gotcha — slice 3's reader and milestone 02's eval consume this shape but treat
   the curve as illustrative, not the G1 number.
3. **Seed population: vendor a small static starting set.** `data/starting_pop.smi`
   (~100-250 drug-like SMILES) is the default, sourced from `mol_opt`'s own Graph-GA
   starting set (a ZINC-derived, public/permissively-licensed sample — same provenance as
   the vendored Jensen operators; attribute the source in a header comment in the `.smi`
   file per PRD N3 / SPEC public-data requirement). CLI `--seed` controls only the RNG. No
   CLI override of the *population* yet — that is the FR-001 launch form (milestone 02).
4. **Cross-generation dedup / oracle memoization: deferred, consciously.** `validate` drops
   intra-batch duplicates only; offspring that re-derive an existing survivor or a
   previously-scored molecule are re-scored (wasting cheap local oracle calls). The
   memoization/caching layer is the backend story (PROJECT.md §10) and lands with the Modal
   oracle in slice 4; the tiny local oracle makes the waste affordable for the skeleton.
   Noted here so it is a deliberate deferral, not a silent gap.

## Deferred (not this slice)

- LLM proposer + invalid→Graph-GA fallback exercise (no LLM yet; Graph-GA is the sole
  proposer) → milestone 02.
- Analyzer step → milestone 03.
- Plateau enforcement, authoritative AUC eval, population override → above.
- FastAPI REST + WS + Next.js → slice 3. Modal oracle + `RunCost` + cost gate → slice 4.
- Alembic migrations → first additive schema change (slice 3/4).

## Testing & verification

- **Unit:** `validate` (canonical / invalid / duplicate handling, incl. an all-invalid and
  an all-duplicate batch hitting the zero-progress path); `propose_offspring` determinism
  (same seed → identical offspring **and** identical parent indices); `score`-node budget
  trim (batch larger than remaining budget is trimmed, never overshoots); `stop_check`
  termination logic (budget / max-gen / zero-progress); `summary_json` top-K + curve
  computation; deterministic survivor tiebreak on equal scores.
- **End-to-end:** one CLI test against the **real** harness QED oracle with a **small pop
  (`pop_size≈20`, `offspring≈10`) and a budget that covers gen 0 + ≥2 offspring
  generations** (so monotonicity is non-vacuous). Asserts a run + generations + candidates +
  oracle calls land in Postgres; that `parent_candidate_id` is populated for gen-≥1
  candidates and NULL for gen-0; that `calls_used` never exceeds `budget`; and that
  best-score-so-far is monotonic non-decreasing across generations.
- **Determinism (G6, slice-local):** two CLI runs with the same task + same seed produce
  identical top-K SMILES + scores.
- **Gate:** `scripts/smoke.sh` gains a loop check (CLI run on a tiny budget → rows in DB).
  mypy strict + ruff stay green on all new modern code.

## Exit criteria (slice-local)

- `capychem-run --task qed --budget <small> --seed 42` completes locally end-to-end.
- Run / Generation / Candidate / OracleCall rows persist with correct provenance.
- Langfuse shows a nested trace (run → generation → node) when keys are set.
- Same seed → identical top-K across two runs (G6, slice-local check).
- No `import` from `harness/` anywhere in `packages/` or `apps/`.
