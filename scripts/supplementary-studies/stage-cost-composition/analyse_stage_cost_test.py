#!/usr/bin/env python3
"""Offline-only evaluator for stored independent stage measurements.

Accepted schema is documented in validation fixtures. The evaluator opens only
measurements/P and measurements/C first and persists their Oracle predictions.
It then opens only PC files with a matching persisted case/block prediction;
other PC labels remain unopened. It never imports a launcher or hardware module.
"""

import argparse
import csv
import json
from pathlib import Path
import re

from stage_cost_oracle import (MEASURED_COUNT, WARMUP_COUNT, ResourceDescriptor,
                               StageCapacity, completion_rates, predict_oracle,
                               compare_prediction, summarize)


IDENTITY_FIELDS = ("case_id", "config_id", "candidate_id", "implementation_id",
                   "input_recipe_id", "resource_descriptor_id")
BINDING_FIELDS = ("effective_input_sha256", "handoff_sha256", "artifact_binding_id")
METRICS = ("fps_P_core", "fps_C_core", "cP_ms", "cC_ms", "fps_Oracle_core",
           "fps_PC_core", "fps_PC_total", "signed_error_pct", "absolute_error_pct",
           "cycle_residual_ms")
COMMON_FIELDS = ["case_id", "config_id", "candidate_id", "block_id", "mode", "run_id",
                 "implementation_id", "runner_sha256", "input_recipe_id", "resource_descriptor_id",
                 "source_path", "source_scope", "run_status", "timing_valid", "input_valid",
                 "stage_contract_valid", "validity_status", "output_status", "output_pre_status",
                 "output_post_status", "task_valid", "state_status", "state_comparable",
                 "historical_join_status", "warmup_completed", "measured_completed", "requested",
                 "unique_request_ids", "drained", "timer_start_s", "timer_end_s",
                 "total_duration_s", "core_duration_s", "fps_core", "fps_total",
                 "fps_first_half", "fps_second_half", "drift_relative_pct", "drift_flag",
                 "configured_inflight", "observed_max_inflight", "completion_endpoint",
                 "handoff_dtype", "handoff_layout", "reasons", "state_notes"]
PREDICTION_FIELDS = ["case_id", "config_id", "candidate_id", "block_id", "implementation_id",
                     "input_recipe_id", "resource_descriptor_id", "P_run_id", "C_run_id",
                     "P_source_path", "C_source_path", "fps_P_core", "fps_C_core", "cP_ms",
                     "cC_ms", "cOracle_ms", "fps_Oracle_core", "predicted_bottleneck",
                     "state_comparable", "model"]
COMPARISON_FIELDS = ["record_type", "case_id", "config_id", "candidate_id", "block_id",
                     "P_run_id", "C_run_id", "PC_run_id", "fps_P_core", "fps_C_core",
                     "cP_ms", "cC_ms", "cOracle_ms", "fps_Oracle_core", "predicted_bottleneck",
                     "fps_PC_core", "fps_PC_total", "signed_error_pct", "absolute_error_pct",
                     "cycle_residual_ms", "within_10pct_band", "task_valid", "state_comparable",
                     "drift_flag", "group_id", "numerator_case_id", "denominator_case_id",
                     "predicted_ratio", "observed_ratio", "predicted_direction",
                     "observed_direction", "direction_agrees", "ratio_signed_error_pct", "notes"]


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, obj):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            clean = {key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict, tuple))
                     else value for key, value in row.items()}
            writer.writerow(clean)


def _cases(plan):
    cases = plan.get("cases", [])
    if isinstance(cases, dict):
        cases = [dict(value, case_id=key) for key, value in cases.items()]
    if not isinstance(cases, list):
        raise ValueError("PLAN.cases must be a list or mapping")
    result = {}
    for case in cases:
        key = case.get("case_id")
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("PLAN case identities must be unique nonempty case_id strings")
        case = dict(case)
        case["_expected_runner_sha256"] = plan.get("implementation", {}).get("sha256")
        result[key] = case
    return result


