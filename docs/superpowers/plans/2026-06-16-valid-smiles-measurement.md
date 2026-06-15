# Valid-SMILES Measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure a per-run valid-SMILES rate (RDKit parse-validity) in the loop's `validate` node, accumulate it across generations, persist it in `summary_json`, and print it from the CLI.

**Architecture:** Add a stats-returning sibling to `validate_batch` that counts parse-validity *before* dedup. Thread a cumulative `{"proposed","valid"}` counter through `LoopState` (mirroring the `auc_curve` accumulation idiom), emit a stable `valid_smiles` block from `build_summary`, and print it in the CLI. No DB migration, no API/web changes. Measurement only — the >80% gate check is milestone 02.

**Tech Stack:** Python 3.12, RDKit (via `capychem.validate`), LangGraph, pytest (async via conftest), mypy strict, ruff.

**Reference design:** `docs/superpowers/specs/2026-06-16-valid-smiles-measurement-design.md`

---

### Task 1: Parse-validity stats in `validate.py`

**Files:**
- Modify: `packages/core/capychem/validate.py`
- Test: `packages/core/tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

Add to `packages/core/tests/test_validate.py`. First update the import line at the top:

```python
from capychem.validate import (
    ValidCandidate,
    ValidationStats,
    canonicalize,
    validate_batch,
    validate_batch_with_stats,
)
```

Then append these tests:

```python
def test_validate_batch_with_stats_counts_parse_validity_before_dedup() -> None:
    batch = [
        ("CCO", (0, 1)),
        ("OCC", (2, 3)),  # duplicate of CCO by canonical form — still parse-valid
        ("not_a_smiles", None),  # invalid — not counted as valid
        ("c1ccccc1", None),
    ]
    out, stats = validate_batch_with_stats(batch)
    # dedup still applies to the returned list (unchanged validate_batch behavior)
    assert [c.smiles for c in out] == [canonicalize("CCO"), canonicalize("c1ccccc1")]
    # but the duplicate counts as VALID: 3 parseable of 4 proposed
    assert stats.proposed == 4
    assert stats.valid == 3
    assert stats.rate == 0.75


def test_validation_stats_rate_zero_on_empty_batch() -> None:
    out, stats = validate_batch_with_stats([])
    assert out == []
    assert stats.proposed == 0 and stats.valid == 0
    assert stats.rate == 0.0  # no division-by-zero


def test_validate_batch_with_stats_all_invalid() -> None:
    out, stats = validate_batch_with_stats([("xxx", None), ("yyy", None)])
    assert out == []
    assert stats.proposed == 2 and stats.valid == 0
    assert stats.rate == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_validate.py -x`
Expected: FAIL — `ImportError: cannot import name 'ValidationStats'` / `validate_batch_with_stats`.

- [ ] **Step 3: Implement `ValidationStats` + `validate_batch_with_stats`, refactor `validate_batch` to delegate**

In `packages/core/capychem/validate.py`, add `ValidationStats` after the `ValidCandidate` dataclass (after line 27):

```python
@dataclass(frozen=True)
class ValidationStats:
    """Per-batch parse-validity counts.

    ``valid`` counts RDKit-parseable inputs BEFORE intra-batch dedup, so ``rate``
    measures validity (can RDKit parse it), not novelty. This is the per-run
    valid-SMILES signal milestone 02's >80% gate compares against.
    """

    proposed: int
    valid: int

    @property
    def rate(self) -> float:
        return self.valid / self.proposed if self.proposed else 0.0
