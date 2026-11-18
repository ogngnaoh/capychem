"""Grounded intent resolution: free-text objective -> a PMO task, or a guardrail
refusal (FR-015). The default and fully-tested path is a deterministic
keyword/alias/fuzzy matcher over ``capychem.api.catalog`` — no LLM, no network
required. An LLM seam (the ``Resolver`` protocol + ``get_resolver``) exists for a
future LLM-backed matcher, selected only when ``CAPYCHEM_INTENT_BACKEND=llm`` AND
``DEEPSEEK_API_KEY`` are both set; that backend is unimplemented in this slice, so
resolution always falls back to the deterministic matcher — grounding to the
23-task catalog is never bypassed, and no LLM call is ever required for this path.
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from capychem.api.catalog import TASKS, TaskInfo
from capychem.api.schemas import IntentResolution, RefusalOut, ResolvedPlan
from rdkit import Chem, RDLogger

# Silence per-molecule parse warnings; invalidity is signalled by a None mol
# (mirrors packages/core/capychem/validate.py's convention).
RDLogger.DisableLog("rdApp.*")

Confidence = Literal["high", "medium", "low"]

_HIGH_THRESHOLD = 0.82
_MEDIUM_THRESHOLD = 0.55

_DEFAULT_BUDGET = 10_000  # standard benchmark oracle-call budget
_DEFAULT_PLATEAU_WINDOW = 5  # matches CreateRunRequest's default
_DEFAULT_MUTATION_STRATEGY = "graph_ga"  # matches CreateRunRequest's default
_MAX_BUDGET = 200_000  # generous ceiling above the 10k PMO convention (FR-015)


@dataclass(frozen=True)
class MatchResult:
    task: str | None
    confidence: Confidence | None
    closest_task: str | None
    rationale: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


def _phrase_score(phrase: str, text: str) -> float:
    """1.0 for an exact word-boundary phrase hit; else a fuzzy character ratio
    in [0, 1) (``difflib.SequenceMatcher``)."""
    if re.search(rf"\b{re.escape(phrase)}\b", text):
        return 1.0
    return difflib.SequenceMatcher(None, phrase, text).ratio()


def _best_match(text: str) -> tuple[TaskInfo, float]:
    norm = _normalize(text)
    best_task, best_score = TASKS[0], -1.0
    for t in TASKS:
        phrases = (t.name.replace("_", " "), *t.aliases)
        # Normalize each phrase the same way as the input text (e.g. "drug-likeness"
        # -> "drug likeness"), or a hyphen/punctuation mismatch would silently sink
        # an exact word-boundary hit to a low fuzzy-ratio score.
        score = max(_phrase_score(_normalize(p), norm) for p in phrases)
        if score > best_score:
            best_task, best_score = t, score
    return best_task, best_score


class Resolver(Protocol):
    def resolve(self, text: str) -> MatchResult: ...


class DeterministicResolver:
    """Keyword/alias exact match (score 1.0) or a fuzzy character ratio over the
    catalog. No LLM, no network -- the default, fully-tested path."""

    def resolve(self, text: str) -> MatchResult:
        task, score = _best_match(text)
        if score >= _HIGH_THRESHOLD:
            return MatchResult(
                task=task.name,
                confidence="high",
                closest_task=None,
                rationale=f'Matched "{text.strip()}" to {task.name} ({task.description}).',
            )
        if score >= _MEDIUM_THRESHOLD:
            return MatchResult(
                task=task.name,
                confidence="medium",
                closest_task=None,
                rationale=(
                    f'Matched "{text.strip()}" to {task.name} ({task.description}), '
                    "moderate confidence."
                ),
            )
        return MatchResult(
            task=None,
            confidence="low",
            closest_task=task.name,
            rationale=f'No benchmark exists for "{text.strip()}"; the closest is {task.name}.',
        )


def _llm_configured() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY")) and (
        os.environ.get("CAPYCHEM_INTENT_BACKEND") == "llm"
    )


def get_resolver() -> Resolver:
    """LLM seam: an LLM-backed resolver would be selected here when
    ``CAPYCHEM_INTENT_BACKEND=llm`` and ``DEEPSEEK_API_KEY`` are both set. Not
    implemented in this slice — grounding an LLM path to *only* the 23 PMO tasks
    needs its own validation story, so resolution always uses the deterministic
    matcher for now, even when ``_llm_configured()`` is true."""
    if _llm_configured():
        pass  # seam for a future LLM-backed Resolver; unimplemented in this slice
    return DeterministicResolver()


def resolve_intent(
    text: str, *, budget: int | None = None, seed_smiles: str | None = None
) -> IntentResolution:
    """Resolve free-text ``text`` to a PMO task (FR-015 guardrails).

    Grounded to the 23-task catalog only: a match always names one of
    ``capychem.eval.tasks.PMO_TASKS``, never an invented oracle. ``resolved_plan``
    is null whenever there is a blocking refusal (invalid seed SMILES, an
    out-of-range budget) or no confident task match.
    """
    refusals: list[RefusalOut] = []
    stripped = text.strip()
    if not stripped:
        refusals.append(
            RefusalOut(
                field="objective",
                reason=(
                    "Objective text is empty; describe what you want the molecule "
                    'to do (e.g. "drug-like and easy to synthesize").'
                ),
            )
        )

    match = get_resolver().resolve(stripped) if stripped else None

    if seed_smiles is not None and seed_smiles.strip():
        if Chem.MolFromSmiles(seed_smiles) is None:
            refusals.append(
                RefusalOut(
                    field="seed_smiles",
                    reason=(
                        f"'{seed_smiles}' is not a valid SMILES string; RDKit could not parse it."
                    ),
                )
            )

    if budget is not None and budget <= 0:
        refusals.append(
            RefusalOut(field="budget", reason="Oracle-call budget must be a positive integer.")
        )
    elif budget is not None and budget > _MAX_BUDGET:
        refusals.append(
            RefusalOut(
                field="budget",
                reason=f"Oracle-call budget of {budget} exceeds the {_MAX_BUDGET}-call ceiling.",
            )
        )

    matched_task = match.task if match else None
    confidence = match.confidence if match else None
    closest_task = match.closest_task if match else None
    rationale = (
        match.rationale
        if match
        else "Objective text is empty; describe what you want the molecule to do."
    )

    blocking = bool(refusals) or matched_task is None
    resolved_plan = None
    if not blocking:
        assert matched_task is not None  # blocking is False only when a task matched
        resolved_plan = ResolvedPlan(
            task=matched_task,
            budget=budget if budget is not None else _DEFAULT_BUDGET,
            plateau_window=_DEFAULT_PLATEAU_WINDOW,
            mutation_strategy=_DEFAULT_MUTATION_STRATEGY,
            seed_smiles=seed_smiles if seed_smiles and seed_smiles.strip() else None,
        )

    return IntentResolution(
        matched_task=matched_task,
        confidence=confidence,
        closest_task=closest_task,
        rationale=rationale,
        resolved_plan=resolved_plan,
        refusals=refusals,
        cost_usd=0.0,
    )
