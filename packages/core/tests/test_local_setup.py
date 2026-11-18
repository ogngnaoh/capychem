"""Local launcher safeguards do not touch an active application database."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_running_local_cluster_port_is_verified_before_any_sql(tmp_path, monkeypatch):
    dev = load_script("dev")
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "postgres_bin", lambda: tmp_path / "bin")
    data = tmp_path / ".local/postgres"
    data.mkdir(parents=True)
    (data / "PG_VERSION").write_text("16")
    (data / "postmaster.pid").write_text("1234\n/data\n123456\n55433\n")
    monkeypatch.setattr(
        dev.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0)
    )
    sql = Mock(side_effect=AssertionError("Must not contact another database"))
    monkeypatch.setattr(dev.subprocess, "check_output", sql)
    with pytest.raises(RuntimeError, match="already running on port 55433"):
        dev.local_postgres(55434)
    sql.assert_not_called()


def test_science_config_rejects_partial_manifest_and_preserves_explicit_env(tmp_path):
    dev = load_script("dev")
    config = tmp_path / "setup.json"
    config.write_text('{"configuration":')
    with pytest.raises(RuntimeError, match="Re-run scripts/setup_science.py"):
        dev.load_science_config(config, {})
    config.write_text(json.dumps({"configuration": {"CAPYCHEM_SCIENCE_PYTHON": "/registered"}}))
    env = {"CAPYCHEM_SCIENCE_PYTHON": "/explicit"}
    dev.load_science_config(config, env)
    assert env["CAPYCHEM_SCIENCE_PYTHON"] == "/explicit"
    with pytest.raises(RuntimeError, match="does not exist"):
        dev.load_science_config(tmp_path / "missing.json", {})


def test_failed_setup_manifest_write_keeps_previous_registration(tmp_path, monkeypatch):
    setup = load_script("setup_science")
    path = tmp_path / "setup-manifest.json"
    path.write_text('{"configuration": {"old": "registered"}}')
    before = path.read_bytes()
    original = Path.replace

    def fail_replace(self, destination):
        if destination == path:
            raise OSError("interrupted write")
        return original(self, destination)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted write"):
        setup.atomic_write(path, '{"configuration": {"new": "registered"}}')
    assert path.read_bytes() == before
