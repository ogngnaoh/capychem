# Analyzer Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the analyzer agent (milestone-03 slice 01) — after every generation ≥1 of an LLM run, form a `{focus, avoid}` hypothesis from that generation's results and condition the next proposal on it, in both the product loop and the headless eval path.

**Architecture:** A new `analyze` LangGraph node runs after `persist` (no-op for gen 0 / graph_ga), calling a new `analyzer.py` adapter (DeepSeek, reasoning ON) through a shared `loop/strategy.py` seam so the product loop and headless `eval/runner.py` produce byte-identical hypotheses (G6). The hypothesis is persisted (`AnalyzerHypothesis`, linked from `Generation`) and threaded into the next `propose` via an extended `build_prompt`. Malformed/empty output falls back to last-good/neutral so the loop never stalls.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, LangGraph, RDKit, pytest (async), mypy strict, ruff. DeepSeek-v4-pro via the existing `proposer.py` transport (reused, not modified).

## Global Constraints

- Validate every SMILES via RDKit before persistence (the `validate` node already owns this; the analyzer never produces molecules).
- Wrap every LangGraph node in a Langfuse span — no silent loop steps (`trace.span`, no-op when Langfuse keys absent).
- Never import from `harness/`; the oracle is reached only via `oracle.py` subprocess.
- Cost tracking is first-class: analyzer LLM spend flows into `state["llm_cost_usd"]` (the field the API runner sums into `RunCost.total_usd`) and onto `AnalyzerHypothesis.compute_cost_usd`.
- Every score is an in-silico oracle score — no real-world efficacy claims (PRD N6).
- `proposer.py` and `test_proposer.py` are NOT modified (Key decision 3 in the spec).
- Schema: `metadata.create_all` stays; recreate the dev DB for the new column; Alembic deferred.
- mypy strict on all new code: `uv run mypy -p capychem -p capychem.api`. ruff: `uv run ruff check .`. Tests: `uv run pytest`.
- Reasoning ON for the analyzer (omit `thinking:disabled`); reasoning OFF stays only on the proposer.
- Hypothesis schema is exactly `{focus: str, avoid: list[str]}` + prose; no richer fields.

**Reference:** `docs/superpowers/specs/2026-06-28-analyzer-agent-design.md`.

---

### Task 1: Pure data types + analyzer summary builder

**Files:**
- Modify: `packages/core/capychem/loop/state.py` (add `Hypothesis`, `AnalyzerSummary`, two `LoopState` keys)
- Modify: `packages/core/capychem/loop/logic.py` (add `build_analyzer_summary`)
- Test: `packages/core/tests/test_loop_logic.py` (append)

**Interfaces:**
- Produces:
  - `Hypothesis(structured: dict[str, Any] | None, text: str, note: str | None = None)` — frozen.
  - `AnalyzerSummary(top: list[tuple[str, float]], bottom: list[tuple[str, float]], recent_top10_means: list[float], prior: Hypothesis | None)` — frozen.
  - `build_analyzer_summary(population: list[Scored], score_history: list[float], prior: Hypothesis | None, *, k: int = 10) -> AnalyzerSummary`
  - `LoopState` gains `analyzer_hypothesis: Hypothesis | None` and `gen_db_id: int`.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_loop_logic.py`:

```python
def test_build_analyzer_summary_top_bottom_and_deltas() -> None:
    from capychem.loop.logic import build_analyzer_summary
    from capychem.loop.state import Hypothesis

    pop = [s("c1ccccc1", 0.9, 1), s("CCO", 0.5, 2), s("CCN", 0.4, 3), s("CCC", 0.1, 4)]
    prior = Hypothesis(structured={"focus": "x", "avoid": ["y"]}, text="t")
    summary = build_analyzer_summary(pop, [0.3, 0.5, 0.7, 0.8], prior, k=2)
    assert summary.top == [("c1ccccc1", 0.9), ("CCO", 0.5)]
    assert summary.bottom == [("CCN", 0.4), ("CCC", 0.1)]
    assert summary.recent_top10_means == [0.5, 0.7, 0.8]  # last 3 only
    assert summary.prior is prior


def test_build_analyzer_summary_is_deterministic() -> None:
    from capychem.loop.logic import build_analyzer_summary

    pop = [s("CCO", 0.5, 1), s("CCN", 0.5, 2)]
    a = build_analyzer_summary(pop, [0.5], None)
    b = build_analyzer_summary(pop, [0.5], None)
    assert a == b


def test_build_analyzer_summary_no_bottom_when_small_pop() -> None:
    from capychem.loop.logic import build_analyzer_summary

    pop = [s("CCO", 0.5, 1), s("CCN", 0.4, 2)]
    summary = build_analyzer_summary(pop, [], None, k=10)
    assert summary.top == [("CCO", 0.5), ("CCN", 0.4)]
    assert summary.bottom == []  # pop smaller than k -> no separate bottom slice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_logic.py::test_build_analyzer_summary_top_bottom_and_deltas -x`
Expected: FAIL with `ImportError: cannot import name 'build_analyzer_summary'` (or `Hypothesis`).

- [ ] **Step 3: Add the dataclasses to `state.py`**

In `packages/core/capychem/loop/state.py`, after the `Scored` dataclass, add:

```python
@dataclass(frozen=True)
class Hypothesis:
    """An analyzer hypothesis threaded through the loop. ``structured`` is
    ``{"focus": str, "avoid": list[str]}`` or None (no usable signal -> the
    proposer falls back to its unconditioned prompt). ``note`` records a
    fallback such as "no new signal"."""

    structured: dict[str, Any] | None
    text: str
    note: str | None = None


@dataclass(frozen=True)
class AnalyzerSummary:
    """The compact, deterministic view of one generation the analyzer reasons
    over. Built identically in the product loop and the headless runner (G6)."""

    top: list[tuple[str, float]]
    bottom: list[tuple[str, float]]
    recent_top10_means: list[float]
    prior: Hypothesis | None
```

Then add two keys inside `class LoopState(TypedDict, total=False):` (alongside the other carriers):

```python
    analyzer_hypothesis: Hypothesis | None  # current hypothesis, threaded to next propose (slice 01)
    gen_db_id: int  # the just-persisted Generation row id, for the analyze node to link
```

(`Any` and `dataclass` are already imported in `state.py`.)

- [ ] **Step 4: Add `build_analyzer_summary` to `logic.py`**

In `packages/core/capychem/loop/logic.py`, update the import line and add the function:

```python
from capychem.loop.state import AnalyzerSummary, Hypothesis, Scored
```

```python
def build_analyzer_summary(
    population: list[Scored],
    score_history: list[float],
    prior: Hypothesis | None,
    *,
    k: int = 10,
) -> AnalyzerSummary:
    """Compact, deterministic analyzer input: the top-k and bottom-k survivors by
    score, the last 3 top-10-mean values (the recent trajectory), and the prior
    hypothesis. Pure — no I/O — so it reproduces in both loop paths (G6)."""
    ranked = sorted(population, key=_sort_key)
    top = [(m.smiles, m.score) for m in ranked[:k]]
    bottom = [(m.smiles, m.score) for m in ranked[-k:]] if len(ranked) > k else []
    return AnalyzerSummary(top=top, bottom=bottom, recent_top10_means=score_history[-3:], prior=prior)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_logic.py -x`
