# Modal `llm.propose` Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Modal `propose()` function (DeepSeek-v4-pro via its OpenAI-compatible API) plus a modern async client adapter that returns proposed SMILES + per-call token cost, mirroring the existing oracle pattern.

**Architecture:** A new `packages/core/capychem/proposer.py` adapter selects a backend by env (`stub` default, network-free, for CI; `modal` for the real DeepSeek-backed worker), exactly like `oracle.py::score_batch_async`. The worker returns raw completions + token counts; the adapter cleans the SMILES string and maps tokens→USD. A thin `propose()` Modal function lands beside `score()` in `apps/worker/app.py` on its own lightweight 3.12 image.

**Tech Stack:** Python 3.12, Modal, `requests`, pytest (async auto-mode), mypy strict, ruff.

---

## Refinement vs. design spec

The spec said the worker returns `{raw, smiles, tokens_in, tokens_out}`. This plan moves SMILES cleaning **modern-side** (adapter), so the worker returns `{raw, tokens_in, tokens_out}` and the adapter derives `smiles = _clean_smiles(raw)`. Extraction lives in one place (DRY); `ProposalResult` still exposes both `raw` and `smiles` as designed. No other deviation.

## File structure

- **Create** `packages/core/capychem/proposer.py` — the adapter. One responsibility: talk to the proposer model behind an env-selected backend and return `ProposalResult`s. Mirrors `oracle.py`.
- **Modify** `apps/worker/app.py` — add a lightweight `llm_image`, the `propose()` Modal function, and a `propose_smoke` local entrypoint. Leaves `image`/`score`/`smoke` untouched.
- **Create** `packages/core/tests/test_proposer.py` — unit tests (stub + monkeypatched modal), mirroring `test_oracle_backend.py`.

Out of scope (later slices): prompt construction, RDKit validation, `RunCost` population, the Proposer abstraction / `mutation_strategy` wiring, GPU self-hosting.

---

## Task 1: `proposer.py` foundations — types, config, SMILES cleaning

**Files:**
- Create: `packages/core/capychem/proposer.py`
- Test: `packages/core/tests/test_proposer.py`

- [ ] **Step 1: Write the failing test**

```python
"""Env-selected proposer backend + cost mapping (milestone-02 slice 03)."""

from __future__ import annotations

import pytest
from capychem import proposer
from capychem.proposer import (
    ProposalResult,
    ProposerError,
    _clean_smiles,
    propose_batch_async,
)


def test_clean_smiles_strips_fences_and_prose():
    assert _clean_smiles("```\nCCO\n```") == "CCO"
    assert _clean_smiles("  c1ccccc1  ") == "c1ccccc1"
    assert _clean_smiles("CCO and more text") == "CCO"
    assert _clean_smiles("```smiles\nCC(=O)O\n```") == "CC(=O)O"
    assert _clean_smiles("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_proposer.py::test_clean_smiles_strips_fences_and_prose -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capychem.proposer'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/core/capychem/proposer.py`:

