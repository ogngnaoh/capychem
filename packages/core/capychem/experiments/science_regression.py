"""Compare recorded experiment contracts separately from scientific evidence.

This module does not run inference. Its optional audit reads held-out coordinates
only after a completed experiment has been downloaded by the replay script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def selected_pose(record: dict[str, Any]) -> dict[str, Any] | None:
    poses: list[dict[str, Any]] = record.get("poses", [])
    return next(
        (p for p in poses if p["id"] == record.get("selected_pose_id")), None
    )


def contract_failures(
    case: dict[str, Any],
    report: dict[str, Any],
    exported: dict[str, Any],
    tolerance: float = 1e-8,
) -> list[str]:
    """Check consistency and input policy, never an exact docking-score oracle."""
    failures: list[str] = []

    def check(ok: object, code: str) -> None:
        if not ok:
            failures.append(code)

    experiment = exported["experiment"]
    request = report["request_spec"]
    check(request == experiment["spec"], "request:api_report_mismatch")
    check(digest(request) == report["provenance"]["request_spec_sha256"], "request:hash")
    executable_keys = {
        "schema_version",
        "target_preparation_id",
        "protocol",
        "candidate_source",
        "limits",
        "seeds",
        "constraints",
        "label",
    }
    check(
        report.get("spec") == {k: v for k, v in request.items() if k in executable_keys},
        "request:executable_spec_mismatch",
    )
    resolved = request["resolved_protocol"]
    protocol = report["protocol_manifest"]
    check(protocol["id"] == request["protocol"], "protocol:identity")
    check(protocol["version"] == resolved["revision"], "protocol:revision")
    check(protocol["vina"]["seed"] == request["seeds"]["vina"], "protocol:vina_seed")
    check(
        protocol["embedding"]["seed_start"] == request["seeds"]["embedding"],
        "protocol:embedding_seed",
    )
    check(
        protocol["embedding"]["attempts"] == request["limits"]["embedding_attempts_per_candidate"],
        "protocol:embedding_budget",
    )
    check(
        report["provenance"]["engine_fingerprint"] == resolved["engine_fingerprint"],
        "provenance:engine_fingerprint",
    )
    check(
        report["provenance"]["preset_sha256"] == resolved["target_manifest_sha256"],
        "provenance:target_manifest",
    )
    for key, value in case["spec"].items():
        if key not in {"label", "parent_experiment_id"}:
            check(request.get(key) == value, f"request:baseline_input:{key}")
    records = report["records"]
    by_id = {r["id"]: r for r in records}
    by_index = {r["proposal_index"]: r for r in records}
    active = experiment["counts"]["active_attempt_id"]

    def raw_identity(value: Any) -> Any:
        prefix = active[:8] + "/"
        return value.removeprefix(prefix) if isinstance(value, str) else value

    api_rows = {raw_identity(r["sourceId"]): r for r in exported["candidates"]}
    artifacts = {(a["attempt_id"], a["relative_path"]): a for a in exported["artifacts"]}
    scientific_hashes = {a["path"]: a["sha256"] for a in report["artifacts"]}
    count = len(records)
    check(len(by_id) == count and len(by_index) == count, "accounting:duplicate_record_identity")
    check(set(by_index) == set(range(count)), "accounting:proposal_indices")
    check(set(api_rows) == set(by_id), "accounting:api_candidate_identities")
    check(len(api_rows) == len(exported["candidates"]), "accounting:api_duplicate_source_ids")
    source = request["candidate_source"]
    if source["kind"] == "libinvent":
        check(report["generation"]["source"] == "libinvent", "generation:source")
        check(report["generation"]["seed"] == source["seed"], "generation:seed")
    requested = (
        len(source["candidates"]) if source["kind"] == "supplied" else source["raw_proposal_count"]
    )
    check(
        count
        == requested
        == report["source_accounting"]["requested"]
        == report["source_accounting"]["returned"]
        == len(report["raw_proposals"]),
        "accounting:raw_proposals",
    )
    if source["kind"] == "supplied":
        for index, supplied in enumerate(source["candidates"]):
            record = by_index.get(index, {})
            check(record.get("proposal_smiles") == supplied["smiles"], f"input:{index}:smiles")
            check(record.get("name") == supplied["name"], f"input:{index}:name")
    selected = [selected_pose(r) for r in records]
    computed = {
        "raw_proposals": count,
        "processed_proposals": count,
        "unique_candidates": len(
            {r["normalized_smiles"] for r in records if r.get("normalized_smiles")}
        ),
        "evaluated_candidates": sum(bool(r["evaluated"]) for r in records),
        "pose_count": sum(len(r["poses"]) for r in records),
        "pose_failures": sum(len(r["pose_errors"]) for r in records),
        "objective_hits": sum(
            bool(p and p["review_ready"] and p["asp86_contact"]) for p in selected
        ),
    }
    for key, value in computed.items():
        check(report["summary"].get(key) == value, f"accounting:summary:{key}")
    api_counts = experiment["counts"]
    for api_key, key in [
        ("proposals", "raw_proposals"),
        ("evaluated", "evaluated_candidates"),
        ("poses", "pose_count"),
        ("pose_errors", "pose_failures"),
        ("objective_hits", "objective_hits"),
    ]:
        check(api_counts.get(api_key) == computed[key], f"accounting:api:{api_key}")
    check(api_counts.get("pending") == 0, "accounting:terminal_pending")
    check(
        api_counts.get("review_ready") == sum(bool(p and p["review_ready"]) for p in selected),
        "accounting:api:review_ready",
    )
    check(
        api_counts.get("excluded")
        == sum(r["status"] in {"invalid", "duplicate", "outside_constraints"} for r in records),
        "accounting:api:excluded",
    )
    check(
        api_counts.get("deferred") == sum(r["status"] == "deferred_budget" for r in records),
        "accounting:api:deferred",
    )
    check(
        computed["evaluated_candidates"] <= request["limits"]["max_unique_candidates_evaluated"],
        "accounting:evaluation_budget",
    )
    for record in records:
        rid = record["id"]
        api = api_rows.get(rid, {})
        check(api.get("attemptId") == active, f"candidate:{rid}:attempt")
        check(api.get("error") == record.get("error"), f"candidate:{rid}:error_projection")
        check(api.get("status") == record["status"], f"candidate:{rid}:status")
        check(api.get("poseCount") == len(record["poses"]), f"candidate:{rid}:pose_count")
        if record["status"] == "duplicate":
            original = by_id.get(record.get("duplicate_of"))
            check(
                original is not None
                and original.get("normalized_smiles") == record.get("normalized_smiles"),
                f"duplicate:{rid}:identity",
            )
            check(
                raw_identity(api.get("duplicateOfSourceId")) == record.get("duplicate_of"),
                f"duplicate:{rid}:api_link",
            )
            original_api = api_rows.get(record.get("duplicate_of"), {})
            check(
                api.get("duplicateOfCandidateId") == original_api.get("id"),
                f"duplicate:{rid}:api_candidate_link",
            )
        pose = selected_pose(record)
        api_poses = {raw_identity(p["label"]): p for p in api.get("poses", [])}
        check(
            set(api_poses) == {p["id"] for p in record["poses"]}, f"pose:{rid}:all_pose_identities"
        )
        for saved in record["poses"]:
            projected = api_poses.get(saved["id"], {})
            artifact = artifacts.get((active, saved["sdf"]), {})
            check(
                bool(artifact) and projected.get("sdfUrl") == artifact.get("url"),
                f"pose:{saved['id']}:sdf_artifact_binding",
            )
            check(
                bool(artifact) and artifact.get("sha256") == scientific_hashes.get(saved["sdf"]),
                f"pose:{saved['id']}:sdf_manifest_hash",
            )
            check(
                projected.get("preparedSmiles") == saved["prepared_smiles"],
                f"pose:{saved['id']}:prepared_identity",
            )
        check(
            (pose is not None) == bool(record.get("selected_pose_id")),
            f"pose:{rid}:missing_selected",
        )
        if pose:
            api_pose: dict[str, Any] = next(
                (p for p in api.get("poses", []) if p["id"] == api.get("structureId")), {}
            )
            check(
                raw_identity(api_pose.get("label")) == pose["id"], f"pose:{rid}:selected_identity"
            )
            check(
                api_pose.get("preparedSmiles") == pose["prepared_smiles"],
                f"pose:{rid}:prepared_identity",
            )
            check(
                pose["prepared_state_id"]
                == "state-" + hashlib.sha256(pose["prepared_smiles"].encode()).hexdigest()[:20],
                f"pose:{rid}:prepared_hash",
            )
            check(
                isinstance(api.get("score"), (int, float))
                and math.isclose(api["score"], pose["score"], rel_tol=0, abs_tol=tolerance),
                f"pose:{rid}:score_projection",
            )
            check(
                api.get("asp86Contact") == pose["asp86_contact"], f"pose:{rid}:contact_projection"
            )
            check(
                api.get("reviewReady") == pose["review_ready"], f"pose:{rid}:eligibility_projection"
            )
        else:
            check(api.get("structureId") is None, f"pose:{rid}:unexpected_selected")
    for expected in case["hard_expectations"]:
        index = expected["proposal_index"]
        record = by_index.get(index, {})
        check(
            bool(record.get("evaluated")) == (expected["admission"] == "evaluated"),
            f"admission:{index}",
        )
        if "status" in expected:
            check(record.get("status") == expected["status"], f"input_policy:{index}:status")
        if expected.get("error_required"):
            check(bool(record.get("error")), f"input_policy:{index}:missing_error")
        if "filter_failures" in expected:
            check(
                record.get("filter_failures") == expected["filter_failures"],
                f"input_policy:{index}:exclusion_reasons",
            )
        if "duplicate_of_proposal_index" in expected:
            original = by_index.get(expected["duplicate_of_proposal_index"], {})
            check(
                record.get("duplicate_of") == original.get("id"), f"input_policy:{index}:duplicate"
            )
    return failures


def science_comparison(
    case: dict[str, Any],
    report: dict[str, Any],
    policy: dict[str, Any],
    molecular_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A failed scientific control requires review, distinct from a broken API."""
    review = []
    if report.get("execution_outcome") == "completed_with_errors":
        review.append("execution:completed_with_errors")
    for record in report["records"]:
        if (
            record.get("pose_errors")
            or any(a.get("status") == "failed" for a in record.get("embedding_attempts", []))
            or record["status"] in {"evaluation_error", "no_pose"}
        ):
            review.append(f"execution:{record['id']}:incomplete_pose_pipeline")
    rows = {r["proposal_index"]: r for r in report["records"]}
    for control in case["scientific_controls"]:
        row = rows.get(control["proposal_index"], {})
        pose = selected_pose(row)
        name = control["name"]
        if pose is None:
            review.append(f"control:{name}:no_selected_pose")
            continue
        for key in ["geometry_pass", "review_ready", "asp86_contact"]:
            if pose[key] != control[key]:
                review.append(f"control:{name}:{key}_changed")
        if pose["ring_drift_A"] > control["maximum_ring_drift_A"]:
            review.append(f"control:{name}:ring_drift")
        if pose["hinge_hbond_type_count"] < control["minimum_hinge_hbond_types"]:
            review.append(f"control:{name}:hinge_contact_loss")
        if molecular_audit:
            rmsd = molecular_audit.get("selected_native_rmsd_A", {}).get(row["id"])
            if rmsd is not None and rmsd > policy["known_pose_rmsd_max_A"]:
                review.append(f"control:{name}:heldout_pose_rmsd")
    measurements = case["reference_measurements"]
    has_summary_reference = measurements.get("summary") is not None
    reference_summary = measurements.get("summary") or {}
    summary_deltas = {
        key: {
            "baseline": reference_summary.get(key, 0) if has_summary_reference else None,
            "current": report["summary"].get(key, 0),
            "delta": report["summary"].get(key, 0) - reference_summary.get(key, 0)
            if has_summary_reference
            else None,
        }
        for key in sorted(reference_summary.keys() | report["summary"].keys())
    }
    baseline_by_graph = {
        r["normalized_smiles"]: r
        for r in measurements["candidates"]
        if r.get("normalized_smiles") and r.get("selected")
    }
    candidates = []
    for row in report["records"]:
        pose = selected_pose(row)
        if not pose:
            continue
        baseline = baseline_by_graph.get(row.get("normalized_smiles"))
        old = baseline["selected"] if baseline else None
        candidates.append(
            {
                "source_id": row["id"],
                "name": row["name"],
                "smiles": row.get("normalized_smiles"),
                "score": pose["score"],
                "baseline_score": old["score"] if old else None,
                "score_delta": pose["score"] - old["score"] if old else None,
                "asp86_contact": pose["asp86_contact"],
                "geometry_pass": pose["geometry_pass"],
                "review_ready": pose["review_ready"],
                "interpretation": (
                    "Model scores are descriptive and do not establish affinity improvement."
                ),
            }
        )
    return {
        "status": "review_required" if review else "pass",
        "review_reasons": review,
        "summary_deltas": summary_deltas,
        "candidate_comparisons": candidates,
        "science_seconds_delta": report["seconds"] - measurements["science_seconds"]
        if measurements.get("science_seconds") is not None
        else None,
        "molecular_audit": "performed" if molecular_audit else "not_run",
        "scope": (
            "Curated receptor-informed controls only; no general docking or affinity validation."
        ),
    }


