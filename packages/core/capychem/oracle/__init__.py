"""Subprocess bridge to the isolated legacy harness (PyTDC oracles).

Modern code (Python 3.12) NEVER imports the harness. It shells out to the harness
venv's interpreter, passing a typed JSON request on stdin and reading a typed JSON
response on stdout. The harness side is ``harness/capychem_harness/score.py``,
running under Python 3.10 + PyTDC 0.3.6.

This module is the only sanctioned crossing of the harness↔modern boundary.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# packages/core/capychem/oracle/__init__.py -> repo root is parents[4].
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_HARNESS_PYTHON = _REPO_ROOT / "harness" / ".venv" / "bin" / "python"
_SCORER = _REPO_ROOT / "harness" / "capychem_harness" / "score.py"
_PROPOSER = _REPO_ROOT / "harness" / "capychem_harness" / "propose.py"


class HarnessError(RuntimeError):
    """Raised when the harness subprocess fails or returns an error payload."""


@dataclass(frozen=True)
class OracleResult:
    """One scored candidate. ``score`` is ``None`` when the SMILES is invalid."""

    smiles: str
    score: float | None
    valid: bool
    wall_ms: int
    cost_usd: float = 0.0  # 0 for local; modal backend fills from wall_ms × rate


@dataclass(frozen=True)
class Offspring:
    """One Graph-GA offspring with the indices of its two crossover parents.

    ``parents`` indexes into the population list passed to ``propose_offspring``.
    """

    smiles: str
    parents: tuple[int, int]


def _harness_python() -> Path:
    override = os.environ.get("CAPYCHEM_HARNESS_PYTHON")
    return Path(override) if override else _DEFAULT_HARNESS_PYTHON


def _run_scorer(smiles: list[str], task: str, *, timeout_s: float = 120.0) -> dict[str, Any]:
    """Invoke the harness scorer subprocess and return its parsed JSON payload.

    Raises ``HarnessError`` if the harness env is missing, the subprocess fails, or
    the response is malformed / carries an error. Shared by ``score_smiles`` and
    ``pytdc_version`` so both cross the harness boundary the one sanctioned way.
    """
    python = _harness_python()
    if not python.exists():
        raise HarnessError(
            f"Build the harness env first (`uv sync` in harness/); "
            f"interpreter not found at {python}"
        )

    request = json.dumps({"task": task, "smiles": smiles})
    try:
        proc = subprocess.run(
            [str(python), str(_SCORER)],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"Harness scoring timed out after {timeout_s}s") from exc

    payload = _parse_last_json_line(proc.stdout)
    if payload is None:
        raise HarnessError(
            f"Harness returned no JSON (exit {proc.returncode}). stderr tail: {proc.stderr[-500:]}"
        )
    if payload.get("error"):
        raise HarnessError(str(payload["error"]))
    return payload


def score_smiles(smiles: list[str], task: str, *, timeout_s: float = 120.0) -> list[OracleResult]:
    """Score SMILES against a PyTDC oracle via the isolated harness subprocess.

    Raises ``HarnessError`` if the harness env is missing, the subprocess fails,
    or the response is malformed.
    """
    payload = _run_scorer(smiles, task, timeout_s=timeout_s)
    return [
        OracleResult(
            smiles=row["smiles"],
            score=row["score"],
            valid=row["valid"],
            wall_ms=row["wall_ms"],
        )
        for row in payload["results"]
    ]


@functools.lru_cache(maxsize=1)
def pytdc_version() -> str | None:
    """The harness's real PyTDC version (OD-5 provenance), via a fast analytic probe
    (qed needs no model download; empty SMILES so nothing is scored). The pin is
    constant per process, so the result is cached — at most one probe subprocess, and
    a short timeout so a run's finalize never blocks on it. Best-effort: returns None
    if the harness is unavailable, so a manifest degrades gracefully."""
    try:
        payload = _run_scorer([], "qed", timeout_s=15.0)
    except HarnessError:
        return None
    version = payload.get("pytdc_version")
    return version if isinstance(version, str) else None


def propose_offspring(
    population: list[tuple[str, float]],
    n_offspring: int,
    *,
    mutation_rate: float,
    seed: int,
    timeout_s: float = 120.0,
) -> list[Offspring]:
    """Run one Graph-GA reproduce step via the isolated harness subprocess.

    ``population`` is a list of (smiles, score) pairs. Returns offspring SMILES,
    each with the indices (into ``population``) of its two crossover parents. May
    return fewer than ``n_offspring`` (crossover can fail validity checks).
    Raises ``HarnessError`` if the harness env is missing, the subprocess fails,
    or the response is malformed.
    """
    python = _harness_python()
    if not python.exists():
        raise HarnessError(
            f"Build the harness env first (`uv sync` in harness/); "
            f"interpreter not found at {python}"
        )

    request = json.dumps(
        {
            "population": [{"smiles": s, "score": sc} for s, sc in population],
            "n_offspring": n_offspring,
            "mutation_rate": mutation_rate,
            "seed": seed,
        }
    )
    try:
        proc = subprocess.run(
            [str(python), str(_PROPOSER)],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"Harness proposal timed out after {timeout_s}s") from exc

    payload = _parse_last_json_line(proc.stdout)
    if payload is None:
        raise HarnessError(
            f"Harness returned no JSON (exit {proc.returncode}). stderr tail: {proc.stderr[-500:]}"
        )
    if payload.get("error"):
        raise HarnessError(str(payload["error"]))

    return [
        Offspring(smiles=row["smiles"], parents=(row["parents"][0], row["parents"][1]))
        for row in payload["offspring"]
    ]


def _parse_last_json_line(stdout: str) -> dict[str, Any] | None:
    """Return the last line of stdout that parses as a JSON object, else None.

    The harness writes its response as the final stdout line; library chatter is
    redirected to stderr, but this stays robust if any slips through.
    """
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# ---------------------------------------------------------------------------
# Backend-selected async scoring
# ---------------------------------------------------------------------------

_DEFAULT_ORACLE_USD_PER_SEC = 4e-5  # placeholder ~Modal CPU core-second; configure via env.
# NOT a price guarantee .
_MODAL_APP = "capychem-worker"
_MODAL_FN = "score"


def _oracle_backend() -> str:
    return os.environ.get("CAPYCHEM_ORACLE_BACKEND", "local")


def oracle_usd_per_sec() -> float:
    return float(os.environ.get("CAPYCHEM_ORACLE_USD_PER_SEC", _DEFAULT_ORACLE_USD_PER_SEC))


# --- bounded thread pool for blocking oracle calls (milestone 08 slice 05) --
#
# asyncio.to_thread runs on the loop's DEFAULT executor, which is an unbounded-
# by-default (but sizable, min(32, cpu_count+4)) thread pool shared with
# everything else on the loop. A burst of many concurrent runs, each scoring a
# batch (score_smiles shells out to the harness subprocess and blocks), could
# otherwise pile up an unobservable, untunable number of OS threads. This pool
# is explicit, sized, and shared by every blocking oracle call in this process
# — score_smiles here AND the descriptor-oracle path in capychem.objective —
# so a burst can never exceed CAPYCHEM_ORACLE_THREAD_POOL_SIZE concurrent
# blocking calls, regardless of how many runs are driving at once.

_DEFAULT_ORACLE_THREAD_POOL_SIZE = 8
_executor: ThreadPoolExecutor | None = None


def oracle_thread_pool_size() -> int:
    return int(
        os.environ.get("CAPYCHEM_ORACLE_THREAD_POOL_SIZE", str(_DEFAULT_ORACLE_THREAD_POOL_SIZE))
    )


def oracle_executor() -> ThreadPoolExecutor:
    """The process-wide bounded pool backing every blocking oracle call. Built
    once, lazily, on first use (sized from the env at that point)."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=oracle_thread_pool_size(), thread_name_prefix="capychem-oracle"
        )
    return _executor


