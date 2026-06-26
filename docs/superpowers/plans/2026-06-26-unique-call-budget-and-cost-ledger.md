# Unique-call budget & cost ledger — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the product loop count **unique** oracle calls, populate the LLM cost ledger so `RunCost.total_usd = llm + oracle`, fire the ~$50 cost gate on LLM spend, and enrich the `llm:propose` span with token/cost.

**Architecture:** Five surgical changes across `packages/core` + `apps/api`, each TDD with its own test cycle. The product `score` node gains an in-memory `set[str]` memo (`mol_buffer`) threaded through `LoopState`, mirroring the already-memoized headless `eval/runner.py`; cross-generation repeats become cache hits (skipped, never persisted, never counted). LLM cost is accumulated in `LoopState` by the `propose` node and written to `RunCost` by the API runner, which reads `total_usd` for the gate. A non-breaking `trace._live_spans` registry lets the `llm:propose` span carry post-await token/cost.

**Tech Stack:** Python 3.12, LangGraph, SQLAlchemy 2.0 async, pytest (async), RDKit (validation only), Langfuse v2 SDK (no-op without keys), Modal (not exercised here).

## Global Constraints

- **TDD** — no production code without a failing test first. One assertion-focused test per behavior.
- **Branch:** `slice-05-unique-call-budget-cost-ledger` (already created off `main` @ `f1e9aaa`). Merge + push only when gate-green.
- **Gate-green before merge:** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .`
- **Never import from `harness/`** — subprocess+JSON only (this slice does not touch the harness boundary).
- **Wrap every LangGraph node in a Langfuse span** — preserve existing spans; `trace.*` is a no-op without `LANGFUSE_*` keys.
- **mypy strict** on changed code; **ruff** clean (no unused imports).
- **DO NOT** touch `valid_smiles` purity / `_validation_stats` / `validate.py` — that is the **slice-06 BLOCKER**, explicitly out of scope.
- **DO NOT** modify `eval/runner.py` — it already memoizes.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

- `packages/core/capychem/cost.py` — `record_oracle_cost` gains `llm_usd` (sets llm + oracle; `total = oracle + llm`).
- `packages/core/capychem/loop/trace.py` — `_live_spans` registry + `update_span()`; `span()` registers/de-registers (yield contract unchanged).
- `packages/core/capychem/loop/state.py` — `LoopState` gains `mol_buffer: set[str]` and `llm_cost_usd: float`.
- `packages/core/capychem/loop/graph.py` — `score` node memoizes unique calls; `propose` node accumulates LLM cost + wraps the `llm:propose` await.
- `apps/api/capychem/api/runner.py` — per-generation cost gate reads `total_usd` (oracle + llm).
- Tests: `packages/core/tests/test_cost.py` (+1), `test_trace.py` (+3), `test_loop_memoize.py` (new), `test_loop_propose.py` (+2), `apps/api/tests/test_cost_gate.py` (+1).

Task order respects deps: Task 5 needs Task 1 (`llm_usd`) + Task 4 (`state["llm_cost_usd"]`); Task 4 needs Task 2 (`update_span`); Task 3 is independent.

---

### Task 1: Cost recorder records LLM + oracle

**Files:**
- Modify: `packages/core/capychem/cost.py:32-41` (`record_oracle_cost`)
- Test: `packages/core/tests/test_cost.py` (append one test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `record_oracle_cost(session, run_id, oracle_usd, *, llm_usd: float = 0.0) -> RunCost` — sets `row.oracle_cost_usd`, `row.llm_cost_usd`, `row.total_usd = oracle_usd + llm_usd`. Used by Task 5.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_cost.py`:

```python
async def test_record_oracle_cost_sums_llm_and_oracle(sm):
    async with sm() as session:
        run_id = await _seed_run_with_costs(session, [])
        row = await record_oracle_cost(session, run_id, 0.4, llm_usd=0.6)
    assert row.oracle_cost_usd == pytest.approx(0.4)
    assert row.llm_cost_usd == pytest.approx(0.6)
    assert row.total_usd == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_cost.py::test_record_oracle_cost_sums_llm_and_oracle -v`
Expected: FAIL — `TypeError: record_oracle_cost() got an unexpected keyword argument 'llm_usd'`

- [ ] **Step 3: Write minimal implementation**

Replace `record_oracle_cost` in `packages/core/capychem/cost.py`:

