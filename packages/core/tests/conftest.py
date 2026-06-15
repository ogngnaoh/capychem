"""Shared pytest fixtures for the core test suite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


def harness_available() -> bool:
    """True iff the legacy harness interpreter is reachable, mirroring how
    oracle.py locates it: the CAPYCHEM_HARNESS_PYTHON override, else the default
    harness/.venv/bin/python under the repo root. Harness-backed tests skip when
    this is False so the suite stays green in a harness-less CI env."""
    override = os.environ.get("CAPYCHEM_HARNESS_PYTHON")
    if override:
        return Path(override).exists()
    # packages/core/tests/conftest.py -> repo root is parents[3].
    default = Path(__file__).resolve().parents[3] / "harness" / ".venv" / "bin" / "python"
    return default.exists()


@pytest.fixture
def harness() -> Iterator[None]:
    """Skip a harness-backed test cleanly when no harness interpreter is reachable."""
    if not harness_available():
        pytest.skip("needs harness venv (set CAPYCHEM_HARNESS_PYTHON or build harness/.venv)")
    yield
