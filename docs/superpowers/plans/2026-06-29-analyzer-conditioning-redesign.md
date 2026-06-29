# Analyzer Conditioning Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip the analyzer from value-negative to value-neutral-or-positive on jnk3 by redesigning how its hypothesis conditions the proposer — evidence-first: capture real hypotheses, diagnose, apply the matched fix, re-verify.

**Architecture:** Two always-run code tasks add a trace-capture seam to the headless eval runner (`eval/runner.py`) + a `--capture-analyzer-traces` CLI mode, so we can read the actual `{focus,avoid}` hypotheses and conditioned prompts from a cheap jnk3 `direct` run. A manual decision gate classifies the failure, then ONE of three conditioning fixes (all editing the shared `loop/strategy.py`, so both the eval path and the product loop inherit the change for free) is implemented and re-verified with the existing `--analyzer-verdict` harness.

**Tech Stack:** Python 3.12, uv, pytest, mypy strict, ruff. DeepSeek-v4-pro via the `direct` backend (reasoning OFF). No Modal, no Postgres, no web changes.

## Global Constraints

- Every reported score is an in-silico oracle score — say so in any new docstring/copy (PRD N6). No real-world efficacy claims.
- mypy strict must stay green: `uv run mypy -p capychem -p capychem.api` (both `-p`). ruff clean: `uv run ruff check .`. Full suite green: `uv run pytest`.
- G6 reproducibility: with `trace_sink=None` (the default) and with the conditioning fix inactive, `run_reproduction` and `build_prompt` output must be byte-identical to today. The gen-1 / graph_ga / no-hypothesis prompt paths must not change.
- TDD on the `stub` / monkeypatched backends only (free, deterministic, harness-free). The real `direct` calls happen ONLY in the two manual runs (Phase-1 capture, Phase-4 verdict).
- Verdict harness is canonical: measure AUC only via `eval/metric.top_auc` / `eval/verdict.run_analyzer_verdict`. Never compute AUC ad hoc.
- Scope is single-task (jnk3), single-seed (42). Phase-1 capture budget ≈ 300; Phase-4 verdict budget = 10000.
- DeepSeek prepaid balance ≈ $1 at start — **top up before Phase 4**; confirm balance covers the run (a $0 balance mid-run silently degrades the LLM arm to Graph-GA, which `parse_rate_healthy` does NOT catch — cross-check both `*_valid_rate` ≥ ~0.8).

---

## File Structure

- **Create** `packages/core/capychem/eval/trace.py` — `GenerationTrace` frozen dataclass (one analyzer+propose snapshot per generation) + `trace_to_dict` JSON helper. One responsibility: the trace record shape.
- **Modify** `packages/core/capychem/eval/runner.py` — add an optional `trace_sink` param to `run_reproduction`, populated at the analyzer seam. (Phase-3 Approach B also edits the conditioning decision here.)
- **Modify** `packages/core/capychem/eval/cli.py` — add the `--capture-analyzer-traces` mode.
- **Modify** `packages/core/capychem/loop/strategy.py` — Phase-3 Approach A (soften `build_prompt` + fractional split in `propose_llm_async`) and/or Approach C (descriptive analyzer output).
- **Modify** `packages/core/capychem/analyzer.py` — Phase-3 Approach C only (output schema).
- **Tests**: `packages/core/tests/test_eval_trace.py` (new), `test_eval_runner.py`, `test_eval_cli.py`, `test_strategy.py` (extend).

---

## Task 1: Trace-capture seam in the headless runner

**Files:**
- Create: `packages/core/capychem/eval/trace.py`
- Create: `packages/core/tests/test_eval_trace.py`
- Modify: `packages/core/capychem/eval/runner.py` (add `trace_sink` param + the append at the analyzer seam, ~lines 54–146)