def _references(document):
    cases = document.get("cases", [])
    if isinstance(cases, dict):
        return cases
    if isinstance(cases, list):
        return {row["case_id"]: row for row in cases if isinstance(row, dict) and "case_id" in row}
    return {}


def _descriptor(plan, case):
    ident = case.get("resource_descriptor_id")
    objects = plan.get("resource_descriptors", {})
    if isinstance(objects, list):
        objects = {obj.get("resource_descriptor_id", obj.get("descriptor_id")): obj for obj in objects}
    raw = case.get("resource_descriptor", objects.get(ident, {}) if isinstance(objects, dict) else {})
    if not isinstance(raw, dict):
        raise ValueError("resource descriptor must be an object")
    if raw.get("resource_descriptor_id", raw.get("descriptor_id", ident)) != ident:
        raise ValueError("resource descriptor identity mismatch")
    handoff = raw.get("handoff", {})
    return ResourceDescriptor(ident, raw.get("prefix_inflight"), raw.get("fifo_depth"),
                              raw.get("batch_size"), raw.get("handoff_dtype", handoff.get("dtype")),
                              raw.get("handoff_layout", handoff.get("layout")),
                              raw.get("prefix_scope"), raw.get("consumer_scope"),
                              tuple(raw.get("shared_resources", [])))


def _binding_tuple(binding):
    return tuple(json.dumps(binding.get(field), sort_keys=True, separators=(",", ":"))
                 for field in BINDING_FIELDS)


def _binding_complete(binding):
    return (isinstance(binding, dict)
            and all(isinstance(binding.get(key), list) and 1 <= len(binding[key]) <= 8
                    and all(isinstance(value, str) and len(value) == 64
                            and all(char in "0123456789abcdefABCDEF" for char in value) for value in binding[key])
                    for key in BINDING_FIELDS[:2])
            and isinstance(binding.get("artifact_binding_id"), str)
            and bool(binding["artifact_binding_id"]))


