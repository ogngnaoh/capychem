"""Subprocess bridge to the isolated legacy harness (PyTDC oracles).

Modern code (Python 3.12) NEVER imports the harness. It shells out to the harness
venv's interpreter, passing a typed JSON request on stdin and reading a typed JSON
response on stdout. The harness side is ``harness/capychem_harness/score.py``,
running under Python 3.10 + PyTDC 0.3.6.

This module is the only sanctioned crossing of the harness↔modern boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# packages/core/capychem/oracle.py -> repo root is parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_HARNESS_PYTHON = _REPO_ROOT / "harness" / ".venv" / "bin" / "python"
_SCORER = _REPO_ROOT / "harness" / "capychem_harness" / "score.py"


class HarnessError(RuntimeError):
    """Raised when the harness subprocess fails or returns an error payload."""


@dataclass(frozen=True)
class OracleResult:
    """One scored candidate. ``score`` is ``None`` when the SMILES is invalid."""

    smiles: str
    score: float | None
    valid: bool
    wall_ms: int


def _harness_python() -> Path:
    override = os.environ.get("CAPYCHEM_HARNESS_PYTHON")
    return Path(override) if override else _DEFAULT_HARNESS_PYTHON


def score_smiles(
    smiles: list[str], task: str, *, timeout_s: float = 120.0
) -> list[OracleResult]:
    """Score SMILES against a PyTDC oracle via the isolated harness subprocess.

    Raises ``HarnessError`` if the harness env is missing, the subprocess fails,
    or the response is malformed.
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
            f"Harness returned no JSON (exit {proc.returncode}). "
            f"stderr tail: {proc.stderr[-500:]}"
        )
    if payload.get("error"):
        raise HarnessError(str(payload["error"]))

    return [
        OracleResult(
            smiles=row["smiles"],
            score=row["score"],
            valid=row["valid"],
            wall_ms=row["wall_ms"],
        )
        for row in payload["results"]
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
