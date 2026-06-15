# Reproduce Graph-GA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `packages/core/capychem/eval/` as the canonical AUC-of-top-10 harness + a `capychem-eval` CLI, and reproduce vanilla Graph-GA on QED to within ±0.02 of the published PMO `0.940`.

**Architecture:** A *pure* PMO `top_auc` port (no I/O), a *headless* memoized GA runner (no Postgres, no LangGraph — reuses the existing `oracle`/`validate`/`loop.logic` primitives, differing only in unique-call budget + in-memory buffer), a small published-baselines table, and a thin CLI that wires them into a JSON report. The product loop is untouched.

**Tech Stack:** Python 3.12, the isolated `harness/` env via the existing `oracle.py` subprocess bridge, pytest, mypy strict.

**Binding constraints (from `agent_docs/pmo-auc-and-baselines.md` — do NOT deviate):** `mutation_rate=0.067`; `top_auc` is trapezoidal, sampled every `freq_log=100`, `finish=True` tail-pad, `÷ max_oracle_calls`; budget counts **unique** (memoized) oracle calls; PMO Graph-GA params `pop_size=120`, `offspring=70`.

**Worktree/env note:** Track A is harness-backed. If executed in a worktree, set `CAPYCHEM_HARNESS_PYTHON=/Users/hoangngo/Documents/personal-projects/CapyChem/harness/.venv/bin/python` (worktrees get no own harness venv). Leave `CAPYCHEM_ORACLE_BACKEND` unset (local).

**Reference (confirm exact signatures before use — these are quoted from an Explore pass, line numbers may drift):**
- `oracle.propose_offspring(population: list[tuple[str, float]], n_offspring: int, *, mutation_rate: float, seed: int) -> list[Offspring]`; `Offspring(smiles: str, parents: tuple[int, int])`.
- `oracle.score_smiles(smiles: list[str], task: str, *, timeout_s: float = 120.0) -> list[OracleResult]`; `OracleResult(smiles, score: float|None, valid: bool, wall_ms, cost_usd)`. `smiles` returned is canonical.
- `validate.validate_batch(...)` — canonicalizes + intra-batch dedups + drops invalid → `list[ValidCandidate]`. **Confirm `ValidCandidate` field names** (`.smiles`, `.parent`/`.parents`) in `packages/core/capychem/validate.py`.
- `loop.logic.merge_and_truncate(pop, new_scored, pop_size)` → survivors sorted by `(-score, smiles)`. `Scored(.smiles, .score)`. **Confirm in `packages/core/capychem/loop/logic.py`.**
- `loop.graph.load_starting_pop(n)` reads `harness/capychem_harness/data/starting_pop.smi` (pure file read, no DB) → list of SMILES. If importing `graph` pulls undesired deps, extract it to `packages/core/capychem/loop/seeds.py` and import from both.

---

### Task 1: `eval/metric.py` — pure PMO `top_auc` port (load-bearing)

**Files:**
- Create: `packages/core/capychem/eval/__init__.py` (empty)
- Create: `packages/core/capychem/eval/metric.py`
- Test: `packages/core/tests/test_eval_metric.py`

- [ ] **Step 1: Write the failing tests** (hand-computed expected values — see arithmetic in comments)

```python
# packages/core/tests/test_eval_metric.py
import pytest
from capychem.eval.metric import top_auc


def test_constant_curve_no_finish_pad() -> None:
    # 300 molecules all score 0.5; budget=300 so finish adds nothing.
    # range(100,300,100)=[100,200]; idx100: +100*(0.5+0)/2=25; idx200: +100*(0.5+0.5)/2=50 -> 75
    # partial: (300-200)*(0.5+0.5)/2=50 -> 125 ; 125/300 = 0.416666...
    buf = {f"s{i}": (0.5, i + 1) for i in range(300)}
    assert top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=300) == pytest.approx(0.416666, abs=1e-5)


def test_finish_pads_remaining_budget() -> None:
    # same buffer but budget=400 -> early stop; finish pads (400-300)*0.5=50 -> 175 ; 175/400 = 0.4375
    buf = {f"s{i}": (0.5, i + 1) for i in range(300)}
    assert top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=400) == pytest.approx(0.4375, abs=1e-5)


def test_top_n_selection_and_call_order_replay() -> None:
    # a(0.1,1) b(0.9,2) c(0.2,3) d(0.8,4); top_n=2 freq_log=2 max=4 finish=True
    # idx2: ordered[:2]=[a,b]; top2=[0.9,0.1] mean=0.5; +2*(0.5+0)/2=0.5
    # partial:(4-2); top2 of all=[0.9,0.8] mean=0.85; +2*(0.85+0.5)/2=1.35 -> 1.85 ; 1.85/4=0.4625
    buf = {"a": (0.1, 1), "b": (0.9, 2), "c": (0.2, 3), "d": (0.8, 4)}
    assert top_auc(buf, top_n=2, finish=True, freq_log=2, max_oracle_calls=4) == pytest.approx(0.4625, abs=1e-9)


def test_fewer_than_top_n_molecules() -> None:
    # 3 molecules, top_n=10 -> mean over the 3 available; must not crash
    buf = {"a": (0.2, 1), "b": (0.4, 2), "c": (0.6, 3)}
    val = top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=10000)
    assert 0.0 <= val <= 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_eval_metric.py -x`
