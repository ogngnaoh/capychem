"""Recording merges preserve old evidence and reject identity replacement."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "export_recorded_demo", ROOT / "scripts/export_recorded_demo.py"
)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def test_portable_export_keeps_pose_hashes_and_omits_local_worker_log_urls():
    pose = {"id": "p", "name": "pose.sdf", "sha256": "pose-hash", "url": "/artifacts/p"}
    log = {"id": "l", "name": "stderr.log", "sha256": "log-hash", "url": "/artifacts/l"}
    original = {"artifacts": [pose, log]}
    portable = exporter.portable_experiment_record(original)
    assert portable["artifacts"] == [pose]
    assert portable["omitted_worker_logs"] == [
        {"id": "l", "name": "stderr.log", "sha256": "log-hash"}
    ]
    assert original["artifacts"] == [pose, log]


def recording(number):
    identifier = f"00000000-0000-0000-0000-{number:012d}"
    return {
        "schema_version": 1,
        "kind": "recorded_experiments",
        "recorded_at": f"capture-{number}",
        "presets": {"presets": [{"id": "same-target", "revision": number}]},
        "experiments": [{"experiment": {"id": identifier}, "export_url": f"/{number}.json"}],
        "studies": [{"id": identifier, "provenance": f"original-{number}"}],
    }


def test_append_preserves_old_records_catalog_and_inputs():
    old, new = recording(1), recording(2)
    before = copy.deepcopy(old)
    result = exporter.merge_recordings(old, new)
    assert old == before
    assert result["experiments"] == [*old["experiments"], *new["experiments"]]
    assert result["studies"] == [*old["studies"], *new["studies"]]
    assert result["presets"] == old["presets"]
    assert result["recorded_at"] == new["recorded_at"]


@pytest.mark.parametrize("key", ["experiments", "studies"])
def test_append_rejects_replacement_even_if_data_is_unchanged(key):
    old, new = recording(1), recording(2)
    new[key] = copy.deepcopy(old[key])
    with pytest.raises(ValueError, match="cannot replace existing"):
        exporter.merge_recordings(old, new)


@pytest.mark.parametrize("key", ["experiments", "studies"])
def test_append_rejects_duplicate_identities(key):
    old, new = recording(1), recording(2)
    new[key] *= 2
    with pytest.raises(ValueError, match="Duplicate"):
        exporter.merge_recordings(old, new)


def test_append_rejects_unsupported_recording_format():
    new = recording(2)
    new["schema_version"] = 2
    with pytest.raises(ValueError, match="unsupported recording"):
        exporter.merge_recordings(recording(1), new)
