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
  keep top-K) and budget accounting. This keeps "Graph-GA reproduction" in one place.
- **Determinism is seeded end to end (G6).** `Run.seed` flows into `propose.py`, which
  seeds both `random` and `numpy`, so same task + same seed → same offspring → identical
  trajectory.

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
`sqlalchemy[asyncio]`, `asyncpg`. New harness dep: `numpy`. No PyTorch anywhere.

`capychem` remains a PEP 420 namespace package (no `__init__.py`); the new submodules
(`db`, `loop`) are ordinary sub-packages *under* `capychem` and may carry their own
`__init__.py` without breaking the namespace root.

## The two bridge contracts

`score.py` is unchanged. New **`propose.py`** (the only new crossing of the boundary):

- Request (stdin): `{"population": [{"smiles": "...", "score": 0.61}, ...],
  "n_offspring": 32, "mutation_rate": 0.01, "seed": 42}`
- Response (stdout): `{"offspring": ["...", "..."], "error": null}`
- Internals: seed `random` + `numpy`; fitness-weighted parent selection; `crossover` then
  probabilistic `mutate`; emit offspring SMILES. Library chatter → stderr; only the final
  JSON line reaches stdout (same discipline as `score.py`). On failure: exit 1 +
  `{"offspring": [], "error": "<msg>"}`.

Modern client `propose_offspring(population, n_offspring, *, mutation_rate, seed)` in
`oracle.py` mirrors `score_smiles`: shells out to `harness/.venv/bin/python`, parses the
last JSON line, raises `HarnessError` on failure.

## LangGraph loop

**State** (`loop/state.py`): `run_id`, `task`, `budget`, `calls_used`, `gen_index`,
`population: list[Scored]` (the survivor pool, kept at `pop_size`), `seed`, plus
run-config echoes (`pop_size`, `offspring`, `mutation_rate`, `plateau_window`).

Two distinct K's, kept separate to avoid confusion: `pop_size` is the survivor-pool
size carried generation to generation; the reporting top-K (top-10) is computed only
for `summary_json` / the G1 AUC metric.

**Nodes** (each wrapped in a Langfuse span; spans nest run → generation → node):

1. `propose` — gen 0: load `data/starting_pop.smi` (truncated to `pop_size`); gen ≥1:
   `propose_offspring(population, offspring, ...)`.
2. `validate` — modern RDKit: canonicalize, drop invalid + intra-batch duplicates
   **before** spending oracle calls (FR-004). Graph-GA rarely emits invalid, but the gate
   is mandatory per CLAUDE.md.
3. `score` — `score_smiles(valid_smiles, task)`; increment `calls_used` by the number of
   oracle calls actually made.
4. `persist` — write the `Generation` row, its `Candidate` rows (with `proposer`,
   `parent` provenance where available, `valid`, `score`), and one `OracleCall` per scored
   candidate; merge offspring + survivors and truncate to the top `pop_size` by score.
5. `stop_check` — **budget exhausted → terminate** (FR-002, partial generation persisted
   and counted); else route back to `propose`.

**Langfuse:** SDK wired through `loop/trace.py`. When `LANGFUSE_*` env keys are absent the
helpers degrade to no-ops, so pytest / CI never require a running Langfuse. When enabled,
every node emits a span (CLAUDE.md: "No silent loop steps").

## Persistence + CLI

**Async SQLAlchemy 2.0**, typed `Mapped[...]` declarative models for the four entities,
shaped per SPEC §6.2 **minus `RunCost`** (slice 4). Indexes: `(run_id, generation_index)`,
`(run_id, score DESC)`. `db/session.py` builds the async engine from
`CAPYCHEM_DATABASE_URL` (the Docker Postgres) and runs `Base.metadata.create_all` on first
connect.

**CLI** `capychem-run` (console script): parses `--task qed --budget N --seed M
--pop-size K --offspring K --mutation-rate R`, wraps the loop in `asyncio.run`, and prints
a final summary — top-K SMILES + scores, generation count, oracle calls used. This is the
slice's end-to-end proof.

## Scope calls (the three deferrals, signed off)

1. **Plateau detection (FR-003): deferred to milestone 02.** `plateau_window` is stored on
   the `Run` row (config is "from day one" per PRD) but only budget-exhaustion stops the
   loop this slice. Tuning plateau needs the real multi-gen runs that arrive in 02.
2. **AUC metric: no authoritative eval harness this slice.** Persist everything AUC needs
   (scored candidates + ordered oracle calls) and write a simple `summary_json` (top-K +
   running top-10-mean points). The canonical `packages/core/eval` AUC implementation
   stays in milestone 01/02; recomputing it ad hoc is explicitly a CLAUDE.md gotcha.
3. **Seed population: vendor a small static starting set.** `data/starting_pop.smi`
   (~100-250 drug-like SMILES) is the default. CLI `--seed` controls only the RNG. No CLI
   override of the *population* yet — that is the FR-001 launch form (milestone 02).

## Deferred (not this slice)

- LLM proposer + invalid→Graph-GA fallback exercise (no LLM yet; Graph-GA is the sole
  proposer) → milestone 02.
- Analyzer step → milestone 03.
- Plateau enforcement, authoritative AUC eval, population override → above.
- FastAPI REST + WS + Next.js → slice 3. Modal oracle + `RunCost` + cost gate → slice 4.
- Alembic migrations → first additive schema change (slice 3/4).

## Testing & verification

- **Unit:** `validate` (canonical / invalid / duplicate handling); `propose_offspring`
  determinism (same seed → identical offspring); `stop_check` budget logic; `summary_json`
  top-K computation.
- **End-to-end:** one CLI test on a tiny budget (~50 oracle calls) against the **real**
  harness QED oracle, asserting a run + generations + candidates + oracle calls land in
  Postgres and best-score is monotonic non-decreasing across the run's top-K.
- **Gate:** `scripts/smoke.sh` gains a loop check (CLI run on a tiny budget → rows in DB).
  mypy strict + ruff stay green on all new modern code.

## Exit criteria (slice-local)

- `capychem-run --task qed --budget <small> --seed 42` completes locally end-to-end.
- Run / Generation / Candidate / OracleCall rows persist with correct provenance.
- Langfuse shows a nested trace (run → generation → node) when keys are set.
- Same seed → identical top-K across two runs (G6, slice-local check).
- No `import` from `harness/` anywhere in `packages/` or `apps/`.