Expected: FAIL — `ModuleNotFoundError: capychem.eval.metric`

- [ ] **Step 3: Implement the faithful port** (stdlib only — no numpy)

```python
# packages/core/capychem/eval/metric.py
"""The single authoritative AUC-of-top-10 metric.

Faithful port of PMO `main/optimizer.py::top_auc` (see
agent_docs/pmo-auc-and-baselines.md for the verbatim source). This is the
canonical G1 number; the running curve in loop/logic.py is a live-UI estimate
only — do not let a second AUC definition drift in.
"""
from __future__ import annotations


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def top_auc(
    buffer: dict[str, tuple[float, int]],
    top_n: int = 10,
    finish: bool = True,
    freq_log: int = 100,
    max_oracle_calls: int = 10000,
) -> float:
    """Trapezoidal AUC of the running-best top-`top_n` mean vs unique oracle calls.

    `buffer` maps canonical SMILES -> (score, call_order), where call_order is
    the 1-based ordinal at which the SMILES was first scored. Returns a value in
    [0, 1] because PMO oracle scores live in [0, 1].
    """
    total = 0.0
    prev = 0.0
    called = 0
    ordered = sorted(buffer.items(), key=lambda kv: kv[1][1])  # chronological replay
    for idx in range(freq_log, min(len(buffer), max_oracle_calls), freq_log):
        window = sorted(ordered[:idx], key=lambda kv: kv[1][0], reverse=True)[:top_n]
        top_now = _mean([item[1][0] for item in window])
        total += freq_log * (top_now + prev) / 2
        prev = top_now
        called = idx
    tail = sorted(ordered, key=lambda kv: kv[1][0], reverse=True)[:top_n]
    top_now = _mean([item[1][0] for item in tail])
    total += (len(buffer) - called) * (top_now + prev) / 2
    if finish and len(buffer) < max_oracle_calls:
        total += (max_oracle_calls - len(buffer)) * top_now
    return total / max_oracle_calls
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/core/tests/test_eval_metric.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/__init__.py packages/core/capychem/eval/metric.py packages/core/tests/test_eval_metric.py
git commit -m "feat(eval): faithful PMO top_auc metric port"
```

---

### Task 2: `eval/baselines.py` — published Graph-GA table + tolerance

**Files:**
- Create: `packages/core/capychem/eval/baselines.py`
- Test: `packages/core/tests/test_eval_baselines.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_eval_baselines.py
from capychem.eval.baselines import compare_to_baseline


def test_qed_within_tolerance() -> None:
    res = compare_to_baseline("qed", 0.935)
    assert res.baseline == 0.940
    assert res.within_tolerance is True
    assert abs(res.diff - (-0.005)) < 1e-9


def test_qed_outside_tolerance() -> None:
    res = compare_to_baseline("qed", 0.80)
    assert res.within_tolerance is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py -x`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# packages/core/capychem/eval/baselines.py
"""Published PMO Graph-GA AUC-top-10 baselines (NeurIPS 2022 Table 2) and the
reproduction tolerance. Source: agent_docs/pmo-auc-and-baselines.md."""
from __future__ import annotations

from dataclasses import dataclass

# Published Graph-GA AUC top-10, mean over 5 seeds (PMO paper Table 2).
GRAPH_GA_AUC_TOP10: dict[str, float] = {
    "qed": 0.940,
    # Add other tasks when reproduced (milestone 02+). QED is the smoke target.
}

