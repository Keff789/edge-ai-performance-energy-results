from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import load_yaml


@dataclass(frozen=True)
class AntiAliasConfig:
    attenuation_db: float
    passband_fraction_of_nyquist: float
    stopband_fraction_of_nyquist: float


@dataclass(frozen=True)
class HighRateExtensionConfig:
    enabled: bool
    source_rate_sps: int


@dataclass(frozen=True)
class CommonTraceConfig:
    reconstruction_modes: tuple[str, ...]
    phase_only_source_rate_sps: int
    phase_only_sensitivity_source_rates_sps: tuple[int, ...]
    phase_only_sensitivity_target_rates_sps: tuple[int, ...]
    fmin_thresholds_pct: tuple[float, ...]
    high_rate_extension: HighRateExtensionConfig


@dataclass(frozen=True)
class FrequencyBand:
    label: str
    low_hz: float
    high_hz: float | None


@dataclass(frozen=True)
class PSDConfig:
    analysis_rate_sps: int
    sensitivity_rates_sps: tuple[int, ...]
    sensitivity_check_rates_sps: tuple[int, ...]
    sensitivity_relative_frequency_tolerance: float
    sensitivity_variance_fraction_tolerance: float
    plot_max_points: int
    active_duration_s: float
    idle_duration_s: float
    idle_gap_s: float
    segment_duration_s: float
    overlap_fraction: float
    cumulative_percentiles: tuple[float, ...]
    peak_max_frequency_hz: float
    peak_count: int
    variance_capture_rates_sps: tuple[int, ...]
    variance_capture_thresholds: tuple[float, ...]
    highlighted_rates_sps: tuple[int, ...]
    low_frequency_nyquist_rates_sps: tuple[int, ...]
    full_frequency_nyquist_rates_sps: tuple[int, ...]
    variance_bands: tuple[FrequencyBand, ...]


@dataclass(frozen=True)
class DurationCampaignConfig:
    enabled: bool
    root: Path
    expected_durations_s: tuple[float, ...]
    reference_duration_s: float
    steady_state_tolerance_pct: float
    urecs_correction_factor: float
    urecs_values_already_include_correction_factor: bool
    minimum_runs_per_cell: int
    use_thesis_fallback: bool
    fallback_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DurationSensitivityConfig:
    enabled: bool
    source_rate_sps: int
    target_rates_sps: tuple[int, ...]
    window_durations_s: tuple[float, ...]
    windows_per_duration: int
    edge_margin_s: float
    reconstruction_modes: tuple[str, ...]
    thresholds_pct: tuple[float, ...]
    highlighted_rate_sps: int
    minimum_samples_per_window: int
    campaign: DurationCampaignConfig


@dataclass(frozen=True)
class TimeTraceConfig:
    run: str | int
    active_center_offset_s: float
    window_duration_s: float
    rates_sps: tuple[int, ...]
    max_display_points: int


@dataclass(frozen=True)
class AnalysisConfig:
    dataset_root: Path
    output_root: Path
    reference_rate_sps: int
    reference_rate_directory: str
    analogue_bandwidth_hz: float
    primary_runs: tuple[int, ...]
    sensitivity_runs: tuple[int, ...]
    cache_rates_sps: tuple[int, ...]
    target_rates_sps: tuple[int, ...]
    resampling_quality: str
    chunk_seconds: float
    cache_dtype: str
    guard_seconds: float
    phase_plan: tuple[tuple[int | None, int], ...]
    anti_alias: AntiAliasConfig
    common_trace: CommonTraceConfig
    psd: PSDConfig
    duration_sensitivity: DurationSensitivityConfig
    time_trace: TimeTraceConfig

    def phase_count(self, target_rate: int) -> int:
        for max_rate, phases in self.phase_plan:
            if max_rate is None or target_rate <= max_rate:
                return max(1, int(phases))
        return 1


_ALLOWED_RECONSTRUCTION_MODES = {"anti_alias", "phase_only"}


