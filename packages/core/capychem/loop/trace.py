"""Langfuse span helpers for the loop.

No-ops when LANGFUSE_* keys are absent, so pytest/CI never need a running
Langfuse. When enabled, every node emits a span; nesting is maintained by
threading parent span ids through LoopState (contextvars are unreliable across
async ``await`` boundaries).

NOTE: targets the Langfuse v2 Python SDK (langfuse>=2,<3). If a different major
is installed, adapt the client/span calls inside the ``_enabled`` branches only —
the public surface (is_enabled / trace_run / span / flush) stays the same.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_REQUIRED_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def is_enabled() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_KEYS)


_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from langfuse import Langfuse  # type: ignore[import-untyped]  # no py.typed in v2

        _client = Langfuse()
    return _client


def trace_run(run_id: int, task: str) -> str | None:
    """Open the top-level trace for a run; return its id (None when disabled)."""
    if not is_enabled():
        return None
    try:
        t = _get_client().trace(name="run", metadata={"run_id": run_id, "task": task})
        return str(t.id)
    except Exception:  # noqa: BLE001 - tracing must never break the loop
        return None


@contextmanager
def span(name: str, *, parent_id: str | None, **metadata: Any) -> Iterator[str | None]:
    """Context manager yielding the new span's id (or None when disabled/failed).

    ``parent_id`` is the enclosing trace or span id, threaded via LoopState.
    """
    if not is_enabled():
        yield None
        return
    sp = None
    try:
        sp = _get_client().span(name=name, trace_id=parent_id, metadata=metadata or None)
        yield str(sp.id)
    except Exception:  # noqa: BLE001
        yield None
    finally:
        if sp is not None:
            try:
                sp.end()
            except Exception:  # noqa: BLE001
                pass


def flush() -> None:
    """Flush buffered events (no-op when disabled)."""
    if not is_enabled():
        return
    try:
        _get_client().flush()
    except Exception:  # noqa: BLE001
        pass
