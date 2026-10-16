from __future__ import annotations

import csv
import gc
import json
import math
import os
import re
import shutil
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullFormatter
import numpy as np
import soxr
from scipy.integrate import trapezoid
from scipy.signal import find_peaks, spectrogram, welch

from . import __version__
from .config import load_config
from .duration_sensitivity import UniformLinearIntegral
from .resampling import phase_count_for_target, phase_only_grid, resample_phase_grid
from .scope_config import ScopeComparisonConfig, load_scope_config
from .scope_compare import (
    _pair_source_identity,
    _preflight_pair,
    _read_parquet_column,
    _source_rates_for_directory,
    discover_pairs,
    discover_rate_directories,
)
from .utils import (
    LOGGER,
    human_rate,
    normalise_for_json,
    package_versions,
    quantile,
    read_json,
    stable_hash,
    utc_now_iso,
    write_csv,
    write_json,
)
from .workload_config import MultiWorkloadConfig, WorkloadSpec


_MULTI_WORKLOAD_SCHEMA_VERSION = 2
_CACHE_SCHEMA_VERSION = 1


class WorkloadUnavailable(RuntimeError):
    pass


def _finite(value: Any, default: float = float("nan")) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_")
    return text or "workload"


def _workload_enabled(spec: WorkloadSpec, scope_cfg: ScopeComparisonConfig | None) -> bool:
    if spec.enabled == "false":
        return False
    if spec.enabled == "true":
        return True
    return bool(scope_cfg is not None and scope_cfg.dataset_root.is_dir())


def _load_scope_optional(spec: WorkloadSpec) -> tuple[ScopeComparisonConfig | None, str]:
    if not spec.scope_config.is_file():
        return None, "scope_config_missing"
    try:
        cfg = load_scope_config(spec.scope_config)
    except Exception as error:
        return None, f"scope_config_invalid:{type(error).__name__}:{error}"
    if not cfg.dataset_root.is_dir():
        return cfg, "dataset_root_missing"
    return cfg, "available"


def _rate_directory(scope_cfg: ScopeComparisonConfig, rate_sps: int) -> Path | None:
    try:
        rates = dict(discover_rate_directories(scope_cfg))
    except FileNotFoundError:
        return None
    return rates.get(int(rate_sps))


def _valid_pairs_at_rate(
    scope_cfg: ScopeComparisonConfig,
    rate_sps: int,
) -> tuple[list[tuple[int, Path, Path]], list[dict[str, Any]], str]:
    directory = _rate_directory(scope_cfg, rate_sps)
    if directory is None:
        return [], [], "rate_directory_missing"
    pairs, inventory = discover_pairs(scope_cfg, directory, selected_runs=None)
    section_seconds = inventory.get("section_marker_seconds")
    valid: list[tuple[int, Path, Path]] = []
    rows: list[dict[str, Any]] = []
    for run, tek_path, pico_path in pairs:
        row = _preflight_pair(
            scope_cfg,
            int(rate_sps),
            int(run),
            tek_path,
            pico_path,
            section_seconds,
        )
        rows.append(row)
        if row.get("status") == "valid":
            valid.append((run, tek_path, pico_path))
    return valid, rows, "available" if valid else "no_valid_pairs"


def _zero_model(scope_cfg: ScopeComparisonConfig) -> dict[str, Any]:
    path = scope_cfg.output_root / "zero_correction" / "zero_offset_model.json"
    if path.is_file():
        try:
            payload = read_json(path)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _zero_offset_for_workload(scope_cfg: ScopeComparisonConfig) -> float:
    model = _zero_model(scope_cfg)
    if not bool(model.get("correction_applied", False)):
        return 0.0
    return _finite(model.get("offset_applied_a"), 0.0)


def _power_from_current(current: np.ndarray, scope_cfg: ScopeComparisonConfig) -> np.ndarray:
    current = np.asarray(current, dtype=np.float64)
    voltage = np.asarray(scope_cfg.voltage_model.voltage(current), dtype=np.float64)
    return voltage * current


def _integral(values: np.ndarray, rate_sps: float) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size < 2:
        return 0.0
    return float(trapezoid(values, dx=1.0 / float(rate_sps)))


def _current_and_power(
    scope_cfg: ScopeComparisonConfig,
    source: str,
    raw: np.ndarray,
    *,
    apply_workload_zero: bool,
) -> tuple[np.ndarray, np.ndarray]:
    calibration = scope_cfg.tek if source == "tek" else scope_cfg.pico
    current = np.asarray(calibration.calibrate(raw), dtype=np.float64)
    if source == "tek" and apply_workload_zero:
        current = current + _zero_offset_for_workload(scope_cfg)
    return current, _power_from_current(current, scope_cfg)


def _source_identity_for_workload(
    scope_cfg: ScopeComparisonConfig,
    run: int,
    tek_path: Path,
    pico_path: Path,
) -> dict[str, Any]:
    identity = _pair_source_identity(tek_path, pico_path)
    return {
        "run": int(run),
        "pair_identity": identity,
        "zero_model_hash": str(_zero_model(scope_cfg).get("model_hash", "")),
        "voltage_model": normalise_for_json(scope_cfg.voltage_model),
        "tek_calibration": normalise_for_json(scope_cfg.tek),
        "pico_calibration": normalise_for_json(scope_cfg.pico),
    }