def _tuple_of_ints(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty YAML list")
    return tuple(int(v) for v in value)


def _tuple_of_floats(value: Any, field: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty YAML list")
    return tuple(float(v) for v in value)


def _normalise_modes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("common_trace.reconstruction_modes must be a non-empty YAML list")
    aliases = {
        "anti_aliased": "anti_alias",
        "anti-alias": "anti_alias",
        "phase-only": "phase_only",
    }
    result = tuple(aliases.get(str(item), str(item)) for item in value)
    unknown = set(result) - _ALLOWED_RECONSTRUCTION_MODES
    if unknown:
        raise ValueError(f"Unsupported common-trace reconstruction modes: {sorted(unknown)}")
    if len(set(result)) != len(result):
        raise ValueError("common_trace.reconstruction_modes contains duplicates")
    return result


def _parse_phase_plan(value: Any) -> tuple[tuple[int | None, int], ...]:
    if value is None:
        return ((None, 1),)
    if not isinstance(value, list) or not value:
        raise ValueError("resampling.phase_plan must be a non-empty YAML list")
    result: list[tuple[int | None, int]] = []
    seen_open_end = False
    previous_max = -1
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each resampling.phase_plan item must be a mapping")
        raw_max = entry.get("max_rate_sps")
        max_rate = None if raw_max is None else int(raw_max)
        phases = int(entry.get("phases", 0))
        if phases < 1:
            raise ValueError("Each resampling.phase_plan phases value must be >= 1")
        if seen_open_end:
            raise ValueError("No phase-plan item may follow max_rate_sps: null")
        if max_rate is None:
            seen_open_end = True
        else:
            if max_rate <= previous_max:
                raise ValueError("resampling.phase_plan max_rate_sps values must increase")
            previous_max = max_rate
        result.append((max_rate, phases))
    if not seen_open_end:
        result.append((None, result[-1][1]))
    return tuple(result)


def _parse_frequency_bands(value: Any) -> tuple[FrequencyBand, ...]:
    if value is None:
        value = [
            {"label": "0-75 Hz", "low_hz": 0, "high_hz": 75},
            {"label": "75-200 Hz", "low_hz": 75, "high_hz": 200},
            {"label": "200 Hz-1 kHz", "low_hz": 200, "high_hz": 1000},
            {"label": "1-5 kHz", "low_hz": 1000, "high_hz": 5000},
            {"label": "5-10 kHz", "low_hz": 5000, "high_hz": 10000},
            {"label": "10-20 kHz", "low_hz": 10000, "high_hz": 20000},
            {"label": "20-40 kHz", "low_hz": 20000, "high_hz": 40000},
            {"label": "40-77 kHz", "low_hz": 40000, "high_hz": 77000},
            {"label": ">77 kHz", "low_hz": 77000, "high_hz": None},
        ]
    if not isinstance(value, list) or not value:
        raise ValueError("psd.variance_bands must be a non-empty YAML list")
    bands: list[FrequencyBand] = []
    labels: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each psd.variance_bands item must be a mapping")
        label = str(entry["label"])
        if not label or label in labels:
            raise ValueError(f"Duplicate or empty PSD variance-band label: {label!r}")
        labels.add(label)
        low = float(entry["low_hz"])
        raw_high = entry.get("high_hz")
        high = None if raw_high is None else float(raw_high)
        if low < 0:
            raise ValueError(f"PSD variance band {label!r} has a negative lower limit")
        if high is not None and high <= low:
            raise ValueError(f"PSD variance band {label!r} has high_hz <= low_hz")
        bands.append(FrequencyBand(label=label, low_hz=low, high_hz=high))
    return tuple(bands)


def _parse_rate_selection(value: Any, *, field: str, target_rates: tuple[int, ...]) -> tuple[int, ...]:
    if isinstance(value, str):
        if value != "target_rates":
            raise ValueError(f"{field} must be a list or the literal 'target_rates'")
        return target_rates
    return tuple(sorted(set(_tuple_of_ints(value, field))))


def load_config(path: Path, output_override: Path | None = None) -> AnalysisConfig:
    data = load_yaml(path)
    resampling = data.get("resampling", {})
    anti_alias_data = resampling.get("anti_alias", {})
    common_data = data.get("common_trace", {})
    psd_data = data.get("psd", {})
    duration_data = data.get("duration_sensitivity", {})
    duration_campaign_data = duration_data.get("duration_campaign", {})
    if not isinstance(duration_campaign_data, dict):
        raise ValueError("duration_sensitivity.duration_campaign must be a mapping")
    trace_data = data.get("time_trace", {})

    reference_rate = int(data["reference_rate_sps"])
    cache_rates = tuple(
        sorted(
            set(_tuple_of_ints(data["cache_rates_sps"], "cache_rates_sps")),
            reverse=True,
        )
    )
    target_rates = tuple(
        sorted(set(_tuple_of_ints(data["target_rates_sps"], "target_rates_sps")))
    )
    highest_cache = max(cache_rates)

    modes_value = common_data.get(
        "reconstruction_modes",
        common_data.get("methods", ["anti_alias", "phase_only"]),
    )
    thresholds_value = common_data.get(
        "fmin_thresholds_pct",
        common_data.get("error_limits_pct", [1.0, 2.0, 5.0]),
    )
    high_rate_data = common_data.get("high_rate_extension", {})
    if not isinstance(high_rate_data, dict):
        raise ValueError("common_trace.high_rate_extension must be a mapping")

    cfg = AnalysisConfig(
        dataset_root=Path(data["dataset_root"]).expanduser(),
        output_root=(output_override or Path(data["output_root"]).expanduser()),
        reference_rate_sps=reference_rate,
        reference_rate_directory=str(
            data.get("reference_rate_directory", f"{reference_rate}Sps")
        ),
        analogue_bandwidth_hz=float(data.get("analogue_bandwidth_hz", 77_000.0)),
        primary_runs=_tuple_of_ints(data["primary_runs"], "primary_runs"),
        sensitivity_runs=_tuple_of_ints(
            data.get("sensitivity_runs", data["primary_runs"]),
            "sensitivity_runs",
        ),
        cache_rates_sps=cache_rates,
        target_rates_sps=target_rates,
        resampling_quality=str(resampling.get("quality", "VHQ")),
        chunk_seconds=float(resampling.get("chunk_seconds", 1.0)),
        cache_dtype=str(resampling.get("cache_dtype", "float32")),
        guard_seconds=float(resampling.get("guard_seconds", 3.0)),
        phase_plan=_parse_phase_plan(resampling.get("phase_plan")),
        anti_alias=AntiAliasConfig(
            attenuation_db=float(anti_alias_data.get("attenuation_db", 80.0)),
            passband_fraction_of_nyquist=float(
                anti_alias_data.get("passband_fraction_of_nyquist", 0.90)
            ),
            stopband_fraction_of_nyquist=float(
                anti_alias_data.get("stopband_fraction_of_nyquist", 1.0)
            ),
        ),
        common_trace=CommonTraceConfig(
            reconstruction_modes=_normalise_modes(modes_value),
            phase_only_source_rate_sps=int(
                common_data.get("phase_only_source_rate_sps", highest_cache)
            ),
            phase_only_sensitivity_source_rates_sps=tuple(
                int(v)
                for v in common_data.get(
                    "phase_only_sensitivity_source_rates_sps", []
                )
            ),
            phase_only_sensitivity_target_rates_sps=tuple(
                int(v)
                for v in common_data.get(
                    "phase_only_sensitivity_target_rates_sps", [50, 150, 2000]
                )
            ),
            fmin_thresholds_pct=_tuple_of_floats(
                thresholds_value,
                "common_trace.fmin_thresholds_pct",
            ),
            high_rate_extension=HighRateExtensionConfig(
                enabled=bool(high_rate_data.get("enabled", True)),
                source_rate_sps=int(
                    high_rate_data.get("source_rate_sps", highest_cache)
                ),
            ),
        ),
        psd=PSDConfig(
            analysis_rate_sps=int(psd_data.get("analysis_rate_sps", highest_cache)),
            sensitivity_rates_sps=tuple(
                int(v) for v in psd_data.get("sensitivity_rates_sps", [])
            ),
            sensitivity_check_rates_sps=tuple(
                int(v)
                for v in psd_data.get(
                    "sensitivity_check_rates_sps", [125000, 160000]
                )
            ),
            sensitivity_relative_frequency_tolerance=float(
                psd_data.get("sensitivity_relative_frequency_tolerance", 0.02)
            ),
            sensitivity_variance_fraction_tolerance=float(
                psd_data.get("sensitivity_variance_fraction_tolerance", 0.01)
            ),
            plot_max_points=int(psd_data.get("plot_max_points", 50000)),
            active_duration_s=float(psd_data.get("active_duration_s", 10.0)),
            idle_duration_s=float(psd_data.get("idle_duration_s", 4.0)),
            idle_gap_s=float(psd_data.get("idle_gap_s", 0.5)),
            segment_duration_s=float(psd_data.get("segment_duration_s", 1.0)),
            overlap_fraction=float(psd_data.get("overlap_fraction", 0.5)),
            cumulative_percentiles=tuple(
                float(v) for v in psd_data.get("cumulative_percentiles", [0.95, 0.99])
            ),
            peak_max_frequency_hz=float(
                psd_data.get("peak_max_frequency_hz", 10_000.0)
            ),
            peak_count=int(psd_data.get("peak_count", 10)),
            variance_capture_rates_sps=_parse_rate_selection(
                psd_data.get("variance_capture_rates_sps", "target_rates"),
                field="psd.variance_capture_rates_sps",
                target_rates=target_rates,
            ),
            variance_capture_thresholds=tuple(
                float(v)
                for v in psd_data.get("variance_capture_thresholds", [0.95, 0.99])
            ),
            highlighted_rates_sps=tuple(
                int(v)
                for v in psd_data.get(
                    "highlighted_rates_sps", [2000, 125000, 160000]
                )
            ),
            low_frequency_nyquist_rates_sps=tuple(
                int(v)
                for v in psd_data.get(
                    "low_frequency_nyquist_rates_sps", [150, 400, 2000]
                )
            ),
            full_frequency_nyquist_rates_sps=tuple(
                int(v)
                for v in psd_data.get(
                    "full_frequency_nyquist_rates_sps", [2000, 125000, 160000]
                )
            ),
            variance_bands=_parse_frequency_bands(psd_data.get("variance_bands")),
        ),
        duration_sensitivity=DurationSensitivityConfig(
            enabled=bool(duration_data.get("enabled", True)),
            source_rate_sps=int(duration_data.get("source_rate_sps", 1_000_000)),
            target_rates_sps=tuple(
                sorted(
                    set(
                        _tuple_of_ints(
                            duration_data.get(
                                "target_rates_sps",
                                [50, 85, 150, 240, 400, 680, 1200, 2000, 3300, 5500, 9400, 16000, 27000, 45000, 80000, 125000, 160000],
                            ),
                            "duration_sensitivity.target_rates_sps",
                        )
                    )
                )
            ),
            window_durations_s=tuple(
                sorted(
                    set(
                        _tuple_of_floats(
                            duration_data.get(
                                "window_durations_s",
                                [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 104],
                            ),
                            "duration_sensitivity.window_durations_s",
                        )
                    )
                )
            ),
            windows_per_duration=int(
                duration_data.get("windows_per_duration", 16)
            ),
            edge_margin_s=float(duration_data.get("edge_margin_s", 0.5)),
            reconstruction_modes=_normalise_modes(
                duration_data.get(
                    "reconstruction_modes",
                    ["anti_alias", "phase_only"],
                )
            ),
            thresholds_pct=tuple(
                sorted(
                    set(
                        _tuple_of_floats(
                            duration_data.get(
                                "thresholds_pct", [0.1, 0.5, 1.0, 2.0, 5.0]
                            ),
                            "duration_sensitivity.thresholds_pct",
                        )
                    )
                )
            ),
            highlighted_rate_sps=int(
                duration_data.get("highlighted_rate_sps", 2000)
            ),
            minimum_samples_per_window=int(
                duration_data.get("minimum_samples_per_window", 4)
            ),
            campaign=DurationCampaignConfig(
                enabled=bool(duration_campaign_data.get("enabled", True)),
                root=Path(
                    duration_campaign_data.get(
                        "root",
                        "external-measurements/durations_without_filter",
                    )
                ).expanduser(),
                expected_durations_s=tuple(
                    sorted(
                        set(
                            _tuple_of_floats(
                                duration_campaign_data.get(
                                    "expected_durations_s",
                                    [5, 10, 20, 50, 100, 200, 300, 400, 500, 600],
                                ),
                                "duration_sensitivity.duration_campaign.expected_durations_s",
                            )
                        )
                    )
                ),
                reference_duration_s=float(
                    duration_campaign_data.get("reference_duration_s", 600.0)
                ),
                steady_state_tolerance_pct=float(
                    duration_campaign_data.get("steady_state_tolerance_pct", 3.0)
                ),
                urecs_correction_factor=float(
                    duration_campaign_data.get("urecs_correction_factor", 0.97)
                ),
                urecs_values_already_include_correction_factor=bool(
                    duration_campaign_data.get(
                        "urecs_values_already_include_correction_factor", False
                    )
                ),
                minimum_runs_per_cell=int(
                    duration_campaign_data.get("minimum_runs_per_cell", 5)
                ),
                use_thesis_fallback=bool(
                    duration_campaign_data.get("use_thesis_fallback", True)
                ),
                fallback_rows=tuple(
                    dict(row)
                    for row in duration_campaign_data.get("fallback_rows", [])
                    if isinstance(row, dict)
                ),
            ),
        ),
        time_trace=TimeTraceConfig(
            run=trace_data.get("run", "auto"),
            active_center_offset_s=float(
                trace_data.get("active_center_offset_s", 52.0)
            ),
            window_duration_s=float(trace_data.get("window_duration_s", 0.1)),
            rates_sps=tuple(
                int(v)
                for v in trace_data.get(
                    "rates_sps", [150, 2000, highest_cache, reference_rate]
                )
            ),
            max_display_points=int(trace_data.get("max_display_points", 20_000)),
        ),
    )

    if not cfg.dataset_root.is_absolute():
        raise ValueError("dataset_root must be an absolute path")
    if not cfg.output_root.is_absolute():
        raise ValueError("output_root must be an absolute path")
    if cfg.reference_rate_sps <= 0:
        raise ValueError("reference_rate_sps must be positive")
    if cfg.analogue_bandwidth_hz <= 0:
        raise ValueError("analogue_bandwidth_hz must be positive")
    if any(rate <= 0 for rate in cfg.cache_rates_sps):
        raise ValueError("cache_rates_sps must contain positive values")
    if max(cfg.cache_rates_sps) >= cfg.reference_rate_sps:
        raise ValueError("All cache_rates_sps must be lower than the reference rate")
    if any(rate <= 0 or rate > cfg.reference_rate_sps for rate in cfg.target_rates_sps):
        raise ValueError(
            "target_rates_sps must be positive and cannot exceed reference_rate_sps"
        )
    if cfg.reference_rate_sps not in cfg.target_rates_sps:
        raise ValueError(
            "target_rates_sps must contain reference_rate_sps for the exact reference anchor"
        )
    if cfg.psd.analysis_rate_sps not in cfg.cache_rates_sps:
        raise ValueError("psd.analysis_rate_sps must be present in cache_rates_sps")
    if any(rate not in cfg.cache_rates_sps for rate in cfg.psd.sensitivity_rates_sps):
        raise ValueError("All psd.sensitivity_rates_sps values must be present in cache_rates_sps")
    if cfg.psd.analysis_rate_sps in cfg.psd.sensitivity_rates_sps:
        raise ValueError("psd.sensitivity_rates_sps must not repeat psd.analysis_rate_sps")
    if len(set(cfg.psd.sensitivity_rates_sps)) != len(cfg.psd.sensitivity_rates_sps):
        raise ValueError("psd.sensitivity_rates_sps contains duplicates")
    if any(rate <= 0 for rate in cfg.psd.sensitivity_check_rates_sps):
        raise ValueError("psd.sensitivity_check_rates_sps must contain positive rates")
    if cfg.psd.sensitivity_relative_frequency_tolerance <= 0:
        raise ValueError("psd.sensitivity_relative_frequency_tolerance must be positive")
    if cfg.psd.sensitivity_variance_fraction_tolerance <= 0:
        raise ValueError("psd.sensitivity_variance_fraction_tolerance must be positive")
    if cfg.psd.plot_max_points < 1000:
        raise ValueError("psd.plot_max_points must be at least 1000")
    if any(value <= 0 for value in cfg.common_trace.fmin_thresholds_pct):
        raise ValueError("common_trace.fmin_thresholds_pct must be positive")
    if cfg.duration_sensitivity.enabled:
        if cfg.duration_sensitivity.source_rate_sps not in cfg.cache_rates_sps:
            raise ValueError(
                "duration_sensitivity.source_rate_sps must be present in cache_rates_sps"
            )
        if cfg.duration_sensitivity.windows_per_duration < 1:
            raise ValueError(
                "duration_sensitivity.windows_per_duration must be >= 1"
            )
        if cfg.duration_sensitivity.minimum_samples_per_window < 2:
            raise ValueError(
                "duration_sensitivity.minimum_samples_per_window must be >= 2"
            )
        if cfg.duration_sensitivity.edge_margin_s < 0:
            raise ValueError(
                "duration_sensitivity.edge_margin_s must be non-negative"
            )
        if any(value <= 0 for value in cfg.duration_sensitivity.window_durations_s):
            raise ValueError(
                "duration_sensitivity.window_durations_s must contain positive values"
            )
        if any(value <= 0 for value in cfg.duration_sensitivity.thresholds_pct):
            raise ValueError(
                "duration_sensitivity.thresholds_pct must contain positive values"
            )
        if cfg.duration_sensitivity.highlighted_rate_sps not in cfg.duration_sensitivity.target_rates_sps:
            raise ValueError(
                "duration_sensitivity.highlighted_rate_sps must be one of target_rates_sps"
            )
        highest_cache_rate = max(cfg.cache_rates_sps)
        if any(rate > highest_cache_rate for rate in cfg.duration_sensitivity.target_rates_sps):
            raise ValueError(
                "duration_sensitivity.target_rates_sps cannot exceed the highest cache rate"
            )

        campaign = cfg.duration_sensitivity.campaign
        if campaign.enabled:
            if campaign.minimum_runs_per_cell < 1:
                raise ValueError(
                    "duration_sensitivity.duration_campaign.minimum_runs_per_cell must be >= 1"
                )
            if campaign.steady_state_tolerance_pct <= 0:
                raise ValueError(
                    "duration_sensitivity.duration_campaign.steady_state_tolerance_pct must be positive"
                )
            if campaign.reference_duration_s <= 0:
                raise ValueError(
                    "duration_sensitivity.duration_campaign.reference_duration_s must be positive"
                )
            if campaign.reference_duration_s not in campaign.expected_durations_s:
                raise ValueError(
                    "duration_sensitivity.duration_campaign.reference_duration_s must be listed in expected_durations_s"
                )

    if cfg.common_trace.phase_only_source_rate_sps not in cfg.cache_rates_sps:
        raise ValueError(
            "common_trace.phase_only_source_rate_sps must be present in cache_rates_sps"
        )
    if any(
        rate not in cfg.cache_rates_sps
        for rate in cfg.common_trace.phase_only_sensitivity_source_rates_sps
    ):
        raise ValueError(
            "All common_trace.phase_only_sensitivity_source_rates_sps values must "
            "be present in cache_rates_sps"
        )
    if any(
        rate <= 0 or rate > cfg.common_trace.phase_only_source_rate_sps
        for rate in cfg.common_trace.phase_only_sensitivity_target_rates_sps
    ):
        raise ValueError(
            "common_trace.phase_only_sensitivity_target_rates_sps must be positive "
            "and no greater than the primary phase-only source rate"
        )
    if cfg.common_trace.high_rate_extension.source_rate_sps not in cfg.cache_rates_sps:
        raise ValueError(
            "common_trace.high_rate_extension.source_rate_sps must be present in cache_rates_sps"
        )
    if (
        cfg.common_trace.high_rate_extension.enabled
        and cfg.common_trace.high_rate_extension.source_rate_sps / 2.0
        <= cfg.analogue_bandwidth_hz
    ):
        raise ValueError(
            "The high-rate extension source Nyquist frequency must exceed analogue_bandwidth_hz"
        )
    if (
        max(cfg.target_rates_sps) > max(cfg.cache_rates_sps)
        and not cfg.common_trace.high_rate_extension.enabled
    ):
        raise ValueError(
            "Target rates above the highest cache require common_trace.high_rate_extension.enabled"
        )
    if not (
        0
        < cfg.anti_alias.passband_fraction_of_nyquist
        < cfg.anti_alias.stopband_fraction_of_nyquist
        <= 1.0
    ):
        raise ValueError("Invalid anti-alias pass/stop-band fractions")
    if cfg.anti_alias.attenuation_db <= 0:
        raise ValueError("anti_alias.attenuation_db must be positive")
    if cfg.chunk_seconds <= 0 or cfg.guard_seconds < 0:
        raise ValueError("resampling chunk_seconds must be > 0 and guard_seconds >= 0")
    if cfg.cache_dtype not in {"float32", "float64"}:
        raise ValueError("resampling.cache_dtype must be float32 or float64")
    if cfg.psd.active_duration_s <= 0 or cfg.psd.idle_duration_s <= 0:
        raise ValueError("PSD active and idle durations must be positive")
    if cfg.psd.idle_gap_s < 0 or cfg.psd.segment_duration_s <= 0:
        raise ValueError("PSD idle_gap_s must be >= 0 and segment_duration_s > 0")
    if not 0 <= cfg.psd.overlap_fraction < 1:
        raise ValueError("psd.overlap_fraction must be in [0, 1)")
    if any(not 0 < value < 1 for value in cfg.psd.cumulative_percentiles):
        raise ValueError("psd.cumulative_percentiles must lie between zero and one")
    if cfg.psd.peak_count < 1 or cfg.psd.peak_max_frequency_hz <= 0:
        raise ValueError("PSD peak_count and peak_max_frequency_hz must be positive")
    if any(rate <= 0 for rate in cfg.psd.variance_capture_rates_sps):
        raise ValueError("psd.variance_capture_rates_sps must contain positive rates")
    if any(rate > cfg.reference_rate_sps for rate in cfg.psd.variance_capture_rates_sps):
        raise ValueError("psd.variance_capture_rates_sps cannot exceed the reference rate")
    if any(not 0 < value < 1 for value in cfg.psd.variance_capture_thresholds):
        raise ValueError("psd.variance_capture_thresholds must lie between zero and one")
    if any(rate <= 0 for rate in cfg.psd.highlighted_rates_sps):
        raise ValueError("psd.highlighted_rates_sps must contain positive rates")
    if any(rate <= 0 for rate in cfg.psd.low_frequency_nyquist_rates_sps):
        raise ValueError("psd.low_frequency_nyquist_rates_sps must contain positive rates")
    if any(rate <= 0 for rate in cfg.psd.full_frequency_nyquist_rates_sps):
        raise ValueError("psd.full_frequency_nyquist_rates_sps must contain positive rates")
    if cfg.time_trace.window_duration_s <= 0:
        raise ValueError("time_trace.window_duration_s must be positive")
    if cfg.time_trace.max_display_points < 2:
        raise ValueError("time_trace.max_display_points must be at least two")
    if any(rate <= 0 or rate > cfg.reference_rate_sps for rate in cfg.time_trace.rates_sps):
        raise ValueError("time_trace.rates_sps contains an unsupported rate")

    return cfg
