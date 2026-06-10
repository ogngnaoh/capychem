from __future__ import annotations

import contextlib

from capychem.loop import trace


def test_disabled_without_keys(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    assert trace.is_enabled() is False


def test_span_is_a_noop_context_manager_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    # Must not raise and must yield a usable (possibly None) span id.
    with trace.span("node:propose", parent_id=None) as span_id:
        assert span_id is None or isinstance(span_id, str)


def test_flush_is_safe_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    with contextlib.suppress(Exception):
        trace.flush()  # must be a no-op, never raise