```python
async def record_oracle_cost(
    session: AsyncSession, run_id: int, oracle_usd: float, *, llm_usd: float = 0.0
) -> RunCost:
    """Upsert the run's RunCost row with the latest oracle + llm costs.

    ``total_usd`` sums both so the ~$50 cost gate fires on LLM spend too
    (milestone 02 slice 05). ``llm_usd`` defaults to 0.0 so existing oracle-only
    callers (and the graph_ga path, where LLM cost is 0) are unchanged."""
    row = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    if row is None:
        row = RunCost(run_id=run_id)
        session.add(row)
    row.oracle_cost_usd = oracle_usd
    row.llm_cost_usd = llm_usd
    row.total_usd = oracle_usd + llm_usd
    await session.commit()
    return row
```

Also update the module docstring line "LLM cost is 0 until milestone 02." → "LLM cost is summed in from `llm_usd` (milestone 02 slice 05)."

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_cost.py -v`
Expected: PASS — the new test plus the existing `test_record_oracle_cost_upserts` (calls positionally, `llm_usd` defaults 0.0, `total_usd == 0.9`).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/cost.py packages/core/tests/test_cost.py
git commit -m "$(cat <<'EOF'
feat(cost): record llm + oracle into RunCost so total_usd sums both

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Trace `_live_spans` registry + `update_span`

**Files:**
- Modify: `packages/core/capychem/loop/trace.py` (`span()` + new `update_span`, new `_live_spans`)
- Test: `packages/core/tests/test_trace.py` (append three tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `update_span(span_id: str | None, **metadata) -> None` — no-op when disabled / `span_id is None` / id not live; else calls `_live_spans[span_id].update(metadata=metadata)`. `span()`'s yield stays `str | None`. Used by Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `packages/core/tests/test_trace.py`:

```python
def test_update_span_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    trace.update_span("anything", cost_usd=1.0)  # must not raise


def test_update_span_forwards_metadata_to_live_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    updates: list[dict[str, object]] = []

    class _Span:
        id = "span-up"

        def update(self, **kw: object) -> None:
            updates.append(kw)

        def end(self) -> None: ...

    class _Client:
        def span(self, **kw: object) -> _Span:
            return _Span()

    monkeypatch.setattr(trace, "_get_client", lambda: _Client())
    with trace.span("llm:propose", trace_id="t") as sid:
        assert sid == "span-up"
        trace.update_span(sid, tokens_in=10, cost_usd=0.5)
    assert updates == [{"metadata": {"tokens_in": 10, "cost_usd": 0.5}}]
    assert trace._live_spans == {}  # de-registered on context exit


def test_update_span_noop_for_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    trace.update_span("never-registered", cost_usd=1.0)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_trace.py::test_update_span_forwards_metadata_to_live_span -v`
Expected: FAIL — `AttributeError: module 'capychem.loop.trace' has no attribute 'update_span'`

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/loop/trace.py`, add the registry just above the `@contextmanager def span(...)` definition:

```python
# Live span handles created by ``span()``, keyed by span id, so post-await
# metadata (token/cost) can be attached via ``update_span`` before the span ends.
_live_spans: dict[str, Any] = {}
```

Replace the body of `span()` (the `if not is_enabled()` early-return stays) so the enabled branch registers and de-registers the span:

```python
    if not is_enabled():
        yield None
        return
    sp = None
    try:
        sp = _get_client().span(
            name=name,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
            metadata=metadata or None,
        )
    except Exception:  # noqa: BLE001 - tracing must never break the loop
        sp = None
    span_id = str(sp.id) if sp is not None else None
    if sp is not None and span_id is not None:
        _live_spans[span_id] = sp
    try:
        yield span_id
    finally:
        if span_id is not None:
            _live_spans.pop(span_id, None)
        if sp is not None:
            try:
                sp.end()
            except Exception:  # noqa: BLE001
                pass
```

Add `update_span` immediately after `span()`:

