from __future__ import annotations

"""Read-only analysis of the original 5--600-s duration campaign.

This module intentionally keeps protocol-duration effects separate from the
common-reference sampling-only analysis.  It accepts the historic results tree
as it exists on ``twix`` and falls back to the explicitly configured thesis
summary only when the raw tree is unavailable or cannot provide a complete
workload row.  Fallback rows are always labelled as such; they are never
presented as reprocessed raw measurements.
"""

from collections import defaultdict
from pathlib import Path
import math
import re
import shutil
from typing import Any, Iterable

import numpy as np

from .config import AnalysisConfig, DurationCampaignConfig
from .utils import (
    LOGGER,
    load_yaml,
    quantile,
    read_csv,
    read_json,
    utc_now_iso,
    write_csv,
    write_json,
)


_LEGACY_DURATION_SCHEMA_VERSION = 3
_METHOD_KEYS: tuple[tuple[str, str], ...] = (
    ("oscilloscope_results", "PicoScope"),
    ("firmware_results", "u.RECS"),
    ("jetson_results", "Jetson INA3221"),
    ("shelly_results", "Shelly Plus Plug S"),
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _walk_mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def _first_numeric(value: Any, names: tuple[str, ...]) -> float | None:
    lowered = {name.lower() for name in names}
    for mapping in _walk_mappings(value):
        for key, candidate in mapping.items():
            if str(key).lower() in lowered:
                number = _finite(candidate)
                if number is not None:
                    return number
    return None


def _method_energy_duration(payload: Any) -> tuple[float, float] | None:
    if not isinstance(payload, dict):
        return None
    energy = _first_numeric(
        payload,
        (
            "energy",
            "energy_j",
            "total_energy",
            "total_energy_j",
            "measured_energy",
        ),
    )
    duration = _first_numeric(
        payload,
        (
            "duration",
            "duration_s",
            "measurement_duration",
            "measurement_duration_s",
            "benchmark_duration",
            "benchmark_duration_s",
        ),
    )
    if energy is None or duration is None or duration <= 0:
        return None
    return float(energy), float(duration)


def _normalise_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _duration_from_path(
    path: Path,
    expected: tuple[float, ...],
    data: dict[str, Any],
) -> float | None:
    metadata = _first_numeric(
        data,
        (
            "requested_duration_s",
            "benchmark_duration_s",
            "run_duration_s",
            "target_duration_s",
        ),
    )
    tolerance = 1e-6
    if metadata is not None:
        nearest = min(expected, key=lambda item: abs(item - metadata))
        if abs(nearest - metadata) <= max(tolerance, 1e-3 * nearest):
            return float(nearest)

    candidates: list[float] = []
    for component in path.parts:
        token = component.lower()
        patterns = (
            r"^(\d+(?:\.\d+)?)s$",
            r"^(\d+(?:\.\d+)?)sec(?:ond)?s?$",
            r"^(?:duration|dur|runtime|length)[_-]?(\d+(?:\.\d+)?)(?:s|sec(?:ond)?s?)?$",
            r"^(\d+(?:\.\d+)?)$",
        )
        for pattern in patterns:
            match = re.fullmatch(pattern, token)
            if match:
                candidates.append(float(match.group(1)))
                break
    for candidate in reversed(candidates):
        nearest = min(expected, key=lambda item: abs(item - candidate))
        if abs(nearest - candidate) <= max(tolerance, 1e-6 * max(1.0, nearest)):
            return float(nearest)
    return None


def _run_from_path(path: Path, data: dict[str, Any]) -> int | None:
    run_value = _first_numeric(data, ("run", "run_id", "repetition", "repetition_id"))
    if run_value is not None and abs(run_value - round(run_value)) < 1e-9:
        return int(round(run_value))
    for component in reversed(path.parts):
        token = component.lower()
        if token.isdigit():
            return int(token)
        match = re.fullmatch(r"(?:run|rep|repetition)[_-]?(\d+)", token)
        if match:
            return int(match.group(1))
    return None


def _metadata_text(data: dict[str, Any]) -> str:
    values: list[str] = []
    wanted = {
        "workload",
        "benchmark",
        "benchmark_name",
        "model",
        "precision",
        "datatype",
        "data_type",
        "mode",
    }
    for mapping in _walk_mappings(data):
        for key, value in mapping.items():
            if str(key).lower() in wanted and isinstance(value, (str, int, float)):
                values.append(str(value))
    return " ".join(values)


def _workload_from_path(path: Path, data: dict[str, Any]) -> str | None:
    text = " ".join(_normalise_token(value) for value in path.parts)
    metadata = _normalise_token(_metadata_text(data))
    haystack = f"{text} {metadata}"

    variable_markers = ("variable", "random_pattern", "inconsistent", "inkonsistent", "bursty")
    if "yolo" in haystack and any(marker in haystack for marker in variable_markers):
        return "Variable YOLO"

    family: str | None
    if "gemm" in haystack:
        family = "GEMM"
    elif "yolo" in haystack:
        family = "YOLO"
    else:
        return None

    if "int8" in haystack:
        precision = "INT8"
    elif "fp16" in haystack or "float16" in haystack or "half" in haystack:
        precision = "FP16"
    elif "tf32" in haystack or "fp32" in haystack or "float32" in haystack:
        # The thesis table labels the first GEMM column FP32, while some paper
        # drafts call the same TensorRT configuration TF32.  Preserve the
        # thesis-facing label used by the configured fallback rows.
        precision = "FP32"
    else:
        return None
    return f"{family} {precision}"


def _summary(values: Iterable[float]) -> dict[str, float | int]:
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {
            "n": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "std": float("nan"),
            "q05": float("nan"),
            "q95": float("nan"),
            "minimum": float("nan"),
            "maximum": float("nan"),
        }
    return {
        "n": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array, ddof=0)),
        "q05": quantile(array, 0.05),
        "q95": quantile(array, 0.95),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def _scan_raw_campaign(campaign: DurationCampaignConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    root = campaign.root
    if not root.is_dir():
        return raw, [{"path": str(root), "reason": "campaign_root_not_available"}]

    yaml_paths = sorted(root.rglob("results.yaml"))
    if not yaml_paths:
        return raw, [{"path": str(root), "reason": "no_results_yaml_found"}]

    for yaml_path in yaml_paths:
        try:
            data = load_yaml(yaml_path)
        except Exception as error:  # read-only diagnostic path
            skipped.append(
                {
                    "path": str(yaml_path),
                    "reason": "unreadable_yaml",
                    "detail": f"{type(error).__name__}: {error}",
                }
            )
            continue

        relative = yaml_path.relative_to(root)
        duration = _duration_from_path(relative, campaign.expected_durations_s, data)
        run = _run_from_path(relative.parent, data)
        workload = _workload_from_path(relative, data)
        if duration is None or run is None or workload is None:
            skipped.append(
                {
                    "path": str(yaml_path),
                    "reason": "could_not_infer_identity",
                    "detail": f"workload={workload!r}, duration={duration!r}, run={run!r}",
                }
            )
            continue

        found = 0
        for source_key, method in _METHOD_KEYS:
            extracted = _method_energy_duration(data.get(source_key))
            if extracted is None:
                continue
            energy_j, measured_duration_s = extracted
            raw.append(
                {
                    "workload": workload,
                    "requested_duration_s": duration,
                    "run": run,
                    "method": method,
                    "variant": "raw",
                    "energy_j": energy_j,
                    "measured_duration_s": measured_duration_s,
                    "mean_power_w": energy_j / measured_duration_s,
                    "results_yaml": str(yaml_path),
                    "source_kind": "raw_results_yaml",
                }
            )
            found += 1
        if found == 0:
            skipped.append(
                {
                    "path": str(yaml_path),
                    "reason": "no_supported_energy_result",
                    "detail": "Expected oscilloscope/firmware/jetson/shelly energy and duration",
                }
            )
    return raw, skipped


def _method_summaries(
    raw: list[dict[str, Any]],
    correction_factor: float,
    values_already_include_correction_factor: bool,
) -> list[dict[str, Any]]:
    expanded = list(raw)
    # The archived duration results already contain the setup-specific 0.97
    # correction in the current dataset.  Applying it again would create an
    # artificial ~3% bias.  Retain the optional branch only for genuinely
    # uncorrected legacy trees.
    if not values_already_include_correction_factor:
        for row in raw:
            if row["method"] == "u.RECS":
                corrected = dict(row)
                corrected["variant"] = "factor_corrected"
                corrected["energy_j"] = float(row["energy_j"]) * correction_factor
                corrected["mean_power_w"] = float(row["mean_power_w"]) * correction_factor
                expanded.append(corrected)

    groups: dict[tuple[str, float, str, str], list[float]] = defaultdict(list)
    for row in expanded:
        groups[
            (
                str(row["workload"]),
                float(row["requested_duration_s"]),
                str(row["method"]),
                str(row["variant"]),
            )
        ].append(float(row["mean_power_w"]))

    result: list[dict[str, Any]] = []
    for (workload, duration, method, variant), values in sorted(groups.items()):
        stats = _summary(values)
        result.append(
            {
                "workload": workload,
                "requested_duration_s": duration,
                "method": method,
                "variant": variant,
                "n": stats["n"],
                "mean_power_w_mean": stats["mean"],
                "mean_power_w_median": stats["median"],
                "mean_power_w_std": stats["std"],
                "mean_power_w_q05": stats["q05"],
                "mean_power_w_q95": stats["q95"],
                "source_kind": "raw_results_yaml",
            }
        )
    return result


def _reference_convergence(
    method_summary: list[dict[str, Any]],
    campaign: DurationCampaignConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pico = [
        row
        for row in method_summary
        if row["method"] == "PicoScope" and row["variant"] == "raw"
        and int(row["n"]) >= campaign.minimum_runs_per_cell
    ]
    by_workload: dict[str, dict[float, dict[str, Any]]] = defaultdict(dict)
    for row in pico:
        by_workload[str(row["workload"])][float(row["requested_duration_s"])] = row

    convergence: list[dict[str, Any]] = []
    thresholds: list[dict[str, Any]] = []
    fallback_by_workload = {
        str(row["workload"]): row for row in campaign.fallback_rows
    }
    workloads = sorted(set(by_workload) | set(fallback_by_workload))
    for workload in workloads:
        duration_map = by_workload.get(workload, {})
        reference = duration_map.get(campaign.reference_duration_s)
        complete_raw = reference is not None and bool(duration_map)
        if complete_raw:
            reference_power = float(reference["mean_power_w_median"])
            for duration, row in sorted(duration_map.items()):
                power = float(row["mean_power_w_median"])
                signed = 100.0 * (power - reference_power) / reference_power
                convergence.append(
                    {
                        "workload": workload,
                        "duration_s": duration,
                        "reference_duration_s": campaign.reference_duration_s,
                        "mean_power_w_median": power,
                        "reference_mean_power_w_median": reference_power,
                        "difference_to_reference_pct": signed,
                        "abs_difference_to_reference_pct": abs(signed),
                        "n": row["n"],
                        "source_kind": "raw_results_yaml",
                    }
                )
            raw_rows = [row for row in convergence if row["workload"] == workload]
            duration_5 = next((row for row in raw_rows if math.isclose(float(row["duration_s"]), 5.0)), None)
            passing = sorted(
                float(row["duration_s"])
                for row in raw_rows
                if float(row["abs_difference_to_reference_pct"]) <= campaign.steady_state_tolerance_pct
            )
            if duration_5 is not None and passing:
                thresholds.append(
                    {
                        "workload": workload,
                        "difference_5_to_reference_pct": float(duration_5["abs_difference_to_reference_pct"]),
                        "first_duration_within_tolerance_s": passing[0],
                        "tolerance_pct": campaign.steady_state_tolerance_pct,
                        "reference_duration_s": campaign.reference_duration_s,
                        "source_kind": "raw_results_yaml",
                    }
                )
                continue

        fallback = fallback_by_workload.get(workload)
        if campaign.use_thesis_fallback and fallback is not None:
            thresholds.append(
                {
                    "workload": workload,
                    "difference_5_to_reference_pct": float(fallback["difference_5_to_reference_pct"]),
                    "first_duration_within_tolerance_s": float(fallback["first_duration_within_tolerance_s"]),
                    "tolerance_pct": campaign.steady_state_tolerance_pct,
                    "reference_duration_s": campaign.reference_duration_s,
                    "source_kind": "thesis_summary_fallback",
                }
            )
    return convergence, thresholds


def _urecs_pairs(
    raw: list[dict[str, Any]],
    correction_factor: float,
    values_already_include_correction_factor: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup: dict[tuple[str, float, int, str], dict[str, Any]] = {}
    for row in raw:
        lookup[
            (
                str(row["workload"]),
                float(row["requested_duration_s"]),
                int(row["run"]),
                str(row["method"]),
            )
        ] = row

    paired: list[dict[str, Any]] = []
    for workload, duration, run, method in sorted(lookup):
        if method != "PicoScope":
            continue
        pico = lookup[(workload, duration, run, "PicoScope")]
        urecs = lookup.get((workload, duration, run, "u.RECS"))
        if urecs is None:
            continue
        pico_power = float(pico["mean_power_w"])
        raw_power = float(urecs["mean_power_w"])
        variants = (
            (("stored_processed", 1.0),)
            if values_already_include_correction_factor
            else (("raw", 1.0), ("factor_corrected", correction_factor))
        )
        for variant, factor in variants:
            candidate = raw_power * factor
            error = 100.0 * (candidate - pico_power) / pico_power
            paired.append(
                {
                    "workload": workload,
                    "requested_duration_s": duration,
                    "run": run,
                    "variant": variant,
                    "pico_mean_power_w": pico_power,
                    "urecs_mean_power_w": candidate,
                    "urecs_minus_pico_w": candidate - pico_power,
                    "urecs_vs_pico_error_pct": error,
                    "abs_error_pct": abs(error),
                    "source_kind": "raw_results_yaml",
                }
            )

    summaries: list[dict[str, Any]] = []
    variants_to_summarise = (
        ("stored_processed",)
        if values_already_include_correction_factor
        else ("raw", "factor_corrected")
    )
    for variant in variants_to_summarise:
        selected = [row for row in paired if row["variant"] == variant]
        if selected:
            stats = _summary(row["urecs_vs_pico_error_pct"] for row in selected)
            abs_stats = _summary(row["abs_error_pct"] for row in selected)
            summaries.append(
                {
                    "scope": "all",
                    "variant": variant,
                    "n": stats["n"],
                    "error_median_pct": stats["median"],
                    "error_q05_pct": stats["q05"],
                    "error_q95_pct": stats["q95"],
                    "abs_error_median_pct": abs_stats["median"],
                    "abs_error_q95_pct": abs_stats["q95"],
                    "abs_error_max_pct": abs_stats["maximum"],
                    "source_kind": "raw_results_yaml",
                    "note": "",
                }
            )
        for workload in sorted({str(row["workload"]) for row in selected}):
            workload_rows = [row for row in selected if row["workload"] == workload]
            stats = _summary(row["urecs_vs_pico_error_pct"] for row in workload_rows)
            abs_stats = _summary(row["abs_error_pct"] for row in workload_rows)
            summaries.append(
                {
                    "scope": workload,
                    "variant": variant,
                    "n": stats["n"],
                    "error_median_pct": stats["median"],
                    "error_q05_pct": stats["q05"],
                    "error_q95_pct": stats["q95"],
                    "abs_error_median_pct": abs_stats["median"],
                    "abs_error_q95_pct": abs_stats["q95"],
                    "abs_error_max_pct": abs_stats["maximum"],
                    "source_kind": "raw_results_yaml",
                    "note": "",
                }
            )
    return paired, summaries


def _copy_to_canonical(output_root: Path, source_root: Path) -> None:
    target = output_root / "rate_duration" / "duration_campaign"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "raw_measurements.csv",
        "method_summary.csv",
        "reference_convergence.csv",
        "reference_convergence_thresholds.csv",
        "urecs_vs_pico_per_run.csv",
        "urecs_vs_pico_summary.csv",
        "inventory.csv",
        "skipped.csv",
        "source.json",
    ):
        source = source_root / name
        if source.is_file():
            shutil.copy2(source, target / name)


def analyse_legacy_duration_campaign(
    cfg: AnalysisConfig,
    *,
    force: bool = False,
) -> dict[str, Path | str]:
    campaign = cfg.duration_sensitivity.campaign
    root = cfg.output_root / "duration_sensitivity" / "legacy_duration_campaign"
    root.mkdir(parents=True, exist_ok=True)
    source_path = root / "source.json"
    expected_outputs = (
        root / "reference_convergence_thresholds.csv",
        root / "urecs_vs_pico_summary.csv",
        source_path,
    )
    if not force and all(path.is_file() for path in expected_outputs):
        cached_source = read_json(source_path)
        cache_matches = (
            int(cached_source.get("schema_version", 0))
            == _LEGACY_DURATION_SCHEMA_VERSION
            and math.isclose(
                float(cached_source.get("urecs_correction_factor", float("nan"))),
                float(campaign.urecs_correction_factor),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            and bool(
                cached_source.get(
                    "urecs_values_already_include_correction_factor", False
                )
            )
            == bool(campaign.urecs_values_already_include_correction_factor)
        )
        if cache_matches:
            _copy_to_canonical(cfg.output_root, root)
            return {
                "source_type": cached_source.get("source_type", "cached"),
                "raw": root / "raw_measurements.csv",
                "method_summary": root / "method_summary.csv",
                "convergence": root / "reference_convergence.csv",
                "thresholds": root / "reference_convergence_thresholds.csv",
                "paired": root / "urecs_vs_pico_per_run.csv",
                "urecs_summary": root / "urecs_vs_pico_summary.csv",
            }
        LOGGER.info(
            "Recomputing legacy duration campaign because correction semantics or schema changed"
        )

    if not campaign.enabled:
        raw: list[dict[str, Any]] = []
        skipped = [{"path": str(campaign.root), "reason": "campaign_disabled", "detail": ""}]
    else:
        raw, skipped = _scan_raw_campaign(campaign)

    method_summary = _method_summaries(
        raw,
        campaign.urecs_correction_factor,
        campaign.urecs_values_already_include_correction_factor,
    )
    convergence, threshold_rows = _reference_convergence(method_summary, campaign)
    paired, urecs_summary = _urecs_pairs(
        raw,
        campaign.urecs_correction_factor,
        campaign.urecs_values_already_include_correction_factor,
    )

    if not urecs_summary:
        urecs_summary = [
            {
                "scope": "thesis_summary",
                "variant": (
                    "stored_processed"
                    if campaign.urecs_values_already_include_correction_factor
                    else "factor_corrected"
                ),
                "n": "",
                "error_median_pct": "",
                "error_q05_pct": "",
                "error_q95_pct": "",
                "abs_error_median_pct": "",
                "abs_error_q95_pct": "",
                "abs_error_max_pct": "",
                "source_kind": "thesis_summary_fallback",
                "note": (
                    "The thesis reports corrected u.RECS values within about ±0.5% "
                    "of the PicoScope setup across the duration sweeps; raw per-run "
                    "results were not available to recompute a q95 value."
                ),
            }
        ]

    source_kinds = {str(row["source_kind"]) for row in threshold_rows}
    if raw and source_kinds == {"raw_results_yaml"}:
        source_type = "raw_results_yaml"
    elif raw and "thesis_summary_fallback" in source_kinds:
        source_type = "raw_plus_thesis_fallback"
    elif source_kinds:
        source_type = "thesis_summary_fallback"
    else:
        source_type = "not_available"

    raw_fields = (
        "workload", "requested_duration_s", "run", "method", "variant",
        "energy_j", "measured_duration_s", "mean_power_w", "results_yaml",
        "source_kind",
    )
    write_csv(root / "raw_measurements.csv", raw, fieldnames=raw_fields)
    write_csv(
        root / "method_summary.csv",
        method_summary,
        fieldnames=(
            "workload", "requested_duration_s", "method", "variant", "n",
            "mean_power_w_mean", "mean_power_w_median", "mean_power_w_std",
            "mean_power_w_q05", "mean_power_w_q95", "source_kind",
        ),
    )
    write_csv(
        root / "reference_convergence.csv",
        convergence,
        fieldnames=(
            "workload", "duration_s", "reference_duration_s",
            "mean_power_w_median", "reference_mean_power_w_median",
            "difference_to_reference_pct", "abs_difference_to_reference_pct",
            "n", "source_kind",
        ),
    )
    write_csv(
        root / "reference_convergence_thresholds.csv",
        threshold_rows,
        fieldnames=(
            "workload", "difference_5_to_reference_pct",
            "first_duration_within_tolerance_s", "tolerance_pct",
            "reference_duration_s", "source_kind",
        ),
    )
    write_csv(
        root / "urecs_vs_pico_per_run.csv",
        paired,
        fieldnames=(
            "workload", "requested_duration_s", "run", "variant",
            "pico_mean_power_w", "urecs_mean_power_w", "urecs_minus_pico_w",
            "urecs_vs_pico_error_pct", "abs_error_pct", "source_kind",
        ),
    )
    write_csv(
        root / "urecs_vs_pico_summary.csv",
        urecs_summary,
        fieldnames=(
            "scope", "variant", "n", "error_median_pct", "error_q05_pct",
            "error_q95_pct", "abs_error_median_pct", "abs_error_q95_pct",
            "abs_error_max_pct", "source_kind", "note",
        ),
    )

    inventory_rows: list[dict[str, Any]] = []
    by_identity: dict[tuple[str, float, str], int] = defaultdict(int)
    for row in raw:
        by_identity[
            (str(row["workload"]), float(row["requested_duration_s"]), str(row["method"]))
        ] += 1
    for (workload, duration, method), count in sorted(by_identity.items()):
        inventory_rows.append(
            {
                "workload": workload,
                "duration_s": duration,
                "method": method,
                "valid_runs": count,
                "minimum_runs_per_cell": campaign.minimum_runs_per_cell,
                "sufficient_for_aggregate": count >= campaign.minimum_runs_per_cell,
            }
        )
    write_csv(
        root / "inventory.csv",
        inventory_rows,
        fieldnames=(
            "workload", "duration_s", "method", "valid_runs",
            "minimum_runs_per_cell", "sufficient_for_aggregate",
        ),
    )
    write_csv(
        root / "skipped.csv",
        skipped,
        fieldnames=("path", "reason", "detail"),
    )
    write_json(
        source_path,
        {
            "schema_version": _LEGACY_DURATION_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "source_type": source_type,
            "campaign_root": str(campaign.root),
            "campaign_root_available": campaign.root.is_dir(),
            "raw_result_rows": len(raw),
            "paired_urecs_pico_rows": len(paired),
            "threshold_rows": len(threshold_rows),
            "skipped_items": len(skipped),
            "urecs_correction_factor": campaign.urecs_correction_factor,
            "urecs_values_already_include_correction_factor": (
                campaign.urecs_values_already_include_correction_factor
            ),
            "urecs_correction_application": (
                "not_reapplied_stored_values_already_corrected"
                if campaign.urecs_values_already_include_correction_factor
                else "factor_applied_in_analysis"
            ),
            "steady_state_tolerance_pct": campaign.steady_state_tolerance_pct,
            "reference_duration_s": campaign.reference_duration_s,
            "fallback_rows_are_published_thesis_summaries": True,
            "interpretation": (
                "Sampling-only exact-window errors are not derived from this tree. "
                "This campaign quantifies command-duration, start/stop, fixed-overhead, "
                "window-detection, sensor-averaging and measurement-boundary effects."
            ),
        },
    )
    _copy_to_canonical(cfg.output_root, root)
    LOGGER.info(
        "Legacy duration campaign: %s (%d raw rows, %d threshold rows)",
        source_type,
        len(raw),
        len(threshold_rows),
    )
    return {
        "source_type": source_type,
        "raw": root / "raw_measurements.csv",
        "method_summary": root / "method_summary.csv",
        "convergence": root / "reference_convergence.csv",
        "thresholds": root / "reference_convergence_thresholds.csv",
        "paired": root / "urecs_vs_pico_per_run.csv",
        "urecs_summary": root / "urecs_vs_pico_summary.csv",
    }


def write_duration_summary(cfg: AnalysisConfig) -> Path:
    """Write a combined, terminology-safe answer to the rate/duration question."""

    root = cfg.output_root / "duration_sensitivity"
    summary_path = root / "duration_sensitivity_summary.csv"
    recommendation_path = root / "duration_rate_recommendation.json"
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    summary_rows = read_csv(summary_path)
    recommendation = read_json(recommendation_path) if recommendation_path.is_file() else {}
    highlighted = int(
        recommendation.get(
            "highlighted_rate_sps",
            cfg.duration_sensitivity.highlighted_rate_sps,
        )
    )
    rate_rows = sorted(
        [
            row for row in summary_rows
            if row["reconstruction_mode"] == "phase_only"
            and int(float(row["target_rate_sps"])) == highlighted
        ],
        key=lambda row: float(row["duration_s"]),
    )

    campaign_root = root / "legacy_duration_campaign"
    thresholds_path = campaign_root / "reference_convergence_thresholds.csv"
    thresholds = read_csv(thresholds_path) if thresholds_path.is_file() else []
    urecs_path = campaign_root / "urecs_vs_pico_summary.csv"
    urecs_rows = read_csv(urecs_path) if urecs_path.is_file() else []
    source_path = campaign_root / "source.json"
    source = read_json(source_path) if source_path.is_file() else {}

    lines = [
        "# Sampling-rate and duration decision summary",
        "",
        "## Two different duration questions",
        "",
        "1. **Sampling-only duration sensitivity:** the same stationary high-rate recording and exact physical integration interval are retained while sampling rate, sampling-grid offset and interval length are varied.",
        "2. **Benchmark-duration convergence:** independent 5--600-s commands include workload start/stop, fixed overhead, timeout behaviour, automatic boundary detection, sensor averaging and measurement-boundary differences.",
        "",
        f"## {highlighted/1000:g} kS/s sampling-only result",
        "",
    ]
    for row in rate_rows:
        lines.append(
            f"- {float(row['duration_s']):g} s exact interval: hierarchical q95 "
            f"{float(row['run_abs_error_q95_q95']):.6g}% "
            f"(median run-q95 {float(row['run_abs_error_q95_median']):.6g}%; "
            f"worst observed {float(row['run_abs_error_max_max']):.6g}%)."
        )

    recs = [
        row for row in recommendation.get("recommendations", [])
        if row.get("reconstruction_mode") == "phase_only"
    ]
    if recs:
        lines.extend(["", "### Minimum exact-window duration at the highlighted rate", ""])
        for row in recs:
            value = row.get("minimum_duration_s")
            if value is None or not math.isfinite(float(value)):
                display = "not reached"
            else:
                display = f"{row.get('minimum_duration_relation', '')} {float(value):g} s"
            lines.append(f"- {float(row['threshold_pct']):g}% tolerance: {display}.")

    if thresholds:
        lines.extend(["", "## Independent benchmark-duration protocol context", ""])
        for row in sorted(thresholds, key=lambda item: str(item["workload"])):
            lines.append(
                f"- {row['workload']}: |5-s vs. {float(row['reference_duration_s']):g}-s mean| "
                f"= {float(row['difference_5_to_reference_pct']):.2f}%; first tested duration "
                f"within {float(row['tolerance_pct']):g}% = "
                f"{float(row['first_duration_within_tolerance_s']):g} s "
                f"({row.get('source_kind', 'unknown source')})."
            )

    selected_urecs = next(
        (
            row
            for preferred_variant in (
                "stored_processed",
                "factor_corrected",
                "raw",
            )
            for row in urecs_rows
            if row.get("scope") in {"all", "thesis_summary"}
            and row.get("variant") == preferred_variant
        ),
        None,
    )
    if selected_urecs is not None:
        lines.extend(["", "## Practical u.RECS/PicoScope agreement", ""])
        q95 = _finite(selected_urecs.get("abs_error_q95_pct"))
        n = _finite(selected_urecs.get("n"))
        if q95 is not None and n is not None:
            lines.append(
                f"- Stored processed u.RECS versus PicoScope: q95 absolute difference "
                f"{q95:.3f}% across {int(n)} paired duration records."
            )
        else:
            lines.append(f"- {selected_urecs.get('note', 'See duration-campaign tables.')}" )

    lines.extend(
        [
            "",
            "## Decision rule",
            "",
            "A 2-kS/s u.RECS trace is adequate for run-level energy only after an energy tolerance and integration interval have been declared. The common-reference matrix supplies the sampling-only bound for an exact interval. The independent duration campaign supplies the additional command/protocol requirement. Passing either test does not imply faithful transient reconstruction.",
            "",
            "For the paper, report the result as a function $f_{min,E}(T,\\epsilon)$: the lowest tested rate that keeps the hierarchical energy error within tolerance $\\epsilon$ for interval length $T$, with the 5--600-s protocol convergence reported separately.",
            "",
            f"Duration-campaign source: `{source.get('source_type', 'not_available')}`.",
        ]
    )
    path = root / "DURATION_DECISION_SUMMARY.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    canonical = cfg.output_root / "rate_duration"
    canonical.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, canonical / "RATE_DURATION_SUMMARY.md")
    return path
