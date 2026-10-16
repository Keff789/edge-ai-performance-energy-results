"""Aggregation subset from Common Reference PSD Tool 0.9.0 analysis.py/psd.py.

The historical input outcomes are already calculated; no trace reconstruction.
"""
from __future__ import annotations
from typing import Any
import numpy as np

def quantile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.quantile(values, q))

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

def summarise_common_trace(raw_rows):
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

    return summary_rows

def summarise_real_measurements(raw_rows):
    reference_median = float(raw_rows[0]["reference_5msps_median_j"])
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
    return summary_rows

def summarise_variance(variance_rows):
    analysis_rate = 1000000
    variance_summary_rows: list[dict[str, Any]] = []
    for target_rate in sorted({int(row["target_rate_sps"]) for row in variance_rows}):
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
    return variance_summary_rows
