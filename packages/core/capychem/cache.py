"""Persistent, cross-run oracle-score cache (milestone 08 slice 04).

Keyed on ``(oracle_key, objective_key, canonical_smiles) -> (score, wall_ms)``.
Consulted BEFORE spending the run's oracle-call budget: a hit means some run
(possibly this one, possibly an earlier one) already scored the exact same molecule
under the exact same oracle version + objective, so the real compute is skippable.

Exploratory-mode-only (the ``capychem.mode`` wall): the score node
(``capychem.loop.graph``) never consults or writes this table on the benchmark path,
so the committed G1 PMO numbers and the eval harness
(``packages/core/capychem/eval/runner.py``) are byte-identical whether this table
exists or not.

``oracle_key`` folds in the harness's live PyTDC pin (``capychem.oracle.pytdc_version``)
so an oracle-version bump invalidates every stale entry for free -- old rows simply
never match the new key again, no migration/backfill needed.
"""

from __future__ import annotations

from typing import Any

from capychem.db.models import OracleScoreCache
from capychem.objective import stable_hash
from capychem.oracle import pytdc_version
from capychem.validate import canonicalize
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_ORACLE_NAME = "pytdc"


def oracle_key() -> str:
    """The oracle-identity half of the cache key: name + live PyTDC pin.

    ``pytdc_version()`` is best-effort (None if the harness is unreachable);
    "unknown" keeps the cache functional -- if pessimistically shared across any
    unversioned deploys -- rather than disabling it when provenance is unavailable.
    """
    return f"{_ORACLE_NAME}:{pytdc_version() or 'unknown'}"


def objective_key(*, task: str, objective_json: dict[str, Any] | None) -> str:
    """The scoring-target half of the cache key: the plain benchmark task name, or a
    stable hash of a composed objective spec (07-04)."""
    if objective_json is None:
        return task
    return stable_hash(objective_json)


async def lookup_many(
    session: AsyncSession, oracle_key_: str, objective_key_: str, smiles: list[str]
) -> dict[str, tuple[float, int]]:
    """Batch cache lookup, keyed by ORIGINAL (not necessarily canonical) SMILES.

    Each input is canonicalized before the query, so two distinct SMILES strings for
    the same molecule both resolve to the one shared cache entry. Returns
    ``{original_smiles: (score, wall_ms)}`` for hits only; a missing/unparseable
    input is simply absent from the result (a miss).
    """
    canon_by_input: dict[str, str] = {}
    for s in smiles:
        canon = canonicalize(s)
        if canon is not None:
            canon_by_input[s] = canon
    if not canon_by_input:
        return {}
    rows = (
        await session.execute(
            select(
                OracleScoreCache.canonical_smiles,
                OracleScoreCache.score,
                OracleScoreCache.wall_ms,
            ).where(
                OracleScoreCache.oracle_key == oracle_key_,
                OracleScoreCache.objective_key == objective_key_,
                OracleScoreCache.canonical_smiles.in_(set(canon_by_input.values())),
            )
        )
    ).all()
    by_canon = {canon: (score, wall_ms) for canon, score, wall_ms in rows}
    return {
        orig: by_canon[canon] for orig, canon in canon_by_input.items() if canon in by_canon
    }


async def record_many(
    session: AsyncSession,
    oracle_key_: str,
    objective_key_: str,
    entries: list[tuple[str, float, int]],
) -> None:
    """Best-effort cache write for freshly-computed ``(smiles, score, wall_ms)``
    results (``smiles`` need not be pre-canonicalized). A duplicate-key race (two
    runs discovering the same new molecule at the same time) is harmless -- first
    writer wins; the loser's ``IntegrityError`` is swallowed row by row so the rest
    of the batch still lands.
    """
    canon_entries = [
        (canon, score, wall_ms)
        for smi, score, wall_ms in entries
        if (canon := canonicalize(smi)) is not None
    ]
    if not canon_entries:
        return
    session.add_all(
        OracleScoreCache(
            oracle_key=oracle_key_, objective_key=objective_key_,
            canonical_smiles=canon, score=score, wall_ms=wall_ms,
        )
        for canon, score, wall_ms in canon_entries
    )
    try:
        await session.commit()
        return
    except IntegrityError:
        await session.rollback()
    for canon, score, wall_ms in canon_entries:
        session.add(
            OracleScoreCache(
                oracle_key=oracle_key_, objective_key=objective_key_,
                canonical_smiles=canon, score=score, wall_ms=wall_ms,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
