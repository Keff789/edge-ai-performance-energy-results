from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import load_yaml


@dataclass(frozen=True)
class DatasetDescriptor:
    dataset_id: str
    workload_label: str
    analysis_role: str
    signal_label: str


@dataclass(frozen=True)
class ExternalIdleConfig:
    """Optional independently recorded idle reference.

    The idle tree is read-only and follows the same rate-directory and paired
    file naming conventions as the workload tree.  It is never concatenated
    with workload records.  Same-run pre-benchmark idle remains the preferred
    PSD reference; the external reference is a documented fallback and a
    separate DC-baseline diagnostic.
    """

    enabled: bool
    dataset_root: Path | None
    matching_policy: str
    minimum_pairs: int
    use_for_psd_when_same_run_unavailable: bool
    use_for_baseline_diagnostics: bool
    use_for_incremental_energy: bool
    maximum_idle_current_difference_ma: float


@dataclass(frozen=True)
class ZeroOffsetCorrectionConfig:
    """Adaptive additive zero-offset detection and salvage correction.

    The current implementation deliberately supports only a *constant* offset.
    It does not fit or apply a gain correction.  Detection is based on the
    independently recorded, exact-rate paired idle data.  The resulting
    session-level correction may be propagated to workload rates for which no
    exact-rate idle record exists, provided the available reference rates show
    a stable, same-sign offset.

    Because the paired idle estimate uses the PicoScope as the relative
    reference, a corrected Tektronix result is a documented post-hoc salvage
    result rather than an independent absolute validation of the PicoScope.
    Raw metrics are always preserved alongside corrected metrics.
    """

    enabled: bool
    target_source: str
    detection_source: str
    application_scope: str
    apply_when_detected: bool
    minimum_reference_rates: int
    minimum_reference_pairs_total: int
    minimum_abs_offset_ma: float
    maximum_abs_correction_ma: float
    maximum_rate_median_deviation_ma: float
    maximum_rate_q95_span_ma: float
    minimum_sign_consistency_fraction: float
    preserve_raw_metrics: bool


@dataclass(frozen=True)
class SourceCalibration:
    file_pattern: str
    column: str
    raw_unit: str
    display_name: str
    offset_raw: float
    gain_a_per_raw: float

    def calibrate(self, values):
        return (values + self.offset_raw) * self.gain_a_per_raw


@dataclass(frozen=True)
class SourceRatePolicy:
    directory_rate_source: str
    tek_policy: str
    pico_policy: str
    pico_max_rate_sps: float
    duration_tolerance_s: float
    duration_tolerance_relative: float

    def rates_for_directory(self, directory_rate_sps: float) -> tuple[float, float]:
        if self.directory_rate_source != "tek":
            raise ValueError(
                f"Unsupported directory_rate_source: {self.directory_rate_source}"
            )
        if self.tek_policy != "directory_rate":
            raise ValueError(f"Unsupported Tek rate policy: {self.tek_policy}")
        tek_rate = float(directory_rate_sps)
        if self.pico_policy == "directory_rate":
            pico_rate = float(directory_rate_sps)
        elif self.pico_policy == "capped_directory_rate":
            pico_rate = min(float(directory_rate_sps), float(self.pico_max_rate_sps))
        else:
            raise ValueError(f"Unsupported Pico rate policy: {self.pico_policy}")
        return tek_rate, pico_rate


@dataclass(frozen=True)
class VoltageModel:
    model_type: str
    intercept_v: float
    slope_v_per_a: float
    constant_v: float
    valid_current_min_a: float | None
    valid_current_max_a: float | None
    calibration_id: str

    def voltage(self, current):
        if self.model_type == "constant":
            return current * 0.0 + self.constant_v
        if self.model_type == "linear_current":
            return self.intercept_v + self.slope_v_per_a * current
        raise ValueError(f"Unsupported voltage model: {self.model_type}")


@dataclass(frozen=True)
class AlignmentConfig:
    enabled: bool
    max_lag_ms: float
    analysis_rate_sps: int
    lowpass_hz: float
    drift_window_s: float
    apply_to_waveform_metrics: bool


