"""Load local secrets from .env.local into the process env (idempotent).

Called at each loop entrypoint so Langfuse keys (and any other local secrets)
are present without the operator having to export them. .env.local is gitignored
(SPEC §8.1) — never commit it.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _default_path() -> Path:
    # packages/core/capychem/env.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / ".env.local"


def load_local_env(path: Path | None = None) -> None:
    """Load `.env.local` if present. Does not override already-set env vars."""
    target = path or _default_path()
    if target.exists():
        load_dotenv(dotenv_path=os.fspath(target), override=False)