def _inventory_rows(cfg: MultiWorkloadConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in cfg.workloads:
        scope_cfg, status = _load_scope_optional(spec)
        enabled = _workload_enabled(spec, scope_cfg)
        if spec.enabled == "false":
            inventory_status = "disabled"
        elif status != "available":
            inventory_status = "unavailable"
        else:
            inventory_status = "available"
        row: dict[str, Any] = {
            "workload_id": spec.workload_id,
            "workload_label": spec.label,
            "workload_family": spec.family,
            "workload_precision": spec.precision,
            "configured_enabled": spec.enabled,
            "enabled": enabled,
            "include_in_paper": spec.include_in_paper,
            "scope_config": str(spec.scope_config),
            "scope_config_status": status,
            "dataset_root": str(scope_cfg.dataset_root) if scope_cfg else "",
            "scope_output_root": str(scope_cfg.output_root) if scope_cfg else "",
            "common_psd_rate_sps": cfg.psd.comparison_rate_sps,
            "common_reference_rate_sps": cfg.common_reference.source_rate_sps,
            "common_rate_valid_pairs": 0,
            "scope_summary_available": False,
            "zero_offset_status": "unavailable",
            "psd_ready": False,
            "common_reference_ready": False,
            "status": inventory_status,
            "reason": "" if status == "available" else status,
            "notes": spec.notes,
        }
        if enabled and scope_cfg is not None and scope_cfg.dataset_root.is_dir():
            pairs, _, pair_status = _valid_pairs_at_rate(
                scope_cfg, cfg.psd.comparison_rate_sps
            )
            row["common_rate_valid_pairs"] = len(pairs)
            row["scope_summary_available"] = (
                scope_cfg.output_root / "SCOPE_COMPARISON_SUMMARY.md"
            ).is_file()
            model = _zero_model(scope_cfg)
            row["zero_offset_status"] = str(model.get("status", "not_detected"))
            row["psd_ready"] = len(pairs) >= cfg.psd.minimum_pairs
            row["common_reference_ready"] = (
                len(pairs) >= cfg.psd.minimum_pairs
                and cfg.common_reference.source_rate_sps
                == cfg.psd.comparison_rate_sps
            )
            row["status"] = "ready" if row["psd_ready"] else "partial"
            row["reason"] = pair_status if not row["psd_ready"] else ""
        rows.append(row)
    return rows


def run_multi_workload_inventory(cfg: MultiWorkloadConfig) -> Path:
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    root = cfg.output_root / "inventory"
    root.mkdir(parents=True, exist_ok=True)
    rows = _inventory_rows(cfg)
    write_csv(root / "workload_inventory.csv", rows)
    write_json(
        root / "workload_inventory.json",
        {
            "schema_version": _MULTI_WORKLOAD_SCHEMA_VERSION,
            "created_utc": utc_now_iso(),
            "output_root": str(cfg.output_root),
            "workloads": rows,
        },
    )
    lines = [
        "# Multi-workload inventory",
        "",
        "| Workload | Family | Precision | Status | 5-MS/s pairs | Scope summary | Zero-offset status | PSD | Common reference |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {label} | {family} | {precision} | {status} | {pairs} | {summary} | {zero} | {psd} | {common} |".format(
                label=row["workload_label"],
                family=row["workload_family"],
                precision=row["workload_precision"],
                status=row["status"],
                pairs=row["common_rate_valid_pairs"],
                summary="yes" if row["scope_summary_available"] else "no",
                zero=row["zero_offset_status"],
                psd="yes" if row["psd_ready"] else "no",
                common="yes" if row["common_reference_ready"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "Missing or incomplete workloads are documented and skipped; the measurement trees remain read-only.",
            "",
        ]
    )
    summary = root / "WORKLOAD_INVENTORY.md"
    summary.write_text("\n".join(lines), encoding="utf-8")
    return summary


def _cache_paths(
    cfg: MultiWorkloadConfig,
    workload_id: str,
    source: str,
    run: int,
) -> tuple[Path, Path]:
    root = (
        cfg.output_root
        / "common_reference"
        / "cache"
        / workload_id
        / source
    )
    return root / f"run_{run}_{cfg.common_reference.analysis_rate_sps}Sps.f32", root / f"run_{run}.json"


def _load_or_build_power_cache(
    cfg: MultiWorkloadConfig,
    template_cfg: Any,
    spec: WorkloadSpec,
    scope_cfg: ScopeComparisonConfig,
    run: int,
    tek_path: Path,
    pico_path: Path,
    *,
    force: bool,
) -> tuple[dict[str, np.memmap], dict[str, Any]]:
    identity = _source_identity_for_workload(
        scope_cfg, run, tek_path, pico_path
    )
    signature = stable_hash(
        {
            "schema": _CACHE_SCHEMA_VERSION,
            "source_identity": identity,
            "source_rate_sps": cfg.common_reference.source_rate_sps,
            "analysis_rate_sps": cfg.common_reference.analysis_rate_sps,
            "sources": cfg.common_reference.sources,
            "cache_dtype": cfg.common_reference.cache_dtype,
            "resampling_quality": template_cfg.resampling_quality,
        }
    )
    infos: dict[str, Any] = {}
    reusable = True
    for source in cfg.common_reference.sources:
        data_path, meta_path = _cache_paths(
            cfg, spec.workload_id, source, run
        )
        if force or not data_path.is_file() or not meta_path.is_file():
            reusable = False
            break
        try:
            meta = read_json(meta_path)
            count = int(meta["output_samples"])
            expected = count * np.dtype(meta["dtype"]).itemsize
            if meta.get("signature") != signature or data_path.stat().st_size != expected:
                reusable = False
                break
            infos[source] = meta
        except Exception:
            reusable = False
            break

    if not reusable:
        for source, source_path, column in (
            ("tek", tek_path, scope_cfg.tek.column),
            ("pico", pico_path, scope_cfg.pico.column),
        ):
            if source not in cfg.common_reference.sources:
                continue
            raw, _ = _read_parquet_column(source_path, column)
            current, power = _current_and_power(
                scope_cfg,
                source,
                raw,
                apply_workload_zero=True,
            )
            source_rate = cfg.common_reference.source_rate_sps
            if source_rate != cfg.psd.comparison_rate_sps:
                raise ValueError(
                    "Multi-workload source_rate_sps must match the physical common-rate directory"
                )
            if cfg.common_reference.analysis_rate_sps == source_rate:
                reduced = power
            else:
                reduced = np.asarray(
                    soxr.resample(
                        power,
                        float(source_rate),
                        float(cfg.common_reference.analysis_rate_sps),
                        quality=template_cfg.resampling_quality,
                    ),
                    dtype=np.float64,
                )
            data_path, meta_path = _cache_paths(
                cfg, spec.workload_id, source, run
            )
            data_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = data_path.with_suffix(data_path.suffix + ".part")
            np.asarray(reduced, dtype=cfg.common_reference.cache_dtype).tofile(tmp)
            os.replace(tmp, data_path)
            meta = {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "signature": signature,
                "workload_id": spec.workload_id,
                "workload_label": spec.label,
                "source": source,
                "run": int(run),
                "input_rate_sps": int(source_rate),
                "input_samples": int(power.size),
                "input_energy_j": _integral(power, source_rate),
                "output_rate_sps": int(cfg.common_reference.analysis_rate_sps),
                "output_samples": int(reduced.size),
                "output_energy_j": _integral(
                    reduced, cfg.common_reference.analysis_rate_sps
                ),
                "dtype": cfg.common_reference.cache_dtype,
                "source_identity": identity,
            }
            meta["energy_qc_error_pct"] = (
                100.0
                * (meta["output_energy_j"] - meta["input_energy_j"])
                / meta["input_energy_j"]
                if meta["input_energy_j"]
                else float("nan")
            )
            write_json(meta_path, meta)
            infos[source] = meta
            del raw, current, power, reduced
            gc.collect()

    arrays: dict[str, np.memmap] = {}
    for source in cfg.common_reference.sources:
        data_path, meta_path = _cache_paths(cfg, spec.workload_id, source, run)
        meta = infos.get(source) or read_json(meta_path)
        arrays[source] = np.memmap(
            data_path,
            mode="r",
            dtype=np.dtype(meta["dtype"]),
            shape=(int(meta["output_samples"]),),
        )
        infos[source] = meta
    return arrays, {"signature": signature, "sources": infos}


def _welch_parameters(sample_count: int, rate_sps: float) -> tuple[int, int, int]:
    if sample_count < 64:
        return 0, 0, 0
    target = min(1_048_576, max(64, int(round(0.5 * rate_sps))))
    target = min(target, sample_count)
    if target % 2:
        target -= 1
    while target >= 64:
        overlap = target // 2
        segments = 1 + max(0, (sample_count - target) // max(1, target - overlap))
        if segments >= 8 or target <= 256:
            return int(target), int(overlap), int(segments)
        target //= 2
        if target % 2:
            target -= 1
    return 0, 0, 0


def _density_cumulative(frequencies: np.ndarray, density: np.ndarray) -> np.ndarray:
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    if frequencies.size < 2:
        return np.zeros_like(frequencies)
    increments = 0.5 * (density[1:] + density[:-1]) * np.diff(frequencies)
    cumulative = np.concatenate(([0.0], np.cumsum(increments)))
    total = float(cumulative[-1])
    return cumulative / total if total > 0 else np.zeros_like(cumulative)


def _frequency_at_fraction(
    frequencies: np.ndarray,
    cumulative: np.ndarray,
    fraction: float,
) -> float:
    if frequencies.size == 0 or cumulative.size == 0 or cumulative[-1] <= 0:
        return float("nan")
    return float(np.interp(float(fraction), cumulative, frequencies))


def _density_fraction(
    frequencies: np.ndarray,
    density: np.ndarray,
    low_hz: float,
    high_hz: float,
) -> float:
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    if frequencies.size < 2:
        return float("nan")
    total = float(trapezoid(density, frequencies))
    if total <= 0:
        return float("nan")
    mask = (frequencies >= low_hz) & (frequencies <= high_hz)
    if np.count_nonzero(mask) < 2:
        return 0.0
    return float(trapezoid(density[mask], frequencies[mask]) / total)


def _spectral_centroid(frequencies: np.ndarray, density: np.ndarray) -> float:
    total = float(trapezoid(density, frequencies)) if frequencies.size > 1 else 0.0
    if total <= 0:
        return float("nan")
    return float(trapezoid(frequencies * density, frequencies) / total)


def _spectral_entropy(frequencies: np.ndarray, density: np.ndarray) -> float:
    if frequencies.size < 3:
        return float("nan")
    increments = 0.5 * (density[1:] + density[:-1]) * np.diff(frequencies)
    increments = np.maximum(increments, 0.0)
    total = float(np.sum(increments))
    if total <= 0:
        return float("nan")
    probabilities = increments / total
    positive = probabilities > 0
    entropy = -float(np.sum(probabilities[positive] * np.log(probabilities[positive])))
    maximum = math.log(max(2, int(np.count_nonzero(positive))))
    return entropy / maximum if maximum > 0 else 0.0


def _dominant_peaks(
    frequencies: np.ndarray,
    density: np.ndarray,
    count: int,
    low_hz: float,
    high_hz: float,
) -> list[dict[str, float]]:
    mask = (
        (frequencies >= low_hz)
        & (frequencies <= high_hz)
        & np.isfinite(density)
        & (density > 0)
    )
    if np.count_nonzero(mask) < 3:
        return []
    f = frequencies[mask]
    d = density[mask]
    log_density = 10.0 * np.log10(np.maximum(d, np.max(d) * 1e-15))
    peaks, properties = find_peaks(log_density, prominence=1.0)
    if peaks.size == 0:
        peaks = np.asarray([int(np.argmax(log_density))], dtype=np.int64)
        prominences = np.asarray([0.0])
    else:
        prominences = np.asarray(properties.get("prominences", np.zeros(peaks.size)))
    order = sorted(
        range(peaks.size),
        key=lambda index: (float(d[peaks[index]]), float(prominences[index])),
        reverse=True,
    )[: max(1, int(count))]
    return [
        {
            "frequency_hz": float(f[peaks[index]]),
            "density": float(d[peaks[index]]),
            "relative_db": float(log_density[peaks[index]] - np.max(log_density)),
            "prominence_db": float(prominences[index]),
        }
        for index in order
    ]


def _density_integral_band(
    frequencies: np.ndarray,
    density: np.ndarray,
    low_hz: float,
    high_hz: float,
) -> float:
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    mask = (frequencies >= float(low_hz)) & (frequencies <= float(high_hz))
    if np.count_nonzero(mask) < 2:
        return 0.0
    return float(trapezoid(density[mask], frequencies[mask]))


def _safe_ratio_db(numerator: float, denominator: float) -> float:
    numerator = float(numerator)
    denominator = float(denominator)
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return float("nan")
    if numerator <= 0 or denominator <= 0:
        return float("nan")
    return 10.0 * math.log10(numerator / denominator)


def _classify_idle_load_peak(
    *,
    active_to_idle_db: float,
    idle_peak_matched: bool,
    amplification_threshold_db: float,
    load_only_threshold_db: float,
) -> str:
    if not math.isfinite(active_to_idle_db):
        return "unresolved"
    if idle_peak_matched:
        if active_to_idle_db >= load_only_threshold_db:
            return "idle_matched_strongly_load_amplified"
        if active_to_idle_db >= amplification_threshold_db:
            return "idle_matched_load_amplified"
        if active_to_idle_db <= -amplification_threshold_db:
            return "idle_dominant_at_load_peak"
        return "idle_matched_similar_level"
    if active_to_idle_db >= load_only_threshold_db:
        return "no_dominant_idle_match_load_only_candidate"
    if active_to_idle_db >= amplification_threshold_db:
        return "no_dominant_idle_match_load_enhanced"
    return "no_dominant_idle_match_unresolved"


def _psd_for_signal(values: np.ndarray, rate_sps: float) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    nperseg, noverlap, segments = _welch_parameters(values.size, rate_sps)
    if nperseg < 64:
        raise ValueError("Insufficient samples for Welch PSD")
    frequencies, density = welch(
        np.asarray(values, dtype=np.float64),
        fs=float(rate_sps),
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend="constant",
        scaling="density",
    )
    return frequencies, density, {
        "nperseg": nperseg,
        "noverlap": noverlap,
        "welch_segments": segments,
        "frequency_resolution_hz": float(rate_sps / nperseg),
    }


def _median_on_grid(
    entries: Sequence[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    if not entries:
        raise ValueError("No spectra to aggregate")
    resolutions = [
        float(np.median(np.diff(frequencies)))
        for frequencies, _ in entries
        if frequencies.size > 1
    ]
    if not resolutions:
        raise ValueError("Spectra have no frequency resolution")
    source_index = int(np.argmax(resolutions))
    grid = np.asarray(entries[source_index][0], dtype=np.float64)
    maximum = min(float(frequencies[-1]) for frequencies, _ in entries)
    grid = grid[grid <= maximum]
    stack = []
    for frequencies, density in entries:
        if frequencies.size == grid.size and np.allclose(
            frequencies, grid, rtol=0.0, atol=1e-10
        ):
            stack.append(np.asarray(density, dtype=np.float64))
        else:
            stack.append(np.interp(grid, frequencies, density))
    return grid, np.median(np.vstack(stack), axis=0)


def _idle_psd_at_common_rate(
    cfg: MultiWorkloadConfig,
    scope_cfg: ScopeComparisonConfig,
    rate_sps: int,
) -> dict[str, Any] | None:
    """Build or reuse the exact-rate external-idle PSD reference.

    Every physical idle record is analysed at its full available duration.  The
    Welch segment length/overlap are selected by the same helper as for active
    records.  Each physical idle run contributes one PSD to the pointwise
    cross-run median, so longer records improve the statistical averaging
    within that run without receiving extra cross-run weight.
    """
    if scope_cfg.external_idle.dataset_root is None:
        return None
    idle_cfg = ScopeComparisonConfig(
        dataset_root=scope_cfg.external_idle.dataset_root,
        output_root=scope_cfg.output_root / "external_idle",
        dataset=scope_cfg.dataset,
        external_idle=scope_cfg.external_idle,
        zero_offset_correction=scope_cfg.zero_offset_correction,
        rate_directories=scope_cfg.rate_directories,
        representative_run=scope_cfg.representative_run,
        source_rates=scope_cfg.source_rates,
        tek=scope_cfg.tek,
        pico=scope_cfg.pico,
        voltage_model=scope_cfg.voltage_model,
        alignment=scope_cfg.alignment,
        windows=scope_cfg.windows,
        spectral=scope_cfg.spectral,
        validation=scope_cfg.validation,
        input_policy=scope_cfg.input_policy,
        averaging_windows_ms=scope_cfg.averaging_windows_ms,
    )
    pairs, _, status = _valid_pairs_at_rate(idle_cfg, rate_sps)
    if not pairs:
        return None

    signature = stable_hash(
        {
            "schema": _MULTI_WORKLOAD_SCHEMA_VERSION,
            "rate_sps": int(rate_sps),
            "record_policy": cfg.psd.idle_record_policy,
            "pairs": [
                {
                    "run": int(run),
                    "pair_identity": _pair_source_identity(tek_path, pico_path),
                }
                for run, tek_path, pico_path in pairs
            ],
            "tek_calibration": normalise_for_json(idle_cfg.tek),
            "pico_calibration": normalise_for_json(idle_cfg.pico),
            "voltage_model": normalise_for_json(idle_cfg.voltage_model),
        }
    )
    cache_root = cfg.output_root / "psd" / "external_idle" / f"{rate_sps}Sps"
    cache_npz = cache_root / "idle_psd_summary.npz"
    cache_json = cache_root / "idle_psd_metrics.json"
    cache_csv = cache_root / "idle_per_run.csv"
    if cache_npz.is_file() and cache_json.is_file():
        payload = read_json(cache_json)
        if payload.get("signature") == signature:
            arrays = {key: value for key, value in np.load(cache_npz).items()}
            return {
                "status": "available_cached",
                "valid_pairs": int(payload["valid_pairs"]),
                "arrays": arrays,
                "per_run": _read_csv(cache_csv) if cache_csv.is_file() else [],
                "rate_sps": int(rate_sps),
                "signature": signature,
                "metrics": payload,
            }

    current_entries: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        "tek": [], "pico": []
    }
    power_entries: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        "tek": [], "pico": []
    }
    per_run: list[dict[str, Any]] = []
    for run, tek_path, pico_path in pairs:
        run_row: dict[str, Any] = {"run": int(run)}
        for source, source_path, column in (
            ("tek", tek_path, idle_cfg.tek.column),
            ("pico", pico_path, idle_cfg.pico.column),
        ):
            raw, _ = _read_parquet_column(source_path, column)
            current, power = _current_and_power(
                idle_cfg,
                source,
                raw,
                apply_workload_zero=False,
            )
            f_current, p_current, meta = _psd_for_signal(current, rate_sps)
            f_power, p_power, _ = _psd_for_signal(power, rate_sps)
            current_entries[source].append((f_current, p_current))
            power_entries[source].append((f_power, p_power))
            run_row[f"{source}_sample_count"] = int(current.size)
            run_row[f"{source}_duration_s"] = float(current.size / rate_sps)
            run_row[f"{source}_mean_current_a"] = float(np.mean(current))
            run_row[f"{source}_mean_power_w"] = float(np.mean(power))
            run_row[f"{source}_nperseg"] = int(meta["nperseg"])
            run_row[f"{source}_noverlap"] = int(meta["noverlap"])
            run_row[f"{source}_welch_segments"] = int(meta["welch_segments"])
            run_row[f"{source}_frequency_resolution_hz"] = float(
                meta["frequency_resolution_hz"]
            )
            del raw, current, power
            gc.collect()
        per_run.append(run_row)
        gc.collect()

    arrays: dict[str, np.ndarray] = {}
    for source in ("tek", "pico"):
        f_current, median_current = _median_on_grid(current_entries[source])
        f_power, median_power = _median_on_grid(power_entries[source])
        arrays[f"{source}_current_frequencies_hz"] = f_current
        arrays[f"{source}_current_idle_psd_a2_per_hz"] = median_current
        arrays[f"{source}_power_frequencies_hz"] = f_power
        arrays[f"{source}_power_idle_psd_w2_per_hz"] = median_power

    durations = np.asarray(
        [
            min(float(row["tek_duration_s"]), float(row["pico_duration_s"]))
            for row in per_run
        ],
        dtype=np.float64,
    )
    welch_segments = np.asarray(
        [
            min(int(row["tek_welch_segments"]), int(row["pico_welch_segments"]))
            for row in per_run
        ],
        dtype=np.float64,
    )
    metrics = {
        "signature": signature,
        "schema_version": _MULTI_WORKLOAD_SCHEMA_VERSION,
        "rate_sps": int(rate_sps),
        "valid_pairs": len(pairs),
        "record_policy": cfg.psd.idle_record_policy,
        "record_policy_description": (
            "Full physical idle record per run; identical Welch method to active "
            "records; one equal-weight PSD per physical run before the cross-run median."
        ),
        "total_physical_idle_duration_s": float(np.sum(durations)),
        "median_idle_duration_s": float(np.median(durations)),
        "minimum_idle_duration_s": float(np.min(durations)),
        "maximum_idle_duration_s": float(np.max(durations)),
        "total_welch_segments": int(np.sum(welch_segments)),
        "median_welch_segments_per_run": float(np.median(welch_segments)),
        "minimum_welch_segments_per_run": int(np.min(welch_segments)),
        "maximum_welch_segments_per_run": int(np.max(welch_segments)),
    }
    cache_root.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_npz, **arrays)
    write_json(cache_json, metrics)
    write_csv(cache_csv, per_run)
    return {
        "status": "available",
        "valid_pairs": len(pairs),
        "arrays": arrays,
        "per_run": per_run,
        "rate_sps": int(rate_sps),
        "signature": signature,
        "metrics": metrics,
    }


def _representative_run(scope_cfg: ScopeComparisonConfig, rate_sps: int, run_ids: list[int]) -> int:
    path = (
        scope_cfg.output_root
        / f"{rate_sps}Sps"
        / "validation"
        / "representative_selection.json"
    )
    if path.is_file():
        try:
            selected = int(read_json(path)["selected_run"])
            if selected in run_ids:
                return selected
        except Exception:
            pass
    return int(run_ids[len(run_ids) // 2])


def _cross_workload_psd_for_workload(
    cfg: MultiWorkloadConfig,
    spec: WorkloadSpec,
    scope_cfg: ScopeComparisonConfig,
    pairs: Sequence[tuple[int, Path, Path]],
    *,
    force: bool,
) -> dict[str, Any]:
    output = cfg.output_root / "psd" / "per_workload" / spec.workload_id
    output.mkdir(parents=True, exist_ok=True)
    npz_path = output / "cross_workload_psd_summary.npz"
    metrics_path = output / "psd_metrics.json"
    bands_path = output / "frequency_bands.csv"
    peaks_path = output / "dominant_peaks.csv"
    idle_load_bands_path = output / "idle_load_frequency_bands.csv"
    idle_load_peaks_path = output / "idle_load_peak_classification.csv"
    idle_load_summary_path = output / "idle_load_summary.json"

    rate = cfg.psd.comparison_rate_sps
    idle = _idle_psd_at_common_rate(cfg, scope_cfg, rate)
    if idle is None:
        raise WorkloadUnavailable(
            f"No exact-rate external idle pairs at {human_rate(rate)}"
        )
    idle_arrays = idle["arrays"]
    signature = stable_hash(
        {
            "schema": _MULTI_WORKLOAD_SCHEMA_VERSION,
            "workload": asdict(spec),
            "scope_config": normalise_for_json(scope_cfg),
            "pairs": [
                _source_identity_for_workload(scope_cfg, run, tek, pico)
                for run, tek, pico in pairs
            ],
            "idle_signature": idle.get("signature", ""),
            "psd": asdict(cfg.psd),
        }
    )
    if not force and npz_path.is_file() and metrics_path.is_file():
        payload = read_json(metrics_path)
        if payload.get("signature") == signature:
            return payload
    active_current: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        "tek": [], "pico": []
    }
    active_power: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        "tek": [], "pico": []
    }
    per_run_metrics: list[dict[str, Any]] = []
    representative_data: dict[str, np.ndarray] | None = None
    representative = _representative_run(
        scope_cfg, rate, [int(pair[0]) for pair in pairs]
    )

    for run, tek_path, pico_path in pairs:
        row: dict[str, Any] = {"run": int(run)}
        for source, source_path, column in (
            ("tek", tek_path, scope_cfg.tek.column),
            ("pico", pico_path, scope_cfg.pico.column),
        ):
            raw, _ = _read_parquet_column(source_path, column)
            current, power = _current_and_power(
                scope_cfg,
                source,
                raw,
                apply_workload_zero=True,
            )
            f_current, p_current, meta = _psd_for_signal(current, rate)
            f_power, p_power, _ = _psd_for_signal(power, rate)
            active_current[source].append((f_current, p_current))
            active_power[source].append((f_power, p_power))
            idle_f_current = idle_arrays[f"{source}_current_frequencies_hz"]
            idle_p_current = idle_arrays[f"{source}_current_idle_psd_a2_per_hz"]
            idle_current_interp = np.interp(f_current, idle_f_current, idle_p_current)
            excess_current = np.maximum(p_current - idle_current_interp, 0.0)
            idle_f_power = idle_arrays[f"{source}_power_frequencies_hz"]
            idle_p_power = idle_arrays[f"{source}_power_idle_psd_w2_per_hz"]
            idle_power_interp = np.interp(f_power, idle_f_power, idle_p_power)
            excess_power = np.maximum(p_power - idle_power_interp, 0.0)
            for signal, frequencies, density in (
                ("current", f_current, excess_current),
                ("power", f_power, excess_power),
            ):
                cumulative = _density_cumulative(frequencies, density)
                for fraction in cfg.psd.cumulative_percentiles:
                    label = int(round(100 * fraction))
                    row[f"{source}_{signal}_f{label}_hz"] = _frequency_at_fraction(
                        frequencies, cumulative, fraction
                    )
                row[f"{source}_{signal}_integral"] = float(
                    trapezoid(density, frequencies)
                )
                row[f"{source}_{signal}_centroid_hz"] = _spectral_centroid(
                    frequencies, density
                )
                row[f"{source}_{signal}_entropy"] = _spectral_entropy(
                    frequencies, density
                )
            row[f"{source}_welch_segments"] = meta["welch_segments"]
            if int(run) == representative:
                analysis_rate = min(rate, 250_000)
                if rate != analysis_rate:
                    current_spec = np.asarray(
                        soxr.resample(current, rate, analysis_rate, quality="VHQ"),
                        dtype=np.float64,
                    )
                else:
                    current_spec = current
                if source == "tek":
                    representative_data = {
                        "current": current_spec,
                        "rate_sps": np.asarray([analysis_rate]),
                        "run": np.asarray([run]),
                    }
            del raw, current, power
            gc.collect()
        per_run_metrics.append(row)
        gc.collect()

    arrays: dict[str, np.ndarray] = {}
    aggregate_metrics: dict[str, Any] = {
        "signature": signature,
        "schema_version": _MULTI_WORKLOAD_SCHEMA_VERSION,
        "workload_id": spec.workload_id,
        "workload_label": spec.label,
        "comparison_rate_sps": rate,
        "valid_pairs": len(pairs),
        "external_idle_pairs": int(idle["valid_pairs"]),
        "external_idle_record_policy": str(
            idle.get("metrics", {}).get(
                "record_policy", cfg.psd.idle_record_policy
            )
        ),
        "external_idle_total_duration_s": _finite(
            idle.get("metrics", {}).get("total_physical_idle_duration_s")
        ),
        "external_idle_median_duration_s": _finite(
            idle.get("metrics", {}).get("median_idle_duration_s")
        ),
        "external_idle_total_welch_segments": int(
            _finite(idle.get("metrics", {}).get("total_welch_segments"), 0.0)
        ),
        "external_idle_median_welch_segments_per_run": _finite(
            idle.get("metrics", {}).get("median_welch_segments_per_run")
        ),
        "representative_run": representative,
        "psd_basis": "active_minus_external_rate_matched_idle",
        "metric_basis": "median_of_per_run_metrics; pointwise_median_psd_for_curves",
        "frequency_axis_unit": "Hz",
        "frequency_axis_definition": "cycles_per_second_from_scipy_signal_welch_fs",
        "angular_frequency_conversion_applied": False,
        "per_run_metrics": per_run_metrics,
    }
    band_rows: list[dict[str, Any]] = []
    peak_rows: list[dict[str, Any]] = []
    idle_load_band_rows: list[dict[str, Any]] = []
    idle_load_peak_rows: list[dict[str, Any]] = []
    idle_load_summary_rows: list[dict[str, Any]] = []

    for source in ("tek", "pico"):
        f_current, active_current_median = _median_on_grid(active_current[source])
        idle_current = np.interp(
            f_current,
            idle_arrays[f"{source}_current_frequencies_hz"],
            idle_arrays[f"{source}_current_idle_psd_a2_per_hz"],
        )
        excess_current = np.maximum(active_current_median - idle_current, 0.0)
        cumulative_current = _density_cumulative(f_current, excess_current)

        f_power, active_power_median = _median_on_grid(active_power[source])
        idle_power = np.interp(
            f_power,
            idle_arrays[f"{source}_power_frequencies_hz"],
            idle_arrays[f"{source}_power_idle_psd_w2_per_hz"],
        )
        excess_power = np.maximum(active_power_median - idle_power, 0.0)
        cumulative_power = _density_cumulative(f_power, excess_power)

        arrays[f"{source}_current_frequencies_hz"] = f_current
        arrays[f"{source}_current_active_psd_a2_per_hz"] = active_current_median
        arrays[f"{source}_current_idle_psd_a2_per_hz"] = idle_current
        arrays[f"{source}_current_excess_psd_a2_per_hz"] = excess_current
        arrays[f"{source}_current_cumulative"] = cumulative_current
        arrays[f"{source}_power_frequencies_hz"] = f_power
        arrays[f"{source}_power_active_psd_w2_per_hz"] = active_power_median
        arrays[f"{source}_power_idle_psd_w2_per_hz"] = idle_power
        arrays[f"{source}_power_excess_psd_w2_per_hz"] = excess_power
        arrays[f"{source}_power_cumulative"] = cumulative_power

        if cfg.psd.idle_load_comparison_enabled:
            for signal, frequencies, active_density, idle_density, excess_density, unit in (
                (
                    "current",
                    f_current,
                    active_current_median,
                    idle_current,
                    excess_current,
                    "A2/Hz",
                ),
                (
                    "power",
                    f_power,
                    active_power_median,
                    idle_power,
                    excess_power,
                    "W2/Hz",
                ),
            ):
                overlap_density = np.minimum(active_density, idle_density)
                arrays[
                    f"{source}_{signal}_idle_overlap_psd_{'a2' if signal == 'current' else 'w2'}_per_hz"
                ] = overlap_density
                active_integral = float(trapezoid(active_density, frequencies))
                idle_integral = float(trapezoid(idle_density, frequencies))
                overlap_integral = float(trapezoid(overlap_density, frequencies))
                excess_integral = float(trapezoid(excess_density, frequencies))
                active_to_idle_db = _safe_ratio_db(active_integral, idle_integral)
                idle_load_summary_rows.append(
                    {
                        "workload_id": spec.workload_id,
                        "workload_label": spec.label,
                        "source": source,
                        "signal": signal,
                        "comparison_rate_sps": rate,
                        "active_integral": active_integral,
                        "idle_integral": idle_integral,
                        "idle_overlap_integral": overlap_integral,
                        "load_additional_integral": excess_integral,
                        "active_to_idle_ratio_db": active_to_idle_db,
                        "idle_overlap_of_active_fraction": (
                            overlap_integral / active_integral
                            if active_integral > 0
                            else float("nan")
                        ),
                        "idle_overlap_of_active_percent": (
                            100.0 * overlap_integral / active_integral
                            if active_integral > 0
                            else float("nan")
                        ),
                        "load_additional_of_active_fraction": (
                            excess_integral / active_integral
                            if active_integral > 0
                            else float("nan")
                        ),
                        "load_additional_of_active_percent": (
                            100.0 * excess_integral / active_integral
                            if active_integral > 0
                            else float("nan")
                        ),
                        "external_idle_pairs": int(idle["valid_pairs"]),
                        "external_idle_total_duration_s": _finite(
                            idle.get("metrics", {}).get(
                                "total_physical_idle_duration_s"
                            )
                        ),
                        "external_idle_median_duration_s": _finite(
                            idle.get("metrics", {}).get("median_idle_duration_s")
                        ),
                        "external_idle_total_welch_segments": int(
                            _finite(
                                idle.get("metrics", {}).get(
                                    "total_welch_segments"
                                ),
                                0.0,
                            )
                        ),
                        "idle_record_policy": cfg.psd.idle_record_policy,
                        "density_unit": unit,
                        "interpretation": (
                            "Descriptive spectral decomposition: min(active,idle) "
                            "is the idle-overlapping component and max(active-idle,0) "
                            "is additional variance observed under load. This is not "
                            "a phase-coherent causal source separation."
                        ),
                    }
                )
                for band_label, low, high in cfg.psd.bands:
                    active_band = _density_integral_band(
                        frequencies, active_density, low, high
                    )
                    idle_band = _density_integral_band(
                        frequencies, idle_density, low, high
                    )
                    overlap_band = _density_integral_band(
                        frequencies, overlap_density, low, high
                    )
                    excess_band = _density_integral_band(
                        frequencies, excess_density, low, high
                    )
                    idle_load_band_rows.append(
                        {
                            "workload_id": spec.workload_id,
                            "workload_label": spec.label,
                            "source": source,
                            "signal": signal,
                            "band": band_label,
                            "band_low_hz": low,
                            "band_high_hz": high,
                            "active_integral": active_band,
                            "idle_integral": idle_band,
                            "idle_overlap_integral": overlap_band,
                            "load_additional_integral": excess_band,
                            "active_to_idle_ratio_db": _safe_ratio_db(
                                active_band, idle_band
                            ),
                            "idle_overlap_of_active_percent": (
                                100.0 * overlap_band / active_band
                                if active_band > 0
                                else float("nan")
                            ),
                            "load_additional_of_active_percent": (
                                100.0 * excess_band / active_band
                                if active_band > 0
                                else float("nan")
                            ),
                            "active_share_of_total_percent": (
                                100.0 * active_band / active_integral
                                if active_integral > 0
                                else float("nan")
                            ),
                            "idle_share_of_total_percent": (
                                100.0 * idle_band / idle_integral
                                if idle_integral > 0
                                else float("nan")
                            ),
                        }
                    )

                if signal == "current":
                    excess_peaks = _dominant_peaks(
                        frequencies,
                        excess_density,
                        cfg.psd.dominant_peak_count,
                        cfg.psd.minimum_peak_frequency_hz,
                        min(
                            cfg.psd.maximum_peak_frequency_hz,
                            float(frequencies[-1]),
                        ),
                    )
                    idle_peaks = _dominant_peaks(
                        frequencies,
                        idle_density,
                        max(cfg.psd.dominant_peak_count * 3, 12),
                        cfg.psd.minimum_peak_frequency_hz,
                        min(
                            cfg.psd.maximum_peak_frequency_hz,
                            float(frequencies[-1]),
                        ),
                    )
                    idle_peak_frequencies = np.asarray(
                        [peak["frequency_hz"] for peak in idle_peaks],
                        dtype=np.float64,
                    )
                    resolution_hz = (
                        float(np.median(np.diff(frequencies)))
                        if frequencies.size > 1
                        else float("nan")
                    )
                    match_tolerance_hz = (
                        cfg.psd.idle_peak_match_bins * resolution_hz
                        if math.isfinite(resolution_hz)
                        else float("nan")
                    )
                    for rank, peak in enumerate(excess_peaks, start=1):
                        peak_frequency = float(peak["frequency_hz"])
                        active_at_peak = float(
                            np.interp(peak_frequency, frequencies, active_density)
                        )
                        idle_at_peak = float(
                            np.interp(peak_frequency, frequencies, idle_density)
                        )
                        local_half_width_hz = (
                            match_tolerance_hz
                            if math.isfinite(match_tolerance_hz) and match_tolerance_hz > 0
                            else max(1.0, 0.005 * peak_frequency)
                        )
                        local_active_integral = _integral_with_interpolated_edges(
                            frequencies,
                            active_density,
                            max(float(frequencies[0]), peak_frequency - local_half_width_hz),
                            min(float(frequencies[-1]), peak_frequency + local_half_width_hz),
                        )
                        local_idle_integral = _integral_with_interpolated_edges(
                            frequencies,
                            idle_density,
                            max(float(frequencies[0]), peak_frequency - local_half_width_hz),
                            min(float(frequencies[-1]), peak_frequency + local_half_width_hz),
                        )
                        ratio_db = _safe_ratio_db(
                            local_active_integral, local_idle_integral
                        )
                        if idle_peak_frequencies.size:
                            nearest_index = int(
                                np.argmin(np.abs(idle_peak_frequencies - peak_frequency))
                            )
                            nearest_idle_peak_hz = float(
                                idle_peak_frequencies[nearest_index]
                            )
                            idle_peak_delta_hz = abs(
                                nearest_idle_peak_hz - peak_frequency
                            )
                            idle_peak_matched = bool(
                                math.isfinite(match_tolerance_hz)
                                and idle_peak_delta_hz <= match_tolerance_hz
                            )
                        else:
                            nearest_idle_peak_hz = float("nan")
                            idle_peak_delta_hz = float("nan")
                            idle_peak_matched = False
                        idle_load_peak_rows.append(
                            {
                                "workload_id": spec.workload_id,
                                "workload_label": spec.label,
                                "source": source,
                                "signal": signal,
                                "rank": rank,
                                "load_peak_frequency_hz": peak_frequency,
                                "load_peak_relative_db": peak["relative_db"],
                                "load_peak_prominence_db": peak["prominence_db"],
                                "active_psd_at_peak": active_at_peak,
                                "idle_psd_at_peak": idle_at_peak,
                                "local_ratio_half_width_hz": local_half_width_hz,
                                "local_active_integral": local_active_integral,
                                "local_idle_integral": local_idle_integral,
                                "active_to_idle_ratio_db": ratio_db,
                                "nearest_idle_peak_hz": nearest_idle_peak_hz,
                                "idle_peak_delta_hz": idle_peak_delta_hz,
                                "idle_peak_match_tolerance_hz": match_tolerance_hz,
                                "idle_peak_matched": idle_peak_matched,
                                "classification": _classify_idle_load_peak(
                                    active_to_idle_db=ratio_db,
                                    idle_peak_matched=idle_peak_matched,
                                    amplification_threshold_db=(
                                        cfg.psd.idle_load_amplification_threshold_db
                                    ),
                                    load_only_threshold_db=(
                                        cfg.psd.idle_load_only_threshold_db
                                    ),
                                ),
                                "interpretation": (
                                    "Diagnostic only. A matched idle line indicates "
                                    "spectral proximity, not phase coherence or causal identity."
                                ),
                            }
                        )

        for signal, frequencies, density, cumulative in (
            ("current", f_current, excess_current, cumulative_current),
            ("power", f_power, excess_power, cumulative_power),
        ):
            per_rows = per_run_metrics
            for fraction in cfg.psd.cumulative_percentiles:
                label = int(round(100 * fraction))
                values = np.asarray(
                    [
                        _finite(row.get(f"{source}_{signal}_f{label}_hz"))
                        for row in per_rows
                    ],
                    dtype=np.float64,
                )
                values = values[np.isfinite(values)]
                aggregate_metrics[f"{source}_{signal}_f{label}_hz_median"] = (
                    float(np.median(values)) if values.size else float("nan")
                )
                aggregate_metrics[f"{source}_{signal}_f{label}_hz_q05"] = quantile(
                    values, 0.05
                )
                aggregate_metrics[f"{source}_{signal}_f{label}_hz_q95"] = quantile(
                    values, 0.95
                )
                aggregate_metrics[
                    f"{source}_{signal}_aggregate_psd_f{label}_hz"
                ] = _frequency_at_fraction(frequencies, cumulative, fraction)
            aggregate_metrics[f"{source}_{signal}_centroid_hz"] = _spectral_centroid(
                frequencies, density
            )
            aggregate_metrics[f"{source}_{signal}_entropy"] = _spectral_entropy(
                frequencies, density
            )
            aggregate_metrics[f"{source}_{signal}_integral"] = float(
                trapezoid(density, frequencies)
            )
            aggregate_metrics[
                f"{source}_{signal}_variance_above_77khz"
            ] = 1.0 - _density_fraction(frequencies, density, 0.0, 77_000.0)
            aggregate_metrics[
                f"{source}_{signal}_variance_above_common_nyquist"
            ] = 1.0 - _density_fraction(
                frequencies, density, 0.0, cfg.psd.comparison_rate_sps / 2.0
            )
            for band_label, low, high in cfg.psd.bands:
                fraction = _density_fraction(frequencies, density, low, high)
                band_rows.append(
                    {
                        "workload_id": spec.workload_id,
                        "workload_label": spec.label,
                        "source": source,
                        "signal": signal,
                        "band": band_label,
                        "band_low_hz": low,
                        "band_high_hz": high,
                        "variance_fraction": fraction,
                        "variance_percent": 100.0 * fraction,
                    }
                )
            peaks = _dominant_peaks(
                frequencies,
                density,
                cfg.psd.dominant_peak_count,
                cfg.psd.minimum_peak_frequency_hz,
                min(cfg.psd.maximum_peak_frequency_hz, float(frequencies[-1])),
            )
            for rank, peak in enumerate(peaks, start=1):
                peak_rows.append(
                    {
                        "workload_id": spec.workload_id,
                        "workload_label": spec.label,
                        "source": source,
                        "signal": signal,
                        "rank": rank,
                        **peak,
                    }
                )

    if cfg.psd.idle_load_comparison_enabled:
        aggregate_metrics["idle_load_summary"] = idle_load_summary_rows
        aggregate_metrics["idle_load_peak_classification_count"] = len(
            idle_load_peak_rows
        )
        write_csv(idle_load_bands_path, idle_load_band_rows)
        write_csv(idle_load_peaks_path, idle_load_peak_rows)
        write_json(
            idle_load_summary_path,
            {
                "signature": signature,
                "schema_version": _MULTI_WORKLOAD_SCHEMA_VERSION,
                "workload_id": spec.workload_id,
                "workload_label": spec.label,
                "comparison_rate_sps": rate,
                "idle_record_policy": cfg.psd.idle_record_policy,
                "external_idle_metrics": idle.get("metrics", {}),
                "summary": idle_load_summary_rows,
                "interpretation": (
                    "The active PSD is decomposed descriptively into min(active,idle) "
                    "and max(active-idle,0). The decomposition uses independent records "
                    "and therefore does not establish phase-coherent or causal source identity."
                ),
            },
        )

    np.savez_compressed(npz_path, **arrays)
    write_csv(bands_path, band_rows)
    write_csv(peaks_path, peak_rows)
    write_json(metrics_path, aggregate_metrics)

    if cfg.psd.spectrogram_enabled and representative_data is not None:
        current = representative_data["current"]
        rate_spec = float(representative_data["rate_sps"][0])
        nperseg = min(8192, max(256, int(round(0.02 * rate_spec))))
        if nperseg < current.size:
            frequencies, times, density = spectrogram(
                current,
                fs=rate_spec,
                window="hann",
                nperseg=nperseg,
                noverlap=nperseg // 2,
                detrend="constant",
                scaling="density",
                mode="psd",
            )
            np.savez_compressed(
                output / "representative_current_spectrogram.npz",
                frequencies_hz=frequencies,
                times_s=times,
                density_a2_per_hz=density,
                run=representative_data["run"],
                rate_sps=representative_data["rate_sps"],
            )
    return aggregate_metrics


def _window_starts(
    duration_s: float,
    total_duration_s: float,
    count: int,
    margin_s: float,
    rate_sps: float,
) -> np.ndarray:
    duration_s = float(duration_s)
    total_duration_s = float(total_duration_s)
    if duration_s > total_duration_s + 1.5 / rate_sps:
        return np.empty(0, dtype=np.float64)
    if duration_s >= total_duration_s - 1.5 / rate_sps:
        return np.asarray([0.0], dtype=np.float64)
    maximum_margin = max(0.0, 0.5 * (total_duration_s - duration_s))
    margin = min(max(0.0, margin_s), maximum_margin)
    first = margin
    last = total_duration_s - duration_s - margin
    if last < first:
        first = 0.0
        last = total_duration_s - duration_s
    if count <= 1 or last <= first:
        return np.asarray([0.5 * (first + last)], dtype=np.float64)
    starts = np.linspace(first, last, int(count), dtype=np.float64)
    indices = np.rint(starts * rate_sps).astype(np.int64)
    return np.unique(indices).astype(np.float64) / rate_sps


def _common_reference_run(
    cfg: MultiWorkloadConfig,
    template_cfg: Any,
    spec: WorkloadSpec,
    source: str,
    run: int,
    values: np.ndarray,
) -> list[dict[str, Any]]:
    source_rate = cfg.common_reference.analysis_rate_sps
    values = np.asarray(values, dtype=np.float64)
    # A record with N samples at fs represents the nominal interval [0, N/fs).
    # Append one endpoint sample for the reference integral and add constant
    # guards around the resampling source.  The guards are never reported as
    # workload data; they only prevent FIR/phase grids from losing the first or
    # last physical interval when the GPIO trigger is at record start.
    total_duration = values.size / source_rate
    reference_values = np.concatenate((values, values[-1:]))
    reference_integral = UniformLinearIntegral(
        reference_values,
        sample_rate_sps=source_rate,
        first_sample_time_s=0.0,
    )
    guard_samples = max(1, int(round(cfg.common_reference.guard_seconds * source_rate)))
    padded_values = np.pad(values, (guard_samples, guard_samples), mode="edge")
    segment_start_s = -guard_samples / source_rate
    reference: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for duration in cfg.common_reference.window_durations_s:
        starts = _window_starts(
            duration,
            total_duration,
            cfg.common_reference.windows_per_duration,
            cfg.common_reference.edge_margin_s,
            source_rate,
        )
        if starts.size == 0:
            continue
        stops = np.minimum(starts + duration, total_duration)
        energies = np.asarray(
            [
                reference_integral.integrate(float(start), float(stop))
                for start, stop in zip(starts, stops)
            ],
            dtype=np.float64,
        )
        reference[float(duration)] = (starts, energies)

    rows: list[dict[str, Any]] = []
    for target_rate in cfg.common_reference.target_rates_sps:
        if target_rate > source_rate:
            continue
        requested = phase_count_for_target(template_cfg, target_rate)
        phases = max(1, min(int(requested), source_rate // int(target_rate)))
        if target_rate * phases > source_rate:
            continue
        for mode in cfg.common_reference.reconstruction_modes:
            if mode == "anti_alias":
                grid, grid_rate, filter_meta = resample_phase_grid(
                    padded_values,
                    source_rate,
                    target_rate,
                    phases,
                    template_cfg,
                )
            else:
                grid, grid_rate, filter_meta = phase_only_grid(
                    padded_values,
                    source_rate,
                    target_rate,
                    phases,
                )
            if grid_rate != target_rate * phases:
                raise AssertionError("Unexpected phase-grid rate")
            by_duration: dict[float, list[np.ndarray]] = {
                duration: [] for duration in reference
            }
            for phase in range(phases):
                phase_values = np.asarray(grid[phase::phases], dtype=np.float64)
                phase_first_time = segment_start_s + phase / grid_rate
                integral = UniformLinearIntegral(
                    phase_values,
                    sample_rate_sps=target_rate,
                    first_sample_time_s=phase_first_time,
                )
                for duration, (starts, reference_energies) in reference.items():
                    if duration * target_rate < cfg.common_reference.minimum_samples_per_window:
                        continue
                    stops = np.minimum(starts + duration, total_duration)
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
                del integral
            for duration, chunks in by_duration.items():
                if not chunks:
                    continue
                errors = np.concatenate(chunks)
                errors = errors[np.isfinite(errors)]
                if errors.size == 0:
                    continue
                absolute = np.abs(errors)
                rows.append(
                    {
                        "workload_id": spec.workload_id,
                        "workload_label": spec.label,
                        "source": source,
                        "run": int(run),
                        "mode": mode,
                        "target_rate_sps": int(target_rate),
                        "duration_s": float(duration),
                        "phase_count": int(phases),
                        "window_count": int(len(reference[duration][0])),
                        "observation_count": int(errors.size),
                        "error_pct_median": float(np.median(errors)),
                        "error_pct_q05": quantile(errors, 0.05),
                        "error_pct_q95": quantile(errors, 0.95),
                        "abs_error_pct_median": float(np.median(absolute)),
                        "abs_error_pct_q95": quantile(absolute, 0.95),
                        "abs_error_pct_max": float(np.max(absolute)),
                        "filter": str(filter_meta.get("filter", "")),
                    }
                )
            del grid
            gc.collect()
    del reference_integral, reference_values, padded_values
    return rows


def _summarise_common_reference(
    cfg: MultiWorkloadConfig,
    per_run_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str, int, float], list[dict[str, Any]]] = {}
    for row in per_run_rows:
        key = (
            str(row["workload_id"]),
            str(row["source"]),
            str(row["mode"]),
            int(row["target_rate_sps"]),
            float(row["duration_s"]),
        )
        groups.setdefault(key, []).append(row)
    summary: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        workload_id, source, mode, target_rate, duration = key
        run_q95 = np.asarray(
            [_finite(row["abs_error_pct_q95"]) for row in rows],
            dtype=np.float64,
        )
        run_q95 = run_q95[np.isfinite(run_q95)]
        run_median = np.asarray(
            [_finite(row["abs_error_pct_median"]) for row in rows],
            dtype=np.float64,
        )
        run_median = run_median[np.isfinite(run_median)]
        summary.append(
            {
                "workload_id": workload_id,
                "workload_label": str(rows[0]["workload_label"]),
                "source": source,
                "mode": mode,
                "target_rate_sps": target_rate,
                "duration_s": duration,
                "physical_run_count": int(run_q95.size),
                "hierarchical_abs_error_q95_pct": quantile(run_q95, 0.95),
                "run_abs_error_q95_median_pct": (
                    float(np.median(run_q95)) if run_q95.size else float("nan")
                ),
                "run_abs_error_q95_q05_pct": quantile(run_q95, 0.05),
                "run_abs_error_q95_q95_pct": quantile(run_q95, 0.95),
                "run_abs_error_median_median_pct": (
                    float(np.median(run_median)) if run_median.size else float("nan")
                ),
            }
        )

    by_wsd: dict[tuple[str, str, str, float], list[dict[str, Any]]] = {}
    for row in summary:
        by_wsd.setdefault(
            (
                str(row["workload_id"]),
                str(row["source"]),
                str(row["mode"]),
                float(row["duration_s"]),
            ),
            [],
        ).append(row)
    fmin_rows: list[dict[str, Any]] = []
    for key, rows in sorted(by_wsd.items()):
        rows = sorted(rows, key=lambda item: int(item["target_rate_sps"]))
        workload_id, source, mode, duration = key
        for threshold in cfg.common_reference.thresholds_pct:
            selected: int | None = None
            for index, candidate in enumerate(rows):
                suffix = rows[index:]
                values = [
                    _finite(item["hierarchical_abs_error_q95_pct"])
                    for item in suffix
                ]
                if values and all(
                    math.isfinite(value) and value <= threshold for value in values
                ):
                    selected = int(candidate["target_rate_sps"])
                    break
            fmin_rows.append(
                {
                    "workload_id": workload_id,
                    "workload_label": str(rows[0]["workload_label"]),
                    "source": source,
                    "mode": mode,
                    "duration_s": duration,
                    "threshold_pct": float(threshold),
                    "f_min_sps": selected,
                    "selection_rule": "lowest tested rate for which the candidate and every higher tested rate pass",
                }
            )

    highlighted = [
        row
        for row in summary
        if int(row["target_rate_sps"])
        == cfg.common_reference.highlighted_rate_sps
    ]
    highlighted_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in highlighted:
        highlighted_by_key.setdefault(
            (str(row["workload_id"]), str(row["source"]), str(row["mode"])),
            [],
        ).append(row)
    threshold_rows: list[dict[str, Any]] = []
    for key, rows in sorted(highlighted_by_key.items()):
        rows = sorted(rows, key=lambda item: float(item["duration_s"]))
        workload_id, source, mode = key
        for threshold in cfg.common_reference.thresholds_pct:
            selected: float | None = None
            for index, candidate in enumerate(rows):
                suffix = rows[index:]
                values = [
                    _finite(item["hierarchical_abs_error_q95_pct"])
                    for item in suffix
                ]
                if values and all(
                    math.isfinite(value) and value <= threshold for value in values
                ):
                    selected = float(candidate["duration_s"])
                    break
            threshold_rows.append(
                {
                    "workload_id": workload_id,
                    "workload_label": str(rows[0]["workload_label"]),
                    "source": source,
                    "mode": mode,
                    "highlighted_rate_sps": cfg.common_reference.highlighted_rate_sps,
                    "threshold_pct": float(threshold),
                    "minimum_passing_duration_s": selected,
                    "selection_rule": "shortest tested duration for which that duration and every longer tested duration pass",
                }
            )

    worst_groups: dict[tuple[str, str, float, float], list[dict[str, Any]]] = {}
    for row in fmin_rows:
        key = (
            str(row["source"]),
            str(row["mode"]),
            float(row["duration_s"]),
            float(row["threshold_pct"]),
        )
        worst_groups.setdefault(key, []).append(row)
    worst_rows: list[dict[str, Any]] = []
    expected_workloads = sorted(
        {str(row["workload_id"]) for row in summary}
    )
    for key, rows in sorted(worst_groups.items()):
        finite = [
            int(row["f_min_sps"])
            for row in rows
            if row.get("f_min_sps") not in (None, "")
        ]
        worst_rows.append(
            {
                "source": key[0],
                "mode": key[1],
                "duration_s": key[2],
                "threshold_pct": key[3],
                "worst_case_f_min_sps": max(finite) if finite else None,
                "contributing_workloads": len(rows),
                "expected_workloads": len(expected_workloads),
                "complete_across_available_workloads": len(rows) == len(expected_workloads),
                "limiting_workloads": ",".join(
                    sorted(
                        str(row["workload_id"])
                        for row in rows
                        if row.get("f_min_sps") not in (None, "")
                        and finite
                        and int(row["f_min_sps"]) == max(finite)
                    )
                ),
            }
        )
    return summary, fmin_rows, threshold_rows, worst_rows


def _run_common_reference_workload(
    cfg: MultiWorkloadConfig,
    template_cfg: Any,
    spec: WorkloadSpec,
    scope_cfg: ScopeComparisonConfig,
    pairs: Sequence[tuple[int, Path, Path]],
    *,
    force: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    qc_rows: list[dict[str, Any]] = []
    for run, tek_path, pico_path in pairs:
        arrays, cache_meta = _load_or_build_power_cache(
            cfg,
            template_cfg,
            spec,
            scope_cfg,
            int(run),
            tek_path,
            pico_path,
            force=force,
        )
        for source, values in arrays.items():
            rows.extend(
                _common_reference_run(
                    cfg, template_cfg, spec, source, int(run), values
                )
            )
            source_meta = cache_meta["sources"][source]
            qc_rows.append(
                {
                    "workload_id": spec.workload_id,
                    "workload_label": spec.label,
                    "source": source,
                    "run": int(run),
                    "input_rate_sps": source_meta["input_rate_sps"],
                    "output_rate_sps": source_meta["output_rate_sps"],
                    "input_energy_j": source_meta["input_energy_j"],
                    "output_energy_j": source_meta["output_energy_j"],
                    "energy_qc_error_pct": source_meta["energy_qc_error_pct"],
                    "cache_signature": cache_meta["signature"],
                }
            )
        arrays.clear()
        gc.collect()
    return rows, qc_rows


def _nearest_common_row(
    rows: Sequence[dict[str, Any]],
    workload_id: str,
    source: str,
    rate_sps: float,
    duration_s: float,
    mode: str = "phase_only",
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row["workload_id"] == workload_id
        and row["source"] == source
        and row["mode"] == mode
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (
            abs(math.log(max(1.0, float(row["target_rate_sps"])) / max(1.0, rate_sps))),
            abs(float(row["duration_s"]) - duration_s),
        ),
    )


def _direct_rate_validation(
    cfg: MultiWorkloadConfig,
    workload_contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    common_summary: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not cfg.direct_validation.enabled:
        return []
    output: list[dict[str, Any]] = []
    for spec, scope_cfg in workload_contexts:
        path = scope_cfg.output_root / "cross_rate_summary.csv"
        if not path.is_file():
            continue
        rows = _read_csv(path)
        by_rate = {
            int(round(_finite(row.get("tek_rate_sps")))): row
            for row in rows
            if math.isfinite(_finite(row.get("tek_rate_sps")))
        }
        reference = by_rate.get(cfg.common_reference.source_rate_sps)
        if reference is None:
            continue
        for source in cfg.common_reference.sources:
            energy_prefix = f"{source}_estimated_energy_j_median"
            duration_prefix = f"{source}_nominal_duration_s_median"
            if source == "pico":
                energy_prefix = "pico_estimated_energy_j_median"
                duration_prefix = "pico_nominal_duration_s_median"
            else:
                energy_prefix = "tek_estimated_energy_j_median"
                duration_prefix = "tek_nominal_duration_s_median"
            ref_energy = _finite(reference.get(energy_prefix))
            ref_duration = _finite(reference.get(duration_prefix))
            if not math.isfinite(ref_energy) or ref_duration <= 0:
                continue
            ref_power = ref_energy / ref_duration
            for rate, row in sorted(by_rate.items()):
                if rate > cfg.direct_validation.maximum_rate_sps:
                    continue
                energy = _finite(row.get(energy_prefix))
                duration = _finite(row.get(duration_prefix))
                if not math.isfinite(energy) or duration <= 0:
                    continue
                power = energy / duration
                observed = 100.0 * (power - ref_power) / ref_power if ref_power else float("nan")
                predicted = _nearest_common_row(
                    common_summary,
                    spec.workload_id,
                    source,
                    rate,
                    duration,
                )
                output.append(
                    {
                        "workload_id": spec.workload_id,
                        "workload_label": spec.label,
                        "source": source,
                        "direct_rate_sps": rate,
                        "direct_duration_s": duration,
                        "direct_median_energy_j": energy,
                        "direct_median_power_w": power,
                        "reference_rate_sps": cfg.common_reference.source_rate_sps,
                        "reference_median_power_w": ref_power,
                        "direct_power_deviation_pct": observed,
                        "common_reference_target_rate_sps": (
                            predicted.get("target_rate_sps") if predicted else None
                        ),
                        "common_reference_duration_s": (
                            predicted.get("duration_s") if predicted else None
                        ),
                        "common_reference_hierarchical_q95_pct": (
                            predicted.get("hierarchical_abs_error_q95_pct")
                            if predicted
                            else None
                        ),
                        "interpretation": (
                            "direct rate is a separate physical execution; deviation includes run-to-run and acquisition effects, whereas the common-reference bound isolates sampling on the same trace"
                        ),
                    }
                )
    return output


def _save_figure(fig: plt.Figure, base: Path, cfg: MultiWorkloadConfig) -> list[Path]:
    outputs: list[Path] = []
    base.parent.mkdir(parents=True, exist_ok=True)
    if cfg.paper.generate_pdf:
        path = base.with_suffix(".pdf")
        fig.savefig(path, bbox_inches="tight")
        outputs.append(path)
    if cfg.paper.generate_png:
        path = base.with_suffix(".png")
        fig.savefig(path, dpi=220, bbox_inches="tight")
        outputs.append(path)
    plt.close(fig)
    return outputs


def _decimate_xy(x: np.ndarray, y: np.ndarray, maximum: int) -> tuple[np.ndarray, np.ndarray]:
    if x.size <= maximum:
        return x, y
    indices = np.linspace(0, x.size - 1, maximum, dtype=np.int64)
    return x[indices], y[indices]


def _compact_number(value: float, maximum_decimals: int = 3) -> str:
    value = float(value)
    rounded = round(value)
    if abs(value - rounded) < 10 ** (-(maximum_decimals + 2)):
        return str(int(rounded))
    return f"{value:.{maximum_decimals}f}".rstrip("0").rstrip(".")


def _human_frequency_tick(value: float, _position: int | None = None) -> str:
    value = float(value)
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{_compact_number(value / 1_000_000)} MHz"
    if absolute >= 1_000:
        return f"{_compact_number(value / 1_000)} kHz"
    return f"{_compact_number(value)} Hz"


def _human_rate_tick(value: float, _position: int | None = None) -> str:
    value = float(value)
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{_compact_number(value / 1_000_000)} MS/s"
    if absolute >= 1_000:
        return f"{_compact_number(value / 1_000)} kS/s"
    return f"{_compact_number(value)} S/s"


def _human_duration_tick(value: float, _position: int | None = None) -> str:
    value = float(value)
    absolute = abs(value)
    if absolute >= 1.0:
        return f"{_compact_number(value)} s"
    if absolute >= 1e-3:
        return f"{_compact_number(value * 1e3)} ms"
    if absolute >= 1e-6:
        return f"{_compact_number(value * 1e6)} µs"
    return f"{_compact_number(value * 1e9)} ns"


def _human_percent_tick(value: float, _position: int | None = None) -> str:
    value = float(value)
    absolute = abs(value)
    if absolute >= 1.0:
        decimals = 0 if abs(value - round(value)) < 1e-9 else 1
    elif absolute >= 0.1:
        decimals = 1
    elif absolute >= 0.01:
        decimals = 2
    elif absolute >= 0.001:
        decimals = 3
    elif absolute >= 0.0001:
        decimals = 4
    else:
        decimals = 6
    formatted = f"{value:.{decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted + "%"


def _apply_frequency_axis(axis: plt.Axes) -> None:
    ticks = [10.0, 100.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0]
    axis.xaxis.set_major_locator(FixedLocator(ticks))
    axis.xaxis.set_major_formatter(FuncFormatter(_human_frequency_tick))
    axis.xaxis.set_minor_formatter(NullFormatter())


def _apply_duration_axis(axis: plt.Axes) -> None:
    ticks = [0.02, 0.1, 0.5, 1.0, 5.0, 10.0]
    axis.xaxis.set_major_locator(FixedLocator(ticks))
    axis.xaxis.set_major_formatter(FuncFormatter(_human_duration_tick))
    axis.xaxis.set_minor_formatter(NullFormatter())
    axis.tick_params(axis="x", labelsize=8)


def _apply_percent_axis(axis: plt.Axes, ticks: Sequence[float]) -> None:
    axis.yaxis.set_major_locator(FixedLocator([float(value) for value in ticks]))
    axis.yaxis.set_major_formatter(FuncFormatter(_human_percent_tick))
    axis.yaxis.set_minor_formatter(NullFormatter())


def _apply_rate_axis(axis: plt.Axes, *, orientation: str) -> None:
    if orientation == "x":
        ticks = [2_500.0, 25_000.0, 100_000.0, 1_000_000.0, 5_000_000.0]
        target = axis.xaxis
    else:
        ticks = [200.0, 500.0, 1_000.0, 2_000.0, 5_000.0, 10_000.0, 50_000.0, 100_000.0, 200_000.0]
        target = axis.yaxis
    target.set_major_locator(FixedLocator(ticks))
    target.set_major_formatter(FuncFormatter(_human_rate_tick))
    target.set_minor_formatter(NullFormatter())


def _source_setup_label(source: str, *, compact: bool = False) -> str:
    if source == "tek":
        return "Tek setup" if compact else "Tektronix setup"
    if source == "pico":
        return "Pico setup" if compact else "PicoScope/INA225 setup"
    return str(source)


def _idle_policy_label(value: Any) -> str:
    policy = str(value)
    if policy == "full_record_per_run_equal_weight":
        return "full record; equal run weight"
    return policy.replace("_", " ")


def _idle_load_classification_label(value: Any) -> str:
    labels = {
        "idle_matched_strongly_load_amplified": "idle line; strongly amplified",
        "idle_matched_load_amplified": "idle line; load-amplified",
        "idle_dominant_at_load_peak": "idle-dominant",
        "idle_matched_similar_level": "idle line; similar level",
        "no_dominant_idle_match_load_only_candidate": "load-only candidate",
        "no_dominant_idle_match_load_enhanced": "load-enhanced; no idle match",
        "no_dominant_idle_match_unresolved": "no idle match; unresolved",
        "unresolved": "unresolved",
    }
    return labels.get(str(value), str(value).replace("_", " "))


def _normalised_density(
    frequencies: np.ndarray,
    density: np.ndarray,
) -> np.ndarray:
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    total = float(trapezoid(density, frequencies)) if frequencies.size > 1 else 0.0
    if not math.isfinite(total) or total <= 0:
        return np.zeros_like(density)
    return density / total


def _log_frequency_variance_density(
    frequencies: np.ndarray,
    density: np.ndarray,
) -> np.ndarray:
    """Return dC/dlog10(f) in percent per frequency decade.

    Welch returns frequency directly in hertz because ``fs`` is supplied in
    samples per second. The DFT kernel already contains the 2*pi phase factor,
    while Welch normalises by sampling frequency and window energy. No
    additional continuous-transform 1/(2*pi) or 1/sqrt(2*pi) factor is used.
    For C(f)=integral_0^f p(nu)dnu, the derivative with
    respect to log10(f) is ln(10)*f*p(f).
    """
    frequencies = np.asarray(frequencies, dtype=np.float64)
    normalised = _normalised_density(frequencies, density)
    result = np.zeros_like(normalised)
    valid = (frequencies > 0) & np.isfinite(normalised)
    result[valid] = 100.0 * math.log(10.0) * frequencies[valid] * normalised[valid]
    return result


def _log_binned_variance_share(
    frequencies: np.ndarray,
    density: np.ndarray,
    *,
    bins_per_decade: int = 24,
) -> tuple[np.ndarray, np.ndarray]:
    """Return workload-related variance share in fixed logarithmic bins.

    The bin width is constant in log10(f).  Dividing the returned shares by
    that width would yield a binned estimate of dC/dlog10(f).  Reporting the
    share itself is easier to read: all bins sum to 100 percent and no local
    density value is mistaken for a percentage fraction.
    """
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    valid = (frequencies > 0) & np.isfinite(frequencies) & np.isfinite(density)
    if np.count_nonzero(valid) < 3:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
    f = frequencies[valid]
    d = density[valid]
    cumulative = _density_cumulative(f, d)
    low = float(f[0])
    high = float(f[-1])
    decades = max(math.log10(high) - math.log10(low), 1e-9)
    bin_count = max(8, int(math.ceil(decades * max(1, int(bins_per_decade)))))
    edges = np.geomspace(low, high, bin_count + 1)
    edge_cumulative = np.interp(edges, f, cumulative)
    fractions_pct = 100.0 * np.maximum(np.diff(edge_cumulative), 0.0)
    centres = np.sqrt(edges[:-1] * edges[1:])
    return centres, fractions_pct



def _integral_with_interpolated_edges(
    frequencies: np.ndarray,
    density: np.ndarray,
    low_hz: float,
    high_hz: float,
) -> float:
    """Integrate a PSD over one band, including interpolated band edges."""
    frequencies = np.asarray(frequencies, dtype=np.float64)
    density = np.maximum(np.asarray(density, dtype=np.float64), 0.0)
    low = max(float(low_hz), float(frequencies[0]))
    high = min(float(high_hz), float(frequencies[-1]))
    if frequencies.size < 2 or not high > low:
        return 0.0
    interior = (frequencies > low) & (frequencies < high)
    x = np.concatenate(
        (
            np.asarray([low], dtype=np.float64),
            frequencies[interior],
            np.asarray([high], dtype=np.float64),
        )
    )
    y = np.concatenate(
        (
            np.asarray([np.interp(low, frequencies, density)], dtype=np.float64),
            density[interior],
            np.asarray([np.interp(high, frequencies, density)], dtype=np.float64),
        )
    )
    return float(trapezoid(y, x))


def _log_binned_active_idle_ratio_rows(
    frequencies: np.ndarray,
    active_density: np.ndarray,
    idle_density: np.ndarray,
    *,
    bins_per_decade: int,
) -> list[dict[str, float]]:
    """Return integrated active/idle variance ratios in equal log-frequency bins.

    Integrating each density inside a bin is more stable than dividing two
    pointwise PSD ordinates, especially where the idle estimate approaches the
    numerical floor.  The result is descriptive because active and idle are
    independent acquisitions.
    """
    frequencies = np.asarray(frequencies, dtype=np.float64)
    active_density = np.maximum(np.asarray(active_density, dtype=np.float64), 0.0)
    idle_density = np.maximum(np.asarray(idle_density, dtype=np.float64), 0.0)
    valid = (
        (frequencies > 0)
        & np.isfinite(frequencies)
        & np.isfinite(active_density)
        & np.isfinite(idle_density)
    )
    if np.count_nonzero(valid) < 3:
        return []
    f = frequencies[valid]
    active = active_density[valid]
    idle = idle_density[valid]
    low = float(f[0])
    high = float(f[-1])
    decades = max(math.log10(high) - math.log10(low), 1e-9)
    bin_count = max(8, int(math.ceil(decades * max(1, int(bins_per_decade)))))
    edges = np.geomspace(low, high, bin_count + 1)
    rows: list[dict[str, float]] = []
    for low_edge, high_edge in zip(edges[:-1], edges[1:]):
        active_integral = _integral_with_interpolated_edges(
            f, active, float(low_edge), float(high_edge)
        )
        idle_integral = _integral_with_interpolated_edges(
            f, idle, float(low_edge), float(high_edge)
        )
        ratio_db = _safe_ratio_db(active_integral, idle_integral)
        rows.append(
            {
                "bin_low_hz": float(low_edge),
                "bin_high_hz": float(high_edge),
                "bin_center_hz": float(math.sqrt(low_edge * high_edge)),
                "active_integral": active_integral,
                "idle_integral": idle_integral,
                "active_to_idle_ratio_db": ratio_db,
            }
        )
    return rows


def _idle_load_log_ratio_rows(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec, _ in contexts:
        path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "cross_workload_psd_summary.npz"
        )
        if not path.is_file():
            continue
        arrays = _load_workload_psd(cfg, spec.workload_id)
        frequencies = np.asarray(arrays["tek_current_frequencies_hz"], dtype=np.float64)
        active = np.asarray(arrays["tek_current_active_psd_a2_per_hz"], dtype=np.float64)
        idle = np.asarray(arrays["tek_current_idle_psd_a2_per_hz"], dtype=np.float64)
        for row in _log_binned_active_idle_ratio_rows(
            frequencies,
            active,
            idle,
            bins_per_decade=cfg.psd.idle_load_ratio_bins_per_decade,
        ):
            rows.append(
                {
                    "workload_id": spec.workload_id,
                    "workload_label": spec.label,
                    "source": "tek",
                    "signal": "current",
                    "comparison_rate_sps": cfg.psd.comparison_rate_sps,
                    "bins_per_decade": cfg.psd.idle_load_ratio_bins_per_decade,
                    **row,
                    "interpretation": (
                        "Integrated active/idle PSD ratio in one equal-width "
                        "log10-frequency bin; active and idle are independent records."
                    ),
                }
            )
    return rows


def _load_workload_psd(cfg: MultiWorkloadConfig, workload_id: str) -> dict[str, np.ndarray]:
    path = (
        cfg.output_root
        / "psd"
        / "per_workload"
        / workload_id
        / "cross_workload_psd_summary.npz"
    )
    return {key: value for key, value in np.load(path).items()}


def _plot_cross_workload_psd(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    signal: str,
) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
    display_floor_db = -140.0
    for spec, _ in contexts:
        path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "cross_workload_psd_summary.npz"
        )
        if not path.is_file():
            continue
        arrays = _load_workload_psd(cfg, spec.workload_id)
        f = arrays[f"tek_{signal}_frequencies_hz"]
        density = arrays[
            f"tek_{signal}_excess_psd_{'a2' if signal == 'current' else 'w2'}_per_hz"
        ]
        cumulative = arrays[f"tek_{signal}_cumulative"]
        total = float(trapezoid(density, f)) if f.size > 1 else 0.0
        normalised = density / total if total > 0 else density
        positive = (f > 0) & np.isfinite(normalised) & (normalised > 0)
        fx, py = _decimate_xy(
            f[positive], normalised[positive], cfg.paper.plot_max_points
        )
        py_db = np.maximum(10.0 * np.log10(py), display_floor_db)
        axes[0].plot(fx, py_db, label=spec.label)
        cx, cy = _decimate_xy(f, cumulative, cfg.paper.plot_max_points)
        axes[1].plot(cx, 100.0 * cy, label=spec.label)
    axes[0].set_xscale("log")
    axes[0].set_ylim(display_floor_db, -10.0)
    axes[0].set_yticks([-140, -120, -100, -80, -60, -40, -20])
    axes[0].set_xlabel("Frequency")
    axes[0].set_ylabel("Normalised PSD [dB re 1/Hz]")
    axes[0].set_title(f"(a) Tektronix {signal} PSD shape at 5 MS/s")
    axes[0].grid(True, which="both", alpha=0.25)
    _apply_frequency_axis(axes[0])

    axes[1].set_xscale("log")
    axes[1].set_ylim(0, 100.5)
    axes[1].set_xlabel("Frequency")
    axes[1].set_ylabel("Cumulative workload-related variance")
    axes[1].set_title("(b) Cumulative spectral distribution")
    axes[1].grid(True, which="both", alpha=0.25)
    axes[1].legend(fontsize=8)
    _apply_frequency_axis(axes[1])
    _apply_percent_axis(axes[1], [0, 20, 40, 60, 80, 100])

    fig.suptitle(
        f"Cross-workload Tektronix {signal} spectra — active minus exact-rate external idle"
    )
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / f"cross_workload_{signal}_psd_paper",
        cfg,
    )


def _plot_log_frequency_variance_density(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> list[Path]:
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    for spec, _ in contexts:
        path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "cross_workload_psd_summary.npz"
        )
        if not path.is_file():
            continue
        arrays = _load_workload_psd(cfg, spec.workload_id)
        frequencies = arrays["tek_current_frequencies_hz"]
        density = arrays["tek_current_excess_psd_a2_per_hz"]
        x, y = _log_binned_variance_share(
            frequencies, density, bins_per_decade=24
        )
        if x.size:
            ax.plot(x, y, label=spec.label)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency")
    ax.set_ylabel("Workload-related variance per log-frequency bin [%]")
    ax.set_title("Log-frequency view of the cumulative-spectrum derivative")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    _apply_frequency_axis(ax)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
    ax.yaxis.set_major_formatter(FuncFormatter(_human_percent_tick))
    ax.yaxis.set_minor_formatter(NullFormatter())
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_log_frequency_variance_share_paper",
        cfg,
    )


def _plot_psd_fine_structure(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> list[Path]:
    windows = list(cfg.psd.fine_structure_windows)
    columns = 2
    rows = int(math.ceil(len(windows) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(10.5, 3.25 * rows), squeeze=False)
    flat_axes = list(axes.ravel())
    panel_letters = "abcdefghijklmnopqrstuvwxyz"
    for panel_index, (label, low_hz, high_hz) in enumerate(windows):
        axis = flat_axes[panel_index]
        for spec, _ in contexts:
            path = (
                cfg.output_root
                / "psd"
                / "per_workload"
                / spec.workload_id
                / "cross_workload_psd_summary.npz"
            )
            if not path.is_file():
                continue
            arrays = _load_workload_psd(cfg, spec.workload_id)
            frequencies = np.asarray(arrays["tek_current_frequencies_hz"], dtype=np.float64)
            density = np.asarray(arrays["tek_current_excess_psd_a2_per_hz"], dtype=np.float64)
            normalised_percent_per_hz = 100.0 * _normalised_density(frequencies, density)
            mask = (
                (frequencies >= float(low_hz))
                & (frequencies <= float(high_hz))
                & np.isfinite(normalised_percent_per_hz)
            )
            if np.count_nonzero(mask) < 2:
                continue
            x, y = _decimate_xy(
                frequencies[mask],
                normalised_percent_per_hz[mask],
                cfg.paper.plot_max_points,
            )
            line = axis.plot(x, y, label=spec.label)[0]
            peak_path = (
                cfg.output_root
                / "psd"
                / "per_workload"
                / spec.workload_id
                / "dominant_peaks.csv"
            )
            if peak_path.is_file():
                for peak in _read_csv(peak_path):
                    if peak.get("source") != "tek" or peak.get("signal") != "current":
                        continue
                    peak_frequency = _finite(peak.get("frequency_hz"))
                    if not (float(low_hz) <= peak_frequency <= float(high_hz)):
                        continue
                    peak_value = float(
                        np.interp(peak_frequency, frequencies, normalised_percent_per_hz)
                    )
                    axis.scatter(
                        [peak_frequency],
                        [peak_value],
                        s=15,
                        color=line.get_color(),
                        edgecolors="white",
                        linewidths=0.35,
                        zorder=4,
                    )
        axis.set_xlim(float(low_hz), float(high_hz))
        axis.set_title(f"({panel_letters[panel_index]}) {label}")
        axis.set_xlabel("Frequency")
        axis.set_ylabel("Normalised variance density [%/Hz]")
        axis.grid(True, alpha=0.25)
        axis.xaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
        axis.xaxis.set_major_formatter(FuncFormatter(_human_frequency_tick))
        axis.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
        axis.yaxis.set_major_formatter(FuncFormatter(_human_percent_tick))
        axis.yaxis.set_minor_formatter(NullFormatter())
    for axis in flat_axes[len(windows):]:
        axis.set_visible(False)
    handles, labels = flat_axes[0].get_legend_handles_labels()
    fig.suptitle(
        "Linear fine structure of the 5-MS/s Tektronix current PSD",
        y=0.995,
    )
    if handles:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.962),
            ncol=max(1, len(labels)),
            fontsize=8,
        )
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_psd_fine_structure_paper",
        cfg,
    )


def _plot_active_idle_psd(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> list[Path]:
    available = [
        (spec, scope_cfg)
        for spec, scope_cfg in contexts
        if (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "cross_workload_psd_summary.npz"
        ).is_file()
    ]
    if not available:
        return []
    columns = 2
    rows = int(math.ceil(len(available) / columns))
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(10.5, 3.55 * rows),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    flat_axes = list(axes.ravel())
    display_floor_db = -140.0
    panel_letters = "abcdefghijklmnopqrstuvwxyz"
    for index, (spec, _) in enumerate(available):
        axis = flat_axes[index]
        arrays = _load_workload_psd(cfg, spec.workload_id)
        frequencies = np.asarray(arrays["tek_current_frequencies_hz"], dtype=np.float64)
        active = np.asarray(arrays["tek_current_active_psd_a2_per_hz"], dtype=np.float64)
        idle = np.asarray(arrays["tek_current_idle_psd_a2_per_hz"], dtype=np.float64)
        excess = np.asarray(arrays["tek_current_excess_psd_a2_per_hz"], dtype=np.float64)
        active_total = float(trapezoid(active, frequencies)) if frequencies.size > 1 else 0.0
        if active_total <= 0:
            continue
        positive = frequencies > 0
        for label, density, linestyle in (
            ("Active", active, "-"),
            ("External idle", idle, "--"),
            ("Additional under load", excess, ":"),
        ):
            normalised = np.maximum(density / active_total, 0.0)
            mask = positive & np.isfinite(normalised) & (normalised > 0)
            x, y = _decimate_xy(
                frequencies[mask],
                normalised[mask],
                cfg.paper.plot_max_points,
            )
            axis.plot(
                x,
                np.maximum(10.0 * np.log10(y), display_floor_db),
                linestyle=linestyle,
                label=label,
            )
        metrics_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "psd_metrics.json"
        )
        annotation = ""
        if metrics_path.is_file():
            metrics = read_json(metrics_path)
            pairs = int(_finite(metrics.get("external_idle_pairs"), 0.0))
            total_duration = _finite(metrics.get("external_idle_total_duration_s"))
            if pairs > 0 and math.isfinite(total_duration):
                annotation = f"Idle: {pairs} runs, {total_duration:g} s total"
        axis.set_xscale("log")
        axis.set_ylim(display_floor_db, -10.0)
        axis.set_yticks([-140, -120, -100, -80, -60, -40, -20])
        axis.set_title(f"({panel_letters[index]}) {spec.label}")
        axis.grid(True, which="both", alpha=0.25)
        _apply_frequency_axis(axis)
        if annotation:
            axis.text(
                0.02,
                0.97,
                annotation,
                transform=axis.transAxes,
                fontsize=7,
                va="top",
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
            )
        if index // columns == rows - 1:
            axis.set_xlabel("Frequency")
        if index % columns == 0:
            axis.set_ylabel("PSD / active variance [dB re 1/Hz]")
    for axis in flat_axes[len(available):]:
        axis.set_visible(False)
    handles, labels = flat_axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.965),
            ncol=3,
            fontsize=8,
        )
    fig.suptitle(
        "Tektronix current spectra: active, full-record external idle, and additional load variance",
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_active_idle_psd_paper",
        cfg,
    )