def _modal_score_fn() -> Any:
    """Look up the deployed/serving Modal worker function. Imported lazily so the
    ``local`` backend (CI) never needs ``modal`` and never imports it at module load."""
    import modal

    return modal.Function.from_name(_MODAL_APP, _MODAL_FN)


async def score_batch_async(smiles: list[str], task: str) -> list[OracleResult]:
    """Score a batch via the configured backend. ``local`` wraps the harness
    subprocess in a thread (non-blocking); ``modal`` awaits the worker."""
    backend = _oracle_backend()
    if backend == "local":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(oracle_executor(), score_smiles, smiles, task)
    if backend == "modal":
        rate = oracle_usd_per_sec()
        rows = await _modal_score_fn().remote.aio(smiles, task)
        try:
            return [
                OracleResult(
                    smiles=row["smiles"],
                    score=row["score"],
                    valid=row["valid"],
                    wall_ms=row["wall_ms"],
                    cost_usd=(row["wall_ms"] / 1000.0) * rate,
                )
                for row in rows
            ]
        except (KeyError, TypeError) as exc:
            raise HarnessError(
                f"Modal worker returned a malformed row ({exc}): {repr(rows)[:500]}"
            ) from exc
    raise ValueError(f"Set CAPYCHEM_ORACLE_BACKEND to 'local' or 'modal' (got {backend!r})")
