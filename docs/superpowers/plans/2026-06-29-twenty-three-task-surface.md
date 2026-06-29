# Twenty-three-task surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 23 PMO tasks launchable end-to-end (registry → baselines → schema → UI) and add a mode-pluggable `capychem-eval --all` sweep runner — pure plumbing, no eval cost, unblocking slice 05.

**Architecture:** A single source-of-truth `eval/tasks.py::PMO_TASKS` tuple feeds the baselines dict, the API schema validator, and the sweep's default task list. A new `eval/sweep.py` orchestrates the existing per-task primitives (`run_reproduction`/`run_head_to_head`/`run_analyzer_verdict`) by mode with per-task error isolation; `cli.py` wires `--all` to it. The web launch page gains a `<select>` over a static mirror of the 23 task names.

**Tech Stack:** Python 3.12 (capychem core + apps/api), Pydantic v2, pytest + mypy strict + ruff; Next.js 16 / React 19 / TypeScript, vitest + Playwright.

## Global Constraints

- Every reported score is an in-silico oracle score (PRD N6); never claim real-world efficacy.
- Never `import` from `harness/`; the harness `Oracle(name=task)` is already task-agnostic — no harness change.
- Error messages and prompts use positive imperatives ("Choose a PMO task…", not "Don't…").
- The canonical AUC is `eval/metric.top_auc`; never compute an ad-hoc AUC.
- Published Graph-GA numbers are a sanity reference only; head-to-head/verdict decisions use our own same-seed control.
- mypy strict on all new/changed `apps/` + `packages/` code; ruff lint select = `E,F,I,UP,B`, line-length 100.
- Quality gate before the slice is done: `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` · `pnpm --filter web test` · `pnpm --filter web typecheck` · `pnpm --filter web lint`.
- Work on branch `slice-04-twenty-three-task-surface` (already created).

---

### Task 1: PMO task registry

**Files:**
- Create: `packages/core/capychem/eval/tasks.py`
- Test: `packages/core/tests/test_eval_tasks.py`

**Interfaces:**
- Produces: `PMO_TASKS: tuple[str, ...]` — the 23 canonical PyTDC oracle names in PMO Table 2 order.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_eval_tasks.py`:

```python
from capychem.eval.tasks import PMO_TASKS


def test_registry_has_23_unique_tasks() -> None:
    assert len(PMO_TASKS) == 23
    assert len(set(PMO_TASKS)) == 23


def test_registry_first_entry_is_qed_and_contains_milestone02_tasks() -> None:
    assert PMO_TASKS[0] == "qed"
    assert "jnk3" in PMO_TASKS
    assert "drd2" in PMO_TASKS  # a real PMO task that used to be the "unknown" fixture
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_tasks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.eval.tasks'`.

- [ ] **Step 3: Write minimal implementation**

Create `packages/core/capychem/eval/tasks.py`:

```python
"""Canonical PMO task registry — the single source of truth for the 23-task surface.

Names are the exact PyTDC oracle names (``Oracle(name=task)``), in NeurIPS 2022 PMO
Table 2 row order. Order is cosmetic (UI dropdown + sweep-row order only). Source:
agent_docs/pmo-auc-and-baselines.md. Every score these tasks produce is an in-silico
oracle score (PRD N6).
"""

from __future__ import annotations

PMO_TASKS: tuple[str, ...] = (
    "qed",
    "zaleplon_mpo",
    "perindopril_mpo",
    "celecoxib_rediscovery",
    "troglitazone_rediscovery",
    "drd2",
    "jnk3",
    "gsk3b",
    "albuterol_similarity",
    "amlodipine_mpo",
    "deco_hop",
    "fexofenadine_mpo",
    "isomers_c7h8n2o2",
    "isomers_c9h10n2o2pf2cl",
    "median1",
    "median2",
    "mestranol_similarity",
    "osimertinib_mpo",
    "ranolazine_mpo",
    "scaffold_hop",
    "sitagliptin_mpo",
    "thiothixene_rediscovery",
    "valsartan_smarts",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_tasks.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/tasks.py packages/core/tests/test_eval_tasks.py
git commit -m "feat(eval): PMO task registry (PMO_TASKS, 23 tasks) — single source of truth

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Twenty-three published Graph-GA baselines

**Files:**
- Modify: `packages/core/capychem/eval/baselines.py:8-15` (the `GRAPH_GA_AUC_TOP10` dict + its comment)
- Test: `packages/core/tests/test_eval_baselines.py` (extend)

**Interfaces:**
- Consumes: `PMO_TASKS` (Task 1).
- Produces: `GRAPH_GA_AUC_TOP10` now covers all 23 tasks; `compare_to_baseline` / `DEFAULT_TOLERANCE` unchanged.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_eval_baselines.py`:

```python
from capychem.eval.baselines import GRAPH_GA_AUC_TOP10
from capychem.eval.tasks import PMO_TASKS


def test_baselines_cover_every_registry_task() -> None:
    assert set(GRAPH_GA_AUC_TOP10) == set(PMO_TASKS)


def test_baseline_sum_matches_published_total() -> None:
    # PMO paper Table 2, Graph-GA "Sum (23 tasks)" = 13.751.
    assert abs(sum(GRAPH_GA_AUC_TOP10.values()) - 13.751) < 1e-3


def test_baseline_spot_values() -> None:
    assert GRAPH_GA_AUC_TOP10["jnk3"] == 0.553
    assert GRAPH_GA_AUC_TOP10["drd2"] == 0.964
    assert GRAPH_GA_AUC_TOP10["valsartan_smarts"] == 0.000
```

(Keep the existing `test_qed_within_tolerance`, `test_qed_outside_tolerance`, `test_jnk3_registered`. The existing top-of-file `from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline` import already covers `compare_to_baseline`; add the `PMO_TASKS` import.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py -q`
Expected: FAIL — `test_baselines_cover_every_registry_task` (only qed, jnk3 registered) and `test_baseline_sum_matches_published_total`.

- [ ] **Step 3: Write minimal implementation**

Replace the dict + its comment in `packages/core/capychem/eval/baselines.py` (lines 8–15) with:

```python
# Published Graph-GA AUC top-10, mean over 5 seeds (PMO paper Table 2). Sum = 13.751.
# These are a single-vs-5-seed SANITY REFERENCE only: every head-to-head / verdict
# decision uses our own same-seed Graph-GA control, never the published number as the
# comparator. Source: agent_docs/pmo-auc-and-baselines.md.
GRAPH_GA_AUC_TOP10: dict[str, float] = {
    "qed": 0.940,
    "zaleplon_mpo": 0.346,
    "perindopril_mpo": 0.538,
    "celecoxib_rediscovery": 0.630,
    "troglitazone_rediscovery": 0.390,
    "drd2": 0.964,
    "jnk3": 0.553,
    "gsk3b": 0.788,
    "albuterol_similarity": 0.838,
    "amlodipine_mpo": 0.661,
    "deco_hop": 0.619,
    "fexofenadine_mpo": 0.760,
    "isomers_c7h8n2o2": 0.862,
    "isomers_c9h10n2o2pf2cl": 0.719,
    "median1": 0.294,
    "median2": 0.273,
    "mestranol_similarity": 0.579,
    "osimertinib_mpo": 0.831,
    "ranolazine_mpo": 0.728,
    "scaffold_hop": 0.517,
    "sitagliptin_mpo": 0.433,
    "thiothixene_rediscovery": 0.479,
    "valsartan_smarts": 0.000,
}
```

(Sum of the values above = 13.751.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_baselines.py -q`
Expected: PASS (all, including the new three).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/baselines.py packages/core/tests/test_eval_baselines.py
git commit -m "feat(eval): register all 23 published Graph-GA baselines (Table 2, Sum 13.751)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Widen the launch schema to the 23-task surface

**Files:**
- Modify: `apps/api/capychem/api/schemas.py:7,11` (imports + the `task` field) and add a `field_validator`
- Test: `apps/api/tests/test_task_surface.py` (fix the "unknown task" fixtures, add surface coverage)

**Interfaces:**
- Consumes: `PMO_TASKS` (Task 1).
- Produces: `CreateRunRequest.task: str` accepted iff `task in PMO_TASKS`; otherwise a Pydantic `ValidationError` (→ HTTP 422). Default stays `"qed"`.

- [ ] **Step 1: Write the failing test**

Edit `apps/api/tests/test_task_surface.py`:

Replace `test_schema_rejects_unknown_task` with:

```python
def test_schema_rejects_unknown_task() -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(task="not_a_real_task", budget=10)


def test_schema_accepts_full_pmo_surface() -> None:
    from capychem.eval.tasks import PMO_TASKS

    for task in PMO_TASKS:
        assert CreateRunRequest(task=task, budget=10).task == task
    # drd2 was the old "unknown" fixture; it is a real PMO task and now valid.
    assert CreateRunRequest(task="drd2", budget=10).task == "drd2"
```

And in `test_post_runs_rejects_unknown_task`, change the posted body task `"drd2"` → `"not_a_real_task"`:

```python
            r = await c.post("/runs", json={"task": "not_a_real_task", "budget": 10})
            assert r.status_code == 422
```

(Keep `test_schema_accepts_jnk3_and_qed` and `test_post_runs_maps_task_strategy_plateau_to_config` unchanged.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_task_surface.py -q`
Expected: FAIL — `test_schema_accepts_full_pmo_surface` (e.g. `drd2` raises under the current `Literal["qed","jnk3"]`).

- [ ] **Step 3: Write minimal implementation**

In `apps/api/capychem/api/schemas.py`:

Change the import line (currently `from pydantic import BaseModel, Field`) to:

```python
from pydantic import BaseModel, Field, field_validator

from capychem.eval.tasks import PMO_TASKS
```

Change the `task` field (currently `task: Literal["qed", "jnk3"] = "qed"`) to:

```python
    task: str = "qed"
```

Add this validator as the first member of `CreateRunRequest` (immediately after the field block, before `class TopMolecule`):

```python
    @field_validator("task")
    @classmethod
    def _task_must_be_pmo(cls, v: str) -> str:
        if v not in PMO_TASKS:
            raise ValueError(
                f"Choose a PMO task from the 23-task surface; got {v!r}."
            )
        return v
```

If `Literal` is now unused elsewhere in the file, leave the `from typing import Any, Literal` import as-is only if `Literal` is still referenced (it is — `GenerationCompleteEvent.type` and `RunCompleteEvent.type` use `Literal`). Do not remove it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_task_surface.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add apps/api/capychem/api/schemas.py apps/api/tests/test_task_surface.py
git commit -m "feat(api): validate launch task against the 23-task PMO registry (FR-015)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Mode-pluggable sweep runner

**Files:**
- Create: `packages/core/capychem/eval/sweep.py`
- Test: `packages/core/tests/test_eval_sweep.py`

**Interfaces:**
- Consumes: `PMO_TASKS` (Task 1); `GRAPH_GA_AUC_TOP10`, `compare_to_baseline` (Task 2); existing `run_reproduction` (`eval/runner.py`), `top_auc` (`eval/metric.py`), `run_head_to_head`+`BeatVerdict` (`eval/beat.py`), `run_analyzer_verdict`+`AnalyzerVerdict` (`eval/verdict.py`).
- Produces:
  - `SweepRow(task: str, ok: bool, headline_auc: float | None, beat: bool | None, payload: dict[str, Any])`
  - `SweepReport(mode: str, budget: int, seed: int, tasks_run: int, tasks_failed: int, auc_sum: float, published_sum: float, beats: int | None, rows: list[SweepRow])`
  - `run_sweep(tasks: tuple[str, ...] = PMO_TASKS, *, budget: int, seed: int, mode: str = "reproduce", pop_size: int = 120, offspring: int = 70, mutation_rate: float = 0.067) -> SweepReport`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_eval_sweep.py`:

```python
import pytest

from capychem.eval import sweep as sweep_mod
from capychem.eval.beat import BeatVerdict
from capychem.eval.runner import ReproResult
from capychem.eval.sweep import run_sweep
from capychem.eval.verdict import AnalyzerVerdict


def test_reproduce_mode_aggregates_auc_and_no_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the per-task primitive: a 2-molecule buffer scoring ~0.5 top-10 mean.
    def fake_repro(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return ReproResult(
            mol_buffer={"CCO": (0.5, 1), "c1ccccc1": (0.5, 2)},
            generations=2, unique_calls=2,
        )

    monkeypatch.setattr(sweep_mod, "run_reproduction", fake_repro)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="reproduce")
    assert report.mode == "reproduce"
    assert report.tasks_run == 2 and report.tasks_failed == 0
    assert report.beats is None  # reproduce defines no beat
    assert report.published_sum == pytest.approx(0.940 + 0.553)
    assert report.auc_sum > 0.0
    # qed is registered -> reproduce row carries a baseline diff
    qed_row = next(r for r in report.rows if r.task == "qed")
    assert "baseline_published" in qed_row.payload and "within_tolerance" in qed_row.payload


def test_head_to_head_mode_counts_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_h2h(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        beat = task == "jnk3"
        return BeatVerdict(
            task=task, seed=seed, budget=budget,
            llm_auc=0.60 if beat else 0.40, graph_ga_auc=0.50,
            diff=0.10 if beat else -0.10, beat=beat,
            llm_valid_rate=0.9, llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=None, llm_unique_calls=budget, graph_ga_unique_calls=budget,
        )

    monkeypatch.setattr(sweep_mod, "run_head_to_head", fake_h2h)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="head_to_head")
    assert report.beats == 1
    assert report.auc_sum == pytest.approx(0.40 + 0.60)
    assert report.rows[0].payload["graph_ga_auc"] == 0.50  # full verdict fields preserved


def test_analyzer_verdict_mode_counts_helps(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_av(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        helps = task == "jnk3"
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.70 if helps else 0.50, without_auc=0.60,
            diff=0.10 if helps else -0.10, helps=helps,
            analyzer_parse_rate=1.0, analyzer_calls=10, analyzer_parsed=10,
            parse_rate_healthy=True, with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=budget, without_unique_calls=budget,
        )

    monkeypatch.setattr(sweep_mod, "run_analyzer_verdict", fake_av)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="analyzer_verdict")
    assert report.beats == 1
    assert report.auc_sum == pytest.approx(0.50 + 0.70)
    assert report.rows[0].payload["parse_rate_healthy"] is True


def test_per_task_error_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    def flaky_repro(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        if task == "jnk3":
            raise RuntimeError("oracle download failed")
        return ReproResult(mol_buffer={"CCO": (0.5, 1)}, generations=1, unique_calls=1)

    monkeypatch.setattr(sweep_mod, "run_reproduction", flaky_repro)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="reproduce")
    assert report.tasks_run == 1 and report.tasks_failed == 1
    bad = next(r for r in report.rows if r.task == "jnk3")
    assert bad.ok is False and "oracle download failed" in bad.payload["error"]


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        run_sweep(("qed",), budget=10, seed=42, mode="nonsense")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.eval.sweep'`.

- [ ] **Step 3: Write minimal implementation**

Create `packages/core/capychem/eval/sweep.py`:

```python
"""Mode-pluggable PMO sweep runner: walk a task list, run the existing per-task
primitive for the chosen mode, aggregate per-task rows + a summary.

This is pure orchestration — it adds NO new AUC or comparator logic (the canonical
PMO ``top_auc`` and the existing head-to-head / analyzer-verdict primitives do all the
measuring). One task throwing is isolated to its own row so a long sweep never aborts.
Every score is an in-silico oracle score (PRD N6).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.beat import run_head_to_head
from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction
from capychem.eval.tasks import PMO_TASKS
from capychem.eval.verdict import run_analyzer_verdict


@dataclass(frozen=True)
class SweepRow:
    task: str
    ok: bool
    headline_auc: float | None  # reproduce: auc_top10; h2h: llm_auc; verdict: with_auc
    beat: bool | None  # h2h: beat; verdict: helps; reproduce: None
    payload: dict[str, Any]  # the mode's per-task report fields, or {"error": ...}


@dataclass(frozen=True)
class SweepReport:
    mode: str
    budget: int
    seed: int
    tasks_run: int  # successful rows
    tasks_failed: int
    auc_sum: float  # sum of headline_auc over successful rows
    published_sum: float  # sum of published Graph-GA baselines over the input tasks
    beats: int | None  # count of beat/helps (None for reproduce)
    rows: list[SweepRow]


def _run_one(
    task: str,
    *,
    budget: int,
    seed: int,
    mode: str,
    pop_size: int,
    offspring: int,
    mutation_rate: float,
) -> SweepRow:
    if mode == "reproduce":
        res = run_reproduction(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
            mutation_strategy="graph_ga",
        )
        auc = top_auc(
            res.mol_buffer, top_n=10, finish=True, freq_log=100, max_oracle_calls=budget
        )
        payload: dict[str, Any] = {
            "auc_top10": auc,
            "unique_calls_used": res.unique_calls,
            "generations": res.generations,
        }
        if task in GRAPH_GA_AUC_TOP10:
            cmp = compare_to_baseline(task, auc)
            payload |= {
                "baseline_published": cmp.baseline,
                "tolerance": cmp.tolerance,
                "diff": cmp.diff,
                "within_tolerance": cmp.within_tolerance,
            }
        return SweepRow(task=task, ok=True, headline_auc=auc, beat=None, payload=payload)

    if mode == "head_to_head":
        v = run_head_to_head(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        )
        return SweepRow(task=task, ok=True, headline_auc=v.llm_auc, beat=v.beat, payload=asdict(v))

    if mode == "analyzer_verdict":
        v2 = run_analyzer_verdict(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        )
        return SweepRow(
            task=task, ok=True, headline_auc=v2.with_auc, beat=v2.helps, payload=asdict(v2)
        )

    raise ValueError(f"Use a known sweep mode (reproduce|head_to_head|analyzer_verdict); got {mode!r}.")


def run_sweep(
    tasks: tuple[str, ...] = PMO_TASKS,
    *,
    budget: int,
    seed: int,
    mode: str = "reproduce",
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> SweepReport:
    if mode not in ("reproduce", "head_to_head", "analyzer_verdict"):
        raise ValueError(
            f"Use a known sweep mode (reproduce|head_to_head|analyzer_verdict); got {mode!r}."
        )
    rows: list[SweepRow] = []
    for task in tasks:
        try:
            rows.append(
                _run_one(
                    task, budget=budget, seed=seed, mode=mode,
                    pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
                )
            )
        except Exception as exc:  # per-task isolation: one failure never aborts the sweep
            rows.append(
                SweepRow(task=task, ok=False, headline_auc=None, beat=None,
                         payload={"error": str(exc)})
            )
    ok_rows = [r for r in rows if r.ok]
    auc_sum = sum((r.headline_auc for r in ok_rows if r.headline_auc is not None), 0.0)
    published_sum = sum((GRAPH_GA_AUC_TOP10[t] for t in tasks if t in GRAPH_GA_AUC_TOP10), 0.0)
    beats = None if mode == "reproduce" else sum(1 for r in ok_rows if r.beat)
    return SweepReport(
        mode=mode, budget=budget, seed=seed,
        tasks_run=len(ok_rows), tasks_failed=len(rows) - len(ok_rows),
        auc_sum=auc_sum, published_sum=published_sum, beats=beats, rows=rows,
    )
```

Note: `_run_one` raises `ValueError` for an unknown mode, but `run_sweep` checks the mode up front (before the per-task loop) so a bad mode fails fast rather than being swallowed by the per-task `except`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/sweep.py packages/core/tests/test_eval_sweep.py
git commit -m "feat(eval): mode-pluggable run_sweep over the PMO task surface

reproduce | head_to_head | analyzer_verdict; per-task error isolation;
aggregates auc_sum / published_sum / beats. Reuses the existing per-task
primitives + canonical top_auc.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Wire `capychem-eval --all` to the sweep

**Files:**
- Modify: `packages/core/capychem/eval/cli.py` (add `import dataclasses`; add the `--all` arg; add the `--all` dispatch block)
- Test: `packages/core/tests/test_eval_cli.py` (extend)

**Interfaces:**
- Consumes: `run_sweep` / `SweepReport` / `SweepRow` (Task 4).
- Produces: `capychem-eval --all [--head-to-head|--analyzer-verdict] --budget B --seed S` emits a combined JSON report `{sweep: true, mode, budget, seed, tasks_run, tasks_failed, auc_sum, published_sum, beats, rows, wall_seconds}`.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_eval_cli.py`:

```python
def test_cli_all_default_mode_reproduce(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport, SweepRow

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(
            mode=mode, budget=budget, seed=seed, tasks_run=1, tasks_failed=0,
            auc_sum=0.94, published_sum=13.751, beats=None,
            rows=[SweepRow(task="qed", ok=True, headline_auc=0.94, beat=None,
                           payload={"auc_top10": 0.94})],
        )

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--budget", "200", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sweep"] is True
    assert captured["mode"] == "reproduce"
    assert report["mode"] == "reproduce"
    assert report["published_sum"] == 13.751
    assert report["beats"] is None
    assert report["rows"][0]["task"] == "qed"
    assert "wall_seconds" in report


def test_cli_all_selects_analyzer_verdict_mode(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(mode=mode, budget=budget, seed=seed, tasks_run=0,
                           tasks_failed=0, auc_sum=0.0, published_sum=13.751,
                           beats=0, rows=[])

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--analyzer-verdict", "--budget", "10000", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert captured["mode"] == "analyzer_verdict"
    assert report["mode"] == "analyzer_verdict"


def test_cli_all_selects_head_to_head_mode(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(mode=mode, budget=budget, seed=seed, tasks_run=0,
                           tasks_failed=0, auc_sum=0.0, published_sum=13.751,
                           beats=0, rows=[])

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--head-to-head", "--budget", "1500", "--seed", "42"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "head_to_head"
    assert captured["mode"] == "head_to_head"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -q`
Expected: FAIL — argparse rejects the unknown `--all` flag (SystemExit) / the new tests error.

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/eval/cli.py`:

Add to the imports at the top (after `import time`):

```python
import dataclasses
```

Add the `--all` argument in `main`, immediately after the `--task` argument line (`p.add_argument("--task", required=True)`) is **not** suitable because `--all` makes `--task` optional. Instead: change the `--task` line to no longer be required, and add `--all`:

Replace:

```python
    p.add_argument("--task", required=True)
```

with:

```python
    p.add_argument("--task", default=None)
    p.add_argument(
        "--all",
        action="store_true",
        dest="all_tasks",
        help="Sweep all 23 PMO tasks; mode from --head-to-head/--analyzer-verdict (default reproduce).",  # noqa: E501
    )
```

Then add validation + the dispatch block. Immediately after `args = p.parse_args(argv)` add:

```python
    if not args.all_tasks and args.task is None:
        p.error("--task is required unless --all is given")
```

Immediately after `t0 = time.monotonic()` (before the `if args.capture_analyzer_traces:` block) add:

```python
    if args.all_tasks:
        from capychem.eval.sweep import run_sweep

        mode = (
            "analyzer_verdict" if args.analyzer_verdict
            else "head_to_head" if args.head_to_head
            else "reproduce"
        )
        report = run_sweep(
            budget=args.budget, seed=args.seed, mode=mode,
            pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        sweep_out: dict[str, object] = {
            "sweep": True,
            **dataclasses.asdict(report),
            "wall_seconds": round(wall, 1),
        }
        json.dump(sweep_out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
```

(The existing single-task branches below remain unchanged; they only run when `--all` is absent.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -q`
Expected: PASS (all — the 3 new + the existing tests; the existing single-task tests still pass `--task`).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): capychem-eval --all sweep (mode from existing flags)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Launch-page task selector (all 23)

**Files:**
- Modify: `apps/web/app/page.tsx` (add `PMO_TASKS`, a `task` state + `<select>`, thread it into `createRun`, retitle)
- Modify: `apps/web/app/page.test.tsx` (update title assertion; add a selector test)
- Modify: `apps/web/e2e/launch.spec.ts` (update the title matcher)

**Interfaces:**
- Consumes: `createRun` (`lib/api.ts`, already accepts `task: string`).
- Produces: the launch form submits the user-selected `task` (default `jnk3`).

- [ ] **Step 1: Write the failing test**

Edit `apps/web/app/page.test.tsx`:

Replace the `describe("launch form (jnk3)", ...)` block body's first test and add a selector test:

```tsx
describe("launch form", () => {
  beforeEach(() => {
    createRun.mockClear();
    push.mockClear();
  });

  it("renders the form with a task selector defaulting to jnk3", () => {
    render(<Home />);
    screen.getByText(/Launch an optimization/i);
    const select = screen.getByLabelText(/^Task$/i) as HTMLSelectElement;
    expect(select.value).toBe("jnk3");
    screen.getByLabelText(/Mutation strategy/i);
    screen.getByLabelText(/Plateau window/i);
  });

  it("submits the default task=jnk3 with the chosen strategy", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Mutation strategy/i), {
      target: { value: "llm" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ task: "jnk3", mutation_strategy: "llm" }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/7"));
  });

  it("submits the selected task when changed", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/^Task$/i), {
      target: { value: "drd2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start run/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ task: "drd2" }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter web test -- --run app/page.test.tsx`
Expected: FAIL — no element labelled `Task`; title text `Launch an optimization` not found.

- [ ] **Step 3: Write minimal implementation**

Edit `apps/web/app/page.tsx`:

Add the registry const after the `DEFAULTS` block:

```tsx
// Mirrors capychem.eval.tasks.PMO_TASKS (the canonical source); the PMO 23 are static.
const PMO_TASKS = [
  "qed", "zaleplon_mpo", "perindopril_mpo", "celecoxib_rediscovery",
  "troglitazone_rediscovery", "drd2", "jnk3", "gsk3b", "albuterol_similarity",
  "amlodipine_mpo", "deco_hop", "fexofenadine_mpo", "isomers_c7h8n2o2",
  "isomers_c9h10n2o2pf2cl", "median1", "median2", "mestranol_similarity",
  "osimertinib_mpo", "ranolazine_mpo", "scaffold_hop", "sitagliptin_mpo",
  "thiothixene_rediscovery", "valsartan_smarts",
] as const;
```

Add a `task` state next to `strategy` (after the `const [strategy, setStrategy] = ...` line):

```tsx
  const [task, setTask] = useState<string>("jnk3");
```

Thread it into `createRun` — change the `createRun({ task: "jnk3", ... })` call to:

```tsx
      const { run_id } = await createRun({
        task,
        mutation_strategy: strategy,
        ...form,
      });
```

Retitle — change `<CardTitle>Launch a jnk3 optimization</CardTitle>` to:

```tsx
          <CardTitle>Launch an optimization</CardTitle>
```

Add the task `<select>` as the first field inside the form grid, immediately after `<form ...>` opens and before the numeric-fields `.map(...)`:

```tsx
            <div className="flex flex-col gap-1">
              <Label htmlFor="task">Task</Label>
              <select
                id="task"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {PMO_TASKS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter web test -- --run app/page.test.tsx`
Expected: PASS (3 passed).

Also update `apps/web/e2e/launch.spec.ts`: change the title assertion
`await expect(page.getByText(/Launch a jnk3 optimization/i)).toBeVisible();`
to
`await expect(page.getByText(/Launch an optimization/i)).toBeVisible();`
(The e2e is opt-in / live-stack only; not run in the gate, but keep it correct. The `task` select defaults to jnk3 so the rest of the e2e flow is unchanged.)

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/page.tsx apps/web/app/page.test.tsx apps/web/e2e/launch.spec.ts
git commit -m "feat(web): launch-page task selector across all 23 PMO tasks (G3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Full quality gate + slice-ship docs

**Files:**
- Modify: `docs/03-analyzer-and-scale/milestone.md` (slice 04 status → shipped; advance slice 05 note)
- Modify: `docs/03-analyzer-and-scale/handoff.md` (status flip, "Next session start here", slice log)
- Freeze: the slice-04 design spec + this plan (no further edits)

**Interfaces:** none (docs + verification only).

- [ ] **Step 1: Run the full gate**

Run each and confirm clean:

```bash
uv run pytest -q
uv run mypy -p capychem -p capychem.api
uv run ruff check .
pnpm --filter web test -- --run
pnpm --filter web typecheck
pnpm --filter web lint
```

Expected: all green. Fix any failure before proceeding (do not edit unrelated code).

- [ ] **Step 2: Update milestone + handoff docs**

In `docs/03-analyzer-and-scale/milestone.md`, slice 04 line → `shipped (2026-06-29)`; note in slice 05's line that 04 is now ✓ (its last open dep besides 06).

In `docs/03-analyzer-and-scale/handoff.md`: flip slice 04 to shipped in "Slice status across milestone"; set "Next session start here" to slice 03 (`analyzer-live-surface`) OR slice 05 (top up DeepSeek balance first); add a dated "Slice 04 shipped" log line; record commit refs under "Completed this session".

- [ ] **Step 3: Commit the ship docs**

```bash
git add docs/03-analyzer-and-scale/milestone.md docs/03-analyzer-and-scale/handoff.md
git commit -m "docs(slice-04): ship twenty-three-task surface — registry + baselines + schema/UI + --all sweep

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Finish the branch**

Use `superpowers:finishing-a-development-branch` to merge `slice-04-twenty-three-task-surface` into `main` (fast-forward / no-ff per the project's established pattern) and confirm the gate is green on `main`.

---

## Self-Review

**Spec coverage:**
- Registry (`eval/tasks.py::PMO_TASKS`) → Task 1. ✓
- 23 baselines + Sum 13.751 → Task 2. ✓
- Schema `field_validator` against registry + drd2-now-valid test fix → Task 3. ✓
- `eval/sweep.py` (`run_sweep`, modes, error isolation, summary auc_sum/published_sum/beats) → Task 4. ✓
- `--all` CLI wiring, mode from existing flags → Task 5. ✓
- UI selector (23, default jnk3, retitle, thread task) + web tests + e2e → Task 6. ✓
- Per-task error isolation → Task 4 test `test_per_task_error_isolation`. ✓
- Full quality gate + ship docs → Task 7. ✓
- Out-of-scope items (real sweep, GET /tasks, baseline hints) → not implemented, by design. ✓

**Placeholder scan:** no TBD/TODO; every code step has full code; every command has expected output. ✓

**Type consistency:** `run_sweep(tasks, *, budget, seed, mode, pop_size, offspring, mutation_rate) -> SweepReport`; `SweepRow(task, ok, headline_auc, beat, payload)`; `SweepReport(mode, budget, seed, tasks_run, tasks_failed, auc_sum, published_sum, beats, rows)` — used identically in Task 4 (impl + tests) and Task 5 (CLI asdict + fake `SweepReport`/`SweepRow`). `field_validator` name + signature consistent (Task 3). `PMO_TASKS` tuple (core) / array (web) consistent contents. ✓