def _plot_active_idle_ratio(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    ratio_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    selected = [
        row
        for row in ratio_rows
        if str(row.get("source")) == "tek"
        and str(row.get("signal")) == "current"
    ]
    if not selected:
        return []
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    for spec, _ in contexts:
        workload_rows = sorted(
            [row for row in selected if row.get("workload_id") == spec.workload_id],
            key=lambda row: _finite(row.get("bin_center_hz"), float("inf")),
        )
        if not workload_rows:
            continue
        frequencies = np.asarray(
            [_finite(row.get("bin_center_hz")) for row in workload_rows],
            dtype=np.float64,
        )
        ratios = np.asarray(
            [_finite(row.get("active_to_idle_ratio_db")) for row in workload_rows],
            dtype=np.float64,
        )
        valid = np.isfinite(frequencies) & np.isfinite(ratios) & (frequencies > 0)
        if np.count_nonzero(valid) < 2:
            continue
        ax.plot(frequencies[valid], ratios[valid], label=spec.label)
    ax.axhline(0.0, linewidth=0.8, label="Active = idle")
    ax.axhline(
        cfg.psd.idle_load_amplification_threshold_db,
        linestyle="--",
        linewidth=0.8,
        label=f"+{cfg.psd.idle_load_amplification_threshold_db:g} dB amplification",
    )
    ax.axhline(
        cfg.psd.idle_load_only_threshold_db,
        linestyle=":",
        linewidth=0.8,
        label=f"+{cfg.psd.idle_load_only_threshold_db:g} dB load-only candidate",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Frequency")
    ax.set_ylabel("Active/idle variance ratio [dB per log-frequency bin]")
    ax.set_title(
        "Active-to-idle spectral amplification in logarithmic frequency bins"
    )
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    _apply_frequency_axis(ax)
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_active_idle_ratio_paper",
        cfg,
    )


def _plot_idle_load_band_comparison(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    idle_load_band_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    selected = [
        row
        for row in idle_load_band_rows
        if str(row.get("source")) == "tek"
        and str(row.get("signal")) == "current"
    ]
    if not selected:
        return []
    bands = [band[0] for band in cfg.psd.bands]
    x = np.arange(len(bands), dtype=np.float64)
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.25), sharex=True)
    for spec, _ in contexts:
        rows = {
            str(row["band"]): row
            for row in selected
            if row["workload_id"] == spec.workload_id
        }
        if not rows:
            continue
        additional = [
            _finite(rows.get(band, {}).get("load_additional_of_active_percent"))
            for band in bands
        ]
        ratio_db = [
            _finite(rows.get(band, {}).get("active_to_idle_ratio_db"))
            for band in bands
        ]
        axes[0].plot(x, additional, marker="o", label=spec.label)
        axes[1].plot(x, ratio_db, marker="o", label=spec.label)
    axes[0].set_ylabel("Additional active-band variance")
    axes[0].set_title("(a) Active variance not overlapping the idle PSD")
    axes[0].set_ylim(0, 100.5)
    _apply_percent_axis(axes[0], [0, 20, 40, 60, 80, 100])
    axes[1].axhline(0.0, linestyle="-", linewidth=0.8, label="Active = idle")
    axes[1].axhline(
        cfg.psd.idle_load_amplification_threshold_db,
        linestyle="--",
        linewidth=0.8,
        label=f"+{cfg.psd.idle_load_amplification_threshold_db:g} dB",
    )
    axes[1].axhline(
        cfg.psd.idle_load_only_threshold_db,
        linestyle=":",
        linewidth=0.8,
        label=f"+{cfg.psd.idle_load_only_threshold_db:g} dB",
    )
    axes[1].set_ylabel("Active/idle band ratio [dB]")
    axes[1].set_title("(b) Bandwise active-to-idle level")
    for axis in axes:
        axis.set_xticks(x)
        axis.set_xticklabels(bands, rotation=24, ha="right")
        axis.set_xlabel("Frequency band")
        axis.grid(True, axis="y", alpha=0.25)
    handles, labels = axes[0].get_legend_handles_labels()
    handles2, labels2 = axes[1].get_legend_handles_labels()
    unique_legend: dict[str, Any] = {}
    for handle, label in zip(handles + handles2, labels + labels2):
        unique_legend.setdefault(label, handle)
    fig.legend(
        list(unique_legend.values()),
        list(unique_legend.keys()),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=max(2, min(5, len(unique_legend))),
        fontsize=7,
    )
    fig.suptitle(
        "Bandwise Tektronix current-spectrum changes relative to full-record idle",
        y=1.045,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_idle_load_frequency_bands_paper",
        cfg,
    )