def audit_completed_run(
    directory: Path, reference: Path, reference_hash: str
) -> dict[str, Any]:
    """Optional chemistry environment: inspect artifacts, then held-out RMSD."""
    from capychem.experiments.science_audit import audit
    from rdkit import Chem
    from rdkit.Chem import rdMolAlign

    report = json.loads((directory / "report.json").read_text())
    if report["status"] != "complete":
        raise ValueError("Held-out comparison requires a completed report")
    if hashlib.sha256(reference.read_bytes()).hexdigest() != reference_hash:
        raise ValueError("Held-out reference failed its pinned hash")
    result = audit(directory)
    observed = Chem.SDMolSupplier(str(reference), removeHs=True)[0]
    rmsd = {}
    for record in report["records"]:
        pose = selected_pose(record)
        if pose and record["name"] == "NU6102":
            molecule = Chem.SDMolSupplier(str(directory / pose["sdf"]), removeHs=True)[0]
            rmsd[record["id"]] = rdMolAlign.CalcRMS(molecule, observed, maxMatches=1000)
    result["selected_native_rmsd_A"] = rmsd
    result["rmsd_metric"] = "Symmetry-aware heavy atoms in original1H1S frame; no ligand fitting"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-directory", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_completed_run(args.audit_directory, args.reference, args.reference_sha256)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