def normalize_measurement(raw, path, expected_mode, case, reference, descriptor):
    """Keep validity, semantic output, state, historical join and arithmetic apart."""
    timing = raw.get("timing") or {}
    output = raw.get("output_check") or {}
    state = raw.get("state_check") or {}
    history = raw.get("historical_join") or {}
    contract = raw.get("stage_contract") or {}
    reasons = []
    row = {field: raw.get(field) for field in IDENTITY_FIELDS}
    row.update(block_id=raw.get("block_id"), mode=raw.get("mode"), run_id=raw.get("run_id"),
               runner_sha256=raw.get("runner_sha256"),
               source_path=str(path), source_scope=raw.get("source_scope"),
               run_status=raw.get("run_status", raw.get("status", "unknown")),
               output_status=output.get("status", "unknown"),
               output_pre_status=output.get("pre_status", "unknown"),
               output_post_status=output.get("post_status", "unknown"),
               state_status=state.get("status", "unknown"),
               state_comparable=state.get("status") == "pass" and state.get("comparable") is True,
               historical_join_status=history.get("status", "unknown"),
               state_notes=state.get("notes", []), reasons=reasons)
    row.update({key: timing.get(key) for key in ("warmup_completed", "measured_completed",
               "requested", "drained", "timer_start_s", "timer_end_s")})
    row.update({key: contract.get(key) for key in ("configured_inflight", "observed_max_inflight",
               "completion_endpoint", "handoff_dtype", "handoff_layout")})
    ids = timing.get("request_ids", [])
    try:
        unique_ids = len(set(ids)) if isinstance(ids, list) else 0
    except TypeError:
        unique_ids = 0
    row["unique_request_ids"] = unique_ids
    timing_valid = True
    try:
        row.update(completion_rates(timing))
    except (ValueError, TypeError) as exc:
        reasons.append(f"timing: {exc}")
        timing_valid = False
    if not (timing.get("warmup_completed") == WARMUP_COUNT
            and timing.get("measured_completed") == MEASURED_COUNT
            and timing.get("requested") == MEASURED_COUNT
            and timing.get("drained") is True
            and timing.get("pending_requests", 0) == 0
            and isinstance(ids, list) and len(ids) == unique_ids == MEASURED_COUNT):
        reasons.append("timing: warmup/count/unique-ID/drain contract incomplete")
        timing_valid = False
    warm_ids = timing.get("warmup_request_ids")
    if isinstance(warm_ids, list) and any(value in ids for value in warm_ids):
        reasons.append("timing: warmup IDs leaked into measured completion IDs")
        timing_valid = False
    row["timing_valid"] = timing_valid

    input_valid = True
    if case is None:
        reasons.append("identity: case absent from fixed PLAN")
        input_valid = False
    else:
        for field in IDENTITY_FIELDS:
            if not case.get(field) or raw.get(field) != case.get(field):
                reasons.append(f"identity: {field} differs from fixed PLAN or is missing")
                input_valid = False
        expected_runner = case.get("_expected_runner_sha256")
        if expected_runner and raw.get("runner_sha256") != expected_runner:
            reasons.append("identity: runner content differs from the fixed implementation SHA256")
            input_valid = False
    if not isinstance(raw.get("block_id"), int) or isinstance(raw.get("block_id"), bool) or raw["block_id"] not in (1, 2, 3):
        reasons.append("identity: block_id must be one of 1, 2, 3")
        input_valid = False
    if not isinstance(raw.get("run_id"), str) or not raw["run_id"]:
        reasons.append("identity: unique nonempty run_id missing")
        input_valid = False
    binding = raw.get("input_binding") or {}
    expected_binding = (case or {}).get("input_binding") or (reference or {}).get("input_binding") or reference or {}
    if not _binding_complete(binding) or not _binding_complete(expected_binding):
        reasons.append("input: exact effective-input/handoff/artifact binding is missing")
        input_valid = False
    elif _binding_tuple(binding) != _binding_tuple(expected_binding):
        reasons.append("input: effective tensor or handoff or artifact binding changed")
        input_valid = False
    reference_status = (reference or {}).get("status", "unknown")
    if reference_status != "pass":
        reasons.append(f"input: fixed cohort reference status is {reference_status}")
        input_valid = False
    row["input_valid"] = input_valid

    stage_valid = True
    wanted_scope = {"P": "isolated_prefix", "C": "isolated_consumer", "PC": "joint_pipeline"}[expected_mode]
    if raw.get("mode") != expected_mode or raw.get("source_scope") != wanted_scope:
        reasons.append("stage: isolated/joint source scope does not match its mode directory")
        stage_valid = False
    if descriptor is None:
        reasons.append("stage: fixed resource descriptor missing or invalid")
        stage_valid = False
    else:
        expected_endpoint = "handoff_ready" if expected_mode == "P" else "classification_complete"
        if contract.get("completion_endpoint") != expected_endpoint:
            reasons.append("stage: completion endpoint differs from usable handoff/task completion")
            stage_valid = False
        if contract.get("handoff_dtype") != descriptor.handoff_dtype or contract.get("handoff_layout") != descriptor.handoff_layout:
            reasons.append("stage: genuine handoff dtype/layout differs from fixed resource descriptor")
            stage_valid = False
        if contract.get("configured_inflight") != descriptor.prefix_inflight:
            reasons.append("stage: configured prefix inflight differs from fixed recipe")
            stage_valid = False
        occupancy = contract.get("observed_max_inflight")
        if expected_mode in ("P", "PC") and (isinstance(occupancy, bool) or not isinstance(occupancy, int)
                                               or not 1 <= occupancy <= descriptor.prefix_inflight):
            reasons.append("stage: observed prefix occupancy missing or exceeds configured limit")
            stage_valid = False
    if expected_mode in ("P", "PC") and contract.get("prefix_mapping_complete") is not True:
        reasons.append("stage: prefix completion is not confirmed after mapping/materialization")
        stage_valid = False
    if expected_mode in ("C", "PC"):
        if contract.get("genuine_handoff") is not True:
            reasons.append("stage: consumer does not prove genuine prefix handoff replay")
            stage_valid = False
        if contract.get("classification_complete") is not True:
            reasons.append("stage: classification completion is not confirmed")
            stage_valid = False
    if expected_mode == "P" and contract.get("suffix_requests", 0) != 0:
        reasons.append("stage: suffix work occurred in prefix-only mode")
        stage_valid = False
    if expected_mode == "C" and contract.get("prefix_requests", 0) != 0:
        reasons.append("stage: prefix work occurred in consumer-only mode")
        stage_valid = False
    row["stage_contract_valid"] = stage_valid
    valid = timing_valid and input_valid and stage_valid
    row["validity_status"] = "pass" if valid else "fail"
    output_valid = all(output.get(key) == "pass" for key in ("status", "pre_status", "post_status"))
    if not output_valid:
        reasons.append("output: pre/post/reference parity is not independently PASS")
    row["task_valid"] = valid and output_valid
    if raw.get("errors"):
        reasons.extend(f"recorded: {error}" for error in raw["errors"])
    row["_input_binding"] = _binding_tuple(binding)
    return row