@dataclass(frozen=True)
class WindowConfig:
    mode: str
    trigger_time_s: float | None
    shared_anchor_mode: str
    trigger_fraction: float | None
    trigger_time_by_rate_s: tuple[tuple[int, float], ...]
    detection_smoothing_ms: float
    threshold_fraction: float
    guard_after_trigger_s: float
    idle_gap_s: float
    idle_duration_s: float
    stop_margin_s: float
    minimum_active_duration_s: float
    step_detector_diagnostics: bool


@dataclass(frozen=True)
class SpectralConfig:
    enabled: bool
    max_analysis_rate_sps: int
    segment_duration_s: float
    max_nperseg: int
    overlap_fraction: float
    cumulative_percentiles: tuple[float, ...]
    variance_capture_rates_sps: tuple[int, ...]
    coherence_threshold: float
    psd_ratio_tolerance_db: float
    minimum_frequency_hz: float
    plot_max_points: int
    minimum_welch_segments: int
    minimum_idle_welch_segments: int
    primary_reference_source: str
    primary_reference_min_pairs: int
    primary_reference_min_active_duration_s: float
    primary_reference_min_idle_duration_s: float
    paired_validation_preferred_rate_sps: float


@dataclass(frozen=True)
class ValidationConfig:
    q95_abs_charge_error_pct: float
    q95_abs_energy_error_pct: float
    q95_abs_alignment_ms: float
    median_correlation_100ms: float
    minimum_pairs: int
    minimum_correlation_windows: int
    low_current_threshold_a: float


@dataclass(frozen=True)
class InputPolicyConfig:
    """Read-only scan policy for incrementally populated measurement trees."""

    ignore_empty_rate_directories: bool
    ignore_unpaired_runs: bool
    ignore_invalid_pairs: bool
    fail_if_no_valid_rates: bool
    minimum_rows_per_file: int
    require_equal_sample_counts: bool
    expected_duration_s: float | None
    duration_tolerance_samples: int


@dataclass(frozen=True)
class ScopeComparisonConfig:
    dataset_root: Path
    output_root: Path
    dataset: DatasetDescriptor
    external_idle: ExternalIdleConfig
    zero_offset_correction: ZeroOffsetCorrectionConfig
    rate_directories: str | tuple[str, ...]
    representative_run: int
    source_rates: SourceRatePolicy
    tek: SourceCalibration
    pico: SourceCalibration
    voltage_model: VoltageModel
    alignment: AlignmentConfig
    windows: WindowConfig
    spectral: SpectralConfig
    validation: ValidationConfig
    input_policy: InputPolicyConfig
    averaging_windows_ms: tuple[float, ...]


def _as_nonempty_tuple(value: Any, field: str, cast):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty YAML list")
    return tuple(cast(item) for item in value)


def _source(data: dict[str, Any], name: str) -> SourceCalibration:
    section = data.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"sources.{name} must be a mapping")
    calibration = section.get("calibration", {})
    if not isinstance(calibration, dict):
        raise ValueError(f"sources.{name}.calibration must be a mapping")
    pattern = str(section["file_pattern"])
    if pattern.count("{run}") != 1:
        raise ValueError(f"sources.{name}.file_pattern must contain exactly one {{run}} token")
    return SourceCalibration(
        file_pattern=pattern,
        column=str(section.get("column", "current")),
        raw_unit=str(section.get("raw_unit", "unknown")),
        display_name=str(section.get("display_name", name)),
        offset_raw=float(calibration.get("offset_raw", 0.0)),
        gain_a_per_raw=float(calibration.get("gain_a_per_raw", 1.0)),
    )


def _rate_time_map(value: Any) -> tuple[tuple[int, float], ...]:
    if value in (None, {}):
        return ()
    if not isinstance(value, dict):
        raise ValueError(
            "analysis_windows.trigger_time_by_rate_s must be a mapping"
        )
    rows: list[tuple[int, float]] = []
    for raw_rate, raw_time in value.items():
        rate_text = str(raw_rate)
        if rate_text.endswith("Sps"):
            rate_text = rate_text[:-3]
        rate = int(rate_text)
        time_s = float(raw_time)
        if rate <= 0 or time_s < 0:
            raise ValueError(
                "trigger_time_by_rate_s requires positive rates and "
                "non-negative times"
            )
        rows.append((rate, time_s))
    return tuple(sorted(rows))


