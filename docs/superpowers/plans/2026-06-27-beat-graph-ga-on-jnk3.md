# Beat Graph-GA on jnk3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible head-to-head verdict — LLM-proposer AUC-of-top-10 vs our own same-seed vanilla Graph-GA control on jnk3 — plus the carried valid-SMILES gate-purity fix, rendered as the milestone-02 week-7 kill-switch call.

**Architecture:** Five deterministic, stub-testable code changes (gate-purity guard in the product loop; LLM-only validity tracking in the headless eval runner; jnk3 baseline registration; a head-to-head verdict layer; a `--head-to-head` CLI mode), then a *staged* real experiment: a small calibration run, a human go/no-go checkpoint, then the authoritative full-10k run committed as evidence. The verdict path is headless (no Postgres, deterministic, G6); the product-loop fix keeps the live `summary_json` honest.

**Tech Stack:** Python 3.12, uv workspace, pytest, mypy (strict), ruff. RDKit for SMILES validation. PMO `top_auc` metric. DeepSeek-v4-pro via the Modal-free `direct` proposer backend. jnk3 scored by the isolated `harness/` env via subprocess (never imported).

## Global Constraints

- **Never import from `harness/`** — modern code reaches the oracle only via `oracle.py` (subprocess + JSON). (CLAUDE.md)
- **Never claim real-world drug-discovery efficacy** — every score is an in-silico oracle score (PRD N6). Copy/comments must reflect this.
- **Validate every SMILES via RDKit before persistence** — never trust LLM output. (CLAUDE.md)
- **AUC is the canonical `eval.metric.top_auc`** — never recompute AUC ad hoc. (CLAUDE.md gotcha)
- **mypy strict on new code** under `apps/` and `packages/`; ruff clean.
- **Determinism (G6):** same task + same seed + same model → identical AUC top-10 ±1%.
- **Gate green before any commit that ends a task:** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` · `uv run ruff format .` (web suite untouched — no web changes this slice).
- **Frozen `valid_smiles` block shape** when present: `{proposed, valid, rate, gate}` — read by slice 04; never reshape.
- **No real DeepSeek spend in any test** — tests use the `stub` backend or monkeypatch the proposer/verdict. Real spend happens only in Tasks 6–7, gated by a human checkpoint.
- Branch: `slice-06-beat-graph-ga-on-jnk3` (already created; the design spec is committed there).

---

### Task 1: Gate-purity fix — `summary_json.valid_smiles` counts the LLM proposer only (the BLOCKER)

**Files:**
- Modify: `packages/core/capychem/loop/graph.py:90-106` (the `validate` node)
- Test: `packages/core/tests/test_loop_valid_smiles.py`

**Interfaces:**
- Consumes: `validate_batch_with_stats` (already imported in graph.py), `state["_proposer"]` (set by the `propose` node: `"starting"` | `"llm"` | `"graph_ga"`).
- Produces: `state["_validation_stats"]` is written **only** for LLM-proposer generations; absent on non-LLM runs → `build_summary` omits the `valid_smiles` block.

- [ ] **Step 1: Rewrite the existing graph_ga test + add the LLM-only test**

In `packages/core/tests/test_loop_valid_smiles.py`, **replace** the body of `test_summary_has_valid_smiles_block` (rename it) and **add** a new LLM test. Keep the existing `sm` fixture and imports; add `from capychem.proposer import ProposalResult` and `from capychem.loop import strategy` where used.

Replace the existing test function with these two:

```python
async def test_graph_ga_run_omits_valid_smiles_block(sm, monkeypatch):
    # The >80% gate is an LLM-validity concept. A graph_ga run (gen-0 "starting"
    # seeds + graph_ga offspring) has no LLM proposals, so summary_json must NOT
    # carry a valid_smiles block (previously it reported an inflated ~100%).
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed", budget=12, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=2, max_generations=2,
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
    assert "valid_smiles" not in final["summary"]