def _stage_capacity(row):
    return StageCapacity(row["case_id"], row["block_id"], row["mode"], row["source_scope"],
                         row["source_path"], row["run_id"], row["config_id"], row["candidate_id"],
                         row["implementation_id"], row["input_recipe_id"], row["_input_binding"],
                         row["resource_descriptor_id"], row["fps_core"], row["task_valid"],
                         row["state_comparable"])


def _selected(rows, errors):
    groups = {}
    for row in rows:
        if row["task_valid"]:
            groups.setdefault((row["case_id"], row["block_id"], row["mode"]), []).append(row)
    chosen = {}
    for key, items in groups.items():
        if len(items) == 1:
            chosen[key] = items[0]
        else:
            errors.append(f"ambiguous accepted repetitions {key}: {[row['run_id'] for row in items]}; no FPS-based selection")
    return chosen


def _pc_filename_key(path, cases):
    """Use only the controller's bound filename; do not inspect pending labels."""
    for case_id in cases:
        match = re.fullmatch(re.escape(case_id) + r"_block([123])(?:_.+)?", path.stem)
        if match:
            return case_id, int(match.group(1))
    return None


def _load_mode(root, mode, cases, references, descriptors, errors, on_read=None,
               predicted_pc_keys=None, pending_labels=None):
    if mode == "PC" and predicted_pc_keys is None:
        raise ValueError("PC loading requires already-persisted block prediction keys")
    rows = []
    for path in sorted((root / "measurements" / mode).glob("*.json")):
        filename_key = _pc_filename_key(path, cases) if mode == "PC" else None
        if mode == "PC" and filename_key not in predicted_pc_keys:
            if pending_labels is not None:
                pending_labels.append({"source_path": str(path.relative_to(root)),
                                       "case_id": filename_key[0] if filename_key else None,
                                       "block_id": filename_key[1] if filename_key else None,
                                       "status": "unassessed_pending_stage_prediction",
                                       "reason": "accepted P/C prediction not available" if filename_key
                                       else "filename does not bind a fixed case/block"})
            continue
        try:
            if on_read is not None:
                on_read(path)
            raw = read_json(path)
            ident = raw.get("case_id")
            row = normalize_measurement(raw, path.relative_to(root), mode, cases.get(ident),
                                        references.get(ident), descriptors.get(ident))
            if mode == "PC" and (ident, raw.get("block_id")) != filename_key:
                row["input_valid"] = row["task_valid"] = False
                row["validity_status"] = "fail"
                row["reasons"].append("identity: PC case/block differs from its bound filename")
            rows.append(row)
        except (ValueError, TypeError, OSError, KeyError) as exc:
            errors.append(f"unreadable {path.relative_to(root)}: {type(exc).__name__}: {exc}")
    return rows