Expected: PASS (all, including the 3 new).

- [ ] **Step 6: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/loop/state.py packages/core/capychem/loop/logic.py packages/core/tests/test_loop_logic.py
git commit -m "feat(analyzer): hypothesis types + analyzer summary builder"
```

---

### Task 2: Analyzer adapter — stub backend + hypothesis parsing

**Files:**
- Create: `packages/core/capychem/analyzer.py`
- Test: `packages/core/tests/test_analyzer.py` (new)

**Interfaces:**
- Consumes: `proposer.{ProposerError, TransientProposerError, _deepseek_chat, _deepseek_api_key, llm_model, llm_usd_per_1k_in, llm_usd_per_1k_out}` (reused, unchanged).
- Produces:
  - `AnalyzerResult(text: str, structured: dict[str, Any] | None, tokens_in: int, tokens_out: int, cost_usd: float = 0.0, note: str | None = None)` — frozen.
  - `parse_hypothesis(text: str) -> dict[str, Any] | None`
  - `analyze_async(prompt: str, *, seed: int = 0) -> AnalyzerResult`
  - `analyze_sync(prompt: str, *, seed: int = 0) -> AnalyzerResult`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_analyzer.py`:

```python
"""Analyzer adapter: stub determinism + hypothesis parsing (milestone-03 slice 01)."""

from __future__ import annotations

import pytest
from capychem import analyzer
from capychem.analyzer import AnalyzerResult, analyze_async, parse_hypothesis


def test_parse_hypothesis_valid() -> None:
    out = parse_hypothesis('Some prose.\n{"focus": "increase logP", "avoid": ["phenol", "nitro"]}')
    assert out == {"focus": "increase logP", "avoid": ["phenol", "nitro"]}


def test_parse_hypothesis_takes_last_block() -> None:
    out = parse_hypothesis('{"focus": "a", "avoid": []} then {"focus": "b", "avoid": ["c"]}')
    assert out == {"focus": "b", "avoid": ["c"]}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        '{"focus": "x"}',  # missing avoid
        '{"avoid": ["y"]}',  # missing focus
        '{"focus": 1, "avoid": ["y"]}',  # focus not a string
        '{"focus": "x", "avoid": "y"}',  # avoid not a list
        '{"focus": "x", "avoid": [1, 2]}',  # avoid items not strings
        "{not valid json}",
    ],
)
def test_parse_hypothesis_rejects_malformed(text: str) -> None:
    assert parse_hypothesis(text) is None


async def test_stub_is_deterministic_and_structured(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    a = await analyze_async("summarize gen 3", seed=7)
    b = await analyze_async("summarize gen 3", seed=7)
    assert isinstance(a, AnalyzerResult)
    assert a.structured == b.structured
    assert a.structured is not None
    assert isinstance(a.structured["focus"], str)
    assert isinstance(a.structured["avoid"], list)
    assert a.cost_usd == 0.0
    assert a.note is None


async def test_stub_seed_varies_hypothesis(monkeypatch) -> None:
    # The stub maps one (seed, prompt) to one of a small pool, so any TWO specific
    # seeds may collide. Assert the stub is seed-SENSITIVE across a range instead.
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    foci = {(await analyze_async("p", seed=s)).structured["focus"] for s in range(10)}
    assert len(foci) > 1


async def test_unknown_backend_raises(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_ANALYZER_BACKEND"):
        await analyze_async("p")


async def test_modal_backend_not_implemented_this_slice(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "modal")
    with pytest.raises(analyzer.ProposerError, match="not implemented"):
        await analyze_async("p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_analyzer.py -x`
Expected: FAIL with `ModuleNotFoundError: No module named 'capychem.analyzer'`.

- [ ] **Step 3: Write `analyzer.py` (stub + parse only)**

Create `packages/core/capychem/analyzer.py`:

```python
"""DeepSeek-v4-pro analyzer adapter (milestone-03 slice 01).

The analyzer is a SEPARATE LLM call from the proposer. It runs with reasoning ON
(the proposer forces it OFF for short SMILES) and a generous output budget, then
forms a {"focus", "avoid"} hypothesis from one generation's results. It REUSES
the proposer's DeepSeek transport (proposer is the DeepSeek-client home) but
builds its own reasoning-ON payload + content/usage extraction + parse — do NOT
copy the proposer's thinking:disabled / 128-token payload.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from capychem.proposer import (
    ProposerError,
    TransientProposerError,
    _deepseek_api_key,
    _deepseek_chat,
    llm_model,
    llm_usd_per_1k_in,
    llm_usd_per_1k_out,
)

# Reasoning ON needs room for the chain-of-thought tail PLUS the JSON hypothesis.
_ANALYZER_MAX_OUTPUT_TOKENS = 2048
# Lower than the proposer's 0.7: stabler analysis, better G6 reproducibility.
_ANALYZER_TEMPERATURE = 0.3


@dataclass(frozen=True)
class AnalyzerResult:
    """One analyzer call. ``structured`` is the parsed {"focus","avoid"} or None
    (malformed/empty/off-topic -> the node falls back). ``note`` flags a fallback."""

    text: str
    structured: dict[str, Any] | None
    tokens_in: int
    tokens_out: int
    cost_usd: float = 0.0
    note: str | None = None


def _analyzer_backend() -> str:
    return os.environ.get("CAPYCHEM_ANALYZER_BACKEND", "stub")


def parse_hypothesis(text: str) -> dict[str, Any] | None:
    """Extract the LAST flat ``{...}`` JSON object that has ``focus: str`` and
    ``avoid: list[str]``. Return None on any failure (empty / non-JSON / missing
    keys / wrong types). The schema is flat, so a brace-free body regex suffices."""
    if not text:
        return None
    for blob in reversed(re.findall(r"\{[^{}]*\}", text, re.DOTALL)):
        try:
            obj = json.loads(blob)
        except ValueError:
            continue
        focus = obj.get("focus")
        avoid = obj.get("avoid")
        if (
            isinstance(focus, str)
            and isinstance(avoid, list)
            and all(isinstance(a, str) for a in avoid)
        ):
            return {"focus": focus, "avoid": avoid}
    return None


# --- stub backend (deterministic, network-free) ----------------------------

_STUB_HYPOTHESES: tuple[tuple[str, list[str]], ...] = (
    ("increase lipophilicity (higher logP)", ["polar surface area"]),
    ("add an aromatic ring", ["long aliphatic chains"]),
    ("introduce a hydrogen-bond donor", ["halogen substituents"]),
    ("add a basic nitrogen", ["carboxylic acids"]),
    ("rigidify the scaffold", ["rotatable bonds"]),
)


def _stub_analyze(prompt: str, *, seed: int) -> AnalyzerResult:
    digest = hashlib.sha256(f"{seed}:{prompt}".encode()).digest()
    focus, avoid = _STUB_HYPOTHESES[int.from_bytes(digest[:4], "big") % len(_STUB_HYPOTHESES)]
    structured = {"focus": focus, "avoid": list(avoid)}
    text = f"Focus on {focus}; avoid {', '.join(avoid)}."
    return AnalyzerResult(text=text, structured=structured, tokens_in=0, tokens_out=0, cost_usd=0.0)


# --- public API -------------------------------------------------------------


async def analyze_async(prompt: str, *, seed: int = 0) -> AnalyzerResult:
    """Analyze one generation via the configured backend. ``stub`` (default) is
    deterministic + free; ``direct`` calls DeepSeek with reasoning ON; ``modal``
    is deferred this slice."""
    backend = _analyzer_backend()
    if backend == "stub":
        return _stub_analyze(prompt, seed=seed)
    if backend == "direct":
        return await _direct_analyze(prompt, seed=seed)
    if backend == "modal":
        raise ProposerError(
            "Modal analyzer backend is not implemented this slice; use 'stub' or 'direct'"
        )
    raise ValueError(
        f"Set CAPYCHEM_ANALYZER_BACKEND to 'stub' or 'direct' (got {backend!r})"
    )


def analyze_sync(prompt: str, *, seed: int = 0) -> AnalyzerResult:
    """Synchronous bridge for the headless eval path (no running event loop)."""
    import asyncio

    return asyncio.run(analyze_async(prompt, seed=seed))
```