def _plot_band_fractions(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    band_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    selected = [
        row for row in band_rows if row["source"] == "tek" and row["signal"] == "current"
    ]
    labels = [
        spec.label
        for spec, _ in contexts
        if any(row["workload_id"] == spec.workload_id for row in selected)
    ]
    ids = [spec.workload_id for spec, _ in contexts if spec.label in labels]
    bands = [band[0] for band in cfg.psd.bands]
    fig, ax = plt.subplots(figsize=(10.0, 4.4))
    bottoms = np.zeros(len(ids), dtype=np.float64)
    for band in bands:
        values = []
        for workload_id in ids:
            matches = [
                row
                for row in selected
                if row["workload_id"] == workload_id and row["band"] == band
            ]
            values.append(_finite(matches[0]["variance_percent"], 0.0) if matches else 0.0)
        values_array = np.asarray(values, dtype=np.float64)
        ax.bar(labels, values_array, bottom=bottoms, label=band)
        bottoms += values_array
    ax.set_ylabel("Workload-related current variance")
    ax.set_title("Tektronix current-PSD frequency-band composition at 5 MS/s")
    ax.set_ylim(0, 100.5)
    ax.grid(True, axis="y", alpha=0.25)
    _apply_percent_axis(ax, [0, 20, 40, 60, 80, 100])
    ax.legend(ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_frequency_bands_paper",
        cfg,
    )


def _plot_two_k_duration(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    common_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True)
    for axis, source in zip(axes, ("tek", "pico")):
        for spec, _ in contexts:
            rows = sorted(
                [
                    row
                    for row in common_rows
                    if row["workload_id"] == spec.workload_id
                    and row["source"] == source
                    and row["mode"] == "phase_only"
                    and int(row["target_rate_sps"])
                    == cfg.common_reference.highlighted_rate_sps
                ],
                key=lambda row: float(row["duration_s"]),
            )
            if rows:
                axis.plot(
                    [float(row["duration_s"]) for row in rows],
                    [float(row["hierarchical_abs_error_q95_pct"]) for row in rows],
                    marker="o",
                    label=spec.label,
                )
        axis.axhline(0.5, linestyle=":", linewidth=1.0)
        axis.axhline(1.0, linestyle="--", linewidth=1.0)
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Integration-window duration")
        axis.set_title(f"({ 'a' if source == 'tek' else 'b' }) {_source_setup_label(source)}")
        axis.grid(True, which="both", alpha=0.25)
        _apply_duration_axis(axis)
        _apply_percent_axis(axis, [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])
    axes[0].set_ylabel(
        f"Hierarchical q95 energy error at {human_rate(cfg.common_reference.highlighted_rate_sps)}"
    )
    axes[1].legend(fontsize=8)
    fig.suptitle("Common-reference energy sufficiency across Edge-AI workloads")
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_energy_duration_paper",
        cfg,
    )


