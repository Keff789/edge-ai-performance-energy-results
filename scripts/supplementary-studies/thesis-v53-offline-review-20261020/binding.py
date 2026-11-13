#!/usr/bin/env python3
"""Audit the selected MobileNet evaluation's provenance without evaluating quality.

Normal builds use compact, dated source projections. Optional original verification
checks their complete-file hashes and JSON pointers/source lines; it never imports
the evaluator, loads a model, computes a metric, or starts a bootstrap.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

STUDY = "results/supplementary-studies/thesis-v53-offline-review-20261020"
INPUT = f"{STUDY}/inputs/binding/source_bindings.json"
TARGET_UID = "native|mobilenet_v3_large|DeepX|deepx_to_trt|b135"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pointer(value: Any, path: str) -> Any:
    """Resolve an RFC 6901 pointer, including the empty document pointer."""
    for token in path.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def normalize(value: Any, substitutions: dict[str, str]) -> Any:
    if isinstance(value, str):
        for original in sorted(substitutions, key=len, reverse=True):
            replacement = substitutions[original]
            value = value.replace(original, replacement)
        return value
    if isinstance(value, list):
        return [normalize(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item, substitutions) for key, item in value.items()}
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def archived_binding_inventory(data: dict[str, Any]) -> dict[str, Any]:
    """Count recorded archive bindings; do not claim a new all-UID evaluation."""
    projection = data["sources"]["historical_evaluator_audit"]["projection"]
    expected = data["sources"]["identity_runtime"]["projection"]["/selected_count"]
    rows = []
    session_keys = {
        "base_run_manifest_execution_sessions_tool_build_critical_module_hash":
            "/historical_evaluator/historical_sessions",
        "supplement_run_manifest_execution_sessions_tool_build_critical_module_hash":
            "/historical_evaluator/historical_supplement_sessions",
    }
    for index in range(expected):
        prefix = f"/rows/{index}/"
        required = ("uid", "historical_evaluator_binding",
                    "historical_evaluator_source_sha256", "request_eval_run_id")
        require(all(prefix + key in projection for key in required),
                "Archived selected-binding inventory is incomplete")
        row = {key: projection[prefix + key] for key in required}
        status = row["historical_evaluator_binding"]
        digest = row["historical_evaluator_source_sha256"]
        if digest is not None:
            require(status in session_keys, "Unexpected archived evaluator-binding category")
            sessions = projection[session_keys[status]]
            require(any(session["quality_metrics_sha256"] == "sha256:" + digest
                        for session in sessions),
                    "Archived evaluator hash differs from its recorded session inventory")
        else:
            require(status == "contemporaneous_evaluator_hash_unavailable_for_20261010_evaluation",
                    "Unexpected archived evaluator gap category")
        rows.append(row)
    require(len({row["uid"] for row in rows}) == expected,
            "Duplicate UID in archived selected-binding inventory")
    missing = [row["uid"] for row in rows
               if row["historical_evaluator_source_sha256"] is None]
    require(missing == [TARGET_UID], "Archived missing-evaluator inventory changed")
    return {
        "selected_configuration_count": len(rows),
        "recorded_evaluator_source_bound_count": len(rows) - len(missing),
        "recorded_evaluator_source_unbound_count": len(missing),
        "unbound_uids": missing,
        "binding_categories": dict(sorted(Counter(
            row["historical_evaluator_binding"] for row in rows).items())),
        "records": rows,
        "source_sha256": data["sources"]["historical_evaluator_audit"]["source_sha256"],
        "source_as_of": projection["/created_at"],
        "scope": "Counts and source/session-hash correspondence from all 14 records in the original archived audit. This audit follows the selected b135 chain in depth; it does not independently re-audit the other 13 executions, their dependencies, or all 450 deployments.",
    }


def validate(data: dict[str, Any]) -> dict[str, Any]:
    """Check cross-source identity and provenance edges, not numerical parity."""
    sources = data["sources"]
    inventory = archived_binding_inventory(data)

    def get(name: str, path: str = "") -> Any:
        return sources[name]["projection"][path]

    def digest(name: str) -> str:
        return sources[name]["source_sha256"]

    for name, source in sources.items():
        value = source["source_sha256"]
        require(len(value) == 64 and set(value) <= set("0123456789abcdef"),
                f"{name}: invalid source hash")
        require(source["source_bytes"] > 0, f"{name}: empty source")
        path = Path(source["location"]["path"])
        require(not path.is_absolute() and ".." not in path.parts,
                f"{name}: source location must be relative")

    archived = get("historical_evaluator_audit", "/rows/0")
    receipt = get("central_receipt")
    handoff = get("source_handoff")
    identity = sources["identity_runtime"]["projection"]
    full_uid = identity["/entries/0/uid"]
    require(full_uid.split("|")[1:] == [
        identity[f"/entries/0/{key}"] for key in ("model", "setup", "backend", "case")
    ], "Full UID components differ from manifest identity")
    require(identity["/entries/0/historical_current_result_row/case_uid"]
            == full_uid.replace("native|", "native|revision3|", 1),
            "Historical revision3 UID differs")
    require(full_uid == TARGET_UID, "Full selected UID differs")
    require(archived["uid"] == full_uid
            == get("prediction_inventory", "/rows/0/uid")
            == get("identity_runtime", "/entries/0/uid"),
            "Archive members do not identify the same full UID")
    require(archived["original_metric"]["source_sha256"]
            == get("identity_runtime", "/entries/0/metric_sources/quality")["expected_sha256"]
            == digest("original_quality_result"), "Selected quality source hash differs")

    for source in ("replay_request", "original_runtime_request"):
        for request_key, row_key in (("model_id", "model"), ("case_id", "case"),
                                     ("setup_id", "setup_id"), ("eval_run_id", "eval_run_id")):
            require(get(source, f"/{request_key}")
                    == get("original_quality_result", f"/rows/0/{row_key}"),
                    f"{source}: {request_key} differs from selected result")

    quality = get("original_quality_result", "/rows/0/task_quality_gate")
    require(digest("replay_request") == receipt["source_request_sha256"]
            == handoff["request_sha256"] == archived["request_expected_sha256"]
            == quality["quality_input_request"]["source_request_sha256"]
            == get("prediction_inventory", "/rows/0/request_sha256_expected"),
            "Central replay request hash differs across source chain")
    require(digest("original_runtime_request")
            == get("original_quality_result", "/rows/0/source_request_sha256")
            == get("original_quality_result",
                   "/rows/0/native_split_quality_binding/central_quality_selection")["source_request_sha256"],
            "Original runtime request binding differs")
    require(digest("original_runtime_request") != digest("replay_request"),
            "Original runtime request was conflated with later central replay")
    require(receipt["result_sha256"] == digest("central_result")
            == get("original_quality_result",
                   "/rows/0/postmeasurement_dataset_quality_join/central_result")["sha256"],
            "Central result hash differs")
    require(receipt["source_handoff_sha256"] == digest("source_handoff"),
            "Source handoff hash differs")
    require(quality["evaluation_fingerprint"]
            == get("central_result", "/evaluation_fingerprint"),
            "Selected result does not preserve the central evaluation fingerprint")
    require(quality["primary"] == get("central_result", "/primary"),
            "Selected result's copied quality fields differ from central result")
    require(get("central_result", "/primary")["bootstrap_engine"]
            == archived["factory_recorded_in_result"],
            "Recorded evaluator factory differs")
    require(receipt["at"] == archived["historical_central_evaluation_receipt"]["at"],
            "Central evaluation date differs")
    require(archived["historical_central_evaluation_receipt"]["file"]["sha256"]
            == digest("central_receipt"), "Archived central receipt differs")

    require(digest("candidate_predictions")
            == get("replay_request", "/candidate")["sha256"]
            == get("prediction_inventory", "/rows/0/candidate")["sha256"],
            "Candidate prediction bytes differ")
    require(digest("reference_predictions")
            == receipt["reference_sha256"]
            == get("replay_request", "/reference/reference_sha256")
            == get("prediction_inventory", "/rows/0/reference")["sha256"],
            "Reference prediction bytes differ")
    require(get("central_result", "/reference_identity")
            == f"runner_reference_artifact:{digest('reference_predictions')}",
            "Reference identity differs")
    formats = data["prediction_format_checks"]
    require(formats["reference_records"] == formats["candidate_records"]
            == get("replay_request", "/record_count")
            == get("central_result", "/n"), "Prediction record counts differ")
    require(formats["paired_image_order_matches"] and formats["request_image_order_matches"],
            "Recorded prediction format check did not establish paired order")

    manifest = sources["payload_manifest"]["projection"].values()
    for source in sources.values():
        if source["location"]["root"] == "confirmation_payload":
            matches = [row for row in manifest if row["path"] == source["location"]["path"]]
            require(len(matches) == 1 and matches[0]["sha256"] == source["source_sha256"]
                    and matches[0]["bytes"] == source["source_bytes"],
                    "Archive member differs from bound payload manifest")
    archive_ref = get("archive_reference")
    require(archive_ref["archive_integrity"]["archive_member_manifest_sha256"]
            == digest("payload_manifest"), "Archive payload manifest binding differs")
    resolver = sources["revision3_resolver"]["projection"]
    for name in ("original_quality_result", "central_receipt", "replay_request",
                 "source_handoff", "central_result", "candidate_predictions",
                 "evaluator_source", "service_source", "statistics_helper"):
        source = sources[name]
        require(any(row.get("canonical_path") == source["location"]["path"]
                    and row.get("sha256") == source["source_sha256"] for row in resolver.values()),
                f"{name}: canonical resolver binding differs")
    require(any(row.get("expected_sha256") == receipt["source_commands_sha256"]
                and "unresolved" in row.get("resolution", "") for row in resolver.values()),
            "Missing command-file evidence is not bound to the receipt")
    require(digest("evaluator_source") == archived["corroborating_evaluator_source_sha256"],
            "Inspected evaluator does not match preserved corroborating source")
    require(archived["historical_evaluator_source_sha256"] is None,
            "Input now contains an evaluator binding: review and update this limited audit")

    return {"uid": full_uid, "source_count": len(sources),
            "cross_source_checks": "passed",
            "archived_selected_configuration_count": inventory["selected_configuration_count"],
            "archived_evaluator_source_bound_count": inventory["recorded_evaluator_source_bound_count"],
            "archived_evaluator_source_unbound_count": inventory["recorded_evaluator_source_unbound_count"],
            "quality_recalculated": False, "bootstrap_recalculated": False}


def verify_originals(data: dict[str, Any], roots: dict[str, Path]) -> list[dict[str, str]]:
    """Verify only the explicit projected sources under caller-supplied roots.

    confirmation_payload may be a small member cache arranged as evidence/*.json;
    this routine does not open, extract or download an archive.
    """
    checked = []
    for name, source in data["sources"].items():
        location = source["location"]
        require(location["root"] in roots, f"Missing root: {location['root']}")
        raw = (roots[location["root"]] / location["path"]).read_bytes()
        require(sha256(raw) == source["source_sha256"] and len(raw) == source["source_bytes"],
                f"{name}: original file hash/size differs")
        if source["kind"] == "json_projection":
            original = json.loads(raw)
            for key, value in source["projection"].items():
                require(normalize(pointer(original, key), data["path_normalization"]) == value,
                        f"{name}: original JSON pointer differs: {key}")
        else:
            lines = raw.decode().splitlines(keepends=True)
            for excerpt in source["excerpts"]:
                text = "".join(lines[excerpt["first_line"] - 1:excerpt["last_line"]])
                require(normalize(text, data["path_normalization"]) == excerpt["text"],
                        f"{name}: original source excerpt differs")
        checked.append({"source": name, "status": "hash_and_projection_verified"})
    return checked


def build(repo_root: Path, output: Path) -> dict[str, Any]:
    raw = (repo_root / INPUT).read_bytes()
    data = json.loads(raw)
    checks = validate(data)
    sources = data["sources"]
    archived = sources["historical_evaluator_audit"]["projection"]["/rows/0"]
    receipt = sources["central_receipt"]["projection"][""]
    central = sources["central_result"]["projection"]
    request = sources["replay_request"]["projection"]
    archive_ref = sources["archive_reference"]["projection"][""]
    report = {
        "schema": "thesis-v53/mobile-evaluator-binding/v1",
        "status": "completed_with_limits",
        "historical_evaluator_binding_closed": False,
        "uid": checks["uid"],
        "scope": "The selected MobileNetV3-Large b135 configuration; no parity claim for the 450 deployments.",
        "input": {"path": INPUT, "sha256": sha256(raw)},
        "archived_selected_binding_inventory": archived_binding_inventory(data),
        "archive_context": {
            "payload_root": archive_ref["archive_payload_root"],
            "archive": next(item for item in archive_ref["files"] if item["role"] == "archive"),
            "payload_manifest_sha256": sources["payload_manifest"]["source_sha256"],
            "campaign_commit": archive_ref["source_campaign_commit"],
            "full_archive_hash_rechecked_in_this_audit": False,
            "member_verification": "The three exact evidence members were checked against the bound payload manifest; the earlier whole-archive verification is retained as source metadata.",
        },
        "historical_evaluation": {
            "at": receipt["at"],
            "eval_run_id": request["/eval_run_id"],
            "source_run_id": request["/source_run_id"],
            "setup_id": request["/setup_id"],
            "original_runtime_request_sha256": sources["original_runtime_request"]["source_sha256"],
            "central_replay_request_sha256": sources["replay_request"]["source_sha256"],
            "request_id": central["/request_id"],
            "receipt_sha256": sources["central_receipt"]["source_sha256"],
            "result_sha256": sources["central_result"]["source_sha256"],
            "evaluation_fingerprint": central["/evaluation_fingerprint"],
            "recorded_factory": archived["factory_recorded_in_result"],
            "recorded_algorithm_version": central["/algorithm_version"],
            "execution_location": central["/execution_location"],
            "execution_device": central["/execution_device"],
            "worker_model": central["/worker_model"],
            "recorded_statistics": request["/statistics"],
            "recorded_seed_schema": central["/seed_schema"],
            "selected_quality_source": archived["original_metric"],
            "historical_values_preserved": archived["quality_metrics"],
            "source_chain": [
                "identity_runtime -> original_quality_result (full UID and source hash)",
                "original_quality_result.task_quality_gate.quality_input_request -> replay_request",
                "original_quality_result.postmeasurement_dataset_quality_join -> central_result",
                "central_receipt -> replay_request, central_result, source_handoff and reference_predictions",
                "replay_request -> candidate_predictions and reference_predictions",
            ],
        },
        "corroborating_sources": {
            name: {"source_sha256": sources[name]["source_sha256"],
                   "location": sources[name]["location"],
                   "execution_binding": sources[name]["execution_binding"]}
            for name in ("evaluator_source", "service_source", "statistics_helper")
        },
        "dispatch_and_helpers": {
            "recorded_factory": "onnx_splitpoint_tool.quality_metrics:classification_quality_evaluator",
            "inspected_factory_target": "_ClassificationAccuracyEvaluator",
            "inspected_numeric_dependency": "NumPy",
            "inspected_service_behavior": "The classification task selects the factory; importlib loads it and forwards metric_gate_config. The statistics helper records a numerical environment for its own cache keys.",
            "historical_execution_binding": "No contemporaneous receipt binds these evaluator, service or helper bytes, their loaded dispatch, Python version or NumPy version to the 2026-10-10 request.",
            "classification_scope": "COCO evaluator and pycocotools version questions are not applicable to this classification UID.",
        },
        "open_fields": {
            "evaluation_bound_evaluator_sha256": None,
            "evaluation_bound_service_sha256": None,
            "evaluation_bound_helper_sha256": None,
            "evaluation_bound_python_version": None,
            "evaluation_bound_numpy_version_or_hash": None,
            "request_bound_producer_runner_bytes_status": archived["exact_runner_bytes_status"],
            "producer_runner_search_status_source": {
                "source": "historical_evaluator_audit",
                "as_of": sources["historical_evaluator_audit"]["projection"]["/created_at"],
                "new_runner_search_performed": False,
            },
            "request_bound_producer_runner_sha256": archived["request_bound_runner_sha256"],
            "referenced_command_manifest": {
                "path": receipt["source_commands"], "sha256": receipt["source_commands_sha256"],
                "status": "not present in canonical payload; original resolver explicitly marks unresolved",
            },
        },
        "evidence_limits": [
            "The original runtime request and later central replay are distinct. Earlier campaign-session source hashes do not bind the later independent evaluation.",
            "Preserved evaluator bytes and the recorded factory/algorithm name corroborate implementation semantics but do not prove which source bytes executed.",
            "Matching quality values, current code or a new evaluation cannot retroactively establish the missing execution-to-source binding.",
            "The archived request-bound producer runner hash and the later management evaluator are separate provenance questions.",
        ],
        "next_required_evidence": "A contemporaneous receipt or log for replay request "
        + sources["replay_request"]["source_sha256"]
        + " / evaluation fingerprint " + central["/evaluation_fingerprint"]
        + " binding the loaded evaluator, service/helper source hashes and Python/NumPy environment; "
        "the referenced DX56_QUALITY_COMMANDS.json may supply a further source path but its hash alone does not close the binding.",
        "prediction_inputs": data["prediction_format_checks"],
        "bounded_search": data["bounded_search"],
        "verification": checks,
        "source_evidence": {
            name: {"location": source["location"], "source_sha256": source["source_sha256"],
                   "source_bytes": source["source_bytes"],
                   "input_pointer": f"/sources/{name}"}
            for name, source in sources.items()
        },
        "reproduction_note": "This output rechecks the compact source chain and reproduces the audit conclusion. Original-file verification is a separate optional operation; original evaluator execution is not performed.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "mobilenet_evaluator_binding.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return {"status": report["status"], "uid": checks["uid"],
            "historical_evaluator_binding_closed": False,
            "outputs": ["mobilenet_evaluator_binding.json"], "verification": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-originals", action="store_true")
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--confirmation-payload", type=Path)
    args = parser.parse_args()
    if args.verify_originals:
        if args.canonical_root is None or args.confirmation_payload is None:
            parser.error("--verify-originals requires --canonical-root and --confirmation-payload")
        data = json.loads((args.repo_root / INPUT).read_text())
        checked = verify_originals(data, {
            "canonical_archive": args.canonical_root,
            "confirmation_payload": args.confirmation_payload,
            "results_repository": args.repo_root,
        })
        print(json.dumps({"original_source_verification": checked}, indent=2))
    elif args.canonical_root or args.confirmation_payload:
        parser.error("External roots are used only with --verify-originals")
    print(json.dumps(build(args.repo_root, args.output), indent=2))


if __name__ == "__main__":
    main()