```python
"""DeepSeek-v4-pro proposer adapter (milestone-02 slice 03).

Modern code calls the proposer through an env-selected backend, mirroring
``capychem.oracle``. The ``stub`` backend is deterministic and network-free (CI
+ slice-04 development); the ``modal`` backend awaits the Modal ``propose``
worker, which wraps DeepSeek's OpenAI-compatible API. Cost policy lives here:
the worker returns token counts, this module maps tokens -> USD via env
placeholder rates (NOT a price guarantee; PRD N6).

This module returns the model's *cleaned proposed string* — it does NOT
RDKit-validate. Validation stays in the loop's ``validate`` node (slice 04).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any


class ProposerError(RuntimeError):
    """Raised when the proposer backend fails or returns a malformed response."""


@dataclass(frozen=True)
class ProposalResult:
    """One LLM proposal. ``smiles`` is the model's cleaned proposed string — a
    candidate, NOT a validated molecule (the loop's ``validate`` node checks)."""

    raw: str
    smiles: str
    tokens_in: int
    tokens_out: int
    cost_usd: float = 0.0


# --- config (env, mirrors CAPYCHEM_ORACLE_*) -------------------------------

# Placeholder per-1k-token rates; configure via env. NOT a price guarantee (N6).
_DEFAULT_USD_PER_1K_IN = 0.00014
_DEFAULT_USD_PER_1K_OUT = 0.00028
_DEFAULT_MODEL = "deepseek-v4-pro"
_MODAL_APP = "capychem-worker"
_MODAL_FN = "propose"


def _proposer_backend() -> str:
    return os.environ.get("CAPYCHEM_PROPOSER_BACKEND", "stub")


def llm_usd_per_1k_in() -> float:
    return float(os.environ.get("CAPYCHEM_LLM_USD_PER_1K_IN", _DEFAULT_USD_PER_1K_IN))


def llm_usd_per_1k_out() -> float:
    return float(os.environ.get("CAPYCHEM_LLM_USD_PER_1K_OUT", _DEFAULT_USD_PER_1K_OUT))


def llm_model() -> str:
    return os.environ.get("CAPYCHEM_LLM_MODEL", _DEFAULT_MODEL)


def _clean_smiles(raw: str) -> str:
    """Best-effort: strip code fences/whitespace, return the first token.

    SMILES contain no whitespace, so the first whitespace-delimited token of the
    de-fenced text is the candidate. Does NOT check chemical validity — that is
    the loop's ``validate`` node.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = " ".join(
            ln for ln in text.splitlines() if not ln.strip().startswith("```")
        ).strip()
    tokens = text.split()
    return tokens[0] if tokens else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_proposer.py::test_clean_smiles_strips_fences_and_prose -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/proposer.py packages/core/tests/test_proposer.py