def _plot_worst_case_two_k(
    cfg: MultiWorkloadConfig,
    common_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    for source in ("tek", "pico"):
        durations = sorted(
            {
                float(row["duration_s"])
                for row in common_rows
                if row["source"] == source
                and row["mode"] == "phase_only"
                and int(row["target_rate_sps"])
                == cfg.common_reference.highlighted_rate_sps
            }
        )
        values = []
        for duration in durations:
            candidates = [
                _finite(row["hierarchical_abs_error_q95_pct"])
                for row in common_rows
                if row["source"] == source
                and row["mode"] == "phase_only"
                and int(row["target_rate_sps"])
                == cfg.common_reference.highlighted_rate_sps
                and abs(float(row["duration_s"]) - duration) < 1e-12
            ]
            candidates = [value for value in candidates if math.isfinite(value)]
            values.append(max(candidates) if candidates else float("nan"))
        if durations:
            ax.plot(
                durations,
                values,
                marker="o",
                linewidth=2.0,
                label=f"{_source_setup_label(source)} worst case",
            )
    ax.axhline(1.0, linestyle="--", linewidth=1.0, label="1% criterion")
    ax.axhline(0.5, linestyle=":", linewidth=1.0, label="0.5% criterion")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Integration-window duration")
    ax.set_ylabel(
        f"Maximum workload q95 error at {human_rate(cfg.common_reference.highlighted_rate_sps)}"
    )
    ax.set_title("Conservative 2-kS/s energy-error envelope across available workloads")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    _apply_duration_axis(ax)
    _apply_percent_axis(ax, [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_worst_case_envelope_paper",
        cfg,
    )


def _plot_fmin(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    fmin_rows: Sequence[dict[str, Any]],
    worst_rows: Sequence[dict[str, Any]],
) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True)
    threshold = 1.0
    for axis, source in zip(axes, ("tek", "pico")):
        for spec, _ in contexts:
            rows = sorted(
                [
                    row
                    for row in fmin_rows
                    if row["workload_id"] == spec.workload_id
                    and row["source"] == source
                    and row["mode"] == "phase_only"
                    and abs(float(row["threshold_pct"]) - threshold) < 1e-12
                    and row.get("f_min_sps") not in (None, "")
                ],
                key=lambda row: float(row["duration_s"]),
            )
            if rows:
                axis.plot(
                    [float(row["duration_s"]) for row in rows],
                    [float(row["f_min_sps"]) for row in rows],
                    marker="o",
                    label=spec.label,
                )
        worst = sorted(
            [
                row
                for row in worst_rows
                if row["source"] == source
                and row["mode"] == "phase_only"
                and abs(float(row["threshold_pct"]) - threshold) < 1e-12
                and row.get("worst_case_f_min_sps") not in (None, "")
            ],
            key=lambda row: float(row["duration_s"]),
        )
        if worst:
            axis.plot(
                [float(row["duration_s"]) for row in worst],
                [float(row["worst_case_f_min_sps"]) for row in worst],
                linestyle="--",
                linewidth=2.0,
                label="Worst-case envelope",
            )
        axis.axhline(
            cfg.common_reference.highlighted_rate_sps,
            linestyle=":",
            linewidth=1.2,
            label="2 kS/s u.RECS target",
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Integration-window duration")
        axis.set_title(f"({ 'a' if source == 'tek' else 'b' }) {_source_setup_label(source)}")
        axis.grid(True, which="both", alpha=0.25)
        _apply_duration_axis(axis)
        _apply_rate_axis(axis, orientation="y")
    axes[0].set_ylabel("Minimum tested rate meeting q95 ≤ 1%")
    axes[1].legend(fontsize=7)
    fig.suptitle("Workload-specific and conservative common-reference rate bounds")
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_fmin_paper",
        cfg,
    )


def _plot_direct_validation(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    rows: Sequence[dict[str, Any]],
) -> list[Path]:
    if not rows:
        return []
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True)
    reference_rate = float(cfg.direct_validation.maximum_rate_sps)
    for axis, source in zip(axes, ("tek", "pico")):
        reference_present = False
        for spec, _ in contexts:
            selected = sorted(
                [
                    row
                    for row in rows
                    if row["workload_id"] == spec.workload_id
                    and row["source"] == source
                ],
                key=lambda row: int(row["direct_rate_sps"]),
            )
            if not selected:
                continue
            observed_points = [
                (int(row["direct_rate_sps"]), abs(float(row["direct_power_deviation_pct"])))
                for row in selected
            ]
            predicted_points = [
                (
                    int(row["direct_rate_sps"]),
                    _finite(row.get("common_reference_hierarchical_q95_pct")),
                )
                for row in selected
            ]
            reference_present = reference_present or any(
                rate == int(reference_rate) and value <= 1e-12
                for rate, value in observed_points
            )
            observed_positive = [
                (rate, value) for rate, value in observed_points if value > 1e-12
            ]
            predicted_positive = [
                (rate, value)
                for rate, value in predicted_points
                if math.isfinite(value) and value > 1e-12
            ]
            if observed_positive:
                axis.plot(
                    [item[0] for item in observed_positive],
                    [item[1] for item in observed_positive],
                    marker="o",
                    label=f"{spec.label}: direct",
                )
            if predicted_positive:
                axis.plot(
                    [item[0] for item in predicted_positive],
                    [item[1] for item in predicted_positive],
                    linestyle="--",
                    label=f"{spec.label}: same-trace q95",
                )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Sampling rate")
        axis.set_title(f"({ 'a' if source == 'tek' else 'b' }) {_source_setup_label(source)}")
        axis.grid(True, which="both", alpha=0.25)
        _apply_rate_axis(axis, orientation="x")
        _apply_percent_axis(
            axis,
            [0.000001, 0.00001, 0.0001, 0.001, 0.01, 0.1, 1.0, 10.0],
        )
        if reference_present:
            axis.axvline(reference_rate, linestyle=":", linewidth=0.8, color="0.45")
            axis.text(
                reference_rate,
                0.025,
                "5 MS/s reference = 0%",
                transform=axis.get_xaxis_transform(),
                ha="right",
                va="bottom",
                fontsize=7,
                color="0.35",
            )
    axes[0].set_ylabel("Absolute deviation from the 5-MS/s median")
    axes[1].legend(fontsize=6, ncol=2)
    fig.suptitle("Separate-run rate sweep versus same-trace sampling-only bound")
    fig.tight_layout()
    return _save_figure(
        fig,
        cfg.output_root
        / "paper_artifacts"
        / "figures"
        / "cross_workload_direct_vs_common_reference_paper",
        cfg,
    )


