"""Offline, versioned unit sensitivity of the frozen THESIS20 score inputs.

Only compact graph features and pure, already published score definitions are
loaded. The binary-MiB variant is a counterfactual input adapter, not a change to
the historical fields, fitted coefficients, tool checkout or measured results.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

HISTORICAL = Path("results/supplementary-studies/thesis20-ranking-20261005")
STUDY = Path("results/supplementary-studies/thesis-v53-offline-review-20261020")
VARIANT = "binary_mib_input_v1"
BASELINE = "historical_decimal_mb_input_d164aad6"
METHOD_FIELDS = {
    "cut_bytes_only": "cut_bytes",
    "weighted_score": "weighted_score",
    "cycle_time_no_handover": "predicted_bottleneck_ms",
    "onnx_real_boundary_hardware_aware": "accelerator_fit_score",
    "stored_predicted_stream_fps": "predicted_stream_fps",
}
OBJECTIVE_FIELDS = (
    "accelerator_fit_score",
    "predicted_bottleneck_ms",
    "predicted_handover_ms_raw",
    "predicted_handover_ms",
    "predicted_stream_cycle_ms",
    "predicted_stream_fps",
)
CONTROLS = ("cut_bytes_only", "weighted_score", "cycle_time_no_handover")
AFFECTED = ("onnx_real_boundary_hardware_aware", "stored_predicted_stream_fps")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_csv(path):
    """Use the exact frozen projection's scalar decoding conventions."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key, value in row.items():
            if value == "":
                row[key] = None
            elif value in ("True", "False"):
                row[key] = value == "True"
            elif value.startswith(("{", "[")):
                row[key] = json.loads(value)
            else:
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
    return rows