**Interfaces:**
- Consumes: existing `run_reproduction(...)`, `build_prompt`, `build_analyzer_summary`, `AnalyzerSummary`, `Hypothesis`.
- Produces:
  - `GenerationTrace` (frozen dataclass) with fields: `generation: int`, `summary_top: list[tuple[str, float]]`, `summary_bottom: list[tuple[str, float]]`, `recent_top10_means: list[float]`, `prior_structured: dict[str, Any] | None`, `analyzer_raw: str`, `analyzer_structured: dict[str, Any] | None`, `prompt_used: str`, `prompt_unconditioned: str`.
  - `trace_to_dict(t: GenerationTrace) -> dict[str, Any]`.
  - `run_reproduction(..., trace_sink: list[GenerationTrace] | None = None)` — when not None, one `GenerationTrace` is appended per analyzer-bearing generation. `None` (default) ⇒ behavior byte-identical to today.

- [ ] **Step 1: Write the failing test for the dataclass + serializer**

In `packages/core/tests/test_eval_trace.py`:

```python
from capychem.eval.trace import GenerationTrace, trace_to_dict


def test_generation_trace_serializes_to_json_safe_dict() -> None:
    t = GenerationTrace(
        generation=3,
        summary_top=[("c1ccccc1", 0.9)],
        summary_bottom=[("CCC", 0.1)],
        recent_top10_means=[0.5, 0.7, 0.8],
        prior_structured={"focus": "logP", "avoid": ["amide"]},
        analyzer_raw="Focus on logP. {\"focus\": \"logP\", \"avoid\": [\"amide\"]}",
        analyzer_structured={"focus": "logP", "avoid": ["amide"]},
        prompt_used="...conditioned...",
        prompt_unconditioned="...plain...",
    )
    d = trace_to_dict(t)
    import json
    json.dumps(d)  # must not raise
    assert d["generation"] == 3
    assert d["analyzer_structured"] == {"focus": "logP", "avoid": ["amide"]}
    assert d["summary_top"] == [["c1ccccc1", 0.9]]  # tuples -> lists through JSON-safe dict
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.eval.trace'`.

- [ ] **Step 3: Create `eval/trace.py`**

```python
"""One analyzer+propose snapshot per generation, for offline diagnosis of why the
analyzer hypothesis helps or hurts. Capture-only: never read by the loop itself
(trace_sink=None keeps the run byte-identical). Every score here is an in-silico
oracle score (PRD N6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationTrace:
    generation: int
    summary_top: list[tuple[str, float]]
    summary_bottom: list[tuple[str, float]]
    recent_top10_means: list[float]
    prior_structured: dict[str, Any] | None
    analyzer_raw: str
    analyzer_structured: dict[str, Any] | None
    prompt_used: str
    prompt_unconditioned: str


def trace_to_dict(t: GenerationTrace) -> dict[str, Any]:
    """JSON-safe dict (tuples -> lists) for the --capture-analyzer-traces dump."""
    return {
        "generation": t.generation,
        "summary_top": [[s, sc] for s, sc in t.summary_top],
        "summary_bottom": [[s, sc] for s, sc in t.summary_bottom],
        "recent_top10_means": list(t.recent_top10_means),
        "prior_structured": t.prior_structured,
        "analyzer_raw": t.analyzer_raw,
        "analyzer_structured": t.analyzer_structured,
        "prompt_used": t.prompt_used,
        "prompt_unconditioned": t.prompt_unconditioned,
    }
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_trace.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for the runner seam**

In `packages/core/tests/test_eval_runner.py` (append; mirror `test_analyzer_threads_hypothesis_in_headless_llm`):

```python
def test_trace_sink_captures_per_generation_when_analyzer_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.eval import runner as runner_mod
    from capychem.eval.trace import GenerationTrace
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        return [ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                tokens_in=0, tokens_out=0) for i in range(n)]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    sink: list[GenerationTrace] = []
    res = run_reproduction("qed", budget=40, seed=42, pop_size=3, offspring=4,
                           patience=9, mutation_strategy="llm", analyzer=True, trace_sink=sink)
    assert res.analyzer_calls == len(sink)  # one trace per analyzer call
    assert sink, "expected at least one captured generation"
    first = sink[0]
    assert first.analyzer_structured is not None  # stub always parses
    assert "Guidance" in first.prompt_used  # conditioned prompt reconstructed
    assert "Guidance" not in first.prompt_unconditioned  # plain prompt reconstructed


