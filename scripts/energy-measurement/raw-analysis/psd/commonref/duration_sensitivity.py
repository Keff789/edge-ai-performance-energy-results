from __future__ import annotations

import gc
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .analysis import ANTI_ALIAS_MODE, PHASE_ONLY_MODE
from .config import AnalysisConfig
from .io import MeasurementMetadata
from .resampling import (
    load_cache_info,
    open_cache,
    phase_count_for_target,
    phase_only_grid,
    resample_phase_grid,
)
from .utils import LOGGER, quantile, stable_hash, write_csv, write_json


_DURATION_ANALYSIS_SCHEMA_VERSION = 3


class UniformLinearIntegral:
    """O(1) integrals of a uniformly sampled piecewise-linear signal."""

    def __init__(
        self,
        values: np.ndarray,
        *,
        sample_rate_sps: float,
        first_sample_time_s: float,
    ) -> None:
        array = np.asarray(values, dtype=np.float64)
        if array.ndim != 1 or array.size < 2:
            raise ValueError("UniformLinearIntegral requires at least two samples")
        if sample_rate_sps <= 0:
            raise ValueError("sample_rate_sps must be positive")
        self.values = array
        self.rate = float(sample_rate_sps)
        self.dt = 1.0 / self.rate
        self.first_time = float(first_sample_time_s)
        increments = 0.5 * (array[:-1] + array[1:]) * self.dt
        self.cumulative = np.empty(array.size, dtype=np.float64)
        self.cumulative[0] = 0.0
        np.cumsum(increments, dtype=np.float64, out=self.cumulative[1:])

    @property
    def last_time(self) -> float:
        return self.first_time + (self.values.size - 1) * self.dt

    def _antiderivative(self, time_s: float) -> float:
        position = (float(time_s) - self.first_time) * self.rate
        tolerance = 2e-8
        if position < -tolerance or position > self.values.size - 1 + tolerance:
            raise ValueError(
                f"Time {time_s} s is outside [{self.first_time}, {self.last_time}]"
            )
        position = min(max(position, 0.0), float(self.values.size - 1))
        left = int(math.floor(position))
        if left >= self.values.size - 1:
            return float(self.cumulative[-1])
        fraction = position - left
        if fraction <= 1e-14:
            return float(self.cumulative[left])
        y0 = float(self.values[left])
        y1 = float(self.values[left + 1])
        y_at = y0 + fraction * (y1 - y0)
        return float(
            self.cumulative[left]
            + 0.5 * (y0 + y_at) * (fraction * self.dt)
        )

    def integrate(self, start_time_s: float, stop_time_s: float) -> float:
        if stop_time_s <= start_time_s:
            raise ValueError("stop_time_s must be greater than start_time_s")
        return self._antiderivative(stop_time_s) - self._antiderivative(start_time_s)


def _duration_token(duration_s: float) -> str:
    return f"{float(duration_s):.12g}".replace("-", "m").replace(".", "p")


def _combo_key(mode: str, target_rate_sps: int, duration_s: float) -> str:
    return f"{mode}__r{int(target_rate_sps)}__d{_duration_token(duration_s)}"


def _active_window(meta: MeasurementMetadata) -> tuple[float, float, float]:
    start = float(meta.start_time_s)
    # start_stop_idx has an inclusive stop index.  The YAML duration is the
    # intended physical interval and avoids losing one reference-sample period.
    span = float(meta.duration_s)
    if span <= 0:
        raise ValueError(f"Run {meta.run}: invalid active duration")
    return start, start + span, span