def _write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, sort_keys=True, separators=(",", ":"))
                if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def load_historical_modules(repo_root):
    """Import a uniquely named pure package, without importing ONNX or runners."""
    package_path = repo_root / HISTORICAL / "scripts/method_core"
    package_name = "_thesis_v53_frozen_score_core"
    spec = importlib.util.spec_from_file_location(
        package_name, package_path / "__init__.py",
        submodule_search_locations=[str(package_path)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    modules = {}
    for name in ("objective_scoring", "ranking_methods", "units", "system_model"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{name}", package_path / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


def ranks(rows, values, descending=False):
    """Exact score ties, then boundary and case ID; no rounded score ties."""
    ordered = sorted(
        rows,
        key=lambda row: (
            -values[row["case_id"]] if descending else values[row["case_id"]],
            int(row["boundary"]),
            row["case_id"],
        ),
    )
    return {row["case_id"]: index for index, row in enumerate(ordered, 1)}


def binary_mib_input(row):
    """Version 1 changes only the legacy adapter slot read by objective_scoring.

    This temporary dict keeps the historical API key ``cut_mb_val`` because
    that is the exact consumed slot. It is never serialized as a historical
    feature or used to alter the source CSV. All other fields remain identical.
    """
    return dict(row, cut_mb_val=float(row["cut_bytes"]) / (1024.0 ** 2))


def compare_model(rows, parameters, modules):
    objective = modules["objective_scoring"]
    ranking = modules["ranking_methods"]
    rows = sorted(rows, key=lambda row: row["source_list_order"])
    if any(row["strict_ok"] is not True for row in rows):
        raise ValueError("The frozen universe must contain only strict_ok=true rows")
    if len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate candidate identity")
    profiles = {json.dumps(row["accelerator_fit_profile"], sort_keys=True) for row in rows}
    if len(profiles) != 1:
        raise ValueError("Mixed hardware profiles require a separate comparison")
    profile = json.loads(next(iter(profiles)))
    context = {
        "stage1": profile["stage1"], "stage2": profile["stage2"],
        "direction": profile["stage1"] + "_to_" + profile["stage2"],
        "runner_regime": "native_fifo",
    }
    # Run each variant over the same COMPLETE model universe. No measured or
    # quality-filtered subset is ever passed to the normalization function.
    predictions = {}
    for version, candidates in (
        (BASELINE, rows), (VARIANT, [binary_mib_input(row) for row in rows])
    ):
        predictions[version] = {
            (row["case_id"], row["method_id"]): row
            for row in ranking.compute_ranking_predictions(
                candidates, [context], parameters["ranking_validation"]
            )
        }
    scores = {BASELINE: defaultdict(dict), VARIANT: defaultdict(dict)}
    deltas = []
    max_errors = defaultdict(float)
    boundary_order = {
        row["case_id"]: i
        for i, row in enumerate(sorted(rows, key=lambda r: (int(r["boundary"]), r["case_id"])))
    }
    for row in rows:
        case = row["case_id"]
        if int(row["original_order"]) != boundary_order[case]:
            raise ValueError("Historical original_order does not match boundary/case tie order")
        fallback = 5.0 + row["total_flops"] / 1e10 + row["cut_bytes"] / 1e9
        _close(fallback, row["predicted_total_latency_ms"], "fallback total")
        _close(row["cut_bytes"] / 1e9, row["predicted_transfer_latency_ms"], "fallback transfer")
        _close(row["cut_bytes"] / 1e6, row["cut_mb_val"], "decimal MB")
        _close(row["cut_bytes"] / 2**20, row["cut_mib_val"], "binary MiB")
        enriched = dict(row, pred_latency_total_ms=row["predicted_total_latency_ms"])
        variants = {
            BASELINE: objective.candidate_objective_metrics(
                enriched, stage1=profile["stage1"], stage2=profile["stage2"],
                use_calibration=row["throughput_calibration_enabled"],
            ),
            VARIANT: objective.candidate_objective_metrics(
                binary_mib_input(enriched), stage1=profile["stage1"], stage2=profile["stage2"],
                use_calibration=row["throughput_calibration_enabled"],
            ),
        }
        if variants[BASELINE]["accelerator_fit_profile"] != profile:
            raise ValueError("The supplied historical profile is not reproduced")
        delta = {
            "model_id": row["model_id"], "case_id": case, "boundary": int(row["boundary"]),
            "strict_ok": row["strict_ok"],
            "normalization_scope": "complete_original_model_universe",
            "baseline": BASELINE, "variant": VARIANT,
            "historical_stage1": profile["stage1"], "historical_stage2": profile["stage2"],
            "cut_bytes": row["cut_bytes"], "historical_cut_input_decimal_MB": row["cut_mb_val"],
            "variant_cut_input_binary_MiB": binary_mib_input(row)["cut_mb_val"],
            "source_list_order": int(row["source_list_order"]),
            "original_order": int(row["original_order"]),
        }
        for field in OBJECTIVE_FIELDS:
            old, new = variants[BASELINE][field], variants[VARIANT][field]
            _close(old, row[field], field)
            max_errors[field] = max(max_errors[field], abs(old - row[field]))
            delta["historical_" + field] = old
            delta["variant_" + field] = new
            delta["delta_" + field] = new - old
        for method, field in METHOD_FIELDS.items():
            for version in (BASELINE, VARIANT):
                value = (
                    variants[version][field]
                    if method in AFFECTED
                    else predictions[version][(case, method)]["predicted_value"]
                )
                scores[version][method][case] = value
            if method in CONTROLS:
                if scores[BASELINE][method][case] != scores[VARIANT][method][case]:
                    raise ValueError(f"Unit adapter unexpectedly changed control {method}")
                delta[method + "_score_unchanged"] = scores[BASELINE][method][case]
        deltas.append(delta)
    for method in METHOD_FIELDS:
        old_rank = ranks(rows, scores[BASELINE][method], method == "stored_predicted_stream_fps")
        new_rank = ranks(rows, scores[VARIANT][method], method == "stored_predicted_stream_fps")
        for delta in deltas:
            case = delta["case_id"]
            delta[method + "_historical_rank"] = old_rank[case]
            delta[method + "_variant_rank"] = new_rank[case]
            delta[method + "_rank_delta"] = new_rank[case] - old_rank[case]
    return deltas, scores, dict(max_errors), predictions[BASELINE]


def _close(actual, expected, label):
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"Historical {label} is not reproduced: {actual!r} != {expected!r}")


def selection_summary(rows, scores, method):
    descending = method == "stored_predicted_stream_fps"
    out = {"method": method, "candidate_count": len(rows)}
    rank_maps = {}
    for version, label in ((BASELINE, "historical"), (VARIANT, "variant")):
        values = scores[version][method]
        rank_maps[version] = ranks(rows, values, descending)
        best = min(rows, key=lambda row: rank_maps[version][row["case_id"]])["case_id"]
        out[label + "_selected_case"] = best
        out[label + "_selected_score"] = values[best]
        out[label + "_top_ties"] = [
            row["case_id"] for row in sorted(rows, key=lambda row: rank_maps[version][row["case_id"]])
            if values[row["case_id"]] == values[best]
        ]
    out["selected_case_changed"] = out["historical_selected_case"] != out["variant_selected_case"]
    out["score_changed_candidates"] = sum(
        scores[BASELINE][method][row["case_id"]] != scores[VARIANT][method][row["case_id"]]
        for row in rows
    )
    out["rank_changed_candidates"] = sum(
        rank_maps[BASELINE][row["case_id"]] != rank_maps[VARIANT][row["case_id"]]
        for row in rows
    )
    return out


def field_overview():
    columns = ("field", "actual_meaning", "unit_or_scale", "historical_definition",
               "source_function", "use", "versioned_variant_effect", "limitation")
    values = [
        ("cut_bytes", "Graph tensor boundary storage estimate", "bytes",
         "sum of stored graph crossing tensor byte estimates",
         "workflow.runner.WorkflowRunner._make_real_analysis_candidates; ranking_methods.candidate_cut_bytes",
         "cut_bytes_only and full-universe weighted communication term", "unchanged",
         "Not measured bus traffic; tensor dtype/shape estimate is not all internal runtime precision"),
        ("cut_mb_val", "Decimal boundary size passed to legacy MiB-named slots", "decimal MB",
         "cut_bytes/1000000", "workflow.runner._make_real_analysis_candidates; objective_scoring.accelerator_fit_metrics",
         "Fit threshold penalties and objective handover inputs", "temporary adapter uses cut_bytes/1048576",
         "Historical field is preserved; variant changes the function input, not the source CSV"),
        ("cut_mib_val", "Binary boundary size", "MiB",
         "cut_bytes/1048576", "workflow.runner._make_real_analysis_candidates; ranking_methods.candidate_cut_mib",
         "Pure ranking helper and separate Generic directional handover path", "unchanged",
         "Already binary; no second conversion"),
        ("peak_right_mib_val", "Estimated right-side peak activation storage", "MiB",
         "peak_right_bytes/1048576", "workflow.runner._make_real_analysis_candidates",
         "0.060*peak_right_mib in raw handover heuristic", "unchanged",
         "Storage estimate, not measured latency"),
        ("total_flops; flops_left_abs; flops_right_abs", "Historical graph arithmetic proxy and its partitions",
         "proxy operation count", "historical analyzer costs and prefix sums",
         "core_analysis.analyze_model; workflow.runner._make_real_analysis_candidates",
         "Fallback total, imbalance and accelerator compute share", "unchanged",
         "Operator-dependent proxy; neither measured device operations nor calibrated stage times"),
        ("imbalance_val", "Historical compute partition imbalance", "dimensionless",
         "abs(left-right)/(left+right)", "ranking_methods.candidate_imbalance",
         "Full-universe weighted score and stream calibration hinge", "unchanged",
         "Stored proxy work is not accelerator elapsed-time balance"),
        ("weighted_score", "Weighted normalized communication/imbalance/tensor proxy", "dimensionless",
         "1*minmax(log10(1+bytes))+3*minmax(imbalance)+0.2*minmax(max(n_tensors-1,0))",
         "ranking_methods.compute_ranking_predictions", "Ascending selector",
         "unchanged; both variants normalize over the complete original model universe",
         "Never re-normalized within measured or quality-filtered subsets"),
        ("accelerator_fit_score", "Hardware-profile heuristic fit penalty", "dimensionless",
         "compute+cut+tensor+context+strict+parse+compile-risk penalties",
         "objective_scoring.accelerator_fit_metrics", "Ascending selector",
         "Cut hinge input MB becomes MiB; thresholds and all other terms frozen",
         "Historical Hailo10-to-TensorRT profile is not retargeted to H8 or DeepX"),
        ("predicted_total_latency_ms", "Workflow fallback score with latency-like name", "heuristic ms-labelled scale",
         "5+total_flops/1e10+cut_bytes/1e9", "workflow.runner._make_real_analysis_candidates",
         "Input to objective FLOP-share bottleneck", "unchanged",
         "No supplied hardware throughput/link calibration; renaming does not create physical ms"),
        ("predicted_transfer_latency_ms", "Workflow fallback transfer proxy", "heuristic ms-labelled scale",
         "cut_bytes/1e9", "workflow.runner._make_real_analysis_candidates",
         "Stored legacy prediction; distinct from objective handover", "unchanged",
         "Not a measured transfer time or complete link model"),
        ("predicted_bottleneck_ms", "Fallback total multiplied by larger compute-proxy share", "heuristic ms-labelled scale",
         "predicted_total_latency_ms*max(left,right)/(left+right)",
         "objective_scoring.candidate_objective_metrics; ranking_methods._stage_times_from_candidate",
         "cycle_time_no_handover; input to stream-cycle proxy", "unchanged",
         "Frozen stage throughput models are empty; fallback is not measured stage timing"),
        ("predicted_handover_ms_raw", "Interpretable additive interface/feasibility heuristic", "heuristic ms-labelled scale",
         "0.12*legacy_cut_input+0.010*n+0.040*unknown+0.060*peak_right_MiB+direction_bias+feasibility",
         "objective_scoring.predicted_handover_ms_raw", "Input to stored direction calibration",
         "Legacy cut input becomes binary MiB; coefficients frozen",
         "Mixed historical cut units; not a new Native handover fit"),
        ("predicted_handover_ms", "Stored generic direction-specific calibrated heuristic", "heuristic ms-labelled scale",
         "yolov7_streaming_v1 affine raw/cut-excess/imbalance-excess terms; clamp>=0",
         "objective_scoring.calibrated_handover_ms", "Stored stream-cycle proxy",
         "Raw and cut-excess inputs use MiB; fitted coefficients remain unchanged",
         "Counterfactual sensitivity only; changing the unit does not recalibrate empirical coefficients"),
        ("predicted_stream_cycle_ms", "Bottleneck plus stored handover heuristic", "heuristic ms-labelled scale",
         "predicted_bottleneck_ms+predicted_handover_ms", "objective_scoring.predicted_stream_cycle_ms",
         "Reciprocal stream score", "Changes through handover only",
         "Not measured Native pipeline cycle"),
        ("predicted_stream_fps", "Reciprocal heuristic stream-cycle score", "heuristic FPS-labelled scale",
         "1000/predicted_stream_cycle_ms", "objective_scoring.predicted_stream_fps",
         "Descending stored_predicted_stream_fps selector", "Changes through handover only",
         "Not independently calibrated for every model/setup; no new throughput measurement"),
        ("cycle_time_with_handover", "Native runner/direction cycle predictor", "unavailable",
         "bottleneck+Native handover only when the Native model/fields exist",
         "ranking_methods.runner_direction_handover_ms", "Explicitly unavailable historical method",
         "unchanged/unavailable", "Native handover models are empty; Generic heuristics are not substituted"),
        ("gui_total_latency", "Parameterized GUI system estimate", "model ms when inputs exist",
         "1000*left/(left_GOPS*1e9)+link_ms+1000*right/(right_GOPS*1e9)+overhead_ms",
         "system_model.SystemSpec.estimate_boundary; units.bandwidth_to_bytes_per_s",
         "Separate GUI estimate; unavailable for all frozen models", "unchanged/unavailable",
         "All seven original SystemSpecs are null; no reverse fitting from fallback predictions"),
    ]
    return [dict(zip(columns, row)) for row in values]


def verify_sources(repo_root):
    bindings_path = repo_root / STUDY / "inputs/scores/source_bindings.json"
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    verified = []
    for item in bindings["reproduction_inputs"]:
        path = repo_root / item["path"]
        actual = _sha(path.read_bytes())
        if actual != item["sha256"]:
            raise ValueError(f"Source/input hash mismatch: {item['path']}")
        verified.append(dict(item, hash_verified=True))
    archive = bindings["archive"]
    with tarfile.open(repo_root / archive["path"]) as handle:
        for item in archive["members"]:
            content = handle.extractfile(item["member"]).read()
            if _sha(content) != item["sha256"]:
                raise ValueError(f"Archive source mismatch: {item['member']}")
            verified.append(dict(item, archive_path=archive["path"], hash_verified=True))
    provenance = json.loads((repo_root / HISTORICAL / "inputs/method_code_provenance.json").read_text())
    for item in provenance:
        path = repo_root / HISTORICAL / item["copied_path"]
        if _sha(path.read_bytes()) != item["sha256"]:
            raise ValueError(f"Historical method provenance mismatch: {item['copied_path']}")
    return bindings, verified


def build(repo_root: Path, output: Path) -> dict:
    repo_root, output = Path(repo_root), Path(output)
    if output.resolve().is_relative_to((repo_root / HISTORICAL).resolve()):
        raise ValueError("Historical inputs and outputs must not be overwritten")
    bindings, verified = verify_sources(repo_root)
    modules = load_historical_modules(repo_root)
    features = _read_csv(repo_root / HISTORICAL / "inputs/method_graph_features.csv")
    stored = _read_csv(repo_root / HISTORICAL / "inputs/method_candidate_scores.csv")
    parameters = json.loads((repo_root / HISTORICAL / "inputs/method_parameters.json").read_text())
    frozen_groups = _read_csv(repo_root / HISTORICAL / "tables/method_groups.csv")
    by_model = defaultdict(list)
    for row in features:
        by_model[row["model_id"]].append(row)
    stored_index = {(r["model_id"], r["case_id"], r["method"]): r for r in stored}
    if len(stored_index) != len(stored):
        raise ValueError("Duplicate frozen score identity")
    deltas, full_selections, subset_selections = [], [], []
    model_scores, reproductions = {}, []
    for model, rows in sorted(by_model.items()):
        model_deltas, scores, errors, predictions = compare_model(rows, parameters, modules)
        model_scores[model] = scores
        deltas.extend(model_deltas)
        verified_score_rows = 0
        for row in rows:
            for method in METHOD_FIELDS:
                record = stored_index[(model, row["case_id"], method)]
                _close(scores[BASELINE][method][row["case_id"]], record["score"], "stored method score")
                verified_score_rows += 1
            native = predictions[(row["case_id"], "cycle_time_with_handover")]
            if native["predicted_value"] is not None:
                raise ValueError("Unexpected available Native handover predictor")
            if native["prediction_source"].split("+")[-1] != "native_handover_model_unconfigured":
                raise ValueError("Unexpected Native handover provenance")
            for method in ("cycle_time_with_handover", "gui_total_latency"):
                if stored_index[(model, row["case_id"], method)]["score"] is not None:
                    raise ValueError(f"Unexpected available frozen method: {method}")
                verified_score_rows += 1
        if parameters["system_spec_by_model"][model] is not None:
            raise ValueError("An original GUI SystemSpec is present and needs explicit evaluation")
        reproductions.append({
            "model_id": model, "graph_candidates": len(rows),
            "stored_method_score_rows_verified": verified_score_rows,
            "max_abs_reproduction_errors": errors,
            "system_spec_available": False,
        })
        for method in METHOD_FIELDS:
            full_selections.append(dict(
                model_id=model, scope="complete_original_model_universe",
                **selection_summary(rows, scores, method),
            ))
    # These memberships are the previously published, exactly scoped filters.
    # Reusing IDs does not read or modify Native FPS/energy/quality measurements.
    dimensions = (
        "model_id", "setup_id", "direction", "precision", "comparison_backend",
        "output_endpoint_id", "boundary_class", "cohort", "tier",
    )
    membership_checks = {}
    for group in frozen_groups:
        if group["method"] not in AFFECTED:
            continue
        model, method = group["model_id"], group["method"]
        identities = group["candidate_ids"]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate historical subset identity")
        group_key = tuple(group[key] for key in dimensions)
        if group_key in membership_checks and membership_checks[group_key] != identities:
            raise ValueError("Compared historical methods have different candidate filters")
        membership_checks[group_key] = identities
        index = {row["case_id"]: row for row in by_model[model]}
        rows = [index[case] for case in identities]
        if not rows or len(rows) != int(group["n"]) or int(group["n_missing"]) != 0:
            raise ValueError("Incomplete historical candidate subset")
        summary = selection_summary(rows, model_scores[model], method)
        # evaluate_methods.evaluate_group deliberately suppresses selections
        # for n<3. Keep that eligibility gate, even when a mathematical order
        # exists for one or two candidates.
        if group["status"] == "insufficient_candidates":
            if len(rows) >= 3 or group["selected_case"] is not None:
                raise ValueError("Historical insufficient-candidate gate disagrees")
            for label in ("historical", "variant"):
                summary[label + "_selected_case"] = None
                summary[label + "_selected_score"] = None
                summary[label + "_top_ties"] = None
            summary["selected_case_changed"] = False
        else:
            if group["status"] not in ("ok", "constant_scores") or len(rows) < 3:
                raise ValueError("Unexpected historical group eligibility")
            if summary["historical_selected_case"] != group["selected_case"]:
                raise ValueError(
                    f"Recomputed subset selection disagrees for {group_key} {method}: "
                    f"{summary['historical_selected_case']} != {group['selected_case']}"
                )
            if len(summary["historical_top_ties"]) != int(group["score_top_ties"]):
                raise ValueError("Recomputed exact ties disagree with historical method_groups")
        subset_selections.append(dict(
            **{key: group[key] for key in dimensions},
            scope="unchanged_published_subset_membership_full_universe_scores",
            historical_status=group["status"],
            selection_evaluated=group["status"] != "insufficient_candidates",
            candidate_ids=identities, **summary,
        ))
    counts = {
        "graph_candidates": len(features), "models": len(by_model),
        "score_delta_rows": len(deltas), "frozen_method_scores_verified": len(stored_index),
        "full_universe_method_comparisons": len(full_selections),
        "published_subset_method_comparisons": len(subset_selections),
        "published_subset_selection_comparisons": sum(r["selection_evaluated"] for r in subset_selections),
        "published_subset_insufficient_candidate_groups": sum(not r["selection_evaluated"] for r in subset_selections),
    }
    changes = {}
    for method in METHOD_FIELDS:
        selected = [r for r in full_selections if r["method"] == method]
        changes[method] = {
            "score_changed_candidates": sum(r["score_changed_candidates"] for r in selected),
            "rank_changed_candidates": sum(r["rank_changed_candidates"] for r in selected),
            "full_universe_top1_changes": sum(r["selected_case_changed"] for r in selected),
            "published_subset_top1_changes": sum(
                r["selected_case_changed"] for r in subset_selections if r["method"] == method
            ) if method in AFFECTED else None,
        }
    audit = {
        "schema": "thesis-v53/score-units-and-rank-sensitivity-v1",
        "status": "completed_with_limits",
        "baseline": BASELINE, "variant": VARIANT,
        "variant_definition": "Only the temporary objective input cut_mb_val becomes cut_bytes/1048576; all other input fields, coefficients, profiles, candidate IDs and exact tie rules remain frozen.",
        "variant_role": "Unit sensitivity counterfactual; no tool patch, refit, new calibration, measurement or deployment selection update.",
        "historical_source_binding": bindings["historical_source_binding"],
        "normalization": "Complete original per-model strict saved graph universe before any measured/quality filters; both variants recompute the same weighted control over that full universe.",
        "ranking": "Ascending for all methods except stored_predicted_stream_fps descending; exact ties by boundary then case ID. No rounding and no fallback to measured candidates.",
        "subset_source": str(HISTORICAL / "tables/method_groups.csv"),
        "subset_scope": "Base and augmented cohorts and all three published tiers retained separately; original direction/precision/endpoint keys are retained. Scores always come from the complete graph universe.",
        "counts": counts, "changes": changes,
        "model_reproduction": reproductions,
        "full_universe_selections": full_selections,
        "published_subset_selections": subset_selections,
        "source_verification": verified,
        "limits": [
            "The graph-score sensitivity is evaluated for the frozen THESIS20 features only; no graph hash equivalence with later deployment graphs is inferred.",
            "The byte-identical d164aad6 method definitions and later published db729b9 source support the formulas; a later source commit alone does not prove historical execution.",
            "The ms/FPS-named fallback and the retained yolov7_streaming_v1 coefficients do not become physically calibrated through a unit conversion.",
            "All original GUI SystemSpecs are absent and the Native handover models are unconfigured; both methods stay unavailable.",
            "The current 450-deployment dataset and measured FPS, energy, quality, flags and selected deployment winners are not inputs to this counterfactual and are not changed.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "score_units.csv", field_overview())
    _write_csv(output / "score_rank_deltas.csv", deltas)
    (output / "score_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    return {
        "status": audit["status"], "counts": counts, "changes": changes,
        "variant": VARIANT,
        "outputs": ["score_units.csv", "score_rank_deltas.csv", "score_audit.json"],
        "source_bindings": str(STUDY / "inputs/scores/source_bindings.json"),
        "limitations": audit["limits"],
    }