def _latex_escape(value: Any) -> str:
    mapping = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(mapping.get(character, character) for character in str(value))


def _fmt(value: Any, digits: int = 3) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _write_table_triplet(
    root: Path,
    name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    caption: str,
    label: str,
) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / f"{name}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    md_path = root / f"{name}.md"
    md_lines = [
        f"# {caption}",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    md_lines.extend(
        "| " + " | ".join(str(item) for item in row) + " |" for row in rows
    )
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    tex_path = root / f"{name}.tex"
    column_spec = "l" + "r" * max(0, len(headers) - 1)
    tex_lines = [
        "% Auto-generated by common_reference_psd_tool.",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{" + _latex_escape(caption) + "}",
        "\\label{" + label + "}",
        "\\resizebox{\\textwidth}{!}{%",
        f"\\begin{{tabular}}{{{column_spec}}}",
        "\\toprule",
        " & ".join(_latex_escape(item) for item in headers) + " \\\\",
        "\\midrule",
    ]
    tex_lines.extend(
        " & ".join(_latex_escape(item) for item in row) + " \\\\" for row in rows
    )
    tex_lines.extend(
        ["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}", ""]
    )
    tex_path.write_text("\n".join(tex_lines), encoding="utf-8")
    return [csv_path, md_path, tex_path]


_LATEX_DIGIT_WORDS = {
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
}


def _latex_command_name(name: str) -> str:
    output: list[str] = []
    for character in str(name):
        if character.isalpha():
            output.append(character)
        elif character.isdigit():
            output.append(_LATEX_DIGIT_WORDS[character])
        else:
            output.append("X")
    command = "".join(output)
    if not command or not command.isalpha():
        raise ValueError(f"Invalid TeX macro name: {name}")
    return command


def _write_macros(path: Path, macros: dict[str, Any]) -> Path:
    lines = ["% Auto-generated multi-workload result macros."]
    mapping: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in sorted(macros):
        command = _latex_command_name(key)
        if command in seen:
            raise ValueError(f"TeX macro collision: {key} -> {command}")
        seen.add(command)
        value = macros[key]
        if isinstance(value, float):
            rendered = "n/a" if not math.isfinite(value) else f"{value:.6g}"
        elif value is None:
            rendered = "n/a"
        else:
            rendered = str(value)
        lines.append(f"\\providecommand{{\\{command}}}{{{rendered}}}")
        mapping.append(
            {"analysis_key": key, "tex_command": f"\\{command}", "value": rendered}
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    write_csv(path.with_name(f"{path.stem}_name_map.csv"), mapping)
    return path


def _high_rate_coverage(
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec, scope_cfg in contexts:
        path = scope_cfg.output_root / "cross_rate_summary.csv"
        if not path.is_file():
            continue
        candidates: list[dict[str, Any]] = []
        for row in _read_csv(path):
            rate = int(round(_finite(row.get("tek_rate_sps"), 0.0)))
            workload_value = _finite(
                row.get("native_workload_tek_native_variance_above_pico_nyquist_median")
            )
            active_value = _finite(
                row.get("native_tek_native_active_variance_above_pico_nyquist_median")
            )
            basis = "active_minus_idle" if math.isfinite(workload_value) else "active_only"
            value = workload_value if math.isfinite(workload_value) else active_value
            if rate > 0 and math.isfinite(value):
                candidates.append(
                    {"rate": rate, "value": value, "basis": basis, "row": row}
                )
        if not candidates:
            continue
        selected = max(candidates, key=lambda item: item["rate"])
        rows.append(
            {
                "workload_id": spec.workload_id,
                "workload_label": spec.label,
                "highest_tek_rate_sps": selected["rate"],
                "basis": selected["basis"],
                "variance_above_pico_nyquist_fraction": selected["value"],
                "variance_above_pico_nyquist_percent": 100.0 * selected["value"],
                "pico_sampling_ceiling_capture_percent": 100.0 * (1.0 - selected["value"]),
            }
        )
    return rows


def _generate_tables_and_macros(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    inventory: Sequence[dict[str, Any]],
    psd_metrics: Sequence[dict[str, Any]],
    band_rows: Sequence[dict[str, Any]],
    peak_rows: Sequence[dict[str, Any]],
    idle_load_summary_rows: Sequence[dict[str, Any]],
    idle_load_band_rows: Sequence[dict[str, Any]],
    idle_load_peak_rows: Sequence[dict[str, Any]],
    common_summary: Sequence[dict[str, Any]],
    fmin_rows: Sequence[dict[str, Any]],
    threshold_rows: Sequence[dict[str, Any]],
    worst_rows: Sequence[dict[str, Any]],
    direct_rows: Sequence[dict[str, Any]],
    high_rate_rows: Sequence[dict[str, Any]],
) -> tuple[list[Path], dict[str, Any]]:
    root = cfg.output_root / "paper_artifacts" / "tables"
    outputs: list[Path] = []
    inventory_table = []
    for row in inventory:
        inventory_table.append(
            [
                row["workload_label"],
                row.get("workload_family", ""),
                row.get("workload_precision", "unspecified"),
                row["status"],
                row["common_rate_valid_pairs"],
                "yes" if row["psd_ready"] else "no",
                "yes" if row["common_reference_ready"] else "no",
                row["zero_offset_status"],
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_multi_workload_inventory",
            ["Workload", "Family", "Precision", "Status", "5-MS/s pairs", "PSD", "Common ref.", "Zero-offset status"],
            inventory_table,
            "Availability and analysis status of the paired-scope workload campaigns.",
            "tab:multi-workload-inventory",
        )
    )

    psd_table = []
    for metrics in psd_metrics:
        psd_table.append(
            [
                metrics["workload_label"],
                metrics["valid_pairs"],
                _fmt(_finite(metrics.get("tek_current_f50_hz_median")) / 1000.0, 1),
                _fmt(_finite(metrics.get("tek_current_f90_hz_median")) / 1000.0, 1),
                _fmt(_finite(metrics.get("tek_current_f95_hz_median")) / 1000.0, 1),
                _fmt(_finite(metrics.get("tek_current_f99_hz_median")) / 1000.0, 1),
                _fmt(100.0 * _finite(metrics.get("tek_current_variance_above_77khz")), 2),
                _fmt(_finite(metrics.get("tek_current_entropy")), 3),
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_psd_metrics",
            ["Workload", "n", "$f_{50}$ [kHz]", "$f_{90}$ [kHz]", "$f_{95}$ [kHz]", "$f_{99}$ [kHz]", ">77 kHz [\\%]", "Entropy"],
            psd_table,
            "Cross-workload Tektronix current-spectrum metrics at the common 5-MS/s acquisition rate. Values are medians of per-run active-minus-external-idle metrics; plotted curves are pointwise median PSDs.",
            "tab:cross-workload-psd",
        )
    )

    dominant_peak_table = []
    for row in peak_rows:
        if str(row.get("source")) != "tek" or str(row.get("signal")) != "current":
            continue
        rank = int(float(row.get("rank", 999)))
        if rank > 5:
            continue
        dominant_peak_table.append(
            [
                row.get("workload_label", row.get("workload_id", "")),
                rank,
                _human_frequency_tick(_finite(row.get("frequency_hz"))),
                _fmt(_finite(row.get("relative_db")), 2),
                _fmt(_finite(row.get("prominence_db")), 2),
            ]
        )
    dominant_peak_table.sort(key=lambda row: (str(row[0]), int(row[1])))
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_dominant_peaks",
            ["Workload", "Rank", "Frequency", "Relative level [dB]", "Prominence [dB]"],
            dominant_peak_table,
            "Dominant lines in the common-rate Tektronix current spectra. Frequencies lie on the Welch grid and are descriptive spectral features; causal attribution requires workload-timing evidence.",
            "tab:cross-workload-dominant-peaks",
        )
    )

    idle_load_summary_table = []
    for row in idle_load_summary_rows:
        if str(row.get("source")) != "tek" or str(row.get("signal")) != "current":
            continue
        idle_load_summary_table.append(
            [
                row.get("workload_label", row.get("workload_id", "")),
                row.get("external_idle_pairs", "n/a"),
                _fmt(row.get("external_idle_total_duration_s"), 1),
                _fmt(row.get("active_to_idle_ratio_db"), 2),
                _fmt(row.get("idle_overlap_of_active_percent"), 2),
                _fmt(row.get("load_additional_of_active_percent"), 2),
                _idle_policy_label(row.get("idle_record_policy", "")),
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_idle_load_summary",
            [
                "Workload",
                "Idle runs",
                "Idle duration [s]",
                "Active/idle [dB]",
                "Idle-overlap [\\%]",
                "Additional under load [\\%]",
                "Idle aggregation",
            ],
            idle_load_summary_table,
            "Direct comparison of active and exact-rate external-idle Tektronix current spectra at 5 MS/s. Full physical idle records are analysed with the same Welch policy as active records; each physical idle run contributes one equal-weight PSD to the cross-run median. The overlap/additional decomposition is descriptive and not phase-coherent source separation.",
            "tab:cross-workload-idle-load-summary",
        )
    )

    idle_load_band_table = []
    for row in idle_load_band_rows:
        if str(row.get("source")) != "tek" or str(row.get("signal")) != "current":
            continue
        idle_load_band_table.append(
            [
                row.get("workload_label", row.get("workload_id", "")),
                row.get("band", ""),
                _fmt(row.get("active_to_idle_ratio_db"), 2),
                _fmt(row.get("idle_overlap_of_active_percent"), 2),
                _fmt(row.get("load_additional_of_active_percent"), 2),
                _fmt(row.get("active_share_of_total_percent"), 2),
                _fmt(row.get("idle_share_of_total_percent"), 2),
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_idle_load_bands",
            [
                "Workload",
                "Band",
                "Active/idle [dB]",
                "Idle-overlap [\\%]",
                "Additional [\\%]",
                "Active share [\\%]",
                "Idle share [\\%]",
            ],
            idle_load_band_table,
            "Bandwise active-versus-idle Tektronix current-spectrum comparison. Additional percentage is max(active-idle,0) divided by active-band variance; idle-overlap is min(active,idle) divided by active-band variance.",
            "tab:cross-workload-idle-load-bands",
        )
    )

    idle_load_peak_table = []
    for row in idle_load_peak_rows:
        if str(row.get("source")) != "tek" or str(row.get("signal")) != "current":
            continue
        rank = int(float(row.get("rank", 999)))
        if rank > 5:
            continue
        idle_load_peak_table.append(
            [
                row.get("workload_label", row.get("workload_id", "")),
                rank,
                _human_frequency_tick(_finite(row.get("load_peak_frequency_hz"))),
                _fmt(row.get("active_to_idle_ratio_db"), 2),
                "yes" if str(row.get("idle_peak_matched", "")).lower() in {"true", "1", "yes"} or row.get("idle_peak_matched") is True else "no",
                _human_frequency_tick(_finite(row.get("nearest_idle_peak_hz"))),
                _idle_load_classification_label(row.get("classification", "")),
            ]
        )
    idle_load_peak_table.sort(key=lambda row: (str(row[0]), int(row[1])))
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_idle_load_peaks",
            [
                "Workload",
                "Rank",
                "Load peak",
                "Active/idle [dB]",
                "Idle line matched",
                "Nearest idle peak",
                "Classification",
            ],
            idle_load_peak_table,
            "Diagnostic classification of dominant additional-load spectral lines. Active/idle ratios are integrated over a local multi-bin interval; idle-line matching uses a configurable Welch-bin tolerance and does not establish phase coherence or causal identity.",
            "tab:cross-workload-idle-load-peaks",
        )
    )

    two_k_table = []
    for row in threshold_rows:
        if row["mode"] != "phase_only":
            continue
        if float(row["threshold_pct"]) not in {0.5, 1.0, 2.0, 5.0}:
            continue
        two_k_table.append(
            [
                row["workload_label"],
                _source_setup_label(str(row["source"])),
                _fmt(row["threshold_pct"], 1),
                _fmt(row.get("minimum_passing_duration_s"), 3),
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_two_k_sufficiency",
            ["Workload", "Setup", "Tolerance [\\%]", "Minimum tested duration [s]"],
            two_k_table,
            "Minimum tested integration duration for which 2 kS/s and every longer tested duration satisfy the hierarchical q95 energy-error criterion.",
            "tab:cross-workload-two-k",
        )
    )

    fmin_table = []
    selected_durations = {0.1, 0.5, 1.0, 2.0, 5.0, 10.0}
    for row in fmin_rows:
        if row["mode"] != "phase_only" or abs(float(row["threshold_pct"]) - 1.0) > 1e-12:
            continue
        if float(row["duration_s"]) not in selected_durations:
            continue
        fmin_table.append(
            [
                row["workload_label"],
                _source_setup_label(str(row["source"])),
                _fmt(row["duration_s"], 1),
                human_rate(float(row["f_min_sps"])) if row.get("f_min_sps") not in (None, "") else "n/a",
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_fmin",
            ["Workload", "Setup", "Duration [s]", "$f_{min,E}$ for 1\\%"],
            fmin_table,
            "Minimum tested sampling-rate bounds for the 1\\% hierarchical q95 energy-error criterion.",
            "tab:cross-workload-fmin",
        )
    )

    worst_table = []
    for row in worst_rows:
        if row["mode"] != "phase_only" or abs(float(row["threshold_pct"]) - 1.0) > 1e-12:
            continue
        worst_table.append(
            [
                _source_setup_label(str(row["source"])),
                _fmt(row["duration_s"], 3),
                human_rate(float(row["worst_case_f_min_sps"]))
                if row.get("worst_case_f_min_sps") not in (None, "")
                else "n/a",
                row.get("limiting_workloads", ""),
                f"{row.get('contributing_workloads', 'n/a')}/{row.get('expected_workloads', 'n/a')}",
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_worst_case_envelope",
            ["Setup", "Duration [s]", "Worst-case $f_{min,E}$ for 1\\%", "Limiting workload(s)", "Coverage"],
            worst_table,
            "Conservative 1\\% minimum-rate envelope across every workload currently available to the analysis.",
            "tab:cross-workload-worst-envelope",
        )
    )

    coverage_table = [
        [
            row["workload_label"],
            human_rate(row["highest_tek_rate_sps"]),
            row["basis"],
            _fmt(row["variance_above_pico_nyquist_percent"], 4),
            _fmt(row["pico_sampling_ceiling_capture_percent"], 4),
        ]
        for row in high_rate_rows
    ]
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_high_rate_coverage",
            ["Workload", "Highest Tek rate", "Basis", ">2.5 MHz [\\%]", "Captured below 2.5 MHz [\\%]"],
            coverage_table,
            "Highest-rate Tektronix check of spectral content above the 5-MS/s PicoScope Nyquist limit. Active-only values are diagnostics and are not idle-subtracted workload metrics.",
            "tab:cross-workload-high-rate",
        )
    )

    direct_table = []
    for row in direct_rows:
        if int(row["direct_rate_sps"]) not in {2500, 25000, 100000, 1000000, 5000000}:
            continue
        direct_table.append(
            [
                row["workload_label"],
                _source_setup_label(str(row["source"])),
                human_rate(row["direct_rate_sps"]),
                _fmt(row["direct_power_deviation_pct"], 3),
                _fmt(row.get("common_reference_hierarchical_q95_pct"), 3),
            ]
        )
    outputs.extend(
        _write_table_triplet(
            root,
            "table_cross_workload_direct_validation",
            ["Workload", "Setup", "Direct rate", "Separate-run median deviation [\\%]", "Same-trace q95 [\\%]"],
            direct_table,
            "Directly acquired rate sweeps compared with same-trace sampling-only bounds. Direct measurements are separate physical executions and therefore include run-to-run and acquisition effects.",
            "tab:cross-workload-direct",
        )
    )

    macros: dict[str, Any] = {
        "MultiWorkloadReadyCount": len(contexts),
        "MultiCommonPSDRateSps": cfg.psd.comparison_rate_sps,
        "MultiHighlightedRateSps": cfg.common_reference.highlighted_rate_sps,
    }
    for metrics in psd_metrics:
        prefix = "Multi" + _slug(metrics["workload_label"]).replace("_", "")
        macros[prefix + "TekCurrentFNinetyFiveHz"] = _finite(
            metrics.get("tek_current_f95_hz_median")
        )
        macros[prefix + "TekCurrentFNinetyNineHz"] = _finite(
            metrics.get("tek_current_f99_hz_median")
        )
        macros[prefix + "TekCurrentAboveSeventySevenKPercent"] = 100.0 * _finite(
            metrics.get("tek_current_variance_above_77khz")
        )
        idle_rows = [
            row
            for row in idle_load_summary_rows
            if row.get("workload_id") == metrics.get("workload_id")
            and str(row.get("source")) == "tek"
            and str(row.get("signal")) == "current"
        ]
        if idle_rows:
            idle_row = idle_rows[0]
            macros[prefix + "TekIdleOverlapOfActivePercent"] = _finite(
                idle_row.get("idle_overlap_of_active_percent")
            )
            macros[prefix + "TekAdditionalUnderLoadPercent"] = _finite(
                idle_row.get("load_additional_of_active_percent")
            )
            macros[prefix + "TekActiveToIdleRatioDb"] = _finite(
                idle_row.get("active_to_idle_ratio_db")
            )
            macros[prefix + "ExternalIdleDurationSeconds"] = _finite(
                idle_row.get("external_idle_total_duration_s")
            )
    worst_one_pct = [
        row
        for row in worst_rows
        if row["source"] == "tek"
        and row["mode"] == "phase_only"
        and abs(float(row["threshold_pct"]) - 1.0) < 1e-12
    ]
    for row in worst_one_pct:
        duration_label = str(row["duration_s"]).replace(".", "p")
        macros[f"MultiWorstCaseOnePctDuration{duration_label}SecondsSps"] = row.get(
            "worst_case_f_min_sps"
        )
    macro_path = _write_macros(
        cfg.output_root / "paper_artifacts" / "latex" / "multi_workload_results_macros.tex",
        macros,
    )
    outputs.append(macro_path)
    return outputs, macros


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_inventory(root: Path, target: Path, *, exclude: Sequence[Path] = ()) -> Path:
    excluded = {path.resolve() for path in exclude}
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        rows.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    write_csv(target, rows)
    return target


