#!/usr/bin/env python3
"""R15 reference arithmetic and source-binding checks, with recomputed payloads exposed.

Adapted from R22 analysis/review_r15.py; original source hash and changes are in
publication-inputs/mlsys-r22/evidence_sources.json. Uses Python standard library
only. Source checks remain intact; calculation return values additionally expose
the regenerated folds, predictions, memberships, groups and process contrasts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

T95_DF4 = 2.7764451051977987


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, label):
    require(math.isclose(float(actual), float(expected), rel_tol=2e-11,
                         abs_tol=2e-9), f"{label}: {actual} != {expected}")


def yes(value):
    return value is True or str(value).lower() == "true"


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_manifest(root):
    manifest = read_json(root / "SOURCE_MANIFEST.json")
    seen = set()
    for entry in manifest["files"]:
        relative = entry["bundled_path"]
        path = root / relative
        require(relative not in seen, f"duplicate manifest entry: {relative}")
        require(path.resolve().is_relative_to(root.resolve()), "unsafe source path")
        require(path.is_file(), f"missing source: {relative}")
        require(path.stat().st_size == entry["size_bytes"], f"source size: {relative}")
        require(sha256(path) == entry["sha256"], f"source SHA256: {relative}")
        seen.add(relative)
    return {"files_verified": len(seen), "archives": manifest["archives"]}


def check_quality(base):
    data = rows(base / "results/r14_quality_audit.csv")
    require(len(data) == 450, "quality inventory must contain 450 configurations")
    by_id = {row["config_id"]: row for row in data}
    require(len(by_id) == len(data), "duplicate quality configuration")
    eligible, disagreements = [], 0
    for row in data:
        candidate, reference = float(row["primary_candidate"]), float(row["primary_reference"])
        require(math.isfinite(candidate) and math.isfinite(reference) and reference > 0,
                f"invalid quality observation: {row['config_id']}")
        loss = (reference - candidate) / reference
        close(loss, row["recomputed_loss"], "relative quality loss")
        require(yes(row["passes_5pct"]) == (loss <= .05), "numeric quality decision")
        if loss <= .05:
            eligible.append(row)
        cached = row["original_cached_policy_loss"]
        disagree = bool(cached) and not math.isclose(loss, float(cached),
                                                     rel_tol=1e-9, abs_tol=1e-12)
        require(disagree == yes(row["cached_policy_disagrees"]), "cached quality discrepancy")
        disagreements += disagree
    require(len(eligible) == 407 and disagreements == 53, "quality audit counts")
    counts = Counter((r["kind"], r["runner"]) for r in eligible)
    require(sum(r["kind"] == "full" for r in eligible) == 33, "eligible Full count")
    require(counts[("split", "native")] == counts[("split", "generic")] == 187,
            "eligible Native/Generic split counts")
    winners = rows(base / "results/r14_winner_configurations.csv")
    require(len(winners) == 14 and len({r["config_id"] for r in winners}) == 14,
            "global winner count")
    require(all(yes(by_id[r["config_id"]]["passes_5pct"]) for r in winners),
            "a global winner fails the numerical quality gate")
    summary = read_json(base / "results/audit_summary.json")
    require(summary["configurations"] == len(data), "saved quality audit size")
    require(summary["counts"]["passes_5pct"] == len(eligible), "saved eligible count")
    return {"configurations": len(data), "quality_eligible": len(eligible),
            "quality_excluded": len(data) - len(eligible), "full_eligible": 33,
            "native_split_eligible": 187, "generic_split_eligible": 187,
            "global_winner_configurations_eligible": 14,
            "cached_loss_disagreements": disagreements}, by_id


def fit_ridge(train):
    # Centering makes the unpenalized intercept explicit. Solve the independent
    # 2x2 slope system for MSE + lambda * sum(slopes**2), with lambda = 1.
    raw = [[float(r["prefix_compute_fraction"]), math.log1p(float(r["boundary_bytes"]))]
           for r in train]
    means = [statistics.mean(v[j] for v in raw) for j in range(2)]
    scales = [statistics.pstdev(v[j] for v in raw) or 1. for j in range(2)]
    z = [[(v[j] - means[j]) / scales[j] for j in range(2)] for v in raw]
    zm = [statistics.mean(v[j] for v in z) for j in range(2)]
    target = [math.log(float(r["native_fps"]) / float(r["generic_fps"])) for r in train]
    ym = statistics.mean(target)
    centered = [[v[j] - zm[j] for j in range(2)] for v in z]
    a = math.fsum(v[0] ** 2 for v in centered) + len(train)
    b = math.fsum(v[0] * v[1] for v in centered)
    d = math.fsum(v[1] ** 2 for v in centered) + len(train)
    rhs = [math.fsum(v[j] * (y - ym) for v, y in zip(centered, target)) for j in range(2)]
    determinant = a * d - b * b
    slopes = [(d * rhs[0] - b * rhs[1]) / determinant,
              (a * rhs[1] - b * rhs[0]) / determinant]
    beta = [ym - math.fsum(s * m for s, m in zip(slopes, zm)), *slopes]
    return beta, means, scales


def check_calibration(base, quality):
    result_dir = base / "results"
    candidates = rows(result_dir / "calibration_candidate_audit.csv")
    require(len(candidates) == 204 and len({r["config_id"] for r in candidates}) == 204,
            "candidate pair inventory")
    eligible = []
    for row in candidates:
        q = quality[row["config_id"]]
        gq = quality[row["generic_config_id"]]
        close(row["quality_value"], q["primary_candidate"], "candidate quality join")
        close(row["quality_reference_value"], q["primary_reference"], "reference quality join")
        close(row["quality_numeric_relative_loss"], q["recomputed_loss"], "candidate quality loss")
        passed = yes(q["passes_5pct"]) and yes(gq["passes_5pct"])
        require(passed == yes(row["quality_pass"]), "paired quality decision")
        if passed:
            require(yes(row["confirmed"]), "eligible pair lacks saved source confirmation")
            eligible.append(row)
    classifiers = [r for r in eligible if r["task"] == "classification"]
    detectors = [r for r in eligible if r["task"] == "detection"]
    require(len(classifiers) == 151 and len(detectors) == 36, "eligible task counts")
    groups = defaultdict(list)
    for row in eligible:
        require(float(row["native_fps"]) > 0 and float(row["generic_fps"]) > 0,
                "nonpositive paired throughput")
        groups[(row["model"], row["setup"], row["task"])].append(row)
    require(sum(k[2] == "classification" for k in groups) == 9, "classifier groups")
    require(sum(k[2] == "detection" for k in groups) == 12, "detector groups")
    require(all(len(g) == 3 for k, g in groups.items() if k[2] == "detection"),
            "detector candidate count")
    folds = [r for r in rows(result_dir / "calibration_folds.csv") if r["cohort"] == "confirmed"]
    saved_predictions = {r["config_id"]: r for r in rows(result_dir / "calibration_predictions.csv")
                         if r["cohort"] == "confirmed"}
    memberships = [r for r in rows(result_dir / "calibration_memberships.csv")
                   if r["cohort"] == "confirmed"]
    require(len(folds) == 9 and len(saved_predictions) == 151, "fold/prediction count")
    predicted = {}
    fold_payload = []
    prediction_payload = []
    membership_payload = []
    for fold in folds:
        train = [r for r in classifiers if r["setup"] == fold["setup"]
                 and r["model"] != fold["held_out_architecture"]]
        test = [r for r in classifiers if r["setup"] == fold["setup"]
                and r["model"] == fold["held_out_architecture"]]
        require(len({r["model"] for r in train}) == 2, "whole-architecture training split")
        require(not ({r["config_id"] for r in train} & {r["config_id"] for r in test}),
                "train/test leakage")
        for role, data in (("train", train), ("test", test)):
            saved_ids = {r["config_id"] for r in memberships
                         if r["fold_id"] == fold["fold_id"] and r["role"] == role}
            require(saved_ids == {r["config_id"] for r in data}, "saved fold membership")
            require(int(fold[f"{role}_n"]) == len(data), "fold size")
        require(all(yes(r["feature_available"]) and yes(r["feature_graph_identity_verified"])
                    for r in train + test), "missing saved feature identity")
        beta, means, scales = fit_ridge(train)
        fold_payload.append({"fold_id": fold["fold_id"], "setup": fold["setup"], "held_out_architecture": fold["held_out_architecture"], "train_n": len(train), "test_n": len(test), "lambda": 1., "beta": beta, "train_mean": means, "train_std": scales})
        membership_payload.extend({"fold_id": fold["fold_id"], "role": role, "uid": r["config_id"], "model": r["model"]} for role, members in (("train", train), ("test", test)) for r in members)
        for j in range(3):
            close(beta[j], fold[f"beta{j}"], "ridge coefficient")
        for j, feature in enumerate(("prefix_fraction", "log1p_bytes")):
            close(means[j], fold[f"train_mean_{feature}"], "training feature mean")
            close(scales[j], fold[f"train_std_{feature}"], "training feature scale")
        for row in test:
            raw = [float(row["prefix_compute_fraction"]), math.log1p(float(row["boundary_bytes"]))]
            log_ratio = beta[0] + math.fsum(beta[j + 1] * (raw[j] - means[j]) / scales[j]
                                           for j in range(2))
            value = float(row["generic_fps"]) * math.exp(log_ratio)
            predicted[row["config_id"]] = value
            prediction_payload.append({"fold_id": fold["fold_id"], "uid": row["config_id"], "generic_uid": row["generic_config_id"], "predicted_log_native_generic_ratio": log_ratio, "predicted_native_fps": value})
            close(log_ratio, saved_predictions[row["config_id"]]["predicted_log_native_generic_ratio"],
                  "held-out predicted ratio")
            close(value, saved_predictions[row["config_id"]]["predicted_native_fps"],
                  "held-out predicted FPS")
    metrics = [r for r in rows(result_dir / "calibration_groups.csv") if r["cohort"] == "confirmed"]
    recalculated = defaultdict(list)
    group_payload = []
    for metric in metrics:
        group = groups[(metric["model"], metric["setup"], metric["task"])]
        n, k, method = len(group), int(metric["k"]), metric["method"]
        require(n == int(metric["n"]), "budget group size")
        unavailable = k > n or (metric["task"] == "detection" and
                                method in {"calibrated_generic", "boundary_bytes_only_recomputed"})
        payload = {"cohort": "confirmed", "model": metric["model"], "setup": metric["setup"], "task": metric["task"], "method": method, "k": k, "n": n, "candidate_uids": [r["config_id"] for r in group]}
        if unavailable:
            group_payload.append({**payload, "status": "unavailable", "selected_uids": [], "native_best_fps": max(float(r["native_fps"]) for r in group), "selected_native_fps_or_expectation": None, "regret_pct": None, "winner_coverage": None})
            require(metric["status"] != "evaluated" and
                    metric["native_regret_pct_or_expectation"] == "", "unavailable budget must stay unavailable")
            continue
        require(metric["status"] == "evaluated", "missing expected budget result")
        best = max(float(r["native_fps"]) for r in group)
        winner_ids = {r["config_id"] for r in group if float(r["native_fps"]) == best}
        if method == "uniform_random":
            # Exact finite distribution of the maximum, including ties.
            values = sorted(float(r["native_fps"]) for r in group)
            combinations = math.comb(n, k)
            selected = math.fsum(v * math.comb(i, k - 1) for i, v in enumerate(values)
                                 if i >= k - 1) / combinations
            coverage = 1 - math.comb(n - len(winner_ids), k) / combinations
            require(int(metric["random_subset_count"]) == combinations, "random subset count")
        else:
            if method == "generic":
                key = lambda r: (-float(r["generic_fps"]), r["config_id"])
            elif method == "calibrated_generic":
                key = lambda r: (-predicted[r["config_id"]], r["config_id"])
            else:
                require(method == "boundary_bytes_only_recomputed", "unknown selection method")
                key = lambda r: (float(r["boundary_bytes"]), int(r["boundary"]), r["case"])
            chosen = sorted(group, key=key)[:k]
            selected_ids = [r["config_id"] for r in chosen]
            require(selected_ids == json.loads(metric["selected_ids"]), "selected configurations")
            selected = max(float(r["native_fps"]) for r in chosen)
            coverage = float(bool(set(selected_ids) & winner_ids))
        regret = 100 * (1 - selected / best)
        group_payload.append({**payload, "status": "evaluated", "selected_uids": [] if method == "uniform_random" else selected_ids, "native_best_fps": best, "selected_native_fps_or_expectation": selected, "regret_pct": regret, "winner_coverage": coverage, "random_subset_count": combinations if method == "uniform_random" else None})
        close(best, metric["native_best_fps"], "group oracle")
        close(selected, metric["selected_native_fps_or_expectation"], "selected Native FPS")
        close(regret, metric["native_regret_pct_or_expectation"], "group regret")
        close(coverage, metric["winner_coverage_or_probability"], "winner coverage")
        recalculated[(metric["task"], method, k)].append((regret, coverage))
    summary_values = {}
    for saved in rows(result_dir / "calibration_summary.csv"):
        if saved["cohort"] != "confirmed":
            continue
        key = (saved["task"], saved["method"], int(saved["k"]))
        data = recalculated[key]
        require(len(data) == int(saved["groups_evaluated"]), "summary denominator")
        if not data:
            require(saved["mean_native_regret_pct_or_expectation"] == "", "missing summary stays missing")
            continue
        regret, coverage = (statistics.mean(v[j] for v in data) for j in range(2))
        close(regret, saved["mean_native_regret_pct_or_expectation"], "mean budget regret")
        close(coverage, saved["mean_winner_coverage_or_probability"], "mean budget coverage")
        summary_values["|".join(map(str, key))] = {"groups": len(data), "regret_pct": regret,
                                                       "winner_coverage": coverage}
    return {"eligible_classifier_pairs": 151, "classifier_groups": 9,
            "eligible_detector_pairs": 36, "detector_groups": 12,
            "refitted_architecture_disjoint_folds": len(folds),
            "recomputed_predictions": len(predicted), "budget_results": summary_values, "folds": fold_payload, "predictions": prediction_payload, "memberships": membership_payload, "groups": group_payload}


def check_mechanism(base, resnet=False, prior_native=False):
    stem = "replication_analysis" if resnet else "mechanism_confirmation"
    data = rows(base / f"results/{stem}_cells.csv")
    phase_name = "replication" if prior_native else "primary"
    process_count, cells_per_block = (20, 4) if prior_native else (40, 8)
    if not resnet:
        extension = [r for r in data if r["phase"] == "extension"]
        require(len(extension) == 40 and all(not yes(r["included"]) for r in extension),
                "untriggered RegNet extension must remain unmeasured")
        data = [r for r in data if r["phase"] == phase_name]
    require(len(data) == process_count and all(yes(r["included"]) for r in data), "complete process series")
    require(len({r["worker_pid"] for r in data}) == process_count, "distinct worker PIDs")
    require(all(int(r["attempt_count"]) == 1 for r in data), "unexpected retries")
    protocol_path = base / "PROTOCOL.json"
    protocol, protocol_hash = read_json(protocol_path), sha256(protocol_path)
    phase = protocol["phases"][phase_name]
    require(len(phase["schedule"]) == process_count and phase["blocks"] == [1, 2, 3, 4, 5],
            "frozen complete-block design")
    frozen_ns = int(datetime.fromisoformat(protocol["frozen_at_utc"].replace("Z", "+00:00")).timestamp() * 1e9)
    case_map = {r["case_id"]: r for r in protocol["cases"]}
    by_cell, previous_finish = {}, None
    for row in sorted(data, key=lambda r: int(r["schedule_order"])):
        expected = phase["schedule"][int(row["schedule_order"]) - 1]
        require(all(str(row[k]) == str(expected[k]) for k in ("case_id", "variant", "block")),
                "frozen execution order")
        relative = row["report_path"][row["report_path"].index("results/"):]
        raw_path = base / relative
        require(sha256(raw_path) == row["report_sha256"], "raw report binding")
        raw = read_json(raw_path)
        require(raw["protocol_sha256"] == protocol_hash, "raw protocol binding")
        require(raw["status"] == "complete" and raw["mode"] == "duration", "raw completion status")
        require(str(raw["pid"]) == row["worker_pid"], "raw process identity")
        require(raw["started_time_ns"] > frozen_ns, "protocol frozen before measurement")
        if previous_finish is not None:
            require(raw["started_time_ns"] > previous_finish, "nonoverlapping process execution")
        previous_finish = raw["finished_time_ns"]
        require(str(raw["block"]) == row["block"] and raw["identity"]["case_id"] == row["cut"],
                "raw cell identity")
        require(raw["chain"] == ("native" if row["variant"].startswith("N_") else "generic")
                and raw["schedule"] == row["variant"].split("_", 1)[1], "raw runtime/schedule identity")
        require(raw["accepted_work_drained"] and not raw["energy_measured"], "drain and energy scope")
        close(raw["warmup_duration_s"], 30, "warm-up duration")
        close(raw["admission_window_seconds"], 60, "admission duration")
        required = {r["role"]: r["sha256"] for r in case_map[row["case_id"]]["required_artifacts"]}
        require(raw["artifact_identity"]["part1_runtime"]["sha256"] == required["hef"]
                and raw["artifact_identity"]["engine"]["sha256"] == required["engine"],
                "raw runtime artifacts match frozen per-cut hashes")
        metrics = raw["metrics"]
        if raw["chain"] == "native":
            count, seconds = int(metrics["completed_work_units"]), float(metrics["makespan_ms"]) / 1000
            require(count == metrics["postprocess_completed_frames"] == metrics["produced_frames"]
                    == metrics["consumed_frames"], "Native completed/drained counts")
            require(metrics["task_complete"] and metrics["postprocess_completion_verified"]
                    and metrics["completed_task_stage"] == "classification_top1_top5", "Native endpoint")
        else:
            count, seconds = int(metrics["completed_task_count"]), float(metrics["measured_makespan_seconds"])
            require(count == metrics["admitted_task_count"] == metrics["processor_count_delta"],
                    "Generic completed/drained counts")
            require(metrics["fill_and_drain_included"] and metrics["postprocess_timed"]
                    and metrics["output_materialization_timed"], "Generic completed endpoint")
        require(seconds >= 60 and count > 0, "full measured makespan")
        close(seconds, raw["measurement_time_seconds"], "raw makespan")
        close(count, raw["completed_work_units"], "raw completed count")
        close(seconds, row["measurement_time_seconds"], "cell makespan")
        close(count, row["completed_work_units"], "cell completed count")
        fps = count / seconds
        close(fps, raw["completed_task_fps"], "raw completed-task rate")
        close(fps, row["completed_task_fps"], "CSV completed-task rate")
        key = (int(row["block"]), row["variant"], row["cut"])
        require(key not in by_cell, "duplicate mechanism cell")
        by_cell[key] = fps
    numerator, denominator = ("b095", "b002") if resnet or prior_native else ("b123", "b052")
    variants = ("N_product", "N_single") if prior_native else ("G_product", "G_single", "N_product", "N_single")
    calculated = {}
    for block in range(1, 6):
        values = {v: math.log(by_cell[(block, v, numerator)] / by_cell[(block, v, denominator)])
                  for v in variants}
        values["native_schedule_effect"] = values["N_product"] - values["N_single"]
        if not prior_native:
            values["generic_schedule_effect"] = values["G_product"] - values["G_single"]
            values["interaction"] = values["native_schedule_effect"] - values["generic_schedule_effect"]
        calculated.update({(block, name): value for name, value in values.items()})
    block_rows = rows(base / f"results/{stem}_blocks.csv")
    if not resnet:
        block_rows = [r for r in block_rows if r["phase"] == phase_name]
    n_contrasts = 3 if prior_native else 7
    require(len(block_rows) == len(calculated) == n_contrasts * 5, "contrasts per complete block")
    for row in block_rows:
        value = calculated[(int(row["block"]), row["contrast"])]
        require(yes(row["whole_block_included"]) and int(row["admitted_cells"]) == cells_per_block, "block inclusion")
        close(value, row["log_ratio"], "block log contrast")
        close(math.exp(value), row["ratio"], "block ratio")
    suffix = "summaries" if resnet else "summary"
    summaries = rows(base / f"results/{stem}_{suffix}.csv")
    if not resnet:
        summaries = [r for r in summaries if r["cohort"] == phase_name]
    require(len(summaries) == n_contrasts, "mechanism summaries")
    estimates = {}
    for row in summaries:
        values = [calculated[(block, row["contrast"])] for block in range(1, 6)]
        mean, sd = statistics.mean(values), statistics.stdev(values)
        se = sd / math.sqrt(5)
        require(int(row["n_blocks"]) == 5 and int(row["df"]) == 4, "independent block denominator")
        close(T95_DF4, row["t95"], "nominal t critical value")
        expected = {"mean_log": mean, "sd_log": sd, "se_log": se,
                    "log_ci95_low": mean - T95_DF4 * se,
                    "log_ci95_high": mean + T95_DF4 * se,
                    "geometric_mean": math.exp(mean),
                    "ci95_low": math.exp(mean - T95_DF4 * se),
                    "ci95_high": math.exp(mean + T95_DF4 * se)}
        for key, value in expected.items():
            close(value, row[key], f"{row['contrast']} {key}")
        estimates[row["contrast"]] = expected
    return {"independent_processes": process_count, "randomized_complete_blocks": 5,
            "raw_reports_recomputed": process_count, "block_contrasts": n_contrasts * 5, "summary_contrasts": n_contrasts,
            "estimates": estimates, "blocks": [{"block": block, "contrast": name, "log_ratio": value, "ratio": math.exp(value)} for (block, name), value in sorted(calculated.items())], "process_uids": [r["report_sha256"] for r in data]}