# Reproduction tolerance (our engineering recommendation, not a PMO-published
# value): absorbs starting-pop + single-vs-5-seed variance; tight enough to
# catch a broken metric/pipeline.
DEFAULT_TOLERANCE = 0.02


@dataclass(frozen=True)
class BaselineComparison:
    task: str
    auc: float
    baseline: float
    tolerance: float
    diff: float          # auc - baseline
    within_tolerance: bool


def compare_to_baseline(task: str, auc: float, tolerance: float = DEFAULT_TOLERANCE) -> BaselineComparison:
    if task not in GRAPH_GA_AUC_TOP10:
        raise KeyError(f"No published Graph-GA baseline for task {task!r}; add it to GRAPH_GA_AUC_TOP10.")
    baseline = GRAPH_GA_AUC_TOP10[task]
    diff = auc - baseline
    return BaselineComparison(task, auc, baseline, tolerance, diff, abs(diff) <= tolerance)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/baselines.py packages/core/tests/test_eval_baselines.py
git commit -m "feat(eval): published Graph-GA baselines + tolerance compare"
```

---

### Task 3: `eval/runner.py` — headless memoized GA runner (load-bearing)

**Files:**
- Create: `packages/core/capychem/eval/runner.py`
- Test: `packages/core/tests/test_eval_runner.py`

**Memoization contract (the heart of faithfulness):** a `mol_buffer: dict[str, tuple[float, int]]` keyed by canonical SMILES. Scoring a SMILES already in the buffer must NOT call the oracle and must NOT advance `call_order`. `call_order = len(mol_buffer) + 1` at first insert. The run stops when `len(mol_buffer) >= budget` (unique-call budget) or PMO patience triggers.

- [ ] **Step 1: Write the failing tests** (one pure unit test with a stubbed scorer proving memoization; one harness-backed smoke)

```python
# packages/core/tests/test_eval_runner.py
import os
import pytest
from capychem.eval import runner as runner_mod
from capychem.eval.runner import run_reproduction

HARNESS = bool(os.environ.get("CAPYCHEM_HARNESS_PYTHON")) or True  # local default venv exists