Note: `_direct_analyze` is referenced by `analyze_async` but defined in Task 3. To keep Task 2 importable and green, add a temporary stub at the bottom that Task 3 replaces:

```python
async def _direct_analyze(prompt: str, *, seed: int) -> AnalyzerResult:  # replaced in Task 3
    raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_analyzer.py -x`
Expected: PASS (the parse matrix + stub determinism/seed-sensitivity + backend dispatch).

- [ ] **Step 5: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/analyzer.py packages/core/tests/test_analyzer.py
git commit -m "feat(analyzer): stub backend + hypothesis parsing"
```

---

### Task 3: Analyzer adapter — direct DeepSeek backend (reasoning ON)

**Files:**
- Modify: `packages/core/capychem/analyzer.py` (replace the `_direct_analyze` stub)
- Test: `packages/core/tests/test_analyzer.py` (append)

**Interfaces:**
- Consumes: `analyzer._deepseek_chat` (patchable seam, imported from proposer).
- Produces: `_direct_analyze(prompt, *, seed) -> AnalyzerResult` (real DeepSeek; reasoning ON; transient-degrade).

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_analyzer.py`:

```python
async def test_direct_payload_enables_reasoning_and_big_budget(monkeypatch) -> None:
    # The analyzer is the OPPOSITE of the proposer: reasoning ON (no thinking:disabled)
    # and a generous max_tokens for the chain-of-thought tail + the JSON hypothesis.
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_IN", "0.001")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_OUT", "0.002")
    captured: dict = {}

    async def fake_chat(payload, *, api_key):
        captured.update(payload)
        assert api_key == "sk-test"
        return {
            "choices": [{"message": {"content": 'ok\n{"focus": "logP", "avoid": ["phenol"]}'}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 700},
        }

    monkeypatch.setattr(analyzer, "_deepseek_chat", fake_chat)
    out = await analyze_async("analyze this", seed=5)
    assert "thinking" not in captured  # reasoning ON
    assert captured["max_tokens"] == analyzer._ANALYZER_MAX_OUTPUT_TOKENS
    assert captured["seed"] == 5
    assert out.structured == {"focus": "logP", "avoid": ["phenol"]}
    assert out.tokens_in == 300 and out.tokens_out == 700
    # 300/1000*0.001 + 700/1000*0.002 = 0.0017
    assert out.cost_usd == pytest.approx(0.0017)
    assert out.note is None


async def test_direct_malformed_content_falls_back_to_none(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def fake_chat(payload, *, api_key):
        return {
            "choices": [{"message": {"content": "I could not decide."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    monkeypatch.setattr(analyzer, "_deepseek_chat", fake_chat)
    out = await analyze_async("p")
    assert out.structured is None
    assert out.note == "no new signal"
    assert out.text == "I could not decide."  # raw kept for the trace/history


async def test_direct_transient_error_degrades(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def boom(payload, *, api_key):
        raise analyzer.TransientProposerError("rate limited")

    monkeypatch.setattr(analyzer, "_deepseek_chat", boom)
    out = await analyze_async("p")
    assert out.structured is None and out.cost_usd == 0.0 and out.note == "no new signal"


async def test_direct_missing_key_raises(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "direct")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(analyzer.ProposerError, match="DEEPSEEK_API_KEY"):
        await analyze_async("p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_analyzer.py::test_direct_payload_enables_reasoning_and_big_budget -x`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Replace the `_direct_analyze` stub**

In `packages/core/capychem/analyzer.py`, replace the temporary `_direct_analyze` with:

```python
# --- direct backend (DeepSeek, reasoning ON) --------------------------------


async def _one_analysis_row(prompt: str, *, seed: int, api_key: str) -> dict[str, Any]:
    """One DeepSeek analyzer request. Reasoning ON: omit thinking:disabled and
    leave a generous max_tokens so the chain-of-thought tail + JSON fit. Returns
    a {raw, tokens_in, tokens_out} row carrying this request's own usage."""
    payload = {
        "model": llm_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": _ANALYZER_TEMPERATURE,
        "seed": seed,
        "max_tokens": _ANALYZER_MAX_OUTPUT_TOKENS,
        # NO "thinking": {"type": "disabled"} — the analyzer WANTS chain-of-thought;
        # message.content holds the post-reasoning answer (the prose + JSON hypothesis).
    }
    body = await _deepseek_chat(payload, api_key=api_key)
    try:
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProposerError(
            f"DeepSeek analyzer response missing choices/content: {repr(body)[:500]}"
        ) from exc
    usage = body.get("usage", {})
    return {
        "raw": raw or "",
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
    }


async def _direct_analyze(prompt: str, *, seed: int) -> AnalyzerResult:
    api_key = _deepseek_api_key()
    try:
        row = await _one_analysis_row(prompt, seed=seed, api_key=api_key)
    except TransientProposerError:
        # Degrade like the proposer: a transient blip -> no signal -> node fallback.
        return AnalyzerResult(
            text="", structured=None, tokens_in=0, tokens_out=0, cost_usd=0.0, note="no new signal"
        )
    cost = (row["tokens_in"] / 1000.0) * llm_usd_per_1k_in() + (
        row["tokens_out"] / 1000.0
    ) * llm_usd_per_1k_out()
    structured = parse_hypothesis(row["raw"])
    return AnalyzerResult(
        text=row["raw"],
        structured=structured,
        tokens_in=row["tokens_in"],
        tokens_out=row["tokens_out"],
        cost_usd=cost,
        note=None if structured is not None else "no new signal",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_analyzer.py -x`
Expected: PASS (all).

