# LLM Proposer with Graph-GA Fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire an LLM proposer into the optimization loop behind a `mutation_strategy`-selected abstraction, with a deterministic Graph-GA fallback so generation throughput never drops on invalid LLM output, reachable from both the product loop and the headless eval runner.

**Architecture:** A shared `loop/strategy.py` holds the G6-sensitive pieces (prompt, LLM call + sync bridge, GA fill, fallback fill). The loop gains one node — `propose → validate → fallback → score → persist → stop_check` — so the frozen `valid_smiles` stat stays LLM-only (the `validate` node only ever sees the proposer's direct output; fallback fillers are added after and never counted). Per-candidate provenance flows via an additive `ValidCandidate.proposer` field. The valid-SMILES gate observes and records; it never halts.

**Tech Stack:** Python 3.12, LangGraph, RDKit, SQLAlchemy 2.0 async, pytest (async), mypy strict, ruff. Proposer backend = `stub` (network-free) for all of this slice.

## Global Constraints

(Copied verbatim from CLAUDE.md / SPEC / the approved design — every task implicitly includes these.)

- **NEVER import from `harness/`.** Modern code reaches the harness only via `oracle.py` subprocess + JSON.
- **Validate every SMILES via RDKit before persistence.** Never trust LLM output as valid.
- **Wrap every LangGraph node in a Langfuse span.** No silent loop steps. (`trace.span` no-ops without `LANGFUSE_*` keys.)
- **TDD — no production code without a failing test first.**
- **Stub-only this slice.** No network, no `DEEPSEEK_API_KEY`. The real DeepSeek `direct` run + the actual jnk3 validity verdict are slice 06.
- **The valid-SMILES gate observes + records; it never halts a run.**
- **No cost ledger this slice.** `RunCost.llm_cost_usd` + cost-gate rewire are slice 05.
- **Secrets stay in `.env.local`** (gitignored). **No real-world efficacy claims** (PRD N6).
- **mypy strict on all new/changed code.** Quality gate before merge: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`.
- **Pinned determinism (G6):** LLM temperature is a fixed module constant; per-generation seed is `run_seed + gen_index`.

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `packages/core/capychem/loop/strategy.py` | **Create** | Shared proposer pieces: `build_prompt`, `propose_llm_async`, `propose_llm_sync`, `ga_fill`, `fallback_fill`, `LLM_TEMPERATURE`. |
| `packages/core/capychem/validate.py` | Modify | `ValidCandidate` += `proposer: str = "graph_ga"`. |
| `packages/core/capychem/loop/graph.py` | Modify | `propose` strategy branch + LLM span; `validate` tags from `_proposer`; new `fallback` node; `score` merges fallback; `persist` per-candidate proposer; topology edge. |
| `packages/core/capychem/loop/state.py` | Modify | `LoopState` += `mutation_strategy`, `_fallback_validated`. |
| `packages/core/capychem/loop/logic.py` | Modify | `valid_smiles_gate` helper; `build_summary` embeds the gate. |
| `packages/core/capychem/run.py` | Modify | `RunConfig` += `mutation_strategy`; `create_run` uses it. |
| `packages/core/capychem/cli.py` | Modify | `--mutation-strategy` flag; thread to `LoopState`; gate verdict print. |
| `packages/core/capychem/eval/runner.py` | Modify | `run_reproduction(..., mutation_strategy=...)` LLM branch via the shared helpers. |
| `packages/core/capychem/eval/cli.py` | Modify | `--mutation-strategy` flag. |
| `apps/api/capychem/api/schemas.py` | Modify | `CreateRunRequest` += `mutation_strategy: Literal["graph_ga","llm"]`. |
| `apps/api/capychem/api/routes_runs.py` | Modify | Pass `mutation_strategy` into `RunConfig`. |
| `apps/api/capychem/api/runner.py` | Modify | `_drive` initial `LoopState` sets `mutation_strategy`; bump recursion-limit comment/headroom. |
| `packages/core/tests/test_strategy.py` | **Create** | Strategy-module unit tests. |
| `packages/core/tests/test_loop_fallback.py` | **Create** | Fallback node + provenance tests. |
| `packages/core/tests/test_loop_llm_e2e.py` | **Create** | End-to-end `mutation_strategy="llm"` product run on stub. |
| existing test files | Modify | Add cases to `test_validate_node.py`, `test_loop_logic.py`, `test_eval_runner.py`, `test_runner.py` (api), `test_proposer`-adjacent as needed. |

---

### Task 1: Per-candidate provenance (`ValidCandidate.proposer` + validate tagging)

**Files:**
- Modify: `packages/core/capychem/validate.py`
- Modify: `packages/core/capychem/loop/graph.py` (the `validate` node only)
- Test: `packages/core/tests/test_validate_node.py`

**Interfaces:**
- Produces: `ValidCandidate(smiles: str, parents: tuple[int,int]|None, proposer: str = "graph_ga")`. The `validate` node returns `validated` with each candidate's `proposer` set to `state.get("_proposer", "graph_ga")`.

- [ ] **Step 1: Write the failing test** — append to `packages/core/tests/test_validate_node.py`:

```python
async def test_validate_node_tags_candidates_with_proposer() -> None:
    state: dict[str, Any] = {
        "proposed": [("CCO", None), ("c1ccccc1", None)],
        "_proposer": "llm",
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out = await validate(state)  # type: ignore[arg-type]
    assert {c.proposer for c in out["validated"]} == {"llm"}


async def test_validate_node_defaults_proposer_to_graph_ga() -> None:
    state: dict[str, Any] = {
        "proposed": [("CCO", None)],
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out = await validate(state)  # type: ignore[arg-type]
    assert out["validated"][0].proposer == "graph_ga"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/core/tests/test_validate_node.py -v`
Expected: FAIL — `ValidCandidate` has no `proposer` attribute / `TypeError`.

- [ ] **Step 3: Add the field** in `packages/core/capychem/validate.py` — extend the `ValidCandidate` dataclass:

```python
@dataclass(frozen=True)
class ValidCandidate:
    """A canonicalized, unique candidate that survived validation.

    ``parents`` carries the proposer's provenance forward (None at gen 0).
    ``proposer`` records which proposer produced it ("graph_ga" | "llm" |
    "starting"); defaults to "graph_ga" so the eval + Graph-GA paths need no change.
    """

    smiles: str  # canonical SMILES
    parents: tuple[int, int] | None
    proposer: str = "graph_ga"
```

- [ ] **Step 4: Tag in the validate node** in `packages/core/capychem/loop/graph.py` — add `replace` to the dataclasses import and re-tag inside the `validate` node:

```python
from dataclasses import replace
```

In `validate`, replace the return with:

```python
        validated, stats = validate_batch_with_stats(state["proposed"])
        proposer = state.get("_proposer", "graph_ga")
        validated = [replace(vc, proposer=proposer) for vc in validated]
        prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
        return {
            "validated": validated,
            "_validation_stats": {
                "proposed": prev["proposed"] + stats.proposed,
                "valid": prev["valid"] + stats.valid,
            },
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_validate_node.py -v`
Expected: PASS (all 4, including the two pre-existing).

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/validate.py packages/core/capychem/loop/graph.py packages/core/tests/test_validate_node.py
git commit -m "feat(loop): per-candidate proposer provenance on ValidCandidate"
```

---

### Task 2: Shared strategy module (`loop/strategy.py`)

**Files:**
- Create: `packages/core/capychem/loop/strategy.py`
- Test: `packages/core/tests/test_strategy.py`

**Interfaces:**
- Consumes: `proposer.propose_batch_async` (slice 03), `oracle.propose_offspring`, `validate.validate_batch` + `ValidCandidate`.
- Produces:
  - `LLM_TEMPERATURE: float = 0.7`
  - `build_prompt(task: str, population: list[tuple[str, float]], n: int) -> str`
  - `async propose_llm_async(task: str, population: list[tuple[str, float]], *, n: int, seed: int) -> list[ProposalResult]`
  - `propose_llm_sync(task: str, population: list[tuple[str, float]], *, n: int, seed: int) -> list[ProposalResult]`
  - `ga_fill(population: list[tuple[str, float]], n: int, *, mutation_rate: float, seed: int) -> list[tuple[str, tuple[int,int]|None]]`
  - `fallback_fill(validated: list[ValidCandidate], population: list[tuple[str, float]], *, target: int, mutation_rate: float, seed: int) -> list[ValidCandidate]`

- [ ] **Step 1: Write the failing tests** — create `packages/core/tests/test_strategy.py`:

```python
"""Shared proposer strategy pieces (milestone-02 slice 04)."""

from __future__ import annotations

import pytest
from capychem import proposer as proposer_mod
from capychem.loop import strategy
from capychem.validate import ValidCandidate


def test_build_prompt_is_deterministic_and_mentions_task_and_population() -> None:
    pop = [("CCO", 0.9), ("c1ccccc1", 0.4)]
    p1 = strategy.build_prompt("jnk3", pop, 5)
    p2 = strategy.build_prompt("jnk3", pop, 5)
    assert p1 == p2
    assert "jnk3" in p1
    assert "CCO" in p1


async def test_propose_llm_async_uses_pinned_temperature_and_seed(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_batch(prompt, n, *, temperature=0.7, seed=0):
        captured.update(prompt=prompt, n=n, temperature=temperature, seed=seed)
        return [
            proposer_mod.ProposalResult(raw="CCO", smiles="CCO", tokens_in=0, tokens_out=0)
            for _ in range(n)
        ]

    monkeypatch.setattr(strategy, "propose_batch_async", fake_batch)
    out = await strategy.propose_llm_async("qed", [("CCO", 0.5)], n=3, seed=11)
    assert len(out) == 3
    assert captured["temperature"] == strategy.LLM_TEMPERATURE
    assert captured["seed"] == 11


def test_propose_llm_sync_bridges_async(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    out = strategy.propose_llm_sync("qed", [("CCO", 0.5)], n=4, seed=7)
    assert len(out) == 4
    assert all(isinstance(r, proposer_mod.ProposalResult) for r in out)


def test_ga_fill_wraps_propose_offspring(monkeypatch) -> None:
    from capychem.oracle import Offspring

    def fake_offspring(population, n_offspring, *, mutation_rate, seed, **kw):
        return [Offspring(smiles="CCC", parents=(0, 1)) for _ in range(n_offspring)]

    monkeypatch.setattr(strategy, "propose_offspring", fake_offspring)
    out = strategy.ga_fill([("CCO", 0.5), ("CCN", 0.4)], 3, mutation_rate=0.01, seed=5)
    assert out == [("CCC", (0, 1)), ("CCC", (0, 1)), ("CCC", (0, 1))]


def test_fallback_fill_backfills_gap_and_dedups(monkeypatch) -> None:
    from capychem.oracle import Offspring

    # GA returns one fresh valid SMILES (CCC) and one that duplicates an existing
    # validated candidate (CCO) -> the duplicate is dropped.
    def fake_offspring(population, n_offspring, *, mutation_rate, seed, **kw):
        return [Offspring(smiles="CCC", parents=(0, 1)), Offspring(smiles="OCC", parents=(0, 1))]

    monkeypatch.setattr(strategy, "propose_offspring", fake_offspring)
    validated = [ValidCandidate(smiles="CCO", parents=None, proposer="llm")]  # canonical "CCO"
    out = strategy.fallback_fill(
        validated, [("CCO", 0.5), ("CCN", 0.4)], target=3, mutation_rate=0.01, seed=5
    )
    smiles = {c.smiles for c in out}
    assert "CCC" in smiles
    assert "CCO" not in smiles  # OCC canonicalizes to CCO -> deduped against the LLM-valid set
    assert all(c.proposer == "graph_ga" for c in out)


def test_fallback_fill_returns_empty_when_no_gap() -> None:
    validated = [ValidCandidate(smiles="CCO", parents=None, proposer="llm")]
    assert strategy.fallback_fill(validated, [("CCO", 0.5)], target=1, mutation_rate=0.01, seed=5) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest packages/core/tests/test_strategy.py -v`
Expected: FAIL — `No module named 'capychem.loop.strategy'`.

- [ ] **Step 3: Implement** — create `packages/core/capychem/loop/strategy.py`:

```python
"""Shared proposer strategy pieces for milestone-02 slice 04.

Both the product loop (``loop/graph.py``) and the headless eval runner
(``eval/runner.py``) import these so the LLM path is byte-identical in each — G6
reproducibility. ``build_prompt`` is the MOLLEO-style mutation prompt (no analyzer
hypothesis yet — that arrives in milestone 03). ``ga_fill`` wraps the Graph-GA
seam for BOTH the ``graph_ga`` strategy and the LLM fallback; ``fallback_fill`` is
the invalid-output backfill (FR-005). Temperature is pinned (G6).
"""

from __future__ import annotations

import asyncio

from capychem.oracle import propose_offspring
from capychem.proposer import ProposalResult, propose_batch_async
from capychem.validate import ValidCandidate, validate_batch

LLM_TEMPERATURE = 0.7


def build_prompt(task: str, population: list[tuple[str, float]], n: int) -> str:
    """MOLLEO-style single-molecule mutation prompt.

    Lists the current best molecules (by score, descending) and asks for ONE new
    valid SMILES. The ``direct`` backend fans out ``n`` single-choice requests and
    ``_clean_smiles`` takes the first token, so one SMILES per completion.
    """
    top = sorted(population, key=lambda p: (-p[1], p[0]))[:10]
    lines = "\n".join(f"{smi}\t{score:.4f}" for smi, score in top)
    return (
        f"You are optimizing molecules for the '{task}' objective (higher score is better).\n"
        f"Current best molecules (SMILES, score):\n{lines}\n\n"
        "Propose ONE new, valid, drug-like molecule likely to score higher. "
        "Output only its SMILES string — no prose, no code fences."
    )


async def propose_llm_async(
    task: str, population: list[tuple[str, float]], *, n: int, seed: int
) -> list[ProposalResult]:
    """Propose ``n`` LLM candidates with a pinned temperature + per-gen seed (G6)."""
    return await propose_batch_async(
        build_prompt(task, population, n), n, temperature=LLM_TEMPERATURE, seed=seed
    )


def propose_llm_sync(
    task: str, population: list[tuple[str, float]], *, n: int, seed: int
) -> list[ProposalResult]:
    """Synchronous bridge for the headless eval path (no running event loop)."""
    return asyncio.run(propose_llm_async(task, population, n=n, seed=seed))


def ga_fill(
    population: list[tuple[str, float]], n: int, *, mutation_rate: float, seed: int
) -> list[tuple[str, tuple[int, int] | None]]:
    """Graph-GA offspring as (smiles, parents) pairs. Serves the graph_ga strategy
    AND the LLM fallback. May return fewer than ``n`` (crossover validity)."""
    offs = propose_offspring(population, n, mutation_rate=mutation_rate, seed=seed)
    return [(o.smiles, o.parents) for o in offs]


def fallback_fill(
    validated: list[ValidCandidate],
    population: list[tuple[str, float]],
    *,
    target: int,
    mutation_rate: float,
    seed: int,
) -> list[ValidCandidate]:
    """Backfill invalid LLM output with Graph-GA offspring so a generation reaches
    ``target`` valid candidates (FR-005). Single GA-fill round (no retry). Fillers
    are RDKit-validated and deduped against the LLM-valid set; tagged "graph_ga"."""
    gap = target - len(validated)
    if gap <= 0 or not population:
        return []
    fillers_raw = ga_fill(population, gap, mutation_rate=mutation_rate, seed=seed)
    existing = {v.smiles for v in validated}
    return [vc for vc in validate_batch(fillers_raw) if vc.smiles not in existing]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest packages/core/tests/test_strategy.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/strategy.py packages/core/tests/test_strategy.py
git commit -m "feat(loop): shared LLM/Graph-GA proposer strategy module"
```

---

### Task 3: Thread `mutation_strategy` through config, state, schema, and CLIs

**Files:**
- Modify: `packages/core/capychem/run.py`, `packages/core/capychem/loop/state.py`, `packages/core/capychem/cli.py`
- Modify: `apps/api/capychem/api/schemas.py`, `apps/api/capychem/api/routes_runs.py`, `apps/api/capychem/api/runner.py`
- Test: `packages/core/tests/test_run_config.py` (**create**), and `apps/api/tests/test_runner.py` (add a case)

**Interfaces:**
- Produces: `RunConfig(..., mutation_strategy: str = "graph_ga")`; `LoopState["mutation_strategy"]`; `CreateRunRequest.mutation_strategy: Literal["graph_ga","llm"] = "graph_ga"`. `create_run` writes `config.mutation_strategy` to `Run.mutation_strategy`.

- [ ] **Step 1: Write the failing test** — create `packages/core/tests/test_run_config.py`:

```python
"""RunConfig threads mutation_strategy onto the Run row (slice 04)."""

from __future__ import annotations

import pytest
from capychem.db.models import Base, Run
from capychem.run import RunConfig, create_run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _cfg(**kw):
    base = dict(
        task="qed", budget=10, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=2, max_generations=1,
    )
    base.update(kw)
    return RunConfig(**base)


async def test_create_run_persists_mutation_strategy(sm) -> None:
    async with sm() as s:
        run_id = await create_run(s, _cfg(mutation_strategy="llm"))
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row.mutation_strategy == "llm"


async def test_run_config_defaults_to_graph_ga(sm) -> None:
    async with sm() as s:
        run_id = await create_run(s, _cfg())
    async with sm() as s:
        row = await s.get(Run, run_id)
    assert row.mutation_strategy == "graph_ga"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_run_config.py -v`
Expected: FAIL — `RunConfig` has no `mutation_strategy` / `create_run` ignores it (row is "graph_ga" for the "llm" case).

- [ ] **Step 3: Add to `RunConfig` + `create_run`** in `packages/core/capychem/run.py`:

```python
@dataclass(frozen=True)
class RunConfig:
    task: str
    budget: int
    seed: int
    pop_size: int
    offspring: int
    mutation_rate: float
    plateau_window: int
    max_generations: int
    mutation_strategy: str = "graph_ga"
```

And in `create_run`, change the hardcoded line to:

```python
        mutation_strategy=config.mutation_strategy,
```

- [ ] **Step 4: Add to `LoopState`** in `packages/core/capychem/loop/state.py` — under the `# config / identity` block add `mutation_strategy: str`, and in the transient carriers block add `_fallback_validated: list[ValidCandidate]`:

```python
    mutation_strategy: str
```
```python
    _fallback_validated: list[ValidCandidate]  # GA fallback fillers (slice 04)
```

- [ ] **Step 5: Add to the API schema + route** — in `apps/api/capychem/api/schemas.py`, add to `CreateRunRequest`:

```python
    mutation_strategy: Literal["graph_ga", "llm"] = "graph_ga"
```

In `apps/api/capychem/api/routes_runs.py`, add to the `RunConfig(...)` construction in `create_run_endpoint`:

```python
        mutation_strategy=body.mutation_strategy,
```

- [ ] **Step 6: Set it in the runner + CLI initial state** — in `apps/api/capychem/api/runner.py` `_drive`, add to the `initial` dict:

```python
            "mutation_strategy": cfg.mutation_strategy,
```

In `packages/core/capychem/cli.py`: add the arg in `parse_args` (after `--max-generations`):

```python
    p.add_argument("--mutation-strategy", choices=["graph_ga", "llm"], default="graph_ga")
```

add to the `RunConfig(...)` in `run`:

```python
        mutation_strategy=args.mutation_strategy,
```

and add to the `initial` `LoopState` dict in `run`:

```python
        "mutation_strategy": args.mutation_strategy,
```

- [ ] **Step 7: Run the tests** (new + the touched suites)

Run: `uv run pytest packages/core/tests/test_run_config.py apps/api/tests/test_runner.py -v`
Expected: PASS. (If `apps/api/tests/test_runner.py` builds a `RunConfig`/initial state literally, it still passes via the default.)

- [ ] **Step 8: Commit**

```bash
git add packages/core/capychem/run.py packages/core/capychem/loop/state.py packages/core/capychem/cli.py apps/api/capychem/api/schemas.py apps/api/capychem/api/routes_runs.py apps/api/capychem/api/runner.py packages/core/tests/test_run_config.py
git commit -m "feat: thread mutation_strategy launch -> RunConfig -> LoopState"
```

---

### Task 4: Strategy-aware `propose` node (+ LLM span)

**Files:**
- Modify: `packages/core/capychem/loop/graph.py` (the `propose` node)
- Test: `packages/core/tests/test_loop_propose.py` (**create**)

**Interfaces:**
- Consumes: `strategy.ga_fill`, `strategy.propose_llm_async`, `strategy.LLM_TEMPERATURE`, `proposer.llm_model`, `state["mutation_strategy"]`.
- Produces: `propose` returns `{"proposed": list[tuple[str, tuple[int,int]|None]], "_proposer": "starting"|"graph_ga"|"llm", "gen_span_id": ...}`. For `llm`, `proposed` items have `parents=None`.

- [ ] **Step 1: Write the failing tests** — create `packages/core/tests/test_loop_propose.py`:

```python
"""The propose node selects the proposer by mutation_strategy (slice 04)."""

from __future__ import annotations

from typing import Any

from capychem.loop import graph as graph_mod
from capychem.loop import strategy
from capychem.loop.state import Scored


def _gen1_state(strategy_name: str) -> dict[str, Any]:
    return {
        "gen_index": 1,
        "mutation_strategy": strategy_name,
        "task": "qed",
        "offspring": 3,
        "mutation_rate": 0.01,
        "seed": 42,
        "pop_size": 4,
        "population": [Scored(smiles="CCO", score=0.9), Scored(smiles="CCN", score=0.4)],
        "calls_used": 0,
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_propose_graph_ga_uses_ga_fill(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_mod.strategy, "ga_fill",
        lambda pop, n, *, mutation_rate, seed: [("CCC", (0, 1))] * n,
    )
    out = await graph_mod.propose(_gen1_state("graph_ga"))  # type: ignore[arg-type]
    assert out["_proposer"] == "graph_ga"
    assert out["proposed"] == [("CCC", (0, 1))] * 3


async def test_propose_llm_returns_raw_strings_parents_none(monkeypatch) -> None:
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        return [ProposalResult(raw="CCO", smiles="CCO", tokens_in=1, tokens_out=2) for _ in range(n)]

    monkeypatch.setattr(graph_mod.strategy, "propose_llm_async", fake_llm)
    out = await graph_mod.propose(_gen1_state("llm"))  # type: ignore[arg-type]
    assert out["_proposer"] == "llm"
    assert out["proposed"] == [("CCO", None)] * 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_propose.py -v`
Expected: FAIL — `propose` does not branch on `mutation_strategy` / `graph_mod.strategy` not imported.

- [ ] **Step 3: Implement** — in `packages/core/capychem/loop/graph.py`, add imports:

```python
from capychem.loop import strategy
from capychem import proposer
```

Replace the gen≥1 branch of the `propose` node body so the whole node reads:

```python
async def propose(state: LoopState) -> dict[str, Any]:
    gen_span_id = trace.gen_span(
        state.get("run_trace_id"),
        state["run_id"],
        state["gen_index"],
        calls_used=state["calls_used"],
    )
    with trace.span(
        "node:propose",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=gen_span_id,
    ):
        raw: list[tuple[str, tuple[int, int] | None]]
        if state["gen_index"] == 0:
            raw = [(smi, None) for smi in _load_starting_pop(state["pop_size"])]
            proposer_label = "starting"
        else:
            pop = [(m.smiles, m.score) for m in state["population"]]
            seed = state["seed"] + state["gen_index"]  # per-gen derived seed (G6)
            if state.get("mutation_strategy", "graph_ga") == "llm":
                results = await strategy.propose_llm_async(
                    state["task"], pop, n=state["offspring"], seed=seed
                )
                with trace.span(
                    "llm:propose",
                    trace_id=state.get("run_trace_id"),
                    parent_observation_id=gen_span_id,
                    model=proposer.llm_model(),
                    n=state["offspring"],
                    temperature=strategy.LLM_TEMPERATURE,
                    seed=seed,
                ):
                    pass
                raw = [(r.smiles, None) for r in results]
                proposer_label = "llm"
            else:
                raw = strategy.ga_fill(
                    pop, state["offspring"], mutation_rate=state["mutation_rate"], seed=seed
                )
                proposer_label = "graph_ga"
        return {"proposed": raw, "_proposer": proposer_label, "gen_span_id": gen_span_id}
```

> Note: the LLM span carries the static call params (model, n, temperature, seed). Token/cost metadata rides slice 05 with the `RunCost` ledger — flagged here intentionally; it is a small, deliberate trim from the design's metadata list, not a gap.

You may now drop the now-unused `from capychem.oracle import propose_offspring` import from `graph.py` **only if** no other node references it (the `score` node still imports `score_batch_async` from `oracle`; `propose_offspring` is now reached via `strategy`). Keep `score_batch_async`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_loop_propose.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Regression check** — the Graph-GA path must be unchanged:

Run: `uv run pytest packages/core/tests/test_loop_cost.py packages/core/tests/test_loop_logic.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/loop/graph.py packages/core/tests/test_loop_propose.py
git commit -m "feat(loop): strategy-aware propose node with LLM span"
```

---

### Task 5: Fallback node + topology + score merge + persist provenance

**Files:**
- Modify: `packages/core/capychem/loop/graph.py` (new `fallback` node, `score`, `_persist`, `build_graph`)
- Modify: `apps/api/capychem/api/runner.py` + `packages/core/capychem/cli.py` (recursion-limit comment/headroom)
- Modify: `packages/core/capychem/db/models.py` (comment-only: extend the `proposer_used`/`proposer` value list)
- Test: `packages/core/tests/test_loop_fallback.py` (**create**)

**Interfaces:**
- Consumes: `strategy.fallback_fill`, `state["validated"]`, `state["_proposer"]`, `state["population"]`, `state["offspring"]`.
- Produces: `fallback` returns `{}` (no-op) or `{"_fallback_validated": list[ValidCandidate], "_proposer": "mixed"}`. `score` reads `state["validated"] + state.get("_fallback_validated", [])`. `_persist` writes `Candidate.proposer = vc.proposer` per candidate and `Generation.proposer_used = state["_proposer"]`.

- [ ] **Step 1: Write the failing tests** — create `packages/core/tests/test_loop_fallback.py`:

```python
"""The fallback node backfills invalid LLM output with Graph-GA (slice 04, FR-005)."""

from __future__ import annotations

from typing import Any

import pytest
from capychem.db.models import Base, Candidate, Generation
from capychem.loop import graph as graph_mod
from capychem.loop.state import Scored
from capychem.validate import ValidCandidate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _state(proposer: str, validated: list[ValidCandidate]) -> dict[str, Any]:
    return {
        "_proposer": proposer,
        "validated": validated,
        "offspring": 4,
        "mutation_rate": 0.01,
        "seed": 42,
        "gen_index": 1,
        "population": [Scored(smiles="CCO", score=0.9), Scored(smiles="CCN", score=0.4)],
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_fallback_backfills_gap_for_llm(monkeypatch) -> None:
    # 1 valid LLM candidate, offspring target 4 -> fill 3 from GA.
    monkeypatch.setattr(
        graph_mod.strategy, "fallback_fill",
        lambda validated, pop, *, target, mutation_rate, seed: [
            ValidCandidate(smiles=s, parents=(0, 1), proposer="graph_ga") for s in ("CCC", "CCCC", "CCCCC")
        ],
    )
    out = await graph_mod.fallback(_state("llm", [ValidCandidate("CCO", None, "llm")]))  # type: ignore[arg-type]
    assert len(out["_fallback_validated"]) == 3
    assert out["_proposer"] == "mixed"


async def test_fallback_is_noop_for_graph_ga() -> None:
    out = await graph_mod.fallback(_state("graph_ga", [ValidCandidate("CCC", (0, 1))]))  # type: ignore[arg-type]
    assert out == {}


async def test_fallback_is_noop_when_llm_batch_full(monkeypatch) -> None:
    full = [ValidCandidate(f"C{'C' * i}", None, "llm") for i in range(4)]
    out = await graph_mod.fallback(_state("llm", full))  # type: ignore[arg-type]
    assert out == {}


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_persist_records_per_candidate_proposer(sm) -> None:
    from capychem.db.models import Run

    async with sm() as s:
        run = Run(
            task="qed", budget=10, mutation_strategy="llm", plateau_window=2,
            pop_size=4, offspring=4, mutation_rate=0.01, seed=42, status="running",
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    state: dict[str, Any] = {
        "run_id": run_id,
        "gen_index": 1,
        "_proposer": "mixed",
        "_scored": [
            (ValidCandidate("CCO", None, "llm"), 0.8, 0.0),
            (ValidCandidate("CCC", (0, 1), "graph_ga"), 0.6, 0.0),
        ],
        "population": [],
        "pop_size": 4,
        "task": "qed",
        "calls_used": 2,
        "auc_curve": [],
        "run_trace_id": None,
        "gen_span_id": None,
    }
    await graph_mod._persist(state, sm)  # type: ignore[arg-type]
    async with sm() as s:
        gen = (await s.execute(select(Generation))).scalars().one()
        cands = (await s.execute(select(Candidate).order_by(Candidate.smiles))).scalars().all()
    assert gen.proposer_used == "mixed"
    assert {c.proposer for c in cands} == {"llm", "graph_ga"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_fallback.py -v`
Expected: FAIL — `graph_mod.fallback` does not exist; persist still writes `state["_proposer"]` per candidate.

- [ ] **Step 3: Add the `fallback` node** in `packages/core/capychem/loop/graph.py` (after the `validate` node):

```python
async def fallback(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:fallback",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        if state.get("_proposer") != "llm":
            return {}
        validated = state["validated"]
        pop = [(m.smiles, m.score) for m in state["population"]]
        fillers = strategy.fallback_fill(
            validated,
            pop,
            target=state["offspring"],
            mutation_rate=state["mutation_rate"],
            seed=state["seed"] + state["gen_index"],
        )
        if not fillers:
            return {}
        return {"_fallback_validated": fillers, "_proposer": "mixed"}
```

- [ ] **Step 4: Merge fallback fillers in the `score` node** — change the `batch` line in `score`:

```python
        candidates = [*state["validated"], *state.get("_fallback_validated", [])]
        batch = trim_to_budget(
            candidates, budget=state["budget"], calls_used=state["calls_used"]
        )
```

- [ ] **Step 5: Per-candidate proposer in `_persist`** — change the `Candidate(...)` construction to read `vc.proposer`:

```python
                cand = Candidate(
                    generation_id=gen.id,
                    smiles=vc.smiles,
                    parent_candidate_id=parent_cid,
                    proposer=vc.proposer,
                    valid=True,
                    score=sc,
                )
```

(`Generation(..., proposer_used=state["_proposer"])` is unchanged — it is now `"mixed"` after a fallback.)

- [ ] **Step 6: Insert the node into the graph** — in `build_graph`, add the node and rewire the edge:

```python
    builder.add_node("propose", propose)
    builder.add_node("validate", validate)
    builder.add_node("fallback", fallback)
    builder.add_node("score", score)
    builder.add_node("persist", persist)
    builder.add_node("stop_check", stop_check)
    builder.set_entry_point("propose")
    builder.add_edge("propose", "validate")
    builder.add_edge("validate", "fallback")
    builder.add_edge("fallback", "score")
    builder.add_edge("score", "persist")
    builder.add_edge("persist", "stop_check")
    builder.add_conditional_edges("stop_check", _route, {"continue": "propose", "stop": END})
```

- [ ] **Step 7: Bump recursion-limit headroom for the added node** — in `apps/api/capychem/api/runner.py` and `packages/core/capychem/cli.py`, change both occurrences:

```python
        # Each generation is 6 node-steps; allow headroom over the cap.
        recursion_limit = cfg.max_generations * 7 + 10
```
(in `cli.py` the variable is `args.max_generations`.)

- [ ] **Step 8: Update the model comments** (comment-only) in `packages/core/capychem/db/models.py`:

```python
    proposer_used: Mapped[str] = mapped_column(String(16))  # "starting" | "graph_ga" | "llm" | "mixed"
```
```python
    proposer: Mapped[str] = mapped_column(String(16))  # "starting" | "graph_ga" | "llm"
```

- [ ] **Step 9: Run the tests**

Run: `uv run pytest packages/core/tests/test_loop_fallback.py packages/core/tests/test_loop_cost.py -v`
Expected: PASS (fallback tests + the Graph-GA cost regression).

- [ ] **Step 10: Commit**

```bash
git add packages/core/capychem/loop/graph.py apps/api/capychem/api/runner.py packages/core/capychem/cli.py packages/core/capychem/db/models.py packages/core/tests/test_loop_fallback.py
git commit -m "feat(loop): Graph-GA fallback node + per-candidate provenance (FR-005)"
```

---

### Task 6: Valid-SMILES gate (helper + summary + CLI verdict)

**Files:**
- Modify: `packages/core/capychem/loop/logic.py` (`valid_smiles_gate`, `build_summary`)
- Modify: `packages/core/capychem/cli.py` (print verdict)
- Test: `packages/core/tests/test_loop_logic.py` (add cases)

**Interfaces:**
- Produces: `valid_smiles_gate(rate: float, threshold: float = VALID_SMILES_THRESHOLD) -> dict[str, Any]` returning `{"threshold", "passed"}`. `build_summary` embeds it at `summary["valid_smiles"]["gate"]`. `VALID_SMILES_THRESHOLD = 0.80`.

- [ ] **Step 1: Write the failing tests** — append to `packages/core/tests/test_loop_logic.py`:

```python
from capychem.loop.logic import build_summary, valid_smiles_gate
from capychem.loop.state import Scored


def test_valid_smiles_gate_pass_and_fail() -> None:
    assert valid_smiles_gate(0.85)["passed"] is True
    assert valid_smiles_gate(0.80)["passed"] is True
    assert valid_smiles_gate(0.79)["passed"] is False
    assert valid_smiles_gate(0.85)["threshold"] == 0.80


def test_build_summary_embeds_gate() -> None:
    summary = build_summary(
        [Scored(smiles="CCO", score=0.9)],
        [(1, 0.9)],
        generations=1,
        oracle_calls=1,
        validation_stats={"proposed": 10, "valid": 9},
    )
    assert summary["valid_smiles"]["rate"] == 0.9
    assert summary["valid_smiles"]["gate"] == {"threshold": 0.80, "passed": True}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -v`
Expected: FAIL — `valid_smiles_gate` undefined; `gate` key missing.

- [ ] **Step 3: Implement** — in `packages/core/capychem/loop/logic.py`, add the constant + helper near the top:

```python
VALID_SMILES_THRESHOLD = 0.80


def valid_smiles_gate(rate: float, threshold: float = VALID_SMILES_THRESHOLD) -> dict[str, Any]:
    """The milestone-02 >80% valid-SMILES gate. Observational: it reports a verdict,
    it never halts a run (the Graph-GA fallback guarantees throughput)."""
    return {"threshold": threshold, "passed": rate >= threshold}
```

In `build_summary`, inside the `if validation_stats is not None:` block, embed the gate:

```python
        rate = valid / proposed if proposed else 0.0
        summary["valid_smiles"] = {
            "proposed": proposed,
            "valid": valid,
            "rate": rate,
            "gate": valid_smiles_gate(rate),
        }
```

- [ ] **Step 4: Print the verdict in the CLI** — in `packages/core/capychem/cli.py` `main`, extend the `valid_smiles` print block:

```python
    vs = summary.get("valid_smiles")
    if vs:
        print(f"  valid SMILES: {vs['rate']:.1%} ({vs['valid']}/{vs['proposed']} parseable)")
        gate = vs.get("gate")
        if gate:
            verdict = "PASS" if gate["passed"] else "FAIL"
            print(f"  valid-SMILES gate (>= {gate['threshold']:.0%}): {verdict}")
```

- [ ] **Step 5: Run the tests** (and the broader logic suite — an existing test may assert the exact `valid_smiles` dict shape; if so, update it to include the `gate` key)

Run: `uv run pytest packages/core/tests/test_loop_logic.py -v`
Expected: PASS. If a pre-existing test fails on the new `gate` key, add `"gate": {"threshold": 0.80, "passed": <expected>}` to its expected dict and re-run.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/loop/logic.py packages/core/capychem/cli.py packages/core/tests/test_loop_logic.py
git commit -m "feat(loop): observational >80% valid-SMILES gate in summary + CLI"
```

---

### Task 7: Headless LLM path (`run_reproduction` + eval CLI)

**Files:**
- Modify: `packages/core/capychem/eval/runner.py`
- Modify: `packages/core/capychem/eval/cli.py`
- Test: `packages/core/tests/test_eval_runner.py` (add a case)

**Interfaces:**
- Consumes: `strategy.propose_llm_sync`, `strategy.fallback_fill` (imported into `runner.py` namespace so tests can monkeypatch them), `validate_batch`.
- Produces: `run_reproduction(task, budget, seed, *, pop_size=120, offspring=70, mutation_rate=0.067, patience=5, freq_log=100, mutation_strategy="graph_ga") -> ReproResult`. The eval CLI gains `--mutation-strategy`.

- [ ] **Step 1: Write the failing test** — append to `packages/core/tests/test_eval_runner.py`:

```python
def test_llm_strategy_runs_to_budget_on_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # LLM path, harness-free: stub the LLM proposer + the oracle; no fallback fires
    # because the LLM returns valid SMILES.
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]

    def fake_llm_sync(task, population, *, n, seed):
        return [ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                               tokens_in=0, tokens_out=0) for i in range(n)]

    def fake_score(smiles, task, **kw):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction("qed", budget=5, seed=42, pop_size=3, offspring=4,
                           patience=2, mutation_strategy="llm")
    assert res.unique_calls == len(res.mol_buffer)
    assert res.mol_buffer  # produced + scored candidates via the LLM path
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_runner.py::test_llm_strategy_runs_to_budget_on_stub -v`
Expected: FAIL — `run_reproduction` has no `mutation_strategy` parameter / `propose_llm_sync` not importable in `runner_mod`.

- [ ] **Step 3: Implement the LLM branch** — in `packages/core/capychem/eval/runner.py`, add imports:

```python
from capychem.loop.strategy import fallback_fill, ga_fill, propose_llm_sync
from capychem.validate import ValidCandidate
```

Add `mutation_strategy: str = "graph_ga"` to the `run_reproduction` signature (last keyword param). Replace the offspring-generation lines inside the `while` loop:

```python
        pop_pairs = [(s.smiles, s.score) for s in population]
        if mutation_strategy == "llm":
            results = propose_llm_sync(task, pop_pairs, offspring, seed=seed + generations) \
                if False else propose_llm_sync(task, pop_pairs, n=offspring, seed=seed + generations)
            valid_llm = validate_batch([(r.smiles, None) for r in results])
            fillers = fallback_fill(
                valid_llm, pop_pairs, target=offspring,
                mutation_rate=mutation_rate, seed=seed + generations,
            )
            valid = [*valid_llm, *fillers]
        else:
            offs = ga_fill(pop_pairs, offspring, mutation_rate=mutation_rate, seed=seed + generations)
            valid = validate_batch(offs)
        new_scored = score_unique([c.smiles for c in valid])
        population = merge_and_truncate(population, _as_scored(new_scored), pop_size=pop_size)
        generations += 1
```

> Clean up the `if False else` scaffolding — write the single line: `results = propose_llm_sync(task, pop_pairs, n=offspring, seed=seed + generations)`.

> The gen-0 seed block and patience block are unchanged. The `graph_ga` branch now routes through `strategy.ga_fill` (identical args to the previous direct `propose_offspring` call) — the existing harness-backed and monkeypatched tests still pass because they patch `runner_mod.propose_offspring`, which `ga_fill` calls. If the monkeypatched tests patch `runner_mod.propose_offspring` and `ga_fill` imports `propose_offspring` from `oracle`, the patch must target where it is *looked up*: keep `from capychem.oracle import propose_offspring` in `runner.py` AND have the `graph_ga` branch call `propose_offspring` directly (not via `ga_fill`) so existing patches keep working. Use this for the `graph_ga` branch instead:

```python
        else:
            offs = propose_offspring(pop_pairs, offspring, mutation_rate=mutation_rate, seed=seed + generations)
            valid = validate_batch([(o.smiles, o.parents) for o in offs])
```

(So `runner.py` keeps its existing `propose_offspring` import; `ga_fill` is only used transitively inside `fallback_fill`.)

- [ ] **Step 4: Add the eval CLI flag** — in `packages/core/capychem/eval/cli.py`, add the argument and pass it through:

```python
    p.add_argument("--mutation-strategy", choices=["graph_ga", "llm"], default="graph_ga")
```

and add `mutation_strategy=args.mutation_strategy,` to the `run_reproduction(...)` call.

- [ ] **Step 5: Run the tests** (new + existing eval suite, incl. the Graph-GA regressions)

Run: `uv run pytest packages/core/tests/test_eval_runner.py -v`
Expected: PASS (new LLM case + the 2 monkeypatched + the real-harness smoke). The real-harness smoke needs the `harness` fixture/env; if unavailable locally it is skipped/xfail per existing conftest behavior.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/runner.py packages/core/capychem/eval/cli.py packages/core/tests/test_eval_runner.py
git commit -m "feat(eval): LLM proposer + Graph-GA fallback reachable headless (G6)"
```

---

### Task 8: End-to-end LLM product run on stub + full quality gate (capstone)

**Files:**
- Test: `packages/core/tests/test_loop_llm_e2e.py` (**create**)
- No production code (verification + gate task).

**Interfaces:**
- Consumes: everything above. Exercises `build_graph` → `ainvoke` with `mutation_strategy="llm"` on the stub backend (no network, no harness because the all-valid stub fires no fallback).

- [ ] **Step 1: Write the e2e test** — create `packages/core/tests/test_loop_llm_e2e.py`:

```python
"""End-to-end: a mutation_strategy='llm' run completes on the stub backend (slice 04)."""

from __future__ import annotations

import pytest
from capychem.db.models import Base, Candidate, Generation
from capychem.loop import graph as graph_mod
from capychem.loop.state import LoopState
from capychem.oracle import OracleResult
from capychem.run import RunConfig, create_run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_llm_run_completes_end_to_end(sm, monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")  # network-free, all-valid

    async def fake_score(smiles, task):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    cfg = RunConfig(
        task="qed", budget=50, seed=42, pop_size=6, offspring=4,
        mutation_rate=0.01, plateau_window=3, max_generations=2,
        mutation_strategy="llm",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    initial: LoopState = {
        "run_id": run_id, "task": cfg.task, "budget": cfg.budget, "seed": cfg.seed,
        "pop_size": cfg.pop_size, "offspring": cfg.offspring, "mutation_rate": cfg.mutation_rate,
        "plateau_window": cfg.plateau_window, "max_generations": cfg.max_generations,
        "mutation_strategy": "llm", "calls_used": 0, "gen_index": 0, "population": [],
        "run_trace_id": None, "gen_span_id": None, "auc_curve": [], "done": False,
    }
    final = await g.ainvoke(initial, config={"recursion_limit": 40})

    # 1. Completed end-to-end with a summary.
    assert final["done"] is True
    assert final["summary"]["generations"] >= 1
    # 2. valid_smiles + gate present (gen 1 ran the LLM; stub pool is all valid -> PASS).
    gate = final["summary"]["valid_smiles"]["gate"]
    assert gate["passed"] is True
    # 3. Provenance: a generation produced by the LLM is recorded as such.
    async with sm() as s:
        gens = (await s.execute(select(Generation.proposer_used))).scalars().all()
        cand_proposers = set((await s.execute(select(Candidate.proposer))).scalars().all())
    assert "llm" in gens
    assert "llm" in cand_proposers
```

- [ ] **Step 2: Run the e2e test**

Run: `uv run pytest packages/core/tests/test_loop_llm_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Full test suite**

Run: `uv run pytest`
Expected: PASS — all tests green (existing + new). Investigate and fix any regression before proceeding.

- [ ] **Step 4: Type-check (strict)**

Run: `uv run mypy -p capychem -p capychem.api`
Expected: no errors.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean. (Run `uv run ruff format .` then re-stage if formatting changed files.)

- [ ] **Step 6: Frontend typecheck/lint (unchanged surface — sanity only if web touched)**

Skip unless the web app was modified (it was not in this slice).

- [ ] **Step 7: Commit**

```bash
git add packages/core/tests/test_loop_llm_e2e.py
git commit -m "test(loop): end-to-end mutation_strategy=llm run on stub backend"
```

---

## Self-Review

**1. Spec coverage** (each design section → task):
- Proposer abstraction selected by `mutation_strategy`, reachable from product loop + headless eval → Tasks 2, 3, 4, 7. ✓
- LLM proposer wired into propose node → Task 4. ✓
- Invalid LLM → Graph-GA fallback, no starved generation (FR-005) → Tasks 2 (`fallback_fill`), 5 (node). ✓
- Pinned determinism (temperature constant, seed = run_seed + gen_index, G6) → Task 2 (`LLM_TEMPERATURE`), Tasks 4 + 7 (seed). ✓
- >80% valid-SMILES gate reading `valid_smiles.rate`, observe-only → Task 6. ✓ Gate honesty (LLM-only stat) is structural: `_validation_stats` is computed only from `proposed` (Task 1/4 keep fillers out of `proposed`); verified by Task 8's PASS + Task 5's no-op-for-graph_ga.
- Per-candidate provenance + `Generation.proposer_used="mixed"` → Tasks 1, 5. ✓
- LLM-call Langfuse span → Task 4. ✓ (static metadata; token/cost deferred to slice 05 — flagged).
- Threading launch → RunConfig → LoopState (+ API schema, CLIs) → Task 3, 7. ✓
- Async/sync bridge headless → Task 2 (`propose_llm_sync`), Task 7. ✓
- End-to-end LLM run (done-bar #1) → Task 8. ✓
- Out-of-scope items (cost ledger, analyzer, jnk3 launch, real run, retries) → not implemented, per Global Constraints. ✓

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to". The only `if False else` appears as scaffolding I explicitly instruct to delete in Task 7 Step 3 (replaced with the single real line). All code blocks are complete.

**3. Type consistency:** `ValidCandidate(smiles, parents, proposer="graph_ga")` used identically in Tasks 1, 2, 5, 8. `propose_llm_async`/`propose_llm_sync` keyword-only `n`, `seed` consistent across Tasks 2, 4, 7. `fallback_fill(validated, population, *, target, mutation_rate, seed)` consistent Tasks 2, 5, 7. `valid_smiles_gate(rate, threshold)` consistent Tasks 6, 8 (`summary["valid_smiles"]["gate"]` shape `{"threshold","passed"}`). `run_reproduction(..., mutation_strategy="graph_ga")` consistent Tasks 7. `RunConfig.mutation_strategy` / `LoopState["mutation_strategy"]` / `CreateRunRequest.mutation_strategy` consistent Task 3.