```

Then replace the current `validate_batch` (lines 38-55) with a stats-returning core plus a thin delegating wrapper:

```python
def validate_batch_with_stats(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> tuple[list[ValidCandidate], ValidationStats]:
    """Like :func:`validate_batch`, but also report parse-validity stats.

    ``valid`` is incremented for every RDKit-parseable input, before the dedup
    filter — so a repeated-but-valid molecule still counts as valid.
    """
    seen: set[str] = set()
    out: list[ValidCandidate] = []
    valid = 0
    for raw, parents in candidates:
        canon = canonicalize(raw)
        if canon is None:
            continue
        valid += 1
        if canon in seen:
            continue
        seen.add(canon)
        out.append(ValidCandidate(smiles=canon, parents=parents))
    return out, ValidationStats(proposed=len(candidates), valid=valid)


def validate_batch(
    candidates: list[tuple[str, tuple[int, int] | None]],
) -> list[ValidCandidate]:
    """Canonicalize, drop invalid, collapse intra-batch duplicates.

    ``candidates`` is a list of (raw_smiles, parents) pairs. The first occurrence
    of each canonical form wins (keeping its provenance). Input order is
    preserved — deterministic for G6.
    """
    out, _ = validate_batch_with_stats(candidates)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_validate.py -v`
Expected: PASS — all existing tests (delegation preserves behavior) + 3 new tests.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/validate.py packages/core/tests/test_validate.py
git commit -m "feat(validate): parse-validity stats seam (validate_batch_with_stats)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `build_summary` emits a stable `valid_smiles` block

**Files:**
- Modify: `packages/core/capychem/loop/logic.py:56-73`
- Test: `packages/core/tests/test_loop_logic.py`

- [ ] **Step 1: Write the failing tests**

Append to `packages/core/tests/test_loop_logic.py`:

```python
def test_build_summary_includes_valid_smiles_when_stats_given() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(
        pop,
        [(10, 0.9)],
        generations=1,
        oracle_calls=10,
        validation_stats={"proposed": 40, "valid": 38},
    )
    assert summary["valid_smiles"] == {"proposed": 40, "valid": 38, "rate": 38 / 40}


def test_build_summary_valid_smiles_rate_zero_when_no_proposals() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(
        pop, [(10, 0.9)], generations=1, oracle_calls=10,
        validation_stats={"proposed": 0, "valid": 0},
    )
    assert summary["valid_smiles"] == {"proposed": 0, "valid": 0, "rate": 0.0}


def test_build_summary_omits_valid_smiles_when_stats_absent() -> None:
    pop = [s("c1ccccc1", 0.9, 3)]
    summary = build_summary(pop, [(10, 0.9)], generations=1, oracle_calls=10)
    assert "valid_smiles" not in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -x`
Expected: FAIL — `TypeError: build_summary() got an unexpected keyword argument 'validation_stats'`.

- [ ] **Step 3: Add the `validation_stats` kwarg to `build_summary`**

Replace `build_summary` in `packages/core/capychem/loop/logic.py` (lines 56-73) with:

```python
def build_summary(
    population: list[Scored],
    auc_curve: list[tuple[int, float]],
    *,
    generations: int,
    oracle_calls: int,
    validation_stats: dict[str, int] | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """Build the (un-authoritative) summary_json. The auc_curve here is the
    running top-10-mean; the canonical AUC lives in packages/core/eval (later
    milestone) — do not treat this as the G1 number.

    When ``validation_stats`` (cumulative {"proposed","valid"}) is supplied, a
    stable ``valid_smiles`` block is added. This is the field milestone 02's
    >80% gate reads; keep its shape stable.
    """
    top = sorted(population, key=_sort_key)[:top_k]
    summary: dict[str, Any] = {
        "top_k": [{"smiles": m.smiles, "score": m.score} for m in top],
        "auc_curve": [{"oracle_calls": c, "top10_mean": v} for c, v in auc_curve],
        "generations": generations,
        "oracle_calls": oracle_calls,
    }
    if validation_stats is not None:
        proposed = validation_stats.get("proposed", 0)
        valid = validation_stats.get("valid", 0)
        summary["valid_smiles"] = {
            "proposed": proposed,
            "valid": valid,
            "rate": valid / proposed if proposed else 0.0,
        }
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -v`
Expected: PASS — existing `test_build_summary_shape` (stats absent → no `valid_smiles`) + 3 new tests.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/logic.py packages/core/tests/test_loop_logic.py
git commit -m "feat(loop): build_summary emits stable valid_smiles block

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Accumulate stats in the `validate` node

**Files:**
- Modify: `packages/core/capychem/loop/state.py:48` (add field)
- Modify: `packages/core/capychem/loop/graph.py:24` (import) and `:61-67` (node)
- Test: `packages/core/tests/test_validate_node.py` (create)

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_validate_node.py`:

```python
"""The validate node accumulates per-run parse-validity stats across generations.

trace.span() no-ops without LANGFUSE_* keys, so this needs no Langfuse. The node
is async; the test runner runs `async def` tests directly (see conftest).
"""

from __future__ import annotations

from typing import Any

from capychem.loop.graph import validate


async def test_validate_node_accumulates_stats_across_generations() -> None:
    proposed = [("CCO", None), ("OCC", None), ("not_a_smiles", None)]  # 2 valid of 3
    state: dict[str, Any] = {
        "proposed": proposed,
        "run_trace_id": None,
        "gen_span_id": None,
    }
    out1 = await validate(state)  # type: ignore[arg-type]
    assert out1["_validation_stats"] == {"proposed": 3, "valid": 2}
    assert len(out1["validated"]) == 2  # dedup: OCC == CCO

    # Simulate LangGraph merging the prior stats back into state for gen 2.
    state2: dict[str, Any] = {**state, "_validation_stats": out1["_validation_stats"]}
    out2 = await validate(state2)  # type: ignore[arg-type]
    assert out2["_validation_stats"] == {"proposed": 6, "valid": 4}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_validate_node.py -x`
Expected: FAIL — `KeyError: '_validation_stats'` (node does not return it yet).

- [ ] **Step 3a: Declare the state field**

In `packages/core/capychem/loop/state.py`, add after line 48 (`validated: ...`):

```python
    _validation_stats: dict[str, int]  # cumulative {"proposed","valid"} across gens
```

- [ ] **Step 3b: Switch the import in `graph.py`**

In `packages/core/capychem/loop/graph.py` line 24, change:

```python
from capychem.validate import validate_batch
```
to:
```python
from capychem.validate import validate_batch_with_stats
```

- [ ] **Step 3c: Accumulate in the `validate` node**

Replace the `validate` node body in `packages/core/capychem/loop/graph.py` (lines 61-67) with:

```python
async def validate(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:validate",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        validated, stats = validate_batch_with_stats(state["proposed"])
        prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
        return {
            "validated": validated,
            "_validation_stats": {
                "proposed": prev["proposed"] + stats.proposed,
                "valid": prev["valid"] + stats.valid,
            },
        }
```

(No driver needs to seed `_validation_stats`: the `state.get(..., {0,0})` default initializes it on the first generation, the same way `auc_curve` is read with a default in the persist node.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_validate_node.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/graph.py packages/core/tests/test_validate_node.py
git commit -m "feat(loop): accumulate per-run valid-SMILES stats in validate node

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire stats into the final summary + in-suite integration guard

**Files:**
- Modify: `packages/core/capychem/loop/graph.py:168-173` (stop_check passes stats)
- Test: `packages/core/tests/test_loop_valid_smiles.py` (create)

- [ ] **Step 1: Write the failing integration test**

Create `packages/core/tests/test_loop_valid_smiles.py` (mirrors `test_loop_cost.py`'s fake-scorer mini-run — no harness needed):

```python
"""The loop persists a per-run valid_smiles block in summary_json.

Drives the real graph with a fake scorer (no harness). Graph-GA / starting-pop
SMILES are all RDKit-valid, so the measured rate is 1.0 — the deliverable is the
plumbing, not the number.
"""

from __future__ import annotations

import pytest
from capychem.db.models import Base
from capychem.loop import graph as graph_mod
from capychem.loop.state import LoopState
from capychem.oracle import OracleResult
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_summary_has_valid_smiles_block(sm, monkeypatch):
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed", budget=4, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=2, max_generations=1,
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    initial: LoopState = {
        "run_id": run_id, "task": cfg.task, "budget": cfg.budget, "seed": cfg.seed,
        "pop_size": cfg.pop_size, "offspring": cfg.offspring,
        "mutation_rate": cfg.mutation_rate, "plateau_window": cfg.plateau_window,
        "max_generations": cfg.max_generations, "calls_used": 0, "gen_index": 0,
        "population": [], "run_trace_id": None, "gen_span_id": None,
        "auc_curve": [], "done": False,
    }
    final = await g.ainvoke(initial, config={"recursion_limit": 30})
    vs = final["summary"]["valid_smiles"]
    assert vs["proposed"] >= vs["valid"] > 0
    assert vs["rate"] == 1.0  # starting-pop SMILES are all valid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_valid_smiles.py -x`
Expected: FAIL — `KeyError: 'valid_smiles'` (stop_check does not pass `validation_stats` yet).

- [ ] **Step 3: Pass `validation_stats` from `stop_check`**

In `packages/core/capychem/loop/graph.py`, in the `build_summary(...)` call inside `stop_check` (lines 168-173), add the `validation_stats` argument:

```python
            summary = build_summary(
                state["population"],
                state.get("auc_curve", []),
                generations=state["gen_index"] + 1,
                oracle_calls=state["calls_used"],
                validation_stats=state.get("_validation_stats"),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_loop_valid_smiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/graph.py packages/core/tests/test_loop_valid_smiles.py
git commit -m "feat(loop): persist valid_smiles block via stop_check summary

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Surface the rate in the CLI

**Files:**
- Modify: `packages/core/capychem/cli.py:117-118` (print block)

- [ ] **Step 1: Add the print line**

In `packages/core/capychem/cli.py`, in `main()`, after the `oracle calls used` line (currently line 118) and before `print("  top molecules:")`, add:

```python
    vs = summary.get("valid_smiles")
    if vs:
        print(
            f"  valid SMILES: {vs['rate']:.1%} "
            f"({vs['valid']}/{vs['proposed']} parseable)"
        )
```

(No unit test — this is a print-formatting line, verified by the real Graph-GA run in the verification step. `summary.get(...)` keeps it safe if the block is ever absent.)

- [ ] **Step 2: Verify the full suite + static checks are green**

Run:
```bash
uv run pytest
uv run mypy -p capychem -p capychem.api
uv run ruff check .
```
Expected: all PASS (pytest all green, mypy clean, ruff clean).

- [ ] **Step 3: Commit**

```bash
git add packages/core/capychem/cli.py
git commit -m "feat(cli): print per-run valid-SMILES rate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Verification (post-implementation, before ship)

- [ ] Full suite green: `uv run pytest` (paste real output).
- [ ] Types: `uv run mypy -p capychem -p capychem.api` (paste real output).
- [ ] Lint: `uv run ruff check .` (paste real output).
- [ ] **Exercise on a real Graph-GA run** (local harness; `CAPYCHEM_ORACLE_BACKEND` unset):
  `uv run capychem-run --task qed --budget 200 --seed 42`
  Record the printed `valid SMILES: <rate> (<valid>/<proposed> parseable)` line as evidence. Expect ~100% (deterministic graph edits). The plumbing is the deliverable, not the number.
- [ ] One fresh-context review (superpowers:requesting-code-review) over the slice diff.

## Self-review (plan vs spec)

- **Spec coverage:** parse-validity semantics → Task 1; summary_json storage → Tasks 2+4; per-run cumulative + raw counts → Tasks 3+2; headless surfacing (summary_json + CLI) → Tasks 4+5. All four approved decisions covered.
- **Placeholders:** none — every code step shows complete code.
- **Type consistency:** `ValidationStats(proposed, valid, .rate)`, `validate_batch_with_stats -> tuple[list[ValidCandidate], ValidationStats]`, state field `_validation_stats: dict[str, int]`, `build_summary(..., validation_stats: dict[str, int] | None = None)`, summary block `{"proposed","valid","rate"}` — consistent across Tasks 1-5.
- **Out of scope honored:** no >80% gate, no LLM proposer, no DB migration, no API/web, no per-generation series, no `eval/` touch, no harness import.
