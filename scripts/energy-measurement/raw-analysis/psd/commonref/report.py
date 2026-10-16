from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .config import AnalysisConfig
from . import __version__
from .utils import human_rate, package_versions, read_csv, read_json, utc_now_iso, write_json


def write_manifest(cfg: AnalysisConfig, runs: Sequence[int], config_path: Path) -> Path:
    manifest = {
        "created_utc": utc_now_iso(),
        "tool_version": __version__,
        "config_path": str(config_path.resolve()),
        "dataset_root": str(cfg.dataset_root),
        "output_root": str(cfg.output_root),
        "primary_runs": list(runs),
        "reference_rate_sps": cfg.reference_rate_sps,
        "target_rates_sps": list(cfg.target_rates_sps),
        "cache_rates_sps": list(cfg.cache_rates_sps),
        "common_trace": cfg.common_trace,
        "psd": cfg.psd,
        "duration_sensitivity": cfg.duration_sensitivity,
        "package_versions": package_versions(),
        "methodological_scope": (
            "Archived oscilloscope.npy files contain calibrated power values. "
            "The tool therefore characterises sampling requirements of the derived power signal, "
            "not the complete separate voltage/current acquisition chain."
        ),
        "analogue_bandwidth_hz": cfg.analogue_bandwidth_hz,
        "psd_bandwidth_sensitivity_scope": (
            "The primary PSD is evaluated at the configured analysis rate and repeated at "
            "each configured sensitivity rate on identical active and idle intervals. "
            "f95/f99 and selected variance-capture values are compared before the full run."
        ),
        "high_rate_extension_scope": (
            "Nominal common-trace rates above the configured extension source are bandwidth-saturated "
            "anchors. The configured extension source has a Nyquist frequency above the "
            "configured analogue bandwidth, so those points add no measured analogue bandwidth "
            "and are not independent high-rate phase sweeps."
        ),
    }
    path = cfg.output_root / "analysis_manifest.json"
    write_json(path, manifest)
    return path


def _metric_lookup(rows: list[dict[str, str]], key: str) -> dict[str, str] | None:
    return next((row for row in rows if row["metric"] == key), None)