def test_trace_sink_none_is_default_and_no_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    pool = ["CCO", "c1ccccc1", "CCN", "CCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
        return [ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                tokens_in=0, tokens_out=0) for i in range(n)]

    def fake_score(smiles, task, **kw):  # type: ignore[no-untyped-def]
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    # default trace_sink=None: runs identically, returns a ReproResult, no error
    res = run_reproduction("qed", budget=40, seed=42, pop_size=3, offspring=4,
                           patience=9, mutation_strategy="llm", analyzer=True)
    assert res.analyzer_calls > 0
```

- [ ] **Step 6: Run to verify the new tests fail**

Run: `uv run pytest packages/core/tests/test_eval_runner.py::test_trace_sink_captures_per_generation_when_analyzer_on -v`
Expected: FAIL — `TypeError: run_reproduction() got an unexpected keyword argument 'trace_sink'`.

- [ ] **Step 7: Add the `trace_sink` param + the append in `runner.py`**

Add the import near the top of `runner.py`:

```python
from capychem.eval.trace import GenerationTrace
from capychem.loop.strategy import build_prompt  # add to the existing strategy import line
```

Add the param to the `run_reproduction` signature (after `analyzer: bool = False`):

```python
    analyzer: bool = False,
    trace_sink: list[GenerationTrace] | None = None,
```

Inside the `if analyzer and mutation_strategy == "llm":` block, capture BEFORE `hypothesis` is reassigned (i.e. before `hypothesis = resolve_effective_hypothesis(...)`). The prompt that conditioned THIS generation's propose used the pre-merge `pop_pairs` and the incoming `hypothesis`, both still in scope:

```python
        if analyzer and mutation_strategy == "llm":
            summary = build_analyzer_summary(population, score_history, hypothesis)
            result = run_analyzer_sync(summary, seed=seed + generations - 1)
            analyzer_calls += 1
            if result.structured is not None:
                analyzer_parsed += 1
            if trace_sink is not None:
                trace_sink.append(GenerationTrace(
                    generation=generations,
                    summary_top=summary.top,
                    summary_bottom=summary.bottom,
                    recent_top10_means=summary.recent_top10_means,
                    prior_structured=hypothesis.structured if hypothesis else None,
                    analyzer_raw=result.text,
                    analyzer_structured=result.structured,
                    prompt_used=build_prompt(task, pop_pairs, offspring, hypothesis),
                    prompt_unconditioned=build_prompt(task, pop_pairs, offspring, None),
                ))
            hypothesis = resolve_effective_hypothesis(result, hypothesis)
```

Note: `pop_pairs` here is the pre-merge population used by this generation's propose, so `prompt_used` reconstructs exactly what was sent. `build_prompt` is seed-independent, so reconstruction is exact.

- [ ] **Step 8: Run to verify all runner tests pass**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -v`
Expected: PASS (the two new tests + all existing, including `test_trace_sink_none_is_default_and_no_capture`).

- [ ] **Step 9: Gate + commit**

Run: `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

```bash
git add packages/core/capychem/eval/trace.py packages/core/tests/test_eval_trace.py \
        packages/core/capychem/eval/runner.py packages/core/tests/test_eval_runner.py