def _direction(ratio):
    return "numerator_faster" if ratio > 1 else "denominator_faster" if ratio < 1 else "equal"


def _ratio_rows(cases, comparisons):
    groups = {}
    for case_id, case in cases.items():
        group = case.get("comparison_group", case.get("group_id", case.get("family")))
        if group:
            groups.setdefault(group, []).append(case_id)
    by_key = {(row["case_id"], row["block_id"]): row for row in comparisons}
    result = []
    for group, names in sorted(groups.items()):
        if len(names) != 2:
            continue
        # Fixed PLAN case order defines numerator; never observed throughput.
        numerator, denominator = names
        for block in (1, 2, 3):
            one, two = by_key.get((numerator, block)), by_key.get((denominator, block))
            if one is None or two is None:
                continue
            predicted = one["fps_Oracle_core"] / two["fps_Oracle_core"]
            observed = one["fps_PC_core"] / two["fps_PC_core"]
            result.append({"record_type": "pair_ratio", "group_id": group, "block_id": block,
                           "numerator_case_id": numerator, "denominator_case_id": denominator,
                           "predicted_ratio": predicted, "observed_ratio": observed,
                           "predicted_direction": _direction(predicted),
                           "observed_direction": _direction(observed),
                           "direction_agrees": _direction(predicted) == _direction(observed),
                           "ratio_signed_error_pct": 100.0 * (predicted / observed - 1),
                           "task_valid": True,
                           "state_comparable": one["state_comparable"] and two["state_comparable"],
                           "drift_flag": one["drift_flag"] or two["drift_flag"]})
    return result


