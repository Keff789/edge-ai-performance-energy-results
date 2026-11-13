"""Pure plotting subset from Common Reference PSD Tool 0.9.0 commonref/plotting.py.

Retains the original energy-error and five spectral views; adds SVG export.
No raw-waveform, cache, hardware, calibration or source-tree access.
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
def configure_matplotlib():
    global plt
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

ANTI_ALIAS_MODE = "anti_alias"
PHASE_ONLY_MODE = "phase_only"

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

def human_rate(rate: float) -> str:
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:g} MS/s"
    if rate >= 1_000:
        return f"{rate / 1_000:g} kS/s"
    return f"{rate:g} S/s"

def _save_figure(fig: plt.Figure, base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(base.with_suffix(".png"), dpi=220, bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)

def _run_label(n_runs: int) -> str:
    return f"pilot, n={n_runs}" if n_runs == 1 else f"historical runs 2–14, n={n_runs}"

def plot_energy_error(cfg) -> Path:
    configure_matplotlib()
    common_rows = read_csv(cfg.output_root / "common_trace" / "common_trace_summary.csv")
    real_rows = read_csv(cfg.output_root / "real_measurements" / "real_measurements_summary.csv")

    n_runs = max(int(row["n_runs"]) for row in common_rows)
    available_modes = [
        mode
        for mode in (ANTI_ALIAS_MODE, PHASE_ONLY_MODE)
        if any(row["reconstruction_mode"] == mode for row in common_rows)
    ]

    fig, axes = plt.subplots(
        1 + len(available_modes),
        1,
        figsize=(8.3, 3.35 + 2.35 * len(available_modes)),
        sharex=True,
        gridspec_kw={"height_ratios": [1.15] + [1.0] * len(available_modes)},
    )
    axes = np.atleast_1d(axes)
    ax_real = axes[0]

    real_rows.sort(key=lambda row: int(row["directory_rate_sps"]))
    real_rate = np.asarray([int(row["directory_rate_sps"]) for row in real_rows])
    real_median = np.asarray([float(row["error_median_pct"]) for row in real_rows])
    real_q05 = np.asarray([float(row["error_q05_pct"]) for row in real_rows])
    real_q95 = np.asarray([float(row["error_q95_pct"]) for row in real_rows])

    ax_real.errorbar(
        real_rate,
        real_median,
        yerr=np.vstack([real_median - real_q05, real_q95 - real_median]),
        fmt="s",
        markersize=4,
        capsize=2,
        linestyle="none",
        label="Independent real measurements",
    )
    ax_real.plot(real_rate, real_median, linewidth=0.8, alpha=0.65)
    for limit in (1.0, 2.0, 5.0):
        ax_real.axhline(limit, linewidth=0.55, linestyle="--", alpha=0.65)
        ax_real.axhline(-limit, linewidth=0.55, linestyle="--", alpha=0.65)
    ax_real.axhline(0.0, linewidth=0.8)
    ax_real.axvline(2000, linewidth=0.9, linestyle=":", label="2 kS/s")
    ax_real.set_ylabel("Independent-run\nenergy error (%)")
    ax_real.grid(True, which="both", alpha=0.3)
    ax_real.legend(fontsize=8, loc="best")
    ax_real.set_title(
        "Jetson GEMM-FP16 energy error: independent runs and same-trace reconstructions "
        f"({_run_label(n_runs)})"
    )

    for panel_index, mode in enumerate(available_modes, start=1):
        ax = axes[panel_index]
        rows = [row for row in common_rows if row["reconstruction_mode"] == mode]
        rows.sort(key=lambda row: int(row["target_rate_sps"]))
        rates = np.asarray([int(row["target_rate_sps"]) for row in rows], dtype=float)
        med_pct = np.asarray([float(row["error_median_pct"]) for row in rows])
        q05_pct = np.asarray([float(row["error_q05_pct"]) for row in rows])
        q95_pct = np.asarray([float(row["error_q95_pct"]) for row in rows])
        anchors = np.asarray(
            [
                str(row["is_high_rate_anchor"]).lower() in {"true", "1", "yes"}
                for row in rows
            ]
        )

        if mode == ANTI_ALIAS_MODE:
            scale = 10_000.0
            unit = "ppm"
            label = "Anti-aliased common trace (controlled best case)"
            marker = "o"
        else:
            max_abs_pct = float(
                np.max(np.abs(np.concatenate([med_pct, q05_pct, q95_pct])))
            )
            if max_abs_pct < 0.01:
                scale = 10_000.0
                unit = "ppm"
            else:
                scale = 1.0
                unit = "%"
            label = "Phase-only common trace (no target-rate AA filter)"
            marker = "^"

        median = scale * med_pct
        q05 = scale * q05_pct
        q95 = scale * q95_pct
        ax.fill_between(rates, q05, q95, alpha=0.20, label="5th–95th percentile")
        ax.plot(
            rates,
            median,
            marker=marker,
            markersize=3.5,
            linewidth=1.15,
            label=label,
        )
        if np.any(anchors):
            ax.scatter(
                rates[anchors],
                median[anchors],
                marker="x",
                s=30,
                label="Bandwidth-saturated high-rate anchors",
                zorder=3,
            )
        if mode == PHASE_ONLY_MODE:
            observed = float(
                np.max(np.abs(np.concatenate([median, q05, q95])))
            )
            if unit == "%":
                y_limit = max(0.05, 1.15 * observed)
                # Draw a tolerance line only when it is close enough to the
                # observed range; otherwise it would flatten the data visually.
                for threshold in (1.0, 5.0):
                    if threshold <= 1.25 * y_limit:
                        ax.axhline(
                            threshold, linewidth=0.5, linestyle="--", alpha=0.55
                        )
                        ax.axhline(
                            -threshold, linewidth=0.5, linestyle="--", alpha=0.55
                        )
            else:
                y_limit = max(1.0, 1.15 * observed)
            ax.set_ylim(-y_limit, y_limit)
        ax.axhline(0.0, linewidth=0.8)
        ax.axvline(2000, linewidth=0.9, linestyle=":")
        ax.set_ylabel(f"Same-trace\nenergy error ({unit})")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7.5, loc="best")

    axes[-1].set_xscale("log")
    axes[-1].set_xlabel("Nominal sampling rate (S/s)")
    base = cfg.output_root / "figures" / "common_trace_energy_error"
    _save_figure(fig, base)
    return base

def _load_psd_summary(cfg, analysis_rate_sps=None):
    rows = read_csv(cfg.output_root / "psd" / "psd_plot_samples.csv")
    result = {key: np.asarray([float(row[key]) for row in rows]) for key in rows[0]}
    result["n_runs_value"] = 13
    result["analysis_rate_value"] = 1000000
    return result


def _spectral_plot_indices(size: int, max_points: int) -> np.ndarray:
    """Return a compact index set that retains linear and low-frequency detail."""
    if size <= max_points:
        return np.arange(size, dtype=np.int64)
    half = max(2, max_points // 2)
    linear = np.linspace(0, size - 1, half, dtype=np.int64)
    geometric = np.geomspace(1, size, half, dtype=np.float64) - 1.0
    geometric = np.rint(geometric).astype(np.int64)
    return np.unique(
        np.concatenate(
            [np.asarray([0, size - 1], dtype=np.int64), linear, geometric]
        )
    )

def _frequency_at_fraction(
    frequencies: np.ndarray,
    cumulative: np.ndarray,
    fraction: float,
) -> float:
    index = int(np.searchsorted(cumulative, fraction, side="left"))
    index = min(max(index, 1), frequencies.size - 1)
    x0, x1 = cumulative[index - 1], cumulative[index]
    f0, f1 = frequencies[index - 1], frequencies[index]
    if x1 <= x0:
        return float(f1)
    return float(f0 + (fraction - x0) / (x1 - x0) * (f1 - f0))

def plot_psd(cfg) -> tuple[Path, ...]:
    configure_matplotlib()
    data = _load_psd_summary(cfg)
    frequencies = np.asarray(data["frequencies_hz"])
    active_median = np.asarray(data["active_median"])
    active_q10 = np.asarray(data["active_q10"])
    active_q90 = np.asarray(data["active_q90"])
    idle_median = np.asarray(data["idle_median"])
    cumulative_median = np.asarray(data["cumulative_median"])
    cumulative_q10 = np.asarray(data["cumulative_q10"])
    cumulative_q90 = np.asarray(data["cumulative_q90"])
    n_runs = int(data["n_runs_value"])

    percentile_frequencies = {
        fraction: _frequency_at_fraction(frequencies, cumulative_median, fraction)
        for fraction in cfg.psd.cumulative_percentiles
    }

    positive = frequencies > 0
    f = frequencies[positive]
    tiny = np.finfo(float).tiny
    active_db = 10.0 * np.log10(np.maximum(active_median[positive], tiny))
    active_q10_db = 10.0 * np.log10(np.maximum(active_q10[positive], tiny))
    active_q90_db = 10.0 * np.log10(np.maximum(active_q90[positive], tiny))
    idle_db = 10.0 * np.log10(np.maximum(idle_median[positive], tiny))
    spectral_indices = _spectral_plot_indices(
        f.size, cfg.psd.plot_max_points
    )
    f_plot = f[spectral_indices]
    active_db_plot = active_db[spectral_indices]
    active_q10_db_plot = active_q10_db[spectral_indices]
    active_q90_db_plot = active_q90_db[spectral_indices]
    idle_db_plot = idle_db[spectral_indices]

    fig = plt.figure(figsize=(8.3, 4.8))
    ax = fig.add_subplot(1, 1, 1)
    if n_runs > 1:
        ax.fill_between(
            f_plot,
            active_q10_db_plot,
            active_q90_db_plot,
            alpha=0.20,
            label="Active: 10th–90th percentile",
        )
    ax.plot(f_plot, active_db_plot, linewidth=1.0, label="Active median")
    ax.plot(f_plot, idle_db_plot, linewidth=0.9, label="Pre-benchmark idle median")
    for rate in cfg.psd.full_frequency_nyquist_rates_sps:
        nyquist = rate / 2.0
        if nyquist <= f[-1]:
            ax.axvline(
                nyquist,
                linewidth=0.75,
                linestyle=":",
                label=f"Nyquist at {human_rate(rate)}",
            )
    for fraction, value in percentile_frequencies.items():
        ax.axvline(
            value,
            linewidth=0.8,
            linestyle="--",
            label=f"f{int(fraction * 100)} ≈ {value / 1000:.1f} kHz",
        )
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(r"PSD of mean-removed power ($\mathrm{dB\;W^2/Hz}$)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    ax.set_title(f"Active and idle power spectra ({_run_label(n_runs)})")
    full_base = cfg.output_root / "figures" / "psd_active_vs_idle_full"
    _save_figure(fig, full_base)

    low_mask = f <= min(5000.0, f[-1])
    fig = plt.figure(figsize=(8.3, 4.6))
    ax = fig.add_subplot(1, 1, 1)
    ax.plot(f[low_mask], active_db[low_mask], linewidth=1.0, label="Active median")
    ax.plot(f[low_mask], idle_db[low_mask], linewidth=0.9, label="Pre-benchmark idle median")
    for rate in cfg.psd.low_frequency_nyquist_rates_sps:
        ax.axvline(
            rate / 2.0,
            linewidth=0.75,
            linestyle=":",
            label=f"Nyquist at {human_rate(rate)}",
        )
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(r"PSD of mean-removed power ($\mathrm{dB\;W^2/Hz}$)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title(f"Low-frequency detail ({_run_label(n_runs)})")
    low_base = cfg.output_root / "figures" / "psd_active_vs_idle_0_5khz"
    _save_figure(fig, low_base)

    cumulative_positive = frequencies > 0
    cumulative_f = frequencies[cumulative_positive]
    cumulative_med = cumulative_median[cumulative_positive]
    cumulative_lo = cumulative_q10[cumulative_positive]
    cumulative_hi = cumulative_q90[cumulative_positive]
    cumulative_indices = _spectral_plot_indices(
        cumulative_f.size, cfg.psd.plot_max_points
    )
    cumulative_f_plot = cumulative_f[cumulative_indices]
    cumulative_med_plot = cumulative_med[cumulative_indices]
    cumulative_lo_plot = cumulative_lo[cumulative_indices]
    cumulative_hi_plot = cumulative_hi[cumulative_indices]

    fig = plt.figure(figsize=(8.3, 4.6))
    ax = fig.add_subplot(1, 1, 1)
    if n_runs > 1:
        ax.fill_between(
            cumulative_f_plot,
            cumulative_lo_plot,
            cumulative_hi_plot,
            alpha=0.20,
            label="10th–90th percentile",
        )
    ax.plot(
        cumulative_f_plot,
        cumulative_med_plot,
        linewidth=1.2,
        label="Median cumulative excess PSD",
    )
    for fraction, value in percentile_frequencies.items():
        ax.axhline(fraction, linewidth=0.75, linestyle="--")
        ax.axvline(
            value,
            linewidth=0.8,
            linestyle=":",
            label=f"f{int(fraction * 100)} ≈ {value / 1000:.1f} kHz",
        )
    for rate in cfg.psd.full_frequency_nyquist_rates_sps:
        nyquist = rate / 2.0
        if nyquist <= frequencies[-1]:
            ax.axvline(
                nyquist,
                linewidth=0.6,
                linestyle="-.",
                label=f"Nyquist at {human_rate(rate)}",
            )
    ax.set_xscale("log")
    ax.set_xlim(max(frequencies[1], 1.0), frequencies[-1])
    ax.set_ylim(0.0, 1.01)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Cumulative fraction of workload-related power variance")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    ax.set_title(f"Cumulative workload-related power variance ({_run_label(n_runs)})")
    cumulative_base = cfg.output_root / "figures" / "psd_cumulative"
    _save_figure(fig, cumulative_base)

    # Compact paper-oriented two-panel figure.
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.7))
    ax_psd, ax_cum = axes
    ax_psd.plot(f_plot, active_db_plot, linewidth=0.9, label="Active")
    ax_psd.plot(f_plot, idle_db_plot, linewidth=0.8, label="Idle")
    for fraction, value in percentile_frequencies.items():
        ax_psd.axvline(value, linewidth=0.7, linestyle="--")
    ax_psd.set_xscale("log")
    ax_psd.set_xlabel("Frequency (Hz)")
    ax_psd.set_ylabel(r"PSD ($\mathrm{dB\;W^2/Hz}$)")
    ax_psd.grid(True, which="both", alpha=0.3)
    ax_psd.legend(fontsize=7)
    ax_psd.set_title("(a) Active vs. idle")

    ax_cum.plot(cumulative_f_plot, cumulative_med_plot, linewidth=1.0)
    for fraction, value in percentile_frequencies.items():
        ax_cum.axhline(fraction, linewidth=0.65, linestyle="--")
        ax_cum.axvline(
            value,
            linewidth=0.7,
            linestyle=":",
            label=f"f{int(fraction * 100)}={value / 1000:.1f} kHz",
        )
    ax_cum.set_xscale("log")
    ax_cum.set_xlim(max(frequencies[1], 1.0), frequencies[-1])
    ax_cum.set_ylim(0.0, 1.01)
    ax_cum.set_xlabel("Frequency (Hz)")
    ax_cum.set_ylabel("Cumulative variance fraction")
    ax_cum.grid(True, which="both", alpha=0.3)
    ax_cum.legend(fontsize=7)
    ax_cum.set_title("(b) Cumulative excess PSD")
    fig.suptitle(f"Jetson GEMM-FP16 spectral analysis ({_run_label(n_runs)})")
    combined_base = cfg.output_root / "figures" / "psd_and_cumulative"
    _save_figure(fig, combined_base)

    variance_rows = read_csv(
        cfg.output_root / "psd" / "variance_capture_summary.csv"
    )
    variance_rows.sort(key=lambda row: int(row["target_rate_sps"]))
    rates = np.asarray(
        [int(row["target_rate_sps"]) for row in variance_rows], dtype=np.float64
    )
    median_percent = np.asarray(
        [float(row["percent_median"]) for row in variance_rows], dtype=np.float64
    )
    q05_percent = np.asarray(
        [float(row["percent_q05"]) for row in variance_rows], dtype=np.float64
    )
    q95_percent = np.asarray(
        [float(row["percent_q95"]) for row in variance_rows], dtype=np.float64
    )

    fig = plt.figure(figsize=(8.3, 4.8))
    ax = fig.add_subplot(1, 1, 1)
    if n_runs > 1:
        ax.fill_between(
            rates, q05_percent, q95_percent, alpha=0.20,
            label="5th–95th percentile across runs",
        )
    ax.plot(
        rates, median_percent, marker="o", markersize=3.5, linewidth=1.1,
        label="Median variance below Nyquist",
    )
    for threshold in cfg.psd.variance_capture_thresholds:
        ax.axhline(
            100.0 * threshold, linewidth=0.75, linestyle="--",
            label=f"{100.0 * threshold:g}% criterion",
        )
    highlight_set = set(cfg.psd.highlighted_rates_sps)
    highlighted = np.asarray([int(rate) in highlight_set for rate in rates])
    if np.any(highlighted):
        ax.scatter(
            rates[highlighted], median_percent[highlighted], marker="s", s=35,
            label="Selected paper rates", zorder=3,
        )
    ax.set_xscale("log")
    ax.set_ylim(0.0, 101.0)
    ax.set_xlabel("Sampling rate (S/s)")
    ax.set_ylabel("Workload-related variance below Nyquist (%)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7.5, loc="best")
    ax.set_title(
        f"Temporal variance captured by each sampling rate ({_run_label(n_runs)})"
    )
    variance_base = (
        cfg.output_root / "figures" / "variance_capture_by_sampling_rate"
    )
    _save_figure(fig, variance_base)

    return full_base, low_base, cumulative_base, combined_base, variance_base

