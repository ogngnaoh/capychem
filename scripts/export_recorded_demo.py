#!/usr/bin/env python3
"""Capture completed local experiments as a verified, API-free studio recording.

This preserves actual experiment IDs, protocol specifications, coordinates and
evidence. It never fabricates a run or changes its scientific outcome. The
manifest is published last so a failed download cannot expose a partial capture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def portable_experiment_record(exported: dict[str, Any]) -> dict[str, Any]:
    """Keep verified scientific files. Worker diagnostics can contain local paths."""
    files = []
    diagnostics = []
    for artifact in exported["artifacts"]:
        if artifact["name"].endswith(".log"):
            diagnostics.append({key: artifact[key] for key in ("id", "name", "sha256")})
        else:
            files.append(artifact)
    return {**exported, "artifacts": files, "omitted_worker_logs": diagnostics}


def merge_recordings(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Append a capture without replacing any previously recorded result."""
    for value in (existing, incoming):
        if value.get("schema_version") != 1 or value.get("kind") != "recorded_experiments":
            raise ValueError("Cannot merge an unsupported recording format")
    result = {**existing, "recorded_at": incoming["recorded_at"]}
    for key in ("experiments", "studies"):
        old = existing.get(key, [])
        new = incoming.get(key, [])

        def identity(row: dict[str, Any], collection: str = key) -> str:
            return str(
                uuid.UUID(row["experiment"]["id"] if collection == "experiments" else row["id"])
            )

        old_ids = [identity(row) for row in old]
        new_ids = [identity(row) for row in new]
        if len(set(old_ids)) != len(old_ids) or len(set(new_ids)) != len(new_ids):
            raise ValueError(f"Duplicate {key} identities in recording")
        if set(old_ids) & set(new_ids):
            raise ValueError(f"Merge cannot replace existing {key}; capture only new IDs")
        result[key] = [*old, *new]
    # Existing catalog entries may describe older recorded engine revisions.
    # Keep them intact; each experiment carries its own frozen protocol identity.
    presets = {p["id"]: p for p in existing["presets"]["presets"]}
    for preset in incoming["presets"]["presets"]:
        presets.setdefault(preset["id"], preset)
    result["presets"] = {**existing["presets"], "presets": list(presets.values())}
    return result


def rewrite_artifacts(value: Any, replacements: dict[str, str], eid: str) -> Any:
    if isinstance(value, str):
        if value.startswith("/artifacts/"):
            if value not in replacements:
                raise ValueError(f"{eid}: unrecorded artifact reference {value}")
            return replacements[value]
        return value
    if isinstance(value, list):
        return [rewrite_artifacts(item, replacements, eid) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_artifacts(item, replacements, eid) for key, item in value.items()}
    return value