def analyse(input_dir, output_dir=None, on_read=None):
    root = Path(input_dir).resolve(strict=True)
    destination = Path(output_dir).resolve() if output_dir else root
    if destination != root and root not in destination.parents:
        raise ValueError("offline outputs must stay inside this experiment directory")
    plan = read_json(root / "PLAN.json")
    if plan.get("task_id") != "stage_cost_composition_20261014":
        raise ValueError("input is not the new stage-cost experiment; historical directories remain read-only")
    cases = _cases(plan)
    reference_path = root / "INPUT_REFERENCE_CHECK.json"
    references = _references(read_json(reference_path)) if reference_path.exists() else {}
    destination.mkdir(parents=True, exist_ok=True)
    for relative in ("STAGE_CAPACITIES.csv", "ORACLE_PREDICTIONS.csv", "PIPELINE_MEASUREMENTS.csv",
                     "COMPOSITION_COMPARISON.csv", "results", "results/ORACLE_PREDICTIONS.json", "results/ANALYSIS.json"):
        resolved = (destination / relative).resolve()
        if root not in resolved.parents:
            raise ValueError("offline output path escapes experiment directory through a symlink")
    (destination / "results").mkdir(exist_ok=True)
    errors = []
    descriptors = {}
    for key, case in cases.items():
        try:
            descriptors[key] = _descriptor(plan, case)
        except (ValueError, TypeError) as exc:
            errors.append(f"{key}: fixed resource descriptor unavailable: {exc}")
    stages = (_load_mode(root, "P", cases, references, descriptors, errors, on_read)
              + _load_mode(root, "C", cases, references, descriptors, errors, on_read))
    chosen_stages = _selected(stages, errors)
    predictions = []
    for case_id in cases:
        for block in (1, 2, 3):
            prefix, consumer = chosen_stages.get((case_id, block, "P")), chosen_stages.get((case_id, block, "C"))
            if prefix is None or consumer is None or case_id not in descriptors:
                continue
            try:
                predictions.append(predict_oracle(_stage_capacity(prefix), _stage_capacity(consumer), descriptors[case_id]))
            except (ValueError, TypeError) as exc:
                errors.append(f"{case_id} block {block}: prediction rejected: {exc}")
    write_csv(destination / "STAGE_CAPACITIES.csv", COMMON_FIELDS, stages)
    # Closing this file precedes the first open of any PC performance report.
    write_csv(destination / "ORACLE_PREDICTIONS.csv", PREDICTION_FIELDS, predictions)
    write_json(destination / "results" / "ORACLE_PREDICTIONS.json", predictions)

    pending_pipeline_labels = []
    predicted_pc_keys = {(row["case_id"], row["block_id"]) for row in predictions}
    pipelines = _load_mode(root, "PC", cases, references, descriptors, errors, on_read,
                           predicted_pc_keys=predicted_pc_keys, pending_labels=pending_pipeline_labels)
    chosen_pipelines = _selected(pipelines, errors)
    comparisons = []
    for prediction in predictions:
        case_id, block = prediction["case_id"], prediction["block_id"]
        pc = chosen_pipelines.get((case_id, block, "PC"))
        prefix = chosen_stages[(case_id, block, "P")]
        consumer = chosen_stages[(case_id, block, "C")]
        if pc is None:
            continue
        if any(pc[field] != prefix[field] for field in IDENTITY_FIELDS) or pc["_input_binding"] != prefix["_input_binding"]:
            errors.append(f"{case_id} block {block}: PC identity does not match accepted isolated stages")
            continue
        row = dict(prediction, record_type="block", PC_run_id=pc["run_id"], task_valid=True,
                   state_comparable=prediction["state_comparable"] and pc["state_comparable"],
                   drift_flag=any(item.get("drift_flag") is True for item in (prefix, consumer, pc)))
        row.update(compare_prediction(prediction, pc["fps_core"], pc["fps_total"]))
        row["notes"] = [] if row["state_comparable"] else ["descriptive only: operating states not fully comparable"]
        comparisons.append(row)
    ratios = _ratio_rows(cases, comparisons)
    write_csv(destination / "PIPELINE_MEASUREMENTS.csv", COMMON_FIELDS, pipelines)
    write_csv(destination / "COMPOSITION_COMPARISON.csv", COMPARISON_FIELDS, comparisons + ratios)

    summaries = []
    for case_id, case in cases.items():
        accepted = [row for row in comparisons if row["case_id"] == case_id]
        measured = [row for row in stages + pipelines if row["case_id"] == case_id]
        pending = [row for row in pending_pipeline_labels if row["case_id"] == case_id]
        metrics = {field: summarize([row.get(field) for row in accepted]) for field in METRICS}
        stage_stats = {mode: {field: summarize([row.get(field) for row in measured if row["mode"] == mode and row["task_valid"]])
                             for field in ("fps_core", "fps_total", "drift_relative_pct")} for mode in ("P", "C", "PC")}
        n = len(accepted)
        inside = sum(row["within_10pct_band"] for row in accepted)
        all_states = n > 0 and all(row["state_comparable"] for row in accepted)
        drift = any(row["drift_flag"] for row in accepted)
        spreads = [metrics[field]["spread_relative_pct"] for field in
                   ("fps_P_core", "fps_C_core", "fps_Oracle_core", "fps_PC_core")]
        # 5% flags a substantial fraction of the prechosen 10% orientation band;
        # it is a descriptive uncertainty rule, never a significance test.
        unclear_variation = drift or any(spread is not None and spread >= 5.0 for spread in spreads)
        if n < 2 or not all_states:
            decision = "D"
            conclusion = "not fully evaluable: fewer than two accepted triplets or missing comparable operating state"
        elif unclear_variation:
            decision = "D"
            conclusion = "unclear: process/time-section variation is material relative to the practical error band"
        elif inside == n:
            decision = "A"
            conclusion = "composition is practically usable on this checked recipe within the prechosen 10% band"
        elif inside == 0:
            decision = "C"
            conclusion = "valid independent stage costs do not provide a useful simple maximum on this recipe"
        else:
            decision = "B"
            conclusion = "mixed block evidence on this recipe; some accepted blocks exceed the 10% band"
        gaps = []
        for block in (1, 2, 3):
            missing = [mode for mode in ("P", "C", "PC")
                       if (case_id, block, mode) not in (chosen_pipelines if mode == "PC" else chosen_stages)]
            if missing:
                gaps.append({"block_id": block, "missing_or_unaccepted_modes": missing,
                             "pipeline_label_saved_but_unopened": any(row["block_id"] == block for row in pending)})
        summaries.append({"case_id": case_id, "config_id": case.get("config_id"),
                          "candidate_id": case.get("candidate_id"), "n": n,
                          "within_10pct_band_n": inside, "decision": decision, "conclusion": conclusion,
                          "metrics": metrics, "stage_stats": stage_stats, "gaps": gaps,
                          "state_comparable": all_states, "drift_flag": drift,
                          "variation_unclear": unclear_variation,
                          "reference_status": references.get(case_id, {}).get("status", "unknown"),
                          "plan_status": case.get("status", "unknown"),
                          "historical_context": case.get("historical_context", {}),
                          "measurement_rows": len(measured),
                          "pending_pipeline_labels": pending,
                          "pending_pipeline_label_count": len(pending),
                          "task_valid_rows": sum(row["task_valid"] for row in measured)})
    decisions = [row["decision"] for row in summaries]
    if decisions and all(item == "A" for item in decisions):
        overall = "A"
    elif "A" in decisions and any(item in ("B", "C") for item in decisions):
        overall = "B"
    elif decisions and all(item == "C" for item in decisions):
        overall = "C"
    else:
        overall = "D"
    ratio_summaries = []
    for group in dict.fromkeys(row["group_id"] for row in ratios):
        grouped = [row for row in ratios if row["group_id"] == group]
        ratio_summaries.append({"group_id": group, "n": len(grouped),
                                "numerator_case_id": grouped[0]["numerator_case_id"],
                                "denominator_case_id": grouped[0]["denominator_case_id"],
                                "direction_agrees_n": sum(row["direction_agrees"] for row in grouped),
                                "metrics": {field: summarize([row[field] for row in grouped])
                                            for field in ("predicted_ratio", "observed_ratio", "ratio_signed_error_pct")}})
    summary = {"schema_version": 1, "model": "two_stage_max_independent_core_costs",
               "offline_only": True, "prediction_before_PC_read": True,
               "per_block_PC_label_embargo": True,
               "core_definition": "8000 / (t_9000 - t_1000), 1-based observed completion order, seconds",
               "drift_definition": "100*(fps_t5000_to_t9000/fps_t1000_to_t5000-1); flag abs>5%",
               "practical_band_pct": 10.0, "variation_warning_pct": 5.0,
               "overall_decision": overall, "cases": summaries, "pair_ratios": ratios,
               "pair_ratio_summaries": ratio_summaries,
               "measurement_rows": len(stages) + len(pipelines), "accepted_stage_rows": sum(row["task_valid"] for row in stages),
               "accepted_pipeline_rows": sum(row["task_valid"] for row in pipelines),
               "pending_pipeline_labels": pending_pipeline_labels,
               "pending_pipeline_label_count": len(pending_pipeline_labels),
               "prediction_rows": len(predictions), "comparison_rows": len(comparisons),
               "errors": errors}
    write_json(destination / "results" / "ANALYSIS.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional output directory inside the new experiment")
    args = parser.parse_args(argv)
    result = analyse(args.input, args.output)
    print(json.dumps({"overall_decision": result["overall_decision"], "prediction_rows": result["prediction_rows"],
                      "comparison_rows": result["comparison_rows"],
                      "pending_pipeline_label_count": result["pending_pipeline_label_count"],
                      "errors": len(result["errors"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