def _zip_tree(
    source_root: Path,
    zip_path: Path,
    *,
    exclude_predicate=None,
) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = zip_path.with_suffix(zip_path.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root)
            if exclude_predicate is not None and exclude_predicate(relative):
                continue
            info = zipfile.ZipInfo.from_file(path, arcname=str(relative))
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.external_attr = 0o100644 << 16
            with path.open("rb") as handle:
                archive.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(tmp, zip_path)
    return zip_path


def _figure_snippets(cfg: MultiWorkloadConfig) -> Path:
    path = cfg.output_root / "paper_artifacts" / "latex" / "multi_workload_figure_snippets.tex"
    rows = [
        (
            "cross_workload_current_psd_paper",
            "Cross-workload Tektronix current spectra at the common 5-MS/s rate. Each curve subtracts the exact-rate external-idle median. The left panel shows the normalised PSD shape in dB relative to 1/Hz; the right panel shows the cumulative workload-related variance in percent.",
            "fig:cross-workload-current-psd",
        ),
        (
            "cross_workload_power_psd_paper",
            "Cross-workload spectra of estimated power derived from the calibrated current traces using the shared current-dependent voltage model. The left panel shows normalised PSD shape; the right panel shows cumulative workload-related power variance.",
            "fig:cross-workload-power-psd",
        ),
        (
            "cross_workload_frequency_bands_paper",
            "Frequency-band composition of the workload-related Tektronix current variance at 5 MS/s.",
            "fig:cross-workload-bands",
        ),
        (
            "cross_workload_log_frequency_variance_share_paper",
            "Log-frequency view of the cumulative-spectrum derivative. Each point reports the workload-related variance share in one fixed-width logarithmic frequency bin; the shares sum to 100 percent across the analysed band.",
            "fig:cross-workload-log-derivative",
        ),
        (
            "cross_workload_psd_fine_structure_paper",
            "Linear-axis fine structure of the normalised Tektronix current PSD in selected low-frequency, mid-frequency, precision-sensitive 25–35-kHz, and upper-tail regions. Exact dominant-peak frequencies remain listed in the generated CSV artifacts.",
            "fig:cross-workload-fine-structure",
        ),
        (
            "cross_workload_active_idle_psd_paper",
            "Per-workload Tektronix current spectra for active operation, full-record exact-rate external idle, and the additional under-load component max(active-idle,0). Every physical idle run is analysed at its full duration with the same Welch method; physical runs receive equal weight in the cross-run median.",
            "fig:cross-workload-active-idle",
        ),
        (
            "cross_workload_active_idle_ratio_paper",
            "Integrated active-to-idle Tektronix current-variance ratio in equal-width logarithmic frequency bins. Positive values indicate more variance under load; the 3-dB and 6-dB guide lines mark the configured load-amplified and load-only-candidate thresholds. Active and idle are independent acquisitions, so the comparison is descriptive rather than phase-coherent source separation.",
            "fig:cross-workload-active-idle-ratio",
        ),
        (
            "cross_workload_idle_load_frequency_bands_paper",
            "Bandwise comparison of active and external-idle Tektronix current spectra. Panel (a) shows the fraction of active-band variance that exceeds the idle PSD; panel (b) shows the integrated active/idle PSD ratio. This is a descriptive comparison of independent records, not phase-coherent source separation.",
            "fig:cross-workload-idle-load-bands",
        ),
        (
            "cross_workload_energy_duration_paper",
            "Duration-dependent common-reference energy error at 2 kS/s. Each point is the hierarchical q95: window-position and sampling-grid-offset sensitivity are first aggregated within each physical run and then across physical runs. The horizontal lines mark the 0.5% and 1% criteria.",
            "fig:cross-workload-duration",
        ),
        (
            "cross_workload_worst_case_envelope_paper",
            "Conservative worst-case 2-kS/s energy-error envelope. At each integration duration, the plotted value is the maximum hierarchical q95 among all currently available workloads; the horizontal lines mark the 0.5% and 1% criteria.",
            "fig:cross-workload-worst-envelope",
        ),
        (
            "cross_workload_fmin_paper",
            "Workload-specific minimum tested rates for the 1\\% energy criterion. A rate is reported only when that rate and every higher tested rate satisfy the criterion; the dashed curve is the maximum across available workloads and the dotted line marks the 2-kS/s u.RECS target.",
            "fig:cross-workload-fmin",
        ),
        (
            "cross_workload_direct_vs_common_reference_paper",
            "Separate-run rate-sweep deviations versus same-trace sampling-only bounds. Solid curves show deviations of independently acquired runs from the 5-MS/s median; dashed curves show the q95 bound reconstructed from the same physical trace. The 5-MS/s zero reference is annotated rather than displaced on the logarithmic axis.",
            "fig:cross-workload-direct",
        ),
    ]
    lines = ["% Auto-generated multi-workload figure snippets.", ""]
    for name, caption, label in rows:
        lines.extend(
            [
                "\\begin{figure}[t]",
                "  \\centering",
                f"  \\includegraphics[width=\\textwidth]{{paper_artifacts/figures/{name}.pdf}}",
                f"  \\caption{{{caption}}}",
                f"  \\label{{{label}}}",
                "\\end{figure}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _table_snippets(cfg: MultiWorkloadConfig) -> Path:
    path = cfg.output_root / "paper_artifacts" / "latex" / "multi_workload_table_snippets.tex"
    names = [
        "table_multi_workload_inventory",
        "table_cross_workload_psd_metrics",
        "table_cross_workload_dominant_peaks",
        "table_cross_workload_idle_load_summary",
        "table_cross_workload_idle_load_bands",
        "table_cross_workload_idle_load_peaks",
        "table_cross_workload_two_k_sufficiency",
        "table_cross_workload_fmin",
        "table_cross_workload_worst_case_envelope",
        "table_cross_workload_high_rate_coverage",
        "table_cross_workload_direct_validation",
    ]
    lines = ["% Auto-generated multi-workload table snippets.", ""]
    lines.extend(
        f"% \\input{{paper_artifacts/tables/{name}.tex}}" for name in names
    )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _summary_document(
    cfg: MultiWorkloadConfig,
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
    inventory: Sequence[dict[str, Any]],
    psd_metrics: Sequence[dict[str, Any]],
    threshold_rows: Sequence[dict[str, Any]],
    worst_rows: Sequence[dict[str, Any]],
    high_rate_rows: Sequence[dict[str, Any]],
) -> Path:
    path = cfg.output_root / "MULTI_WORKLOAD_SUMMARY.md"
    lines = [
        "# Multi-workload PSD and common-reference analysis",
        "",
        f"Tool version: `{__version__}`  ",
        f"Common PSD rate: `{human_rate(cfg.psd.comparison_rate_sps)}`  ",
        f"Highlighted energy rate: `{human_rate(cfg.common_reference.highlighted_rate_sps)}`",
        "",
        "## Included workloads",
        "",
        "| Workload | 5-MS/s pairs | PSD | Common reference | Zero-offset status |",
        "|---|---:|---:|---:|---|",
    ]
    for row in inventory:
        if not row["enabled"]:
            continue
        lines.append(
            f"| {row['workload_label']} | {row['common_rate_valid_pairs']} | "
            f"{'yes' if row['psd_ready'] else 'no'} | "
            f"{'yes' if row['common_reference_ready'] else 'no'} | "
            f"{row['zero_offset_status']} |"
        )
    lines.extend(["", "## Common-rate Tektronix current PSD", ""])
    lines.append("| Workload | $f_{95}$ | $f_{99}$ | Variance above 77 kHz |")
    lines.append("|---|---:|---:|---:|")
    for metrics in psd_metrics:
        lines.append(
            f"| {metrics['workload_label']} | "
            f"{_fmt(_finite(metrics.get('tek_current_f95_hz_median'))/1000.0,1)} kHz | "
            f"{_fmt(_finite(metrics.get('tek_current_f99_hz_median'))/1000.0,1)} kHz | "
            f"{_fmt(100.0*_finite(metrics.get('tek_current_variance_above_77khz')),2)}% |"
        )
    lines.extend(["", "## Active versus external idle", ""])
    lines.append(
        "| Workload | Idle runs | Idle duration | Active/idle | Idle-overlap of active | Additional under load |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for metrics in psd_metrics:
        idle_rows = [
            row
            for row in metrics.get("idle_load_summary", [])
            if str(row.get("source")) == "tek"
            and str(row.get("signal")) == "current"
        ]
        if not idle_rows:
            continue
        row = idle_rows[0]
        lines.append(
            f"| {metrics['workload_label']} | {row.get('external_idle_pairs', 'n/a')} | "
            f"{_fmt(row.get('external_idle_total_duration_s'),1)} s | "
            f"{_fmt(row.get('active_to_idle_ratio_db'),2)} dB | "
            f"{_fmt(row.get('idle_overlap_of_active_percent'),2)}% | "
            f"{_fmt(row.get('load_additional_of_active_percent'),2)}% |"
        )
    lines.extend(
        [
            "",
            "Every exact-rate idle record is analysed at its full physical duration with the same Welch segment-duration and overlap policy as active records. One PSD per physical idle run enters the cross-run median, so longer idle records improve within-run averaging without receiving additional cross-run weight.",
            "",
            "The overlap/additional decomposition is descriptive: min(active,idle) is the idle-overlapping component and max(active-idle,0) is additional variance observed under load. Because active and idle are independent acquisitions, this is not phase-coherent or causal source separation.",
            "",
            "The 5-MS/s curves are the fair cross-workload comparison. Faster Tektronix records are used only to check how much variance lies above the 2.5-MHz PicoScope Nyquist limit.",
            "",
            "Frequencies are reported directly in hertz by Welch using the configured sampling rate in samples per second. The DFT kernel already contains the 2*pi phase factor; no additional continuous-transform 1/(2*pi) or 1/sqrt(2*pi) normalisation is introduced. The derivative of the cumulative distribution with respect to linear frequency is the normalised PSD. The generated per-decade figure instead shows dC/dlog10(f) = ln(10) f dC/df.",
            "",
            "## 2-kS/s energy sufficiency",
            "",
            "| Workload | Setup | 1% minimum tested duration | 0.5% minimum tested duration |",
            "|---|---|---:|---:|",
        ]
    )
    keys = sorted(
        {(row["workload_id"], row["source"], row["workload_label"]) for row in threshold_rows}
    )
    for workload_id, source, label in keys:
        matching = [
            row
            for row in threshold_rows
            if row["workload_id"] == workload_id
            and row["source"] == source
            and row["mode"] == "phase_only"
        ]
        one = next((row for row in matching if abs(float(row["threshold_pct"])-1.0)<1e-12), None)
        half = next((row for row in matching if abs(float(row["threshold_pct"])-0.5)<1e-12), None)
        lines.append(
            f"| {label} | {_source_setup_label(source)} | "
            f"{_fmt(one.get('minimum_passing_duration_s') if one else None,3)} s | "
            f"{_fmt(half.get('minimum_passing_duration_s') if half else None,3)} s |"
        )
    lines.extend(
        [
            "",
            "## Method boundary",
            "",
            "- Common reference: all lower rates are reconstructed from the same 5-MS/s physical execution; this isolates the sampling effect.",
            "- Direct rate validation: the recorded rate sweep consists of separate executions and therefore includes run-to-run, acquisition, offset, and setup effects.",
            "- The short paired-scope records support windows only up to their physical duration; the 104-s GEMM-FP16 analysis remains the long-duration anchor.",
            "- Missing or incomplete workloads are skipped and remain visible in the inventory.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_multi_workload_artifact_summary(
    cfg: MultiWorkloadConfig,
    config_path: Path,
    artifact_outputs: Sequence[Path],
) -> Path:
    """Write current-run artifact provenance before bundle staging."""
    artifact_root = cfg.output_root / "paper_artifacts"
    artifact_summary = artifact_root / "MULTI_WORKLOAD_PAPER_ARTIFACTS_SUMMARY.md"
    expected_bundle_outputs: list[Path] = []
    if cfg.paper.generate_bundles:
        full_zip = artifact_root / "multi_workload_documentation_artifacts.zip"
        review_zip = artifact_root / "multi_workload_documentation_artifacts_review.zip"
        expected_bundle_outputs = [
            full_zip,
            artifact_root / f"{full_zip.name}.sha256",
            review_zip,
            artifact_root / f"{review_zip.name}.sha256",
        ]

    listed_outputs = list(artifact_outputs) + expected_bundle_outputs + [artifact_summary]
    lines = [
        "# Multi-workload paper artifacts",
        "",
        f"Generated with tool `{__version__}` from `{config_path.resolve()}`.",
        "",
        "## Canonical outputs",
        "",
    ]
    expected_bundle_set = set(expected_bundle_outputs)
    for path in sorted(set(listed_outputs), key=lambda item: str(item)):
        if path.exists() or path in expected_bundle_set or path == artifact_summary:
            lines.append(f"- `{path.relative_to(cfg.output_root)}`")
    lines.extend(
        [
            "",
            "The 5-MS/s Tektronix current PSD is the primary cross-workload spectral comparison. Full physical exact-rate idle records are used for direct active/idle/excess artifacts with equal physical-run weighting. Faster Tektronix records are coverage checks, while the common-reference energy analysis reconstructs lower rates from each same physical 5-MS/s record.",
            "",
        ]
    )
    artifact_summary.parent.mkdir(parents=True, exist_ok=True)
    artifact_summary.write_text("\n".join(lines), encoding="utf-8")
    return artifact_summary


def _build_bundles(cfg: MultiWorkloadConfig) -> list[Path]:
    if not cfg.paper.generate_bundles:
        return []
    root = cfg.output_root
    artifact_root = root / "paper_artifacts"
    full_staging = root / ".bundle_full"
    review_staging = root / ".bundle_review"
    for staging in (full_staging, review_staging):
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

    def copy_selected(target: Path, review: bool) -> None:
        for relative in (
            Path("MULTI_WORKLOAD_SUMMARY.md"),
            Path("inventory"),
            Path("psd"),
            Path("common_reference"),
            Path("direct_rate_validation"),
            Path("paper_artifacts"),
            Path("multi_workload_manifest.json"),
        ):
            source = root / relative
            if not source.exists():
                continue
            destination = target / relative
            if source.is_dir():
                shutil.copytree(
                    source,
                    destination,
                    ignore=(
                        shutil.ignore_patterns(
                            "cache",
                            "per_run_common_reference.csv",
                            "*.zip",
                            "*.zip.sha256",
                            "*.npz" if review else "__never__",
                        )
                    ),
                )
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        notice = target / "BUNDLE_NOTICE.md"
        notice.write_text(
            (
                "# Review bundle\n\nLarge binary caches, per-run common-reference rows, and NPZ arrays are omitted. CSV/JSON summaries, paper figures, tables, macros, and provenance remain.\n"
                if review
                else "# Full multi-workload analysis bundle\n\nThe raw Parquet measurement tree and regenerable 1-MS/s caches are not included. Aggregated NPZ arrays and all documentation artifacts are included.\n"
            ),
            encoding="utf-8",
        )
        _write_inventory(target, target / "bundle_inventory.csv")

    copy_selected(full_staging, review=False)
    copy_selected(review_staging, review=True)
    full_zip = artifact_root / "multi_workload_documentation_artifacts.zip"
    review_zip = artifact_root / "multi_workload_documentation_artifacts_review.zip"
    _zip_tree(full_staging, full_zip)
    _zip_tree(review_staging, review_zip)
    full_sha = artifact_root / f"{full_zip.name}.sha256"
    review_sha = artifact_root / f"{review_zip.name}.sha256"
    full_sha.write_text(f"{_sha256_file(full_zip)}  {full_zip.name}\n", encoding="utf-8")
    review_sha.write_text(f"{_sha256_file(review_zip)}  {review_zip.name}\n", encoding="utf-8")
    shutil.rmtree(full_staging)
    shutil.rmtree(review_staging)
    return [full_zip, full_sha, review_zip, review_sha]


def _write_manifest(
    cfg: MultiWorkloadConfig,
    config_path: Path,
    inventory: Sequence[dict[str, Any]],
    contexts: Sequence[tuple[WorkloadSpec, ScopeComparisonConfig]],
) -> Path:
    path = cfg.output_root / "multi_workload_manifest.json"
    payload = {
        "schema_version": _MULTI_WORKLOAD_SCHEMA_VERSION,
        "tool_version": __version__,
        "created_utc": utc_now_iso(),
        "config_path": str(config_path.resolve()),
        "config": normalise_for_json(cfg),
        "package_versions": package_versions(),
        "workload_inventory": inventory,
        "scope_outputs": [
            {
                "workload_id": spec.workload_id,
                "label": spec.label,
                "family": spec.family,
                "precision": spec.precision,
                "scope_config": str(spec.scope_config),
                "scope_output_root": str(scope_cfg.output_root),
                "scope_manifest": str(scope_cfg.output_root / "scope_comparison_manifest.json"),
                "scope_manifest_sha256": (
                    _sha256_file(scope_cfg.output_root / "scope_comparison_manifest.json")
                    if (scope_cfg.output_root / "scope_comparison_manifest.json").is_file()
                    else None
                ),
            }
            for spec, scope_cfg in contexts
        ],
        "method_contract": {
            "cross_workload_psd": "All workloads are compared at the same native 5-MS/s Tektronix rate using active-minus-exact-rate-external-idle current and estimated-power spectra.",
            "active_idle_comparison": "Every exact-rate idle record is analysed at its full physical duration using the same Welch policy as active records. One PSD per physical idle run enters an equal-weight cross-run median. Active/idle overlap and excess are descriptive independent-record comparisons, not phase-coherent source separation.",
            "common_reference": "Lower rates are reconstructed from each physical 5-MS/s record after VHQ conversion to the validated 1-MS/s analysis representation; rates are never treated as separate runs in this stage.",
            "direct_validation": "Directly acquired rate sweeps remain separate physical executions and are compared only as a validation of the real measurement system, not as common-reference samples.",
        },
    }
    write_json(path, payload)
    return path


def run_multi_workload_analysis(
    cfg: MultiWorkloadConfig,
    *,
    config_path: Path,
    selected_workloads: Sequence[str] | None = None,
    force: bool = False,
    artifacts_only: bool = False,
) -> Path:
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    inventory_path = run_multi_workload_inventory(cfg)
    inventory = _inventory_rows(cfg)
    selected_set = set(selected_workloads or [])

    contexts: list[tuple[WorkloadSpec, ScopeComparisonConfig]] = []
    for spec in cfg.workloads:
        if selected_set and spec.workload_id not in selected_set:
            continue
        scope_cfg, status = _load_scope_optional(spec)
        if not _workload_enabled(spec, scope_cfg):
            LOGGER.info("Skipping disabled or unavailable workload %s", spec.workload_id)
            continue
        if scope_cfg is None or not scope_cfg.dataset_root.is_dir():
            LOGGER.warning("Skipping %s: %s", spec.workload_id, status)
            continue
        pairs, _, pair_status = _valid_pairs_at_rate(
            scope_cfg, cfg.psd.comparison_rate_sps
        )
        if len(pairs) < cfg.psd.minimum_pairs:
            LOGGER.warning(
                "Skipping %s: only %d valid pairs at %s (%s)",
                spec.workload_id,
                len(pairs),
                human_rate(cfg.psd.comparison_rate_sps),
                pair_status,
            )
            continue
        contexts.append((spec, scope_cfg))

    if not contexts:
        raise WorkloadUnavailable(
            "No workload has enough valid pairs at the common 5-MS/s rate"
        )

    template_cfg = load_config(cfg.analysis_template_config)
    psd_metrics: list[dict[str, Any]] = []
    band_rows: list[dict[str, Any]] = []
    peak_rows: list[dict[str, Any]] = []
    idle_load_summary_rows: list[dict[str, Any]] = []
    idle_load_band_rows: list[dict[str, Any]] = []
    idle_load_peak_rows: list[dict[str, Any]] = []
    all_common_per_run: list[dict[str, Any]] = []
    all_qc_rows: list[dict[str, Any]] = []

    for spec, scope_cfg in contexts:
        pairs, _, _ = _valid_pairs_at_rate(scope_cfg, cfg.psd.comparison_rate_sps)
        LOGGER.info(
            "Multi-workload %s: %d valid 5-MS/s pairs",
            spec.label,
            len(pairs),
        )
        metrics_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "psd_metrics.json"
        )
        if cfg.psd.enabled and not artifacts_only:
            metrics = _cross_workload_psd_for_workload(
                cfg, spec, scope_cfg, pairs, force=force
            )
        elif metrics_path.is_file():
            metrics = read_json(metrics_path)
        else:
            LOGGER.warning("PSD results missing for %s", spec.label)
            continue
        psd_metrics.append(metrics)
        workload_band_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "frequency_bands.csv"
        )
        if workload_band_path.is_file():
            band_rows.extend(_read_csv(workload_band_path))
        workload_peak_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "dominant_peaks.csv"
        )
        if workload_peak_path.is_file():
            peak_rows.extend(_read_csv(workload_peak_path))
        idle_load_summary_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "idle_load_summary.json"
        )
        if idle_load_summary_path.is_file():
            idle_payload = read_json(idle_load_summary_path)
            idle_load_summary_rows.extend(idle_payload.get("summary", []))
        idle_load_band_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "idle_load_frequency_bands.csv"
        )
        if idle_load_band_path.is_file():
            idle_load_band_rows.extend(_read_csv(idle_load_band_path))
        idle_load_peak_path = (
            cfg.output_root
            / "psd"
            / "per_workload"
            / spec.workload_id
            / "idle_load_peak_classification.csv"
        )
        if idle_load_peak_path.is_file():
            idle_load_peak_rows.extend(_read_csv(idle_load_peak_path))

        if cfg.common_reference.enabled and not artifacts_only:
            run_rows, qc_rows = _run_common_reference_workload(
                cfg,
                template_cfg,
                spec,
                scope_cfg,
                pairs,
                force=force,
            )
            all_common_per_run.extend(run_rows)
            all_qc_rows.extend(qc_rows)

    common_root = cfg.output_root / "common_reference"
    common_root.mkdir(parents=True, exist_ok=True)
    per_run_path = common_root / "per_run_common_reference.csv"
    qc_path = common_root / "cache_energy_qc.csv"
    if all_common_per_run:
        write_csv(per_run_path, all_common_per_run)
        write_csv(qc_path, all_qc_rows)
    elif per_run_path.is_file():
        all_common_per_run = [
            {key: value for key, value in row.items()} for row in _read_csv(per_run_path)
        ]
        for row in all_common_per_run:
            for key in (
                "run", "target_rate_sps", "phase_count", "window_count", "observation_count"
            ):
                if key in row:
                    row[key] = int(float(row[key]))
            for key in (
                "duration_s", "error_pct_median", "error_pct_q05", "error_pct_q95",
                "abs_error_pct_median", "abs_error_pct_q95", "abs_error_pct_max",
            ):
                if key in row:
                    row[key] = float(row[key])

    if all_common_per_run:
        common_summary, fmin_rows, threshold_rows, worst_rows = _summarise_common_reference(
            cfg, all_common_per_run
        )
        write_csv(common_root / "common_reference_summary.csv", common_summary)
        write_csv(common_root / "f_min_by_workload_duration.csv", fmin_rows)
        write_csv(common_root / "highlighted_rate_thresholds.csv", threshold_rows)
        write_csv(common_root / "worst_case_envelope.csv", worst_rows)
    else:
        common_summary = _read_csv(common_root / "common_reference_summary.csv") if (common_root / "common_reference_summary.csv").is_file() else []
        fmin_rows = _read_csv(common_root / "f_min_by_workload_duration.csv") if (common_root / "f_min_by_workload_duration.csv").is_file() else []
        threshold_rows = _read_csv(common_root / "highlighted_rate_thresholds.csv") if (common_root / "highlighted_rate_thresholds.csv").is_file() else []
        worst_rows = _read_csv(common_root / "worst_case_envelope.csv") if (common_root / "worst_case_envelope.csv").is_file() else []
        for collection in (common_summary, fmin_rows, threshold_rows, worst_rows):
            for row in collection:
                for key, value in list(row.items()):
                    if value == "":
                        row[key] = None
                        continue
                    try:
                        if key in {"workload_id", "workload_label", "source", "mode", "selection_rule", "limiting_workloads"}:
                            continue
                        row[key] = float(value)
                    except (TypeError, ValueError):
                        pass

    direct_rows = _direct_rate_validation(cfg, contexts, common_summary)
    direct_root = cfg.output_root / "direct_rate_validation"
    direct_root.mkdir(parents=True, exist_ok=True)
    if direct_rows:
        write_csv(direct_root / "direct_rate_validation.csv", direct_rows)

    high_rate_rows = _high_rate_coverage(contexts)
    if high_rate_rows:
        write_csv(cfg.output_root / "psd" / "high_rate_coverage.csv", high_rate_rows)
    if idle_load_summary_rows:
        write_csv(
            cfg.output_root / "psd" / "idle_load_summary.csv",
            idle_load_summary_rows,
        )
    if idle_load_band_rows:
        write_csv(
            cfg.output_root / "psd" / "idle_load_frequency_bands.csv",
            idle_load_band_rows,
        )
    if idle_load_peak_rows:
        write_csv(
            cfg.output_root / "psd" / "idle_load_peak_classification.csv",
            idle_load_peak_rows,
        )
    idle_load_ratio_rows = (
        _idle_load_log_ratio_rows(cfg, contexts)
        if cfg.psd.idle_load_comparison_enabled
        else []
    )
    if idle_load_ratio_rows:
        write_csv(
            cfg.output_root / "psd" / "idle_load_log_frequency_ratio.csv",
            idle_load_ratio_rows,
        )

    artifact_outputs: list[Path] = []
    if cfg.paper.generate_pdf or cfg.paper.generate_png:
        artifact_outputs.extend(_plot_cross_workload_psd(cfg, contexts, "current"))
        artifact_outputs.extend(_plot_cross_workload_psd(cfg, contexts, "power"))
        if cfg.psd.log_frequency_derivative_enabled:
            artifact_outputs.extend(_plot_log_frequency_variance_density(cfg, contexts))
        if cfg.psd.fine_structure_enabled:
            artifact_outputs.extend(_plot_psd_fine_structure(cfg, contexts))
        if cfg.psd.idle_load_comparison_enabled:
            artifact_outputs.extend(_plot_active_idle_psd(cfg, contexts))
            artifact_outputs.extend(
                _plot_active_idle_ratio(cfg, contexts, idle_load_ratio_rows)
            )
            artifact_outputs.extend(
                _plot_idle_load_band_comparison(
                    cfg, contexts, idle_load_band_rows
                )
            )
        artifact_outputs.extend(_plot_band_fractions(cfg, contexts, band_rows))
        if common_summary:
            artifact_outputs.extend(_plot_two_k_duration(cfg, contexts, common_summary))
            artifact_outputs.extend(_plot_worst_case_two_k(cfg, common_summary))
            artifact_outputs.extend(_plot_fmin(cfg, contexts, fmin_rows, worst_rows))
        if direct_rows:
            artifact_outputs.extend(_plot_direct_validation(cfg, contexts, direct_rows))

    if cfg.paper.generate_tables or cfg.paper.generate_macros:
        table_outputs, macros = _generate_tables_and_macros(
            cfg,
            contexts,
            inventory,
            psd_metrics,
            band_rows,
            peak_rows,
            idle_load_summary_rows,
            idle_load_band_rows,
            idle_load_peak_rows,
            common_summary,
            fmin_rows,
            threshold_rows,
            worst_rows,
            direct_rows,
            high_rate_rows,
        )
        artifact_outputs.extend(table_outputs)
    artifact_outputs.extend([_figure_snippets(cfg), _table_snippets(cfg)])
    summary = _summary_document(
        cfg,
        contexts,
        inventory,
        psd_metrics,
        threshold_rows,
        worst_rows,
        high_rate_rows,
    )
    manifest = _write_manifest(cfg, config_path, inventory, contexts)
    artifact_outputs.extend([summary, manifest, inventory_path])

    # Write current provenance first so both bundles stage the current summary.
    artifact_summary = _write_multi_workload_artifact_summary(
        cfg, config_path, artifact_outputs
    )
    artifact_outputs.append(artifact_summary)
    bundle_outputs = _build_bundles(cfg)
    artifact_outputs.extend(bundle_outputs)
    LOGGER.info("Multi-workload summary: %s", summary)
    LOGGER.info("Multi-workload paper artifacts: %s", artifact_summary)
    return summary