def test_memoization_does_not_rescore_known_smiles(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub propose + score so no harness is needed; prove duplicates are not re-scored.
    scored_calls: list[list[str]] = []

    def fake_score(smiles, task, **kw):
        scored_calls.append(list(smiles))
        from capychem.oracle import OracleResult
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    # propose always returns the SAME two molecules -> after gen 0 they are all known
    def fake_propose(population, n_offspring, **kw):
        from capychem.oracle import Offspring
        return [Offspring(smiles="CCO", parents=(0, 0)) for _ in range(n_offspring)]

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_offspring", fake_propose)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: ["CCO", "c1ccccc1"][:n])

    res = run_reproduction("qed", budget=10, seed=42, pop_size=2, offspring=5, patience=2)
    # only the unseen unique SMILES ever reach the scorer; no SMILES scored twice
    all_scored = [s for batch in scored_calls for s in batch]
    assert len(all_scored) == len(set(all_scored))
    assert set(res.mol_buffer) <= {"CCO", "c1ccccc1"}


@pytest.mark.skipif(not HARNESS, reason="needs harness venv")
def test_smoke_real_harness_unique_budget() -> None:
    res = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert len(res.mol_buffer) <= 200                      # never exceeds unique budget
    assert res.unique_calls == len(res.mol_buffer)
    assert all(0.0 <= score <= 1.0 for score, _ in res.mol_buffer.values())
    # determinism: same seed -> same buffer keys
    res2 = run_reproduction("qed", budget=200, seed=42, pop_size=20, offspring=10)
    assert set(res.mol_buffer) == set(res2.mol_buffer)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_eval_runner.py::test_memoization_does_not_rescore_known_smiles -x`
Expected: FAIL — `ModuleNotFoundError: capychem.eval.runner`

- [ ] **Step 3: Implement the runner**

```python
# packages/core/capychem/eval/runner.py
"""Headless, memoized Graph-GA reproduction runner.

No Postgres, no LangGraph. Reuses the production oracle/validate/merge
primitives; the ONLY differences from the product loop are (a) a memoizing
mol_buffer keyed by canonical SMILES so budget counts UNIQUE oracle calls, and
(b) no persistence. Used by `capychem-eval` to reproduce PMO baselines.
"""
from __future__ import annotations

from dataclasses import dataclass

from capychem.oracle import Offspring, OracleResult, propose_offspring, score_smiles  # noqa: F401
from capychem.validate import validate_batch
from capychem.loop.logic import merge_and_truncate
from capychem.loop.graph import load_starting_pop as starting_population  # pure file read


@dataclass(frozen=True)
class ReproResult:
    mol_buffer: dict[str, tuple[float, int]]
    generations: int
    unique_calls: int


def run_reproduction(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
    patience: int = 5,
    freq_log: int = 100,
) -> ReproResult:
    mol_buffer: dict[str, tuple[float, int]] = {}

    def score_unique(smiles_list: list[str]) -> list[tuple[str, float]]:
        """Score only unseen SMILES; memoize; return (smiles, score) for all known."""
        unseen = [s for s in smiles_list if s not in mol_buffer]
        # respect the unique-call budget: only score up to remaining headroom
        room = budget - len(mol_buffer)
        if room > 0 and unseen:
            for r in score_smiles(unseen[:room], task):
                if r.valid and r.score is not None and r.smiles not in mol_buffer:
                    mol_buffer[r.smiles] = (r.score, len(mol_buffer) + 1)
        return [(s, mol_buffer[s][0]) for s in smiles_list if s in mol_buffer]

    # --- generation 0: seed population ---
    seeds = starting_population(pop_size)
    valid0 = validate_batch([(s, None) for s in seeds])           # confirm input shape vs validate.py
    population = score_unique([c.smiles for c in valid0])          # list[(smiles, score)]
    population = merge_and_truncate([], _as_scored(population), pop_size)

    generations = 1
    patience_left = patience
    prev_top = _top_k_mean(mol_buffer, 100)

    # --- generations 1..N ---
    while len(mol_buffer) < budget:
        offs = propose_offspring(
            [(s.smiles, s.score) for s in population],
            offspring,
            mutation_rate=mutation_rate,
            seed=seed + generations,
        )
        valid = validate_batch([(o.smiles, o.parents) for o in offs])
        new_scored = score_unique([c.smiles for c in valid])
        population = merge_and_truncate(population, _as_scored(new_scored), pop_size)
        generations += 1

        # PMO patience: top-100 mean improvement < 1e-3 -> decrement; break at 0
        cur_top = _top_k_mean(mol_buffer, 100)
        if cur_top - prev_top < 1e-3:
            patience_left -= 1
            if patience_left <= 0:
                break
        else:
            patience_left = patience
        prev_top = cur_top

    return ReproResult(mol_buffer=mol_buffer, generations=generations, unique_calls=len(mol_buffer))


def _top_k_mean(buf: dict[str, tuple[float, int]], k: int) -> float:
    scores = sorted((score for score, _ in buf.values()), reverse=True)[:k]
    return sum(scores) / len(scores) if scores else 0.0
```

**Note:** `_as_scored(list[(smiles, score)]) -> list[Scored]` adapts to whatever `Scored` type `merge_and_truncate` expects. Inspect `loop/logic.py`; if `merge_and_truncate` already accepts `(smiles, score)` tuples or a `Scored` dataclass, build that exact type here (or import the existing constructor). Keep `population` elements with `.smiles`/`.score` attributes so the `propose_offspring` adapter above works. **Confirm `ValidCandidate`, `Scored`, and `merge_and_truncate`'s signature against the source before finalizing — adapt the three adapter lines, not the memoization logic.**

- [ ] **Step 4: Run both tests**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -v`
Expected: `test_memoization...` PASS; smoke PASS (needs harness; ~1–2 min).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/runner.py packages/core/tests/test_eval_runner.py
git commit -m "feat(eval): headless memoized Graph-GA reproduction runner"
```

---

### Task 4: `eval/cli.py` — `capychem-eval` entrypoint + report

**Files:**
- Create: `packages/core/capychem/eval/cli.py`
- Modify: `packages/core/pyproject.toml` — add to `[project.scripts]`
- Test: `packages/core/tests/test_eval_cli.py`

- [ ] **Step 1: Write the failing test** (small harness-backed run; assert report shape)

```python
# packages/core/tests/test_eval_cli.py
import json
from capychem.eval.cli import main


def test_cli_emits_report(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["--task", "qed", "--budget", "120", "--seed", "42", "--pop-size", "20", "--offspring", "10"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["task"] == "qed"
    assert report["budget"] == 120
    assert 0.0 <= report["auc_top10"] <= 1.0
    assert report["unique_calls_used"] <= 120
    assert report["baseline_published"] == 0.940
    assert "within_tolerance" in report and "diff" in report and "wall_seconds" in report
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -x`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the CLI** (`--budget` feeds BOTH the run stop and the metric's `max_oracle_calls`)

```python
# packages/core/capychem/eval/cli.py
"""`capychem-eval` — reproduce a PMO baseline and emit an AUC report."""
from __future__ import annotations

import argparse
import json
import sys
import time

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="capychem-eval", description="Reproduce a PMO Graph-GA baseline (AUC top-10).")
    p.add_argument("--task", required=True)
    p.add_argument("--budget", type=int, default=10000)       # unique-call budget AND metric max_oracle_calls
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pop-size", type=int, default=120)
    p.add_argument("--offspring", type=int, default=70)
    p.add_argument("--mutation-rate", type=float, default=0.067)
    args = p.parse_args(argv)

    t0 = time.monotonic()
    res = run_reproduction(
        args.task, args.budget, args.seed,
        pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
    )
    auc = top_auc(res.mol_buffer, top_n=10, finish=True, freq_log=100, max_oracle_calls=args.budget)
    wall = time.monotonic() - t0

    report: dict[str, object] = {
        "task": args.task, "seed": args.seed, "budget": args.budget,
        "pop_size": args.pop_size, "offspring": args.offspring, "mutation_rate": args.mutation_rate,
        "unique_calls_used": res.unique_calls, "generations": res.generations,
        "auc_top10": auc, "wall_seconds": round(wall, 1),
    }
    if args.task in GRAPH_GA_AUC_TOP10:
        cmp = compare_to_baseline(args.task, auc)
        report |= {"baseline_published": cmp.baseline, "tolerance": cmp.tolerance,
                   "diff": cmp.diff, "within_tolerance": cmp.within_tolerance}
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the console script**

Modify `packages/core/pyproject.toml` `[project.scripts]` (this block currently holds only `capychem-run`):

```toml
[project.scripts]
capychem-run = "capychem.cli:main"
capychem-eval = "capychem.eval.cli:main"
```

Run: `uv sync` then `uv run pytest packages/core/tests/test_eval_cli.py -v`
Expected: PASS (needs harness; ~1 min).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/cli.py packages/core/pyproject.toml packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): capychem-eval CLI + report"
```

---

### Task 5: Full reproduction run (orchestrator-run verification — NOT a CI test)

This is run by the orchestrator during the VERIFY phase, not by the implementer; it satisfies the milestone exit criterion. Recorded as evidence, not committed as a test (SPEC §10: the full sweep is on-demand / cost-bounded).

- [ ] **Step 1: Run the full reproduction**

Run: `uv run capychem-eval --task qed --budget 10000 --seed 42`
Expected: completes (~10–30 min local); `auc_top10` lands in **0.92–0.96**, `within_tolerance: true`.

- [ ] **Step 2: Record the number** in the slice doc + handoff (`auc_top10`, `unique_calls_used`, `generations`, `wall_seconds`). If it lands outside 0.92–0.96, STOP and debug (likely a metric or memoization bug) before claiming the exit criterion.

---

## Self-Review (completed by plan author)

- **Spec coverage:** metric (Task 1) ✓, baselines (Task 2) ✓, headless memoized runner with unique-call budget (Task 3) ✓, CLI + report + `--budget`→`max_oracle_calls` + pyproject script (Task 4) ✓, full-repro exit-criterion run (Task 5) ✓. Faithfulness invariants (mutation_rate, top_auc shape, finish, PMO params) baked into Tasks 1/3/4.
- **Placeholder scan:** none. The "confirm signatures" notes point at real, existing types the implementer must read — not undefined references.
- **Type consistency:** `mol_buffer: dict[str, tuple[float, int]]` and `top_auc(...)` signature identical across Tasks 1/3/4; `compare_to_baseline`/`BaselineComparison` fields consistent Tasks 2/4.
- **Known reconciliation points (flagged inline, intentional):** `ValidCandidate`/`Scored`/`merge_and_truncate` exact field names + `load_starting_pop` import path — the implementer confirms against source and adapts the three adapter lines only.