git commit -m "feat(proposer): ProposalResult + config + SMILES cleaning"
```

---

## Task 2: stub backend + `propose_batch_async` dispatch

**Files:**
- Modify: `packages/core/capychem/proposer.py`
- Test: `packages/core/tests/test_proposer.py`

> Note: `propose_batch_async` references `_modal_propose` (added in Task 3). Python resolves that name only when the `modal` branch runs, so the module imports and the stub/unknown tests pass before Task 3 exists.

- [ ] **Step 1: Write the failing tests**

Append to `packages/core/tests/test_proposer.py`:

```python
async def test_stub_is_deterministic_and_free(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    a = await propose_batch_async("make a molecule", 5, seed=42)
    b = await propose_batch_async("make a molecule", 5, seed=42)
    assert [r.smiles for r in a] == [r.smiles for r in b]  # deterministic by seed
    assert len(a) == 5
    assert all(r.cost_usd == 0.0 for r in a)  # stub is free
    assert all(isinstance(r, ProposalResult) for r in a)


async def test_stub_seed_changes_output(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "stub")
    a = await propose_batch_async("p", 8, seed=1)
    b = await propose_batch_async("p", 8, seed=2)
    assert [r.smiles for r in a] != [r.smiles for r in b]


async def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "bogus")
    with pytest.raises(ValueError, match="CAPYCHEM_PROPOSER_BACKEND"):
        await propose_batch_async("p", 1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest packages/core/tests/test_proposer.py -v -k "stub or unknown_backend"`
Expected: FAIL — `AttributeError`/`ImportError` (`propose_batch_async` references undefined names) or `cannot import name`. (Import of `propose_batch_async` already exists at top of file from Task 1 edits; the function itself is undefined → `ImportError`.)

- [ ] **Step 3: Write minimal implementation**

Append to `packages/core/capychem/proposer.py`:

```python
# --- stub backend (deterministic, network-free) ----------------------------

_STUB_POOL = (
    "CCO", "c1ccccc1", "CC(=O)O", "CCN", "C1CCCCC1",
    "CCOC(=O)C", "c1ccncc1", "CC(C)O", "CCCCO", "c1ccc(O)cc1",
)


def _stub_propose(
    prompt: str, n: int, *, temperature: float, seed: int
) -> list[ProposalResult]:
    """Deterministic proposer for CI + slice-04 development. Same (prompt, seed,
    index) -> same SMILES from a fixed pool; cost is zero."""
    results: list[ProposalResult] = []
    for i in range(n):
        digest = hashlib.sha256(f"{seed}:{prompt}:{i}".encode()).digest()
        smi = _STUB_POOL[int.from_bytes(digest[:4], "big") % len(_STUB_POOL)]
        results.append(
            ProposalResult(raw=smi, smiles=smi, tokens_in=0, tokens_out=0, cost_usd=0.0)
        )
    return results


# --- public API -------------------------------------------------------------

async def propose_batch_async(
    prompt: str, n: int, *, temperature: float = 0.7, seed: int = 0
) -> list[ProposalResult]:
    """Propose ``n`` candidate SMILES via the configured backend.

    ``stub`` (default) is deterministic and network-free; ``modal`` awaits the
    DeepSeek-backed worker and maps token usage to USD. Returns cleaned proposed
    strings — NOT validated molecules (the loop validates).
    """
    backend = _proposer_backend()
    if backend == "stub":
        return _stub_propose(prompt, n, temperature=temperature, seed=seed)
    if backend == "modal":
        return await _modal_propose(prompt, n, temperature=temperature, seed=seed)
    raise ValueError(
        f"Set CAPYCHEM_PROPOSER_BACKEND to 'stub' or 'modal' (got {backend!r})"
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest packages/core/tests/test_proposer.py -v -k "stub or unknown_backend"`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/proposer.py packages/core/tests/test_proposer.py
git commit -m "feat(proposer): deterministic stub backend + dispatch"
```

---

## Task 3: modal backend — token→USD cost + malformed handling

**Files:**
- Modify: `packages/core/capychem/proposer.py`
- Test: `packages/core/tests/test_proposer.py`

- [ ] **Step 1: Write the failing tests**

Append to `packages/core/tests/test_proposer.py`:

```python
async def test_modal_backend_maps_tokens_to_cost(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "modal")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_IN", "0.001")
    monkeypatch.setenv("CAPYCHEM_LLM_USD_PER_1K_OUT", "0.002")

    class FakeRemote:
        async def aio(self, *, prompt, n, temperature, seed, model):
            return [
                {"raw": "```\nCCO\n```", "tokens_in": 1000, "tokens_out": 500}
                for _ in range(n)
            ]

    class FakeFn:
        remote = FakeRemote()

    monkeypatch.setattr(proposer, "_modal_propose_fn", lambda: FakeFn())
    out = await propose_batch_async("prompt", 2, temperature=0.0, seed=7)
    assert len(out) == 2
    assert out[0].smiles == "CCO"  # cleaned from the code fence
    assert out[0].raw == "```\nCCO\n```"
    # 1000/1000*0.001 + 500/1000*0.002 = 0.001 + 0.001 = 0.002
    assert out[0].cost_usd == pytest.approx(0.002)


async def test_modal_malformed_row_raises(monkeypatch):
    monkeypatch.setenv("CAPYCHEM_PROPOSER_BACKEND", "modal")

    class FakeRemote:
        async def aio(self, **kwargs):
            return [{"raw": "CCO"}]  # missing tokens_in/tokens_out

    class FakeFn:
        remote = FakeRemote()

    monkeypatch.setattr(proposer, "_modal_propose_fn", lambda: FakeFn())
    with pytest.raises(ProposerError, match="malformed"):
        await propose_batch_async("p", 1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest packages/core/tests/test_proposer.py -v -k "modal"`
Expected: FAIL — `AttributeError: module 'capychem.proposer' has no attribute '_modal_propose_fn'`

- [ ] **Step 3: Write minimal implementation**

Append to `packages/core/capychem/proposer.py`:

```python
# --- modal backend (DeepSeek via the worker) --------------------------------

def _modal_propose_fn() -> Any:
    """Look up the deployed Modal worker ``propose`` function. Imported lazily so
    the ``stub`` backend (CI) never needs or imports ``modal``."""
    import modal

    return modal.Function.from_name(_MODAL_APP, _MODAL_FN)


async def _modal_propose(
    prompt: str, n: int, *, temperature: float, seed: int
) -> list[ProposalResult]:
    in_rate = llm_usd_per_1k_in()
    out_rate = llm_usd_per_1k_out()
    rows = await _modal_propose_fn().remote.aio(
        prompt=prompt, n=n, temperature=temperature, seed=seed, model=llm_model()
    )
    try:
        return [
            ProposalResult(
                raw=row["raw"],
                smiles=_clean_smiles(row["raw"]),
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                cost_usd=(row["tokens_in"] / 1000.0) * in_rate
                + (row["tokens_out"] / 1000.0) * out_rate,
            )
            for row in rows
        ]
    except (KeyError, TypeError) as exc:
        raise ProposerError(
            f"Modal proposer returned a malformed row ({exc}): {repr(rows)[:500]}"
        ) from exc
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest packages/core/tests/test_proposer.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add packages/core/capychem/proposer.py packages/core/tests/test_proposer.py
git commit -m "feat(proposer): modal backend with token-based cost"
```

---

## Task 4: Modal `propose()` worker function

**Files:**
- Modify: `apps/worker/app.py` (add after the `score` function, before `smoke`)

No unit test — this function needs the real API + a secret; it is exercised by the manual smoke (Task 6). This task adds the code and confirms it parses/lints under modern Python.

- [ ] **Step 1: Add the lightweight LLM image** (after the existing `image = (...)` block, before `app = modal.App(...)`)

```python
# Lightweight image for the LLM proposer (NOT the harness env). Modern Python +
# a single HTTP client; the DeepSeek API key arrives via a Modal secret.
llm_image = modal.Image.debian_slim(python_version="3.12").pip_install("requests==2.34.2")
```

- [ ] **Step 2: Add the `propose` function** (after `score`, before `smoke`)

```python
@app.function(
    image=llm_image,
    timeout=300,
    secrets=[modal.Secret.from_name("deepseek-api-key")],
)
def propose(prompt: str, n: int, temperature: float, seed: int, model: str) -> list[dict]:
    """Propose n candidate completions via DeepSeek's OpenAI-compatible API.

    Returns [{raw, tokens_in, tokens_out}] — raw completion text + per-choice
    token usage. SMILES cleaning and USD cost are computed modern-side in
    capychem.proposer. The DEEPSEEK_API_KEY env var is injected by the Modal
    secret; never hard-code or commit it."""
    import os

    import requests

    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "seed": seed,
            "n": n,
        },
        timeout=240,
    )
    resp.raise_for_status()
    body = resp.json()
    choices = body["choices"]
    usage = body.get("usage", {})
    # Usage is reported per request; attribute evenly across the n choices.
    per_in = usage.get("prompt_tokens", 0) // max(len(choices), 1)
    per_out = usage.get("completion_tokens", 0) // max(len(choices), 1)
    return [
        {
            "raw": choice["message"]["content"],
            "tokens_in": per_in,
            "tokens_out": per_out,
        }
        for choice in choices
    ]
```

- [ ] **Step 3: Add the smoke entrypoint** (after the existing `smoke` entrypoint)

```python
@app.local_entrypoint()
def propose_smoke() -> None:
    """`modal run apps/worker/app.py::propose_smoke` — one real DeepSeek call."""
    rows = propose.remote(
        prompt="Propose one drug-like molecule. Output only its SMILES string.",
        n=2,
        temperature=0.7,
        seed=0,
        model="deepseek-v4-pro",
    )
    print(rows)
    assert len(rows) == 2 and all("raw" in r and "tokens_in" in r for r in rows)
```

- [ ] **Step 4: Verify it parses and lints under modern Python**

Run: `uv run python -m py_compile apps/worker/app.py && uv run ruff check apps/worker/app.py`
Expected: no output / "All checks passed!" (the body imports `requests` lazily, so module parse needs no `requests` install)

- [ ] **Step 5: Commit**

```bash
git add apps/worker/app.py
git commit -m "feat(worker): add DeepSeek-backed propose() Modal function"
```

---

## Task 5: Full quality gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python gate**

```bash
uv run pytest packages/core/tests/test_proposer.py -v
uv run mypy -p capychem -p capychem.api
uv run ruff check .
uv run ruff format --check .
```
Expected: pytest all PASS; mypy clean; ruff clean; format clean. If `ruff format --check` reports a file, run `uv run ruff format .` and re-commit.

- [ ] **Step 2: Run the whole suite to confirm no regressions**

Run: `uv run pytest`
Expected: all prior tests still PASS (proposer additions are net-new; nothing else changed).

- [ ] **Step 3: Commit any formatting fixups**

```bash
git add -A && git commit -m "style(proposer): formatting" || echo "nothing to format"
```

---

## Task 6: One-time manual real-API smoke (retires the integration risk)

**Files:** none (manual verification; requires a DeepSeek API key + Modal access)

This is the slice's "done bar." It is manual and network-dependent — not part of CI.

- [ ] **Step 1: Create the Modal secret** (key value supplied by the operator; never committed)

```bash
modal secret create deepseek-api-key DEEPSEEK_API_KEY=<your-deepseek-key>
```

- [ ] **Step 2: Run the real smoke**

Run: `modal run apps/worker/app.py::propose_smoke`
Expected: prints 2 rows, each with a non-empty `raw` string and integer `tokens_in`/`tokens_out`. (If the real API rejects `n` or `seed`, note it and adjust the worker payload — surfaced here on purpose.)

- [ ] **Step 3: Confirm the adapter end-to-end against Modal** (optional, after `modal deploy apps/worker/app.py`)

```bash
CAPYCHEM_PROPOSER_BACKEND=modal uv run python -c "
import asyncio
from capychem.proposer import propose_batch_async
out = asyncio.run(propose_batch_async('Propose one drug-like SMILES. Output only the SMILES.', 2, temperature=0.7, seed=0))
print([(r.smiles, r.tokens_in, r.tokens_out, r.cost_usd) for r in out])
"
```
Expected: 2 `ProposalResult`s with cleaned `smiles`, token counts, and a small positive `cost_usd`.

---

## Self-Review

**1. Spec coverage** (against `2026-06-17-modal-llm-propose-endpoint-design.md`):
- Modal `propose()` beside `score()` on its own image, key via secret → Task 4. ✓
- New `proposer.py` adapter, `ProposalResult`, env-selected `stub`/`modal` → Tasks 1–3. ✓
- Env keys `CAPYCHEM_PROPOSER_BACKEND` / `_LLM_USD_PER_1K_IN`/`_OUT` / `_LLM_MODEL` → Task 1 config + Task 3 cost. ✓
- Cleaned proposed string, NOT validated; `temperature`/`seed` first-class → Task 1 `_clean_smiles`, Task 2/3 signatures. ✓
- Typed `ProposerError`; unknown-backend `ValueError`; malformed-row handling → Tasks 1–3. ✓
- Stub determinism, monkeypatched modal cost-from-tokens + malformed, extraction, selector tests → Tasks 1–3. ✓
- One-time manual real-API smoke → Task 6. ✓
- Out-of-scope items (prompt construction, validation, RunCost, abstraction, GPU) → touched by no task. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every command has expected output. ✓

**3. Type consistency:** `ProposalResult(raw, smiles, tokens_in, tokens_out, cost_usd)` used identically in stub (Task 2) and modal (Task 3); `propose_batch_async(prompt, n, *, temperature, seed)` signature matches across dispatch, stub, and modal; the modal worker returns `{raw, tokens_in, tokens_out}` consumed exactly by `_modal_propose`. ✓
