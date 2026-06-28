"""DeepSeek-v4-pro proposer adapter (milestone-02 slice 03).

Modern code calls the proposer through an env-selected backend, mirroring
``capychem.oracle``. The ``stub`` backend is deterministic and network-free (CI
+ later-slice development); the ``modal`` backend awaits the Modal ``propose``
worker, which wraps DeepSeek's OpenAI-compatible API; the ``direct`` backend
calls DeepSeek's OpenAI-compatible chat-completions API straight from the modern
process via httpx (no Modal). Cost policy lives here: the worker / API returns
token counts, this module maps tokens -> USD via env placeholder rates (NOT a
price guarantee; PRD N6).

This module returns the model's *cleaned proposed string* — it does NOT
RDKit-validate. Validation stays in the loop's ``validate`` node (a later slice).
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


# Placeholder per-1k-token rates; configure via env. NOT a price guarantee (N6).
# These correspond to _DEFAULT_MODEL (deepseek-v4-pro: $0.435/$0.87 per M tokens).
# Keep aligned with the model — V4-Flash rates (0.00014/0.00028) understate v4-pro
# spend ~3.1x and silently corrupt RunCost.
_DEFAULT_USD_PER_1K_IN = 0.000435
_DEFAULT_USD_PER_1K_OUT = 0.00087
_DEFAULT_MODEL = "deepseek-v4-pro"
# Hard cap on output tokens per request. A SMILES is short, so this leaves ample
# headroom while bounding a reasoning-mode tail (which would otherwise balloon cost).
_MAX_OUTPUT_TOKENS = 128
_MODAL_APP = "capychem-worker"
_MODAL_FN = "propose"
_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


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
        text = " ".join(ln for ln in text.splitlines() if not ln.strip().startswith("```")).strip()
    tokens = text.split()
    return tokens[0] if tokens else ""


# --- stub backend (deterministic, network-free) ----------------------------

_STUB_POOL = (
    "CCO",
    "c1ccccc1",
    "CC(=O)O",
    "CCN",
    "C1CCCCC1",
    "CCOC(=O)C",
    "c1ccncc1",
    "CC(C)O",
    "CCCCO",
    "c1ccc(O)cc1",
)


def _stub_propose(prompt: str, n: int, *, temperature: float, seed: int) -> list[ProposalResult]:
    """Deterministic proposer for CI + later-slice development. Same (prompt,
    seed, index) -> same SMILES from a fixed pool; cost is zero."""
    results: list[ProposalResult] = []
    for i in range(n):
        digest = hashlib.sha256(f"{seed}:{prompt}:{i}".encode()).digest()
        smi = _STUB_POOL[int.from_bytes(digest[:4], "big") % len(_STUB_POOL)]
        results.append(ProposalResult(raw=smi, smiles=smi, tokens_in=0, tokens_out=0, cost_usd=0.0))
    return results


# --- shared row → result mapping -------------------------------------------


def _rows_to_results(rows: Any) -> list[ProposalResult]:
    """Map a list of ``{raw, tokens_in, tokens_out}`` dicts to ProposalResult.

    Shared by both the ``modal`` and ``direct`` backends so cost maths and
    cleaning stay in one place.
    """
    in_rate = llm_usd_per_1k_in()
    out_rate = llm_usd_per_1k_out()
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
            f"Proposer returned a malformed row ({exc}): {repr(rows)[:500]}"
        ) from exc


# --- public API -------------------------------------------------------------


async def propose_batch_async(
    prompt: str, n: int, *, temperature: float = 0.7, seed: int = 0
) -> list[ProposalResult]:
    """Propose ``n`` candidate SMILES via the configured backend.

    ``stub`` (default) is deterministic and network-free; ``modal`` awaits the
    DeepSeek-backed worker; ``direct`` calls DeepSeek's API from the local
    process. Returns cleaned proposed strings — NOT validated molecules (the
    loop validates).
    """
    backend = _proposer_backend()
    if backend == "stub":
        return _stub_propose(prompt, n, temperature=temperature, seed=seed)
    if backend == "modal":
        return await _modal_propose(prompt, n, temperature=temperature, seed=seed)
    if backend == "direct":
        return await _direct_propose(prompt, n, temperature=temperature, seed=seed)
    raise ValueError(
        f"Set CAPYCHEM_PROPOSER_BACKEND to 'stub', 'modal', or 'direct' (got {backend!r})"
    )


# --- modal backend (DeepSeek via the worker) --------------------------------


def _modal_propose_fn() -> Any:
    """Look up the deployed Modal worker ``propose`` function. Imported lazily so
    the ``stub`` backend (CI) never needs or imports ``modal``."""
    import modal

    return modal.Function.from_name(_MODAL_APP, _MODAL_FN)


async def _modal_propose(
    prompt: str, n: int, *, temperature: float, seed: int
) -> list[ProposalResult]:
    rows = await _modal_propose_fn().remote.aio(
        prompt=prompt, n=n, temperature=temperature, seed=seed, model=llm_model()
    )
    return _rows_to_results(rows)


# --- direct backend (DeepSeek API, no Modal) --------------------------------


def _deepseek_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ProposerError("Set DEEPSEEK_API_KEY to use the 'direct' proposer backend")
    return key


async def _post_deepseek(payload: dict[str, Any], *, api_key: str) -> Any:
    """Raw POST to DeepSeek's chat-completions API, returning the httpx Response.
    Patchable seam: tests monkeypatch this to avoid network."""
    import httpx

    async with httpx.AsyncClient(timeout=240.0) as client:
        return await client.post(
            _DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )


async def _deepseek_chat(payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    """POST to DeepSeek and return the parsed JSON body, mapping HTTP errors and
    non-JSON bodies to a clean ProposerError that surfaces the response text (so a
    400 'Invalid n value' is legible, not a raw httpx traceback)."""
    resp = await _post_deepseek(payload, api_key=api_key)
    if resp.status_code >= 400:
        raise ProposerError(f"DeepSeek API error {resp.status_code}: {resp.text[:500]}")
    try:
        body: dict[str, Any] = resp.json()
    except ValueError as exc:
        raise ProposerError(f"DeepSeek returned a non-JSON body: {resp.text[:500]}") from exc
    return body


async def _one_proposal_row(
    prompt: str, *, temperature: float, seed: int, api_key: str
) -> dict[str, Any]:
    """One DeepSeek request (the API caps n=1). Returns a {raw, tokens_in,
    tokens_out} row carrying this request's own token usage."""
    payload = {
        "model": llm_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "seed": seed,
        "max_tokens": _MAX_OUTPUT_TOKENS,
        # deepseek-v4 models reason by default — they leave message.content empty
        # until the chain-of-thought finishes (~800 tok) and bill it all as output.
        # We want a short SMILES in content, so force non-reasoning (chat) mode.
        "thinking": {"type": "disabled"},
    }
    body = await _deepseek_chat(payload, api_key=api_key)
    try:
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProposerError(
            f"DeepSeek response missing choices/content: {repr(body)[:500]}"
        ) from exc
    usage = body.get("usage", {})
    return {
        "raw": raw,
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
    }


async def _direct_propose(
    prompt: str, n: int, *, temperature: float, seed: int
) -> list[ProposalResult]:
    """Call DeepSeek directly (no Modal). DeepSeek allows only n=1 per request, so
    fan out n single-choice requests concurrently, each with a per-index seed
    (seed+i) for distinct-yet-deterministic samples. Each request reports its own
    token usage; rows flow through _rows_to_results for cleaning + cost."""
    import asyncio

    api_key = _deepseek_api_key()
    rows = await asyncio.gather(
        *(
            _one_proposal_row(prompt, temperature=temperature, seed=seed + i, api_key=api_key)
            for i in range(n)
        )
    )
    return _rows_to_results(list(rows))
