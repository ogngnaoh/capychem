"""The eval CLI must load .env.local so an --mutation-strategy=llm eval doesn't
silently fall back to the stub when the key lives only in .env.local (a fresh-fork
footgun; the API lifespan and capychem-run already do this)."""

import pytest
from capychem.eval import cli


def test_eval_cli_main_loads_local_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"n": 0}
    monkeypatch.setattr(
        cli, "load_local_env", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    )
    # --help exits early via argparse; load_local_env must already have run by then.
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert called["n"] == 1
