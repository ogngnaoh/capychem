from __future__ import annotations

import contextlib

import pytest
from capychem.loop import trace


def test_disabled_without_keys(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    assert trace.is_enabled() is False


def test_span_is_a_noop_context_manager_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    # Must not raise and must yield a usable (possibly None) span id.
    with trace.span("node:propose", trace_id=None) as span_id:
        assert span_id is None or isinstance(span_id, str)


def test_flush_is_safe_when_disabled(monkeypatch) -> None:
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    with contextlib.suppress(Exception):
        trace.flush()  # must be a no-op, never raise


def _fake_client(ended: list[bool]) -> object:
    class _FakeSpan:
        id = "span-123"

        def end(self) -> None:
            ended.append(True)

    class _FakeClient:
        def span(self, **kwargs: object) -> _FakeSpan:
            return _FakeSpan()

    return _FakeClient()


def test_span_yields_id_and_ends_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ended: list[bool] = []
    monkeypatch.setattr(trace, "_get_client", lambda: _fake_client(ended))
    with trace.span("node:x", trace_id="trace-1") as sid:
        assert sid == "span-123"
    assert ended == [True]  # span ended on normal exit


def test_span_propagates_body_exception_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ended: list[bool] = []
    monkeypatch.setattr(trace, "_get_client", lambda: _fake_client(ended))
    # The body's ValueError must propagate as ValueError (NOT a masking RuntimeError).
    with pytest.raises(ValueError):
        with trace.span("node:x", trace_id=None):
            raise ValueError("boom")
    assert ended == [True]  # span still ended despite the body error


def test_span_threads_parent_observation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    calls: list[dict[str, object]] = []

    class _Span:
        id = "span-1"

        def end(self) -> None: ...

    class _Client:
        def span(self, **kw: object) -> _Span:
            calls.append(kw)
            return _Span()

    monkeypatch.setattr(trace, "_get_client", lambda: _Client())
    with trace.span("node:propose", trace_id="trace-1", parent_observation_id="gen-1"):
        pass
    assert calls[0]["trace_id"] == "trace-1"
    assert calls[0]["parent_observation_id"] == "gen-1"


def test_gen_span_opens_under_trace_and_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ended: list[bool] = []

    class _Span:
        id = "gen-span-9"

        def end(self) -> None:
            ended.append(True)

    class _Client:
        def span(self, **kw: object) -> _Span:
            assert kw["trace_id"] == "trace-1"
            assert kw.get("parent_observation_id") is None  # gen span is a direct child of the trace
            return _Span()

    monkeypatch.setattr(trace, "_get_client", lambda: _Client())
    sid = trace.gen_span("trace-1", run_id=7, gen_index=0)
    assert sid == "gen-span-9"
    trace.end_gen_span(run_id=7, gen_index=0)
    assert ended == [True]
    trace.end_gen_span(run_id=7, gen_index=0)  # idempotent: second end is a safe no-op
