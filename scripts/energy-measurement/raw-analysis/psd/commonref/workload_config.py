from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import load_yaml


@dataclass(frozen=True)
class WorkloadSpec:
    workload_id: str
    label: str
    family: str
    precision: str
    scope_config: Path
    enabled: str
    include_in_paper: bool
    notes: str


@dataclass(frozen=True)
class CrossWorkloadPSDConfig:
    enabled: bool
    comparison_rate_sps: int
    minimum_pairs: int
    cumulative_percentiles: tuple[float, ...]
    bands: tuple[tuple[str, float, float], ...]
    dominant_peak_count: int
    minimum_peak_frequency_hz: float
    maximum_peak_frequency_hz: float
    spectrogram_enabled: bool
    spectrogram_run_policy: str
    high_rate_coverage_threshold_hz: float
    log_frequency_derivative_enabled: bool
    fine_structure_enabled: bool
    fine_structure_windows: tuple[tuple[str, float, float], ...]
    idle_load_comparison_enabled: bool
    idle_record_policy: str
    idle_peak_match_bins: int
    idle_load_ratio_bins_per_decade: int
    idle_load_amplification_threshold_db: float
    idle_load_only_threshold_db: float


@dataclass(frozen=True)
class CrossWorkloadCommonReferenceConfig:
    enabled: bool
    sources: tuple[str, ...]
    source_rate_sps: int
    analysis_rate_sps: int
    target_rates_sps: tuple[int, ...]
    window_durations_s: tuple[float, ...]
    windows_per_duration: int
    edge_margin_s: float
    guard_seconds: float
    reconstruction_modes: tuple[str, ...]
    thresholds_pct: tuple[float, ...]
    highlighted_rate_sps: int
    minimum_samples_per_window: int
    cache_dtype: str


@dataclass(frozen=True)
class DirectRateValidationConfig:
    enabled: bool
    maximum_rate_sps: int
    use_normalised_power: bool


@dataclass(frozen=True)
class MultiWorkloadPaperConfig:
    generate_pdf: bool
    generate_png: bool
    generate_tables: bool
    generate_macros: bool
    generate_bundles: bool
    plot_max_points: int


@dataclass(frozen=True)
class MultiWorkloadConfig:
    output_root: Path
    analysis_template_config: Path
    workloads: tuple[WorkloadSpec, ...]
    psd: CrossWorkloadPSDConfig
    common_reference: CrossWorkloadCommonReferenceConfig
    direct_validation: DirectRateValidationConfig
    paper: MultiWorkloadPaperConfig


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _tuple_list(data: Any, field: str, cast) -> tuple:
    if not isinstance(data, list) or not data:
        raise ValueError(f"{field} must be a non-empty YAML list")
    return tuple(cast(item) for item in data)