def _window_starts(
    meta: MeasurementMetadata,
    duration_s: float,
    count: int,
    edge_margin_s: float,
) -> np.ndarray:
    active_start, active_stop, active_span = _active_window(meta)
    duration = float(duration_s)
    tolerance = 1.5 / float(meta.sample_rate_sps)
    if duration > active_span + tolerance:
        return np.empty(0, dtype=np.float64)
    if duration >= active_span - tolerance:
        return np.asarray([active_start], dtype=np.float64)

    maximum_symmetric_margin = max(0.0, 0.5 * (active_span - duration))
    margin = min(max(0.0, float(edge_margin_s)), maximum_symmetric_margin)
    first = active_start + margin
    latest = active_stop - duration - margin
    if latest < first:
        first = active_start
        latest = active_stop - duration
    if latest <= first + tolerance or int(count) <= 1:
        return np.asarray([0.5 * (first + latest)], dtype=np.float64)

    starts = np.linspace(first, latest, max(1, int(count)), dtype=np.float64)
    indices = np.rint(starts * meta.sample_rate_sps).astype(np.int64)
    return np.unique(indices).astype(np.float64) / meta.sample_rate_sps


def _segment_from_cache(
    cache: np.ndarray,
    cache_rate_sps: int,
    meta: MeasurementMetadata,
    guard_seconds: float,
) -> tuple[np.ndarray, float]:
    full_last_time = (cache.size - 1) / cache_rate_sps
    _, active_stop, _ = _active_window(meta)
    start_time = max(0.0, meta.start_time_s - guard_seconds)
    stop_time = min(full_last_time, active_stop + guard_seconds)
    start_idx = max(0, int(math.floor(start_time * cache_rate_sps)))
    stop_idx = min(cache.size, int(math.ceil(stop_time * cache_rate_sps)) + 1)
    return np.asarray(cache[start_idx:stop_idx]), start_idx / cache_rate_sps


def _duration_signature(cfg: AnalysisConfig, meta: MeasurementMetadata) -> str:
    active_start, active_stop, _ = _active_window(meta)
    return stable_hash(
        {
            "schema": _DURATION_ANALYSIS_SCHEMA_VERSION,
            "run": meta.run,
            "duration_sensitivity": asdict(cfg.duration_sensitivity),
            "phase_plan": cfg.phase_plan,
            "anti_alias": asdict(cfg.anti_alias),
            "resampling_quality": cfg.resampling_quality,
            "guard_seconds": cfg.guard_seconds,
            "active_interval": [active_start, active_stop],
            "reference_energy_j": meta.energy_j,
        }
    )


def _reference_window_energies(
    cfg: AnalysisConfig,
    meta: MeasurementMetadata,
) -> tuple[dict[float, tuple[np.ndarray, np.ndarray]], dict[str, Any]]:
    source_rate = cfg.duration_sensitivity.source_rate_sps
    info = load_cache_info(cfg.output_root, source_rate, meta.run)
    cache = open_cache(info)
    segment, first_time = _segment_from_cache(
        cache, source_rate, meta, cfg.guard_seconds
    )
    integral = UniformLinearIntegral(
        segment,
        sample_rate_sps=source_rate,
        first_sample_time_s=first_time,
    )
    _, active_stop, active_span = _active_window(meta)
    result: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for duration in cfg.duration_sensitivity.window_durations_s:
        if duration > active_span + 1.5 / meta.sample_rate_sps:
            continue
        starts = _window_starts(
            meta,
            duration,
            cfg.duration_sensitivity.windows_per_duration,
            cfg.duration_sensitivity.edge_margin_s,
        )
        if starts.size == 0:
            continue
        stops = np.minimum(starts + duration, active_stop)
        energies = np.asarray(
            [integral.integrate(float(start), float(stop)) for start, stop in zip(starts, stops)],
            dtype=np.float64,
        )
        result[float(duration)] = (starts, energies)
    metadata = {
        "source_rate_sps": source_rate,
        "source_cache": str(info.data_path),
        "source_cache_dtype": info.dtype,
        "source_cache_duration_s": info.duration_s,
        "edge_margin_s": cfg.duration_sensitivity.edge_margin_s,
        "note": (
            "Reference sub-window energies are integrated from the validated "
            "band-limited cache. Sub-windows avoid active start/stop transitions "
            "where possible. Window positions are sensitivity conditions, not "
            "independent benchmark runs."
        ),
    }
    del integral, segment, cache
    gc.collect()
    return result, metadata