def share_backbones(viewer: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate display data only; the audited source artifacts stay intact."""
    shared: dict[str, Any] = {}
    structures = []
    for original in viewer["structures"]:
        structure = dict(original)
        atoms = structure.pop("backboneAtoms", None)
        if atoms is not None:
            encoded = json.dumps(atoms, separators=(",", ":"), allow_nan=False).encode()
            key = hashlib.sha256(encoded).hexdigest()
            shared[key] = atoms
            structure["backboneRef"] = key
        structures.append(structure)
    return {**viewer, "structures": structures, "sharedBackbones": shared}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_ids", nargs="*")
    parser.add_argument(
        "--study-id",
        action="append",
        default=[],
        help="Capture a completed study and all of its member experiments",
    )
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    parser.add_argument("--public-dir", type=Path, default=ROOT / "apps/studio/public")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Append new IDs while preserving existing recorded results",
    )
    args = parser.parse_args()
    base = args.api.rstrip("/")
    if urllib.parse.urlsplit(base).scheme not in {"http", "https"}:
        parser.error("--api must be an HTTP(S) API address")
    experiment_ids = list(dict.fromkeys(str(uuid.UUID(eid)) for eid in args.experiment_ids))
    study_ids = list(dict.fromkeys(str(uuid.UUID(sid)) for sid in args.study_id))
    if not experiment_ids and not study_ids:
        parser.error("Supply experiment IDs or --study-id")
    public = args.public_dir.resolve()
    public.mkdir(parents=True, exist_ok=True)
    manifest = public / "data/recorded-experiments.json"
    existing = json.loads(manifest.read_text()) if args.merge and manifest.exists() else None

    def fetch(path: str) -> bytes:
        with urllib.request.urlopen(base + path, timeout=60) as response:
            return response.read()

    def fetch_json(path: str) -> Any:
        return json.loads(fetch(path))

    study_exports = []
    for sid in study_ids:
        exported_study = fetch_json(f"/studies/{sid}/export")
        study = exported_study["study"]
        if study["status"] not in {"completed", "completed_with_errors"}:
            raise ValueError(f"{sid}: only completed studies can be recorded")
        for member in study["members"]:
            eid = str(uuid.UUID(member["experiment"]["id"]))
            if eid not in experiment_ids:
                experiment_ids.append(eid)
        exported_study["experiments"] = [
            portable_experiment_record(member) for member in exported_study["experiments"]
        ]
        study_exports.append(exported_study)

    recorded: dict[str, Any] = {
        "schema_version": 1,
        "kind": "recorded_experiments",
        "recorded_at": datetime.now(UTC).isoformat(),
        "presets": fetch_json("/experiments/presets"),
        "experiments": [],
        "studies": [],
    }
    downloaded = 0
    all_replacements: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix=".recording-", dir=public) as temporary:
        staging = Path(temporary)
        for eid in experiment_ids:
            prefix = f"/experiments/{eid}"
            exported = portable_experiment_record(fetch_json(prefix + "/export"))
            experiment = exported["experiment"]
            if experiment["status"] not in {"completed", "completed_with_errors"}:
                raise ValueError(f"{eid}: only completed experiments can be recorded")
            candidates = fetch_json(prefix + "/candidates")["items"]
            if [c["id"] for c in candidates] != [c["id"] for c in exported["candidates"]]:
                raise ValueError(f"{eid}: result set changed during capture")
            viewer = fetch_json(prefix + "/viewer")
            attempts = fetch_json(prefix + "/attempts")["items"]
            events: list[dict[str, Any]] = []
            after = 0
            while True:
                page = fetch_json(prefix + f"/events?after={after}&limit=500")
                items = page["events"]
                if not items:
                    break
                next_after = max(item["seq"] for item in items)
                if next_after <= after:
                    raise ValueError(f"{eid}: event cursor did not advance")
                events.extend(items)
                after = next_after
                if len(items) < 500:
                    break
            replacements: dict[str, str] = {}
            for artifact in exported["artifacts"]:
                aid = str(uuid.UUID(artifact["id"]))
                suffix = Path(artifact["name"]).suffix
                if not re.fullmatch(r"\.[A-Za-z0-9_-]{1,16}", suffix):
                    suffix = ".bin"
                relative = f"data/recorded/{eid}/artifacts/{aid}{suffix}"
                data = fetch(f"/artifacts/{aid}")
                checksum = hashlib.sha256(data).hexdigest()
                if checksum != artifact["sha256"] or len(data) != artifact["size_bytes"]:
                    raise ValueError(f"{eid}: artifact {aid} failed its size/hash check")
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                replacements[f"/artifacts/{aid}"] = "/" + relative
                downloaded += 1
            all_replacements.update(replacements)

            candidates = rewrite_artifacts(candidates, replacements, eid)
            for candidate in candidates:
                if candidate.get("status") == "invalid" or not candidate.get("smiles"):
                    continue
                cid = str(uuid.UUID(candidate["id"]))
                query = urllib.parse.urlencode({"smiles": candidate["smiles"], "w": 320, "h": 220})
                data = fetch("/molecule/svg?" + query)
                if ET.fromstring(data).tag.rsplit("}", 1)[-1] != "svg":
                    raise ValueError(f"{eid}: depiction response was not SVG")
                relative = f"data/recorded/{eid}/depictions/{cid}.svg"
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                candidate["depictionUrl"] = "/" + relative
                candidate["recorded"] = True
                candidate["description"] = "Recorded local calculation"
            export_url = f"/data/recorded/{eid}/experiment.json"
            export_path = staging / export_url.lstrip("/")
            export_path.parent.mkdir(parents=True, exist_ok=True)
            captured_export = rewrite_artifacts(exported, replacements, eid)
            captured_export["kind"] = "recorded_computation"
            captured_export["recorded_at"] = recorded["recorded_at"]
            export_path.write_text(json.dumps(captured_export, indent=2, allow_nan=False) + "\n")
            recorded["experiments"].append(
                {
                    "experiment": rewrite_artifacts(experiment, replacements, eid),
                    "candidates": candidates,
                    "decisions": exported["decisions"],
                    "attempts": attempts,
                    "events": events,
                    "viewer": share_backbones(rewrite_artifacts(viewer, replacements, eid)),
                    "export_url": export_url,
                }
            )

        for exported_study in study_exports:
            sid = exported_study["study"]["id"]
            captured = rewrite_artifacts(exported_study, all_replacements, sid)
            captured["kind"] = "recorded_study"
            captured["recorded_at"] = recorded["recorded_at"]
            export_url = f"/data/recorded/studies/{sid}.json"
            export_path = staging / export_url.lstrip("/")
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(json.dumps(captured, indent=2, allow_nan=False) + "\n")
            recorded["studies"].append({**captured["study"], "export_url": export_url})

        if existing is not None:
            recorded = merge_recordings(existing, recorded)
            # Check all conflicts before publication, including exports and
            # depictions, so append mode cannot rewrite prior capture files.
            for source in staging.rglob("*"):
                destination = public / source.relative_to(staging)
                if (
                    source.is_file()
                    and destination.exists()
                    and source.read_bytes() != destination.read_bytes()
                ):
                    raise ValueError(f"Merge cannot replace existing recording file: {destination}")

        for source in staging.rglob("*"):
            if not source.is_file():
                continue
            destination = public / source.relative_to(staging)
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            if (
                "artifacts" in source.parts
                and destination.exists()
                and destination.read_bytes() != data
            ):
                raise ValueError(f"Existing recorded artifact changed: {destination.name}")
            temporary_path = destination.with_name(destination.name + ".recording-tmp")
            temporary_path.write_bytes(data)
            temporary_path.replace(destination)
        temporary_manifest = manifest.with_suffix(".tmp")
        temporary_manifest.write_text(
            json.dumps(recorded, separators=(",", ":"), allow_nan=False) + "\n"
        )
        temporary_manifest.replace(manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "experiments": len(recorded["experiments"]),
                "studies": len(recorded["studies"]),
                "added_experiments": len(experiment_ids),
                "added_studies": len(study_ids),
                "verified_artifacts": downloaded,
            }
        )
    )


if __name__ == "__main__":
    main()
