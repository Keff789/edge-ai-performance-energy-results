from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.integrate import cumulative_trapezoid, trapezoid
from scipy.signal import find_peaks, welch

from .config import AnalysisConfig, FrequencyBand
from .io import load_measurement
from .resampling import load_cache_info, open_cache
from .utils import (
    LOGGER,
    quantile,
    read_json,
    stable_hash,
    utc_now_iso,
    write_csv,
    write_json,
)


def _slice_by_time(
    trace: np.ndarray,
    rate: int,
    start_s: float,
    duration_s: float,
) -> np.ndarray:
    start = int(round(start_s * rate))
    count = int(round(duration_s * rate))
    stop = start + count
    if start < 0 or stop > trace.size:
        raise ValueError(
            f"Requested interval [{start_s}, {start_s + duration_s}] s outside trace"
        )
    return np.asarray(trace[start:stop], dtype=np.float64)


def _f_at_cumulative(
    frequencies: np.ndarray,
    cumulative: np.ndarray,
    fraction: float,
) -> float:
    index = int(np.searchsorted(cumulative, fraction, side="left"))
    if index <= 0:
        return float(frequencies[0])
    if index >= frequencies.size:
        return float(frequencies[-1])
    x0, x1 = cumulative[index - 1], cumulative[index]
    f0, f1 = frequencies[index - 1], frequencies[index]
    if x1 <= x0:
        return float(f1)
    alpha = (fraction - x0) / (x1 - x0)
    return float(f0 + alpha * (f1 - f0))


def _cumulative_at_frequency(
    frequencies: np.ndarray,
    cumulative: np.ndarray,
    frequency_hz: float,
) -> float:
    if frequency_hz <= frequencies[0]:
        return float(cumulative[0])
    if frequency_hz >= frequencies[-1]:
        return float(cumulative[-1])
    return float(np.interp(frequency_hz, frequencies, cumulative))


def _band_fraction(
    frequencies: np.ndarray,
    cumulative: np.ndarray,
    band: FrequencyBand,
) -> float:
    low = _cumulative_at_frequency(frequencies, cumulative, band.low_hz)
    high_frequency = frequencies[-1] if band.high_hz is None else band.high_hz
    high = _cumulative_at_frequency(frequencies, cumulative, high_frequency)
    return max(0.0, float(high - low))


def _analysis_rates(cfg: AnalysisConfig) -> tuple[int, ...]:
    return (
        cfg.psd.analysis_rate_sps,
        *tuple(
            rate
            for rate in cfg.psd.sensitivity_rates_sps
            if rate != cfg.psd.analysis_rate_sps
        ),
    )


def _per_run_paths(
    cfg: AnalysisConfig,
    analysis_rate: int,
    run: int,
) -> tuple[Path, Path]:
    base = cfg.output_root / "psd" / "per_run" / f"{analysis_rate}Sps"
    return base / f"run_{run}.npz", base / f"run_{run}.json"


def _summary_root(cfg: AnalysisConfig, analysis_rate: int) -> Path:
    if analysis_rate == cfg.psd.analysis_rate_sps:
        return cfg.output_root / "psd"
    return cfg.output_root / "psd" / "sensitivity" / f"{analysis_rate}Sps"


