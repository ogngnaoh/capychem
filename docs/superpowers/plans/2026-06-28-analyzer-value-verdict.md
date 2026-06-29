# Analyzer Value Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the milestone-03 differentiator kill-switch — does the analyzer add AUC-of-top-10 value on jnk3 (with-analyzer LLM vs without-analyzer LLM, same seed)? — with a `parse_hypothesis` success-rate guard that prevents a CoT-truncation false null.

**Architecture:** Three small headless-`eval/` code tasks (parse-rate instrumentation on `run_reproduction`; a `verdict.py` module mirroring `beat.py`; a `--analyzer-verdict` CLI branch), all TDD on the free deterministic stub backends, followed by one real `direct`-backend experiment task that runs the single-seed jnk3 verdict and records the kill-switch decision. No product loop / WS / UI / Postgres changes.

**Tech Stack:** Python 3.12, uv workspace (`packages/core`), pytest + mypy strict + ruff, DeepSeek-v4-pro via the `direct` backend (real run only), the canonical PMO `top_auc` metric.

## Global Constraints

- **AUC is `eval/metric.top_auc` only** — `top_n=10`, `max_oracle_calls=budget`; never recompute AUC ad hoc.
- **Backends:** dev + ALL tests on `stub` (free, deterministic, network-free); `direct` only for the real verdict (Task 4). Tests must never make a DeepSeek call.
- **Reasoning:** analyzer reasoning ON (`analyzer.py` owns this); proposer reasoning OFF — never cross-contaminate the two prompts/payloads.
- **Untouched:** `proposer.py`, `tests/test_proposer.py`, `eval/beat.py`, `tests/test_eval_beat.py`, the product loop (`loop/graph.py`), WS, UI, DB schema.
- **`analyzer.py` may change ONLY `_ANALYZER_MAX_OUTPUT_TOKENS`**, and only if Task 4's smoke shows CoT truncating the JSON.
- **Parse-rate floor = 0.8** (mirrors the valid-SMILES gate). A with-arm parse-rate `< 0.8` makes the verdict INVALID, not null.
- **Real verdict scope = one seed (42)** (sized to the ~$2.37 prepaid DeepSeek balance); documented as a single observation, not a robustness claim.
- **PRD N6:** every score is an in-silico oracle score; no real-world drug-discovery efficacy claims in code/docs.
- **Per-task gate:** `uv run pytest` · `uv run mypy -p capychem -p capychem.api` · `uv run ruff check .` — all green before commit.

---

## File Structure

- **`packages/core/capychem/eval/runner.py`** (modify) — `ReproResult` gains `analyzer_calls`, `analyzer_parsed`, `analyzer_parse_rate`; `run_reproduction` counts raw parse successes in the analyzer branch. (Task 1)
- **`packages/core/capychem/eval/verdict.py`** (create) — `AnalyzerVerdict` dataclass + `run_analyzer_verdict(...)`; `_PARSE_RATE_FLOOR`. (Task 2)
- **`packages/core/capychem/eval/cli.py`** (modify) — `--analyzer-verdict` flag + report branch with a three-way `verdict` string. (Task 3)
- **`packages/core/tests/test_eval_runner.py`** (modify) — parse-rate field tests. (Task 1)
- **`packages/core/tests/test_eval_verdict.py`** (create) — verdict shape / determinism / parse-rate-healthy boundary. (Task 2)
- **`packages/core/tests/test_eval_cli.py`** (modify) — `--analyzer-verdict` report wiring. (Task 3)
- **`packages/core/capychem/analyzer.py`** (conditional modify, Task 4 only) — `_ANALYZER_MAX_OUTPUT_TOKENS` bump if truncating.
- **`docs/03-analyzer-and-scale/02-analyzer-value-verdict.md`** + **`handoff.md`** + **`milestone.md`** — slice doc + status flips, recording the verdict. (Task 4)

---

### Task 1: Parse-rate instrumentation on the headless runner

