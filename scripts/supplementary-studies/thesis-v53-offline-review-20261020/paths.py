"""Inventory A/B/C from frozen execution receipts and bounded source inspection.

This generator neither starts the old reproducers nor imports campaign scripts.
It verifies compact evidence and current repository bytes, then reports the
earlier A executions separately from documented, unexecuted B/C commands.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STUDY = Path("results/supplementary-studies/thesis-v53-offline-review-20261020")
INPUT = STUDY / "inputs/reproduction"
CONFIRMATION = Path("results/supplementary-studies/thesis-v49-confirmation-20261019")
ALLOWED = {"documented", "inputs_verified", "executed_pass", "executed_fail", "blocked"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Repository evidence path escapes the checkout")
    return path


def verify_record(root, row, path_key="path"):
    path = repository_file(root, row[path_key])
    if sha(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
        raise ValueError("Bound evidence changed: " + row[path_key])


def verify_receipts(repo, receipts, inspection, archive):
    """Validate evidence, without treating verification as another A execution."""
    source_count = 0
    for run in receipts["runs"]:
        if run["status"] != "executed_pass" or run["exit_code"] != 0:
            raise ValueError("A execution receipt must record a successful command")
        if not run["outputs"] or run["matching_scientific_files"] != len(run["outputs"]):
            raise ValueError("A output count does not match exact file evidence")
        if run["hardware_or_network_operations"] != 0 or run["resampling_performed"] is not False:
            raise ValueError("A receipt exceeds the compact offline scope")
        for row in run["code"] + run["inputs"]:
            verify_record(repo, row)
            source_count += 1
        for row in run["outputs"]:
            if row["byte_equal"] is not True:
                raise ValueError("A output was not byte-equal")
            verify_record(repo, row, "reference_path")
        log = repository_file(repo, str(INPUT / run["log"]["path"]))
        if sha(log) != run["log"]["sha256"]:
            raise ValueError("Execution log projection changed")
    bundle = next(row for row in archive["files"] if row["role"] == "campaign_git_bundle")
    for key in ("sha256", "bytes", "filename"):
        if inspection["campaign_bundle"][key] != bundle[key]:
            raise ValueError("Campaign bundle differs from the canonical archive reference")
    if inspection["campaign_commit"] != archive["source_campaign_commit"]:
        raise ValueError("Campaign source commit differs from the archive reference")
    if inspection["payload_manifest"]["sha256"] != archive["archive_integrity"]["archive_member_manifest_sha256"]:
        raise ValueError("Campaign payload manifest differs from the archive reference")
    for source in inspection["sources"]:
        member = source["payload_manifest_record"]
        if (source["path"], source["sha256"], source["bytes"]) != (
            member["path"], member["sha256"], member["bytes"]
        ) or source["bundle_and_manifest_bytes_match"] is not True:
            raise ValueError("Named campaign source is not manifest-bound")
    return source_count


def validate_routes(routes):
    for route in routes:
        if route["status"] not in ALLOWED:
            raise ValueError("Invalid reproduction-path status")
        if route["category"] in {"B", "C"}:
            if route["executed_in_this_audit"] or route["status"].startswith("executed_"):
                raise ValueError("B/C execution is outside this audit")
        if route["category"] == "A":
            if route["status"] != "executed_pass" or not route.get("execution_receipt"):
                raise ValueError("A pass requires its recorded execution receipt")
        if not route["source_files"] or not route["inputs"] or not route["expected_controls"]:
            raise ValueError("Reproduction route lacks sources, inputs or controls")


def build(repo_root: Path, output: Path) -> dict:
    repo, output = Path(repo_root), Path(output)
    if output.resolve().is_relative_to((repo / INPUT).resolve()):
        raise ValueError("Output must not overwrite reproduction inputs")
    receipt_path = repo / INPUT / "executed_A.json"
    inspection_path = repo / INPUT / "source_inspection.json"
    binding_path = repo / STUDY / "inputs/binding/source_bindings.json"
    archive_path = repo / CONFIRMATION / "ARCHIVE_REFERENCE.json"
    receipts = json.loads(receipt_path.read_text())
    inspection = json.loads(inspection_path.read_text())
    binding = json.loads(binding_path.read_text())
    archive = json.loads(archive_path.read_text())
    checked = verify_receipts(repo, receipts, inspection, archive)
    sources = {row["path"]: row for row in inspection["sources"]}

    def campaign_source(path):
        row = sources[path]
        return {
            "root": "confirmation_campaign",
            "path": path, "sha256": row["sha256"], "bytes": row["bytes"],
            "commit": inspection["campaign_commit"],
            "evidence": str(INPUT / "source_inspection.json"),
            "payload_manifest_pointer": row["payload_manifest_pointer"],
            "source_only_inspected": True,
        }

    routes = []
    for index, run in enumerate(receipts["runs"]):
        routes.append({
            "id": run["id"], "category": "A", "status": run["status"],
            "executed_in_this_audit": True,
            "reexecuted_by_this_inventory_generator": False,
            "scope": run["scope"],
            "source_files": run["code"], "inputs": run["inputs"],
            "recorded_argv": run["argv"],
            "command_root": "RESULTS_ROOT",
            "reproduction_command": (
                "python -I -B scripts/split-inference/reproduce.py --output NEW_OUTPUT "
                "--publication mlsys-r22 --numeric-only --verify"
                if run["id"] == "A_deployment_tables"
                else "python -I -B scripts/supplementary-studies/thesis-v49-confirmation-20261019/reproduce.py "
                "--inputs results/supplementary-studies/thesis-v49-confirmation-20261019/inputs --output NEW_OUTPUT"
            ),
            "execution_receipt": str(INPUT / "executed_A.json") + f"#/runs/{index}",
            "execution_log": str(INPUT / run["log"]["path"]),
            "exit_code": run["exit_code"],
            "observed_environment": run["environment"],
            "environment_requirements": (
                "The recorded Python 3.12.3 environment reproduces the checked-in bytes. "
                "Main --numeric-only generation is stdlib; --verify also exercises existing scientific-dependency checks. "
                "v49 reads saved bootstrap arrays with NumPy>=1.22,<3 (recorded 1.26.4). "
                "No package installation is part of this command inventory."
            ),
            "access_requirements": ["Published compact repository inputs", "Existing compatible Python environment",
                                    "Fresh writable external output directory"],
            "expected_controls": run["controls"],
            "observed_result": {
                "matching_scientific_files": len(run["outputs"]),
                "all_recorded_reference_files_hash_verified_now": True,
                "original_output_bytes_compared_after_execution": True,
                "outputs": run["outputs"],
                "new_prediction_evaluations": 0, "new_bootstrap_resamples": 0,
                "new_acquisitions": 0, "raw_waveform_integrations": 0,
            },
            "limits": [
                "This PASS covers the recorded compact numerical command and file set.",
                "It does not execute individual predictions, raw signals or physical acquisition.",
                "No PDF/SVG/PNG rendering was requested for A_deployment_tables in this audit.",
            ],
        })

    format_checks = binding["prediction_format_checks"]
    prediction_bindings = {}
    for key in ("candidate_predictions", "reference_predictions", "replay_request"):
        row = binding["sources"][key]
        prediction_bindings[key] = {
            "location": row["location"], "source_sha256": row["source_sha256"],
            "source_bytes": row["source_bytes"],
            "evidence": str(STUDY / "inputs/binding/source_bindings.json") + f"#/sources/{key}",
        }
    prediction_inventory = "confirmation_payload:/evidence/quality_prediction_inventory.json"
    common_external = [
        "Private bound preservation archive or readable mirror and its original payload manifest",
        "Path mapping in an isolated writable copy; no in-place writes to preserved originals",
    ]
    routes.append({
        "id": "B_prediction_input_inspection", "category": "B", "status": "inputs_verified",
        "executed_in_this_audit": False,
        "input_inspection_executed_in_this_audit": True,
        "execution_flag_scope": "False means no metric/waveform derivation was executed; the bounded input inspection was performed.",
        "scope": "Limited hash/JSON and paired image-ID checks for the exact MobileNet b135 candidate and CPU reference.",
        "source_files": [{"path": str(STUDY / "inputs/binding/source_bindings.json"),
                          "sha256": sha(binding_path), "role": "Recorded bounded inspection"}],
        "inputs": prediction_bindings,
        "source_cli": "Read only the three manifest-bound JSON files; no metric evaluator entry point was invoked.",
        "environment_requirements": ["Python standard-library hashlib/json for the recorded input inspection"],
        "access_requirements": common_external,
        "expected_controls": format_checks,
        "observed_result": format_checks,
        "limits": [
            "All 5,000 paired image IDs and request order were checked.",
            "Record-schema fields were inspected at records[0] in each prediction file, not exhaustively for every record.",
            "No top1/top5 mean, COCO metric, paired Full/Split interval or new bootstrap was computed.",
            "This limited input check does not close the missing historical evaluator-execution binding.",
        ],
    })
    routes.append({
        "id": "B_saved_prediction_metrics", "category": "B", "status": "documented",
        "executed_in_this_audit": False,
        "scope": "Recompute metrics from saved predictions; classification means or official COCOeval on final stored detections.",
        "source_files": [campaign_source("scripts/quality_offline_cocoeval.py")],
        "inputs": [prediction_inventory, "Hash-bound candidate/reference JSON records with image IDs",
                   "Saved ground truth for detection, category/score/box fields, and selected historical metric metadata"],
        "source_cli": "python scripts/quality_offline_cocoeval.py",
        "cli_semantics": "No argparse options; OUT is the parent of scripts/. Inventory comes from OUT/evidence/quality_prediction_inventory.json.",
        "command_root": "An isolated, correctly mapped confirmation-campaign copy",
        "environment_requirements": ["Python", "NumPy", "pycocotools with its COCOeval source/version recorded"],
        "access_requirements": common_external,
        "expected_controls": [
            "Input SHA256 equality before/after; candidate/reference image order and converted ground truth must match.",
            "Uses saved final detections without new NMS or inference; comparison is limited to the selected 14.",
            "Would write quality_official tables and per-case ground truth, predictions, stdout and precision/recall arrays.",
        ],
        "limits": [
            "Only the limited MobileNet pair input inspection above was performed; the complete 14-case input closure was not checked.",
            "No new metric run occurred. A future run is new numerical evidence, not proof of historical evaluator identity.",
        ],
    })
    routes.append({
        "id": "B_paired_quality_bootstrap", "category": "B", "status": "documented",
        "executed_in_this_audit": False,
        "scope": "Original campaign entry for direct Split-minus-Full paired quality intervals.",
        "source_files": [campaign_source("scripts/history_paired_quality.py")],
        "inputs": [prediction_inventory, "Exactly matched selected Full/Split prediction records and ground truth",
                   "evidence/history/quality_metrics_for_paired_analysis.py", "Saved frozen_plan.json and bootstrap arrays when present"],
        "source_cli": "python scripts/history_paired_quality.py [--workers INTEGER] [--models MODEL ...]",
        "cli_semantics": "Defaults workers=4 and all inventory models; ROOT is the parent of scripts/. Hardcoded original evaluator source is used only if its campaign copy is absent.",
        "command_root": "An isolated, explicitly mapped confirmation-campaign copy",
        "environment_requirements": ["Python", "NumPy", "pycocotools", "Bound original evaluator source and dependencies"],
        "access_requirements": common_external,
        "expected_controls": [
            "Exactly 5,000 unique image IDs with identical Full/Split order and ground truth.",
            "B=1,000, hash-derived seed, NumPy PCG64; ordinary 2.5/97.5 percentiles with linear interpolation.",
            "Point metrics must match saved points within 1e-10; no subtraction of CPU-relative interval endpoints.",
            "No new resampling is authorized by this audit; only A consumes already saved absolute bootstrap values.",
        ],
        "limits": [
            "Not a safe generic read-only replay: it writes plans/arrays/results and can start 1,000 new bootstrap replicates.",
            "A missing evaluator copy triggers a read from HISTORICAL_HOME/ONNX-Splitpoint-Tool/onnx_splitpoint_tool/quality_metrics.py.",
            "For detection a complete saved bootstrap may be reused after plan checks; classification computes draws anew. This command was not run.",
        ],
    })
    routes.append({
        "id": "B_raw_interval_rederivation", "category": "B", "status": "documented",
        "executed_in_this_audit": False,
        "scope": "Recompute an inner pipeline interval and conditional energy from an existing collector trace.",
        "source_files": [campaign_source("scripts/collector_interval/analyze_interval.py"),
                         campaign_source("evidence/energy_supplement_20261019/electrical/evaluate_attempt.py")],
        "inputs": [
            "Per-attempt runtime timing JSON and clock_probes.jsonl",
            "collector_storage/fast_firmware.parquet, runtime_interval_events.jsonl, packet anchors and stream origin",
            "command_window_markers.json, source lifecycle and acquisition_manifest.json",
            "Hash-bound electrical-model JSON and coefficient source; evaluate_attempt also needs an expected identity JSON",
        ],
        "source_cli": (
            "python scripts/collector_interval/analyze_interval.py --storage COPY_STORAGE "
            "--timing COPY_TIMING --clock-probes COPY_PROBES --electrical-model COPY_MODEL --output NEW_JSON"
        ),
        "additional_documented_cli": (
            "python evidence/energy_supplement_20261019/electrical/evaluate_attempt.py "
            "--attempt COPY_ATTEMPT --expected COPY_EXPECTED"
        ),
        "command_root": "An isolated writable archive copy with source-bound helper/exporter layout",
        "environment_requirements": [
            "Python standard library and adjacent clock_mapping.py",
            "The bound collector/target/release/trace_export binary, with its compatible archived build/runtime",
            "evaluate_attempt dynamically loads its bound source helpers; their complete closure is external",
        ],
        "access_requirements": common_external,
        "expected_controls": [
            "N_completed equals measured_submitted; warmup/measurement drained; runtime PID/UID/start/end agree.",
            "Declared makespan equals timer boundaries; rate=N_completed/pipeline_makespan_including_drain_s.",
            "Exported sample row count equals packet-anchor total_rows; row_index is contiguous.",
            "Preserve conditional estimates, missing uncertainty terms and valid_for_final_energy=false; no new physical qualification.",
        ],
        "write_behavior": "analyze_interval invokes trace_export and writes fast_firmware_samples.csv INSIDE --storage, then writes --output. Never point it at the immutable original storage.",
        "limits": [
            "Source, exact CLI and manifest hashes were inspected; no full raw trace integration was started.",
            "No raw parquet payload, exporter execution or full per-attempt dependency closure was validated in this task.",
            "The electrical evaluator was only source-inspected, not imported or invoked.",
        ],
    })
    routes.append({
        "id": "C_physical_campaign", "category": "C", "status": "documented",
        "executed_in_this_audit": False,
        "scope": "Physical timed acquisition and separately bounded energy supplements, inventoried only.",
        "source_files": [campaign_source("scripts/run_timed_campaign.py"),
                         campaign_source("scripts/run_energy_supplement.py")],
        "inputs": [
            "Frozen plan plus SHA256, qualified-path mapping, hardware registry and SSH/runtime contracts",
            "Compiled HEF/DXNN/TRT models and model/runtime hashes, input images and owning setup",
            "Collector bridge/entry/binary manifests, firmware and electrical models",
            "For supplements: frozen policy/index, preserved primary resolution, readiness, previous resolution if applicable, and root amendment with SHA256",
        ],
        "source_cli": (
            "python scripts/run_timed_campaign.py --execute --plan PLAN --plan-sha256 SHA256 "
            "--qualified-paths QUALIFIED_PATHS --output NEW_OUTPUT --registry REGISTRY "
            "--collector-entry COLLECTOR_ENTRY --electrical-models ELECTRICAL_MODELS"
        ),
        "additional_documented_cli": (
            "python scripts/run_energy_supplement.py --execute --output FROZEN_INDEX_DIRECTORY "
            "--amendment AMENDMENT --amendment-sha256 SHA256"
        ),
        "cli_semantics": "Each controller requires exactly one of --validate-only/--execute. Supplement --execute reads the existing attempt_index.json; it rejects fresh policy/previous-resolution arguments.",
        "environment_requirements": [
            "Original controller/runtime helper closure and source-bound execution environment",
            "SSH access, accelerator drivers/SDKs, TensorRT, owning accelerator hardware and u.RECS collector hardware",
            "Compatible compiled models, private inputs, registry and collector binaries",
        ],
        "access_requirements": ["Private campaign and external dependency archives", "Authorized physical setups and execution resources"],
        "expected_controls": [
            "Source-bound plan/setup/UID/compiled model identities and complete drain accounting.",
            "Existing primary/supplement identities and provenance stay separate; this inventory does not promise a new run will reproduce old samples.",
            "The stored compact controls remain 70 primary A, 68 B, 0 C; they do not authorize new acquisition or physical qualification.",
        ],
        "write_behavior": "Even --validate-only creates output/index/validation artifacts; neither mode was run.",
        "limits": [
            "C is a documented interface, not an executable readiness or parity certification.",
            "No inference, model compilation, hardware/collector access, environment update or validation-only controller invocation occurred.",
            "The full hardware dependency closure is not bundled in this compact result repository.",
        ],
    })
    validate_routes(routes)
    report = {
        "schema": "thesis-v53/reproduction-paths-v1",
        "status": "completed_with_limits",
        "root_legend": {
            **receipts["root_legend"],
            "confirmation_campaign": "Source at the explicitly bound campaign Git commit from the verified bundle",
            "confirmation_payload": "Payload root named by the canonical ARCHIVE_REFERENCE.json",
            "HISTORICAL_HOME": "Recorded historical source-home prefix; not assumed to exist on the current host",
            "COPY_*": "Source-bound files in an isolated writable archive copy; never the preservation original",
            "NEW_*": "Fresh output path supplied by a future caller",
        },
        "execution_semantics": "Only A commands were executed. This compact inventory revalidates their receipts and repository hashes; it does not rerun A or execute B/C.",
        "source_inputs": [
            {"path": str(path.relative_to(repo)), "sha256": sha(path), "bytes": path.stat().st_size}
            for path in (receipt_path, inspection_path, binding_path, archive_path)
        ],
        "archive_dependencies": {
            "reference": str(CONFIRMATION / "ARCHIVE_REFERENCE.json"),
            "campaign_commit": inspection["campaign_commit"],
            "campaign_bundle": inspection["campaign_bundle"],
            "payload_manifest": inspection["payload_manifest"],
            "source_inspection": str(INPUT / "source_inspection.json"),
            "full_raw_archive_rehashed_in_this_task": False,
        },
        "routes": routes,
        "summary": {
            "executed_A_commands": len(receipts["runs"]),
            "byte_equal_A_files": sum(len(run["outputs"]) for run in receipts["runs"]),
            "A_output_files": {run["id"]: len(run["outputs"]) for run in receipts["runs"]},
            "A_code_and_input_hash_records_rechecked": checked,
            "manifest_bound_campaign_source_files": len(sources),
            "B_metric_or_waveform_runs": 0, "new_bootstrap_resamples": 0,
            "C_runs_including_validate_only": 0,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "reproduction_paths.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return {
        "status": report["status"], "outputs": ["reproduction_paths.json"],
        "summary": report["summary"],
        "source_inputs": report["source_inputs"],
        "limits": [
            "A covers only the recorded numerical commands and file sets.",
            "B has bounded source/input inspection only; no new quality metric, raw integration or bootstrap.",
            "C is documented only; its hardware and dependency closure was not executed or certified.",
        ],
    }
