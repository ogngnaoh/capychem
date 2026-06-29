# Week-8 Sweep & Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a with-analyzer-LLM vs vanilla-Graph-GA comparator to the eval surface, then run it across a 9-task high-headroom PMO subset and render the guarded Week-8 verdict (≥3 trustworthy beats → on track; <3 → inconclusive).

**Architecture:** Extend the existing `run_head_to_head` primitive with an `analyzer` flag (Approach A) rather than fork a new module — `run_reproduction(mutation_strategy="llm", analyzer=True)` already produces the with-analyzer arm. Add a `week8` sweep mode, a guarded `week8_verdict` reader, and `--week8`/`--tasks` CLI wiring. The cost gate already sums proposer+analyzer+oracle; verify it with a focused test. All new code is TDD'd on the free, deterministic stub backend; only the final sweep spends money.

**Tech Stack:** Python 3.12, pytest, mypy strict, ruff. `packages/core/capychem/eval/*` (beat, sweep, cli), `apps/api/tests/test_cost_gate.py`. DeepSeek-v4-pro via `direct` backends for the paid run only.

## Global Constraints

- **Never import from `harness/`** — the oracle is reached via subprocess + JSON; it is already task-agnostic. No harness change this slice.
- **TDD** — no new production code without a failing test first; commit per task.
- **Measure only via `eval/metric.top_auc`** — never an ad-hoc AUC. The beat is vs our **own same-seed** Graph-GA control, not the published number (sanity reference only; 23 verbatim baselines sum to 13.742).
- **`eval/tasks.py::PMO_TASKS`** is the single source of truth for task names; validate any task input against it.
- **Standard budget = 10000** unique oracle calls for the real sweep (PMO comparability).
- **Paid runs need BOTH** `CAPYCHEM_PROPOSER_BACKEND=direct` AND `CAPYCHEM_ANALYZER_BACKEND=direct`; source `.env.local` for `DEEPSEEK_API_KEY`. Secrets stay in `.env.local` (gitignored).
- **Every score is an in-silico oracle score** (PRD N6) — never claim real-world efficacy.
- **Gates green before merge:** `uv run pytest`, `uv run mypy -p capychem -p capychem.api`, `uv run ruff check .` (no web surface touched this slice).
- **Branch:** `slice-05-week8-sweep-and-gate` (already created off `main`).

---

### Task 1: `run_head_to_head` gains an `analyzer` flag + analyzer-health on `BeatVerdict`

**Files:**
- Modify: `packages/core/capychem/eval/beat.py`
- Test: `packages/core/tests/test_eval_beat.py`