```python
def update_span(span_id: str | None, **metadata: Any) -> None:
    """Attach metadata to a still-open span created by ``span()``.

    No-op when Langfuse is disabled, when ``span_id`` is None, or when the span is
    no longer live (already exited). Never raises — tracing must not break the loop.
    """
    if not is_enabled() or span_id is None:
        return
    sp = _live_spans.get(span_id)
    if sp is None:
        return
    try:
        sp.update(metadata=metadata)
    except Exception:  # noqa: BLE001 - tracing must never break the loop
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_trace.py -v`
Expected: PASS — the three new tests plus all existing ones (`span()`'s yield is still `str | None`, so `test_span_yields_id_and_ends_when_enabled` and the disabled test are unchanged).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/loop/trace.py packages/core/tests/test_trace.py
git commit -m "$(cat <<'EOF'
feat(trace): add _live_spans registry + update_span for post-await metadata

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Product-loop unique-call memoization

**Files:**
- Modify: `packages/core/capychem/loop/state.py` (`LoopState` — add `mol_buffer`)
- Modify: `packages/core/capychem/loop/graph.py` (`score` node; drop orphaned `trim_to_budget` import)
- Test: `packages/core/tests/test_loop_memoize.py` (new)

**Interfaces:**
- Consumes: `OracleResult` (`capychem.oracle`), `ValidCandidate` (`capychem.validate`).
- Produces: `score` node now reads/returns `mol_buffer: set[str]`; `calls_used == len(mol_buffer)` (unique calls); `_scored` carries only newly-scored unique candidates.

- [ ] **Step 1: Write the failing tests**

Create `packages/core/tests/test_loop_memoize.py`:

```python
"""The score node memoizes by canonical SMILES so the budget counts UNIQUE calls (slice 05)."""

from __future__ import annotations

from typing import Any

from capychem.loop import graph as graph_mod
from capychem.oracle import OracleResult
from capychem.validate import ValidCandidate


def _score_state(validated: list[ValidCandidate], *, buffer: set[str], budget: int) -> dict[str, Any]:
    return {
        "validated": validated,
        "_fallback_validated": [],
        "mol_buffer": buffer,
        "budget": budget,
        "task": "qed",
        "run_trace_id": None,
        "gen_span_id": None,
    }


async def test_score_skips_cross_generation_duplicates(monkeypatch) -> None:
    scored_batches: list[list[str]] = []

    async def fake_score(smiles, task):
        scored_batches.append(list(smiles))
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state(
        [ValidCandidate("CCO", None), ValidCandidate("CCN", None), ValidCandidate("c1ccccc1", None)],
        buffer={"CCO"},  # CCO already scored by a prior generation
        budget=10,
    )
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert scored_batches == [["CCN", "c1ccccc1"]]          # CCO not sent to the oracle
    assert out["calls_used"] == 3                            # {CCO} + 2 new
    assert out["mol_buffer"] == {"CCO", "CCN", "c1ccccc1"}
    assert {c.smiles for c, _, _ in out["_scored"]} == {"CCN", "c1ccccc1"}  # cache hit not persisted


async def test_score_caps_unseen_to_unique_headroom(monkeypatch) -> None:
    scored_batches: list[list[str]] = []

    async def fake_score(smiles, task):
        scored_batches.append(list(smiles))
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state(
        [ValidCandidate("CCN", None), ValidCandidate("c1ccccc1", None), ValidCandidate("CCC", None)],
        buffer={"CCO"},   # 1 unique call already used
        budget=2,         # room = 2 - 1 = 1
    )
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert scored_batches == [["CCN"]]                       # only one unseen fits the headroom
    assert out["calls_used"] == 2
    assert out["mol_buffer"] == {"CCO", "CCN"}


async def test_score_no_headroom_scores_nothing(monkeypatch) -> None:
    async def fake_score(smiles, task):
        raise AssertionError("must not score when the unique budget is exhausted")

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    state = _score_state([ValidCandidate("CCN", None)], buffer={"CCO", "CCC"}, budget=2)
    out = await graph_mod.score(state)  # type: ignore[arg-type]
    assert out["_scored"] == []
    assert out["calls_used"] == 2
    assert out["mol_buffer"] == {"CCO", "CCC"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_loop_memoize.py -v`
Expected: FAIL — the current `score` node returns no `mol_buffer` and counts every scored call (`calls_used` and `scored_batches` assertions mismatch).

- [ ] **Step 3: Add the `mol_buffer` field to `LoopState`**

In `packages/core/capychem/loop/state.py`, inside `class LoopState`, add under the `# progress` group (next to `calls_used`):

```python
    mol_buffer: set[str]  # canonical SMILES already scored — unique-call budget memo (slice 05)
```

- [ ] **Step 4: Rewrite the `score` node**

In `packages/core/capychem/loop/graph.py`, replace the `score` function body (keep the signature + the `node:score` span) with:

```python
async def score(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:score",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        candidates = [*state["validated"], *state.get("_fallback_validated", [])]
        buffer = state.get("mol_buffer", set())
        # Cross-generation memoization (slice 05): a molecule a prior generation
        # already scored is a cache hit — not re-scored, not counted, not persisted.
        # The budget counts UNIQUE oracle calls (FR-002), unifying with eval/runner.py.
        unseen = [c for c in candidates if c.smiles not in buffer]
        room = max(state["budget"] - len(buffer), 0)  # remaining unique headroom
        batch = unseen[:room]
        if not batch:
            return {"_scored": [], "calls_used": len(buffer), "mol_buffer": buffer}
        results = await score_batch_async([c.smiles for c in batch], task=state["task"])
        scored = [
            (c, r.score, r.cost_usd)
            for c, r in zip(batch, results, strict=True)
            if r.valid and r.score is not None
        ]
        new_buffer = buffer | {c.smiles for c, _, _ in scored}
        return {
            "_scored": scored,
            "calls_used": len(new_buffer),
            "mol_buffer": new_buffer,
        }
```

Then drop the now-orphaned `trim_to_budget` from the `capychem.loop.logic` import at the top of `graph.py` (leave `build_summary, merge_and_truncate, stop_reason`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_memoize.py packages/core/tests/test_loop_cost.py packages/core/tests/test_loop_llm_e2e.py packages/core/tests/test_loop_fallback.py -v`
Expected: PASS — new memoize tests pass; the existing loop tests still pass (gen-0 seeds are distinct ZINC molecules, so no cross-gen collision turns an e2e candidate into a cache hit).

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/graph.py packages/core/tests/test_loop_memoize.py
git commit -m "$(cat <<'EOF'
feat(loop): memoize oracle calls by canonical SMILES — budget counts unique calls

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Propose-node LLM cost accumulation + `llm:propose` span enrichment

**Files:**
- Modify: `packages/core/capychem/loop/state.py` (`LoopState` — add `llm_cost_usd`)
- Modify: `packages/core/capychem/loop/graph.py` (`propose` node, llm branch + return)
- Test: `packages/core/tests/test_loop_propose.py` (append two tests + `import pytest`)

**Interfaces:**
- Consumes: `trace.update_span` (Task 2); `ProposalResult.cost_usd/tokens_in/tokens_out` (`capychem.proposer`).
- Produces: `propose` node returns `llm_cost_usd: float` (cumulative) on the llm branch only; absent on seed/graph_ga branches. Read by Task 5.

- [ ] **Step 1: Write the failing tests**

In `packages/core/tests/test_loop_propose.py`, add `import pytest` near the top, then append:

```python
async def test_propose_llm_accumulates_cost(monkeypatch) -> None:
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        return [
            ProposalResult(raw="CCO", smiles="CCO", tokens_in=5, tokens_out=3, cost_usd=0.1)
            for _ in range(n)
        ]

    monkeypatch.setattr(graph_mod.strategy, "propose_llm_async", fake_llm)
    state = _gen1_state("llm")
    state["llm_cost_usd"] = 0.25  # cost carried from a prior generation
    out = await graph_mod.propose(state)  # type: ignore[arg-type]
    # offspring=3 proposals * 0.1 each = 0.3, added to the prior 0.25.
    assert out["llm_cost_usd"] == pytest.approx(0.55)


async def test_propose_graph_ga_does_not_set_llm_cost(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_mod.strategy,
        "ga_fill",
        lambda pop, n, *, mutation_rate, seed: [("CCC", (0, 1))] * n,
    )
    out = await graph_mod.propose(_gen1_state("graph_ga"))  # type: ignore[arg-type]
    assert "llm_cost_usd" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_loop_propose.py::test_propose_llm_accumulates_cost -v`
Expected: FAIL — `KeyError: 'llm_cost_usd'` (propose does not yet emit it).

- [ ] **Step 3: Add the `llm_cost_usd` field to `LoopState`**

In `packages/core/capychem/loop/state.py`, under the `# progress` group, add:

```python
    llm_cost_usd: float  # cumulative LLM proposer spend this run (slice 05)
```

- [ ] **Step 4: Rewrite the `propose` node's llm branch + return**

In `packages/core/capychem/loop/graph.py`, in the `propose` function: initialise `gen_llm_cost = 0.0` just before the `if state["gen_index"] == 0:` branch, replace the llm branch so the await is wrapped by the `llm:propose` span and carries token/cost, and assemble the return so `llm_cost_usd` is added only on the llm branch.

The llm branch becomes:

```python
            if state.get("mutation_strategy", "graph_ga") == "llm":
                with trace.span(
                    "llm:propose",
                    trace_id=state.get("run_trace_id"),
                    parent_observation_id=gen_span_id,
                    model=proposer.llm_model(),
                    n=state["offspring"],
                    temperature=strategy.LLM_TEMPERATURE,
                    seed=seed,
                ) as llm_span_id:
                    results = await strategy.propose_llm_async(
                        state["task"], pop, n=state["offspring"], seed=seed
                    )
                    gen_llm_cost = sum(r.cost_usd for r in results)
                    trace.update_span(
                        llm_span_id,
                        tokens_in=sum(r.tokens_in for r in results),
                        tokens_out=sum(r.tokens_out for r in results),
                        cost_usd=gen_llm_cost,
                    )
                raw = [(r.smiles, None) for r in results]
                proposer_label = "llm"
```

Replace the final `return {...}` of `propose` with:

```python
        result: dict[str, Any] = {
            "proposed": raw,
            "_proposer": proposer_label,
            "gen_span_id": gen_span_id,
        }
        if proposer_label == "llm":
            result["llm_cost_usd"] = state.get("llm_cost_usd", 0.0) + gen_llm_cost
        return result
```

(`gen_llm_cost = 0.0` is initialised before the branches so mypy sees it bound on every path; the seed and graph_ga branches leave it 0.0 and never read it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_propose.py packages/core/tests/test_loop_llm_e2e.py -v`
Expected: PASS — new accumulation tests pass; existing `test_propose_llm_returns_raw_strings_parents_none` still passes (it asserts only `_proposer`/`proposed`; the new `llm_cost_usd` key is 0.0 and unasserted); the e2e llm run still completes (await now inside the span; `update_span` no-ops without Langfuse).

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/graph.py packages/core/tests/test_loop_propose.py
git commit -m "$(cat <<'EOF'
feat(loop): accumulate LLM cost in state; wrap llm:propose span with token/cost

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: API cost gate reads `total_usd`

**Files:**
- Modify: `apps/api/capychem/api/runner.py:179-202` (per-generation cost aggregation + gate)
- Test: `apps/api/tests/test_cost_gate.py` (append one test)

**Interfaces:**
- Consumes: `cost.record_oracle_cost(..., llm_usd=)` (Task 1); `state["llm_cost_usd"]` (Task 4).
- Produces: the gate trips on `total_usd = oracle + llm`; `RunCost.total_usd` persisted accordingly.

> **Note:** `make_sessionmaker` uses `expire_on_commit=False`, so reading `row.total_usd` after `record_oracle_cost` commits is safe (attributes are not expired). The new test is hermetic (fake proposer + fake scorer; no harness), needs real Postgres like the existing gate test.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_cost_gate.py`:

```python
async def test_cost_cap_trips_on_llm_spend_alone(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Oracle cost is 0 (fake scorer); the LLM proposals carry a large cost, so the
    # gate must trip on total_usd = oracle + llm (slice 05).
    from capychem.loop import graph as graph_mod
    from capychem.loop import strategy
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        return [
            ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1),
                tokens_in=1000, tokens_out=1000, cost_usd=100.0,
            )
            for i in range(n)
        ]

    async def fake_score(smiles, task):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=0, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(strategy, "propose_llm_async", fake_llm)
    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    registry = RunRegistry(sm)
    cfg = RunConfig(
        task="qed", budget=20, seed=42, pop_size=6, offspring=6,
        mutation_rate=0.01, plateau_window=3, max_generations=5,
        mutation_strategy="llm",
    )
    run_id = await registry.start_run(cfg)
    handle = registry._runs[run_id]
    await handle.task

    assert handle.terminal_event is not None
    assert handle.terminal_event["status"] == "cost_capped"
    async with sm() as session:
        run = await session.get(Run, run_id)
        rc = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    assert run is not None and run.status == "cost_capped"
    assert rc is not None
    assert rc.oracle_cost_usd == pytest.approx(0.0)
    assert rc.llm_cost_usd >= 50.0                    # gen-1 LLM spend alone exceeds the $50 cap
    assert rc.total_usd == pytest.approx(rc.llm_cost_usd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_cost_gate.py::test_cost_cap_trips_on_llm_spend_alone -v`
Expected: FAIL — the runner records only oracle cost, so `rc.llm_cost_usd == 0.0` and the run never trips `cost_capped` on LLM spend (it exhausts/maxes instead).

- [ ] **Step 3: Rewire the gate to read `total_usd`**

In `apps/api/capychem/api/runner.py`, replace the cost-aggregation block (currently lines ~179-201, the `# Aggregate ...` comment through the `if total >= cost.cost_cap_usd():` check). The `state` variable is the streamed loop state from `async for state in stream`:

```python
                    # Aggregate the run's oracle cost from persisted OracleCalls and
                    # the cumulative LLM proposer cost from loop state; upsert RunCost
                    # so total_usd = oracle + llm (record_oracle_cost commits internally).
                    async with self._sm() as session:
                        oracle = await cost.oracle_cost_so_far(session, handle.run_id)
                        llm = state.get("llm_cost_usd", 0.0)
                        row = await cost.record_oracle_cost(
                            session, handle.run_id, oracle, llm_usd=llm
                        )
                        total = row.total_usd
                    snap["cost_so_far_usd"] = total
                    handle.broadcast(
                        GenerationCompleteEvent(
                            generation_index=snap["generation_index"],
                            best_score=snap["best_score"],
                            top10_mean=snap["auc_curve"][-1]["top10_mean"],
                            oracle_calls_used=snap["oracle_calls_used"],
                            cost_so_far_usd=total,
                            top_k=[TopMolecule(**m) for m in snap["top_k"]],
                        ).model_dump()
                    )
                    if total >= cost.cost_cap_usd():
                        cost_capped = True
                        break
                    if handle.cancel.is_set():
                        stopped = True
                        break
```

(Only the aggregation lines change — the `GenerationCompleteEvent` broadcast, the cost-cap break, and the cancel check keep their existing bodies; shown in full for context.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_cost_gate.py -v`
Expected: PASS — the new LLM-spend test trips `cost_capped`; the existing `test_cost_cap_trips_cost_capped` still passes (graph_ga run: `llm == 0`, monkeypatched `oracle_cost_so_far` → 999, so `total_usd == 999`).

- [ ] **Step 5: Commit**

```bash
git add apps/api/capychem/api/runner.py apps/api/tests/test_cost_gate.py
git commit -m "$(cat <<'EOF'
feat(api): cost gate reads RunCost.total_usd so it fires on LLM spend

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Full gate-green verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python test suite**

Run: `uv run pytest`
Expected: PASS — all tests (slice-04 baseline was 98 passed; this slice adds the new memoize/trace/propose/cost-gate tests).

- [ ] **Step 2: Typecheck**

Run: `uv run mypy -p capychem -p capychem.api`
Expected: no errors (strict). Watch for: orphaned `trim_to_budget` import (Task 3) and possibly-unbound `gen_llm_cost` (Task 4 initialises it to 0.0).

- [ ] **Step 3: Lint**

Run: `uv run ruff check .`
Expected: clean. Watch for: unused `trim_to_budget` import in `graph.py` (removed in Task 3).

- [ ] **Step 4: Report**

Report the three command outputs verbatim. If all green, the slice is ready for the merge checkpoint (do not merge without user sign-off per the kickoff). At the merge checkpoint, land in one commit on `main`: milestone-02 `milestone.md` slice-05 status → shipped (+ advance slice 06); `handoff.md` status flip + "Next session start here" → slice 06 (carry forward the gate-purity BLOCKER); freeze the slice doc; dated "Slice 05 shipped" log line.

---

## Self-Review

**Spec coverage:**
- Unique-call budget (spec §1, goal 1, exit-crit 4) → Task 3.
- LLM cost ledger / `total_usd = llm + oracle` (spec §2, goal 2, exit-crit 5) → Task 1 (recorder) + Task 4 (accumulation) + Task 5 (persist via runner).
- Cost gate reads `total_usd` (spec §3, goal 3) → Task 5.
- `llm:propose` span enrichment (spec §4, goal 4) → Task 2 (`update_span`) + Task 4 (wrap await + update).
- Out-of-scope (valid_smiles purity, eval/runner.py) → untouched; called out in Global Constraints.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `record_oracle_cost(..., *, llm_usd=0.0) -> RunCost` (Task 1) called with `llm_usd=llm` (Task 5); `update_span(span_id, **metadata)` (Task 2) called in Task 4; `mol_buffer: set[str]` / `llm_cost_usd: float` (Tasks 3/4) read via `state.get(...)` in `score`/`propose`/runner; `score` returns `mol_buffer` + `calls_used` consistently. No mismatches.