async def test_llm_run_reports_llm_only_valid_rate(sm, monkeypatch):
    # Gen-1 LLM proposes 4 (2 valid + 2 invalid); gen-0 seeds are all valid.
    # The block must reflect LLM-only validity: proposed=4, valid=2, rate=0.5
    # (gen-0 seeds excluded; fallback fills never enter _validation_stats).
    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0)
            for s in smiles
        ]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    from capychem.loop import strategy
    from capychem.proposer import ProposalResult

    async def fake_llm(task, population, *, n, seed):
        smis = ["CCO", "c1ccccc1", "not-a-smiles", "@@@@"]
        return [
            ProposalResult(raw=smis[i % 4], smiles=smis[i % 4], tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    monkeypatch.setattr(strategy, "propose_llm_async", fake_llm)
    from capychem.run import RunConfig, create_run

    cfg = RunConfig(
        task="qed", budget=12, seed=42, pop_size=4, offspring=4,
        mutation_rate=0.01, plateau_window=2, max_generations=2,
        mutation_strategy="llm",
    )
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    initial: LoopState = {
        "run_id": run_id, "task": cfg.task, "budget": cfg.budget, "seed": cfg.seed,
        "pop_size": cfg.pop_size, "offspring": cfg.offspring,
        "mutation_rate": cfg.mutation_rate, "plateau_window": cfg.plateau_window,
        "max_generations": cfg.max_generations, "mutation_strategy": "llm",
        "calls_used": 0, "gen_index": 0, "population": [], "run_trace_id": None,
        "gen_span_id": None, "auc_curve": [], "done": False,
    }
    final = await g.ainvoke(initial, config={"recursion_limit": 30})
    vs = final["summary"]["valid_smiles"]
    assert vs["proposed"] == 4
    assert vs["valid"] == 2
    assert vs["rate"] == 0.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_loop_valid_smiles.py -v`
Expected: FAIL — `test_graph_ga_run_omits_valid_smiles_block` fails because the block is still present; `test_llm_run_reports_llm_only_valid_rate` fails because the cumulative stats still include the gen-0 seeds (gets `proposed==8, valid==6, rate==0.75`).

- [ ] **Step 3: Add the LLM-only guard to the `validate` node**

In `packages/core/capychem/loop/graph.py`, replace the `validate` node body (lines ~96-106) so `_validation_stats` is accumulated only for the LLM proposer:

```python
async def validate(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:validate",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        validated, stats = validate_batch_with_stats(state["proposed"])
        proposer_label = state.get("_proposer", "graph_ga")
        validated = [replace(vc, proposer=proposer_label) for vc in validated]
        out: dict[str, Any] = {"validated": validated}
        # Gate purity (slice 06): the >80% valid-SMILES gate measures the LLM
        # proposer only. Gen-0 "starting" seeds and graph_ga batches are excluded;
        # graph_ga fallback fills never reach this node (they enter via `fallback`).
        if proposer_label == "llm":
            prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
            out["_validation_stats"] = {
                "proposed": prev["proposed"] + stats.proposed,
                "valid": prev["valid"] + stats.valid,
            }
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_valid_smiles.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest packages/core/tests/ -q && uv run mypy -p capychem -p capychem.api && uv run ruff check . && uv run ruff format .`
Expected: all green. (Watch for any *other* test that asserted a `valid_smiles` block on a non-llm run — if one exists, update it to the corrected semantic before committing.)

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/loop/graph.py packages/core/tests/test_loop_valid_smiles.py
git commit -m "fix(loop): valid_smiles gate counts the LLM proposer only (slice-06 blocker)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Headless LLM-only validity tracking in the eval runner

**Files:**
- Modify: `packages/core/capychem/eval/runner.py` (imports, `ReproResult`, `run_reproduction`)
- Test: `packages/core/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `validate_batch_with_stats(candidates) -> (list[ValidCandidate], ValidationStats)` from `capychem.validate`; `ValidationStats.proposed`, `ValidationStats.valid` (valid is pre-dedup RDKit-valid).
- Produces: `ReproResult.llm_proposed: int`, `ReproResult.llm_valid: int`, `ReproResult.valid_rate: float | None` (None on a graph_ga run). Consumed by Task 4 (`run_head_to_head`).

- [ ] **Step 1: Write the failing tests**

Add to `packages/core/tests/test_eval_runner.py`:

```python
def test_llm_validity_rate_is_llm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # LLM emits 2 valid + 2 invalid each gen; seeds are all valid. The tracked
    # rate must reflect LLM proposals only (seeds excluded) -> 0.5.
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    def fake_llm_sync(task, population, *, n, seed):  # type: ignore[no-untyped-def]
        smis = ["CCO", "c1ccccc1", "not-a-smiles", "@@@@"]
        return [
            ProposalResult(raw=smis[i % 4], smiles=smis[i % 4], tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1", "CCN", "CCC"][:n])

    res = run_reproduction("qed", budget=20, seed=42, pop_size=4, offspring=4,
                           patience=2, mutation_strategy="llm")
    assert res.llm_proposed > 0
    assert res.llm_valid / res.llm_proposed == 0.5
    assert res.valid_rate == 0.5


def test_graph_ga_run_has_no_valid_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.oracle import OracleResult, Offspring

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    def fake_propose(population, n_offspring, **kw):  # type: ignore[no-untyped-def]
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n_offspring)]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_propose)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1"][:n])

    res = run_reproduction("qed", budget=20, seed=42, pop_size=2, offspring=3, patience=2)
    assert res.valid_rate is None
    assert res.llm_proposed == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_eval_runner.py::test_llm_validity_rate_is_llm_only packages/core/tests/test_eval_runner.py::test_graph_ga_run_has_no_valid_rate -v`
Expected: FAIL with `AttributeError: 'ReproResult' object has no attribute 'llm_proposed'` (and `valid_rate`).

- [ ] **Step 3: Add validity fields + tracking**

In `packages/core/capychem/eval/runner.py`:

(a) Extend the import (line 19):

```python
from capychem.validate import validate_batch, validate_batch_with_stats
```

(b) Extend `ReproResult` (lines 22-26):

```python
@dataclass(frozen=True)
class ReproResult:
    mol_buffer: dict[str, tuple[float, int]]
    generations: int
    unique_calls: int
    llm_proposed: int = 0
    llm_valid: int = 0
    valid_rate: float | None = None
```

(c) Initialize counters before the generation loop (after `prev_top = ...`, around line 77):

```python
    llm_proposed = 0
    llm_valid = 0
```

(d) In the llm branch (lines 82-89), use `validate_batch_with_stats` and accumulate:

```python
        if mutation_strategy == "llm":
            results = propose_llm_sync(task, pop_pairs, n=offspring, seed=seed + generations)
            valid_llm, stats = validate_batch_with_stats([(r.smiles, None) for r in results])
            llm_proposed += stats.proposed
            llm_valid += stats.valid
            fillers = fallback_fill(
                valid_llm, pop_pairs, target=offspring,
                mutation_rate=mutation_rate, seed=seed + generations,
            )
            valid = [*valid_llm, *fillers]
```

(e) Replace the return (line 112):

```python
    valid_rate = (llm_valid / llm_proposed) if llm_proposed else None
    return ReproResult(
        mol_buffer=mol_buffer,
        generations=generations,
        unique_calls=len(mol_buffer),
        llm_proposed=llm_proposed,
        llm_valid=llm_valid,
        valid_rate=valid_rate,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -v`
Expected: PASS (new tests + the existing memoization/patience/llm-strategy tests still green).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest packages/core/tests/ -q && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/runner.py packages/core/tests/test_eval_runner.py
git commit -m "feat(eval): track LLM-only valid-SMILES rate in the headless runner

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Register the jnk3 Graph-GA published baseline (sanity reference)

**Files:**
- Modify: `packages/core/capychem/eval/baselines.py:9-12`
- Test: `packages/core/tests/test_eval_baselines.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GRAPH_GA_AUC_TOP10["jnk3"] == 0.553`; `compare_to_baseline("jnk3", auc)` resolves. Consumed by Task 4 (`published_baseline`) and Task 5 (CLI report).

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_baselines.py`:

```python
def test_jnk3_registered() -> None:
    from capychem.eval.baselines import GRAPH_GA_AUC_TOP10

    assert GRAPH_GA_AUC_TOP10["jnk3"] == 0.553
    res = compare_to_baseline("jnk3", 0.553)
    assert res.baseline == 0.553
    assert res.within_tolerance is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py::test_jnk3_registered -v`
Expected: FAIL with `KeyError: 'jnk3'`.

- [ ] **Step 3: Register the baseline**

In `packages/core/capychem/eval/baselines.py`, update the dict (lines 9-12):

```python
# Published Graph-GA AUC top-10, mean over 5 seeds (PMO paper Table 2).
GRAPH_GA_AUC_TOP10: dict[str, float] = {
    "qed": 0.940,
    # jnk3 is a SANITY REFERENCE only (single-vs-5-seed): the slice-06 head-to-head
    # decision uses our own same-seed Graph-GA control, never this number. Source:
    # agent_docs/pmo-auc-and-baselines.md.
    "jnk3": 0.553,
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/baselines.py packages/core/tests/test_eval_baselines.py
git commit -m "feat(eval): register jnk3 Graph-GA baseline as a sanity reference

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Head-to-head verdict layer (`eval/beat.py`)

**Files:**
- Create: `packages/core/capychem/eval/beat.py`
- Test: `packages/core/tests/test_eval_beat.py`

**Interfaces:**
- Consumes: `run_reproduction(...) -> ReproResult` (Task 2, with `valid_rate`/`unique_calls`); `top_auc(buffer, top_n=10, max_oracle_calls=...)`; `valid_smiles_gate(rate) -> dict` from `capychem.loop.logic`; `GRAPH_GA_AUC_TOP10` (Task 3).
- Produces: `BeatVerdict` dataclass and `run_head_to_head(task, budget, seed, *, pop_size=120, offspring=70, mutation_rate=0.067) -> BeatVerdict`. Consumed by Task 5 (CLI).

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_eval_beat.py`:

```python
import pytest
from capychem.eval import runner as runner_mod
from capychem.eval.beat import BeatVerdict, run_head_to_head


def _stub(monkeypatch: pytest.MonkeyPatch, llm_pool: list[str]) -> None:
    from capychem.oracle import OracleResult, Offspring
    from capychem.proposer import ProposalResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        # deterministic per-SMILES score by length so LLM and GA buffers differ
        return [
            OracleResult(smiles=s, score=min(0.99, 0.3 + 0.05 * len(s)), valid=True, wall_ms=1)
            for s in smiles
        ]

    def fake_ga(population, n, **kw):  # type: ignore[no-untyped-def]
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n)]

    def fake_llm(task, population, *, n, seed):  # type: ignore[no-untyped-def]
        return [
            ProposalResult(raw=llm_pool[i % len(llm_pool)], smiles=llm_pool[i % len(llm_pool)],
                           tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_ga)
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm)
    monkeypatch.setattr(runner_mod, "starting_population",
                        lambda n: ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"][:n])


def test_head_to_head_shape_and_determinism(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1", "CCN", "CCC"])
    v1 = run_head_to_head("jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert isinstance(v1, BeatVerdict)
    assert v1.beat == (v1.llm_auc > v1.graph_ga_auc)
    assert abs(v1.diff - (v1.llm_auc - v1.graph_ga_auc)) < 1e-12
    assert v1.published_baseline == 0.553          # jnk3 registered (Task 3)
    assert v1.llm_valid_rate is not None            # llm path ran
    assert v1.llm_valid_gate is not None
    # same seed -> identical verdict (G6)
    v2 = run_head_to_head("jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v2 == v1


def test_head_to_head_unknown_task_has_no_published_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1"])
    v = run_head_to_head("qed", budget=6, seed=1, pop_size=2, offspring=3, mutation_rate=0.01)
    assert v.published_baseline == 0.940           # qed IS registered
    assert isinstance(v.beat, bool)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_beat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'capychem.eval.beat'`.

- [ ] **Step 3: Create `beat.py`**

Create `packages/core/capychem/eval/beat.py`:

```python
"""Head-to-head beat verdict: LLM proposer vs our own same-seed Graph-GA control.

The slice-06 / milestone-02 week-7 kill-switch. Both runs go through the headless
``run_reproduction`` (deterministic, no DB) and are measured with the canonical
PMO ``top_auc`` — never an ad-hoc AUC. Every score is an in-silico oracle score
(PRD N6). The published baseline (if any) is a sanity reference, not the comparator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.loop.logic import valid_smiles_gate


@dataclass(frozen=True)
class BeatVerdict:
    task: str
    seed: int
    budget: int
    llm_auc: float
    graph_ga_auc: float
    diff: float  # llm_auc - graph_ga_auc
    beat: bool  # llm_auc > graph_ga_auc
    llm_valid_rate: float | None
    llm_valid_gate: dict[str, Any] | None
    published_baseline: float | None  # sanity reference, if registered
    llm_unique_calls: int
    graph_ga_unique_calls: int


def run_head_to_head(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> BeatVerdict:
    """Run graph_ga and llm same-seed, measure both via top_auc, return the verdict."""
    ga = run_reproduction(
        task, budget, seed, pop_size=pop_size, offspring=offspring,
        mutation_rate=mutation_rate, mutation_strategy="graph_ga",
    )
    llm = run_reproduction(
        task, budget, seed, pop_size=pop_size, offspring=offspring,
        mutation_rate=mutation_rate, mutation_strategy="llm",
    )
    ga_auc = top_auc(ga.mol_buffer, top_n=10, max_oracle_calls=budget)
    llm_auc = top_auc(llm.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = llm.valid_rate
    gate = valid_smiles_gate(rate) if rate is not None else None
    return BeatVerdict(
        task=task,
        seed=seed,
        budget=budget,
        llm_auc=llm_auc,
        graph_ga_auc=ga_auc,
        diff=llm_auc - ga_auc,
        beat=llm_auc > ga_auc,
        llm_valid_rate=rate,
        llm_valid_gate=gate,
        published_baseline=GRAPH_GA_AUC_TOP10.get(task),
        llm_unique_calls=llm.unique_calls,
        graph_ga_unique_calls=ga.unique_calls,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_beat.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest packages/core/tests/ -q && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/beat.py packages/core/tests/test_eval_beat.py
git commit -m "feat(eval): head-to-head beat verdict (LLM vs same-seed Graph-GA)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `--head-to-head` CLI mode

**Files:**
- Modify: `packages/core/capychem/eval/cli.py`
- Test: `packages/core/tests/test_eval_cli.py`

**Interfaces:**
- Consumes: `run_head_to_head(...) -> BeatVerdict` (Task 4).
- Produces: a `BeatVerdict`-shaped JSON report with `"head_to_head": true` when `--head-to-head` is passed; the existing single-strategy report is unchanged otherwise.

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_cli.py`:

```python
def test_cli_head_to_head_report(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # Stub the verdict so the CLI test runs no eval and makes no DeepSeek call —
    # the wiring (flag -> run_head_to_head -> report) is what's under test.
    from capychem.eval import beat as beat_mod
    from capychem.eval.beat import BeatVerdict

    def fake_h2h(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return BeatVerdict(
            task=task, seed=seed, budget=budget, llm_auc=0.61, graph_ga_auc=0.55,
            diff=0.06, beat=True, llm_valid_rate=0.9,
            llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=0.553, llm_unique_calls=budget, graph_ga_unique_calls=budget,
        )

    monkeypatch.setattr(beat_mod, "run_head_to_head", fake_h2h)
    rc = main(["--task", "jnk3", "--budget", "1500", "--seed", "42", "--head-to-head"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["head_to_head"] is True
    assert report["task"] == "jnk3"
    assert report["beat"] is True
    assert report["llm_auc"] == 0.61 and report["graph_ga_auc"] == 0.55
    assert report["published_baseline"] == 0.553
    assert report["llm_valid_gate"] == {"threshold": 0.8, "passed": True}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_cli.py::test_cli_head_to_head_report -v`
Expected: FAIL — `--head-to-head` is an unrecognized argument (argparse SystemExit), or `head_to_head` key absent.

- [ ] **Step 3: Add the flag + branch**

In `packages/core/capychem/eval/cli.py`, add the argument after the `--mutation-strategy` line (line 31):

```python
    p.add_argument(
        "--head-to-head",
        action="store_true",
        help="Run llm vs graph_ga same-seed on --task and emit a beat verdict.",
    )
```

Then, immediately after `args = p.parse_args(argv)` (line 32) and `t0 = time.monotonic()` (line 34), insert the head-to-head branch *before* the existing single-strategy `run_reproduction` block:

```python
    t0 = time.monotonic()
    if args.head_to_head:
        from capychem.eval.beat import run_head_to_head

        v = run_head_to_head(
            args.task, args.budget, args.seed,
            pop_size=args.pop_size, offspring=args.offspring,
            mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        h2h_report: dict[str, object] = {
            "task": v.task,
            "seed": v.seed,
            "budget": v.budget,
            "head_to_head": True,
            "llm_auc": v.llm_auc,
            "graph_ga_auc": v.graph_ga_auc,
            "diff": v.diff,
            "beat": v.beat,
            "llm_valid_rate": v.llm_valid_rate,
            "llm_valid_gate": v.llm_valid_gate,
            "published_baseline": v.published_baseline,
            "llm_unique_calls": v.llm_unique_calls,
            "graph_ga_unique_calls": v.graph_ga_unique_calls,
            "wall_seconds": round(wall, 1),
        }
        json.dump(h2h_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
```

Note: the head-to-head branch uses a distinct variable name (`h2h_report`) so it does not collide with the existing single-strategy `report: dict[str, object]` annotation further down — no mypy redefinition error, and the existing path (including its `report |= {...}` baseline block) is left exactly as-is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -v`
Expected: PASS — both `test_cli_emits_report` (single-strategy, unchanged) and `test_cli_head_to_head_report`.

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest packages/core/tests/ -q && uv run mypy -p capychem -p capychem.api && uv run ruff check . && uv run ruff format .`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): --head-to-head CLI mode emits the beat verdict report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Staged calibration run + human go/no-go checkpoint  *(operator task — not subagent-delegable; real DeepSeek spend)*

**Files:**
- Output: `<scratchpad>/jnk3-calibration.json` (throwaway, not committed)

This task runs the real `direct` backend against DeepSeek + the jnk3 harness oracle. It is **not** a TDD task; it produces a directional verdict and cost/wall-time calibration, then **stops for a human decision**.

- [ ] **Step 1: Sanity-check the harness + env (no spend)**

Run a tiny graph_ga-only eval to confirm the harness + jnk3 oracle work on this branch:

```bash
uv run capychem-eval --task jnk3 --budget 60 --seed 42 --pop-size 20 --offspring 10
```
Expected: a JSON report with `auc_top10` in [0,1], `baseline_published: 0.553`, and `unique_calls_used <= 60`. (graph_ga makes no LLM call — no spend.) If the harness errors, stop and surface it.

- [ ] **Step 2: Run the small head-to-head calibration (real DeepSeek `direct` backend)**

```bash
set -a; source .env.local; set +a
SCRATCH="/private/tmp/claude-501/-Users-hoangngo-Documents-personal-projects-CapyChem/e00557b3-a455-4d08-b7b9-ebf2a8c70071/scratchpad"
time uv run capychem-eval --head-to-head --task jnk3 --budget 1500 --seed 42 \
  | tee "$SCRATCH/jnk3-calibration.json"
```
Expected: a `head_to_head: true` report with `llm_auc`, `graph_ga_auc`, `diff`, `beat`, `llm_valid_rate` + `llm_valid_gate`, both `*_unique_calls`, and `wall_seconds`. Capture the `time` wall-clock separately (the report's `wall_seconds` covers both runs).

- [ ] **Step 3: Record calibration findings**

Note, for the checkpoint: total wall-time, per-generation feel (≈ `wall_seconds / (llm_unique_calls/offspring)`), the directional `beat`/`diff`, the `llm_valid_rate` vs the 0.80 gate, and the DeepSeek cost (from the DeepSeek dashboard, or estimate from token rates). Confirm cost « $1 at budget 1500.

- [ ] **Step 4: CHECKPOINT — present results and get the go/no-go**

Stop here. Present to the operator: the directional verdict, the measured cost + wall-time, and a recommendation on whether to commit to the full 10k run (and whether to keep defaults pop_size=120/offspring=70 or adjust for wall-time). **Do not start the full run without an explicit go.** If the directional result already shows `beat == False`, surface the kill-switch options (narrow scope; analyzer-only narrative) before deciding.

---

### Task 7: Authoritative full-10k run + committed verdict  *(operator task — conditional on Task 6 go)*

**Files:**
- Create: `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md` (slice doc with the verdict)
- Output: `docs/02-end-to-end-loop/jnk3-beat-verdict.json` (committed evidence)

- [ ] **Step 1: Run the full head-to-head (real DeepSeek `direct` backend)**

```bash
set -a; source .env.local; set +a
time uv run capychem-eval --head-to-head --task jnk3 --budget 10000 --seed 42 \
  | tee docs/02-end-to-end-loop/jnk3-beat-verdict.json
```
Expected: the `head_to_head` report at the full 10k unique-call budget. Watch the cost stays under the ~$50 gate.

- [ ] **Step 2: Reproducibility spot-check (G6)**

Re-run graph_ga alone at the same seed and confirm the AUC matches the report's `graph_ga_auc` to ±1% (the deterministic control anchors G6; a full llm re-run is optional given API variance):

```bash
uv run capychem-eval --task jnk3 --budget 10000 --seed 42
```
Expected: `auc_top10` within ±1% of the committed `graph_ga_auc`.

- [ ] **Step 3: Write the slice doc**

Create `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md` (per `~/.claude/CLAUDE.md` slice-doc shape: Goal / Plan / Tasks / Notes), recording: the verdict (`beat`, `llm_auc`, `graph_ga_auc`, `diff`), the `llm_valid_rate` vs the 0.80 gate, the published 0.553 sanity reference, both unique-call counts, cost + wall-time, and the **exact full-run command** above. State the kill-switch reading: `beat == True` → on track for milestone 03; `beat == False` → narrow scope (do not abandon; analyzer-only narrative remains). Every score is an in-silico oracle score (PRD N6).

- [ ] **Step 4: Commit the verdict evidence**

```bash
git add docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md docs/02-end-to-end-loop/jnk3-beat-verdict.json
git commit -m "docs(slice-06): jnk3 beat-Graph-GA verdict (week-7 kill-switch)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Ship the slice  *(operator task — per project conventions)*

**Files:**
- Modify: `docs/milestones.md`, `docs/02-end-to-end-loop/milestone.md`, `docs/02-end-to-end-loop/handoff.md`
- Freeze: `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md`

- [ ] **Step 1: Flip statuses + advance the handoff (one commit on the main-flow branch)**

Per `CLAUDE.md` "When a slice ships": in `docs/02-end-to-end-loop/milestone.md` Slices list, flip `06-beat-graph-ga-on-jnk3` → shipped; in `docs/milestones.md` update the milestone-02 slice line; in `handoff.md` flip the slice-status block, advance "Next session start here" (→ slice 02 `plateau-stop-and-signal`, the last remaining slice, OR the milestone-02 ship if 02 is the only thing left), and append a dated "Slice 06 shipped" log line with commit refs. Freeze the slice doc (no further edits). If slice 06 was the last unshipped slice except 02, note milestone 02 stays `← active` until 02 ships.

- [ ] **Step 2: Verify the gate one last time, then merge to `main`**

```bash
uv run pytest -q && uv run mypy -p capychem -p capychem.api && uv run ruff check . && pnpm --filter web test
git checkout main
git merge --no-ff slice-06-beat-graph-ga-on-jnk3
```
Per the project's local-only convention, **do not push** unless the operator asks. Confirm the ship-doc edits landed on `main` (not just the branch).

---

## Self-Review

**Spec coverage** (each spec section → task):
- Spec §1 headless validity → **Task 2**. ✅
- Spec §1 product-loop gate-purity BLOCKER → **Task 1**. ✅
- Spec §2 head-to-head verdict layer → **Task 4**. ✅
- Spec §3 jnk3 baseline registration → **Task 3**. ✅
- Spec §4 `--head-to-head` CLI → **Task 5**. ✅
- Spec §5 staged run protocol (calibration → checkpoint → full) → **Tasks 6 + 7**. ✅
- Spec testing section → folded into each task's Steps 1-5. ✅
- Spec goal 5 / exit criterion 8 verdict artifact → **Task 7** (committed slice doc + JSON). ✅
- Ship ritual (CLAUDE.md) → **Task 8**. ✅

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". All code steps carry complete code; all run steps carry exact commands + expected output. Task 6/7/8 are operator tasks with concrete commands (real-spend + human-gate by nature) — explicitly flagged, not vague. ✅

**Type consistency:**
- `ReproResult` fields `llm_proposed/llm_valid/valid_rate` defined in Task 2, consumed identically in Task 4. ✅
- `BeatVerdict` fields defined in Task 4, consumed by the same names in Task 5's report + tests. ✅
- `run_head_to_head(task, budget, seed, *, pop_size, offspring, mutation_rate)` — same signature in Task 4 def, Task 5 call, and the stubs. ✅
- `validate_batch_with_stats(...) -> (list, ValidationStats)` with `.proposed`/`.valid` — used consistently in Tasks 1 + 2. ✅
- `valid_smiles_gate(rate) -> dict` — used in Task 4. ✅
- `GRAPH_GA_AUC_TOP10["jnk3"] == 0.553` — set in Task 3, asserted in Tasks 4 + (calibration) 6. ✅
