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
_DEFAULT_USD_PER_1K_IN = 0.00014
_DEFAULT_USD_PER_1K_OUT = 0.00028
_DEFAULT_MODEL = "deepseek-v4-pro"
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


async def _deepseek_chat(payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    """POST to DeepSeek's OpenAI-compatible API and return the parsed JSON body.
    Patchable seam: tests monkeypatch this to avoid network."""
    import httpx

    async with httpx.AsyncClient(timeout=240.0) as client:
        resp = await client.post(
            _DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


async def _direct_propose(
    prompt: str, n: int, *, temperature: float, seed: int
) -> list[ProposalResult]:
    """Call DeepSeek's API directly from the local process (no Modal). Key from
    the DEEPSEEK_API_KEY env var. Same {raw, tokens_in, tokens_out} row shape as
    the Modal worker, so cost + cleaning go through _rows_to_results."""
    api_key = _deepseek_api_key()
    payload = {
        "model": llm_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "seed": seed,
        "n": n,
    }
    body = await _deepseek_chat(payload, api_key=api_key)
    choices = body["choices"]
    usage = body.get("usage", {})
    # Usage is per request; attribute evenly across the n choices.
    per_in = usage.get("prompt_tokens", 0) // max(len(choices), 1)
    per_out = usage.get("completion_tokens", 0) // max(len(choices), 1)
    rows = [
        {"raw": c["message"]["content"], "tokens_in": per_in, "tokens_out": per_out}
        for c in choices
    ]
    return _rows_to_results(rows)