**Files:**
- Modify: `packages/core/capychem/eval/runner.py`
- Test: `packages/core/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `run_analyzer_sync(summary, *, seed) -> AnalyzerResult` (already imported into `runner.py`); `AnalyzerResult.structured: dict | None`.
- Produces: `ReproResult.analyzer_calls: int`, `ReproResult.analyzer_parsed: int`, `ReproResult.analyzer_parse_rate: float | None` (read by Task 2).

- [ ] **Step 1: Write the failing tests**

Append to `packages/core/tests/test_eval_runner.py`:

```python
def test_analyzer_parse_rate_all_parsed_on_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # stub analyzer always returns a structured hypothesis -> parse_rate == 1.0.
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        return [
            ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                           tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction("qed", budget=40, seed=42, pop_size=3, offspring=4,
                           patience=9, mutation_strategy="llm", analyzer=True)
    assert res.analyzer_calls > 0
    assert res.analyzer_parsed == res.analyzer_calls
    assert res.analyzer_parse_rate == 1.0


def test_analyzer_parse_rate_counts_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real CoT-truncation failure returns structured=None. The counter must track
    # the RAW result (before resolve_effective_hypothesis re-injects last-good), so a
    # fallback cannot masquerade as a parse success. This is the load-bearing guard.
    from capychem.analyzer import AnalyzerResult
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]
    n_calls = {"n": 0}

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        return [
            ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                           tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    def fake_analyzer(summary, *, seed):  # type: ignore[no-untyped-def]
        n_calls["n"] += 1
        # every other call "truncates" (structured=None), like a CoT-crowded JSON tail
        structured = {"focus": "f", "avoid": ["a"]} if n_calls["n"] % 2 == 1 else None
        return AnalyzerResult(
            text="x", structured=structured, tokens_in=0, tokens_out=0,
            note=None if structured is not None else "no new signal",
        )

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "run_analyzer_sync", fake_analyzer)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction("qed", budget=40, seed=42, pop_size=3, offspring=4,
                           patience=9, mutation_strategy="llm", analyzer=True)
    assert res.analyzer_calls >= 2
    assert res.analyzer_parsed < res.analyzer_calls
    assert res.analyzer_parse_rate is not None
    assert 0.0 < res.analyzer_parse_rate < 1.0


