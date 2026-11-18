#!/usr/bin/env python3
"""Opt-in live replay of the versioned CDK2 regression baseline.

No jobs are submitted without --run. Existing experiments and user decisions are
never edited. Exit0=pass,1=execution/preflight failure,2=contract failure,
3=scientific review required. A generated extra hit is not a failure.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/core"))
from capychem.experiments.science_regression import (  # noqa: E402
    contract_failures,
    science_comparison,
)

TERMINAL = {"completed", "completed_with_errors", "failed", "cancelled"}


class ContractError(ValueError):
    """Downloaded evidence violates an immutable artifact contract."""


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


class API:
    def __init__(self, origin):
        parsed = urllib.parse.urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("This opt-in runner supports a local loopback HTTP API only")
        self.origin = origin.rstrip("/")

    def read(self, path, body=None, key=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Expected an API-relative path")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(
            self.origin + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        # A retry uses the exact same idempotency key after a lost POST response.
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError:
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(1)

    def download(self, artifact, root):
        relative = artifact["relative_path"]
        attempt = str(uuid.UUID(artifact["attempt_id"]))
        attempt_root = (root / attempt).resolve()
        target = (attempt_root / relative).resolve()
        if not target.is_relative_to(attempt_root) or Path(relative).is_absolute():
            raise ContractError("Artifact path escapes the attempt evidence directory")
        url = artifact["url"]
        if not url.startswith("/artifacts/"):
            raise ContractError("Expected an opaque local artifact URL")
        with urllib.request.urlopen(self.origin + url, timeout=30) as response:
            payload = response.read()
            etag = response.headers.get("ETag", "").strip('"')
            length = response.headers.get("Content-Length")
        if hashlib.sha256(payload).hexdigest() != artifact["sha256"]:
            raise ContractError(f"Artifact hash mismatch: {relative}")
        if len(payload) != artifact["size_bytes"] or (length and int(length) != len(payload)):
            raise ContractError(f"Artifact size mismatch: {relative}")
        if etag != artifact["sha256"]:
            raise ContractError(f"Artifact ETag mismatch: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != payload:
            raise ContractError("Two artifacts disagree at one attempt-relative path")
        target.write_bytes(payload)


def identity_changes(baseline, preset):
    expected = baseline["identity"]
    if preset["id"] != expected["target_preparation_id"]:
        raise ValueError("Target preparation identity changed; create a new baseline")
    if preset["manifest"]["manifest_sha256"] != expected["target_manifest_sha256"]:
        raise ValueError("Target preparation bytes changed; create a new baseline")
    descriptor = preset["protocol_descriptor"]
    if descriptor["id"] != expected["protocol"]:
        raise ValueError("Protocol identity changed; create a new baseline")
    return [
        {"field": key, "baseline": expected[key], "current": descriptor[current]}
        for key, current in [
            ("engine_fingerprint", "engine_fingerprint"),
            ("protocol_revision", "revision"),
        ]
        if expected[key] != descriptor[current]
    ]


def verify_science_files(directory, report):
    published = set()
    for artifact in report["artifacts"]:
        path = (directory / artifact["path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ContractError("Scientific manifest path is invalid")
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ContractError(f"Scientific artifact hash mismatch: {artifact['path']}")
        published.add(artifact["path"])
    for record in [report["parent"], *report["records"]]:
        poses = record.get("poses", [record["baseline_pose"]] if "baseline_pose" in record else [])
        for pose in poses:
            for key in ["sdf", "view_json", "log"]:
                if pose[key] not in published:
                    raise ContractError(f"Pose references an unpublished {key} artifact")
    protocol = directory / "inputs/protocol.json"
    for name, key in [("request", "request_spec"), ("spec", "spec")]:
        if json.loads((directory / f"inputs/{name}.json").read_text()) != report[key]:
            raise ContractError(f"Frozen {name} artifact and report disagree")
    if json.loads(protocol.read_text()) != report["protocol_manifest"]:
        raise ContractError("Protocol artifact and report manifest disagree")
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != report["provenance"]["protocol_sha256"]:
        raise ContractError("Protocol artifact hash mismatch")


def replay_case(api, baseline, case, output, invocation, args):
    output.mkdir()
    spec = copy.deepcopy(case["spec"])
    spec["label"] = f"Regression {case['id']} · {invocation[:8]}"
    spec["parent_experiment_id"] = None
    key = f"regression-{invocation}-{case['id']}"
    write(output / "submission-request.json", {"spec": spec, "idempotency_key": key})
    submitted = api.read("/experiments", spec, key)
    write(output / "submission.json", submitted)
    eid = submitted["id"]
    print(json.dumps({"event": "submitted", "case": case["id"], "experiment_id": eid}), flush=True)
    started = time.monotonic()
    previous = None
    while True:
        detail = api.read(f"/experiments/{eid}")
        state = detail["status"]
        if state != previous:
            print(json.dumps({"event": "state", "case": case["id"], "status": state}), flush=True)
            previous = state
        write(output / "detail.json", detail)
        if state in TERMINAL:
            break
        if time.monotonic() - started > args.timeout:
            raise TimeoutError(f"Monitoring deadline for {eid}; inspect it in the workspace")
        time.sleep(args.poll_seconds)
    if state in {"failed", "cancelled"}:
        raise RuntimeError(f"Experiment {eid} ended {state}; see saved detail.json")
    exported = api.read(f"/experiments/{eid}/export")
    write(output / "export.json", exported)
    artifacts = output / "attempts"
    artifacts.mkdir()
    for artifact in exported["artifacts"]:
        api.download(artifact, artifacts)
    active = detail["counts"]["active_attempt_id"]
    directory = artifacts / active
    report = json.loads((directory / "report.json").read_text())
    verify_science_files(directory, report)
    failures = contract_failures(
        case, report, exported, baseline["comparison_policy"]["numeric_identity_absolute_tolerance"]
    )
    model_changes = []
    expected = baseline["identity"]
    for key in ["engine_fingerprint", "vina_binary_sha256"]:
        actual = report["provenance"][key]
        if actual != expected[key]:
            model_changes.append({"field": key, "baseline": expected[key], "current": actual})
    if report["provenance"]["versions"] != expected["science_versions"]:
        model_changes.append(
            {
                "field": "science_versions",
                "baseline": expected["science_versions"],
                "current": report["provenance"]["versions"],
            }
        )
    if case["spec"]["candidate_source"]["kind"] == "libinvent":
        for key, value in expected["generator"].items():
            if report["generation"].get(key) != value:
                model_changes.append(
                    {
                        "field": f"generator.{key}",
                        "baseline": value,
                        "current": report["generation"].get(key),
                    }
                )
    if model_changes and not args.allow_engine_change:
        failures.append("identity:changed_without_allow_engine_change")
    molecular_audit = None
    if args.science_python and not failures:
        reference = baseline["heldout_reference"]
        audit_path = output / "molecular-audit.json"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "packages/core")}
        process = subprocess.run(
            [
                args.science_python,
                "-m",
                "capychem.experiments.science_regression",
                "--audit-directory",
                str(directory),
                "--reference",
                str(ROOT / reference["path"]),
                "--reference-sha256",
                reference["sha256"],
                "--output",
                str(audit_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        (output / "molecular-audit.log").write_text(process.stdout + process.stderr)
        if process.returncode:
            failures.append("artifact:molecular_audit_execution_failed")
        else:
            molecular_audit = json.loads(audit_path.read_text())
            failures.extend("artifact:" + f for f in molecular_audit["failures"])
    science = science_comparison(case, report, baseline["comparison_policy"], molecular_audit)
    if model_changes:
        science["review_reasons"].append(
            "engine_identity_changed:controls_do_not_establish_general_improvement"
        )
        science["status"] = "review_required"
    status = "contract_failed" if failures else science["status"]
    started_at = datetime.fromisoformat(detail["created_at"].replace("Z", "+00:00"))
    finished_at = datetime.fromisoformat(detail["finished_at"].replace("Z", "+00:00"))
    result = {
        "case": case["id"],
        "experiment_id": eid,
        "attempt_id": active,
        "status": status,
        "contract_failures": failures,
        "identity_changes": model_changes,
        "scientific_comparison": science,
        "molecular_audit": molecular_audit,
        "server_seconds": (finished_at - started_at).total_seconds(),
        "http_artifacts_verified": len(exported["artifacts"]),
        "scientific_artifacts_verified": len(report["artifacts"]),
        "report_sha256": hashlib.sha256((directory / "report.json").read_bytes()).hexdigest(),
    }
    write(output / "comparison.json", result)
    print(json.dumps({"event": "compared", "case": case["id"], "status": status}), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", type=Path, default=ROOT / "data/validation/cdk2/growth-v2-baseline-v2.json"
    )
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--run", action="store_true", help="Actually submit new local calculations")
    parser.add_argument("--allow-engine-change", action="store_true")
    parser.add_argument(
        "--science-python", help="Optional isolated chemistry Python for saved-pose audit"
    )
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Per-case monitoring/audit seconds"
    )
    parser.add_argument("--poll-seconds", type=float, default=2)
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline.read_text())
    if baseline["schema_version"] != 1:
        parser.error("Unsupported baseline schema")
    cases = [c for c in baseline["cases"] if not args.cases or c["id"] in args.cases]
    if not cases or (args.cases and set(args.cases) - {c["id"] for c in cases}):
        parser.error("Unknown case; choose " + ", ".join(c["id"] for c in baseline["cases"]))
    needs_generator = any(c["spec"]["candidate_source"]["kind"] == "libinvent" for c in cases)
    if args.timeout < 1 or not 0 < args.poll_seconds <= 30:
        parser.error("Timeout must be positive; poll interval must be in (0,30]")
    if not args.run:
        print(
            json.dumps(
                {
                    "baseline": baseline["id"],
                    "cases": [c["id"] for c in cases],
                    "submitted": False,
                    "instruction": "Use --run --output-dir NEW_DIRECTORY",
                }
            )
        )
        return 0
    if not args.output_dir:
        parser.error("--run requires a fresh --output-dir")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "baseline_id": baseline["id"],
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "status": "running",
        "cases": [],
        "allow_engine_change": args.allow_engine_change,
        "api": args.api,
        "scientific_scope": "Retrospective curated controls; no affinity or general accuracy claim",
    }
    write(output / "baseline.json", baseline)
    try:
        api = API(args.api)
        ready = api.read("/experiments/readiness")
        write(output / "readiness.json", ready)
        if not ready["ready"]:
            raise RuntimeError("Local worker/science runtime is not ready")
        presets = api.read("/experiments/presets")
        write(output / "presets.json", presets)
        preset = next(
            p
            for p in presets["presets"]
            if p["id"] == baseline["identity"]["target_preparation_id"]
        )
        changes = identity_changes(baseline, preset)
        runtime = ready["worker"]["health"]
        for field, current, expected in [
            (
                "science_versions",
                runtime["science"]["versions"],
                baseline["identity"]["science_versions"],
            ),
            *[
                (
                    f"generator.{key}",
                    runtime["generator"].get(key),
                    baseline["identity"]["generator"][key],
                )
                for key in ["checkpoint_sha256", "source_commit"]
                if needs_generator
            ],
        ]:
            if current != expected:
                changes.append({"field": field, "baseline": expected, "current": current})
        result["preflight_identity_changes"] = changes
        if changes and not args.allow_engine_change:
            raise ValueError(
                "Engine identity changed; inspect it or explicitly use --allow-engine-change"
            )
        if needs_generator and not ready["capabilities"]["libinvent"]:
            raise RuntimeError("This case requires a ready LibInvent generator")
        invocation = str(uuid.uuid4())
        for case in cases:
            result["cases"].append(
                replay_case(api, baseline, case, output / case["id"], invocation, args)
            )
            write(output / "comparison.json", result)
        statuses = {c["status"] for c in result["cases"]}
        result["status"] = (
            "contract_failed"
            if "contract_failed" in statuses
            else ("review_required" if "review_required" in statuses else "pass")
        )
    except ContractError as exc:
        result.update(status="contract_failed", error=str(exc))
    except Exception as exc:
        result.update(status="execution_failed", error=f"{type(exc).__name__}: {exc}")
    write(output / "comparison.json", result)
    print(
        json.dumps({"status": result["status"], "evidence": str(output / "comparison.json")}),
        flush=True,
    )
    return {"pass": 0, "execution_failed": 1, "contract_failed": 2, "review_required": 3}[
        result["status"]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