def _psd_for_run_at_rate(
    cfg: AnalysisConfig,
    run: int,
    analysis_rate: int,
    force: bool = False,
) -> Path:
    out_path, meta_path = _per_run_paths(cfg, analysis_rate, run)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    signature = stable_hash(
        {
            "tool_schema": 3,
            "run": run,
            "analysis_rate_sps": analysis_rate,
            "psd": cfg.psd,
            "target_rates_sps": cfg.target_rates_sps,
            "quality": cfg.resampling_quality,
        }
    )

    if not force and out_path.is_file() and meta_path.is_file():
        metadata = read_json(meta_path)
        if metadata.get("signature") == signature:
            LOGGER.info(
                "PSD result exists: run %d at %d S/s",
                run,
                analysis_rate,
            )
            return out_path

    measurement = load_measurement(
        cfg.dataset_root / cfg.reference_rate_directory / str(run)
    )
    cache_info = load_cache_info(cfg.output_root, analysis_rate, run)
    trace = open_cache(cache_info)
    rate = cache_info.sample_rate_sps

    active_start = measurement.start_time_s + (
        measurement.duration_s - cfg.psd.active_duration_s
    ) / 2.0
    idle_stop = measurement.start_time_s - cfg.psd.idle_gap_s
    idle_start = idle_stop - cfg.psd.idle_duration_s
    if idle_start < 0:
        raise ValueError(f"Run {run} has insufficient pre-benchmark idle data for PSD")

    active = _slice_by_time(trace, rate, active_start, cfg.psd.active_duration_s)
    idle = _slice_by_time(trace, rate, idle_start, cfg.psd.idle_duration_s)

    nperseg = int(round(cfg.psd.segment_duration_s * rate))
    noverlap = int(round(cfg.psd.overlap_fraction * nperseg))
    if nperseg <= 1 or nperseg > idle.size:
        raise ValueError("Invalid PSD segment duration")

    frequencies, active_psd = welch(
        active,
        fs=rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend="constant",
        scaling="density",
        average="mean",
    )
    idle_frequencies, idle_psd = welch(
        idle,
        fs=rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend="constant",
        scaling="density",
        average="mean",
    )
    if not np.array_equal(frequencies, idle_frequencies):
        raise RuntimeError("Active and idle PSD frequency grids differ")

    excess_psd = np.maximum(active_psd - idle_psd, 0.0)
    cumulative_raw = cumulative_trapezoid(
        excess_psd,
        frequencies,
        initial=0.0,
    )
    total = float(cumulative_raw[-1])
    if not np.isfinite(total) or total <= 0:
        raise RuntimeError(f"Run {run}: non-positive excess PSD integral")
    cumulative = cumulative_raw / total

    metrics: dict[str, float] = {
        "active_psd_integral_w2": float(trapezoid(active_psd, frequencies)),
        "idle_psd_integral_w2": float(trapezoid(idle_psd, frequencies)),
        "excess_psd_integral_w2": total,
    }
    for fraction in cfg.psd.cumulative_percentiles:
        label = int(round(fraction * 100))
        frequency = _f_at_cumulative(frequencies, cumulative, fraction)
        metrics[f"f{label}_hz"] = frequency
        metrics[f"nyquist_sample_rate_for_f{label}_sps"] = 2.0 * frequency

    variance_capture = {
        str(target_rate): _cumulative_at_frequency(
            frequencies,
            cumulative,
            target_rate / 2.0,
        )
        for target_rate in cfg.psd.variance_capture_rates_sps
    }
    band_fractions = {
        band.label: _band_fraction(frequencies, cumulative, band)
        for band in cfg.psd.variance_bands
    }

    np.savez_compressed(
        out_path,
        frequencies_hz=frequencies,
        active_psd_w2_per_hz=active_psd,
        idle_psd_w2_per_hz=idle_psd,
        excess_psd_w2_per_hz=excess_psd,
        cumulative_excess=cumulative,
    )
    write_json(
        meta_path,
        {
            "created_utc": utc_now_iso(),
            "signature": signature,
            "run": run,
            "analysis_rate_sps": rate,
            "analysis_nyquist_hz": rate / 2.0,
            "active_start_s": active_start,
            "active_duration_s": cfg.psd.active_duration_s,
            "idle_start_s": idle_start,
            "idle_duration_s": cfg.psd.idle_duration_s,
            "nperseg": nperseg,
            "noverlap": noverlap,
            "variance_capture_below_nyquist_by_target_rate": variance_capture,
            "variance_fraction_by_frequency_band": band_fractions,
            **metrics,
        },
    )
    LOGGER.info(
        "PSD run %d at %d S/s: %s",
        run,
        rate,
        ", ".join(
            f"{key}={value:.3f}"
            for key, value in metrics.items()
            if key.startswith("f") and key.endswith("_hz")
        ),
    )
    return out_path