def test_analyzer_off_has_none_parse_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        return [
            ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                           tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction("qed", budget=20, seed=42, pop_size=3, offspring=4,
                           patience=2, mutation_strategy="llm")  # analyzer defaults False
    assert res.analyzer_calls == 0
    assert res.analyzer_parsed == 0
    assert res.analyzer_parse_rate is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -k "parse_rate or none_parse_rate" -v`
Expected: FAIL — `AttributeError: 'ReproResult' object has no attribute 'analyzer_calls'` (and `analyzer_parse_rate`).

- [ ] **Step 3: Add the fields to `ReproResult`**

In `packages/core/capychem/eval/runner.py`, extend the dataclass:

```python
@dataclass(frozen=True)
class ReproResult:
    mol_buffer: dict[str, tuple[float, int]]
    generations: int
    unique_calls: int
    llm_proposed: int = 0
    llm_valid: int = 0
    valid_rate: float | None = None
    analyzer_calls: int = 0
    analyzer_parsed: int = 0
    analyzer_parse_rate: float | None = None
```

- [ ] **Step 4: Count raw parse successes in the analyzer branch**

In `run_reproduction`, initialize counters next to `llm_proposed`/`llm_valid` (just before the `while` loop):

```python
    llm_proposed = 0
    llm_valid = 0
    analyzer_calls = 0
    analyzer_parsed = 0
```

Then update the analyzer branch (count on the RAW result, BEFORE `resolve_effective_hypothesis`):

```python
        if analyzer and mutation_strategy == "llm":
            summary = build_analyzer_summary(population, score_history, hypothesis)
            # `generations` was already incremented above, so generation N's analyzer
            # seed must be seed+N — matching the product node's seed+gen_index for the
            # generation just scored (G6 parity). Hence `generations - 1`.
            result = run_analyzer_sync(summary, seed=seed + generations - 1)
            analyzer_calls += 1
            if result.structured is not None:
                analyzer_parsed += 1
            hypothesis = resolve_effective_hypothesis(result, hypothesis)
```

And at the return, compute the rate and pass the new fields:

```python
    valid_rate = (llm_valid / llm_proposed) if llm_proposed else None
    analyzer_parse_rate = (analyzer_parsed / analyzer_calls) if analyzer_calls else None
    return ReproResult(
        mol_buffer=mol_buffer,
        generations=generations,
        unique_calls=len(mol_buffer),
        llm_proposed=llm_proposed,
        llm_valid=llm_valid,
        valid_rate=valid_rate,
        analyzer_calls=analyzer_calls,
        analyzer_parsed=analyzer_parsed,
        analyzer_parse_rate=analyzer_parse_rate,
    )
```

- [ ] **Step 5: Run the full runner suite to verify pass + no regression**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -v`
Expected: PASS (new parse-rate tests + all existing runner tests, incl. `test_analyzer_threads_hypothesis_in_headless_llm`).

- [ ] **Step 6: Gate + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: clean.

```bash
git add packages/core/capychem/eval/runner.py packages/core/tests/test_eval_runner.py
git commit -m "feat(eval): instrument analyzer parse-hypothesis success rate in run_reproduction

ReproResult gains analyzer_calls/analyzer_parsed/analyzer_parse_rate, counted on
the RAW analyzer result before resolve_effective_hypothesis — so a 'no new signal'
fallback cannot mask a CoT-truncation parse failure. Guards the slice-02 verdict.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `eval/verdict.py` — the with/without-analyzer verdict

**Files:**
- Create: `packages/core/capychem/eval/verdict.py`
- Test: `packages/core/tests/test_eval_verdict.py`

**Interfaces:**
- Consumes: `run_reproduction(task, budget, seed, *, pop_size, offspring, mutation_rate, mutation_strategy, analyzer) -> ReproResult` (with the Task-1 fields); `top_auc(buffer, top_n=10, max_oracle_calls=budget) -> float`.
- Produces: `AnalyzerVerdict` (frozen dataclass, fields below) + `run_analyzer_verdict(task, budget, seed, *, pop_size=120, offspring=70, mutation_rate=0.067) -> AnalyzerVerdict` + module constant `_PARSE_RATE_FLOOR = 0.8` (consumed by Task 3).

- [ ] **Step 1: Write the failing tests**

Create `packages/core/tests/test_eval_verdict.py`:

```python
import pytest
from capychem.eval import verdict as verdict_mod
from capychem.eval.runner import ReproResult
from capychem.eval.verdict import AnalyzerVerdict, run_analyzer_verdict


def _stub(monkeypatch: pytest.MonkeyPatch, llm_pool: list[str]) -> None:
    # Harness-free, deterministic. The fake LLM is hypothesis-SENSITIVE so the
    # with-arm (conditioned from gen 2) and without-arm produce different buffers
    # -> a real, non-zero AUC delta to assert on.
    from capychem.analyzer import AnalyzerResult
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [
            OracleResult(smiles=s, score=min(0.99, 0.3 + 0.05 * len(s)), valid=True, wall_ms=1)
            for s in smiles
        ]

    def fake_llm(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        conditioned = hypothesis is not None and hypothesis.structured is not None
        base = llm_pool[1] if conditioned else llm_pool[0]
        return [
            ProposalResult(raw=base * (i + 1), smiles=base * (i + 1), tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_analyzer(summary, *, seed):  # type: ignore[no-untyped-def]
        return AnalyzerResult(
            text="focus", structured={"focus": "f", "avoid": ["a"]}, tokens_in=0, tokens_out=0
        )

    monkeypatch.setattr(verdict_mod, "run_reproduction", run_real)  # placeholder; see below
    monkeypatch.setattr(runner_for_verdict := __import__(
        "capychem.eval.runner", fromlist=["x"]), "score_smiles", fake_score)
    monkeypatch.setattr(runner_for_verdict, "propose_llm_sync", fake_llm)
    monkeypatch.setattr(runner_for_verdict, "run_analyzer_sync", fake_analyzer)
    monkeypatch.setattr(runner_for_verdict, "starting_population",
                        lambda nn: ["C", "CC", "CCC", "CCCC", "CCCCC"][:nn])


# run_analyzer_verdict calls the REAL run_reproduction (which we stub at the
# runner-module level), so do NOT replace it; the line above is removed in the
# actual test (kept minimal here). See concrete version below.


def _patch_runner(monkeypatch: pytest.MonkeyPatch, llm_pool: list[str]) -> None:
    from capychem.analyzer import AnalyzerResult
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [
            OracleResult(smiles=s, score=min(0.99, 0.3 + 0.05 * len(s)), valid=True, wall_ms=1)
            for s in smiles
        ]

    def fake_llm(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        conditioned = hypothesis is not None and hypothesis.structured is not None
        base = llm_pool[1] if conditioned else llm_pool[0]
        return [
            ProposalResult(raw=base * (i + 1), smiles=base * (i + 1), tokens_in=0, tokens_out=0)
            for i in range(n)
        ]

    def fake_analyzer(summary, *, seed):  # type: ignore[no-untyped-def]
        return AnalyzerResult(
            text="focus", structured={"focus": "f", "avoid": ["a"]}, tokens_in=0, tokens_out=0
        )

    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm)
    monkeypatch.setattr(runner_mod, "run_analyzer_sync", fake_analyzer)
    monkeypatch.setattr(runner_mod, "starting_population",
                        lambda nn: ["C", "CC", "CCC", "CCCC", "CCCCC"][:nn])


def test_verdict_shape_and_determinism(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(monkeypatch, llm_pool=["C", "O"])
    v1 = run_analyzer_verdict("qed", budget=40, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert isinstance(v1, AnalyzerVerdict)
    assert v1.task == "qed" and v1.seed == 42 and v1.budget == 40
    assert abs(v1.diff - (v1.with_auc - v1.without_auc)) < 1e-12
    assert v1.helps == (v1.with_auc > v1.without_auc)
    # stub analyzer always parses -> healthy
    assert v1.analyzer_parse_rate == 1.0
    assert v1.parse_rate_healthy is True
    assert v1.analyzer_calls > 0 and v1.analyzer_parsed == v1.analyzer_calls
    # same seed -> identical verdict (G6 on the deterministic stub path)
    v2 = run_analyzer_verdict("qed", budget=40, seed=42, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v2 == v1


def test_verdict_arms_differ_when_analyzer_conditions_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # hypothesis-sensitive fake LLM -> with-arm and without-arm explore different
    # molecules -> different buffers -> the verdict is a real comparison, not a no-op.
    _patch_runner(monkeypatch, llm_pool=["C", "O"])
    v = run_analyzer_verdict("qed", budget=60, seed=7, pop_size=3, offspring=4, mutation_rate=0.01)
    assert v.with_unique_calls != v.without_unique_calls or v.with_auc != v.without_auc


def test_parse_rate_healthy_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    # Drive run_reproduction's return directly to pin the 0.8 floor. The with-arm
    # (analyzer=True) carries the parse rate; the without-arm has analyzer off.
    def make(rate: float) -> ReproResult:
        parsed = round(rate * 100)
        return ReproResult(
            mol_buffer={"CCO": (0.5, 1)}, generations=2, unique_calls=1,
            analyzer_calls=100, analyzer_parsed=parsed, analyzer_parse_rate=rate,
        )

    off = ReproResult(mol_buffer={"CCN": (0.4, 1)}, generations=2, unique_calls=1)

    def make_fake(rate: float):  # type: ignore[no-untyped-def]
        def fake_run(task, budget, seed, *, analyzer=False, **kw):  # type: ignore[no-untyped-def]
            return make(rate) if analyzer else off
        return fake_run

    monkeypatch.setattr(verdict_mod, "run_reproduction", make_fake(0.80))
    assert run_analyzer_verdict("qed", budget=100, seed=1).parse_rate_healthy is True

    monkeypatch.setattr(verdict_mod, "run_reproduction", make_fake(0.79))
    v = run_analyzer_verdict("qed", budget=100, seed=1)
    assert v.parse_rate_healthy is False
    assert v.analyzer_parse_rate == 0.79
```

> Note: the first `_stub` helper above is illustrative scaffolding — delete it and keep only `_patch_runner` + the three `test_*` functions in the committed file. (Kept here so the reviewer sees why the runner-module-level patch, not a `verdict_mod.run_reproduction` patch, is correct for the determinism test: `run_analyzer_verdict` must exercise the REAL `run_reproduction`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_eval_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.eval.verdict'`.

- [ ] **Step 3: Create the verdict module**

Create `packages/core/capychem/eval/verdict.py`:

```python
"""With/without-analyzer value verdict: does the analyzer add AUC-of-top-10 value?

The milestone-03 slice-02 differentiator kill-switch (SPEC §9 / PROJECT §9). Both
arms run the headless ``run_reproduction`` with the LLM proposer at the SAME seed —
the only difference is the analyzer (off vs on), which first conditions the proposer
at generation 2. Both are measured with the canonical PMO ``top_auc`` (never ad hoc).
The with-arm's ``parse_hypothesis`` success rate guards the verdict: below
``_PARSE_RATE_FLOOR`` the reasoning-mode chain-of-thought is crowding out the
{focus, avoid} JSON, so a null is untrustworthy (raise analyzer max_tokens, rerun).
Every score is an in-silico oracle score (PRD N6).
"""

from __future__ import annotations

from dataclasses import dataclass

from capychem.eval.metric import top_auc
from capychem.eval.runner import run_reproduction

# Mirror the valid-SMILES gate: below this the with-arm's hypotheses are not really
# parsing, so the AUC delta is not a true with/without comparison.
_PARSE_RATE_FLOOR = 0.8


@dataclass(frozen=True)
class AnalyzerVerdict:
    task: str
    seed: int
    budget: int
    with_auc: float
    without_auc: float
    diff: float  # with_auc - without_auc
    helps: bool  # with_auc > without_auc
    analyzer_parse_rate: float | None
    analyzer_calls: int
    analyzer_parsed: int
    parse_rate_healthy: bool
    with_valid_rate: float | None
    without_valid_rate: float | None
    with_unique_calls: int
    without_unique_calls: int


def run_analyzer_verdict(
    task: str,
    budget: int,
    seed: int,
    *,
    pop_size: int = 120,
    offspring: int = 70,
    mutation_rate: float = 0.067,
) -> AnalyzerVerdict:
    """Run llm-with-analyzer and llm-without-analyzer same-seed, measure both via
    ``top_auc``, return the verdict. The analyzer is the only treatment difference."""
    with_a = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="llm", analyzer=True,
    )
    without_a = run_reproduction(
        task, budget, seed,
        pop_size=pop_size, offspring=offspring, mutation_rate=mutation_rate,
        mutation_strategy="llm", analyzer=False,
    )
    with_auc = top_auc(with_a.mol_buffer, top_n=10, max_oracle_calls=budget)
    without_auc = top_auc(without_a.mol_buffer, top_n=10, max_oracle_calls=budget)
    rate = with_a.analyzer_parse_rate
    return AnalyzerVerdict(
        task=task,
        seed=seed,
        budget=budget,
        with_auc=with_auc,
        without_auc=without_auc,
        diff=with_auc - without_auc,
        helps=with_auc > without_auc,
        analyzer_parse_rate=rate,
        analyzer_calls=with_a.analyzer_calls,
        analyzer_parsed=with_a.analyzer_parsed,
        parse_rate_healthy=(rate is not None and rate >= _PARSE_RATE_FLOOR),
        with_valid_rate=with_a.valid_rate,
        without_valid_rate=without_a.valid_rate,
        with_unique_calls=with_a.unique_calls,
        without_unique_calls=without_a.unique_calls,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_verdict.py -v`
Expected: PASS (shape/determinism, arms-differ, 0.8 boundary).

- [ ] **Step 5: Gate + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: clean.

```bash
git add packages/core/capychem/eval/verdict.py packages/core/tests/test_eval_verdict.py
git commit -m "feat(eval): with/without-analyzer value verdict (eval/verdict.py)

run_analyzer_verdict runs llm-with-analyzer vs llm-without-analyzer same-seed,
measures both via canonical top_auc, and surfaces the with-arm parse-rate with a
0.8 health floor. Mirrors eval/beat.py; the differentiator kill-switch comparator.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `--analyzer-verdict` CLI mode

**Files:**
- Modify: `packages/core/capychem/eval/cli.py`
- Test: `packages/core/tests/test_eval_cli.py`

**Interfaces:**
- Consumes: `run_analyzer_verdict(...)` + `AnalyzerVerdict` (Task 2).
- Produces: a JSON report on stdout with keys `task, seed, budget, analyzer_verdict, with_auc, without_auc, diff, helps, analyzer_parse_rate, analyzer_calls, analyzer_parsed, parse_rate_healthy, with_valid_rate, without_valid_rate, with_unique_calls, without_unique_calls, verdict, wall_seconds`.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_eval_cli.py`:

```python
def test_cli_analyzer_verdict_report(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # Stub the verdict so the CLI test runs no eval and makes no DeepSeek call —
    # the wiring (flag -> run_analyzer_verdict -> report + verdict string) is under test.
    from capychem.eval import verdict as verdict_mod
    from capychem.eval.verdict import AnalyzerVerdict

    def fake_verdict(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.72, without_auc=0.66, diff=0.06, helps=True,
            analyzer_parse_rate=0.95, analyzer_calls=20, analyzer_parsed=19,
            parse_rate_healthy=True,
            with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=2600, without_unique_calls=3100,
        )

    monkeypatch.setattr(verdict_mod, "run_analyzer_verdict", fake_verdict)
    rc = main(["--task", "jnk3", "--budget", "10000", "--seed", "42", "--analyzer-verdict"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["analyzer_verdict"] is True
    assert report["task"] == "jnk3" and report["seed"] == 42 and report["budget"] == 10000
    assert report["with_auc"] == 0.72 and report["without_auc"] == 0.66
    assert report["diff"] == 0.06 and report["helps"] is True
    assert report["analyzer_parse_rate"] == 0.95 and report["parse_rate_healthy"] is True
    assert report["analyzer_calls"] == 20 and report["analyzer_parsed"] == 19
    assert report["with_unique_calls"] == 2600 and report["without_unique_calls"] == 3100
    assert "ADDS value" in report["verdict"]
    assert "wall_seconds" in report


def test_cli_analyzer_verdict_invalid_when_parse_rate_unhealthy(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import verdict as verdict_mod
    from capychem.eval.verdict import AnalyzerVerdict

    def fake_verdict(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.50, without_auc=0.55, diff=-0.05, helps=False,
            analyzer_parse_rate=0.40, analyzer_calls=20, analyzer_parsed=8,
            parse_rate_healthy=False,
            with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=2600, without_unique_calls=3100,
        )

    monkeypatch.setattr(verdict_mod, "run_analyzer_verdict", fake_verdict)
    rc = main(["--task", "jnk3", "--budget", "10000", "--seed", "42", "--analyzer-verdict"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    # an unhealthy parse-rate must read INVALID, never as a clean null
    assert report["parse_rate_healthy"] is False
    assert "INVALID" in report["verdict"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -k analyzer_verdict -v`
Expected: FAIL — argparse rejects the unknown `--analyzer-verdict` flag (SystemExit 2).

- [ ] **Step 3: Add the flag + report branch**

In `packages/core/capychem/eval/cli.py`, add the argument next to `--head-to-head`:

```python
    p.add_argument(
        "--analyzer-verdict",
        action="store_true",
        help="Run llm with-analyzer vs without-analyzer same-seed on --task; emit the value verdict.",
    )
```

Then add the branch immediately after the `if args.head_to_head:` block returns (before the plain `run_reproduction` call):

```python
    if args.analyzer_verdict:
        from capychem.eval.verdict import run_analyzer_verdict

        v = run_analyzer_verdict(
            args.task,
            args.budget,
            args.seed,
            pop_size=args.pop_size,
            offspring=args.offspring,
            mutation_rate=args.mutation_rate,
        )
        wall = time.monotonic() - t0
        if not v.parse_rate_healthy:
            verdict_str = "INVALID — analyzer parse-rate <0.8; raise analyzer max_tokens and rerun"
        elif v.helps:
            verdict_str = "analyzer ADDS value (with_auc > without_auc)"
        else:
            verdict_str = (
                "analyzer NULL (with_auc <= without_auc) — "
                "pivot to analyzer-only narrative, do not abandon"
            )
        av_report: dict[str, object] = {
            "task": v.task,
            "seed": v.seed,
            "budget": v.budget,
            "analyzer_verdict": True,
            "with_auc": v.with_auc,
            "without_auc": v.without_auc,
            "diff": v.diff,
            "helps": v.helps,
            "analyzer_parse_rate": v.analyzer_parse_rate,
            "analyzer_calls": v.analyzer_calls,
            "analyzer_parsed": v.analyzer_parsed,
            "parse_rate_healthy": v.parse_rate_healthy,
            "with_valid_rate": v.with_valid_rate,
            "without_valid_rate": v.without_valid_rate,
            "with_unique_calls": v.with_unique_calls,
            "without_unique_calls": v.without_unique_calls,
            "verdict": verdict_str,
            "wall_seconds": round(wall, 1),
        }
        json.dump(av_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_cli.py -v`
Expected: PASS (both new analyzer-verdict tests + existing CLI tests).

- [ ] **Step 5: Gate + commit**

Run: `uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: clean.

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): --analyzer-verdict CLI mode with three-way verdict string

Emits the with/without-analyzer report; an unhealthy parse-rate reads INVALID
(never a clean null), helps reads ADDS-value, else NULL/pivot.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Run the real `direct` jnk3 verdict and record the kill-switch decision

> **Real-$ task — the slice deliverable.** Uses the `direct` backends (real DeepSeek). Do NOT run as part of the automated suite. Single seed (42), per the approved scope.

**Files:**
- Conditional modify: `packages/core/capychem/analyzer.py` (`_ANALYZER_MAX_OUTPUT_TOKENS` only, if truncating).
- Create: `docs/03-analyzer-and-scale/02-analyzer-value-verdict.md` (slice doc, with the verdict table).
- Modify: `docs/03-analyzer-and-scale/handoff.md`, `docs/03-analyzer-and-scale/milestone.md` (status flips, verdict record).

- [ ] **Step 1: Confirm the DeepSeek balance covers the run**

Confirm the prepaid balance is comfortably above the ~$1.2–2.0 estimate BEFORE starting (a $0 balance mid-run degrades the LLM arm to Graph-GA via the 402→transient path, silently corrupting the verdict). If the balance is tight, stop and report — do not start a run that could degrade.

- [ ] **Step 2: Parse-rate smoke — one direct analyzer call (~$0.01–0.05)**

Run a single real analyzer call on a realistic jnk3 summary and inspect token headroom + parse success:

```bash
CAPYCHEM_ANALYZER_BACKEND=direct DEEPSEEK_API_KEY=<key> uv run python - <<'PY'
import asyncio
from capychem.loop.state import Scored
from capychem.loop.logic import build_analyzer_summary
from capychem.loop.strategy import build_analyzer_prompt
from capychem.analyzer import analyze_async, _ANALYZER_MAX_OUTPUT_TOKENS, parse_hypothesis

# a small, plausible jnk3-ish survivor pool (scores are illustrative, in [0,1])
pop = [Scored(smiles=s, score=sc) for s, sc in [
    ("O=C(Nc1ccccc1)c1ccc(Cl)cc1", 0.81), ("c1ccc2[nH]ccc2c1", 0.74),
    ("CC(=O)Nc1ccc(O)cc1", 0.69), ("c1ccccc1", 0.12), ("CCO", 0.05),
]]
summary = build_analyzer_summary(pop, [0.40, 0.55, 0.69], None)
prompt = build_analyzer_prompt(summary)
res = asyncio.run(analyze_async(prompt, seed=42))
print("max_tokens cap:", _ANALYZER_MAX_OUTPUT_TOKENS)
print("tokens_out:", res.tokens_out)
print("structured:", res.structured)
print("parsed-again:", parse_hypothesis(res.text))
print("TAIL:", repr(res.text[-300:]))
PY
```

Healthy: `structured` is a `{focus, avoid}` dict AND `tokens_out` is comfortably below the cap (JSON not truncated). If `structured is None` or `tokens_out` is at/near the cap with the JSON cut off → go to Step 3; otherwise skip to Step 4.

- [ ] **Step 3 (conditional): Bump `_ANALYZER_MAX_OUTPUT_TOKENS` and re-smoke**

Only if Step 2 showed truncation. In `packages/core/capychem/analyzer.py` raise the cap (e.g. `2048 → 4096`):

```python
# Reasoning ON needs room for the chain-of-thought tail PLUS the JSON hypothesis.
_ANALYZER_MAX_OUTPUT_TOKENS = 4096
```

Re-run Step 2. Confirm `structured` now parses with headroom. Then:

```bash
uv run pytest packages/core/tests/test_analyzer.py -q && uv run mypy -p capychem -p capychem.api && uv run ruff check .
git add packages/core/capychem/analyzer.py
git commit -m "fix(analyzer): raise reasoning-mode max_tokens so CoT cannot truncate the {focus,avoid} JSON

The first real direct-backend smoke showed the chain-of-thought tail crowding out
the hypothesis JSON at 2048; raising the cap restores parse success (slice-02 guard).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Run the single-seed jnk3 verdict (~$1.2–2.0)**

```bash
CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct DEEPSEEK_API_KEY=<key> \
  uv run capychem-eval --task=jnk3 --budget=10000 --seed=42 --analyzer-verdict | tee /tmp/jnk3-analyzer-verdict-seed42.json
```

Capture the JSON. The `verdict` string + `parse_rate_healthy` give the read directly. Sanity-check `with_valid_rate`/`without_valid_rate` are ≥~0.8 (a low rate means the LLM arm degraded — likely a balance/transient issue, not a real signal).

- [ ] **Step 5: Interpret + record the kill-switch decision**

Decision rule (from the design):
- `parse_rate_healthy == false` → verdict INVALID → return to Step 3 (raise max_tokens), rerun Step 4. Never record a null under truncation.
- healthy & `helps == true` (`diff > 0`) → **analyzer ADDS value** → differentiator confirmed.
- healthy & `helps == false` (`diff <= 0`) → **clean null** → pivot to analyzer-only narrative (document it); do NOT abandon. Slice still ships.

Write `docs/03-analyzer-and-scale/02-analyzer-value-verdict.md` (mirror `docs/02-end-to-end-loop/06-beat-graph-ga-on-jnk3.md`): Goal, Plan, Tasks (checked), a **Verdict** section with the table below, Notes/decisions (parse-rate health, one-seed honesty, provider sampling), Out-of-scope. Verdict table:

| seed | with-analyzer AUC | without-analyzer AUC | diff | helps | parse-rate | with/without valid-rate | with/without unique calls | wall | cost |
|---|---|---|---|---|---|---|---|---|---|

- [ ] **Step 6: Ship-the-slice doc updates (one commit, on the slice branch)**

Per `~/.claude/CLAUDE.md` slice-completion ritual:
- `docs/03-analyzer-and-scale/milestone.md` Slices list: flip `02 analyzer-value-verdict … planned → shipped (2026-06-28)` with the verdict one-liner.
- `docs/03-analyzer-and-scale/handoff.md`: "Slice status across milestone" flip; "Completed this session" with commit refs; "Next session start here" → slice 03 or 04; append a dated "Slice 02 shipped" log line; update Active concerns (parse-rate result; max_tokens final value).
- Freeze `docs/03-analyzer-and-scale/02-analyzer-value-verdict.md`.

```bash
git add docs/03-analyzer-and-scale/
git commit -m "docs(slice-03-02): ship analyzer-value-verdict — <ADDS value|null pivot>; status flips + slice freeze

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: Final gate + integrate**

Run the full suite + gates one more time:

Run: `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

ff-merge the slice branch to `main` locally; **ASK before pushing** (origin is unpushed by choice).

```bash
git checkout main && git merge --ff-only slice/03-02-analyzer-value-verdict && git branch -d slice/03-02-analyzer-value-verdict
```

---

## Self-Review

**Spec coverage:**
- Parse-rate instrumentation (design Component a; load-bearing risk) → Task 1. ✓
- Verdict module mirroring `beat.py` (Component b, Decision 2) → Task 2. ✓
- `--analyzer-verdict` CLI + three-way verdict string (Component c) → Task 3. ✓
- Raw-`structured` counting, not effective hypothesis (Decision 4) → Task 1 Step 4 + `test_analyzer_parse_rate_counts_failures`. ✓
- 0.8 parse-rate floor (Decision 3) → Task 2 `_PARSE_RATE_FLOOR` + `test_parse_rate_healthy_boundary`. ✓
- Parse smoke + conditional max_tokens bump (Decision 5, Step A) → Task 4 Steps 2–3. ✓
- Real single-seed jnk3 verdict + three-way interpretation (Steps B/C, Decision 1) → Task 4 Steps 4–5. ✓
- One-seed honesty / provider sampling (Decision 6) → Task 4 Step 5 Notes. ✓
- `beat.py`/`proposer.py` untouched; `ReproResult` new fields default to off-values (regression) → Task 1 defaults + `test_analyzer_off_has_none_parse_rate`. ✓
- Slice-completion ritual (milestone/handoff flips, freeze, ff-merge, ask-before-push) → Task 4 Steps 6–7. ✓

**Placeholder scan:** No TBD/TODO. `<key>` / `<ADDS value|null pivot>` are operator-supplied at run time (a secret and a result), not plan gaps. The illustrative `_stub` helper in Task 2 Step 1 is explicitly flagged for deletion with the reason it's shown.

**Type consistency:** `ReproResult.analyzer_{calls,parsed,parse_rate}` (Task 1) match the reads in `run_analyzer_verdict` (Task 2) and the report keys (Task 3). `AnalyzerVerdict` field names match across the dataclass (Task 2), the CLI report (Task 3), and both CLI tests. `run_analyzer_verdict` signature `(task, budget, seed, *, pop_size, offspring, mutation_rate)` is identical in module, CLI call, and test fakes.
