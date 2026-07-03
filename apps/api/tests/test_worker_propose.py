"""Unit test for the Modal worker's pure `_choice_to_row` helper (slice 06-06,
Part D). apps/worker/app.py is not a uv workspace member and its `score`/
`propose` are wrapped by Modal decorators at import time, so the Modal wiring
itself is verified by inspection against the proven fan-out pattern in
capychem.proposer._direct_propose — only the module-level, undecorated
`_choice_to_row` helper is a plain function and is unit-tested here. Imported
by file path since pytest's testpaths cover packages/core/tests and
apps/api/tests, not apps/worker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import requests

_WORKER_APP = Path(__file__).resolve().parents[3] / "apps" / "worker" / "app.py"


def _load_worker_app() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capychem_worker_app", _WORKER_APP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


worker_app = _load_worker_app()


class _FakeResponse:
    """Minimal stand-in for requests.Response — only what _choice_to_row reads."""

    def __init__(self, status_code: int, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        raise requests.exceptions.HTTPError(f"{self.status_code} error")


def test_choice_to_row_maps_a_good_response_with_its_own_usage() -> None:
    resp = _FakeResponse(
        200,
        {
            "choices": [{"message": {"content": "CCO"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )
    row = worker_app._choice_to_row(resp)
    assert row == {"raw": "CCO", "tokens_in": 12, "tokens_out": 4}


@pytest.mark.parametrize("status_code", [402, 429, 500, 503])
def test_choice_to_row_degrades_a_transient_status(status_code: int) -> None:
    resp = _FakeResponse(status_code, {"error": "boom"})
    row = worker_app._choice_to_row(resp)
    assert row == {"raw": "", "tokens_in": 0, "tokens_out": 0}


def test_choice_to_row_degrades_a_request_exception() -> None:
    exc = requests.exceptions.ConnectionError("connection reset")
    row = worker_app._choice_to_row(exc)
    assert row == {"raw": "", "tokens_in": 0, "tokens_out": 0}


def test_choice_to_row_propagates_a_non_transient_4xx() -> None:
    resp = _FakeResponse(400, {"error": "invalid request"})
    with pytest.raises(requests.exceptions.HTTPError):
        worker_app._choice_to_row(resp)