def psd_for_run(cfg: AnalysisConfig, run: int, force: bool = False) -> Path:
    primary: Path | None = None
    for analysis_rate in _analysis_rates(cfg):
        path = _psd_for_run_at_rate(
            cfg,
            run,
            analysis_rate,
            force=force,
        )
        if analysis_rate == cfg.psd.analysis_rate_sps:
            primary = path
    if primary is None:
        raise RuntimeError("Primary PSD analysis did not run")
    return primary


def _aggregate_numeric(values: np.ndarray) -> dict[str, float | int]:
    return {
        "n_runs": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "q05": quantile(values, 0.05),
        "q95": quantile(values, 0.95),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def _summarise_psd_rate(
    cfg: AnalysisConfig,
    runs: Sequence[int],
    analysis_rate: int,
) -> tuple[Path, ...]:
    output_root = _summary_root(cfg, analysis_rate)
    output_root.mkdir(parents=True, exist_ok=True)

    spectra: list[dict[str, np.ndarray]] = []
    metadata_by_run: dict[int, dict[str, Any]] = {}
    for run in runs:
        path, meta_path = _per_run_paths(cfg, analysis_rate, run)
        metadata = read_json(meta_path)
        metadata_by_run[run] = metadata
        with np.load(path) as data:
            spectra.append({key: np.asarray(data[key]) for key in data.files})

    frequencies = spectra[0]["frequencies_hz"]
    for item in spectra[1:]:
        if not np.array_equal(frequencies, item["frequencies_hz"]):
            raise RuntimeError(
                f"PSD frequency grids differ between runs at {analysis_rate} S/s"
            )

    active_stack = np.vstack(
        [item["active_psd_w2_per_hz"] for item in spectra]
    )
    idle_stack = np.vstack(
        [item["idle_psd_w2_per_hz"] for item in spectra]
    )
    excess_stack = np.vstack(
        [item["excess_psd_w2_per_hz"] for item in spectra]
    )
    cumulative_stack = np.vstack(
        [item["cumulative_excess"] for item in spectra]
    )

    summary_path = output_root / "psd_summary.npz"
    np.savez_compressed(
        summary_path,
        frequencies_hz=frequencies,
        analysis_rate_sps=np.asarray([analysis_rate], dtype=np.int64),
        n_runs=np.asarray([len(runs)], dtype=np.int64),
        active_median=np.median(active_stack, axis=0),
        active_q10=np.quantile(active_stack, 0.10, axis=0),
        active_q90=np.quantile(active_stack, 0.90, axis=0),
        idle_median=np.median(idle_stack, axis=0),
        idle_q10=np.quantile(idle_stack, 0.10, axis=0),
        idle_q90=np.quantile(idle_stack, axis=0, q=0.90),
        excess_median=np.median(excess_stack, axis=0),
        cumulative_median=np.median(cumulative_stack, axis=0),
        cumulative_q10=np.quantile(cumulative_stack, 0.10, axis=0),
        cumulative_q90=np.quantile(cumulative_stack, 0.90, axis=0),
    )

    metric_keys = [
        "active_psd_integral_w2",
        "idle_psd_integral_w2",
        "excess_psd_integral_w2",
    ]
    for fraction in cfg.psd.cumulative_percentiles:
        label = int(round(fraction * 100))
        metric_keys.extend(
            [f"f{label}_hz", f"nyquist_sample_rate_for_f{label}_sps"]
        )

    metric_rows: list[dict[str, Any]] = []
    for run in runs:
        row = {"run": run, "analysis_rate_sps": analysis_rate}
        row.update(
            {key: float(metadata_by_run[run][key]) for key in metric_keys}
        )
        metric_rows.append(row)
    metrics_path = output_root / "psd_metrics_per_run.csv"
    write_csv(metrics_path, metric_rows)

    aggregate_rows: list[dict[str, Any]] = []
    units = {
        "active_psd_integral_w2": "W^2",
        "idle_psd_integral_w2": "W^2",
        "excess_psd_integral_w2": "W^2",
    }
    for key in metric_keys:
        values = np.asarray(
            [float(row[key]) for row in metric_rows],
            dtype=np.float64,
        )
        aggregate = _aggregate_numeric(values)
        aggregate_rows.append(
            {
                "analysis_rate_sps": analysis_rate,
                "metric": key,
                "unit": units.get(
                    key,
                    "S/s" if key.endswith("_sps") else "Hz",
                ),
                **aggregate,
            }
        )
    aggregate_path = output_root / "psd_metrics_summary.csv"
    write_csv(aggregate_path, aggregate_rows)

    variance_rows: list[dict[str, Any]] = []
    for run in runs:
        capture = metadata_by_run[run][
            "variance_capture_below_nyquist_by_target_rate"
        ]
        for target_rate in cfg.psd.variance_capture_rates_sps:
            variance_rows.append(
                {
                    "run": run,
                    "analysis_rate_sps": analysis_rate,
                    "target_rate_sps": target_rate,
                    "nyquist_hz": target_rate / 2.0,
                    "variance_fraction_below_nyquist": float(
                        capture[str(target_rate)]
                    ),
                    "variance_percent_below_nyquist": 100.0
                    * float(capture[str(target_rate)]),
                }
            )
    variance_per_run_path = output_root / "variance_capture_per_run.csv"
    write_csv(variance_per_run_path, variance_rows)

    variance_summary_rows: list[dict[str, Any]] = []
    for target_rate in cfg.psd.variance_capture_rates_sps:
        values = np.asarray(
            [
                float(row["variance_fraction_below_nyquist"])
                for row in variance_rows
                if int(row["target_rate_sps"]) == target_rate
            ],
            dtype=np.float64,
        )
        aggregate = _aggregate_numeric(values)
        variance_summary_rows.append(
            {
                "analysis_rate_sps": analysis_rate,
                "target_rate_sps": target_rate,
                "nyquist_hz": target_rate / 2.0,
                "n_runs": aggregate["n_runs"],
                "fraction_mean": aggregate["mean"],
                "fraction_median": aggregate["median"],
                "fraction_q05": aggregate["q05"],
                "fraction_q95": aggregate["q95"],
                "fraction_min": aggregate["min"],
                "fraction_max": aggregate["max"],
                "percent_median": 100.0 * float(aggregate["median"]),
                "percent_q05": 100.0 * float(aggregate["q05"]),
                "percent_q95": 100.0 * float(aggregate["q95"]),
            }
        )
    variance_summary_path = output_root / "variance_capture_summary.csv"
    write_csv(variance_summary_path, variance_summary_rows)

    threshold_rows: list[dict[str, Any]] = []
    ordered_variance = sorted(
        variance_summary_rows,
        key=lambda row: int(row["target_rate_sps"]),
    )
    lowest_rate = int(ordered_variance[0]["target_rate_sps"])
    highest_rate = int(ordered_variance[-1]["target_rate_sps"])
    for threshold in cfg.psd.variance_capture_thresholds:
        selected: int | None = None
        for index, row in enumerate(ordered_variance):
            higher_q05 = [
                float(candidate["fraction_q05"])
                for candidate in ordered_variance[index:]
            ]
            if higher_q05 and all(value >= threshold for value in higher_q05):
                selected = int(row["target_rate_sps"])
                break

        if selected is None:
            relation = ">"
            status = "not_identified"
            display = f"> {highest_rate} S/s"
        elif selected == lowest_rate:
            relation = "<="
            status = "at_or_below_lowest_evaluated"
            display = f"≤ {selected} S/s"
        else:
            relation = "="
            status = "identified_within_evaluated_range"
            display = f"{selected} S/s"

        threshold_rows.append(
            {
                "analysis_rate_sps": analysis_rate,
                "variance_fraction": threshold,
                "variance_percent": 100.0 * threshold,
                "sampling_rate_bound_sps": (
                    selected if selected is not None else highest_rate
                ),
                "relation": relation,
                "status": status,
                "display": display,
                "lowest_evaluated_rate_sps": lowest_rate,
                "highest_evaluated_rate_sps": highest_rate,
                "criterion": (
                    "5th percentile across runs is at least the requested "
                    "variance fraction; all higher evaluated rates must also pass"
                ),
            }
        )
    variance_thresholds_path = output_root / "variance_capture_thresholds.csv"
    write_csv(variance_thresholds_path, threshold_rows)

    band_rows: list[dict[str, Any]] = []
    for run in runs:
        fractions = metadata_by_run[run][
            "variance_fraction_by_frequency_band"
        ]
        for band in cfg.psd.variance_bands:
            value = float(fractions[band.label])
            band_rows.append(
                {
                    "run": run,
                    "analysis_rate_sps": analysis_rate,
                    "band": band.label,
                    "low_hz": band.low_hz,
                    "high_hz": band.high_hz,
                    "variance_fraction": value,
                    "variance_percent": 100.0 * value,
                }
            )
    bands_per_run_path = output_root / "variance_bands_per_run.csv"
    write_csv(bands_per_run_path, band_rows)

    band_summary_rows: list[dict[str, Any]] = []
    for band in cfg.psd.variance_bands:
        values = np.asarray(
            [
                float(row["variance_fraction"])
                for row in band_rows
                if row["band"] == band.label
            ],
            dtype=np.float64,
        )
        aggregate = _aggregate_numeric(values)
        band_summary_rows.append(
            {
                "analysis_rate_sps": analysis_rate,
                "band": band.label,
                "low_hz": band.low_hz,
                "high_hz": band.high_hz,
                "n_runs": aggregate["n_runs"],
                "fraction_mean": aggregate["mean"],
                "fraction_median": aggregate["median"],
                "fraction_q05": aggregate["q05"],
                "fraction_q95": aggregate["q95"],
                "percent_median": 100.0 * float(aggregate["median"]),
                "percent_q05": 100.0 * float(aggregate["q05"]),
                "percent_q95": 100.0 * float(aggregate["q95"]),
            }
        )
    bands_summary_path = output_root / "variance_bands_summary.csv"
    write_csv(bands_summary_path, band_summary_rows)

    median_excess = np.median(excess_stack, axis=0)
    mask = (
        (frequencies > 0)
        & (frequencies <= cfg.psd.peak_max_frequency_hz)
    )
    f_subset = frequencies[mask]
    p_subset = median_excess[mask]
    db = 10.0 * np.log10(np.maximum(p_subset, np.finfo(float).tiny))
    peak_indices, properties = find_peaks(db, prominence=3.0)
    prominence_by_index = {
        int(index): float(prominence)
        for index, prominence in zip(
            peak_indices,
            properties["prominences"],
        )
    }
    ranked = sorted(
        peak_indices,
        key=lambda index: p_subset[index],
        reverse=True,
    )[: cfg.psd.peak_count]
    peak_rows = [
        {
            "rank": rank + 1,
            "analysis_rate_sps": analysis_rate,
            "spectral_component": "narrowband_peak",
            "frequency_hz": float(f_subset[index]),
            "psd_w2_per_hz": float(p_subset[index]),
            "psd_db_w2_per_hz": float(db[index]),
            "prominence_db": prominence_by_index[int(index)],
        }
        for rank, index in enumerate(ranked)
    ]
    peaks_path = output_root / "dominant_peaks.csv"
    write_csv(
        peaks_path,
        peak_rows,
        fieldnames=[
            "rank",
            "analysis_rate_sps",
            "spectral_component",
            "frequency_hz",
            "psd_w2_per_hz",
            "psd_db_w2_per_hz",
            "prominence_db",
        ],
    )

    return (
        summary_path,
        aggregate_path,
        peaks_path,
        variance_summary_path,
        variance_thresholds_path,
        bands_summary_path,
    )


def _metric_value(metadata: dict[str, Any], key: str) -> float:
    return float(metadata[key])


def _summarise_bandwidth_sensitivity(
    cfg: AnalysisConfig,
    runs: Sequence[int],
) -> tuple[Path, Path, Path] | None:
    if not cfg.psd.sensitivity_rates_sps:
        return None

    primary_rate = cfg.psd.analysis_rate_sps
    per_run_rows: list[dict[str, Any]] = []
    for run in runs:
        _, primary_meta_path = _per_run_paths(cfg, primary_rate, run)
        primary = read_json(primary_meta_path)
        for sensitivity_rate in cfg.psd.sensitivity_rates_sps:
            _, sensitivity_meta_path = _per_run_paths(
                cfg,
                sensitivity_rate,
                run,
            )
            sensitivity = read_json(sensitivity_meta_path)
            row: dict[str, Any] = {
                "run": run,
                "primary_analysis_rate_sps": primary_rate,
                "sensitivity_analysis_rate_sps": sensitivity_rate,
                "primary_nyquist_hz": primary_rate / 2.0,
                "sensitivity_nyquist_hz": sensitivity_rate / 2.0,
                "primary_excess_psd_integral_w2": _metric_value(
                    primary,
                    "excess_psd_integral_w2",
                ),
                "sensitivity_excess_psd_integral_w2": _metric_value(
                    sensitivity,
                    "excess_psd_integral_w2",
                ),
            }
            primary_integral = float(
                row["primary_excess_psd_integral_w2"]
            )
            sensitivity_integral = float(
                row["sensitivity_excess_psd_integral_w2"]
            )
            row["excess_psd_integral_relative_delta"] = (
                (sensitivity_integral - primary_integral) / primary_integral
                if primary_integral != 0
                else float("nan")
            )

            frequency_passes: list[bool] = []
            for fraction in cfg.psd.cumulative_percentiles:
                label = int(round(fraction * 100))
                key = f"f{label}_hz"
                primary_value = _metric_value(primary, key)
                sensitivity_value = _metric_value(sensitivity, key)
                relative_delta = (
                    (sensitivity_value - primary_value) / primary_value
                    if primary_value != 0
                    else float("nan")
                )
                row[f"primary_{key}"] = primary_value
                row[f"sensitivity_{key}"] = sensitivity_value
                row[f"{key}_delta_hz"] = (
                    sensitivity_value - primary_value
                )
                row[f"{key}_relative_delta"] = relative_delta
                passed = bool(
                    np.isfinite(relative_delta)
                    and abs(relative_delta)
                    <= cfg.psd.sensitivity_relative_frequency_tolerance
                )
                row[f"{key}_pass"] = passed
                frequency_passes.append(passed)

            variance_passes: list[bool] = []
            primary_capture = primary[
                "variance_capture_below_nyquist_by_target_rate"
            ]
            sensitivity_capture = sensitivity[
                "variance_capture_below_nyquist_by_target_rate"
            ]
            for target_rate in cfg.psd.sensitivity_check_rates_sps:
                primary_fraction = float(primary_capture[str(target_rate)])
                sensitivity_fraction = float(
                    sensitivity_capture[str(target_rate)]
                )
                delta = sensitivity_fraction - primary_fraction
                prefix = f"variance_at_{target_rate}_sps"
                row[f"primary_{prefix}"] = primary_fraction
                row[f"sensitivity_{prefix}"] = sensitivity_fraction
                row[f"{prefix}_delta"] = delta
                passed = bool(
                    abs(delta)
                    <= cfg.psd.sensitivity_variance_fraction_tolerance
                )
                row[f"{prefix}_pass"] = passed
                variance_passes.append(passed)

            row["frequency_metrics_pass"] = all(frequency_passes)
            row["variance_metrics_pass"] = all(variance_passes)
            row["overall_pass"] = all(
                frequency_passes + variance_passes
            )
            per_run_rows.append(row)

    per_run_path = (
        cfg.output_root / "psd" / "psd_bandwidth_sensitivity_per_run.csv"
    )
    write_csv(per_run_path, per_run_rows)

    summary_rows: list[dict[str, Any]] = []
    for sensitivity_rate in cfg.psd.sensitivity_rates_sps:
        subset = [
            row
            for row in per_run_rows
            if int(row["sensitivity_analysis_rate_sps"])
            == sensitivity_rate
        ]
        row: dict[str, Any] = {
            "primary_analysis_rate_sps": primary_rate,
            "sensitivity_analysis_rate_sps": sensitivity_rate,
            "n_runs": len(subset),
            "frequency_relative_tolerance": (
                cfg.psd.sensitivity_relative_frequency_tolerance
            ),
            "variance_fraction_tolerance": (
                cfg.psd.sensitivity_variance_fraction_tolerance
            ),
        }
        summary_passes: list[bool] = []
        for fraction in cfg.psd.cumulative_percentiles:
            label = int(round(fraction * 100))
            key = f"f{label}_hz_relative_delta"
            values = np.asarray(
                [abs(float(item[key])) for item in subset],
                dtype=np.float64,
            )
            aggregate = _aggregate_numeric(values)
            row[f"abs_{key}_median"] = aggregate["median"]
            row[f"abs_{key}_q95"] = aggregate["q95"]
            passed = bool(
                float(aggregate["q95"])
                <= cfg.psd.sensitivity_relative_frequency_tolerance
            )
            row[f"{key}_q95_pass"] = passed
            summary_passes.append(passed)

        for target_rate in cfg.psd.sensitivity_check_rates_sps:
            key = f"variance_at_{target_rate}_sps_delta"
            values = np.asarray(
                [abs(float(item[key])) for item in subset],
                dtype=np.float64,
            )
            aggregate = _aggregate_numeric(values)
            row[f"abs_{key}_median"] = aggregate["median"]
            row[f"abs_{key}_q95"] = aggregate["q95"]
            passed = bool(
                float(aggregate["q95"])
                <= cfg.psd.sensitivity_variance_fraction_tolerance
            )
            row[f"{key}_q95_pass"] = passed
            summary_passes.append(passed)

        integral_values = np.asarray(
            [
                abs(float(item["excess_psd_integral_relative_delta"]))
                for item in subset
            ],
            dtype=np.float64,
        )
        integral_aggregate = _aggregate_numeric(integral_values)
        row["abs_excess_psd_integral_relative_delta_median"] = (
            integral_aggregate["median"]
        )
        row["abs_excess_psd_integral_relative_delta_q95"] = (
            integral_aggregate["q95"]
        )
        row["overall_pass"] = all(summary_passes)
        row["criterion"] = (
            "95th percentile of absolute f95/f99 relative delta and selected "
            "variance-fraction delta must remain within configured tolerances."
        )
        summary_rows.append(row)

    summary_path = (
        cfg.output_root / "psd" / "psd_bandwidth_sensitivity_summary.csv"
    )
    write_csv(summary_path, summary_rows)
    decision_path = (
        cfg.output_root / "psd" / "psd_bandwidth_sensitivity_decision.json"
    )
    write_json(
        decision_path,
        {
            "created_utc": utc_now_iso(),
            "primary_analysis_rate_sps": primary_rate,
            "sensitivity_rates_sps": list(cfg.psd.sensitivity_rates_sps),
            "frequency_relative_tolerance": (
                cfg.psd.sensitivity_relative_frequency_tolerance
            ),
            "variance_fraction_tolerance": (
                cfg.psd.sensitivity_variance_fraction_tolerance
            ),
            "all_sensitivity_checks_pass": all(
                bool(row["overall_pass"]) for row in summary_rows
            ),
            "results": summary_rows,
            "note": (
                "The excess-PSD integral delta is reported diagnostically but "
                "is not part of the automatic pass criterion."
            ),
        },
    )
    return per_run_path, summary_path, decision_path


def summarise_psd(cfg: AnalysisConfig, runs: Sequence[int]) -> tuple[Path, ...]:
    primary_outputs = _summarise_psd_rate(
        cfg,
        runs,
        cfg.psd.analysis_rate_sps,
    )
    for sensitivity_rate in cfg.psd.sensitivity_rates_sps:
        _summarise_psd_rate(cfg, runs, sensitivity_rate)
    sensitivity_outputs = _summarise_bandwidth_sensitivity(cfg, runs)
    if sensitivity_outputs is None:
        return primary_outputs
    return (*primary_outputs, *sensitivity_outputs)