**Interfaces:**
- Consumes: `run_reproduction(task, budget, seed, *, pop_size, offspring, mutation_rate, mutation_strategy, analyzer)` → `ReproResult` (has `analyzer_parse_rate: float|None`, `analyzer_calls: int`, `analyzer_parsed: int`, `valid_rate: float|None`).
- Produces: `run_head_to_head(..., analyzer: bool = False) -> BeatVerdict`; `BeatVerdict` gains `analyzer: bool`, `analyzer_parse_rate: float|None`, `analyzer_calls: int`, `analyzer_parsed: int`, `parse_rate_healthy: bool` (all defaulted, appended last).

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_beat.py` (the `_stub` helper already exists in this file):

```python
def test_head_to_head_analyzer_on_populates_health(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.analyzer import AnalyzerResult

    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1", "CCN", "CCC"])
    # the with-analyzer arm calls run_analyzer_sync (imported into runner); stub it parsed
    monkeypatch.setattr(
        runner_mod,
        "run_analyzer_sync",
        lambda summary, *, seed: AnalyzerResult(
            text="focus rings", structured={"focus": "rings", "avoid": []},
            tokens_in=0, tokens_out=0, cost_usd=0.0,
        ),
    )
    v = run_head_to_head(
        "jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01, analyzer=True
    )
    assert v.analyzer is True
    assert v.analyzer_calls >= 1
    assert v.analyzer_parsed == v.analyzer_calls
    assert v.analyzer_parse_rate == 1.0
    assert v.parse_rate_healthy is True


def test_head_to_head_analyzer_off_is_default_and_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, llm_pool=["CCO", "c1ccccc1", "CCN", "CCC"])
    v = run_head_to_head("jnk3", budget=8, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v.analyzer is False
    assert v.analyzer_calls == 0
    assert v.analyzer_parse_rate is None
    assert v.parse_rate_healthy is False  # no analyzer ran -> not "healthy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_beat.py::test_head_to_head_analyzer_on_populates_health -x`
Expected: FAIL — `run_head_to_head() got an unexpected keyword argument 'analyzer'` (or `BeatVerdict` has no field `analyzer`).

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/eval/beat.py`, add a parse-rate floor constant near the top (after imports):

```python
# Mirror the valid-SMILES gate and verdict._PARSE_RATE_FLOOR: below this the
# with-analyzer arm's hypotheses are not really parsing (a $0-balance mid-run
# degrades the LLM arm to Graph-GA), so a beat is not trustworthy.
_PARSE_RATE_FLOOR = 0.8
```

Append the new fields to `BeatVerdict` (after `graph_ga_unique_calls`, all with defaults so existing constructors are unchanged):

```python
    llm_unique_calls: int
    graph_ga_unique_calls: int
    # with-analyzer-arm health (milestone 03 slice 05); defaults keep the
    # existing analyzer-off head_to_head constructions unchanged.
    analyzer: bool = False
    analyzer_parse_rate: float | None = None
    analyzer_calls: int = 0
    analyzer_parsed: int = 0
    parse_rate_healthy: bool = False
```

Add `analyzer: bool = False` to `run_head_to_head`'s keyword-only params, thread it into the LLM arm, and populate the new fields:

```python
def run_head_to_head(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
    analyzer: bool = False,
) -> BeatVerdict:
    """Run graph_ga and llm same-seed, measure both via top_auc, return the verdict.

    ``analyzer=True`` runs the LLM arm WITH the analyzer (the Week-8 bar:
    with-analyzer-LLM vs vanilla Graph-GA). ``parse_rate_healthy`` then guards the
    beat alongside ``llm_valid_gate``."""
    ga = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="graph_ga",
    )
    llm = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="llm", analyzer=analyzer,
    )
    ga_auc = top_auc(ga.mol_buffer, top_n=10, max_oracle_calls=budget)
    llm_auc = top_auc(llm.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = llm.valid_rate
    gate = valid_smiles_gate(rate) if rate is not None else None
    parse_rate = llm.analyzer_parse_rate
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
        analyzer=analyzer,
        analyzer_parse_rate=parse_rate,
        analyzer_calls=llm.analyzer_calls,
        analyzer_parsed=llm.analyzer_parsed,
        parse_rate_healthy=(
            analyzer and parse_rate is not None and parse_rate >= _PARSE_RATE_FLOOR
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_beat.py -x`
Expected: PASS (both new tests + the 4 existing head_to_head tests, since the new fields are defaulted).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/beat.py packages/core/tests/test_eval_beat.py
git commit -m "feat(eval): run_head_to_head analyzer flag + analyzer-health on BeatVerdict"
```

---

### Task 2: `week8` sweep mode

**Files:**
- Modify: `packages/core/capychem/eval/sweep.py`
- Test: `packages/core/tests/test_eval_sweep.py`

**Interfaces:**
- Consumes: `run_head_to_head(task, budget, seed, *, pop_size, offspring, mutation_rate, analyzer=True)` → `BeatVerdict` (Task 1).
- Produces: `run_sweep(tasks, *, budget, seed, mode="week8", ...)` dispatches to the with-analyzer comparator; `SweepRow.payload` carries `asdict(BeatVerdict)` incl. the analyzer-health fields; `SweepReport.beats` counts `beat`.

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_sweep.py`:

```python
def test_week8_mode_runs_with_analyzer_and_counts_beats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    def fake_h2h(task, budget, seed, *, analyzer=False, **kw):  # type: ignore[no-untyped-def]
        seen[task] = analyzer
        beat = task == "jnk3"
        return BeatVerdict(
            task=task, seed=seed, budget=budget,
            llm_auc=0.60 if beat else 0.40, graph_ga_auc=0.50,
            diff=0.10 if beat else -0.10, beat=beat,
            llm_valid_rate=0.95, llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=None, llm_unique_calls=budget, graph_ga_unique_calls=budget,
            analyzer=True, analyzer_parse_rate=1.0, analyzer_calls=10, analyzer_parsed=10,
            parse_rate_healthy=True,
        )

    monkeypatch.setattr(sweep_mod, "run_head_to_head", fake_h2h)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="week8")
    assert report.mode == "week8"
    assert report.beats == 1
    assert seen == {"qed": True, "jnk3": True}  # week8 always runs the analyzer arm
    assert report.rows[0].payload["parse_rate_healthy"] is True
    assert report.auc_sum == pytest.approx(0.40 + 0.60)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py::test_week8_mode_runs_with_analyzer_and_counts_beats -x`
Expected: FAIL — `ValueError: Use a known sweep mode (...); got 'week8'`.

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/eval/sweep.py`, add a `week8` branch in `_run_one` (after the `head_to_head` branch):

```python
    if mode == "week8":
        v = run_head_to_head(
            task, budget, seed,
            pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
            analyzer=True,
        )
        return SweepRow(task=task, ok=True, headline_auc=v.llm_auc, beat=v.beat, payload=asdict(v))
```

Add `"week8"` to BOTH mode-validation tuples (the one in `_run_one`'s final `raise` and the guard at the top of `run_sweep`):

```python
    if mode not in ("reproduce", "head_to_head", "analyzer_verdict", "week8"):
        raise ValueError(
            "Use a known sweep mode (reproduce|head_to_head|analyzer_verdict|week8); "
            f"got {mode!r}."
        )
```

(Update the `_run_one` trailing `raise ValueError(...)` message string identically.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py -x`
Expected: PASS (new test + all existing sweep tests, incl. `test_unknown_mode_raises`).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/sweep.py packages/core/tests/test_eval_sweep.py
git commit -m "feat(eval): week8 sweep mode (with-analyzer-LLM vs Graph-GA)"
```

---

### Task 3: `week8_verdict` guarded reader

**Files:**
- Modify: `packages/core/capychem/eval/sweep.py`
- Test: `packages/core/tests/test_eval_sweep.py`

**Interfaces:**
- Consumes: a `week8`-mode `SweepReport` whose rows carry `asdict(BeatVerdict)` payloads.
- Produces: `week8_verdict(report: SweepReport) -> dict[str, Any]` with keys `trustworthy_beats: int`, `raw_beats: int|None`, `on_track: bool`, `degraded_tasks: list[str]`, `week8_verdict: str`.

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_sweep.py` (import `week8_verdict` at the top: `from capychem.eval.sweep import run_sweep, week8_verdict`):

```python
def _week8_row(task, *, beat, valid_passed=True, parse_healthy=True):  # type: ignore[no-untyped-def]
    from capychem.eval.sweep import SweepRow
    return SweepRow(
        task=task, ok=True, headline_auc=0.6 if beat else 0.4, beat=beat,
        payload={
            "beat": beat,
            "llm_valid_gate": {"threshold": 0.8, "passed": valid_passed},
            "parse_rate_healthy": parse_healthy,
        },
    )


def test_week8_verdict_counts_only_guarded_beats() -> None:
    from capychem.eval.sweep import SweepReport
    rows = [
        _week8_row("jnk3", beat=True),                                   # trustworthy
        _week8_row("median1", beat=True),                               # trustworthy
        _week8_row("median2", beat=True),                               # trustworthy -> >=3
        _week8_row("sitagliptin_mpo", beat=True, parse_healthy=False),  # degraded, excluded
        _week8_row("zaleplon_mpo", beat=False),                         # no beat
        _week8_row("perindopril_mpo", beat=True, valid_passed=False),   # degraded, excluded
    ]
    report = SweepReport(
        mode="week8", budget=10000, seed=42, tasks_run=6, tasks_failed=0,
        auc_sum=0.0, published_sum=0.0, beats=4, rows=rows,
    )
    out = week8_verdict(report)
    assert out["trustworthy_beats"] == 3
    assert out["raw_beats"] == 4
    assert out["on_track"] is True
    assert set(out["degraded_tasks"]) == {"sitagliptin_mpo", "perindopril_mpo"}
    assert "CLEARED" in out["week8_verdict"]


def test_week8_verdict_inconclusive_below_three() -> None:
    from capychem.eval.sweep import SweepReport
    rows = [_week8_row("jnk3", beat=True), _week8_row("median1", beat=False)]
    report = SweepReport(
        mode="week8", budget=10000, seed=42, tasks_run=2, tasks_failed=0,
        auc_sum=0.0, published_sum=0.0, beats=1, rows=rows,
    )
    out = week8_verdict(report)
    assert out["trustworthy_beats"] == 1
    assert out["on_track"] is False
    assert "INCONCLUSIVE" in out["week8_verdict"]
    assert "NOT a clean pivot" in out["week8_verdict"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py::test_week8_verdict_counts_only_guarded_beats -x`
Expected: FAIL — `ImportError: cannot import name 'week8_verdict'`.

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/eval/sweep.py`, add the function (after `run_sweep`):

```python
def week8_verdict(report: SweepReport) -> dict[str, Any]:
    """Guarded Week-8 read over a ``week8`` SweepReport.

    A beat counts only if BOTH the with-analyzer arm's valid-SMILES gate passed AND
    the analyzer parse-rate is healthy — a $0-balance mid-run silently degrades the
    LLM arm to Graph-GA (the slice-02 failure mode), which the guards catch. On a
    SUBSET, <3 trustworthy beats is INCONCLUSIVE, not "<3/23" -> not a clean pivot.
    """
    trustworthy = 0
    degraded: list[str] = []
    for r in report.rows:
        if not r.ok:
            continue
        gate = r.payload.get("llm_valid_gate")
        guards_ok = bool(gate and gate.get("passed")) and bool(
            r.payload.get("parse_rate_healthy")
        )
        if not guards_ok:
            degraded.append(r.task)
            continue
        if r.payload.get("beat"):
            trustworthy += 1
    on_track = trustworthy >= 3
    if on_track:
        verdict = (
            f"Week-8 bar CLEARED: {trustworthy} trustworthy beats (>=3 of the 23 PMO "
            "tasks) -> on track."
        )
    else:
        verdict = (
            f"INCONCLUSIVE: {trustworthy} trustworthy beats of {report.tasks_run} tasks "
            "run (<3). On a subset this cannot conclude <3/23 -> NOT a clean pivot; "
            "resolve with more budget."
        )
    return {
        "trustworthy_beats": trustworthy,
        "raw_beats": report.beats,
        "on_track": on_track,
        "degraded_tasks": degraded,
        "week8_verdict": verdict,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_sweep.py -x`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/sweep.py packages/core/tests/test_eval_sweep.py
git commit -m "feat(eval): week8_verdict guarded reader (trustworthy beats, >=3 gate)"
```

---

### Task 4: CLI `--week8` + `--tasks` wiring

**Files:**
- Modify: `packages/core/capychem/eval/cli.py`
- Test: `packages/core/tests/test_eval_cli.py`

**Interfaces:**
- Consumes: `run_sweep(tasks, *, budget, seed, mode="week8", ...)` (Task 2) and `week8_verdict(report)` (Task 3); `PMO_TASKS` (`capychem.eval.tasks`).
- Produces: `capychem-eval --all --week8 [--tasks t1,t2,…]` emits the sweep JSON plus the `week8_verdict` keys; `--tasks` overrides the sweep task list (validated vs `PMO_TASKS`); `--week8`/`--tasks` require `--all`.

- [ ] **Step 1: Write the failing test**

Add to `packages/core/tests/test_eval_cli.py`:

```python
def test_cli_all_selects_week8_and_passes_tasks(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport, SweepRow

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        captured["tasks"] = tasks
        return SweepReport(
            mode=mode, budget=budget, seed=seed, tasks_run=1, tasks_failed=0,
            auc_sum=0.6, published_sum=0.553, beats=1,
            rows=[SweepRow(task="jnk3", ok=True, headline_auc=0.6, beat=True,
                           payload={"beat": True,
                                    "llm_valid_gate": {"threshold": 0.8, "passed": True},
                                    "parse_rate_healthy": True})],
        )

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--week8", "--tasks", "jnk3,median1", "--budget", "10000", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert captured["mode"] == "week8"
    assert captured["tasks"] == ("jnk3", "median1")
    assert report["mode"] == "week8"
    # week8 verdict keys are merged into the sweep output
    assert report["trustworthy_beats"] == 1
    assert "week8_verdict" in report and "on_track" in report


def test_cli_tasks_rejects_unknown_task(capsys) -> None:  # type: ignore[no-untyped-def]
    import pytest as _pytest
    with _pytest.raises(SystemExit):
        main(["--all", "--week8", "--tasks", "jnk3,not_a_real_task", "--budget", "10000"])
    assert "not_a_real_task" in capsys.readouterr().err


def test_cli_week8_requires_all(capsys) -> None:  # type: ignore[no-untyped-def]
    import pytest as _pytest
    with _pytest.raises(SystemExit):
        main(["--week8", "--task", "jnk3", "--budget", "10000"])
    assert "--all" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_cli.py::test_cli_all_selects_week8_and_passes_tasks -x`
Expected: FAIL — `--week8`/`--tasks` are unrecognized arguments (SystemExit 2).

- [ ] **Step 3: Write minimal implementation**

In `packages/core/capychem/eval/cli.py`, register the two new arguments (next to `--head-to-head`/`--analyzer-verdict`):

```python
    p.add_argument(
        "--week8",
        action="store_true",
        help="With --all: run with-analyzer-LLM vs vanilla Graph-GA and render the Week-8 verdict.",  # noqa: E501
    )
    p.add_argument(
        "--tasks",
        default=None,
        help="With --all: comma-separated PMO task subset to sweep (default: all 23).",
    )
```

Add a guard right after `args = p.parse_args(argv)` and the existing `--task` check:

```python
    if (args.week8 or args.tasks) and not args.all_tasks:
        p.error("--week8 and --tasks require --all")
```

In the `if args.all_tasks:` branch, replace the `mode = (...)` / `run_sweep(...)` block with task-list resolution, week8 in the mode chain, and the verdict merge:

```python
        from capychem.eval.sweep import run_sweep, week8_verdict
        from capychem.eval.tasks import PMO_TASKS

        mode = (
            "week8" if args.week8
            else "analyzer_verdict" if args.analyzer_verdict
            else "head_to_head" if args.head_to_head
            else "reproduce"
        )
        sweep_tasks = PMO_TASKS
        if args.tasks:
            sweep_tasks = tuple(t.strip() for t in args.tasks.split(",") if t.strip())
            unknown = [t for t in sweep_tasks if t not in PMO_TASKS]
            if unknown:
                p.error(f"--tasks has unknown PMO tasks: {unknown}")
        sweep_report = run_sweep(
            sweep_tasks,
            budget=args.budget, seed=args.seed, mode=mode,
            pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        sweep_out: dict[str, object] = {
            "sweep": True,
            **dataclasses.asdict(sweep_report),
            "wall_seconds": round(wall, 1),
        }
        if mode == "week8":
            sweep_out |= week8_verdict(sweep_report)
        json.dump(sweep_out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
```

(The previous `from capychem.eval.sweep import run_sweep` lazy import line is replaced by the combined import above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -x`
Expected: PASS (3 new tests + all existing CLI tests, incl. the `--all` mode-selection tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): capychem-eval --week8 + --tasks subset (Week-8 verdict in output)"
```

---

### Task 5: Cost-gate verification — analyzer spend is in the gated total

**Files:**
- Modify: `apps/api/tests/test_cost_gate.py`

**Interfaces:**
- Consumes: `RunRegistry`, `RunConfig(mutation_strategy="llm")`; the product loop's analyze node calls `strategy.run_analyzer_async(summary, *, seed) -> AnalyzerResult`. The analyze node folds `result.cost_usd` into `state["llm_cost_usd"]`; `runner.py` gates `total = oracle + llm` against `cost.cost_cap_usd()`.
- Produces: a test proving the analyzer term is inside the gated total (no production change — verification only; if it already passes, the gate is confirmed).

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_cost_gate.py`:

```python
async def test_cost_cap_trips_on_analyzer_spend(sm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Cheap proposer + zero oracle, but the ANALYZER carries a large cost_usd, so the
    # gate must trip on total_usd including the analyzer term (milestone 03 slice 05).
    from capychem.analyzer import AnalyzerResult
    from capychem.loop import graph as graph_mod
    from capychem.loop import strategy
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    async def cheap_llm(task, population, *, n, seed, hypothesis=None):
        return [
            ProposalResult(
                raw="C" * (i + 1), smiles="C" * (i + 1),
                tokens_in=1, tokens_out=1, cost_usd=0.0,
            )
            for i in range(n)
        ]

    async def fake_score(smiles, task):
        return [
            OracleResult(smiles=s, score=0.5, valid=True, wall_ms=0, cost_usd=0.0)
            for s in smiles
        ]

    async def pricey_analyzer(summary, *, seed):
        return AnalyzerResult(
            text="focus on rings", structured={"focus": "rings", "avoid": []},
            tokens_in=1000, tokens_out=1000, cost_usd=100.0,
        )

    monkeypatch.setattr(strategy, "propose_llm_async", cheap_llm)
    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    monkeypatch.setattr(strategy, "run_analyzer_async", pricey_analyzer)

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
    assert rc.oracle_cost_usd == pytest.approx(0.0)   # oracle is free here
    assert rc.llm_cost_usd >= 50.0                     # analyzer spend alone (proposer=0) caps it
    assert rc.total_usd == pytest.approx(rc.llm_cost_usd)
```

- [ ] **Step 2: Run test to verify it fails (or confirm it passes — see note)**

Run: `uv run pytest apps/api/tests/test_cost_gate.py::test_cost_cap_trips_on_analyzer_spend -x`
Expected: **PASS** is the likely outcome — the analyzer term is already folded into `state["llm_cost_usd"]` (graph.py), so this test *confirms* the wiring rather than driving a fix. If it FAILS (e.g. analyzer cost not summed), that is a real gap: fix it in `loop/graph.py`'s `_analyze` so the returned `llm_cost_usd` includes `result.cost_usd`, then re-run. (Requires a running Postgres — same as the other `test_cost_gate.py` tests.)

- [ ] **Step 3: (only if Step 2 failed) Fix the analyzer cost fold**

If and only if the test failed, ensure `_analyze` in `packages/core/capychem/loop/graph.py` returns:

```python
        return {
            "analyzer_hypothesis": effective,
            "llm_cost_usd": state.get("llm_cost_usd", 0.0) + result.cost_usd,
        }
```

- [ ] **Step 4: Run the cost-gate suite**

Run: `uv run pytest apps/api/tests/test_cost_gate.py -x`
Expected: PASS (new test + the 2 existing gate tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_cost_gate.py
git commit -m "test(api): cost gate trips on analyzer spend (combined proposer+analyzer+oracle)"
```

---

### Task 6: Full-gate check, then the real 9-task sweep (CHECKPOINT — spends money)

**Files:**
- Read/run only (no code). Output → scratchpad; verdict → the slice doc + handoff.

**Interfaces:** consumes the `--week8`/`--tasks` CLI (Task 4). Produces the rendered Week-8 verdict.

- [ ] **Step 1: Run the full local gate suite (free)**

```bash
uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .
```
Expected: all green. (No web surface touched — skip the web gates.)

- [ ] **Step 2: CHECKPOINT — confirm the operator topped up, then verify balance**

The operator tops up DeepSeek to ~$8–10. Then verify the balance covers ~9 × ~$0.7 ≈ $6.3 with margin:

```bash
set -a; source .env.local; set +a
curl -s -H "Authorization: Bearer $DEEPSEEK_API_KEY" https://api.deepseek.com/user/balance
```
Expected: `is_available: true`, `total_balance` ≥ ~$7. **Do not launch below ~$7** — a mid-run $0 degrades arms (the two-guard read will catch it, but avoid wasting the run). Record the starting balance (for the spend delta).

- [ ] **Step 3: Launch the 9-task sweep in the background (detached; ~hours)**

```bash
set -a; source .env.local; set +a
CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct \
  uv run capychem-eval --all --week8 \
  --tasks jnk3,median1,median2,sitagliptin_mpo,zaleplon_mpo,troglitazone_rediscovery,perindopril_mpo,scaffold_hop,thiothixene_rediscovery \
  --budget 10000 --seed 42 \
  > "$SCRATCH/week8_sweep_seed42.json" 2> "$SCRATCH/week8_sweep_seed42.log"
```
(Run via the Bash tool with `run_in_background: true`; `$SCRATCH` = the session scratchpad dir. Per-task error isolation means one failing task does not abort the sweep.)

- [ ] **Step 4: Two-guard read on every arm + record the verdict**

When the run completes, parse `week8_sweep_seed42.json`:
- For **every** row: confirm `payload.llm_valid_gate.passed is true` AND `payload.parse_rate_healthy is true`. Any arm failing a guard appears in `degraded_tasks` and is excluded from `trustworthy_beats` — report it honestly, do not silently count it.
- Read `trustworthy_beats`, `on_track`, `week8_verdict`.
- Re-check the DeepSeek balance; record the spend delta (expect ≈ $6).

- [ ] **Step 5: Render the verdict into the slice doc**

Fill the slice doc's results table (per-task: `llm_auc`, `graph_ga_auc`, `diff`, `beat`, `llm_valid_gate.passed`, `parse_rate_healthy`) and the Week-8 decision: `on_track` → "≥3 trustworthy beats, on track"; else → "INCONCLUSIVE on a 9-task subset (not a clean pivot)". Commit the sweep JSON under `docs/03-analyzer-and-scale/` or reference the scratchpad path in the doc. Note: cost gate "stays under" is demonstrated by the ≈$0.7/arm spend ≪ $50 cap (Task 5 shows it "fires").

```bash
git add docs/03-analyzer-and-scale/05-week8-sweep-and-gate.md
git commit -m "docs(slice-05): Week-8 sweep verdict — <N> trustworthy beats on the 9-task subset"
```

---

### Task 7: Ship the slice

**Files:**
- Modify: `docs/03-analyzer-and-scale/milestone.md`, `docs/03-analyzer-and-scale/handoff.md`
- Freeze: `docs/03-analyzer-and-scale/05-week8-sweep-and-gate.md`

- [ ] **Step 1: Flip statuses + advance pointers (one commit on the branch)**

- `milestone.md` "Slices" list: slice 05 `planned → shipped (2026-06-29)` with the verdict one-liner; Exit criteria #8 + #9 → MET (cite the trustworthy-beats count).
- `handoff.md`: "Slice status across milestone" flip 05 → shipped; "Next session start here" → slice 03 `analyzer-live-surface` (the remaining planned slice, no eval cost) OR the m04 G1 push, per the verdict; "Completed this session" → slice-05 commit refs; append a dated "Slice 05 shipped" log line.
- Freeze the slice doc (no further edits).

- [ ] **Step 2: Final gate + merge to main (ff, local; do not push unless asked)**

```bash
uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .
git add docs/03-analyzer-and-scale/
git commit -m "docs(slice-05): ship week-8-sweep-and-gate — <verdict one-liner>"
git checkout main && git merge --ff-only slice-05-week8-sweep-and-gate
```
Expected: clean ff-merge; `main` advances. Leave pushing to the operator (per slice-06 pattern: do not push unless asked).

---

## Self-Review

**1. Spec coverage:**
- Comparator exists + TDD on stub + canonical path → Tasks 1–4. ✓
- 9-task subset run for real; both guards on every arm → Task 6. ✓
- Week-8 verdict rendered (count + table; ≥3 on track / <3 inconclusive) → Tasks 3, 6. ✓
- Cost gate fires on combined spend + run stays under → Task 5 (fires) + Task 6 step 4 (stays under). ✓
- Gates green + ship docs → Tasks 6 (step 1), 7. ✓
- Non-goals (live WS surface, compare view, G1 full-23, expensive oracles, headless dollar tracking) — none built. ✓

**2. Placeholder scan:** No TBD/"add error handling"/"similar to Task N". Every code step has complete code. `<N>` / `<verdict one-liner>` in Tasks 6–7 commit messages are run-dependent values filled at execution, not plan placeholders. ✓

**3. Type consistency:** `BeatVerdict` new fields (`analyzer`, `analyzer_parse_rate`, `analyzer_calls`, `analyzer_parsed`, `parse_rate_healthy`) are defined in Task 1 and consumed unchanged in Tasks 2–4. `week8_verdict(report) -> dict` keys (`trustworthy_beats`, `raw_beats`, `on_track`, `degraded_tasks`, `week8_verdict`) defined in Task 3, consumed in Task 4. `run_sweep(tasks, *, mode="week8")` and `run_head_to_head(..., analyzer=True)` signatures consistent across tasks. ✓