def write_summary(cfg: AnalysisConfig, runs: Sequence[int]) -> Path:
    fmin = read_csv(cfg.output_root / "common_trace" / "f_min.csv")
    psd_metrics = read_csv(cfg.output_root / "psd" / "psd_metrics_summary.csv")
    variance = read_csv(cfg.output_root / "psd" / "variance_capture_summary.csv")
    variance_thresholds = read_csv(
        cfg.output_root / "psd" / "variance_capture_thresholds.csv"
    )
    bands = read_csv(cfg.output_root / "psd" / "variance_bands_summary.csv")
    psd_sensitivity_path = (
        cfg.output_root / "psd" / "psd_bandwidth_sensitivity_summary.csv"
    )
    psd_sensitivity = (
        read_csv(psd_sensitivity_path) if psd_sensitivity_path.is_file() else []
    )
    phase_sensitivity_path = (
        cfg.output_root
        / "common_trace"
        / "phase_only_source_sensitivity"
        / "phase_only_source_sensitivity_comparison.csv"
    )
    phase_sensitivity = (
        read_csv(phase_sensitivity_path) if phase_sensitivity_path.is_file() else []
    )
    duration_root = cfg.output_root / "rate_duration"
    duration_summary_path = duration_root / "same_trace_summary.csv"
    duration_fmin_path = duration_root / "f_min_by_duration.csv"
    duration_recommendation_path = duration_root / "highlighted_rate_duration_decision.json"
    duration_summary = (
        read_csv(duration_summary_path) if duration_summary_path.is_file() else []
    )
    duration_fmin = read_csv(duration_fmin_path) if duration_fmin_path.is_file() else []
    duration_recommendation = (
        read_json(duration_recommendation_path)
        if duration_recommendation_path.is_file()
        else {}
    )

    lines = [
        "# Common-reference-trace and PSD analysis summary",
        "",
        f"- Tool version: {__version__}",
        f"- Dataset: `{cfg.dataset_root}`",
        f"- Primary run IDs: {', '.join(str(v) for v in runs)} (n={len(runs)})",
        f"- Reference rate: {cfg.reference_rate_sps} S/s",
        "- Archived input: calibrated power traces (`oscilloscope.npy`)",
        f"- Band-limited resampling quality: {cfg.resampling_quality}",
        f"- Primary PSD rate: {human_rate(cfg.psd.analysis_rate_sps)}",
        f"- PSD sensitivity rates: {', '.join(human_rate(v) for v in cfg.psd.sensitivity_rates_sps) or 'none'}",
        "- Reconstruction modes: anti-aliased best case and phase-only sampling without a target-rate anti-alias filter",
        "",
        "## Run-level energy thresholds",
        "",
    ]
    for mode in sorted({row["reconstruction_mode"] for row in fmin}):
        lines.append(f"### `{mode}`")
        lines.append("")
        for row in fmin:
            if row["reconstruction_mode"] != mode:
                continue
            lines.append(
                f"- ±{float(row['error_limit_pct']):g}%: {row['display']} "
                f"(`{row['status']}`)"
            )
        lines.append("")

    lines.extend(
        [
            "The `<=` relation means that the lowest evaluated rate already passed. It is an upper "
            "bound on the unknown threshold, not evidence that the threshold equals that rate.",
            "",
            "## PSD metrics",
            "",
        ]
    )
    for fraction in cfg.psd.cumulative_percentiles:
        label = int(round(fraction * 100))
        f_row = _metric_lookup(psd_metrics, f"f{label}_hz")
        fs_row = _metric_lookup(psd_metrics, f"nyquist_sample_rate_for_f{label}_sps")
        if f_row is None or fs_row is None:
            continue
        lines.append(
            f"- f{label}: median {float(f_row['median']) / 1000:.3f} kHz "
            f"(5th–95th percentile {float(f_row['q05']) / 1000:.3f}–"
            f"{float(f_row['q95']) / 1000:.3f} kHz); corresponding Nyquist rate "
            f"≈ {human_rate(float(fs_row['median']))}."
        )

    highlighted = set(cfg.psd.highlighted_rates_sps)
    lines.extend(["", "## Workload-related variance below Nyquist", ""])
    for row in variance:
        rate = int(row["target_rate_sps"])
        if rate not in highlighted:
            continue
        lines.append(
            f"- {human_rate(rate)}: median {float(row['percent_median']):.2f}% "
            f"(5th–95th percentile {float(row['percent_q05']):.2f}–"
            f"{float(row['percent_q95']):.2f}%)."
        )

    lines.extend(["", "## Conservative tested variance-capture rates", ""])
    for row in variance_thresholds:
        lines.append(
            f"- {float(row['variance_percent']):g}% variance: {row['display']} "
            f"(`{row['status']}`; criterion uses the 5th percentile across runs)."
        )

    lines.extend(["", "## Workload-related variance by frequency band", ""])
    for row in bands:
        lines.append(
            f"- {row['band']}: median {float(row['percent_median']):.2f}% "
            f"(5th–95th percentile {float(row['percent_q05']):.2f}–"
            f"{float(row['percent_q95']):.2f}%)."
        )

    if psd_sensitivity:
        lines.extend(["", "## PSD bandwidth sensitivity", ""])
        for row in psd_sensitivity:
            lines.append(
                f"- {human_rate(float(row['primary_analysis_rate_sps']))} vs. "
                f"{human_rate(float(row['sensitivity_analysis_rate_sps']))}: "
                f"overall pass = `{row['overall_pass']}` under the configured "
                "f95/f99 and variance-fraction tolerances."
            )
            for fraction in cfg.psd.cumulative_percentiles:
                label = int(round(fraction * 100))
                key = f"abs_f{label}_hz_relative_delta_q95"
                if key in row:
                    lines.append(
                        f"  - |Δf{label}|/f{label}, q95: "
                        f"{100.0 * float(row[key]):.3f}%"
                    )
            for target_rate in cfg.psd.sensitivity_check_rates_sps:
                key = f"abs_variance_at_{target_rate}_sps_delta_q95"
                if key in row:
                    lines.append(
                        f"  - variance fraction at {human_rate(target_rate)}, "
                        f"q95 absolute delta: {100.0 * float(row[key]):.3f} percentage points"
                    )

    if phase_sensitivity:
        lines.extend(["", "## Phase-only source-bandwidth sensitivity", ""])
        for row in phase_sensitivity:
            lines.append(
                f"- Target {human_rate(float(row['target_rate_sps']))}: "
                f"signed difference of q95 absolute errors between "
                f"{human_rate(float(row['primary_source_rate_sps']))} and "
                f"{human_rate(float(row['sensitivity_source_rate_sps']))} sources = "
                f"{float(row['abs_error_q95_delta_percentage_points']):+.6f} percentage points."
            )

    if duration_summary:
        highlighted = int(duration_recommendation.get("highlighted_rate_sps", 2000))
        lines.extend(
            [
                "",
                "## Duration-dependent energy-sampling requirement",
                "",
                (
                    "This stage uses exact sub-windows from stationary GEMM-FP16 "
                    "recordings. It isolates sampling and sampling-grid offset; it "
                    "does not include benchmark start/stop, automatic boundary, "
                    "timeout, or fixed-overhead effects."
                ),
                "",
            ]
        )
        highlighted_rows = sorted(
            [
                row
                for row in duration_summary
                if row["reconstruction_mode"] == "phase_only"
                and int(float(row["target_rate_sps"])) == highlighted
            ],
            key=lambda row: float(row["window_duration_s"]),
        )
        for row in highlighted_rows:
            lines.append(
                f"- {human_rate(highlighted)}, {float(row['window_duration_s']):g}-s exact window: "
                f"median run-q95 {float(row['per_run_abs_error_q95_median_pct']):.5g}%, "
                f"hierarchical q95 {float(row['per_run_abs_error_q95_q95_pct']):.5g}%, "
                f"worst observed {float(row['abs_error_max_pct']):.5g}%."
            )
        if duration_fmin:
            lines.extend(["", "Minimum tested rate bounds (unfiltered grid-offset mode):", ""])
            for row in duration_fmin:
                if row["reconstruction_mode"] != "phase_only":
                    continue
                if float(row["window_duration_s"]) not in {0.1, 1.0, 5.0, 10.0, 100.0, 104.0}:
                    continue
                lines.append(
                    f"- {float(row['window_duration_s']):g} s, "
                    f"±{float(row['error_limit_pct']):g}%: {row['display']}."
                )
        lines.extend(
            [
                "",
                (
                    "Protocol context is separate: in the independent 5-600-s "
                    "campaign the corrected u.RECS path stayed within about "
                    "±0.5% of the PicoScope setup, while 50-200 s were required "
                    "for the detected mean power to come within 3% of the 600-s "
                    "result depending on workload."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Method interpretation",
            "",
            (
                "The anti-aliased reconstruction is a controlled best case: lower-rate power "
                f"traces are derived from the same calibrated {human_rate(cfg.reference_rate_sps)} "
                "recording while preserving the fixed benchmark interval. The phase-only "
                f"reconstruction retains the {human_rate(cfg.common_trace.phase_only_source_rate_sps)} "
                "source but does not add a target-rate anti-alias filter, making alias and "
                "relative-phase effects visible."
            ),
            "",
            (
                f"Nominal points above {human_rate(cfg.common_trace.high_rate_extension.source_rate_sps)} "
                "are shown as bandwidth-saturated anchors. The extension source has a Nyquist "
                f"frequency of {cfg.common_trace.high_rate_extension.source_rate_sps / 2000:.1f} kHz, "
                f"above the configured {cfg.analogue_bandwidth_hz / 1000:.1f}-kHz analogue bandwidth. "
                "These anchors are useful for comparing the common trace with the independent real "
                "sweep, but they are not additional high-rate phase sweeps."
            ),
            "",
            (
                "Because the archived traces contain calibrated power rather than separate voltage "
                "and current channels, the analysis characterises the sampling requirements of the "
                "derived power signal rather than reproducing the complete two-channel acquisition chain."
            ),
            "",
            "## Main generated files",
            "",
            "- `common_trace/common_trace_summary.csv`",
            "- `common_trace/anti_aliased_summary.csv`",
            "- `common_trace/phase_only_summary.csv`",
            "- `common_trace/f_min.csv`",
            "- `real_measurements/real_measurements_summary.csv`",
            "- `psd/psd_metrics_summary.csv`",
            "- `psd/variance_capture_summary.csv`",
            "- `psd/variance_capture_thresholds.csv`",
            "- `psd/variance_bands_summary.csv`",
            "- `psd/dominant_peaks.csv`",
            "- `psd/psd_bandwidth_sensitivity_summary.csv`",
            "- `psd/psd_bandwidth_sensitivity_decision.json`",
            "- `common_trace/phase_only_source_sensitivity/`",
            "- `rate_duration/same_trace_summary.csv`",
            "- `rate_duration/f_min_by_duration.csv`",
            "- `rate_duration/highlighted_rate_duration_decision.json`",
            "- `rate_duration/duration_campaign/reference_convergence_thresholds.csv`",
            "- `validation/real_measurement_run_selection.csv`",
            "- `figures/` (PNG and PDF, including variance-capture and PSD-sensitivity plots)",
            "",
        ]
    )
    path = cfg.output_root / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