git commit -m "feat(eval): trace-capture seam for analyzer diagnosis (trace_sink)"
```

---

## Task 2: `--capture-analyzer-traces` CLI mode

**Files:**
- Modify: `packages/core/capychem/eval/cli.py` (add the flag + mode branch)
- Modify: `packages/core/tests/test_eval_cli.py` (add a mode test; monkeypatch `run_reproduction`)

**Interfaces:**
- Consumes: `run_reproduction(..., trace_sink=...)`, `trace_to_dict` (Task 1).
- Produces: CLI mode `--capture-analyzer-traces` that runs the LLM-with-analyzer arm once and dumps `{"task","seed","budget","analyzer_calls","traces":[...]}` JSON to stdout.

- [ ] **Step 1: Write the failing CLI test** (monkeypatch the runner so it's harness-free)

In `packages/core/tests/test_eval_cli.py` (mirror the existing mode tests):

```python
def test_capture_analyzer_traces_mode_emits_traces(monkeypatch, capsys) -> None:
    import json
    from capychem.eval import cli as cli_mod
    from capychem.eval.runner import ReproResult
    from capychem.eval.trace import GenerationTrace

    def fake_run(task, budget, seed, *, trace_sink=None, **kw):
        assert trace_sink is not None  # capture mode must pass a sink
        trace_sink.append(GenerationTrace(
            generation=2, summary_top=[("CCO", 0.5)], summary_bottom=[], recent_top10_means=[0.5],
            prior_structured=None, analyzer_raw="raw", analyzer_structured={"focus": "f", "avoid": []},
            prompt_used="cond", prompt_unconditioned="plain",
        ))
        return ReproResult(mol_buffer={"CCO": (0.5, 1)}, generations=2, unique_calls=1,
                           analyzer_calls=1, analyzer_parsed=1, analyzer_parse_rate=1.0)

    monkeypatch.setattr(cli_mod, "run_reproduction", fake_run)
    rc = cli_mod.main(["--task=jnk3", "--budget=300", "--seed=42",
                       "--mutation-strategy=llm", "--capture-analyzer-traces"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["task"] == "jnk3"
    assert out["analyzer_calls"] == 1
    assert out["traces"][0]["analyzer_structured"] == {"focus": "f", "avoid": []}
    assert out["traces"][0]["prompt_used"] == "cond"
```

(If `test_eval_cli.py` imports `run_reproduction` directly into `cli`, monkeypatch `cli_mod.run_reproduction`; it is already imported there.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_cli.py::test_capture_analyzer_traces_mode_emits_traces -v`
Expected: FAIL — unrecognized argument `--capture-analyzer-traces`.

- [ ] **Step 3: Add the flag + mode branch in `cli.py`**

Add the argument next to `--analyzer-verdict`:

```python
    p.add_argument(
        "--capture-analyzer-traces",
        action="store_true",
        help="Run the LLM-with-analyzer arm once and dump per-generation hypotheses + prompts (diagnosis).",  # noqa: E501
    )
```

Add the import at the top: `from capychem.eval.trace import trace_to_dict`.

Add the branch BEFORE the `--analyzer-verdict` branch (so it short-circuits):

```python
    if args.capture_analyzer_traces:
        from capychem.eval.trace import GenerationTrace

        sink: list[GenerationTrace] = []
        res = run_reproduction(
            args.task, args.budget, args.seed,
            pop_size=args.pop_size, offspring=args.offspring, mutation_rate=args.mutation_rate,
            mutation_strategy="llm", analyzer=True, trace_sink=sink,
        )
        wall = time.monotonic() - t0
        cap_report: dict[str, object] = {
            "task": args.task,
            "seed": args.seed,
            "budget": args.budget,
            "capture_analyzer_traces": True,
            "analyzer_calls": res.analyzer_calls,
            "analyzer_parsed": res.analyzer_parsed,
            "analyzer_parse_rate": res.analyzer_parse_rate,
            "traces": [trace_to_dict(t) for t in sink],
            "wall_seconds": round(wall, 1),
        }
        json.dump(cap_report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_eval_cli.py::test_capture_analyzer_traces_mode_emits_traces -v`
Expected: PASS.

- [ ] **Step 5: Gate + commit**

Run: `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

```bash
git add packages/core/capychem/eval/cli.py packages/core/tests/test_eval_cli.py
git commit -m "feat(eval): --capture-analyzer-traces CLI mode for analyzer diagnosis"
```

---

## DECISION GATE (Phase 2) — manual, no code

Top up the DeepSeek balance if needed (this is cheap — budget 300). Run the capture:

```bash
CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct \
  uv run capychem-eval --task=jnk3 --budget=300 --seed=42 \
  --mutation-strategy=llm --capture-analyzer-traces > /tmp/jnk3-traces.json
```

Read `/tmp/jnk3-traces.json` and classify the **dominant** failure (record the read + decision in the slice doc `docs/03-analyzer-and-scale/06-analyzer-conditioning.md`):

| What the traces show | Mechanism | → Approach |
|---|---|---|
| `analyzer_structured.focus/avoid` are *chemically reasonable* given `summary_top`, but `prompt_used` forces every offspring one way | Application | **3A** |
| `recent_top10_means` was *climbing* across generations where conditioning was active (analyzer interrupted a working trajectory) | Timing | **3B** |
| `focus`/`avoid` are *generic / contradict the top scorers / repeat every gen* regardless of `summary_top` | Content | **3C** |

Implement exactly ONE of 3A / 3B / 3C. (3A's softening may additionally layer onto 3B/3C if the traces show two effects, but pick the primary lever first — re-verify before stacking.)

---

## Task 3A: Soften & diversify the application *(default / Application finding)*

**Files:**
- Modify: `packages/core/capychem/loop/strategy.py` — `build_prompt` (wording + `avoid` demotion) and `propose_llm_async` (fractional split).
- Modify: `packages/core/tests/test_strategy.py` — update `test_build_prompt_appends_guidance_when_hypothesis_present` to the new wording; add a fractional-split test.

**Interfaces:**
- `build_prompt(task, population, n, hypothesis=None)` — unchanged signature; new guidance text frames the hypothesis as optional inspiration and demotes `avoid` to a soft "tended to score lower" note (or drops it — decide from traces).
- `propose_llm_async(task, population, *, n, seed, hypothesis=None, conditioned_fraction: float = strategy.CONDITIONED_FRACTION)` — when a structured hypothesis is present and the fraction < 1.0, only `round(n*fraction)` proposals are conditioned; the rest use the plain prompt. `conditioned_fraction = 1.0` (or no structured hypothesis) reproduces today's behavior exactly. Add `CONDITIONED_FRACTION` module constant (start 0.5).

- [ ] **Step 1: Update the guidance-wording test (RED)**

Replace the body of `test_build_prompt_appends_guidance_when_hypothesis_present` in `test_strategy.py` to assert the softened framing and that the hard "avoid …" directive is gone:

```python
def test_build_prompt_softens_guidance_to_optional_inspiration() -> None:
    from capychem.loop.state import Hypothesis

    pop = [("CCO", 0.9)]
    h = Hypothesis(structured={"focus": "increase logP", "avoid": ["phenol"]}, text="Push logP.")
    p = strategy.build_prompt("jnk3", pop, 5, hypothesis=h)
    assert "increase logP" in p
    assert "Push logP." in p
    # framed as optional, not a command:
    assert "may help" in p or "optional" in p
    assert "your own" in p.lower()  # "prioritize your own judgment"
    # the hard negative directive is demoted/removed:
    assert "avoid phenol" not in p.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_strategy.py::test_build_prompt_softens_guidance_to_optional_inspiration -v`
Expected: FAIL on the new assertions.

- [ ] **Step 3: Soften `build_prompt`'s guidance block**

Replace the `guidance` construction in `build_prompt`:

```python
    guidance = ""
    if hypothesis is not None and hypothesis.structured is not None:
        s = hypothesis.structured
        guidance = (
            "\nAn analysis of the previous generation suggests this MAY help — treat it as "
            "optional inspiration, not a constraint, and prioritize your own chemical judgment: "
            f"consider {s['focus']}. {hypothesis.text}\n"
        )
```

(Decide from the traces whether to drop `avoid` entirely — as above — or demote it to a soft note like `f" Features such as {', '.join(s['avoid'])} tended to score lower."`. The test as written assumes the drop; if demoting, adjust the test to assert the soft phrasing instead of `"avoid phenol" not in`.)

- [ ] **Step 4: Run to verify it passes** + confirm the no-hypothesis regression still holds

Run: `uv run pytest packages/core/tests/test_strategy.py -k build_prompt -v`
Expected: PASS, including `test_build_prompt_unchanged_without_hypothesis` (the gen-1 / neutral path is untouched).

- [ ] **Step 5: Write the failing fractional-split test**

```python
async def test_propose_llm_async_conditions_only_a_fraction(monkeypatch) -> None:
    from capychem.loop.state import Hypothesis

    prompts: list[str] = []

    async def fake_batch(prompt, n, *, temperature=0.7, seed=0):
        prompts.append(prompt)
        return [proposer_mod.ProposalResult(raw="CCO", smiles="CCO", tokens_in=0, tokens_out=0)
                for _ in range(n)]

    monkeypatch.setattr(strategy, "propose_batch_async", fake_batch)
    h = Hypothesis(structured={"focus": "logP", "avoid": []}, text="t")
    out = await strategy.propose_llm_async("qed", [("CCO", 0.5)], n=4, seed=1,
                                           hypothesis=h, conditioned_fraction=0.5)
    assert len(out) == 4
    # two sub-batches: one conditioned (mentions the focus), one plain (no guidance)
    assert len(prompts) == 2
    assert any("logP" in pr for pr in prompts)
    assert any("logP" not in pr for pr in prompts)
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_strategy.py::test_propose_llm_async_conditions_only_a_fraction -v`
Expected: FAIL — `propose_llm_async() got an unexpected keyword argument 'conditioned_fraction'`.

- [ ] **Step 7: Implement the fractional split**

Add the constant near `LLM_TEMPERATURE`:

```python
# Fraction of each generation's offspring conditioned on the analyzer hypothesis;
# the remainder use the plain prompt to preserve batch diversity (milestone 03 redesign).
CONDITIONED_FRACTION = 0.5
```

Rewrite `propose_llm_async`:

```python
async def propose_llm_async(
    task: str,
    population: list[tuple[str, float]],
    *,
    n: int,
    seed: int,
    hypothesis: Hypothesis | None = None,
    conditioned_fraction: float = CONDITIONED_FRACTION,
) -> list[ProposalResult]:
    """Propose ``n`` LLM candidates (pinned temperature + per-gen seed, G6). When a
    structured hypothesis is present and ``conditioned_fraction`` < 1.0, only that
    fraction of the batch is conditioned; the rest use the plain prompt to preserve
    diversity. No structured hypothesis (or fraction >= 1.0) -> single plain batch,
    byte-identical to milestone 02."""
    if hypothesis is None or hypothesis.structured is None or conditioned_fraction >= 1.0:
        return await propose_batch_async(
            build_prompt(task, population, n, hypothesis), n,
            temperature=LLM_TEMPERATURE, seed=seed,
        )
    n_cond = round(n * conditioned_fraction)
    n_plain = n - n_cond
    out: list[ProposalResult] = []
    if n_cond:
        out += await propose_batch_async(
            build_prompt(task, population, n_cond, hypothesis), n_cond,
            temperature=LLM_TEMPERATURE, seed=seed,
        )
    if n_plain:
        out += await propose_batch_async(
            build_prompt(task, population, n_plain, None), n_plain,
            temperature=LLM_TEMPERATURE, seed=seed + n_cond,
        )
    return out
```

`propose_llm_sync` needs the matching kwarg — update its signature + the forwarded call:

```python
def propose_llm_sync(
    task, population, *, n, seed, hypothesis=None,
    conditioned_fraction: float = CONDITIONED_FRACTION,
) -> list[ProposalResult]:
    return asyncio.run(propose_llm_async(
        task, population, n=n, seed=seed, hypothesis=hypothesis,
        conditioned_fraction=conditioned_fraction,
    ))
```

(The runner calls `propose_llm_sync(...)` without the kwarg, so it picks up the `CONDITIONED_FRACTION` default automatically — no runner change needed. Confirm `test_llm_strategy_runs_to_budget_on_stub` and the analyzer threading tests still pass, since their `fake_llm_sync` ignores the new kwarg.)

- [ ] **Step 8: Run to verify it passes + full strategy suite**

Run: `uv run pytest packages/core/tests/test_strategy.py packages/core/tests/test_eval_runner.py -v`
Expected: PASS.

- [ ] **Step 9: Gate + commit**

Run: `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .`
Expected: all green.

```bash
git add packages/core/capychem/loop/strategy.py packages/core/tests/test_strategy.py
git commit -m "feat(strategy): soften analyzer guidance + fractional-batch conditioning"
```

---

## Task 3B: Gate the analyzer to plateaus *(Timing finding)*

**Files:**
- Modify: `packages/core/capychem/eval/runner.py` — add a plateau gate on the conditioning decision, **reusing the existing `logic.is_plateau`** (do NOT add a new helper — `is_plateau(top10_history, plateau_window) -> bool` already exists in `loop/logic.py:43` and uses `PLATEAU_MIN_IMPROVEMENT` as ε; the runner's `score_history` IS the top-10-mean history it expects).
- Modify: `packages/core/tests/test_eval_runner.py` — add the gated-conditioning test.

**Interface:**
- Reuse `is_plateau(score_history, plateau_window)`. Add a `_GATE_PLATEAU_WINDOW = 3` module constant in `runner.py` (the window over which a flat top-10 mean opens the gate). No new logic-layer function.
- In `run_reproduction`, the propose call passes `hypothesis` only when `is_plateau` is True, else `None`. The analyzer still runs every generation (parse-rate + future live surface unaffected); only the *application* is gated.

- [ ] **Step 1: Failing runner test** — conditioning applied only once the top-10 mean flattens. Extend the `test_analyzer_threads_hypothesis_in_headless_llm` pattern with a `fake_score` that makes the survivor top-10 mean climb for the first few generations then go flat; collect `hypothesis` per `propose` call in a `seen` list and assert it is `None` during the climb and not-None only after a full flat `_GATE_PLATEAU_WINDOW`. (Reuse the existing `fake_llm_sync`/`fake_score` scaffold from that test; the only change is a climbing-then-flat score function.)

- [ ] **Step 2: Run to verify fail.** `uv run pytest packages/core/tests/test_eval_runner.py -k gate -v` → FAIL (hypothesis applied every gen, not gated).

- [ ] **Step 3: Gate the application in `runner.py`.** Add `is_plateau` to the existing `from capychem.loop.logic import build_analyzer_summary, merge_and_truncate` line, add the constant near the top of the module:

```python
# Apply analyzer conditioning only once the survivor top-10 mean has been flat for
# this many generations — let the strong unconditioned proposer run until it stalls
# (milestone-03 redesign; reuses logic.is_plateau / PLATEAU_MIN_IMPROVEMENT as ε).
_GATE_PLATEAU_WINDOW = 3
```

In the `if mutation_strategy == "llm":` branch, gate the hypothesis passed to propose (`score_history` at this point excludes the current generation, which is correct — we gate on what was known before proposing):

```python
        if mutation_strategy == "llm":
            apply_hyp = hypothesis if is_plateau(score_history, _GATE_PLATEAU_WINDOW) else None
            results = propose_llm_sync(
                task, pop_pairs, n=offspring, seed=seed + generations, hypothesis=apply_hyp
            )
```

(`hypothesis` is still updated by the analyzer block each generation, so once the plateau hits, the latest hypothesis is the one applied.)

- [ ] **Step 4: Run to verify pass + full suite.** `uv run pytest packages/core/tests/test_eval_runner.py -v` → PASS (the existing analyzer-threading tests use `patience=9` and flat 0.5 scores, so they plateau quickly and still see a non-None hypothesis — confirm they pass; adjust their assertions only if the gate legitimately delays the first conditioned gen).

- [ ] **Step 5: Gate + commit.** `uv run pytest && uv run mypy -p capychem -p capychem.api && uv run ruff check .` → green. `git commit -m "feat(eval): gate analyzer conditioning to plateaus (reuse logic.is_plateau)"`

> **Parity note:** the product loop (`loop/graph.py`) must gain the same gate before the live surface (slice 03) ships, for criterion-1 both-paths parity. The Phase-4 verdict only needs the headless path, so graph.py parity is a follow-up, not a blocker here. Record the deferral in the slice doc.

---

## Task 3C: Descriptive (not prescriptive) analyzer output *(Content finding)*

**Files:**
- Modify: `packages/core/capychem/loop/strategy.py` — `build_analyzer_prompt` (ask for an observation) + `build_prompt` (inject the observation as context).
- Modify: `packages/core/capychem/analyzer.py` — `parse_hypothesis` accepts the new schema.
- Modify: `packages/core/capychem/loop/state.py` — `Hypothesis.structured` shape note.
- Modify: tests across `test_strategy.py`, `test_analyzer.py`.

**Interface change:** the analyzer emits `{"observation": "<what the top scorers structurally share>"}` instead of `{"focus","avoid"}`; `parse_hypothesis` returns `{"observation": str}`; `build_prompt` injects it as *"Observed in the last generation's best molecules: <observation>. Use this as context."*

- [ ] **Step 1: Failing test** — `parse_hypothesis` extracts `observation`:

```python
def test_parse_hypothesis_extracts_observation() -> None:
    from capychem.analyzer import parse_hypothesis
    out = parse_hypothesis('Top scorers share an aromatic core.\n{"observation": "aromatic core with basic N"}')
    assert out == {"observation": "aromatic core with basic N"}
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement.** Update `parse_hypothesis` to accept `{"observation": str}` (keep returning None on missing/wrong-typed). Update `build_analyzer_prompt`'s closing instruction to request the observation JSON. Update `build_prompt`'s guidance block to inject the observation as soft context.

> **Scope flag:** 3C ripples through every test that asserts the `{focus,avoid}` schema (`test_strategy.py`, `test_analyzer.py`, `test_eval_runner.py` stub-analyzer fakes, the `_STUB_HYPOTHESES`). If the gate selects 3C, **spend ~10 minutes refining this task into full bite-sized steps** (one per touched test) before executing — it is the heavy branch and reintroduces the parse-rate risk, so keep the slice-02 `parse_rate_healthy` guard front-and-centre in Phase 4. The representative code above defines the shape; the detailed micro-plan is finalized post-gate because the exact test edits depend on the chosen schema.

- [ ] **Steps 4–9:** RED→GREEN per touched test; gate (`pytest && mypy && ruff`); commit `feat(strategy): descriptive analyzer observations (not prescriptive directives)`.

---

## VERIFY (Phase 4) — manual, no code

Top up the DeepSeek balance and confirm it covers a full run (≈ $1). Re-run the canonical verdict:

```bash
CAPYCHEM_PROPOSER_BACKEND=direct CAPYCHEM_ANALYZER_BACKEND=direct \
  uv run capychem-eval --task=jnk3 --budget=10000 --seed=42 --analyzer-verdict
```

Acceptance (record in the slice doc):
- **Primary:** `diff` (= `with_auc − without_auc`) ≥ 0 — i.e. the redesign flipped the slice-02 −0.066. A positive diff is the stretch.
- **Trust guards (BOTH required, per slice-02):** `parse_rate_healthy` is true (≥ 0.8) AND both `with_valid_rate` / `without_valid_rate` ≥ ~0.8 (no silent Graph-GA degradation from a depleted balance).
- If it still nulls *with* healthy guards, that is a clean trace-backed result: record it and re-open the strategic fork (the no-headroom reading strengthens the analyzer-only-narrative pivot — but only for jnk3; the 23-task sweep, slice 05, remains the authoritative bar).

---

## Self-Review (filled at plan-write time)

- **Spec coverage:** Phase 1 (capture) → Tasks 1–2. Phase 2 (diagnose) → Decision Gate. Phase 3 (matched fix A/B/C) → Tasks 3A/3B/3C. Phase 4 (re-verify) → Verify section. Spec §5 file-touch map matches the File Structure above. ✓
- **Placeholder scan:** Tasks 1, 2, 3A carry complete code. 3B is concrete (helper + gate code shown). 3C is intentionally a shape-defining task with an explicit "refine post-gate" note — flagged, not a silent gap (it is the unlikely branch and depends on the chosen schema). ✓
- **Type consistency:** `GenerationTrace`/`trace_to_dict` (Task 1) used identically in Task 2; `run_reproduction(..., trace_sink=...)` signature consistent across Tasks 1–2; `propose_llm_async/sync(..., conditioned_fraction=...)` + `CONDITIONED_FRACTION` consistent within 3A; 3B reuses the existing `logic.is_plateau(top10_history, plateau_window)` (no new helper, no duplicate). ✓
- **Reuse check:** 3B reuses `logic.is_plateau` rather than adding `is_plateaued` (verified it exists at `loop/logic.py:43`). 3A's fractional split is added to the existing `propose_llm_async`, not a parallel function. ✓