def _summary(values: np.ndarray, prefix: str = "") -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    array = array[np.isfinite(array)]
    names = {
        f"{prefix}n_observations": 0,
        f"{prefix}error_pct_median": float("nan"),
        f"{prefix}error_pct_q05": float("nan"),
        f"{prefix}error_pct_q95": float("nan"),
        f"{prefix}abs_error_pct_median": float("nan"),
        f"{prefix}abs_error_pct_q95": float("nan"),
        f"{prefix}abs_error_pct_q99": float("nan"),
        f"{prefix}abs_error_pct_max": float("nan"),
    }
    if array.size == 0:
        return names
    absolute = np.abs(array)
    names.update(
        {
            f"{prefix}n_observations": int(array.size),
            f"{prefix}error_pct_median": float(np.median(array)),
            f"{prefix}error_pct_q05": quantile(array, 0.05),
            f"{prefix}error_pct_q95": quantile(array, 0.95),
            f"{prefix}abs_error_pct_median": float(np.median(absolute)),
            f"{prefix}abs_error_pct_q95": quantile(absolute, 0.95),
            f"{prefix}abs_error_pct_q99": quantile(absolute, 0.99),
            f"{prefix}abs_error_pct_max": float(np.max(absolute)),
        }
    )
    return names


def duration_sensitivity_for_run(
    cfg: AnalysisConfig,
    meta: MeasurementMetadata,
    *,
    force: bool = False,
) -> Path:
    if not cfg.duration_sensitivity.enabled:
        raise RuntimeError("duration_sensitivity is disabled")
    root = cfg.output_root / "duration_sensitivity" / "per_run"
    root.mkdir(parents=True, exist_ok=True)
    npz_path = root / f"run_{meta.run}.npz"
    summary_path = root / f"run_{meta.run}_summary.csv"
    sidecar_path = root / f"run_{meta.run}.json"
    signature = _duration_signature(cfg, meta)
    if not force and npz_path.is_file() and summary_path.is_file() and sidecar_path.is_file():
        import json

        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if payload.get("signature") == signature:
            LOGGER.info("Duration-sensitivity result exists: run %d", meta.run)
            return npz_path

    references, reference_meta = _reference_window_energies(cfg, meta)
    arrays: dict[str, np.ndarray] = {}
    mapping: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    source_rate = cfg.duration_sensitivity.source_rate_sps
    info = load_cache_info(cfg.output_root, source_rate, meta.run)
    cache = open_cache(info)
    source_segment, segment_start = _segment_from_cache(
        cache, source_rate, meta, cfg.guard_seconds
    )
    _, active_stop, _ = _active_window(meta)

    for target_rate in cfg.duration_sensitivity.target_rates_sps:
        requested_phases = phase_count_for_target(cfg, target_rate)
        phases = max(1, min(requested_phases, source_rate // target_rate))
        if target_rate * phases > source_rate:
            continue
        for mode in cfg.duration_sensitivity.reconstruction_modes:
            if mode == PHASE_ONLY_MODE:
                grid, grid_rate, filter_meta = phase_only_grid(
                    source_segment, source_rate, target_rate, phases
                )
            elif mode == ANTI_ALIAS_MODE:
                grid, grid_rate, filter_meta = resample_phase_grid(
                    source_segment, source_rate, target_rate, phases, cfg
                )
            else:
                raise ValueError(f"Unsupported reconstruction mode: {mode}")
            if grid_rate != target_rate * phases:
                raise AssertionError("Unexpected duration phase-grid rate")
            LOGGER.info(
                "Duration sensitivity run %d: target=%d S/s, mode=%s, phases=%d",
                meta.run,
                target_rate,
                mode,
                phases,
            )

            by_duration: dict[float, list[np.ndarray]] = {duration: [] for duration in references}
            for phase in range(phases):
                phase_values = np.asarray(grid[phase::phases], dtype=np.float64)
                phase_first_time = segment_start + phase / grid_rate
                integral = UniformLinearIntegral(
                    phase_values,
                    sample_rate_sps=target_rate,
                    first_sample_time_s=phase_first_time,
                )
                for duration, (starts, reference_energies) in references.items():
                    if duration * target_rate < cfg.duration_sensitivity.minimum_samples_per_window:
                        continue
                    stops = np.minimum(starts + duration, active_stop)
                    derived = np.asarray(
                        [
                            integral.integrate(float(start), float(stop))
                            for start, stop in zip(starts, stops)
                        ],
                        dtype=np.float64,
                    )
                    valid = np.isfinite(reference_energies) & (reference_energies != 0)
                    errors = np.full(reference_energies.shape, np.nan, dtype=np.float64)
                    errors[valid] = (
                        (derived[valid] - reference_energies[valid])
                        / reference_energies[valid]
                        * 100.0
                    )
                    by_duration[duration].append(errors)
                del integral, phase_values

            for duration, chunks in by_duration.items():
                if not chunks:
                    continue
                values = np.concatenate(chunks).astype(np.float32, copy=False)
                key = _combo_key(mode, target_rate, duration)
                arrays[key] = values
                mapping[key] = {
                    "reconstruction_mode": mode,
                    "target_rate_sps": target_rate,
                    "duration_s": duration,
                    "phase_count": phases,
                    "window_count": int(references[duration][0].size),
                    "source_rate_sps": source_rate,
                    "grid_rate_sps": grid_rate,
                    "filter_description": filter_meta.get("filter"),
                }
                rows.append(
                    {
                        "run": meta.run,
                        "reconstruction_mode": mode,
                        "target_rate_sps": target_rate,
                        "duration_s": duration,
                        "phase_count": phases,
                        "window_count": int(references[duration][0].size),
                        "source_rate_sps": source_rate,
                        **_summary(values),
                    }
                )
            del grid
            gc.collect()

    del source_segment, cache
    np.savez_compressed(npz_path, **arrays)
    write_csv(summary_path, rows)
    write_json(
        sidecar_path,
        {
            "schema_version": _DURATION_ANALYSIS_SCHEMA_VERSION,
            "signature": signature,
            "run": meta.run,
            "mapping": mapping,
            "reference": reference_meta,
            "statistical_unit_note": (
                "Sampling-grid offsets and sub-window positions are sensitivity "
                "conditions within a physical run, not independent repetitions."
            ),
        },
    )
    return npz_path


def _load_payload(
    cfg: AnalysisConfig,
    run: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    import json

    root = cfg.output_root / "duration_sensitivity" / "per_run"
    npz_path = root / f"run_{run}.npz"
    json_path = root / f"run_{run}.json"
    if not npz_path.is_file() or not json_path.is_file():
        raise FileNotFoundError(f"Missing duration output for run {run}")
    with np.load(npz_path) as data:
        arrays = {key: np.asarray(data[key], dtype=np.float64) for key in data.files}
    return arrays, json.loads(json_path.read_text(encoding="utf-8"))


def _monotonic_fmin(
    rows: list[dict[str, Any]],
    threshold_pct: float,
    *,
    field: str = "run_abs_error_q95_q95",
) -> tuple[float, str]:
    ordered = sorted(rows, key=lambda row: float(row["target_rate_sps"]))
    if not ordered:
        return float("nan"), ">"
    passed = [
        np.isfinite(float(row.get(field, row.get("abs_error_pct_q95", float("nan")))))
        and float(row.get(field, row.get("abs_error_pct_q95", float("nan")))) <= threshold_pct
        for row in ordered
    ]
    for index, row in enumerate(ordered):
        if passed[index] and all(passed[index:]):
            return float(row["target_rate_sps"]), "<=" if index == 0 else "="
    return float("nan"), ">"


def _minimum_duration_passing(
    rows: list[dict[str, Any]],
    threshold_pct: float,
    *,
    field: str = "run_abs_error_q95_q95",
) -> tuple[float, str]:
    ordered = sorted(rows, key=lambda row: float(row["duration_s"]))
    if not ordered:
        return float("nan"), ">"
    passed = [
        np.isfinite(float(row.get(field, row.get("abs_error_pct_q95", float("nan")))))
        and float(row.get(field, row.get("abs_error_pct_q95", float("nan")))) <= threshold_pct
        for row in ordered
    ]
    for index, row in enumerate(ordered):
        if passed[index] and all(passed[index:]):
            return float(row["duration_s"]), "<=" if index == 0 else "="
    return float("nan"), ">"


def summarise_duration_sensitivity(
    cfg: AnalysisConfig,
    runs: Iterable[int],
) -> tuple[Path, Path, Path]:
    selected_runs = list(runs)
    pooled: dict[str, list[np.ndarray]] = {}
    per_run_statistics: dict[str, list[dict[str, float]]] = {}
    mapping: dict[str, dict[str, Any]] = {}
    for run in selected_runs:
        arrays, metadata = _load_payload(cfg, run)
        run_mapping = metadata.get("mapping", {})
        for key, values in arrays.items():
            pooled.setdefault(key, []).append(values)
            mapping.setdefault(key, run_mapping[key])
            stats = _summary(values)
            per_run_statistics.setdefault(key, []).append(
                {
                    "run": int(run),
                    "abs_error_q95_pct": float(stats["abs_error_pct_q95"]),
                    "abs_error_max_pct": float(stats["abs_error_pct_max"]),
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for key, chunks in pooled.items():
        values = np.concatenate(chunks)
        meta = mapping[key]
        run_q95 = np.asarray(
            [row["abs_error_q95_pct"] for row in per_run_statistics[key]],
            dtype=np.float64,
        )
        run_max = np.asarray(
            [row["abs_error_max_pct"] for row in per_run_statistics[key]],
            dtype=np.float64,
        )
        summary_rows.append(
            {
                "reconstruction_mode": meta["reconstruction_mode"],
                "target_rate_sps": int(meta["target_rate_sps"]),
                "duration_s": float(meta["duration_s"]),
                "n_runs": len(chunks),
                "phase_count": int(meta["phase_count"]),
                "window_count_per_run": int(meta["window_count"]),
                "n_nominal_conditions": int(
                    len(chunks) * int(meta["phase_count"]) * int(meta["window_count"])
                ),
                **_summary(values),
                "run_abs_error_q95_median": float(np.median(run_q95)),
                "run_abs_error_q95_q05": quantile(run_q95, 0.05),
                "run_abs_error_q95_q95": quantile(run_q95, 0.95),
                "run_abs_error_q95_max": float(np.max(run_q95)),
                "run_abs_error_max_median": float(np.median(run_max)),
                "run_abs_error_max_q95": quantile(run_max, 0.95),
                "run_abs_error_max_max": float(np.max(run_max)),
            }
        )
    summary_rows.sort(
        key=lambda row: (
            str(row["reconstruction_mode"]),
            float(row["duration_s"]),
            float(row["target_rate_sps"]),
        )
    )
    root = cfg.output_root / "duration_sensitivity"
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "duration_sensitivity_summary.csv"
    write_csv(summary_path, summary_rows)

    per_run_rows: list[dict[str, Any]] = []
    for key, run_rows in per_run_statistics.items():
        meta = mapping[key]
        for row in run_rows:
            per_run_rows.append(
                {
                    "run": int(row["run"]),
                    "reconstruction_mode": meta["reconstruction_mode"],
                    "target_rate_sps": int(meta["target_rate_sps"]),
                    "duration_s": float(meta["duration_s"]),
                    "phase_count": int(meta["phase_count"]),
                    "window_count": int(meta["window_count"]),
                    "abs_error_q95_pct": float(row["abs_error_q95_pct"]),
                    "abs_error_max_pct": float(row["abs_error_max_pct"]),
                    "statistical_unit_note": (
                        "Window positions and sampling-grid offsets are within-run "
                        "sensitivity conditions; the physical run is the independent unit."
                    ),
                }
            )
    per_run_rows.sort(
        key=lambda row: (
            int(row["run"]),
            str(row["reconstruction_mode"]),
            float(row["duration_s"]),
            int(row["target_rate_sps"]),
        )
    )
    write_csv(root / "duration_sensitivity_per_run.csv", per_run_rows)

    fmin_rows: list[dict[str, Any]] = []
    for mode in cfg.duration_sensitivity.reconstruction_modes:
        durations = sorted(
            {
                float(row["duration_s"])
                for row in summary_rows
                if row["reconstruction_mode"] == mode
            }
        )
        for duration in durations:
            candidates = [
                row
                for row in summary_rows
                if row["reconstruction_mode"] == mode
                and math.isclose(float(row["duration_s"]), duration, abs_tol=1e-12)
            ]
            for threshold in cfg.duration_sensitivity.thresholds_pct:
                rate, relation = _monotonic_fmin(candidates, threshold)
                fmin_rows.append(
                    {
                        "reconstruction_mode": mode,
                        "duration_s": duration,
                        "threshold_pct": threshold,
                        "f_min_relation": relation,
                        "f_min_sps": rate,
                        "lowest_tested_rate_sps": min(float(row["target_rate_sps"]) for row in candidates),
                        "highest_tested_rate_sps": max(float(row["target_rate_sps"]) for row in candidates),
                        "criterion": (
                            "the 95th percentile across physical runs of each run's "
                            "q95 grid/window absolute energy error is within the "
                            "threshold at this and all higher tested rates"
                        ),
                    }
                )
    fmin_path = root / "duration_dependent_f_min.csv"
    write_csv(fmin_path, fmin_rows)

    highlighted = cfg.duration_sensitivity.highlighted_rate_sps
    highlighted_rows = [
        row for row in summary_rows if int(row["target_rate_sps"]) == highlighted
    ]
    write_csv(root / "highlighted_rate_sufficiency.csv", highlighted_rows)

    recommendations: list[dict[str, Any]] = []
    for mode in cfg.duration_sensitivity.reconstruction_modes:
        rows = [row for row in highlighted_rows if row["reconstruction_mode"] == mode]
        for threshold in cfg.duration_sensitivity.thresholds_pct:
            duration, relation = _minimum_duration_passing(rows, threshold)
            recommendations.append(
                {
                    "reconstruction_mode": mode,
                    "highlighted_rate_sps": highlighted,
                    "threshold_pct": threshold,
                    "minimum_duration_relation": relation,
                    "minimum_duration_s": duration,
                    "criterion": (
                        "the 95th percentile across physical runs of each run's q95 "
                        "grid/window absolute energy error remains within the threshold "
                        "for this and all longer tested windows"
                    ),
                }
            )
    recommendation_path = root / "duration_rate_recommendation.json"
    recommendation_payload = {
        "schema_version": _DURATION_ANALYSIS_SCHEMA_VERSION,
        "highlighted_rate_sps": highlighted,
        "runs": selected_runs,
        "window_durations_s": cfg.duration_sensitivity.window_durations_s,
        "target_rates_sps": cfg.duration_sensitivity.target_rates_sps,
        "recommendations": recommendations,
        "interpretation": {
            "pure_sampling": (
                "This common-reference analysis isolates sampling-grid and "
                "window-duration effects inside stationary GEMM-FP16 activity."
            ),
            "protocol_duration": (
                "The independent 5--600-s campaign separately quantifies "
                "start/stop, windowing, sensor averaging and fixed overhead."
            ),
            "temporal_fidelity": (
                "Passing an energy tolerance does not imply faithful transient reconstruction."
            ),
        },
    }
    write_json(recommendation_path, recommendation_payload)

    # Canonical v0.5.7 paper/documentation contract.  Keep the historical
    # duration_sensitivity files above for backwards compatibility, but expose
    # a terminology-stable rate_duration tree used by reports and LaTeX.
    canonical = cfg.output_root / "rate_duration"
    canonical.mkdir(parents=True, exist_ok=True)
    write_csv(canonical / "same_trace_per_run.csv", per_run_rows)
    canonical_summary: list[dict[str, Any]] = []
    for row in summary_rows:
        canonical_summary.append(
            {
                "reconstruction_mode": row["reconstruction_mode"],
                "window_duration_s": row["duration_s"],
                "target_rate_sps": row["target_rate_sps"],
                "n_runs": row["n_runs"],
                "phase_count": row["phase_count"],
                "window_count_per_run": row["window_count_per_run"],
                "n_nominal_conditions": row["n_nominal_conditions"],
                "per_run_abs_error_q95_median_pct": row["run_abs_error_q95_median"],
                "per_run_abs_error_q95_q05_pct": row["run_abs_error_q95_q05"],
                "per_run_abs_error_q95_q95_pct": row["run_abs_error_q95_q95"],
                "per_run_abs_error_q95_max_pct": row["run_abs_error_q95_max"],
                "abs_error_median_pct": row["abs_error_pct_median"],
                "abs_error_q95_pct": row["abs_error_pct_q95"],
                "abs_error_max_pct": row["run_abs_error_max_max"],
                "statistical_unit_note": (
                    "Physical runs are the independent units. Window positions and "
                    "sampling-grid offsets are within-run sensitivity conditions."
                ),
            }
        )
    canonical_summary_path = canonical / "same_trace_summary.csv"
    write_csv(canonical_summary_path, canonical_summary)

    canonical_fmin: list[dict[str, Any]] = []
    for row in fmin_rows:
        rate = float(row["f_min_sps"])
        relation = str(row["f_min_relation"])
        if np.isfinite(rate):
            status = "lowest_tested_rate_passed" if relation == "<=" else "threshold_crossed"
            display = f"{relation} {rate:g} S/s"
        else:
            status = "not_reached"
            display = f"> {float(row['highest_tested_rate_sps']):g} S/s"
        canonical_fmin.append(
            {
                "reconstruction_mode": row["reconstruction_mode"],
                "window_duration_s": row["duration_s"],
                "error_limit_pct": row["threshold_pct"],
                "selected_rate_sps": rate,
                "f_min_relation": relation,
                "display": display,
                "status": status,
                "criterion": row["criterion"],
            }
        )
    write_csv(canonical / "f_min_by_duration.csv", canonical_fmin)

    canonical_highlighted = [
        row for row in canonical_summary
        if int(row["target_rate_sps"]) == highlighted
    ]
    write_csv(canonical / "highlighted_rate_by_duration.csv", canonical_highlighted)

    canonical_recommendations: list[dict[str, Any]] = []
    for row in recommendations:
        duration = float(row["minimum_duration_s"])
        relation = str(row["minimum_duration_relation"])
        if np.isfinite(duration):
            display = f"{relation} {duration:g} s"
        else:
            display = "not reached"
        canonical_recommendations.append(
            {
                "reconstruction_mode": row["reconstruction_mode"],
                "error_limit_pct": row["threshold_pct"],
                "minimum_passing_duration_s": duration,
                "minimum_duration_relation": relation,
                "display": display,
                "criterion": row["criterion"],
            }
        )
    write_json(
        canonical / "highlighted_rate_duration_decision.json",
        {
            "schema_version": _DURATION_ANALYSIS_SCHEMA_VERSION,
            "highlighted_rate_sps": highlighted,
            "runs": selected_runs,
            "recommendations": canonical_recommendations,
            "interpretation": recommendation_payload["interpretation"],
        },
    )
    write_csv(
        canonical / "highlighted_rate_duration_thresholds.csv",
        [
            row for row in canonical_fmin
            if row["reconstruction_mode"] == PHASE_ONLY_MODE
            and np.isfinite(float(row["selected_rate_sps"]))
            and float(row["selected_rate_sps"]) <= highlighted
        ],
    )
    write_json(
        canonical / "same_trace_duration_analysis.json",
        {
            "schema_version": _DURATION_ANALYSIS_SCHEMA_VERSION,
            "runs": selected_runs,
            "source_tree": "duration_sensitivity/per_run",
            "statistical_hierarchy": (
                "physical run -> q95 over window positions/grid offsets -> q95 across runs"
            ),
        },
    )
    return summary_path, fmin_path, recommendation_path
