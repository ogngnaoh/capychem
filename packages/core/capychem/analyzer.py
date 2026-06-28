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
