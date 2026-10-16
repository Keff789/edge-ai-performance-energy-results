from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .config import AnalysisConfig
from .io import MeasurementMetadata, load_measurement, validate_measurement
from .resampling import (
    build_cache_for_run,
    choose_source_cache,
    integrate_uniform_fixed_window,
    load_cache_info,
    open_cache,
    phase_count_for_target,
    phase_only_grid,
    resample_phase_grid,
)
from .utils import (
    LOGGER,
    discover_rate_directories,
    quantile,
    read_csv,
    stable_hash,
    utc_now_iso,
    write_csv,
    write_json,
)


ANTI_ALIAS_MODE = "anti_alias"
PHASE_ONLY_MODE = "phase_only"


def reference_run_dir(cfg: AnalysisConfig, run: int) -> Path:
    return cfg.dataset_root / cfg.reference_rate_directory / str(run)


def load_reference_measurements(
    cfg: AnalysisConfig, runs: Sequence[int]
) -> list[MeasurementMetadata]:
    return [load_measurement(reference_run_dir(cfg, run)) for run in runs]


def validate_dataset(cfg: AnalysisConfig, runs: Sequence[int]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        meta = load_measurement(reference_run_dir(cfg, run))
        row = validate_measurement(meta, expected_rate=cfg.reference_rate_sps)
        rows.append(row)
        status = "OK" if row["valid"] else "; ".join(row["issues"])
        LOGGER.info(
            "Reference run %d: %.3f J, %.6f s active, %s",
            run,
            meta.energy_j,
            row["active_duration_from_indices_s"],
            status,
        )
    valid = all(row["valid"] for row in rows)
    output = {
        "created_utc": utc_now_iso(),
        "dataset_root": str(cfg.dataset_root),
        "reference_rate_sps": cfg.reference_rate_sps,
        "runs": rows,
        "valid": valid,
    }
    write_json(cfg.output_root / "validation" / "reference_runs.json", output)
    if not valid:
        raise RuntimeError("Dataset validation failed; see validation/reference_runs.json")
    return output


def prepare_caches(cfg: AnalysisConfig, runs: Sequence[int], force: bool = False) -> None:
    qc_rows: list[dict[str, Any]] = []
    highest_cache_rate = max(cfg.cache_rates_sps)
    for meta in load_reference_measurements(cfg, runs):
        build_cache_for_run(cfg, meta, force=force)
        cache_info = load_cache_info(cfg.output_root, highest_cache_rate, meta.run)
        cache = open_cache(cache_info)
        cache_energy = integrate_uniform_fixed_window(
            cache,
            sample_rate=cache_info.sample_rate_sps,
            first_sample_time_s=0.0,
            start_time_s=meta.start_time_s,
            stop_time_s=meta.stop_time_s,
        )
        error_pct = (cache_energy - meta.energy_j) / meta.energy_j * 100.0
        qc_rows.append(
            {
                "run": meta.run,
                "cache_rate_sps": highest_cache_rate,
                "reference_energy_j": meta.energy_j,
                "cache_energy_j": cache_energy,
                "error_pct": error_pct,
                "abs_error_pct": abs(error_pct),
                "cache_samples": cache_info.sample_count,
                "cache_duration_s": cache_info.duration_s,
            }
        )
        if abs(error_pct) > 0.1:
            LOGGER.warning(
                "Run %d: %d-S/s cache differs from reference by %.6f%%",
                meta.run,
                highest_cache_rate,
                error_pct,
            )
        else:
            LOGGER.info("Run %d: cache-energy QC error %.9f%%", meta.run, error_pct)
        del cache
    write_csv(cfg.output_root / "validation" / "cache_energy_qc.csv", qc_rows)


def _common_signature(cfg: AnalysisConfig, runs: Sequence[int]) -> str:
    return stable_hash(
        {
            "tool_schema": 3,
            "runs": list(runs),
            "target_rates_sps": cfg.target_rates_sps,
            "cache_rates_sps": cfg.cache_rates_sps,
            "quality": cfg.resampling_quality,
            "guard_seconds": cfg.guard_seconds,
            "phase_plan": cfg.phase_plan,
            "anti_alias": cfg.anti_alias,
            "common_trace": cfg.common_trace,
        }
    )


def _segment_from_cache(
    cache: np.ndarray,
    cache_rate: int,
    meta: MeasurementMetadata,
    guard_seconds: float,
) -> tuple[np.ndarray, float]:
    full_duration = cache.size / cache_rate
    start_time = max(0.0, meta.start_time_s - guard_seconds)
    stop_time = min(full_duration - 1.0 / cache_rate, meta.stop_time_s + guard_seconds)
    start_idx = max(0, int(math.floor(start_time * cache_rate)))
    stop_idx = min(cache.size, int(math.ceil(stop_time * cache_rate)) + 1)
    actual_start = start_idx / cache_rate
    return np.asarray(cache[start_idx:stop_idx]), actual_start


def _rows_from_phase_grid(
    *,
    meta: MeasurementMetadata,
    reconstruction_mode: str,
    target_rate: int,
    phases: int,
    grid: np.ndarray,
    grid_rate: int,
    segment_start_time: float,
    source_rate: int,
    filter_meta: dict[str, Any],
    quality: str,
    is_anchor: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase in range(phases):
        phase_values = grid[phase::phases]
        phase_first_time = segment_start_time + phase / grid_rate
        derived_energy = integrate_uniform_fixed_window(
            phase_values,
            sample_rate=target_rate,
            first_sample_time_s=phase_first_time,
            start_time_s=meta.start_time_s,
            stop_time_s=meta.stop_time_s,
        )
        error_pct = (derived_energy - meta.energy_j) / meta.energy_j * 100.0
        rows.append(
            {
                "run": meta.run,
                "reconstruction_mode": reconstruction_mode,
                "target_rate_sps": target_rate,
                "phase_index": phase,
                "phase_count": phases,
                "phase_fraction": phase / phases,
                "source_rate_sps": source_rate,
                "grid_rate_sps": grid_rate,
                "reference_energy_j": meta.energy_j,
                "derived_energy_j": derived_energy,
                "error_pct": error_pct,
                "abs_error_pct": abs(error_pct),
                "filter_num_taps": filter_meta.get("num_taps", 0),
                "filter_description": filter_meta.get("filter"),
                "passband_hz": filter_meta.get("passband_hz"),
                "stopband_hz": filter_meta.get("stopband_hz"),
                "resampling_quality": quality,
                "derivation_method": filter_meta.get("derivation_method", "phase_grid"),
                "is_high_rate_anchor": is_anchor,
            }
        )
    return rows


def _high_rate_anchor_row(
    cfg: AnalysisConfig,
    meta: MeasurementMetadata,
    target_rate: int,
) -> dict[str, Any]:
    """Create a transparent high-rate continuation above the cache bandwidth.

    The configured extension source has a Nyquist frequency above the nominal
    analogue current-path bandwidth. For nominal target rates above that source
    rate, no additional measured bandwidth is claimed.
    The fixed-window cache energy is therefore used as a bandwidth-saturated
    anchor. The 5-MS/s point itself is the archived reference energy.
    """

    source_rate = cfg.common_trace.high_rate_extension.source_rate_sps
    if target_rate == cfg.reference_rate_sps:
        derived_energy = meta.energy_j
        source_rate = cfg.reference_rate_sps
        method = "archived 5-MS/s reference trace"
    else:
        cache_info = load_cache_info(cfg.output_root, source_rate, meta.run)
        cache = open_cache(cache_info)
        derived_energy = integrate_uniform_fixed_window(
            cache,
            sample_rate=source_rate,
            first_sample_time_s=0.0,
            start_time_s=meta.start_time_s,
            stop_time_s=meta.stop_time_s,
        )
        del cache
        method = (
            f"bandwidth-saturated anchor from validated {source_rate}-S/s cache; "
            "nominal rates above the cache add no measured analogue bandwidth"
        )

    error_pct = (derived_energy - meta.energy_j) / meta.energy_j * 100.0
    return {
        "run": meta.run,
        "reconstruction_mode": ANTI_ALIAS_MODE,
        "target_rate_sps": target_rate,
        "phase_index": 0,
        "phase_count": 1,
        "phase_fraction": 0.0,
        "source_rate_sps": source_rate,
        "grid_rate_sps": target_rate,
        "reference_energy_j": meta.energy_j,
        "derived_energy_j": derived_energy,
        "error_pct": error_pct,
        "abs_error_pct": abs(error_pct),
        "filter_num_taps": 0,
        "filter_description": method,
        "passband_hz": None,
        "stopband_hz": None,
        "resampling_quality": cfg.resampling_quality,
        "derivation_method": "bandwidth_saturated_anchor",
        "is_high_rate_anchor": True,
    }


def common_trace_for_run(
    cfg: AnalysisConfig,
    meta: MeasurementMetadata,
    force: bool = False,
) -> Path:
    out_dir = cfg.output_root / "common_trace" / "per_run"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"run_{meta.run}.csv"
    sidecar = out_dir / f"run_{meta.run}.json"
    signature = _common_signature(cfg, [meta.run])

    if not force and out_path.is_file() and sidecar.is_file():
        existing = __import__("json").load(sidecar.open("r", encoding="utf-8"))
        if existing.get("signature") == signature:
            LOGGER.info("Common-trace result exists: run %d", meta.run)
            return out_path

    rows: list[dict[str, Any]] = []
    highest_cache = max(cfg.cache_rates_sps)

    for target_rate in cfg.target_rates_sps:
        if ANTI_ALIAS_MODE in cfg.common_trace.reconstruction_modes:
            if target_rate > highest_cache:
                if cfg.common_trace.high_rate_extension.enabled:
                    LOGGER.info(
                        "Run %d: target=%d S/s, anti-aliased high-rate anchor",
                        meta.run,
                        target_rate,
                    )
                    rows.append(_high_rate_anchor_row(cfg, meta, target_rate))
            else:
                phases = phase_count_for_target(cfg, target_rate)
                grid_rate = target_rate * phases
                cache_info = choose_source_cache(cfg, grid_rate, meta.run)
                cache = open_cache(cache_info)
                source_segment, segment_start_time = _segment_from_cache(
                    cache,
                    cache_info.sample_rate_sps,
                    meta,
                    cfg.guard_seconds,
                )
                LOGGER.info(
                    "Run %d: target=%d S/s, mode=anti_alias, phases=%d, source=%d S/s",
                    meta.run,
                    target_rate,
                    phases,
                    cache_info.sample_rate_sps,
                )
                grid, actual_grid_rate, filter_meta = resample_phase_grid(
                    source_segment,
                    cache_info.sample_rate_sps,
                    target_rate,
                    phases,
                    cfg,
                )
                if actual_grid_rate != grid_rate:
                    raise AssertionError("Unexpected anti-alias phase-grid rate")
                filter_meta["derivation_method"] = "target_rate_anti_aliased_phase_grid"
                rows.extend(
                    _rows_from_phase_grid(
                        meta=meta,
                        reconstruction_mode=ANTI_ALIAS_MODE,
                        target_rate=target_rate,
                        phases=phases,
                        grid=grid,
                        grid_rate=grid_rate,
                        segment_start_time=segment_start_time,
                        source_rate=cache_info.sample_rate_sps,
                        filter_meta=filter_meta,
                        quality=cfg.resampling_quality,
                    )
                )
                del grid, source_segment, cache

        if PHASE_ONLY_MODE in cfg.common_trace.reconstruction_modes:
            source_rate = cfg.common_trace.phase_only_source_rate_sps
            if target_rate > source_rate:
                continue
            phases = phase_count_for_target(cfg, target_rate)
            phases = max(1, min(phases, source_rate // target_rate))
            grid_rate = target_rate * phases
            cache_info = load_cache_info(cfg.output_root, source_rate, meta.run)
            cache = open_cache(cache_info)
            source_segment, segment_start_time = _segment_from_cache(
                cache,
                cache_info.sample_rate_sps,
                meta,
                cfg.guard_seconds,
            )
            LOGGER.info(
                "Run %d: target=%d S/s, mode=phase_only, phases=%d, source=%d S/s",
                meta.run,
                target_rate,
                phases,
                source_rate,
            )
            grid, actual_grid_rate, filter_meta = phase_only_grid(
                source_segment,
                source_rate,
                target_rate,
                phases,
            )
            if actual_grid_rate != grid_rate:
                raise AssertionError("Unexpected phase-only grid rate")
            filter_meta["derivation_method"] = "phase_only_without_target_rate_antialias"
            rows.extend(
                _rows_from_phase_grid(
                    meta=meta,
                    reconstruction_mode=PHASE_ONLY_MODE,
                    target_rate=target_rate,
                    phases=phases,
                    grid=grid,
                    grid_rate=grid_rate,
                    segment_start_time=segment_start_time,
                    source_rate=source_rate,
                    filter_meta=filter_meta,
                    quality="none",
                )
            )
            del grid, source_segment, cache

    write_csv(out_path, rows)
    write_json(
        sidecar,
        {
            "created_utc": utc_now_iso(),
            "signature": signature,
            "run": meta.run,
            "row_count": len(rows),
            "reconstruction_modes": list(cfg.common_trace.reconstruction_modes),
        },
    )
    return out_path



def _phase_only_sensitivity_signature(
    cfg: AnalysisConfig, runs: Sequence[int]
) -> str:
    return stable_hash(
        {
            "tool_schema": 3,
            "runs": list(runs),
            "primary_source_rate_sps": cfg.common_trace.phase_only_source_rate_sps,
            "sensitivity_source_rates_sps": (
                cfg.common_trace.phase_only_sensitivity_source_rates_sps
            ),
            "target_rates_sps": (
                cfg.common_trace.phase_only_sensitivity_target_rates_sps
            ),
            "guard_seconds": cfg.guard_seconds,
            "phase_plan": cfg.phase_plan,
        }
    )


def phase_only_source_sensitivity_for_run(
    cfg: AnalysisConfig,
    meta: MeasurementMetadata,
    force: bool = False,
) -> Path | None:
    """Compare phase-only reconstruction from 1-MS/s and lower cache sources.

    This is a compact sensitivity analysis for the paper-relevant rates. It is
    intentionally kept separate from the primary common-trace table so that
    source-bandwidth variants do not get pooled into the main phase-only
    statistics or the f_min calculation.
    """

    alternate_sources = tuple(
        rate
        for rate in cfg.common_trace.phase_only_sensitivity_source_rates_sps
        if rate != cfg.common_trace.phase_only_source_rate_sps
    )
    if not alternate_sources:
        return None

    out_dir = (
        cfg.output_root
        / "common_trace"
        / "phase_only_source_sensitivity"
        / "per_run"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"run_{meta.run}.csv"
    sidecar = out_dir / f"run_{meta.run}.json"
    signature = _phase_only_sensitivity_signature(cfg, [meta.run])

    if not force and out_path.is_file() and sidecar.is_file():
        existing = __import__("json").load(sidecar.open("r", encoding="utf-8"))
        if existing.get("signature") == signature:
            LOGGER.info(
                "Phase-only source-sensitivity result exists: run %d", meta.run
            )
            return out_path

    source_rates = (
        cfg.common_trace.phase_only_source_rate_sps,
        *alternate_sources,
    )
    rows: list[dict[str, Any]] = []
    for source_rate in source_rates:
        cache_info = load_cache_info(cfg.output_root, source_rate, meta.run)
        cache = open_cache(cache_info)
        source_segment, segment_start_time = _segment_from_cache(
            cache,
            cache_info.sample_rate_sps,
            meta,
            cfg.guard_seconds,
        )
        for target_rate in cfg.common_trace.phase_only_sensitivity_target_rates_sps:
            if target_rate > source_rate:
                continue
            phases = cfg.phase_count(target_rate)
            phases = max(1, min(phases, source_rate // target_rate))
            grid_rate = target_rate * phases
            LOGGER.info(
                "Run %d: phase-only source sensitivity, target=%d S/s, "
                "phases=%d, source=%d S/s",
                meta.run,
                target_rate,
                phases,
                source_rate,
            )
            grid, actual_grid_rate, filter_meta = phase_only_grid(
                source_segment,
                source_rate,
                target_rate,
                phases,
            )
            if actual_grid_rate != grid_rate:
                raise AssertionError("Unexpected source-sensitivity phase grid rate")
            filter_meta["derivation_method"] = (
                "phase_only_source_bandwidth_sensitivity"
            )
            generated = _rows_from_phase_grid(
                meta=meta,
                reconstruction_mode=PHASE_ONLY_MODE,
                target_rate=target_rate,
                phases=phases,
                grid=grid,
                grid_rate=grid_rate,
                segment_start_time=segment_start_time,
                source_rate=source_rate,
                filter_meta=filter_meta,
                quality="none",
            )
            for row in generated:
                row["phase_only_source_role"] = (
                    "primary"
                    if source_rate
                    == cfg.common_trace.phase_only_source_rate_sps
                    else "sensitivity"
                )
                row["phase_only_source_rate_sps"] = source_rate
            rows.extend(generated)
            del grid
        del source_segment, cache

    write_csv(out_path, rows)
    write_json(
        sidecar,
        {
            "created_utc": utc_now_iso(),
            "signature": signature,
            "run": meta.run,
            "row_count": len(rows),
            "primary_source_rate_sps": (
                cfg.common_trace.phase_only_source_rate_sps
            ),
            "sensitivity_source_rates_sps": list(alternate_sources),
            "target_rates_sps": list(
                cfg.common_trace.phase_only_sensitivity_target_rates_sps
            ),
        },
    )
    return out_path


def summarise_phase_only_source_sensitivity(
    cfg: AnalysisConfig, runs: Sequence[int]
) -> tuple[Path, Path] | None:
    base = cfg.output_root / "common_trace" / "phase_only_source_sensitivity"
    raw_rows: list[dict[str, str]] = []
    for run in runs:
        path = base / "per_run" / f"run_{run}.csv"
        if path.is_file():
            raw_rows.extend(read_csv(path))
    if not raw_rows:
        return None

    merged_path = base / "phase_only_source_sensitivity_raw.csv"
    write_csv(merged_path, raw_rows, fieldnames=list(raw_rows[0].keys()))

    grouped: dict[tuple[int, int], list[float]] = {}
    run_ids: dict[tuple[int, int], set[int]] = {}
    phase_counts: dict[tuple[int, int], set[int]] = {}
    for row in raw_rows:
        key = (
            int(row["phase_only_source_rate_sps"]),
            int(row["target_rate_sps"]),
        )
        grouped.setdefault(key, []).append(float(row["error_pct"]))
        run_ids.setdefault(key, set()).add(int(row["run"]))
        phase_counts.setdefault(key, set()).add(int(row["phase_count"]))

    summary_rows: list[dict[str, Any]] = []
    for source_rate, target_rate in sorted(grouped):
        key = (source_rate, target_rate)
        values = np.asarray(grouped[key], dtype=np.float64)
        abs_values = np.abs(values)
        summary_rows.append(
            {
                "source_rate_sps": source_rate,
                "source_role": (
                    "primary"
                    if source_rate
                    == cfg.common_trace.phase_only_source_rate_sps
                    else "sensitivity"
                ),
                "target_rate_sps": target_rate,
                "n_runs": len(run_ids[key]),
                "n_run_phase_cases": int(values.size),
                "phase_counts": ";".join(
                    str(value) for value in sorted(phase_counts[key])
                ),
                "error_median_pct": float(np.median(values)),
                "error_q05_pct": quantile(values, 0.05),
                "error_q95_pct": quantile(values, 0.95),
                "abs_error_median_pct": float(np.median(abs_values)),
                "abs_error_q95_pct": quantile(abs_values, 0.95),
                "abs_error_max_pct": float(np.max(abs_values)),
            }
        )

    summary_path = base / "phase_only_source_sensitivity_summary.csv"
    write_csv(summary_path, summary_rows)

    primary_source = cfg.common_trace.phase_only_source_rate_sps
    primary_by_target = {
        int(row["target_rate_sps"]): row
        for row in summary_rows
        if int(row["source_rate_sps"]) == primary_source
    }
    comparison_rows: list[dict[str, Any]] = []
    for row in summary_rows:
        source_rate = int(row["source_rate_sps"])
        target_rate = int(row["target_rate_sps"])
        if source_rate == primary_source or target_rate not in primary_by_target:
            continue
        primary = primary_by_target[target_rate]
        primary_q95 = float(primary["abs_error_q95_pct"])
        alternate_q95 = float(row["abs_error_q95_pct"])
        comparison_rows.append(
            {
                "primary_source_rate_sps": primary_source,
                "sensitivity_source_rate_sps": source_rate,
                "target_rate_sps": target_rate,
                "primary_abs_error_q95_pct": primary_q95,
                "sensitivity_abs_error_q95_pct": alternate_q95,
                "abs_error_q95_delta_percentage_points": (
                    alternate_q95 - primary_q95
                ),
                "primary_error_median_pct": float(
                    primary["error_median_pct"]
                ),
                "sensitivity_error_median_pct": float(
                    row["error_median_pct"]
                ),
                "error_median_delta_percentage_points": (
                    float(row["error_median_pct"])
                    - float(primary["error_median_pct"])
                ),
                "interpretation": (
                    "Source-bandwidth sensitivity only; no automatic "
                    "equivalence threshold is imposed."
                ),
            }
        )
    comparison_path = base / "phase_only_source_sensitivity_comparison.csv"
    write_csv(
        comparison_path,
        comparison_rows,
        fieldnames=[
            "primary_source_rate_sps",
            "sensitivity_source_rate_sps",
            "target_rate_sps",
            "primary_abs_error_q95_pct",
            "sensitivity_abs_error_q95_pct",
            "abs_error_q95_delta_percentage_points",
            "primary_error_median_pct",
            "sensitivity_error_median_pct",
            "error_median_delta_percentage_points",
            "interpretation",
        ],
    )
    return summary_path, comparison_path


def validate_real_measurement_selection(
    cfg: AnalysisConfig, runs: Sequence[int]
) -> Path:
    """Document the fixed run-ID policy used for all independent-rate data."""

    rows: list[dict[str, Any]] = []
    selected = set(int(run) for run in runs)
    for rate, rate_dir in discover_rate_directories(cfg.dataset_root):
        numeric_runs = sorted(
            int(path.name)
            for path in rate_dir.iterdir()
            if path.is_dir() and path.name.isdigit()
        )
        available = set(numeric_runs)
        invalid_directories = sorted(
            path.name
            for path in rate_dir.iterdir()
            if path.is_dir() and path.name.startswith("invalid_runs")
        )
        missing = sorted(selected - available)
        extras = sorted(available - selected)
        rows.append(
            {
                "directory_rate_sps": rate,
                "rate_directory": str(rate_dir),
                "available_numeric_runs": ";".join(str(v) for v in numeric_runs),
                "selected_run_ids": ";".join(str(v) for v in sorted(selected)),
                "selected_runs_present": ";".join(
                    str(v) for v in sorted(selected & available)
                ),
                "selected_runs_missing": ";".join(str(v) for v in missing),
                "unselected_numeric_runs": ";".join(str(v) for v in extras),
                "invalid_run_directories": ";".join(invalid_directories),
                "selection_policy": (
                    "Use the same predeclared primary run IDs at every "
                    "independently recorded sampling rate."
                ),
                "valid": not missing,
            }
        )

    path = cfg.output_root / "validation" / "real_measurement_run_selection.csv"
    write_csv(path, rows)
    if any(not bool(row["valid"]) for row in rows):
        LOGGER.warning(
            "One or more real-rate directories do not contain every selected run; "
            "see %s",
            path,
        )
    else:
        LOGGER.info(
            "Real-measurement run selection validated for %d rate directories",
            len(rows),
        )
    return path

def summarise_common_trace(cfg: AnalysisConfig, runs: Sequence[int]) -> tuple[Path, Path]:
    raw_rows: list[dict[str, str]] = []
    for run in runs:
        raw_rows.extend(
            read_csv(cfg.output_root / "common_trace" / "per_run" / f"run_{run}.csv")
        )

    merged_path = cfg.output_root / "common_trace" / "common_trace_raw.csv"
    write_csv(merged_path, raw_rows, fieldnames=list(raw_rows[0].keys()))

    numeric_by_key: dict[tuple[str, int], list[float]] = {}
    phase_counts: dict[tuple[str, int], set[int]] = {}
    run_ids: dict[tuple[str, int], set[int]] = {}
    anchor_flags: dict[tuple[str, int], list[bool]] = {}
    for row in raw_rows:
        mode = row["reconstruction_mode"]
        rate = int(row["target_rate_sps"])
        key = (mode, rate)
        numeric_by_key.setdefault(key, []).append(float(row["error_pct"]))
        phase_counts.setdefault(key, set()).add(int(row["phase_count"]))
        run_ids.setdefault(key, set()).add(int(row["run"]))
        anchor_flags.setdefault(key, []).append(
            str(row["is_high_rate_anchor"]).lower() in {"true", "1", "yes"}
        )

    summary_rows: list[dict[str, Any]] = []
    for mode, rate in sorted(numeric_by_key, key=lambda item: (item[0], item[1])):
        key = (mode, rate)
        values = np.asarray(numeric_by_key[key], dtype=np.float64)
        abs_values = np.abs(values)
        summary_rows.append(
            {
                "reconstruction_mode": mode,
                "target_rate_sps": rate,
                "n_runs": len(run_ids[key]),
                "n_run_phase_cases": values.size,
                "phase_counts": ";".join(str(v) for v in sorted(phase_counts[key])),
                "is_high_rate_anchor": all(anchor_flags[key]),
                "error_mean_pct": float(np.mean(values)),
                "error_median_pct": float(np.median(values)),
                "error_q05_pct": quantile(values, 0.05),
                "error_q95_pct": quantile(values, 0.95),
                "abs_error_median_pct": float(np.median(abs_values)),
                "abs_error_q95_pct": quantile(abs_values, 0.95),
                "abs_error_max_pct": float(np.max(abs_values)),
            }
        )

    summary_path = cfg.output_root / "common_trace" / "common_trace_summary.csv"
    write_csv(summary_path, summary_rows)

    anti_alias_rows = [
        row for row in summary_rows if row["reconstruction_mode"] == ANTI_ALIAS_MODE
    ]
    if anti_alias_rows:
        write_csv(
            cfg.output_root / "common_trace" / "anti_aliased_summary.csv",
            anti_alias_rows,
        )
    phase_only_rows = [
        row for row in summary_rows if row["reconstruction_mode"] == PHASE_ONLY_MODE
    ]
    if phase_only_rows:
        write_csv(
            cfg.output_root / "common_trace" / "phase_only_summary.csv",
            phase_only_rows,
        )

    return merged_path, summary_path


def determine_fmin(cfg: AnalysisConfig, summary_path: Path) -> Path:
    rows = read_csv(summary_path)
    modes = sorted({row["reconstruction_mode"] for row in rows})
    output_rows: list[dict[str, Any]] = []

    for mode in modes:
        records = sorted(
            (
                int(row["target_rate_sps"]),
                float(row["abs_error_q95_pct"]),
            )
            for row in rows
            if row["reconstruction_mode"] == mode
        )
        if not records:
            continue
        lowest_rate = records[0][0]
        highest_rate = records[-1][0]

        for threshold in cfg.common_trace.fmin_thresholds_pct:
            selected: int | None = None
            for index, (rate, _) in enumerate(records):
                higher = [q95 for _, q95 in records[index:]]
                if higher and all(value <= threshold for value in higher):
                    selected = rate
                    break

            if selected is None:
                relation = ""
                status = "not_identified"
                display = f"not identified up to {highest_rate} S/s"
            elif selected == lowest_rate:
                relation = "<="
                status = "at_or_below_lowest_evaluated"
                display = f"≤ {selected} S/s"
            else:
                relation = "="
                status = "identified_within_evaluated_range"
                display = f"{selected} S/s"

            output_rows.append(
                {
                    "reconstruction_mode": mode,
                    "error_limit_pct": threshold,
                    "f_min_sps": selected,
                    "relation": relation,
                    "status": status,
                    "display": display,
                    "lowest_evaluated_rate_sps": lowest_rate,
                    "highest_evaluated_rate_sps": highest_rate,
                    "criterion": (
                        "95th percentile of absolute common-trace error; all higher "
                        "evaluated rates within the same reconstruction mode must also pass"
                    ),
                }
            )

    out_path = cfg.output_root / "common_trace" / "f_min.csv"
    write_csv(out_path, output_rows)
    return out_path


def analyse_real_measurements(cfg: AnalysisConfig, runs: Sequence[int]) -> tuple[Path, Path]:
    rates = discover_rate_directories(cfg.dataset_root)
    reference_energies = [
        load_measurement(reference_run_dir(cfg, run)).energy_j for run in runs
    ]
    reference_median = float(np.median(reference_energies))

    raw_rows: list[dict[str, Any]] = []
    for directory_rate, rate_dir in rates:
        for run in runs:
            run_dir = rate_dir / str(run)
            if not run_dir.is_dir():
                LOGGER.warning("Missing real measurement: %s", run_dir)
                continue
            meta = load_measurement(run_dir)
            error_pct = (meta.energy_j - reference_median) / reference_median * 100.0
            raw_rows.append(
                {
                    "directory_rate_sps": directory_rate,
                    "reported_rate_sps": meta.sample_rate_sps,
                    "run": run,
                    "energy_j": meta.energy_j,
                    "error_vs_reference_median_pct": error_pct,
                    "reference_5msps_median_j": reference_median,
                }
            )

    raw_path = cfg.output_root / "real_measurements" / "real_measurements_raw.csv"
    write_csv(raw_path, raw_rows)

    grouped: dict[int, list[float]] = {}
    energy_grouped: dict[int, list[float]] = {}
    reported_grouped: dict[int, list[float]] = {}
    for row in raw_rows:
        rate = int(row["directory_rate_sps"])
        grouped.setdefault(rate, []).append(float(row["error_vs_reference_median_pct"]))
        energy_grouped.setdefault(rate, []).append(float(row["energy_j"]))
        reported_grouped.setdefault(rate, []).append(float(row["reported_rate_sps"]))

    summary_rows: list[dict[str, Any]] = []
    for rate in sorted(grouped):
        errors = np.asarray(grouped[rate], dtype=np.float64)
        energies = np.asarray(energy_grouped[rate], dtype=np.float64)
        summary_rows.append(
            {
                "directory_rate_sps": rate,
                "reported_rate_median_sps": float(np.median(reported_grouped[rate])),
                "n_runs": errors.size,
                "energy_mean_j": float(np.mean(energies)),
                "energy_median_j": float(np.median(energies)),
                "energy_std_j": float(np.std(energies, ddof=1)) if errors.size > 1 else 0.0,
                "error_mean_pct": float(np.mean(errors)),
                "error_median_pct": float(np.median(errors)),
                "error_q05_pct": quantile(errors, 0.05),
                "error_q95_pct": quantile(errors, 0.95),
                "error_min_pct": float(np.min(errors)),
                "error_max_pct": float(np.max(errors)),
                "reference_5msps_median_j": reference_median,
            }
        )
    summary_path = cfg.output_root / "real_measurements" / "real_measurements_summary.csv"
    write_csv(summary_path, summary_rows)
    return raw_path, summary_path