- [ ] **Step 5: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/analyzer.py packages/core/tests/test_analyzer.py
git commit -m "feat(analyzer): direct DeepSeek backend with reasoning ON"
```

---

### Task 4: Strategy seam — analyzer prompt + prompt conditioning + fake updates

**Files:**
- Modify: `packages/core/capychem/loop/strategy.py`
- Test: `packages/core/tests/test_strategy.py` (append)
- Modify (fakes, add `hypothesis=None` to signature): `packages/core/tests/test_loop_llm_e2e.py:105`, `packages/core/tests/test_loop_propose.py:43,57`, `packages/core/tests/test_loop_valid_smiles.py:88`, `packages/core/tests/test_eval_beat.py:20`, `packages/core/tests/test_eval_runner.py:90,118`, `apps/api/tests/test_cost_gate.py:62`

**Interfaces:**
- Consumes: `analyzer.{AnalyzerResult, analyze_async, analyze_sync}`, `state.{AnalyzerSummary, Hypothesis}`.
- Produces:
  - `build_prompt(task, population, n, hypothesis: Hypothesis | None = None) -> str` (extended)
  - `propose_llm_async(task, population, *, n, seed, hypothesis: Hypothesis | None = None)` (extended)
  - `propose_llm_sync(task, population, *, n, seed, hypothesis: Hypothesis | None = None)` (extended)
  - `build_analyzer_prompt(summary: AnalyzerSummary) -> str`
  - `run_analyzer_async(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult`
  - `run_analyzer_sync(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult`

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_strategy.py`:

```python
def test_build_prompt_unchanged_without_hypothesis() -> None:
    from capychem.loop.state import Hypothesis

    pop = [("CCO", 0.9), ("c1ccccc1", 0.4)]
    base = strategy.build_prompt("jnk3", pop, 5)
    assert strategy.build_prompt("jnk3", pop, 5, hypothesis=None) == base
    # A hypothesis with no structured signal (neutral fallback) must ALSO not change it.
    neutral = Hypothesis(structured=None, text="No new signal.", note="no new signal")
    assert strategy.build_prompt("jnk3", pop, 5, hypothesis=neutral) == base
    assert "Guidance" not in base


def test_build_prompt_appends_guidance_when_hypothesis_present() -> None:
    from capychem.loop.state import Hypothesis

    pop = [("CCO", 0.9)]
    h = Hypothesis(structured={"focus": "increase logP", "avoid": ["phenol", "nitro"]}, text="Push logP.")
    p = strategy.build_prompt("jnk3", pop, 5, hypothesis=h)
    assert "Guidance from analysis" in p
    assert "increase logP" in p
    assert "phenol, nitro" in p
    assert "Push logP." in p


def test_build_analyzer_prompt_mentions_summary() -> None:
    from capychem.loop.state import AnalyzerSummary

    summary = AnalyzerSummary(
        top=[("c1ccccc1", 0.9)], bottom=[("CCC", 0.1)], recent_top10_means=[0.5, 0.7], prior=None
    )
    p = strategy.build_analyzer_prompt(summary)
    assert "c1ccccc1" in p and "CCC" in p
    assert "focus" in p and "avoid" in p  # asks for the JSON schema


async def test_run_analyzer_async_wires_summary_to_adapter(monkeypatch) -> None:
    from capychem.analyzer import AnalyzerResult
    from capychem.loop.state import AnalyzerSummary

    captured: dict = {}

    async def fake_analyze(prompt, *, seed=0):
        captured.update(prompt=prompt, seed=seed)
        return AnalyzerResult(text="t", structured={"focus": "x", "avoid": []}, tokens_in=1, tokens_out=2)

    monkeypatch.setattr(strategy, "analyze_async", fake_analyze)
    summary = AnalyzerSummary(top=[("CCO", 0.5)], bottom=[], recent_top10_means=[], prior=None)
    out = await strategy.run_analyzer_async(summary, seed=9)
    assert out.structured == {"focus": "x", "avoid": []}
    assert captured["seed"] == 9
    assert "CCO" in captured["prompt"]


def test_run_analyzer_sync_bridges_async(monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    from capychem.loop.state import AnalyzerSummary

    out = strategy.run_analyzer_sync(
        AnalyzerSummary(top=[("CCO", 0.5)], bottom=[], recent_top10_means=[], prior=None), seed=3
    )
    assert out.structured is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_strategy.py::test_build_prompt_appends_guidance_when_hypothesis_present -x`
Expected: FAIL with `TypeError: build_prompt() got an unexpected keyword argument 'hypothesis'`.

- [ ] **Step 3: Extend `strategy.py`**

In `packages/core/capychem/loop/strategy.py`, add imports:

```python
from capychem.analyzer import AnalyzerResult, analyze_async, analyze_sync
from capychem.loop.state import AnalyzerSummary, Hypothesis
```

Replace `build_prompt` with the hypothesis-aware version (the `hypothesis=None` output is BYTE-IDENTICAL to today — `{lines}\n` + `""` + `\n` == the old `{lines}\n\n`):

```python
def build_prompt(
    task: str,
    population: list[tuple[str, float]],
    n: int,
    hypothesis: Hypothesis | None = None,
) -> str:
    """MOLLEO-style single-molecule mutation prompt, optionally conditioned on the
    analyzer hypothesis. With no structured hypothesis the output is byte-identical
    to the unconditioned milestone-02 prompt (gen-1 / graph_ga regression)."""
    top = sorted(population, key=lambda p: (-p[1], p[0]))[:10]
    lines = "\n".join(f"{smi}\t{score:.4f}" for smi, score in top)
    guidance = ""
    if hypothesis is not None and hypothesis.structured is not None:
        s = hypothesis.structured
        guidance = (
            f"\nGuidance from analysis of the last generation: focus on {s['focus']}; "
            f"avoid {', '.join(s['avoid'])}. {hypothesis.text}\n"
        )
    return (
        f"You are optimizing molecules for the '{task}' objective (higher score is better).\n"
        f"Current best molecules (SMILES, score):\n{lines}\n"
        f"{guidance}\n"
        "Propose ONE new, valid, drug-like molecule likely to score higher. "
        "Output only its SMILES string — no prose, no code fences."
    )
```

Add `hypothesis` to both LLM wrappers (thread to `build_prompt`):

```python
async def propose_llm_async(
    task: str,
    population: list[tuple[str, float]],
    *,
    n: int,
    seed: int,
    hypothesis: Hypothesis | None = None,
) -> list[ProposalResult]:
    """Propose ``n`` LLM candidates with a pinned temperature + per-gen seed (G6),
    optionally conditioned on the analyzer hypothesis (milestone 03)."""
    return await propose_batch_async(
        build_prompt(task, population, n, hypothesis), n, temperature=LLM_TEMPERATURE, seed=seed
    )


def propose_llm_sync(
    task: str,
    population: list[tuple[str, float]],
    *,
    n: int,
    seed: int,
    hypothesis: Hypothesis | None = None,
) -> list[ProposalResult]:
    """Synchronous bridge for the headless eval path (no running event loop)."""
    return asyncio.run(propose_llm_async(task, population, n=n, seed=seed, hypothesis=hypothesis))
```

Add the analyzer seam (after `propose_llm_sync`):

```python
def build_analyzer_prompt(summary: AnalyzerSummary) -> str:
    """Template the generation summary into the analyzer instruction. Asks for
    prose followed by a JSON {"focus","avoid"} object so parse_hypothesis can lift it."""
    top = "\n".join(f"{smi}\t{score:.4f}" for smi, score in summary.top)
    bottom = "\n".join(f"{smi}\t{score:.4f}" for smi, score in summary.bottom)
    deltas = ", ".join(f"{d:.4f}" for d in summary.recent_top10_means)
    prior = ""
    if summary.prior is not None and summary.prior.structured is not None:
        ps = summary.prior.structured
        prior = f"Prior hypothesis: focus={ps['focus']}; avoid={ps['avoid']}.\n"
    return (
        "You are analyzing one generation of a molecular optimization loop.\n"
        f"Top molecules (SMILES, score):\n{top}\n\n"
        f"Bottom molecules (SMILES, score):\n{bottom}\n\n"
        f"Recent top-10 mean trajectory: {deltas}\n"
        f"{prior}\n"
        "Reason about which structural features are improving the score, then output a short "
        "prose explanation followed by a JSON object on its own line of the form "
        '{"focus": "<one concrete thing to pursue>", "avoid": ["<thing to steer away from>"]}.'
    )


async def run_analyzer_async(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult:
    """Build the analyzer prompt + call the adapter (async product-loop path)."""
    return await analyze_async(build_analyzer_prompt(summary), seed=seed)


def run_analyzer_sync(summary: AnalyzerSummary, *, seed: int) -> AnalyzerResult:
    """Build the analyzer prompt + call the adapter (sync headless path)."""
    return analyze_sync(build_analyzer_prompt(summary), seed=seed)
```

- [ ] **Step 4: Update the 8 existing LLM fakes to accept `hypothesis=None`**

The callers will soon pass `hypothesis=...`. Update every fake that monkeypatches `propose_llm_async` / `propose_llm_sync` so its signature accepts the kwarg. Find them:

Run: `grep -rn "def fake_llm" packages/core/tests apps/api/tests`

In each of these, change `*, n, seed` to `*, n, seed, hypothesis=None`:
- `packages/core/tests/test_loop_llm_e2e.py:105` (`async def fake_llm(task, population, *, n, seed)`)
- `packages/core/tests/test_loop_propose.py:43` and `:57`
- `packages/core/tests/test_loop_valid_smiles.py:88`
- `packages/core/tests/test_eval_beat.py:20`
- `packages/core/tests/test_eval_runner.py:90` and `:118`
- `apps/api/tests/test_cost_gate.py:62`

Example edit (test_loop_llm_e2e.py:105):

```python
    async def fake_llm(task, population, *, n, seed, hypothesis=None):  # type: ignore[no-untyped-def]
```

(Only the signature changes; bodies are untouched. A fake that patches `propose_batch_async`, `_stub_propose`, or `propose_offspring` instead does NOT need editing — only the `propose_llm_async`/`propose_llm_sync` fakes.)

- [ ] **Step 5: Run the full suite to verify green**

Run: `uv run pytest packages/core apps/api -q`
Expected: PASS (new strategy tests + all existing, including the updated fakes).

- [ ] **Step 6: Typecheck + lint + commit**

```bash
uv run mypy -p capychem -p capychem.api && uv run ruff check .
git add packages/core/capychem/loop/strategy.py packages/core/tests/test_strategy.py \
  packages/core/tests/test_loop_llm_e2e.py packages/core/tests/test_loop_propose.py \
  packages/core/tests/test_loop_valid_smiles.py packages/core/tests/test_eval_beat.py \
  packages/core/tests/test_eval_runner.py apps/api/tests/test_cost_gate.py
git commit -m "feat(analyzer): analyzer prompt seam + prompt conditioning"
```

---

### Task 5: Schema — `AnalyzerHypothesis` table + `Generation` link

**Files:**
- Modify: `packages/core/capychem/db/models.py`
- Modify: `packages/core/capychem/db/session.py` (docstring only)
- Test: `packages/core/tests/test_models_analyzer.py` (new)

**Interfaces:**
- Produces:
  - `AnalyzerHypothesis` model: `id, run_id, after_generation_index, text, structured_json, tokens_in, tokens_out, compute_cost_usd`.
  - `Generation.analyzer_hypothesis_id: int | None`.

**Note (test/CI Postgres, not just dev):** `create_all` adds the new TABLE but never ALTERs the existing `generations` table to add the new COLUMN. The core loop tests use ephemeral in-memory sqlite (fine — built fresh). But the api-tier tests (`apps/api/tests/test_cost_gate.py`, `test_api.py`, `test_runner.py`) run against real Postgres via `make_engine()` + `init_schema`. On any **already-populated** Postgres (a shared local/CI DB that already has a `generations` table), the new column is absent and every `persist` (which always inserts a `Generation`) plus the `analyze` UPDATE will fail. **Before running the api-tier tests after this task, drop/recreate the Postgres DB** (or ensure CI uses an ephemeral container). This is the create_all/Alembic trade-off the milestone accepted.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_models_analyzer.py`:

```python
"""AnalyzerHypothesis table + Generation link create + persist (slice 01)."""

from __future__ import annotations

import pytest
from capychem.db.models import AnalyzerHypothesis, Base, Generation, Run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def sm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_persist_hypothesis_and_link_generation(sm) -> None:
    async with sm() as s:
        run = Run(task="qed", budget=10, plateau_window=3, pop_size=2, offspring=2,
                  mutation_rate=0.01, seed=1)
        s.add(run)
        await s.flush()
        gen = Generation(run_id=run.id, index=1, proposer_used="llm")
        s.add(gen)
        await s.flush()
        hyp = AnalyzerHypothesis(
            run_id=run.id, after_generation_index=1, text="Focus on logP.",
            structured_json={"focus": "logP", "avoid": ["phenol"]},
            tokens_in=300, tokens_out=700, compute_cost_usd=0.0017,
        )
        s.add(hyp)
        await s.flush()
        gen.analyzer_hypothesis_id = hyp.id
        await s.commit()

    async with sm() as s:
        loaded_gen = (await s.execute(select(Generation))).scalar_one()
        loaded_hyp = (await s.execute(select(AnalyzerHypothesis))).scalar_one()
        assert loaded_gen.analyzer_hypothesis_id == loaded_hyp.id
        assert loaded_hyp.structured_json == {"focus": "logP", "avoid": ["phenol"]}
        assert loaded_hyp.after_generation_index == 1
        assert loaded_hyp.compute_cost_usd == pytest.approx(0.0017)


async def test_generation_hypothesis_id_nullable(sm) -> None:
    async with sm() as s:
        run = Run(task="qed", budget=10, plateau_window=3, pop_size=2, offspring=2,
                  mutation_rate=0.01, seed=1)
        s.add(run)
        await s.flush()
        gen = Generation(run_id=run.id, index=0, proposer_used="starting")  # gen 0: no hypothesis
        s.add(gen)
        await s.commit()
        assert gen.analyzer_hypothesis_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_models_analyzer.py -x`
Expected: FAIL with `ImportError: cannot import name 'AnalyzerHypothesis'`.

- [ ] **Step 3: Add the model + column**

In `packages/core/capychem/db/models.py`, update the import line to add `Text`:

```python
from sqlalchemy import JSON, ForeignKey, Index, String, Text, func
```

Add `analyzer_hypothesis_id` to `class Generation` (after `ended_at`):

```python
    analyzer_hypothesis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyzer_hypotheses.id", ondelete="SET NULL"), default=None
    )
```

Add the new model at the end of the file:

```python
class AnalyzerHypothesis(Base):
    __tablename__ = "analyzer_hypotheses"
    __table_args__ = (Index("ix_analyzerhyp_run_after", "run_id", "after_generation_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    after_generation_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    compute_cost_usd: Mapped[float] = mapped_column(default=0.0)
```

Update the module docstring (top of file) from "Five entities" / "AnalyzerHypothesis arrives in a later slice":

```python
"""Async SQLAlchemy 2.0 models for CapyChem run state (SPEC §6.2).

Six entities: Run, Generation, Candidate, OracleCall, RunCost, AnalyzerHypothesis
(added milestone-03 slice 01). Schema is bootstrapped via metadata.create_all
(db/session.py); after an additive change recreate the dev DB (drop/recreate) —
Alembic is deferred until a persisted DB must be migrated without data loss.
"""
```

- [ ] **Step 4: Update `session.py` docstring**

In `packages/core/capychem/db/session.py`, change the docstring line about Alembic:

```python
"""Async engine, sessionmaker, and first-connect schema bootstrap.

metadata.create_all bootstraps the schema; it creates missing tables but does NOT
ALTER existing ones, so after an additive change (e.g. milestone-03's
Generation.analyzer_hypothesis_id column) recreate the dev DB (drop/recreate).
Reads CAPYCHEM_DATABASE_URL (asyncpg driver). Alembic is deferred.
"""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_models_analyzer.py -x`
Expected: PASS.

- [ ] **Step 6: Typecheck + lint + commit**

```bash
uv run mypy -p capychem && uv run ruff check packages/core
git add packages/core/capychem/db/models.py packages/core/capychem/db/session.py packages/core/tests/test_models_analyzer.py
git commit -m "feat(analyzer): AnalyzerHypothesis schema + Generation link"
```

---

### Task 6: The `analyze` node — product loop integration

**Files:**
- Modify: `packages/core/capychem/loop/graph.py` (persist returns `gen_db_id`; new `analyze` node + propose conditioning + edges)
- Modify: `apps/api/capychem/api/runner.py` (recursion-limit comment only; the `*7` multiplier already covers 7 nodes)
- Test: `packages/core/tests/test_loop_analyze.py` (new)

**Interfaces:**
- Consumes: `strategy.run_analyzer_async`, `build_analyzer_summary`, `Hypothesis`, `AnalyzerHypothesis`, `state["gen_db_id"]`, `state.get("analyzer_hypothesis")`.
- Produces: loop edges `persist → analyze → stop_check`; `state["analyzer_hypothesis"]` set after each llm gen ≥1; `state["llm_cost_usd"]` includes analyzer cost.

**Note (known minor, documented):** the API runner records `RunCost` at each `persist` (curve-growth) yield. An analyzer call's cost lands in `RunCost` at the FOLLOWING generation's persist; the final generation's analyzer cost (~sub-cent) is in `final_state["llm_cost_usd"]` but not re-persisted. Acceptable for slice 01 (single-user MVP, the gate still fires within one generation). Out of scope to fix here.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_loop_analyze.py`:

```python
"""The analyze node: runs for llm gen>=1, persists + links, threads, falls back."""

from __future__ import annotations

import pytest
from capychem.analyzer import AnalyzerResult
from capychem.db.models import AnalyzerHypothesis, Base, Generation
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


def _initial(run_id: int, cfg: RunConfig) -> LoopState:
    return {
        "run_id": run_id, "task": cfg.task, "budget": cfg.budget, "seed": cfg.seed,
        "pop_size": cfg.pop_size, "offspring": cfg.offspring, "mutation_rate": cfg.mutation_rate,
        "plateau_window": cfg.plateau_window, "max_generations": cfg.max_generations,
        "mutation_strategy": cfg.mutation_strategy, "calls_used": 0, "gen_index": 0,
        "population": [], "run_trace_id": None, "gen_span_id": None, "auc_curve": [], "done": False,
    }


async def _run(sm, cfg, monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")

    from capychem import proposer as proposer_mod

    def distinct_valid(prompt, n, *, temperature, seed):
        return [proposer_mod.ProposalResult(raw="C" * (i + 2), smiles="C" * (i + 2),
                tokens_in=0, tokens_out=0, cost_usd=0.0) for i in range(n)]

    monkeypatch.setattr(proposer_mod, "_stub_propose", distinct_valid)

    async def fake_score(smiles, task):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    final = await g.ainvoke(_initial(run_id, cfg), config={"recursion_limit": 60})
    return run_id, final


async def test_analyze_persists_and_links_for_llm(sm, monkeypatch) -> None:
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3, mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
        gens = (await s.execute(select(Generation).order_by(Generation.index))).scalars().all()
    # gen 0 (seed) has no hypothesis; gens >=1 each persist one, linked.
    assert len(hyps) >= 1
    assert all(h.after_generation_index >= 1 for h in hyps)
    gen0 = next(g for g in gens if g.index == 0)
    assert gen0.analyzer_hypothesis_id is None
    linked = [g for g in gens if g.index >= 1 and g.analyzer_hypothesis_id is not None]
    assert linked  # at least one gen>=1 linked its hypothesis
    # the threaded hypothesis is on the final state and feeds the next propose
    assert final.get("analyzer_hypothesis") is not None


async def test_graph_ga_run_does_not_analyze(sm, monkeypatch) -> None:
    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")

    async def fake_score(smiles, task):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1, cost_usd=0.0) for s in smiles]

    monkeypatch.setattr(graph_mod, "score_batch_async", fake_score)

    def fake_offspring(population, n, *, mutation_rate, seed, **kw):
        from capychem.oracle import Offspring
        return [Offspring(smiles="C" * (i + 3), parents=(0, 0)) for i in range(n)]

    monkeypatch.setattr(graph_mod.strategy, "propose_offspring", fake_offspring)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3, mutation_strategy="graph_ga")
    async with sm() as s:
        run_id = await create_run(s, cfg)
    g = graph_mod.build_graph(sm)
    await g.ainvoke(_initial(run_id, cfg), config={"recursion_limit": 60})
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
    assert hyps == []  # graph_ga is analyzer-free


async def test_analyze_fallback_on_malformed_keeps_running(sm, monkeypatch) -> None:
    # Force the analyzer to return no structured signal -> node uses neutral/last-good,
    # the loop still completes and persists a "no new signal" hypothesis.
    async def no_signal(summary, *, seed):
        return AnalyzerResult(text="unsure", structured=None, tokens_in=1, tokens_out=1,
                              cost_usd=0.0, note="no new signal")

    monkeypatch.setattr(graph_mod.strategy, "run_analyzer_async", no_signal)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3, mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    assert final["done"] is True
    async with sm() as s:
        hyps = (await s.execute(select(AnalyzerHypothesis))).scalars().all()
    assert hyps and all(h.structured_json is None for h in hyps)


async def test_analyzer_cost_flows_into_llm_cost(sm, monkeypatch) -> None:
    async def costly(summary, *, seed):
        return AnalyzerResult(text='{"focus": "x", "avoid": []}',
                              structured={"focus": "x", "avoid": []},
                              tokens_in=0, tokens_out=0, cost_usd=0.01)

    monkeypatch.setattr(graph_mod.strategy, "run_analyzer_async", costly)
    cfg = RunConfig(task="qed", budget=200, seed=42, pop_size=6, offspring=4,
                    mutation_rate=0.01, plateau_window=9, max_generations=3, mutation_strategy="llm")
    run_id, final = await _run(sm, cfg, monkeypatch)
    assert final.get("llm_cost_usd", 0.0) >= 0.01  # at least one analyzer call's cost summed in
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_loop_analyze.py::test_analyze_persists_and_links_for_llm -x`
Expected: FAIL (no hypotheses persisted — the node does not exist yet).

- [ ] **Step 3: Add imports + persist `gen_db_id` + propose conditioning in `graph.py`**

In `packages/core/capychem/loop/graph.py`, extend the model + logic + state imports:

```python
from capychem.db.models import AnalyzerHypothesis, Candidate, Generation, OracleCall
from capychem.loop.logic import (
    build_analyzer_summary,
    build_summary,
    merge_and_truncate,
    stop_reason,
)
from capychem.loop.state import Hypothesis, LoopState, Scored
```

In the `propose` node, thread the current hypothesis into the LLM call (the `if state.get("mutation_strategy", "graph_ga") == "llm":` branch):

```python
                    results = await strategy.propose_llm_async(
                        state["task"], pop, n=state["offspring"], seed=seed,
                        hypothesis=state.get("analyzer_hypothesis"),
                    )
```

In `_persist`, add `gen_db_id` to the returned dict:

```python
        return {
            "population": survivors,
            "auc_curve": curve,
            "_made_progress": bool(new_scored),
            "gen_db_id": gen.id,
        }
```

- [ ] **Step 4: Add the `_analyze` node function**

In `packages/core/capychem/loop/graph.py`, add after `_persist` (before `stop_check`):

```python
async def _analyze(
    state: LoopState, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    # The differentiator (SPEC §6.4b). Runs only for an LLM run after gen >=1
    # (gen 0 is the seed population; graph_ga has no hypothesis consumer). No-op
    # otherwise — mirrors how `fallback` no-ops for non-llm strategies.
    if state.get("mutation_strategy") != "llm" or state["gen_index"] < 1:
        return {}
    with trace.span(
        "node:analyze",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        prior = state.get("analyzer_hypothesis")
        score_history = [v for _, v in state.get("auc_curve", [])]
        summary = build_analyzer_summary(state["population"], score_history, prior)
        seed = state["seed"] + state["gen_index"]
        with trace.span(
            "llm:analyze",
            trace_id=state.get("run_trace_id"),
            parent_observation_id=state.get("gen_span_id"),
            model=proposer.llm_model(),
            seed=seed,
        ) as llm_span_id:
            result = await strategy.run_analyzer_async(summary, seed=seed)
            trace.update_span(
                llm_span_id,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=result.cost_usd,
            )
        # Effective hypothesis: the new one, else last-good, else neutral — the loop
        # never stalls on malformed/empty/off-topic output (FR-007, edge case 3).
        if result.structured is not None:
            effective = Hypothesis(structured=result.structured, text=result.text, note=None)
        elif prior is not None:
            effective = Hypothesis(structured=prior.structured, text=prior.text, note="no new signal")
        else:
            effective = Hypothesis(
                structured=None, text="No new signal; continue broad optimization.",
                note="no new signal",
            )
        async with sessionmaker() as session:
            hyp = AnalyzerHypothesis(
                run_id=state["run_id"],
                after_generation_index=state["gen_index"],
                text=effective.text,
                structured_json=effective.structured,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                compute_cost_usd=result.cost_usd,
            )
            session.add(hyp)
            await session.flush()  # hyp.id
            gen = await session.get(Generation, state["gen_db_id"])
            if gen is not None:
                gen.analyzer_hypothesis_id = hyp.id
            await session.commit()
        return {
            "analyzer_hypothesis": effective,
            "llm_cost_usd": state.get("llm_cost_usd", 0.0) + result.cost_usd,
        }
```

- [ ] **Step 5: Wire the node into the graph**

In `build_graph`, add the `analyze` closure (mirroring `persist`) and re-route the edges:

```python
    async def analyze(state: LoopState) -> dict[str, Any]:
        return await _analyze(state, sessionmaker)

    builder.add_node("persist", persist)
    builder.add_node("analyze", analyze)
    builder.add_node("stop_check", stop_check)
    builder.set_entry_point("propose")
    builder.add_edge("propose", "validate")
    builder.add_edge("validate", "fallback")
    builder.add_edge("fallback", "score")
    builder.add_edge("score", "persist")
    builder.add_edge("persist", "analyze")
    builder.add_edge("analyze", "stop_check")
    builder.add_conditional_edges("stop_check", _route, {"continue": "propose", "stop": END})
    return builder.compile()
```

(Remove the old `builder.add_edge("persist", "stop_check")`.)

- [ ] **Step 6: Update the recursion-limit comment in the API runner**

In `apps/api/capychem/api/runner.py`, update the comment (the `* 7` multiplier already covers 7 node-steps):

```python
        # Each generation is 7 node-steps (analyze added in milestone 03); allow headroom.
        recursion_limit = cfg.max_generations * 7 + 10
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_loop_analyze.py packages/core/tests/test_loop_llm_e2e.py -x`
Expected: PASS (new analyze tests + the existing llm e2e tests still green with the analyze node present).

- [ ] **Step 8: Typecheck + lint + commit**

```bash
uv run mypy -p capychem -p capychem.api && uv run ruff check .
git add packages/core/capychem/loop/graph.py apps/api/capychem/api/runner.py packages/core/tests/test_loop_analyze.py
git commit -m "feat(analyzer): analyze node wired into the product loop"
```

---

### Task 7: Headless parity — `run_reproduction(analyzer=...)`

**Files:**
- Modify: `packages/core/capychem/eval/runner.py`
- Test: `packages/core/tests/test_eval_runner.py` (append)

**Interfaces:**
- Consumes: `build_analyzer_summary`, `run_analyzer_sync`, `Hypothesis`, `propose_llm_sync(..., hypothesis=...)`.
- Produces: `run_reproduction(..., analyzer: bool = False)` — when `True` + llm strategy, threads a hypothesis through each generation identically to the product node.

- [ ] **Step 1: Write the failing test**

Append to `packages/core/tests/test_eval_runner.py`:

```python
def test_analyzer_threads_hypothesis_in_headless_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # analyzer=True wires the analyzer into the headless llm path; the propose call
    # receives a hypothesis on gens after the first.
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    seen_hypothesis: list[object] = []
    pool = ["CCO", "c1ccccc1", "CCN", "CCC", "CCCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):
        seen_hypothesis.append(hypothesis)
        return [ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                tokens_in=0, tokens_out=0) for i in range(n)]

    def fake_score(smiles, task, **kw):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setenv("CAPYCHEM_ANALYZER_BACKEND", "stub")
    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    res = run_reproduction("qed", budget=40, seed=42, pop_size=3, offspring=4,
                           patience=9, mutation_strategy="llm", analyzer=True)
    assert res.mol_buffer
    # gen 1 proposes with no hypothesis; a later gen proposes WITH one (analyzer ran).
    assert seen_hypothesis[0] is None
    assert any(h is not None for h in seen_hypothesis[1:])


def test_analyzer_off_leaves_llm_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default analyzer=False -> no analyzer call, hypothesis stays None throughout.
    from capychem.eval import runner as runner_mod
    from capychem.oracle import OracleResult
    from capychem.proposer import ProposalResult

    seen: list[object] = []
    pool = ["CCO", "c1ccccc1", "CCN", "CCC"]

    def fake_llm_sync(task, population, *, n, seed, hypothesis=None):
        seen.append(hypothesis)
        return [ProposalResult(raw=pool[i % len(pool)], smiles=pool[i % len(pool)],
                tokens_in=0, tokens_out=0) for i in range(n)]

    def fake_score(smiles, task, **kw):
        return [OracleResult(smiles=s, score=0.5, valid=True, wall_ms=1) for s in smiles]

    monkeypatch.setattr(runner_mod, "propose_llm_sync", fake_llm_sync)
    monkeypatch.setattr(runner_mod, "score_smiles", fake_score)
    monkeypatch.setattr(runner_mod, "starting_population", lambda n: pool[:n])

    run_reproduction("qed", budget=20, seed=42, pop_size=3, offspring=4,
                     patience=2, mutation_strategy="llm")  # analyzer defaults False
    assert all(h is None for h in seen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_eval_runner.py::test_analyzer_threads_hypothesis_in_headless_llm -x`
Expected: FAIL with `TypeError: run_reproduction() got an unexpected keyword argument 'analyzer'`.

- [ ] **Step 3: Thread the analyzer into `run_reproduction`**

In `packages/core/capychem/eval/runner.py`, update imports (the `logic`, `state`, and `strategy` lines change — adding `build_analyzer_summary`, `Hypothesis`, `run_analyzer_sync`; the existing `seeds` import is unchanged):

```python
from capychem.loop.logic import build_analyzer_summary, merge_and_truncate
from capychem.loop.state import Hypothesis, Scored
from capychem.loop.strategy import fallback_fill, propose_llm_sync, run_analyzer_sync
```

Add the `analyzer` parameter to the signature:

```python
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
    mutation_strategy: str = "graph_ga",
    analyzer: bool = False,
) -> ReproResult:
```

Initialize the hypothesis + score-history trackers near `generations = 1` / `prev_top = ...`:

```python
    generations = 1
    patience_left = patience
    prev_top = _top_k_mean(mol_buffer, 100)
    llm_proposed = 0
    llm_valid = 0
    hypothesis: Hypothesis | None = None
    # Match the product loop's auc_curve EXACTLY: top-10 mean of the SURVIVOR pool
    # (population), not the whole mol_buffer — so the analyzer's recent_top10_means are
    # byte-identical across paths even for small pop_size (G6). _top_k_mean(mol_buffer,…)
    # stays for the patience check (a separate quantity).
    score_history: list[float] = [_pop_top_k_mean(population, 10)]
```

Add the survivor-pool helper at module level (near `_top_k_mean`):

```python
def _pop_top_k_mean(population: list[Scored], k: int) -> float:
    scores = sorted((m.score for m in population), reverse=True)[:k]
    return sum(scores) / len(scores) if scores else 0.0
```

In the `mutation_strategy == "llm"` branch, pass the hypothesis:

```python
            results = propose_llm_sync(
                task, pop_pairs, n=offspring, seed=seed + generations, hypothesis=hypothesis
            )
```

After `generations += 1` and before the patience block, run the analyzer (mirrors the node's effective-hypothesis logic):

```python
        score_history.append(_pop_top_k_mean(population, 10))
        if analyzer and mutation_strategy == "llm":
            summary = build_analyzer_summary(population, score_history, hypothesis)
            # `generations` was already incremented above, so generation N's analyzer
            # seed must be seed+N — matching the product node's seed+gen_index for the
            # generation just scored (G6 parity). Hence `generations - 1`.
            result = run_analyzer_sync(summary, seed=seed + generations - 1)
            if result.structured is not None:
                hypothesis = Hypothesis(structured=result.structured, text=result.text)
            elif hypothesis is not None:
                hypothesis = Hypothesis(
                    structured=hypothesis.structured, text=hypothesis.text, note="no new signal"
                )
            else:
                hypothesis = Hypothesis(
                    structured=None, text="No new signal; continue broad optimization.",
                    note="no new signal",
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/core/tests/test_eval_runner.py -x`
Expected: PASS (the 2 new + all existing, including `test_llm_strategy_runs_to_budget_on_stub` which still passes hypothesis=None implicitly).

- [ ] **Step 5: Full suite + typecheck + lint**

```bash
uv run pytest packages/core apps/api -q
uv run mypy -p capychem -p capychem.api
uv run ruff check .
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add packages/core/capychem/eval/runner.py packages/core/tests/test_eval_runner.py
git commit -m "feat(analyzer): headless eval parity for the analyzer (G6)"
```

---

## Self-Review

**Spec coverage (each spec section → task):**
- `AnalyzerHypothesis` schema + `Generation.analyzer_hypothesis_id` (create_all) → Task 5. ✓
- analyzer adapter, reasoning ON, stub+direct, parse → Tasks 2–3. ✓
- `build_analyzer_summary` (pure) → Task 1. ✓
- `build_analyzer_prompt` / `run_analyzer_async/sync` / `build_prompt(hypothesis)` conditioning → Task 4. ✓
- `analyze` node (gen ≥1, llm-only, span, persist+link, cost into `llm_cost_usd`) → Task 6. ✓
- Malformed/empty/transient fallback → last-good/neutral, loop never stalls → Tasks 3 (adapter degrade) + 6 (node effective hypothesis). ✓
- Headless parity `run_reproduction(analyzer=...)`, default False unchanged → Task 7. ✓
- State fields `analyzer_hypothesis`, `gen_db_id` → Task 1 (types) + Task 6 (use). ✓
- Cost gate sees combined spend (no `cost.py` / API-gate change) → Task 6 (note on the one-gen lag). ✓
- proposer + test_proposer untouched → enforced; no task modifies them. ✓
- Observability spans → Task 6. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The Task 2 `_direct_analyze` `NotImplementedError` is an explicit, labeled temporary replaced in Task 3 (not a placeholder gap).

**Type consistency:** `Hypothesis(structured, text, note)`, `AnalyzerResult(text, structured, tokens_in, tokens_out, cost_usd, note)`, `AnalyzerSummary(top, bottom, recent_top10_means, prior)`, `build_analyzer_summary(population, score_history, prior, *, k)`, `analyze_async/sync(prompt, *, seed)`, `run_analyzer_async/sync(summary, *, seed)`, `build_prompt(..., hypothesis=None)`, `propose_llm_async/sync(..., hypothesis=None)` — names and signatures match across Tasks 1→7.

## Out of scope (deferred, explicit)

With/without value verdict on jnk3 (slice 02) · WS `analyzer.hypothesis` event + watch-live + run-detail sequence (slice 03) · 23-task registry/baselines/UI selector/`--all` sweep (slice 04) · Week-8 sweep + cost gate at scale (slice 05) · Modal `llm.analyze` worker · Alembic · operator-facing analyzer toggle · the final-generation analyzer-cost re-persist (the documented one-gen `RunCost` lag).