def load_multi_workload_config(
    path: Path,
    *,
    output_override: Path | None = None,
) -> MultiWorkloadConfig:
    data = load_yaml(path)
    base = path.resolve().parent

    workload_rows = data.get("workloads")
    if not isinstance(workload_rows, list) or not workload_rows:
        raise ValueError("workloads must be a non-empty YAML list")
    workloads: list[WorkloadSpec] = []
    seen: set[str] = set()
    for row in workload_rows:
        if not isinstance(row, dict):
            raise ValueError("Each workloads entry must be a mapping")
        workload_id = str(row["id"]).strip()
        if not workload_id or workload_id in seen:
            raise ValueError(f"Invalid or duplicate workload id: {workload_id!r}")
        seen.add(workload_id)
        enabled_raw = row.get("enabled", "auto")
        if isinstance(enabled_raw, bool):
            enabled = "true" if enabled_raw else "false"
        else:
            enabled = str(enabled_raw).lower()
        if enabled not in {"true", "false", "auto"}:
            raise ValueError(
                f"workloads[{workload_id}].enabled must be true, false, or auto"
            )
        workloads.append(
            WorkloadSpec(
                workload_id=workload_id,
                label=str(row.get("label", workload_id)),
                family=str(row.get("family", row.get("label", workload_id))),
                precision=str(row.get("precision", "unspecified")),
                scope_config=_resolve(base, row["scope_config"]),
                enabled=enabled,
                include_in_paper=bool(row.get("include_in_paper", True)),
                notes=str(row.get("notes", "")),
            )
        )

    psd_data = data.get("psd", {})
    common_data = data.get("common_reference", {})
    direct_data = data.get("direct_rate_validation", {})
    paper_data = data.get("paper_artifacts", {})
    for name, section in (
        ("psd", psd_data),
        ("common_reference", common_data),
        ("direct_rate_validation", direct_data),
        ("paper_artifacts", paper_data),
    ):
        if not isinstance(section, dict):
            raise ValueError(f"{name} must be a mapping")

    raw_fine_windows = psd_data.get(
        "fine_structure_windows",
        [
            {"label": "0–1 kHz", "low_hz": 0.0, "high_hz": 1_000.0},
            {"label": "1–8 kHz", "low_hz": 1_000.0, "high_hz": 8_000.0},
            {"label": "8–16 kHz", "low_hz": 8_000.0, "high_hz": 16_000.0},
            {"label": "25–35 kHz", "low_hz": 25_000.0, "high_hz": 35_000.0},
            {"label": "300–700 kHz", "low_hz": 300_000.0, "high_hz": 700_000.0},
        ],
    )
    if not isinstance(raw_fine_windows, list) or not raw_fine_windows:
        raise ValueError("psd.fine_structure_windows must be a non-empty YAML list")
    fine_structure_windows: list[tuple[str, float, float]] = []
    for row in raw_fine_windows:
        if not isinstance(row, dict):
            raise ValueError("Each psd.fine_structure_windows entry must be a mapping")
        low = float(row["low_hz"])
        high = float(row["high_hz"])
        if low < 0 or high <= low:
            raise ValueError("psd.fine_structure_windows requires 0 <= low_hz < high_hz")
        fine_structure_windows.append((str(row["label"]), low, high))

    raw_bands = psd_data.get("bands")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise ValueError("psd.bands must be a non-empty YAML list")
    bands: list[tuple[str, float, float]] = []
    previous = -1.0
    for row in raw_bands:
        if not isinstance(row, dict):
            raise ValueError("Each psd.bands entry must be a mapping")
        low = float(row["low_hz"])
        high = float(row["high_hz"])
        if low < 0 or high <= low or low < previous - 1e-12:
            raise ValueError("psd.bands must be ordered, non-overlapping ranges")
        bands.append((str(row["label"]), low, high))
        previous = high

    sources = _tuple_list(
        common_data.get("sources", ["tek", "pico"]),
        "common_reference.sources",
        str,
    )
    if any(source not in {"tek", "pico"} for source in sources):
        raise ValueError("common_reference.sources supports only tek and pico")
    modes = _tuple_list(
        common_data.get("reconstruction_modes", ["anti_alias", "phase_only"]),
        "common_reference.reconstruction_modes",
        str,
    )
    if any(mode not in {"anti_alias", "phase_only"} for mode in modes):
        raise ValueError(
            "common_reference.reconstruction_modes supports anti_alias and phase_only"
        )

    idle_record_policy = str(
        psd_data.get("idle_record_policy", "full_record_per_run_equal_weight")
    )
    if idle_record_policy != "full_record_per_run_equal_weight":
        raise ValueError(
            "psd.idle_record_policy currently supports only "
            "full_record_per_run_equal_weight"
        )
    if int(psd_data.get("idle_peak_match_bins", 3)) < 1:
        raise ValueError("psd.idle_peak_match_bins must be >= 1")
    if int(psd_data.get("idle_load_ratio_bins_per_decade", 24)) < 1:
        raise ValueError("psd.idle_load_ratio_bins_per_decade must be >= 1")
    if float(psd_data.get("idle_load_amplification_threshold_db", 3.0)) < 0:
        raise ValueError("psd.idle_load_amplification_threshold_db must be >= 0")
    if float(psd_data.get("idle_load_only_threshold_db", 6.0)) < float(
        psd_data.get("idle_load_amplification_threshold_db", 3.0)
    ):
        raise ValueError(
            "psd.idle_load_only_threshold_db must be >= "
            "psd.idle_load_amplification_threshold_db"
        )

    source_rate = int(common_data.get("source_rate_sps", 5_000_000))
    analysis_rate = int(common_data.get("analysis_rate_sps", 1_000_000))
    if source_rate <= 0 or analysis_rate <= 0 or analysis_rate > source_rate:
        raise ValueError("Common-reference source/analysis rates are invalid")

    return MultiWorkloadConfig(
        output_root=(
            output_override.resolve()
            if output_override is not None
            else _resolve(base, data["output_root"])
        ),
        analysis_template_config=_resolve(base, data["analysis_template_config"]),
        workloads=tuple(workloads),
        psd=CrossWorkloadPSDConfig(
            enabled=bool(psd_data.get("enabled", True)),
            comparison_rate_sps=int(psd_data.get("comparison_rate_sps", 5_000_000)),
            minimum_pairs=int(psd_data.get("minimum_pairs", 5)),
            cumulative_percentiles=_tuple_list(
                psd_data.get("cumulative_percentiles", [0.5, 0.9, 0.95, 0.99]),
                "psd.cumulative_percentiles",
                float,
            ),
            bands=tuple(bands),
            dominant_peak_count=int(psd_data.get("dominant_peak_count", 8)),
            minimum_peak_frequency_hz=float(
                psd_data.get("minimum_peak_frequency_hz", 1.0)
            ),
            maximum_peak_frequency_hz=float(
                psd_data.get("maximum_peak_frequency_hz", 2_500_000.0)
            ),
            spectrogram_enabled=bool(psd_data.get("spectrogram_enabled", True)),
            spectrogram_run_policy=str(
                psd_data.get("spectrogram_run_policy", "representative")
            ),
            high_rate_coverage_threshold_hz=float(
                psd_data.get("high_rate_coverage_threshold_hz", 2_500_000.0)
            ),
            log_frequency_derivative_enabled=bool(
                psd_data.get("log_frequency_derivative_enabled", True)
            ),
            fine_structure_enabled=bool(
                psd_data.get("fine_structure_enabled", True)
            ),
            fine_structure_windows=tuple(fine_structure_windows),
            idle_load_comparison_enabled=bool(
                psd_data.get("idle_load_comparison_enabled", True)
            ),
            idle_record_policy=str(
                psd_data.get(
                    "idle_record_policy",
                    "full_record_per_run_equal_weight",
                )
            ),
            idle_peak_match_bins=int(psd_data.get("idle_peak_match_bins", 3)),
            idle_load_ratio_bins_per_decade=int(
                psd_data.get("idle_load_ratio_bins_per_decade", 24)
            ),
            idle_load_amplification_threshold_db=float(
                psd_data.get("idle_load_amplification_threshold_db", 3.0)
            ),
            idle_load_only_threshold_db=float(
                psd_data.get("idle_load_only_threshold_db", 6.0)
            ),
        ),
        common_reference=CrossWorkloadCommonReferenceConfig(
            enabled=bool(common_data.get("enabled", True)),
            sources=sources,
            source_rate_sps=source_rate,
            analysis_rate_sps=analysis_rate,
            target_rates_sps=_tuple_list(
                common_data.get(
                    "target_rates_sps",
                    [
                        50, 85, 150, 240, 400, 680, 1200, 2000, 2500,
                        3300, 5500, 9400, 16000, 25000, 45000, 80000,
                        100000, 125000, 160000,
                    ],
                ),
                "common_reference.target_rates_sps",
                int,
            ),
            window_durations_s=_tuple_list(
                common_data.get(
                    "window_durations_s",
                    [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
                ),
                "common_reference.window_durations_s",
                float,
            ),
            windows_per_duration=int(common_data.get("windows_per_duration", 16)),
            edge_margin_s=float(common_data.get("edge_margin_s", 0.0)),
            guard_seconds=float(common_data.get("guard_seconds", 0.5)),
            reconstruction_modes=modes,
            thresholds_pct=_tuple_list(
                common_data.get("thresholds_pct", [0.1, 0.5, 1.0, 2.0, 5.0]),
                "common_reference.thresholds_pct",
                float,
            ),
            highlighted_rate_sps=int(common_data.get("highlighted_rate_sps", 2000)),
            minimum_samples_per_window=int(
                common_data.get("minimum_samples_per_window", 4)
            ),
            cache_dtype=str(common_data.get("cache_dtype", "float32")),
        ),
        direct_validation=DirectRateValidationConfig(
            enabled=bool(direct_data.get("enabled", True)),
            maximum_rate_sps=int(direct_data.get("maximum_rate_sps", 5_000_000)),
            use_normalised_power=bool(direct_data.get("use_normalised_power", True)),
        ),
        paper=MultiWorkloadPaperConfig(
            generate_pdf=bool(paper_data.get("generate_pdf", True)),
            generate_png=bool(paper_data.get("generate_png", True)),
            generate_tables=bool(paper_data.get("generate_tables", True)),
            generate_macros=bool(paper_data.get("generate_macros", True)),
            generate_bundles=bool(paper_data.get("generate_bundles", True)),
            plot_max_points=int(paper_data.get("plot_max_points", 50_000)),
        ),
    )