def load_scope_config(path: Path, output_override: Path | None = None) -> ScopeComparisonConfig:
    data = load_yaml(path)
    source_data = data.get("sources")
    if not isinstance(source_data, dict):
        raise ValueError("sources must be a mapping")

    raw_rate_dirs = data.get("rate_directories", "auto")
    if isinstance(raw_rate_dirs, str):
        if raw_rate_dirs != "auto":
            rate_directories: str | tuple[str, ...] = (raw_rate_dirs,)
        else:
            rate_directories = "auto"
    elif isinstance(raw_rate_dirs, list) and raw_rate_dirs:
        rate_directories = tuple(str(item) for item in raw_rate_dirs)
    else:
        raise ValueError("rate_directories must be 'auto', a string, or a non-empty list")

    rate_policy_data = data.get("source_rates", {})
    if not isinstance(rate_policy_data, dict):
        raise ValueError("source_rates must be a mapping")

    voltage_data = data.get("voltage_model", {})
    if not isinstance(voltage_data, dict):
        raise ValueError("voltage_model must be a mapping")
    model_type = str(voltage_data.get("type", "linear_current"))
    if model_type not in {"constant", "linear_current"}:
        raise ValueError("voltage_model.type must be 'constant' or 'linear_current'")
    valid_range = voltage_data.get("valid_current_range_a")
    if valid_range is None:
        current_min = current_max = None
    else:
        if not isinstance(valid_range, list) or len(valid_range) != 2:
            raise ValueError("voltage_model.valid_current_range_a must contain [min, max]")
        current_min, current_max = float(valid_range[0]), float(valid_range[1])
        if current_max <= current_min:
            raise ValueError("voltage_model.valid_current_range_a max must exceed min")

    alignment_data = data.get("alignment", {})
    windows_data = data.get("analysis_windows", {})
    spectral_data = data.get("spectral", {})
    validation_data = data.get("validation", {})
    input_policy_data = data.get("input_policy", {})
    dataset_data = data.get("dataset", {})
    external_idle_data = data.get("external_idle", {})
    zero_offset_data = data.get("zero_offset_correction", {})
    for name, section in (
        ("alignment", alignment_data),
        ("analysis_windows", windows_data),
        ("spectral", spectral_data),
        ("validation", validation_data),
        ("input_policy", input_policy_data),
        ("dataset", dataset_data),
        ("external_idle", external_idle_data),
        ("zero_offset_correction", zero_offset_data),
    ):
        if not isinstance(section, dict):
            raise ValueError(f"{name} must be a mapping")

    trigger_time_raw = windows_data.get("trigger_time_s")
    trigger_time = None if trigger_time_raw in (None, "auto") else float(trigger_time_raw)
    shared_anchor_mode = str(
        windows_data.get("shared_anchor_mode", "first_valid_detection")
    )
    if shared_anchor_mode not in {
        "first_valid_detection",
        "fixed_time",
        "fixed_fraction",
        "per_rate_time",
    }:
        raise ValueError(
            "analysis_windows.shared_anchor_mode must be first_valid_detection, "
            "fixed_time, fixed_fraction, or per_rate_time"
        )
    trigger_fraction_raw = windows_data.get("trigger_fraction", "auto")
    trigger_fraction = (
        None
        if trigger_fraction_raw in (None, "auto")
        else float(trigger_fraction_raw)
    )
    trigger_time_by_rate = _rate_time_map(
        windows_data.get("trigger_time_by_rate_s", {})
    )
    if shared_anchor_mode == "fixed_time" and trigger_time is None:
        raise ValueError(
            "analysis_windows.trigger_time_s is required for fixed_time anchor"
        )
    if shared_anchor_mode == "fixed_fraction" and trigger_fraction is None:
        raise ValueError(
            "analysis_windows.trigger_fraction is required for fixed_fraction anchor"
        )
    if shared_anchor_mode == "per_rate_time" and not trigger_time_by_rate:
        raise ValueError(
            "analysis_windows.trigger_time_by_rate_s is required for per_rate_time"
        )
    window_mode = str(windows_data.get("mode", "after_main_rise"))
    if window_mode not in {"after_main_rise", "fixed_trigger", "full"}:
        raise ValueError("analysis_windows.mode must be after_main_rise, fixed_trigger, or full")
    if window_mode == "fixed_trigger" and trigger_time is None:
        raise ValueError("analysis_windows.trigger_time_s is required for fixed_trigger mode")

    expected_duration_raw = input_policy_data.get("expected_duration_s", "auto")
    expected_duration = (
        None
        if expected_duration_raw in (None, "auto")
        else float(expected_duration_raw)
    )

    dataset_root = Path(data["dataset_root"]).expanduser()
    inferred_id = dataset_root.name or "paired_scope_dataset"
    inferred_label = inferred_id.replace("_", "-")

    external_idle_enabled = bool(external_idle_data.get("enabled", False))
    external_idle_root_raw = external_idle_data.get("dataset_root")
    external_idle_root = (
        Path(external_idle_root_raw).expanduser()
        if external_idle_root_raw not in (None, "")
        else None
    )
    if external_idle_enabled and external_idle_root is None:
        raise ValueError(
            "external_idle.dataset_root is required when external_idle.enabled=true"
        )
    matching_policy = str(
        external_idle_data.get("matching_policy", "exact_directory_rate")
    )
    if matching_policy not in {"exact_directory_rate"}:
        raise ValueError(
            "external_idle.matching_policy currently supports only "
            "'exact_directory_rate'"
        )

    cfg = ScopeComparisonConfig(
        dataset_root=dataset_root,
        output_root=(output_override or Path(data["output_root"]).expanduser()),
        dataset=DatasetDescriptor(
            dataset_id=str(dataset_data.get("id", inferred_id)),
            workload_label=str(dataset_data.get("workload_label", inferred_label)),
            analysis_role=str(
                dataset_data.get("analysis_role", "paired_scope_validation")
            ),
            signal_label=str(
                dataset_data.get(
                    "signal_label",
                    "estimated power derived from calibrated current",
                )
            ),
        ),
        external_idle=ExternalIdleConfig(
            enabled=external_idle_enabled,
            dataset_root=external_idle_root,
            matching_policy=matching_policy,
            minimum_pairs=int(external_idle_data.get("minimum_pairs", 5)),
            use_for_psd_when_same_run_unavailable=bool(
                external_idle_data.get(
                    "use_for_psd_when_same_run_unavailable", True
                )
            ),
            use_for_baseline_diagnostics=bool(
                external_idle_data.get("use_for_baseline_diagnostics", True)
            ),
            use_for_incremental_energy=bool(
                external_idle_data.get("use_for_incremental_energy", True)
            ),
            maximum_idle_current_difference_ma=float(
                external_idle_data.get(
                    "maximum_idle_current_difference_ma", 50.0
                )
            ),
        ),
        zero_offset_correction=ZeroOffsetCorrectionConfig(
            enabled=bool(zero_offset_data.get("enabled", False)),
            target_source=str(zero_offset_data.get("target_source", "tek")),
            detection_source=str(
                zero_offset_data.get(
                    "detection_source", "external_idle_rate_medians"
                )
            ),
            application_scope=str(
                zero_offset_data.get("application_scope", "all_workload_rates")
            ),
            apply_when_detected=bool(
                zero_offset_data.get("apply_when_detected", True)
            ),
            minimum_reference_rates=int(
                zero_offset_data.get("minimum_reference_rates", 2)
            ),
            minimum_reference_pairs_total=int(
                zero_offset_data.get("minimum_reference_pairs_total", 10)
            ),
            minimum_abs_offset_ma=float(
                zero_offset_data.get("minimum_abs_offset_ma", 50.0)
            ),
            maximum_abs_correction_ma=float(
                zero_offset_data.get("maximum_abs_correction_ma", 500.0)
            ),
            maximum_rate_median_deviation_ma=float(
                zero_offset_data.get(
                    "maximum_rate_median_deviation_ma", 15.0
                )
            ),
            maximum_rate_q95_span_ma=float(
                zero_offset_data.get("maximum_rate_q95_span_ma", 30.0)
            ),
            minimum_sign_consistency_fraction=float(
                zero_offset_data.get(
                    "minimum_sign_consistency_fraction", 1.0
                )
            ),
            preserve_raw_metrics=bool(
                zero_offset_data.get("preserve_raw_metrics", True)
            ),
        ),
        rate_directories=rate_directories,
        representative_run=int(data.get("representative_run", 0)),
        source_rates=SourceRatePolicy(
            directory_rate_source=str(
                rate_policy_data.get("directory_rate_source", "tek")
            ),
            tek_policy=str(rate_policy_data.get("tek_policy", "directory_rate")),
            pico_policy=str(
                rate_policy_data.get("pico_policy", "capped_directory_rate")
            ),
            pico_max_rate_sps=float(
                rate_policy_data.get("pico_max_rate_sps", 5_000_000)
            ),
            duration_tolerance_s=float(
                rate_policy_data.get("duration_tolerance_s", 2e-6)
            ),
            duration_tolerance_relative=float(
                rate_policy_data.get("duration_tolerance_relative", 1e-5)
            ),
        ),
        tek=_source(source_data, "tek"),
        pico=_source(source_data, "pico"),
        voltage_model=VoltageModel(
            model_type=model_type,
            intercept_v=float(voltage_data.get("intercept_v", 0.0)),
            slope_v_per_a=float(voltage_data.get("slope_v_per_a", 0.0)),
            constant_v=float(voltage_data.get("value_v", 19.0)),
            valid_current_min_a=current_min,
            valid_current_max_a=current_max,
            calibration_id=str(voltage_data.get("calibration_id", "unspecified")),
        ),
        alignment=AlignmentConfig(
            enabled=bool(alignment_data.get("enabled", True)),
            max_lag_ms=float(alignment_data.get("max_lag_ms", 10.0)),
            analysis_rate_sps=int(alignment_data.get("analysis_rate_sps", 20_000)),
            lowpass_hz=float(alignment_data.get("lowpass_hz", 500.0)),
            drift_window_s=float(alignment_data.get("drift_window_s", 2.0)),
            apply_to_waveform_metrics=bool(
                alignment_data.get("apply_to_waveform_metrics", True)
            ),
        ),
        windows=WindowConfig(
            mode=window_mode,
            trigger_time_s=trigger_time,
            shared_anchor_mode=shared_anchor_mode,
            trigger_fraction=trigger_fraction,
            trigger_time_by_rate_s=trigger_time_by_rate,
            detection_smoothing_ms=float(
                windows_data.get("detection_smoothing_ms", 20.0)
            ),
            threshold_fraction=float(windows_data.get("threshold_fraction", 0.30)),
            guard_after_trigger_s=float(windows_data.get("guard_after_trigger_s", 0.50)),
            idle_gap_s=float(windows_data.get("idle_gap_s", 0.10)),
            idle_duration_s=float(windows_data.get("idle_duration_s", 1.0)),
            stop_margin_s=float(windows_data.get("stop_margin_s", 0.20)),
            minimum_active_duration_s=float(
                windows_data.get("minimum_active_duration_s", 2.0)
            ),
            step_detector_diagnostics=bool(
                windows_data.get("step_detector_diagnostics", True)
            ),
        ),
        spectral=SpectralConfig(
            enabled=bool(spectral_data.get("enabled", True)),
            max_analysis_rate_sps=int(
                spectral_data.get("max_analysis_rate_sps", 5_000_000)
            ),
            segment_duration_s=float(spectral_data.get("segment_duration_s", 1.0)),
            max_nperseg=int(spectral_data.get("max_nperseg", 1_048_576)),
            overlap_fraction=float(spectral_data.get("overlap_fraction", 0.5)),
            cumulative_percentiles=_as_nonempty_tuple(
                spectral_data.get("cumulative_percentiles", [0.95, 0.99]),
                "spectral.cumulative_percentiles",
                float,
            ),
            variance_capture_rates_sps=_as_nonempty_tuple(
                spectral_data.get("variance_capture_rates_sps", [2_000, 125_000, 160_000]),
                "spectral.variance_capture_rates_sps",
                int,
            ),
            coherence_threshold=float(spectral_data.get("coherence_threshold", 0.80)),
            psd_ratio_tolerance_db=float(
                spectral_data.get("psd_ratio_tolerance_db", 3.0)
            ),
            minimum_frequency_hz=float(spectral_data.get("minimum_frequency_hz", 1.0)),
            plot_max_points=int(spectral_data.get("plot_max_points", 60_000)),
            minimum_welch_segments=int(
                spectral_data.get("minimum_welch_segments", 8)
            ),
            minimum_idle_welch_segments=int(
                spectral_data.get("minimum_idle_welch_segments", 2)
            ),
            primary_reference_source=str(
                spectral_data.get("primary_reference_source", "tek")
            ),
            primary_reference_min_pairs=int(
                spectral_data.get("primary_reference_min_pairs", 5)
            ),
            primary_reference_min_active_duration_s=float(
                spectral_data.get("primary_reference_min_active_duration_s", 2.0)
            ),
            primary_reference_min_idle_duration_s=float(
                spectral_data.get("primary_reference_min_idle_duration_s", 0.5)
            ),
            paired_validation_preferred_rate_sps=float(
                spectral_data.get("paired_validation_preferred_rate_sps", 5_000_000)
            ),
        ),
        validation=ValidationConfig(
            q95_abs_charge_error_pct=float(
                validation_data.get("q95_abs_charge_error_pct", 1.0)
            ),
            q95_abs_energy_error_pct=float(
                validation_data.get("q95_abs_energy_error_pct", 1.0)
            ),
            q95_abs_alignment_ms=float(
                validation_data.get("q95_abs_alignment_ms", 1.0)
            ),
            median_correlation_100ms=float(
                validation_data.get("median_correlation_100ms", 0.99)
            ),
            minimum_pairs=int(validation_data.get("minimum_pairs", 5)),
            minimum_correlation_windows=int(
                validation_data.get("minimum_correlation_windows", 8)
            ),
            low_current_threshold_a=float(
                validation_data.get("low_current_threshold_a", 0.75)
            ),
        ),
        input_policy=InputPolicyConfig(
            ignore_empty_rate_directories=bool(
                input_policy_data.get("ignore_empty_rate_directories", True)
            ),
            ignore_unpaired_runs=bool(
                input_policy_data.get("ignore_unpaired_runs", True)
            ),
            ignore_invalid_pairs=bool(
                input_policy_data.get("ignore_invalid_pairs", True)
            ),
            fail_if_no_valid_rates=bool(
                input_policy_data.get("fail_if_no_valid_rates", True)
            ),
            minimum_rows_per_file=int(
                input_policy_data.get("minimum_rows_per_file", 2)
            ),
            require_equal_sample_counts=bool(
                input_policy_data.get("require_equal_sample_counts", False)
            ),
            expected_duration_s=expected_duration,
            duration_tolerance_samples=int(
                input_policy_data.get("duration_tolerance_samples", 2)
            ),
        ),
        averaging_windows_ms=_as_nonempty_tuple(
            data.get("averaging_windows_ms", [10.0, 50.0, 100.0]),
            "averaging_windows_ms",
            float,
        ),
    )

    if not (0.0 < cfg.spectral.overlap_fraction < 1.0):
        raise ValueError("spectral.overlap_fraction must be between 0 and 1")
    if not (0.0 < cfg.windows.threshold_fraction < 1.0):
        raise ValueError("analysis_windows.threshold_fraction must be between 0 and 1")
    if cfg.windows.trigger_fraction is not None and not (
        0.0 <= cfg.windows.trigger_fraction <= 1.0
    ):
        raise ValueError(
            "analysis_windows.trigger_fraction must be between 0 and 1"
        )
    if cfg.alignment.analysis_rate_sps <= 0:
        raise ValueError("alignment.analysis_rate_sps must be positive")
    if cfg.input_policy.minimum_rows_per_file < 2:
        raise ValueError("input_policy.minimum_rows_per_file must be at least 2")
    if cfg.input_policy.expected_duration_s is not None and cfg.input_policy.expected_duration_s <= 0:
        raise ValueError("input_policy.expected_duration_s must be positive or 'auto'")
    if cfg.input_policy.duration_tolerance_samples < 0:
        raise ValueError("input_policy.duration_tolerance_samples must be non-negative")
    if cfg.source_rates.directory_rate_source != "tek":
        raise ValueError("source_rates.directory_rate_source must be 'tek'")
    if cfg.source_rates.tek_policy != "directory_rate":
        raise ValueError("source_rates.tek_policy must be 'directory_rate'")
    if cfg.external_idle.minimum_pairs < 1:
        raise ValueError("external_idle.minimum_pairs must be at least 1")
    if cfg.external_idle.maximum_idle_current_difference_ma < 0:
        raise ValueError(
            "external_idle.maximum_idle_current_difference_ma must be non-negative"
        )
    if cfg.zero_offset_correction.target_source != "tek":
        raise ValueError(
            "zero_offset_correction.target_source currently supports only 'tek'"
        )
    if cfg.zero_offset_correction.detection_source not in {
        "external_idle_rate_medians",
        "workload_minus_external_idle_rate_medians",
    }:
        raise ValueError(
            "zero_offset_correction.detection_source must be "
            "'external_idle_rate_medians' or "
            "'workload_minus_external_idle_rate_medians'"
        )
    if cfg.zero_offset_correction.application_scope not in {
        "all_workload_rates",
        "workload_only",
    }:
        raise ValueError(
            "zero_offset_correction.application_scope must be "
            "'all_workload_rates' or 'workload_only'"
        )
    if cfg.zero_offset_correction.minimum_reference_rates < 1:
        raise ValueError(
            "zero_offset_correction.minimum_reference_rates must be at least 1"
        )
    if cfg.zero_offset_correction.minimum_reference_pairs_total < 1:
        raise ValueError(
            "zero_offset_correction.minimum_reference_pairs_total must be at least 1"
        )
    if cfg.zero_offset_correction.minimum_abs_offset_ma < 0:
        raise ValueError(
            "zero_offset_correction.minimum_abs_offset_ma must be non-negative"
        )
    if cfg.zero_offset_correction.maximum_abs_correction_ma <= 0:
        raise ValueError(
            "zero_offset_correction.maximum_abs_correction_ma must be positive"
        )
    if (
        cfg.zero_offset_correction.maximum_abs_correction_ma
        < cfg.zero_offset_correction.minimum_abs_offset_ma
    ):
        raise ValueError(
            "zero_offset_correction.maximum_abs_correction_ma must be at least "
            "minimum_abs_offset_ma"
        )
    if cfg.zero_offset_correction.maximum_rate_median_deviation_ma < 0:
        raise ValueError(
            "zero_offset_correction.maximum_rate_median_deviation_ma must be "
            "non-negative"
        )
    if cfg.zero_offset_correction.maximum_rate_q95_span_ma < 0:
        raise ValueError(
            "zero_offset_correction.maximum_rate_q95_span_ma must be non-negative"
        )
    if not cfg.zero_offset_correction.preserve_raw_metrics:
        raise ValueError(
            "zero_offset_correction.preserve_raw_metrics must remain true; "
            "adaptive salvage may never overwrite the measured raw values"
        )
    if not (
        0.5
        <= cfg.zero_offset_correction.minimum_sign_consistency_fraction
        <= 1.0
    ):
        raise ValueError(
            "zero_offset_correction.minimum_sign_consistency_fraction must be "
            "between 0.5 and 1.0"
        )
    if cfg.source_rates.pico_policy not in {"directory_rate", "capped_directory_rate"}:
        raise ValueError(
            "source_rates.pico_policy must be directory_rate or capped_directory_rate"
        )
    if cfg.source_rates.pico_max_rate_sps <= 0:
        raise ValueError("source_rates.pico_max_rate_sps must be positive")
    if cfg.source_rates.duration_tolerance_s < 0:
        raise ValueError("source_rates.duration_tolerance_s must be non-negative")
    if cfg.source_rates.duration_tolerance_relative < 0:
        raise ValueError(
            "source_rates.duration_tolerance_relative must be non-negative"
        )
    if cfg.spectral.minimum_welch_segments < 2:
        raise ValueError("spectral.minimum_welch_segments must be at least 2")
    if cfg.spectral.minimum_idle_welch_segments < 1:
        raise ValueError("spectral.minimum_idle_welch_segments must be at least 1")
    if cfg.spectral.primary_reference_source != "tek":
        raise ValueError("spectral.primary_reference_source must be 'tek'")
    if cfg.spectral.primary_reference_min_pairs < 1:
        raise ValueError("spectral.primary_reference_min_pairs must be positive")
    if cfg.spectral.primary_reference_min_active_duration_s <= 0:
        raise ValueError(
            "spectral.primary_reference_min_active_duration_s must be positive"
        )
    if cfg.spectral.primary_reference_min_idle_duration_s < 0:
        raise ValueError(
            "spectral.primary_reference_min_idle_duration_s must be non-negative"
        )
    if cfg.spectral.paired_validation_preferred_rate_sps <= 0:
        raise ValueError(
            "spectral.paired_validation_preferred_rate_sps must be positive"
        )
    if cfg.validation.minimum_correlation_windows < 3:
        raise ValueError("validation.minimum_correlation_windows must be at least 3")
    if cfg.validation.low_current_threshold_a <= 0:
        raise ValueError("validation.low_current_threshold_a must be positive")
    return cfg
