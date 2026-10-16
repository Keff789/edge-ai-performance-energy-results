from __future__ import annotations

import gc
import hashlib
import json
import math
import re
import shutil
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soxr
from scipy.integrate import cumulative_trapezoid, trapezoid
from scipy.signal import (
    butter,
    coherence,
    correlate,
    correlation_lags,
    csd,
    sosfiltfilt,
    welch,
)

from . import __version__
from .scope_config import ScopeComparisonConfig, SourceCalibration
from .utils import (
    LOGGER,
    human_rate,
    normalise_for_json,
    package_versions,
    quantile,
    stable_hash,
    utc_now_iso,
    write_csv,
    write_json,
)


_RATE_RE = re.compile(r"^(?P<rate>\d+)(?P<suffix>Sps)?$")
_SECTION_RE = re.compile(r"^SectionLength(?P<seconds>\d+(?:\.\d+)?)s$")
_SCOPE_ANALYSIS_SCHEMA_VERSION = 9
_SOURCE_FINGERPRINT_SCHEMA_VERSION = 1
_SOURCE_FINGERPRINT_SAMPLE_BYTES = 65_536
_SOURCE_FINGERPRINT_SAMPLE_COUNT = 5



def _log_optional_percent(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(numeric):
        return "n/a"
    return f"{numeric:+.4f}%"


def _log_pair_result(
    rate: int,
    run: int,
    metrics: dict[str, Any],
    *,
    prefix: str = "Run",
) -> None:
    LOGGER.info(
        "%s %d at %s: raw E %s, selected E %s, active E %s, "
        "incremental E %s, zero=%s (%s mA to %s), "
        "baseline=%s (Pico-Tek %s mA), lag %+0.3f ms",
        prefix,
        run,
        human_rate(rate),
        _log_optional_percent(
            metrics.get("raw_pico_vs_tek_energy_error_pct")
        ),
        _log_optional_percent(metrics.get("pico_vs_tek_energy_error_pct")),
        _log_optional_percent(metrics.get("active_window_energy_error_pct")),
        _log_optional_percent(metrics.get("incremental_energy_error_pct")),
        metrics.get("zero_offset_detection_status", "disabled"),
        (
            f"{float(metrics.get('zero_offset_applied_ma')):+.3f}"
            if metrics.get("zero_offset_applied_ma") is not None
            and np.isfinite(float(metrics.get("zero_offset_applied_ma")))
            else "n/a"
        ),
        metrics.get("zero_offset_target_source", "none"),
        metrics.get("idle_baseline_source", "none"),
        (
            f"{float(metrics.get('idle_baseline_current_difference_ma')):+.3f}"
            if metrics.get("idle_baseline_current_difference_ma") is not None
            and np.isfinite(
                float(metrics.get("idle_baseline_current_difference_ma"))
            )
            else "n/a"
        ),
        float(metrics.get("lag_ms", float("nan"))),
    )


def _format_hz_for_summary(value_hz: float) -> str:
    value = float(value_hz)
    if not np.isfinite(value):
        return "n/a"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.4g} MHz"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.4g} kHz"
    return f"{value:.4g} Hz"


def _format_percent_for_summary(value: float, *, signed: bool = False, decimals: int = 4) -> str:
    numeric = float(value)
    if not np.isfinite(numeric):
        return "n/a"
    sign = "+" if signed else ""
    return f"{numeric:{sign}.{decimals}f}%"


def _format_number_for_summary(value: float, *, decimals: int = 6, suffix: str = "") -> str:
    numeric = float(value)
    if not np.isfinite(numeric):
        return "n/a"
    return f"{numeric:.{decimals}f}{suffix}"


def _sampled_file_digest(
    path: Path,
    *,
    sample_bytes: int = _SOURCE_FINGERPRINT_SAMPLE_BYTES,
    sample_count: int = _SOURCE_FINGERPRINT_SAMPLE_COUNT,
) -> tuple[str, list[int]]:
    """Return a cheap content fingerprint without hashing the whole waveform.

    The cache contract primarily relies on nanosecond mtime/ctime and file size.
    Sampling several fixed byte ranges adds protection against files that were
    replaced while preserving size or coarse timestamps, without rereading tens
    of millions of samples on every invocation.
    """

    stat = path.stat()
    size = int(stat.st_size)
    digest = hashlib.sha256()
    digest.update(f"size={size};samples={sample_count};bytes={sample_bytes}".encode())
    if size <= 0:
        return digest.hexdigest(), []

    chunk = min(int(sample_bytes), size)
    span = max(0, size - chunk)
    if sample_count <= 1 or span == 0:
        offsets = [0]
    else:
        offsets = sorted(
            {int(round(index * span / (sample_count - 1))) for index in range(sample_count)}
        )
    with path.open('rb') as handle:
        for offset in offsets:
            handle.seek(offset)
            payload = handle.read(chunk)
            digest.update(offset.to_bytes(8, 'little', signed=False))
            digest.update(len(payload).to_bytes(8, 'little', signed=False))
            digest.update(payload)
    return digest.hexdigest(), offsets


def _source_file_identity(
    path: Path,
    *,
    parquet_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stat = path.stat()
    sampled_sha256, offsets = _sampled_file_digest(path)
    identity: dict[str, Any] = {
        'path': str(path),
        'file_size_bytes': int(stat.st_size),
        'mtime_ns': int(stat.st_mtime_ns),
        'ctime_ns': int(stat.st_ctime_ns),
        'inode': int(stat.st_ino),
        'device': int(stat.st_dev),
        'sampled_sha256': sampled_sha256,
        'sampled_offsets_bytes': offsets,
        'sample_bytes_per_offset': min(_SOURCE_FINGERPRINT_SAMPLE_BYTES, int(stat.st_size)),
    }
    if parquet_probe is not None:
        for key in ('rows', 'column', 'arrow_type', 'row_groups'):
            if key in parquet_probe:
                identity[key] = parquet_probe[key]
    return identity


def _pair_source_identity(
    tek_path: Path,
    pico_path: Path,
    *,
    tek_probe: dict[str, Any] | None = None,
    pico_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        'fingerprint_schema_version': _SOURCE_FINGERPRINT_SCHEMA_VERSION,
        'tek': _source_file_identity(tek_path, parquet_probe=tek_probe),
        'pico': _source_file_identity(pico_path, parquet_probe=pico_probe),
    }
    identity['fingerprint_sha256'] = stable_hash(identity)
    return identity


def _cache_output_mtime_ns(paths: Sequence[Path]) -> int | None:
    existing = [path.stat().st_mtime_ns for path in paths if path.is_file()]
    return min(existing) if existing else None


def _legacy_cache_is_newer_than_sources(
    source_identity: dict[str, Any],
    required_outputs: Sequence[Path],
) -> bool:
    cache_mtime = _cache_output_mtime_ns(required_outputs)
    if cache_mtime is None:
        return False
    source_mtime = max(
        int(source_identity['tek']['mtime_ns']),
        int(source_identity['pico']['mtime_ns']),
    )
    return source_mtime <= cache_mtime


def _cache_reuse_status(
    *,
    payload: dict[str, Any],
    source_identity: dict[str, Any],
    analysis_config_hash: str,
    required_outputs: Sequence[Path],
    shared_trigger_time_s: float | None,
) -> tuple[bool, str, bool]:
    """Decide whether one cached pair result still matches its sources.

    Returns ``(reuse, reason, upgrade_payload)``.  Legacy v0.5.2 payloads did
    not carry source fingerprints.  They may be reused only when all source
    files are older than every required cache output; in that case the caller
    upgrades the payload in place with the current fingerprint.
    """

    metrics = payload.get('metrics', {})
    cached_schema = int(
        payload.get(
            'scope_analysis_schema_version',
            metrics.get('scope_analysis_schema_version', 0),
        )
    )
    if cached_schema < _SCOPE_ANALYSIS_SCHEMA_VERSION:
        return False, (
            f'analysis_schema_changed:{cached_schema}<'
            f'{_SCOPE_ANALYSIS_SCHEMA_VERSION}'
        ), False

    current_fingerprint = str(source_identity['fingerprint_sha256'])
    cached_fingerprint = payload.get('source_fingerprint_sha256')
    upgrade = False
    if cached_fingerprint is None:
        if not _legacy_cache_is_newer_than_sources(source_identity, required_outputs):
            return False, 'legacy_cache_older_than_source_files', False
        upgrade = True
    elif str(cached_fingerprint) != current_fingerprint:
        return False, 'source_fingerprint_changed', False

    cached_config_hash = payload.get('analysis_config_hash')
    if cached_config_hash is None:
        upgrade = True
    elif str(cached_config_hash) != str(analysis_config_hash):
        return False, 'analysis_config_changed', False

    if shared_trigger_time_s is not None:
        cached_trigger = float(
            metrics.get('shared_trigger_time_s', metrics.get('trigger_time_s', float('nan')))
        )
        if not np.isfinite(cached_trigger) or abs(cached_trigger - shared_trigger_time_s) > 1e-12:
            return False, 'shared_trigger_anchor_changed', False

    reason = 'legacy_cache_upgraded' if upgrade else 'fingerprint_match'
    return True, reason, upgrade

def _require_pyarrow():
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as error:
        raise RuntimeError(
            "The scope-comparison mode requires pyarrow. Activate the common-trace "
            "environment and run `python -m pip install -r requirements.txt`."
        ) from error
    return pa, pq


def _read_parquet_column(path: Path, column: str) -> tuple[np.ndarray, dict[str, Any]]:
    pa, pq = _require_pyarrow()
    parquet_file = pq.ParquetFile(path)
    schema_names = parquet_file.schema_arrow.names
    if column not in schema_names:
        raise ValueError(
            f"Column {column!r} not found in {path}; available columns: {schema_names}"
        )
    table = parquet_file.read(columns=[column], use_threads=True)
    array = table[column].combine_chunks()
    if not pa.types.is_floating(array.type) and not pa.types.is_integer(array.type):
        raise ValueError(f"Column {column!r} in {path} is not numeric: {array.type}")
    values = np.asarray(array.to_numpy(zero_copy_only=False), dtype=np.float64)
    metadata = {
        "path": str(path),
        "rows": int(values.size),
        "column": column,
        "arrow_type": str(array.type),
        "row_groups": int(parquet_file.num_row_groups),
        "file_size_bytes": int(path.stat().st_size),
    }
    return values, metadata


def _probe_parquet_column(path: Path, column: str) -> dict[str, Any]:
    """Read only the Parquet footer/schema for inexpensive input validation.

    A file that is still being written commonly has no readable footer yet.  Such
    files are therefore classified as incomplete without touching the source
    directory or waiting for the acquisition process.
    """

    pa, pq = _require_pyarrow()
    if not path.is_file():
        raise FileNotFoundError(path)
    file_size = int(path.stat().st_size)
    if file_size <= 0:
        raise ValueError(f"Empty Parquet file: {path}")
    parquet_file = pq.ParquetFile(path)
    schema_names = parquet_file.schema_arrow.names
    if column not in schema_names:
        raise ValueError(
            f"Column {column!r} not found in {path}; available columns: {schema_names}"
        )
    field = parquet_file.schema_arrow.field(column)
    if not pa.types.is_floating(field.type) and not pa.types.is_integer(field.type):
        raise ValueError(f"Column {column!r} in {path} is not numeric: {field.type}")
    rows = int(parquet_file.metadata.num_rows)
    return {
        "path": str(path),
        "rows": rows,
        "column": column,
        "arrow_type": str(field.type),
        "row_groups": int(parquet_file.num_row_groups),
        "file_size_bytes": file_size,
    }


def _pattern_parts(pattern: str) -> tuple[str, str]:
    prefix, suffix = pattern.split("{run}", 1)
    return prefix, suffix


def _discover_ids(directory: Path, pattern: str) -> dict[int, Path]:
    prefix, suffix = _pattern_parts(pattern)
    result: dict[int, Path] = {}
    for path in directory.glob(f"{prefix}*{suffix}"):
        if not path.is_file():
            continue
        middle = path.name[len(prefix) :]
        if suffix:
            middle = middle[: -len(suffix)]
        if middle.isdigit():
            result[int(middle)] = path
    return result


def _parse_rate_directory_name(name: str) -> tuple[int, str] | None:
    """Parse both legacy ``<rate>Sps`` and scope-native bare ``<rate>`` names.

    The Tektronix acquisition scripts changed naming convention during the
    campaign.  Low-rate records use names such as ``1000000Sps`` while the
    later high-rate records use bare integer names such as ``125000000``.
    Both represent samples per second and must be treated identically.
    """

    match = _RATE_RE.fullmatch(name)
    if not match:
        return None
    style = "sps_suffix" if match.group("suffix") else "bare_integer"
    return int(match.group("rate")), style


def discover_rate_directories(cfg: ScopeComparisonConfig) -> list[tuple[int, Path]]:
    root = cfg.dataset_root
    direct = _parse_rate_directory_name(root.name)
    if direct is not None and root.is_dir():
        return [(direct[0], root)]

    if cfg.rate_directories == "auto":
        if not root.is_dir():
            raise FileNotFoundError(root)
        by_rate: dict[int, tuple[Path, str]] = {}
        for child in root.iterdir():
            if not child.is_dir():
                continue
            parsed = _parse_rate_directory_name(child.name)
            if parsed is None:
                continue
            rate, style = parsed
            existing = by_rate.get(rate)
            if existing is None:
                by_rate[rate] = (child, style)
                continue
            # Avoid output collisions if both naming conventions exist for one
            # rate.  Prefer the explicit Sps directory and document the choice.
            existing_path, existing_style = existing
            if style == "sps_suffix" and existing_style != "sps_suffix":
                LOGGER.warning(
                    "Duplicate rate directories for %s: preferring %s over %s",
                    human_rate(rate), child, existing_path,
                )
                by_rate[rate] = (child, style)
            else:
                LOGGER.warning(
                    "Duplicate rate directories for %s: keeping %s and ignoring %s",
                    human_rate(rate), existing_path, child,
                )
        if not by_rate:
            raise FileNotFoundError(
                f"No rate directories named <integer>Sps or <integer> found below {root}"
            )
        return sorted((rate, item[0]) for rate, item in by_rate.items())

    result = []
    seen_rates: set[int] = set()
    for name in cfg.rate_directories:
        path = root / name
        parsed = _parse_rate_directory_name(name)
        if parsed is None:
            raise ValueError(
                f"Rate-directory name does not match <integer>Sps or <integer>: {name}"
            )
        rate, _ = parsed
        if rate in seen_rates:
            raise ValueError(f"Duplicate configured sampling rate: {rate} S/s")
        if not path.is_dir():
            raise FileNotFoundError(path)
        seen_rates.add(rate)
        result.append((rate, path))
    return sorted(result)


def _section_marker_seconds(directory: Path) -> float | None:
    for child in directory.iterdir():
        match = _SECTION_RE.fullmatch(child.name)
        if match:
            return float(match.group("seconds"))
    return None


def discover_pairs(
    cfg: ScopeComparisonConfig,
    directory: Path,
    selected_runs: Sequence[int] | None,
) -> tuple[list[tuple[int, Path, Path]], dict[str, Any]]:
    tek = _discover_ids(directory, cfg.tek.file_pattern)
    pico = _discover_ids(directory, cfg.pico.file_pattern)
    all_ids = sorted(set(tek) | set(pico))
    all_paired = set(tek) & set(pico)
    missing_tek = set(pico) - set(tek)
    missing_pico = set(tek) - set(pico)
    if selected_runs is not None:
        wanted = set(selected_runs)
        paired = sorted(all_paired & wanted)
        missing_tek &= wanted
        missing_pico &= wanted
    else:
        paired = sorted(all_paired)
    inventory = {
        "directory": str(directory),
        "tek_run_ids": sorted(tek),
        "pico_run_ids": sorted(pico),
        "all_run_ids": all_ids,
        "selected_run_ids": None if selected_runs is None else sorted(set(selected_runs)),
        "paired_run_ids": paired,
        "missing_tek_run_ids": sorted(missing_tek),
        "missing_pico_run_ids": sorted(missing_pico),
        "all_missing_tek_run_ids": sorted(set(pico) - set(tek)),
        "all_missing_pico_run_ids": sorted(set(tek) - set(pico)),
        "section_marker_seconds": _section_marker_seconds(directory),
    }
    if (inventory["missing_tek_run_ids"] or inventory["missing_pico_run_ids"]) and not cfg.input_policy.ignore_unpaired_runs:
        raise FileNotFoundError(
            f"Unpaired Tek/Pico files found in {directory}: "
            f"missing Tek={inventory['missing_tek_run_ids']}, "
            f"missing Pico={inventory['missing_pico_run_ids']}"
        )
    if not paired and not cfg.input_policy.ignore_empty_rate_directories:
        raise FileNotFoundError(f"No paired Tek/Pico Parquet files found in {directory}")
    return [(run, tek[run], pico[run]) for run in paired], inventory


def _source_rates_for_directory(
    cfg: ScopeComparisonConfig,
    directory_rate_sps: int | float,
) -> tuple[float, float]:
    """Return the physical Tektronix and PicoScope sampling rates.

    The measurement directory names encode the Tektronix rate.  Up to the
    configured PicoScope ceiling both devices use the same rate; above that
    ceiling the PicoScope remains fixed while the Tektronix rate increases.
    """

    tek_rate, pico_rate = cfg.source_rates.rates_for_directory(
        float(directory_rate_sps)
    )
    if tek_rate <= 0 or pico_rate <= 0:
        raise ValueError("Both source sampling rates must be positive")
    return float(tek_rate), float(pico_rate)


def _duration_match_tolerance_s(
    cfg: ScopeComparisonConfig,
    tek_rate_sps: float,
    pico_rate_sps: float,
    duration_s: float,
) -> float:
    sample_based = max(
        cfg.input_policy.duration_tolerance_samples / tek_rate_sps,
        cfg.input_policy.duration_tolerance_samples / pico_rate_sps,
    )
    relative = cfg.source_rates.duration_tolerance_relative * max(
        float(duration_s), 0.0
    )
    return max(
        float(cfg.source_rates.duration_tolerance_s),
        float(sample_based),
        float(relative),
    )


def _preflight_pair(
    cfg: ScopeComparisonConfig,
    rate: int,
    run: int,
    tek_path: Path,
    pico_path: Path,
    section_marker_seconds: float | None,
) -> dict[str, Any]:
    """Validate one pair without loading the waveform payloads.

    Equal *sample counts* are not required.  The two oscilloscopes may use
    different sampling rates, especially above the PicoScope's 5-MS/s ceiling.
    The scientific contract is equal physical record duration and a common
    hardware-trigger position.
    """

    tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
    row: dict[str, Any] = {
        "rate_sps": rate,
        "directory_rate_sps": rate,
        "tek_rate_sps": tek_rate,
        "pico_rate_sps": pico_rate,
        "run": run,
        "tek_path": str(tek_path),
        "pico_path": str(pico_path),
        "status": "valid",
        "reason": "",
    }
    try:
        tek = _probe_parquet_column(tek_path, cfg.tek.column)
        pico = _probe_parquet_column(pico_path, cfg.pico.column)
        source_identity = _pair_source_identity(
            tek_path,
            pico_path,
            tek_probe=tek,
            pico_probe=pico,
        )
        tek_rows = int(tek["rows"])
        pico_rows = int(pico["rows"])
        tek_duration = tek_rows / tek_rate
        pico_duration = pico_rows / pico_rate
        duration_difference = pico_duration - tek_duration
        nominal_duration = min(tek_duration, pico_duration)
        duration_tolerance = _duration_match_tolerance_s(
            cfg, tek_rate, pico_rate, nominal_duration
        )
        row.update(
            {
                "tek_rows": tek_rows,
                "pico_rows": pico_rows,
                "tek_duration_s": tek_duration,
                "pico_duration_s": pico_duration,
                "duration_difference_s": duration_difference,
                "duration_difference_ppm": (
                    1e6 * duration_difference / nominal_duration
                    if nominal_duration > 0
                    else float("nan")
                ),
                "duration_match_tolerance_s": duration_tolerance,
                "common_nominal_duration_s": nominal_duration,
                "tek_file_size_bytes": int(tek["file_size_bytes"]),
                "pico_file_size_bytes": int(pico["file_size_bytes"]),
                "tek_mtime_ns": int(source_identity["tek"]["mtime_ns"]),
                "pico_mtime_ns": int(source_identity["pico"]["mtime_ns"]),
                "tek_ctime_ns": int(source_identity["tek"]["ctime_ns"]),
                "pico_ctime_ns": int(source_identity["pico"]["ctime_ns"]),
                "tek_sampled_sha256": source_identity["tek"]["sampled_sha256"],
                "pico_sampled_sha256": source_identity["pico"]["sampled_sha256"],
                "source_fingerprint_schema_version": _SOURCE_FINGERPRINT_SCHEMA_VERSION,
                "source_fingerprint_sha256": source_identity["fingerprint_sha256"],
                "source_identity": source_identity,
            }
        )
        if tek_rows < cfg.input_policy.minimum_rows_per_file:
            raise ValueError(
                f"Tek file has only {tek_rows} rows; minimum is "
                f"{cfg.input_policy.minimum_rows_per_file}"
            )
        if pico_rows < cfg.input_policy.minimum_rows_per_file:
            raise ValueError(
                f"Pico file has only {pico_rows} rows; minimum is "
                f"{cfg.input_policy.minimum_rows_per_file}"
            )
        if cfg.input_policy.require_equal_sample_counts and tek_rows != pico_rows:
            raise ValueError(
                f"sample-count mismatch Tek={tek_rows} Pico={pico_rows}"
            )
        if abs(duration_difference) > duration_tolerance:
            raise ValueError(
                "record-duration mismatch "
                f"Tek={tek_duration:.12g}s at {tek_rate:g}S/s, "
                f"Pico={pico_duration:.12g}s at {pico_rate:g}S/s, "
                f"tolerance={duration_tolerance:.3g}s"
            )

        expected_duration = cfg.input_policy.expected_duration_s
        duration_source = "configured"
        if expected_duration is None:
            expected_duration = section_marker_seconds
            duration_source = (
                "section_marker" if section_marker_seconds is not None else "auto_pending"
            )
        row["expected_duration_s"] = expected_duration
        row["duration_source"] = duration_source
        row["duration_tolerance_samples"] = (
            cfg.input_policy.duration_tolerance_samples
        )
        if expected_duration is not None:
            tek_expected_rows = int(round(float(expected_duration) * tek_rate))
            pico_expected_rows = int(round(float(expected_duration) * pico_rate))
            row["tek_expected_rows"] = tek_expected_rows
            row["pico_expected_rows"] = pico_expected_rows
            tolerance = cfg.input_policy.duration_tolerance_samples
            if abs(tek_rows - tek_expected_rows) > tolerance:
                raise ValueError(
                    f"Tek row count {tek_rows} does not match expected "
                    f"{tek_expected_rows} +/- {tolerance}"
                )
            if abs(pico_rows - pico_expected_rows) > tolerance:
                raise ValueError(
                    f"Pico row count {pico_rows} does not match expected "
                    f"{pico_expected_rows} +/- {tolerance}"
                )
    except Exception as error:
        row["status"] = "skipped"
        row["reason"] = f"{type(error).__name__}: {error}"
    return row


def _apply_auto_duration_inference(
    cfg: ScopeComparisonConfig,
    rate: int,
    section_marker_seconds: float | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Infer the nominal physical record duration for one rate directory.

    The Tektronix and PicoScope row counts can differ by large integer factors.
    Completeness is therefore inferred from record duration, not from equal row
    counts.  All calculations remain read-only.
    """

    tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
    if cfg.input_policy.expected_duration_s is not None:
        expected_duration = float(cfg.input_policy.expected_duration_s)
        return {
            "duration_source": "configured",
            "expected_duration_s": expected_duration,
            "tek_expected_rows": int(round(expected_duration * tek_rate)),
            "pico_expected_rows": int(round(expected_duration * pico_rate)),
            "support_pairs": sum(row.get("status") == "valid" for row in rows),
        }
    if section_marker_seconds is not None:
        expected_duration = float(section_marker_seconds)
        return {
            "duration_source": "section_marker",
            "expected_duration_s": expected_duration,
            "tek_expected_rows": int(round(expected_duration * tek_rate)),
            "pico_expected_rows": int(round(expected_duration * pico_rate)),
            "support_pairs": sum(row.get("status") == "valid" for row in rows),
        }

    valid = [row for row in rows if row.get("status") == "valid"]
    durations = [
        0.5 * (float(row["tek_duration_s"]) + float(row["pico_duration_s"]))
        for row in valid
    ]
    if not durations:
        return {
            "duration_source": "unavailable",
            "expected_duration_s": None,
            "tek_expected_rows": None,
            "pico_expected_rows": None,
            "support_pairs": 0,
        }

    # Quantise only for modal grouping.  Nanosecond precision is far beyond the
    # duration contract needed for these oscilloscope records.
    rounded = [round(value, 9) for value in durations]
    frequency = Counter(rounded)
    expected_duration, support = sorted(
        frequency.items(), key=lambda item: (-item[1], -item[0])
    )[0]
    required_support = max(2, int(math.ceil(len(durations) / 2.0)))
    if support >= required_support:
        tek_expected_rows = int(round(expected_duration * tek_rate))
        pico_expected_rows = int(round(expected_duration * pico_rate))
        for row in valid:
            tolerance_s = _duration_match_tolerance_s(
                cfg, tek_rate, pico_rate, expected_duration
            )
            row["expected_duration_s"] = float(expected_duration)
            row["tek_expected_rows"] = tek_expected_rows
            row["pico_expected_rows"] = pico_expected_rows
            row["duration_source"] = "inferred_modal_duration"
            if (
                abs(float(row["tek_duration_s"]) - expected_duration) > tolerance_s
                or abs(float(row["pico_duration_s"]) - expected_duration) > tolerance_s
            ):
                row["status"] = "skipped"
                row["reason"] = (
                    "ValueError: physical record duration does not match inferred "
                    f"per-rate duration {expected_duration:.12g}s +/- {tolerance_s:.3g}s"
                )
        return {
            "duration_source": "inferred_modal_duration",
            "expected_duration_s": float(expected_duration),
            "tek_expected_rows": tek_expected_rows,
            "pico_expected_rows": pico_expected_rows,
            "support_pairs": int(support),
            "candidate_pairs": len(durations),
        }

    for row in valid:
        row["expected_duration_s"] = float(row["common_nominal_duration_s"])
        row["tek_expected_rows"] = int(row["tek_rows"])
        row["pico_expected_rows"] = int(row["pico_rows"])
        row["duration_source"] = "observed_pair_duration_no_consensus"
    return {
        "duration_source": "observed_pair_duration_no_consensus",
        "expected_duration_s": None,
        "tek_expected_rows": None,
        "pico_expected_rows": None,
        "support_pairs": int(support),
        "candidate_pairs": len(durations),
    }

def _calibrate(values: np.ndarray, source: SourceCalibration) -> np.ndarray:
    calibrated = (np.asarray(values, dtype=np.float64) + source.offset_raw) * source.gain_a_per_raw
    if not np.all(np.isfinite(calibrated)):
        raise ValueError(f"Non-finite calibrated current values for {source.display_name}")
    return calibrated


def _power_from_current(current_a: np.ndarray, cfg: ScopeComparisonConfig) -> tuple[np.ndarray, np.ndarray]:
    voltage = np.asarray(cfg.voltage_model.voltage(current_a), dtype=np.float64)
    power = voltage * current_a
    return voltage, power


def _configured_shared_trigger_time(
    cfg: ScopeComparisonConfig,
    rate_sps: int,
    duration_s: float,
) -> tuple[float | None, str]:
    """Resolve a configured hardware-trigger anchor.

    Current-only Parquet exports do not contain the GPIO trigger channel.  For
    periodic workloads a current-step detector can therefore be ambiguous even
    though both scopes were triggered at the same hardware position.  The
    anchor can be supplied as an absolute time, a record fraction, or a per-rate
    map.  The legacy first-valid-run detector remains available as a fallback.
    """

    mode = cfg.windows.shared_anchor_mode
    if mode == "fixed_time":
        value = cfg.windows.trigger_time_s
        source = "configured_fixed_time"
    elif mode == "fixed_fraction":
        value = (
            None
            if cfg.windows.trigger_fraction is None
            else float(cfg.windows.trigger_fraction) * float(duration_s)
        )
        source = "configured_fixed_fraction"
    elif mode == "per_rate_time":
        value = dict(cfg.windows.trigger_time_by_rate_s).get(int(rate_sps))
        source = "configured_per_rate_time"
    else:
        return None, "first_valid_detection"

    if value is None:
        return None, f"{source}_missing"
    value = float(value)
    if not (0.0 <= value <= float(duration_s)):
        raise ValueError(
            f"Configured trigger anchor {value:.9g} s lies outside the "
            f"{duration_s:.9g}-s record at {human_rate(rate_sps)}"
        )
    return value, source


def _external_idle_directory_map(
    cfg: ScopeComparisonConfig,
) -> dict[int, Path]:
    """Return exact-rate directories from the optional external idle tree.

    The active workload and the idle data remain separate data sets.  The map
    is used only for a rate-matched fallback and for independent baseline
    diagnostics; records are never concatenated.
    """

    if not cfg.external_idle.enabled or cfg.external_idle.dataset_root is None:
        return {}
    idle_cfg = replace(
        cfg,
        dataset_root=cfg.external_idle.dataset_root,
        output_root=cfg.output_root / "external_idle",
        external_idle=replace(cfg.external_idle, enabled=False),
    )
    try:
        return dict(discover_rate_directories(idle_cfg))
    except FileNotFoundError:
        LOGGER.warning(
            "External idle tree is enabled but no rate directories were found below %s",
            cfg.external_idle.dataset_root,
        )
        return {}


def _stream_calibrated_mean(
    path: Path,
    source: SourceCalibration,
    *,
    batch_size: int = 1_048_576,
) -> tuple[float, int]:
    """Return the calibrated mean without materialising a full waveform.

    This lightweight pass is used only to diagnose an additive zero offset from
    independently recorded idle pairs.  It keeps the measurement tree read-only
    and avoids loading tens of millions of high-rate samples into RAM.
    """

    pa, pq = _require_pyarrow()
    parquet_file = pq.ParquetFile(path)
    if source.column not in parquet_file.schema_arrow.names:
        raise ValueError(
            f"Column {source.column!r} not found in {path}; available columns: "
            f"{parquet_file.schema_arrow.names}"
        )
    total = 0.0
    count = 0
    for batch in parquet_file.iter_batches(
        batch_size=int(batch_size),
        columns=[source.column],
        use_threads=True,
    ):
        array = batch.column(0)
        if not pa.types.is_floating(array.type) and not pa.types.is_integer(array.type):
            raise ValueError(
                f"Column {source.column!r} in {path} is not numeric: {array.type}"
            )
        values = np.asarray(array.to_numpy(zero_copy_only=False), dtype=np.float64)
        calibrated = source.calibrate(values)
        finite = np.isfinite(calibrated)
        if not np.all(finite):
            calibrated = calibrated[finite]
        total += float(np.sum(calibrated, dtype=np.float64))
        count += int(calibrated.size)
    if count <= 0:
        raise ValueError(f"No finite samples in {path}")
    return total / count, count


def _median_absolute_deviation(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    median = float(np.median(values))
    return float(np.median(np.abs(values - median)))


def _derive_zero_offset_decision(
    config: Any,
    rate_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Return the pure decision part of the adaptive zero-offset model.

    Keeping the statistical decision separate from Parquet I/O makes the safety
    contract directly testable: only a material, bounded, same-sign offset that
    is stable within and across several exact-rate idle campaigns may be applied.
    """

    # A populated rate is part of the evidence even when its within-rate spread
    # fails the stability gate.  We must not silently discard an inconvenient
    # rate and then declare the remaining subset stable.  The correction is
    # therefore applied only when every sufficiently populated exact-rate idle
    # campaign is eligible for the session model.
    candidate_rates = [
        row
        for row in rate_rows
        if bool(
            row.get(
                "candidate_for_session_model",
                row.get("eligible_for_session_model", False),
            )
        )
    ]
    eligible_rates = [
        row for row in candidate_rates if bool(row.get("eligible_for_session_model"))
    ]
    rate_medians = np.asarray(
        [float(row["offset_median_ma"]) for row in candidate_rates],
        dtype=np.float64,
    )
    offset_ma = (
        float(np.median(rate_medians)) if rate_medians.size else float("nan")
    )
    total_pairs = int(
        sum(int(row.get("valid_offset_pairs", 0)) for row in candidate_rates)
    )
    max_rate_deviation_ma = (
        float(np.max(np.abs(rate_medians - offset_ma)))
        if rate_medians.size and np.isfinite(offset_ma)
        else float("nan")
    )
    if rate_medians.size and np.isfinite(offset_ma) and offset_ma != 0.0:
        expected_sign = math.copysign(1.0, offset_ma)
        sign_consistency = float(
            np.mean(np.sign(rate_medians) == expected_sign)
        )
    elif rate_medians.size:
        sign_consistency = float(np.mean(rate_medians == 0.0))
    else:
        sign_consistency = float("nan")

    within_rate_mads = np.asarray(
        [float(row.get("offset_mad_ma", float("nan"))) for row in candidate_rates],
        dtype=np.float64,
    )
    within_rate_mads = within_rate_mads[np.isfinite(within_rate_mads)]
    median_within_rate_mad_ma = (
        float(np.median(within_rate_mads))
        if within_rate_mads.size
        else float("nan")
    )
    uncertainty_ma = (
        float(max(max_rate_deviation_ma, 1.4826 * median_within_rate_mad_ma))
        if np.isfinite(max_rate_deviation_ma)
        and np.isfinite(median_within_rate_mad_ma)
        else (
            max_rate_deviation_ma
            if np.isfinite(max_rate_deviation_ma)
            else median_within_rate_mad_ma
        )
    )

    checks = {
        "all_populated_rates_eligible": {
            "value": len(eligible_rates),
            "candidate_rates": len(candidate_rates),
            "limit": len(candidate_rates),
            "pass": bool(candidate_rates) and len(eligible_rates) == len(candidate_rates),
            "failed_rates_sps": [
                int(row["rate_sps"])
                for row in candidate_rates
                if not bool(row.get("eligible_for_session_model"))
            ],
        },
        "minimum_reference_rates": {
            "value": len(candidate_rates),
            "limit": int(config.minimum_reference_rates),
            "pass": len(candidate_rates) >= config.minimum_reference_rates,
        },
        "minimum_reference_pairs_total": {
            "value": total_pairs,
            "limit": int(config.minimum_reference_pairs_total),
            "pass": total_pairs >= config.minimum_reference_pairs_total,
        },
        "minimum_abs_offset_ma": {
            "value": abs(offset_ma) if np.isfinite(offset_ma) else None,
            "limit": float(config.minimum_abs_offset_ma),
            "pass": bool(
                np.isfinite(offset_ma)
                and abs(offset_ma) >= config.minimum_abs_offset_ma
            ),
        },
        "maximum_abs_correction_ma": {
            "value": abs(offset_ma) if np.isfinite(offset_ma) else None,
            "limit": float(config.maximum_abs_correction_ma),
            "pass": bool(
                np.isfinite(offset_ma)
                and abs(offset_ma) <= config.maximum_abs_correction_ma
            ),
        },
        "maximum_rate_median_deviation_ma": {
            "value": max_rate_deviation_ma,
            "limit": float(config.maximum_rate_median_deviation_ma),
            "pass": bool(
                np.isfinite(max_rate_deviation_ma)
                and max_rate_deviation_ma
                <= config.maximum_rate_median_deviation_ma
            ),
        },
        "minimum_sign_consistency_fraction": {
            "value": sign_consistency,
            "limit": float(config.minimum_sign_consistency_fraction),
            "pass": bool(
                np.isfinite(sign_consistency)
                and sign_consistency
                >= config.minimum_sign_consistency_fraction
            ),
        },
    }
    evidence_sufficient = all(bool(item["pass"]) for item in checks.values())
    detected = bool(evidence_sufficient)
    applied = bool(detected and config.apply_when_detected)

    if not candidate_rates:
        status = "unavailable_no_eligible_rate_evidence"
    elif not checks["all_populated_rates_eligible"]["pass"]:
        status = "offset_evidence_contains_unstable_rates"
    elif not checks["minimum_reference_rates"]["pass"]:
        status = "insufficient_reference_rates"
    elif not checks["minimum_reference_pairs_total"]["pass"]:
        status = "insufficient_reference_pairs"
    elif not checks["minimum_abs_offset_ma"]["pass"]:
        status = "no_material_offset_detected"
    elif not checks["maximum_abs_correction_ma"]["pass"]:
        status = "offset_exceeds_safety_bound_not_applied"
    elif not checks["maximum_rate_median_deviation_ma"]["pass"]:
        status = "offset_detected_but_rate_unstable"
    elif not checks["minimum_sign_consistency_fraction"]["pass"]:
        status = "offset_detected_but_sign_inconsistent"
    elif detected and not config.apply_when_detected:
        status = "stable_offset_detected_not_applied"
    else:
        status = "stable_offset_detected_and_corrected"

    applied_offset_a = (
        offset_ma / 1000.0
        if applied and np.isfinite(offset_ma)
        else 0.0
    )
    confidence = "none"
    if detected:
        strict_rate_count = len(candidate_rates) >= max(3, config.minimum_reference_rates)
        strict_pair_count = total_pairs >= max(20, config.minimum_reference_pairs_total)
        strict_stability = bool(
            np.isfinite(max_rate_deviation_ma)
            and max_rate_deviation_ma <= 0.5 * config.maximum_rate_median_deviation_ma
        )
        confidence = (
            "high"
            if strict_rate_count and strict_pair_count and strict_stability
            else "moderate"
        )

    return {
        "status": status,
        "offset_detected": detected,
        "correction_applied": applied,
        "offset_estimate_a": offset_ma / 1000.0 if np.isfinite(offset_ma) else None,
        "offset_estimate_ma": offset_ma if np.isfinite(offset_ma) else None,
        "offset_applied_a": applied_offset_a,
        "offset_applied_ma": 1000.0 * applied_offset_a,
        "offset_uncertainty_ma": uncertainty_ma,
        "confidence": confidence,
        "reference_rate_count": len(candidate_rates),
        "reference_rates_sps": [
            int(row["rate_sps"]) for row in candidate_rates
        ],
        "reference_pair_count": total_pairs,
        "rate_median_max_deviation_ma": max_rate_deviation_ma,
        "rate_sign_consistency_fraction": sign_consistency,
        "median_within_rate_mad_ma": median_within_rate_mad_ma,
        "checks": checks,
    }


def _build_workload_session_shift_zero_model(
    cfg: ScopeComparisonConfig,
    workload_dirs: dict[int, Path],
    external_idle_dirs: dict[int, Path],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Detect a session-specific Tek zero shift from workload/idle contrast.

    A correctly zeroed external idle campaign can legitimately show only the
    small residual path difference between the instruments.  If the workload
    campaign was captured in another probe-zero state, its paired Pico-minus-
    Tek mean difference is shifted by an additional nearly constant amount.
    The rate-wise correction evidence is therefore

        median(Pico-Tek | workload) - median(Pico-Tek | external idle).

    This deliberately does *not* force the corrected workload difference to
    zero; it preserves the residual instrument-path difference observed in the
    correctly zeroed idle campaign.  Workload and idle files remain read-only,
    all raw metrics are preserved, no gain is fitted, and the result is marked
    as a non-independent post-hoc session-salvage correction.
    """

    config = cfg.zero_offset_correction
    root = cfg.output_root / "zero_correction"
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "zero_offset_model.json"
    pair_path = root / "zero_offset_pair_evidence.csv"
    rate_path = root / "zero_offset_rate_evidence.csv"
    pair_rows: list[dict[str, Any]] = []
    rate_rows: list[dict[str, Any]] = []
    pair_fieldnames = [
        "evidence_role",
        "rate_sps",
        "run",
        "tek_path",
        "pico_path",
        "source_fingerprint_sha256",
        "tek_samples_used",
        "pico_samples_used",
        "tek_mean_current_a_raw",
        "pico_mean_current_a_raw",
        "pico_minus_tek_current_ma_raw",
        "status",
        "reason",
    ]
    rate_fieldnames = [
        "rate_sps",
        "workload_directory",
        "external_idle_directory",
        "workload_candidate_pairs",
        "workload_valid_offset_pairs",
        "external_idle_candidate_pairs",
        "external_idle_valid_offset_pairs",
        "workload_pico_minus_tek_median_ma",
        "external_idle_pico_minus_tek_median_ma",
        "offset_median_ma",
        "offset_q05_ma",
        "offset_q95_ma",
        "offset_q90_span_ma",
        "offset_mad_ma",
        "workload_difference_q90_span_ma",
        "external_idle_difference_q90_span_ma",
        "valid_offset_pairs",
        "candidate_for_session_model",
        "eligible_for_session_model",
        "eligibility_reason",
    ]

    def finish(model: dict[str, Any]) -> dict[str, Any]:
        payload = dict(model)
        payload["model_hash"] = stable_hash(payload)
        write_csv(pair_path, pair_rows, fieldnames=pair_fieldnames)
        write_csv(rate_path, rate_rows, fieldnames=rate_fieldnames)
        write_json(model_path, payload)
        return payload

    base_model: dict[str, Any] = {
        "model_schema_version": 2,
        "enabled": bool(config.enabled),
        "target_source": config.target_source,
        "reference_source": config.detection_source,
        "application_scope": "workload_only",
        "apply_to_external_idle": False,
        "raw_values_preserved": bool(config.preserve_raw_metrics),
        "independent_reference": False,
        "validation_independence": (
            "post_hoc_workload_minus_external_idle_session_shift_not_independent"
        ),
        "correction_model": "additive_current_offset_only",
        "gain_correction_applied": False,
    }

    common_rates = sorted(set(workload_dirs) & set(external_idle_dirs))
    if not config.enabled:
        return finish(
            {
                **base_model,
                "status": "disabled",
                "offset_detected": False,
                "correction_applied": False,
                "offset_estimate_a": 0.0,
                "offset_estimate_ma": 0.0,
                "offset_applied_a": 0.0,
                "offset_applied_ma": 0.0,
                "offset_uncertainty_ma": 0.0,
                "confidence": "none",
                "reference_rate_count": 0,
                "reference_rates_sps": [],
                "reference_pair_count": 0,
                "source_fingerprint_sha256": "",
                "analysis_config_hash": "",
                "checks": {},
                "interpretation": "Adaptive zero-offset correction disabled.",
            }
        )
    if not common_rates:
        return finish(
            {
                **base_model,
                "status": "unavailable_no_rate_matched_workload_idle_pairs",
                "offset_detected": False,
                "correction_applied": False,
                "offset_estimate_a": None,
                "offset_estimate_ma": None,
                "offset_applied_a": 0.0,
                "offset_applied_ma": 0.0,
                "offset_uncertainty_ma": None,
                "confidence": "none",
                "reference_rate_count": 0,
                "reference_rates_sps": [],
                "reference_pair_count": 0,
                "source_fingerprint_sha256": "",
                "analysis_config_hash": "",
                "checks": {},
                "interpretation": (
                    "No exact-rate overlap exists between workload and external "
                    "idle trees; no session-shift correction was applied."
                ),
            }
        )

    def valid_catalog(
        base_cfg: ScopeComparisonConfig,
        rate: int,
        directory: Path,
        role: str,
    ) -> tuple[list[tuple[int, Path, Path]], dict[int, dict[str, Any]], list[dict[str, Any]]]:
        local_cfg = replace(
            base_cfg,
            dataset_root=(
                base_cfg.external_idle.dataset_root or directory.parent
                if role == "external_idle"
                else base_cfg.dataset_root
            ),
            output_root=base_cfg.output_root / "zero_correction" / "preflight",
            external_idle=replace(base_cfg.external_idle, enabled=False),
            zero_offset_correction=replace(config, enabled=False),
        )
        pairs, inventory = discover_pairs(local_cfg, directory, None)
        section_seconds = inventory.get("section_marker_seconds")
        preflight_rows = [
            _preflight_pair(
                local_cfg,
                int(rate),
                run,
                tek_path,
                pico_path,
                section_seconds,
            )
            for run, tek_path, pico_path in pairs
        ]
        _apply_auto_duration_inference(
            local_cfg,
            int(rate),
            section_seconds,
            preflight_rows,
        )
        by_run = {int(row["run"]): row for row in preflight_rows}
        valid_pairs = [
            pair for pair in pairs if by_run[int(pair[0])]["status"] == "valid"
        ]
        identities: list[dict[str, Any]] = []
        for run, tek_path, pico_path in valid_pairs:
            identity = by_run[int(run)].get("source_identity")
            if not isinstance(identity, dict):
                identity = _pair_source_identity(tek_path, pico_path)
            identities.append(
                {
                    "role": role,
                    "rate_sps": int(rate),
                    "run": int(run),
                    "identity": identity,
                }
            )
        return valid_pairs, by_run, identities

    catalogs: list[dict[str, Any]] = []
    source_catalog: list[dict[str, Any]] = []
    for rate in common_rates:
        workload_pairs, workload_by_run, workload_ids = valid_catalog(
            cfg, rate, workload_dirs[rate], "workload"
        )
        idle_pairs, idle_by_run, idle_ids = valid_catalog(
            cfg, rate, external_idle_dirs[rate], "external_idle"
        )
        source_catalog.extend(workload_ids)
        source_catalog.extend(idle_ids)
        catalogs.append(
            {
                "rate": int(rate),
                "workload_directory": workload_dirs[rate],
                "idle_directory": external_idle_dirs[rate],
                "workload_pairs": workload_pairs,
                "idle_pairs": idle_pairs,
                "workload_by_run": workload_by_run,
                "idle_by_run": idle_by_run,
            }
        )

    source_fingerprint = stable_hash(
        {"schema": 2, "workload_and_external_idle_pairs": source_catalog}
    )
    analysis_config_hash = stable_hash(
        {
            "schema": 2,
            "tool_version": __version__,
            "zero_offset_correction": normalise_for_json(config),
            "external_idle": normalise_for_json(cfg.external_idle),
            "tek_calibration": normalise_for_json(cfg.tek),
            "pico_calibration": normalise_for_json(cfg.pico),
            "source_rates": normalise_for_json(cfg.source_rates),
            "model": "workload_minus_external_idle_rate_medians",
        }
    )
    if not force and model_path.is_file() and pair_path.is_file() and rate_path.is_file():
        try:
            cached = json.loads(model_path.read_text(encoding="utf-8"))
            if (
                int(cached.get("model_schema_version", 0)) == 2
                and cached.get("source_fingerprint_sha256") == source_fingerprint
                and cached.get("analysis_config_hash") == analysis_config_hash
            ):
                LOGGER.info(
                    "Reused adaptive workload-session zero model: status=%s, "
                    "offset=%s mA",
                    cached.get("status", "unknown"),
                    (
                        f"{float(cached.get('offset_estimate_ma')):+.3f}"
                        if cached.get("offset_estimate_ma") is not None
                        else "n/a"
                    ),
                )
                return cached
        except Exception:
            pass

    for item in catalogs:
        rate = int(item["rate"])
        role_values: dict[str, np.ndarray] = {}
        role_counts: dict[str, int] = {}
        for role, pairs, by_run in (
            ("workload", item["workload_pairs"], item["workload_by_run"]),
            ("external_idle", item["idle_pairs"], item["idle_by_run"]),
        ):
            differences: list[float] = []
            for run, tek_path, pico_path in pairs:
                try:
                    tek_mean, tek_count = _stream_calibrated_mean(tek_path, cfg.tek)
                    pico_mean, pico_count = _stream_calibrated_mean(pico_path, cfg.pico)
                    difference_ma = 1000.0 * (pico_mean - tek_mean)
                    differences.append(difference_ma)
                    identity = by_run[int(run)].get("source_identity")
                    if not isinstance(identity, dict):
                        identity = _pair_source_identity(tek_path, pico_path)
                    pair_rows.append(
                        {
                            "evidence_role": role,
                            "rate_sps": rate,
                            "run": int(run),
                            "tek_path": str(tek_path),
                            "pico_path": str(pico_path),
                            "source_fingerprint_sha256": identity.get(
                                "fingerprint_sha256", ""
                            ),
                            "tek_samples_used": int(tek_count),
                            "pico_samples_used": int(pico_count),
                            "tek_mean_current_a_raw": float(tek_mean),
                            "pico_mean_current_a_raw": float(pico_mean),
                            "pico_minus_tek_current_ma_raw": float(difference_ma),
                            "status": "valid",
                            "reason": "",
                        }
                    )
                except Exception as error:
                    pair_rows.append(
                        {
                            "evidence_role": role,
                            "rate_sps": rate,
                            "run": int(run),
                            "tek_path": str(tek_path),
                            "pico_path": str(pico_path),
                            "source_fingerprint_sha256": "",
                            "tek_samples_used": 0,
                            "pico_samples_used": 0,
                            "tek_mean_current_a_raw": float("nan"),
                            "pico_mean_current_a_raw": float("nan"),
                            "pico_minus_tek_current_ma_raw": float("nan"),
                            "status": "invalid",
                            "reason": f"{type(error).__name__}: {error}",
                        }
                    )
            values = np.asarray(differences, dtype=np.float64)
            role_values[role] = values[np.isfinite(values)]
            role_counts[role] = len(pairs)

        workload_values = role_values.get("workload", np.asarray([], dtype=np.float64))
        idle_values = role_values.get("external_idle", np.asarray([], dtype=np.float64))
        workload_median = (
            float(np.median(workload_values)) if workload_values.size else float("nan")
        )
        idle_median = (
            float(np.median(idle_values)) if idle_values.size else float("nan")
        )
        session_shift_ma = (
            workload_median - idle_median
            if np.isfinite(workload_median) and np.isfinite(idle_median)
            else float("nan")
        )
        workload_q05 = quantile(workload_values, 0.05)
        workload_q95 = quantile(workload_values, 0.95)
        idle_q05 = quantile(idle_values, 0.05)
        idle_q95 = quantile(idle_values, 0.95)
        workload_span = (
            float(workload_q95 - workload_q05)
            if np.isfinite(workload_q05) and np.isfinite(workload_q95)
            else float("nan")
        )
        idle_span = (
            float(idle_q95 - idle_q05)
            if np.isfinite(idle_q05) and np.isfinite(idle_q95)
            else float("nan")
        )
        combined_span = (
            max(workload_span, idle_span)
            if np.isfinite(workload_span) and np.isfinite(idle_span)
            else float("nan")
        )
        workload_mad = _median_absolute_deviation(workload_values)
        idle_mad = _median_absolute_deviation(idle_values)
        combined_mad = (
            float(math.hypot(workload_mad, idle_mad))
            if np.isfinite(workload_mad) and np.isfinite(idle_mad)
            else float("nan")
        )
        candidate = bool(
            workload_values.size >= cfg.external_idle.minimum_pairs
            and idle_values.size >= cfg.external_idle.minimum_pairs
            and np.isfinite(session_shift_ma)
        )
        eligible = bool(
            candidate
            and np.isfinite(combined_span)
            and combined_span <= config.maximum_rate_q95_span_ma
            and abs(session_shift_ma) <= config.maximum_abs_correction_ma
        )
        rate_rows.append(
            {
                "rate_sps": rate,
                "workload_directory": str(item["workload_directory"]),
                "external_idle_directory": str(item["idle_directory"]),
                "workload_candidate_pairs": role_counts.get("workload", 0),
                "workload_valid_offset_pairs": int(workload_values.size),
                "external_idle_candidate_pairs": role_counts.get("external_idle", 0),
                "external_idle_valid_offset_pairs": int(idle_values.size),
                "workload_pico_minus_tek_median_ma": workload_median,
                "external_idle_pico_minus_tek_median_ma": idle_median,
                "offset_median_ma": session_shift_ma,
                "offset_q05_ma": (
                    session_shift_ma - 0.5 * combined_span
                    if np.isfinite(session_shift_ma) and np.isfinite(combined_span)
                    else float("nan")
                ),
                "offset_q95_ma": (
                    session_shift_ma + 0.5 * combined_span
                    if np.isfinite(session_shift_ma) and np.isfinite(combined_span)
                    else float("nan")
                ),
                "offset_q90_span_ma": combined_span,
                "offset_mad_ma": combined_mad,
                "workload_difference_q90_span_ma": workload_span,
                "external_idle_difference_q90_span_ma": idle_span,
                "valid_offset_pairs": int(
                    min(workload_values.size, idle_values.size)
                ),
                "candidate_for_session_model": candidate,
                "eligible_for_session_model": eligible,
                "eligibility_reason": (
                    "ok"
                    if eligible
                    else (
                        "insufficient_rate_matched_pairs"
                        if not candidate
                        else "unstable_or_out_of_bounds"
                    )
                ),
            }
        )

    decision = _derive_zero_offset_decision(config, rate_rows)
    model = {
        **base_model,
        **decision,
        "source_fingerprint_sha256": source_fingerprint,
        "analysis_config_hash": analysis_config_hash,
        "external_idle_applied_correction": False,
        "interpretation": (
            "A stable session-specific additive Tektronix probe-zero shift is "
            "estimated as the cross-rate median of [paired workload Pico-minus-"
            "Tek mean difference] minus [rate-matched external-idle Pico-minus-"
            "Tek mean difference]. The correction is applied only to workload "
            "Tek traces before voltage, power, energy and paired-waveform "
            "processing. External idle traces remain uncorrected because they "
            "represent another probe-zero state. Raw metrics remain archived, "
            "no gain correction is fitted, and the result is explicitly a "
            "non-independent post-hoc session-salvage analysis."
        ),
    }
    return finish(model)


def _build_zero_offset_model(
    cfg: ScopeComparisonConfig,
    external_idle_dirs: dict[int, Path],
    workload_dirs: dict[int, Path] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Detect and optionally correct a stable additive probe-zero error.

    Detection uses independently recorded, exact-rate *paired* idle campaigns.
    For every available rate the mean Pico-minus-Tek current difference is
    calculated for each physical repetition. A rate is eligible only when it
    contains enough pairs and its 5--95% interval is sufficiently narrow. The
    session offset is then the median of the eligible rate medians.

    A correction is applied only when the offset is material, bounded, stable
    across rates, and has a consistent sign. Raw measurements are always
    preserved. Because the PicoScope participates in the estimate, corrected
    absolute agreement is explicitly a post-hoc salvage analysis rather than an
    independent validation of the PicoScope setup.
    """

    config = cfg.zero_offset_correction
    if (
        config.enabled
        and config.detection_source
        == "workload_minus_external_idle_rate_medians"
    ):
        return _build_workload_session_shift_zero_model(
            cfg,
            workload_dirs or dict(discover_rate_directories(cfg)),
            external_idle_dirs,
            force=force,
        )

    root = cfg.output_root / "zero_correction"
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "zero_offset_model.json"
    pair_path = root / "zero_offset_pair_evidence.csv"
    rate_path = root / "zero_offset_rate_evidence.csv"
    pair_rows: list[dict[str, Any]] = []
    rate_rows: list[dict[str, Any]] = []
    pair_fieldnames = [
        "rate_sps",
        "run",
        "tek_path",
        "pico_path",
        "source_fingerprint_sha256",
        "tek_samples_used",
        "pico_samples_used",
        "tek_idle_mean_current_a_raw",
        "pico_idle_mean_current_a_raw",
        "pico_minus_tek_idle_current_ma_raw",
        "status",
        "reason",
    ]
    rate_fieldnames = [
        "rate_sps",
        "directory",
        "candidate_pairs",
        "valid_offset_pairs",
        "offset_median_ma",
        "offset_q05_ma",
        "offset_q95_ma",
        "offset_q90_span_ma",
        "offset_mad_ma",
        "candidate_for_session_model",
        "eligible_for_session_model",
        "eligibility_reason",
    ]

    def finish(model: dict[str, Any]) -> dict[str, Any]:
        model = dict(model)
        model["model_hash"] = stable_hash(model)
        write_csv(pair_path, pair_rows, fieldnames=pair_fieldnames)
        write_csv(rate_path, rate_rows, fieldnames=rate_fieldnames)
        write_json(model_path, model)
        return model

    base_model: dict[str, Any] = {
        "model_schema_version": 1,
        "enabled": bool(config.enabled),
        "target_source": config.target_source,
        "reference_source": config.detection_source,
        "application_scope": config.application_scope,
        "raw_values_preserved": bool(config.preserve_raw_metrics),
        "independent_reference": False,
        "validation_independence": (
            "post_hoc_paired_idle_salvage_not_independent"
        ),
        "correction_formula": (
            "I_Tek_corrected = I_Tek_raw + offset_applied_a"
        ),
    }
    if not config.enabled:
        return finish(
            {
                **base_model,
                "status": "disabled",
                "offset_detected": False,
                "correction_applied": False,
                "offset_estimate_a": 0.0,
                "offset_estimate_ma": 0.0,
                "offset_applied_a": 0.0,
                "offset_applied_ma": 0.0,
                "offset_uncertainty_ma": 0.0,
                "confidence": "none",
                "reference_rate_count": 0,
                "reference_rates_sps": [],
                "reference_pair_count": 0,
                "source_fingerprint_sha256": "",
                "analysis_config_hash": "",
                "checks": {},
                "interpretation": "Adaptive zero-offset correction disabled.",
            }
        )

    # First perform a metadata-only pass so an unchanged correction model can be
    # reused without rereading every high-rate idle waveform.
    catalog: list[dict[str, Any]] = []
    source_catalog: list[dict[str, Any]] = []
    for rate, directory in sorted(external_idle_dirs.items()):
        idle_cfg = replace(
            cfg,
            dataset_root=cfg.external_idle.dataset_root or directory.parent,
            output_root=cfg.output_root / "zero_correction" / "preflight",
            external_idle=replace(cfg.external_idle, enabled=False),
            zero_offset_correction=replace(config, enabled=False),
        )
        pairs, inventory = discover_pairs(idle_cfg, directory, None)
        section_seconds = inventory.get("section_marker_seconds")
        preflight_rows = [
            _preflight_pair(
                idle_cfg,
                int(rate),
                run,
                tek_path,
                pico_path,
                section_seconds,
            )
            for run, tek_path, pico_path in pairs
        ]
        _apply_auto_duration_inference(
            idle_cfg,
            int(rate),
            section_seconds,
            preflight_rows,
        )
        by_run = {int(row["run"]): row for row in preflight_rows}
        valid_pairs = [
            pair
            for pair in pairs
            if by_run[int(pair[0])]["status"] == "valid"
        ]
        identities: list[dict[str, Any]] = []
        for run, tek_path, pico_path in valid_pairs:
            identity = by_run[int(run)].get("source_identity")
            if not isinstance(identity, dict):
                identity = _pair_source_identity(tek_path, pico_path)
            identities.append({"run": int(run), "identity": identity})
        source_catalog.append(
            {
                "rate_sps": int(rate),
                "directory": str(directory),
                "pairs": identities,
            }
        )
        catalog.append(
            {
                "rate": int(rate),
                "directory": directory,
                "idle_cfg": idle_cfg,
                "pairs": pairs,
                "valid_pairs": valid_pairs,
                "by_run": by_run,
            }
        )

    source_fingerprint = stable_hash(
        {"schema": 1, "external_idle_pairs": source_catalog}
    )
    analysis_config_hash = stable_hash(
        {
            "schema": 1,
            "tool_version": __version__,
            "zero_offset_correction": normalise_for_json(config),
            "external_idle": normalise_for_json(cfg.external_idle),
            "tek_calibration": normalise_for_json(cfg.tek),
            "pico_calibration": normalise_for_json(cfg.pico),
            "source_rates": normalise_for_json(cfg.source_rates),
        }
    )
    if not force and model_path.is_file() and pair_path.is_file() and rate_path.is_file():
        try:
            cached = json.loads(model_path.read_text(encoding="utf-8"))
            if (
                int(cached.get("model_schema_version", 0)) == 1
                and cached.get("source_fingerprint_sha256") == source_fingerprint
                and cached.get("analysis_config_hash") == analysis_config_hash
            ):
                LOGGER.info(
                    "Reused adaptive zero-offset model: status=%s, offset=%s mA",
                    cached.get("status", "unknown"),
                    (
                        f"{float(cached.get('offset_estimate_ma')):+.3f}"
                        if cached.get("offset_estimate_ma") is not None
                        else "n/a"
                    ),
                )
                return cached
        except Exception:
            pass

    for item in catalog:
        rate = int(item["rate"])
        directory = item["directory"]
        valid_pairs = item["valid_pairs"]
        by_run = item["by_run"]
        differences: list[float] = []
        for run, tek_path, pico_path in valid_pairs:
            try:
                tek_mean, tek_count = _stream_calibrated_mean(tek_path, cfg.tek)
                pico_mean, pico_count = _stream_calibrated_mean(pico_path, cfg.pico)
                difference_ma = 1000.0 * (pico_mean - tek_mean)
                differences.append(difference_ma)
                identity = by_run[int(run)].get("source_identity")
                if not isinstance(identity, dict):
                    identity = _pair_source_identity(tek_path, pico_path)
                pair_rows.append(
                    {
                        "rate_sps": rate,
                        "run": int(run),
                        "tek_path": str(tek_path),
                        "pico_path": str(pico_path),
                        "source_fingerprint_sha256": identity.get(
                            "fingerprint_sha256", ""
                        ),
                        "tek_samples_used": int(tek_count),
                        "pico_samples_used": int(pico_count),
                        "tek_idle_mean_current_a_raw": float(tek_mean),
                        "pico_idle_mean_current_a_raw": float(pico_mean),
                        "pico_minus_tek_idle_current_ma_raw": float(difference_ma),
                        "status": "valid",
                        "reason": "",
                    }
                )
            except Exception as error:
                pair_rows.append(
                    {
                        "rate_sps": rate,
                        "run": int(run),
                        "tek_path": str(tek_path),
                        "pico_path": str(pico_path),
                        "source_fingerprint_sha256": "",
                        "tek_samples_used": 0,
                        "pico_samples_used": 0,
                        "tek_idle_mean_current_a_raw": float("nan"),
                        "pico_idle_mean_current_a_raw": float("nan"),
                        "pico_minus_tek_idle_current_ma_raw": float("nan"),
                        "status": "invalid",
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )

        values = np.asarray(differences, dtype=np.float64)
        values = values[np.isfinite(values)]
        median_ma = float(np.median(values)) if values.size else float("nan")
        q05_ma = quantile(values, 0.05)
        q95_ma = quantile(values, 0.95)
        q90_span_ma = (
            float(q95_ma - q05_ma)
            if np.isfinite(q05_ma) and np.isfinite(q95_ma)
            else float("nan")
        )
        mad_ma = _median_absolute_deviation(values)
        candidate = bool(
            values.size >= cfg.external_idle.minimum_pairs
            and np.isfinite(median_ma)
        )
        eligible = bool(
            candidate
            and np.isfinite(q90_span_ma)
            and q90_span_ma <= config.maximum_rate_q95_span_ma
            and abs(median_ma) <= config.maximum_abs_correction_ma
        )
        rate_rows.append(
            {
                "rate_sps": rate,
                "directory": str(directory),
                "candidate_pairs": len(item["pairs"]),
                "valid_offset_pairs": int(values.size),
                "offset_median_ma": median_ma,
                "offset_q05_ma": q05_ma,
                "offset_q95_ma": q95_ma,
                "offset_q90_span_ma": q90_span_ma,
                "offset_mad_ma": mad_ma,
                "candidate_for_session_model": candidate,
                "eligible_for_session_model": eligible,
                "eligibility_reason": (
                    "ok"
                    if eligible
                    else (
                        "insufficient_pairs"
                        if not candidate
                        else "unstable_or_out_of_bounds"
                    )
                ),
            }
        )

    decision = _derive_zero_offset_decision(config, rate_rows)
    model = {
        **base_model,
        **decision,
        "source_fingerprint_sha256": source_fingerprint,
        "analysis_config_hash": analysis_config_hash,
        "interpretation": (
            "A stable additive Tektronix probe-zero error is detected from "
            "exact-rate paired idle repetitions and corrected before current-"
            "dependent voltage, power, energy, waveform and PSD calculations. "
            "Raw current, charge and energy metrics remain archived. Because "
            "the PicoScope idle setup participates in the estimate, corrected "
            "absolute agreement is a post-hoc salvage analysis, not an "
            "independent validation of the PicoScope. No gain correction is "
            "fitted or applied."
        ),
    }
    return finish(model)


def _zero_offset_for_rate(
    model: dict[str, Any] | None,
    rate: int,
) -> float:
    del rate  # the current contract applies one stable session offset to all rates
    if not model or not bool(model.get("correction_applied", False)):
        return 0.0
    if model.get("target_source") != "tek":
        return 0.0
    try:
        value = float(model.get("offset_applied_a", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if np.isfinite(value) else 0.0


def _zero_offset_for_external_idle(
    model: dict[str, Any] | None,
    rate: int,
) -> float:
    """Return an offset only when the model explicitly covers idle files.

    Session-shift salvage models are workload-only by construction: applying
    the old workload-session probe-zero correction to a newly acquired idle
    campaign would manufacture a false baseline mismatch.
    """

    if not model or not bool(model.get("apply_to_external_idle", True)):
        return 0.0
    return _zero_offset_for_rate(model, rate)


def _external_idle_unavailable(
    cfg: ScopeComparisonConfig,
    rate: int,
    reason: str,
    *,
    directory: Path | None = None,
    candidate_pairs: int = 0,
    valid_pairs: int = 0,
) -> dict[str, Any]:
    payload = {
        "status": "unavailable",
        "rate_sps": int(rate),
        "directory": str(directory) if directory is not None else "",
        "candidate_pairs": int(candidate_pairs),
        "valid_pairs": int(valid_pairs),
        "minimum_pairs": int(cfg.external_idle.minimum_pairs),
        "reason": reason,
        "source_fingerprint_sha256": "",
        "summary": {},
        "common": None,
        "native": None,
    }
    out = cfg.output_root / "external_idle" / f"{rate}Sps"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "idle_reference.json", payload)
    return payload


def _build_external_idle_reference(
    cfg: ScopeComparisonConfig,
    rate: int,
    directory_map: dict[int, Path],
    *,
    force: bool = False,
    zero_correction_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or reuse an independently recorded, exact-rate idle reference.

    The returned common-band and native-Tek PSDs are pointwise medians across
    physical idle repetitions.  Mean current and mean estimated power are kept
    separately for DC-baseline diagnostics and optional incremental-energy
    calculations.  Raw absolute workload current/energy is never overwritten.
    """

    if not cfg.external_idle.enabled:
        return {
            "status": "disabled",
            "rate_sps": int(rate),
            "source_fingerprint_sha256": "",
            "summary": {},
            "common": None,
            "native": None,
        }
    directory = directory_map.get(int(rate))
    if directory is None:
        return _external_idle_unavailable(
            cfg,
            rate,
            "no_exact_rate_directory",
        )

    idle_cfg = replace(
        cfg,
        dataset_root=cfg.external_idle.dataset_root or directory.parent,
        output_root=cfg.output_root / "external_idle",
        external_idle=replace(cfg.external_idle, enabled=False),
    )
    pairs, inventory = discover_pairs(idle_cfg, directory, None)
    section_seconds = inventory.get("section_marker_seconds")
    preflight_rows = [
        _preflight_pair(
            idle_cfg,
            rate,
            run,
            tek_path,
            pico_path,
            section_seconds,
        )
        for run, tek_path, pico_path in pairs
    ]
    _apply_auto_duration_inference(
        idle_cfg,
        rate,
        section_seconds,
        preflight_rows,
    )
    valid_pairs = [
        pair
        for pair in pairs
        if next(row for row in preflight_rows if int(row["run"]) == pair[0])[
            "status"
        ]
        == "valid"
    ]
    out = cfg.output_root / "external_idle" / f"{rate}Sps"
    out.mkdir(parents=True, exist_ok=True)
    write_json(
        out / "inventory.json",
        {
            **inventory,
            "rate_sps": int(rate),
            "candidate_pairs": len(pairs),
            "valid_pairs": len(valid_pairs),
            "minimum_pairs": int(cfg.external_idle.minimum_pairs),
            "preflight": preflight_rows,
        },
    )
    if len(valid_pairs) < cfg.external_idle.minimum_pairs:
        return _external_idle_unavailable(
            cfg,
            rate,
            "insufficient_valid_pairs",
            directory=directory,
            candidate_pairs=len(pairs),
            valid_pairs=len(valid_pairs),
        )

    source_identities = []
    by_run = {int(row["run"]): row for row in preflight_rows}
    for run, tek_path, pico_path in valid_pairs:
        identity = by_run[run].get("source_identity")
        if not isinstance(identity, dict):
            identity = _pair_source_identity(tek_path, pico_path)
        source_identities.append({"run": int(run), "identity": identity})
    source_fingerprint = stable_hash(
        {
            "schema": 1,
            "rate_sps": int(rate),
            "pairs": source_identities,
        }
    )
    analysis_hash = stable_hash(
        {
            "tool_version": __version__,
            "rate_sps": int(rate),
            "tek": normalise_for_json(cfg.tek),
            "pico": normalise_for_json(cfg.pico),
            "source_rates": normalise_for_json(cfg.source_rates),
            "voltage_model": normalise_for_json(cfg.voltage_model),
            "spectral": normalise_for_json(cfg.spectral),
            "external_idle": normalise_for_json(cfg.external_idle),
            "zero_offset_model_hash": (
                zero_correction_model.get("model_hash", "")
                if zero_correction_model is not None
                else ""
            ),
            "zero_offset_applied_a": _zero_offset_for_external_idle(
                zero_correction_model, rate
            ),
        }
    )
    summary_path = out / "idle_reference.json"
    pair_metrics_path = out / "idle_pair_metrics.csv"
    common_path = out / "paired_idle_psd_summary.npz"
    native_path = out / "tek_native_idle_psd_summary.npz"
    if (
        not force
        and summary_path.is_file()
        and pair_metrics_path.is_file()
        and common_path.is_file()
        and native_path.is_file()
    ):
        try:
            cached = json.loads(summary_path.read_text(encoding="utf-8"))
            if (
                cached.get("status") == "available"
                and cached.get("source_fingerprint_sha256") == source_fingerprint
                and cached.get("analysis_config_hash") == analysis_hash
            ):
                return {
                    **cached,
                    "common": dict(np.load(common_path)),
                    "native": dict(np.load(native_path)),
                }
        except Exception:
            pass

    tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
    common_rate = min(tek_rate, pico_rate)
    common_counts = []
    native_counts = []
    for run, _, _ in valid_pairs:
        row = by_run[run]
        duration = min(float(row["tek_duration_s"]), float(row["pico_duration_s"]))
        common_counts.append(int(round(duration * common_rate)))
        native_counts.append(int(round(duration * tek_rate)))
    common_nperseg, common_noverlap, common_segments, common_policy = (
        _choose_welch_parameters(
            min(common_counts),
            common_rate,
            cfg,
            minimum_segments=max(2, cfg.spectral.minimum_idle_welch_segments),
        )
    )
    native_nperseg, native_noverlap, native_segments, native_policy = (
        _choose_welch_parameters(
            min(native_counts),
            tek_rate,
            cfg,
            minimum_segments=max(2, cfg.spectral.minimum_idle_welch_segments),
        )
    )
    if common_nperseg < 32 or native_nperseg < 32:
        return _external_idle_unavailable(
            cfg,
            rate,
            "insufficient_samples_for_idle_psd",
            directory=directory,
            candidate_pairs=len(pairs),
            valid_pairs=len(valid_pairs),
        )

    pair_rows: list[dict[str, Any]] = []
    tek_common_psds: list[np.ndarray] = []
    pico_common_psds: list[np.ndarray] = []
    tek_native_psds: list[np.ndarray] = []
    common_frequencies: np.ndarray | None = None
    native_frequencies: np.ndarray | None = None
    for run, tek_path, pico_path in valid_pairs:
        tek_raw, _ = _read_parquet_column(tek_path, cfg.tek.column)
        pico_raw, _ = _read_parquet_column(pico_path, cfg.pico.column)
        tek_current_raw = _calibrate(tek_raw, cfg.tek)
        pico_current = _calibrate(pico_raw, cfg.pico)
        duration = min(
            tek_current_raw.size / tek_rate, pico_current.size / pico_rate
        )
        tek_current_raw = tek_current_raw[: int(round(duration * tek_rate))]
        pico_current = pico_current[: int(round(duration * pico_rate))]
        zero_offset_a = _zero_offset_for_external_idle(
            zero_correction_model, rate
        )
        tek_current = tek_current_raw + zero_offset_a
        _, tek_power_raw = _power_from_current(tek_current_raw, cfg)
        _, tek_power = _power_from_current(tek_current, cfg)
        _, pico_power = _power_from_current(pico_current, cfg)

        tek_common = _resample_signal(tek_power, tek_rate, common_rate)
        pico_common = _resample_signal(pico_power, pico_rate, common_rate)
        common_count = min(tek_common.size, pico_common.size)
        tek_common = tek_common[:common_count]
        pico_common = pico_common[:common_count]
        f_common, tek_common_psd = welch(
            tek_common,
            fs=common_rate,
            window="hann",
            nperseg=common_nperseg,
            noverlap=common_noverlap,
            detrend="constant",
            scaling="density",
        )
        _, pico_common_psd = welch(
            pico_common,
            fs=common_rate,
            window="hann",
            nperseg=common_nperseg,
            noverlap=common_noverlap,
            detrend="constant",
            scaling="density",
        )
        f_native, tek_native_psd = welch(
            tek_power,
            fs=tek_rate,
            window="hann",
            nperseg=native_nperseg,
            noverlap=native_noverlap,
            detrend="constant",
            scaling="density",
        )
        if common_frequencies is None:
            common_frequencies = f_common
            native_frequencies = f_native
        tek_common_psds.append(tek_common_psd)
        pico_common_psds.append(pico_common_psd)
        tek_native_psds.append(tek_native_psd)
        pair_rows.append(
            {
                "rate_sps": int(rate),
                "run": int(run),
                "tek_rate_sps": float(tek_rate),
                "pico_rate_sps": float(pico_rate),
                "duration_s": float(duration),
                "raw_tek_mean_current_a": float(np.mean(tek_current_raw)),
                "raw_pico_mean_current_a": float(np.mean(pico_current)),
                "raw_idle_current_difference_ma": float(
                    1000.0
                    * (np.mean(pico_current) - np.mean(tek_current_raw))
                ),
                "raw_tek_mean_power_w": float(np.mean(tek_power_raw)),
                "raw_pico_mean_power_w": float(np.mean(pico_power)),
                "raw_idle_power_difference_w": float(
                    np.mean(pico_power) - np.mean(tek_power_raw)
                ),
                "tek_mean_current_a": float(np.mean(tek_current)),
                "pico_mean_current_a": float(np.mean(pico_current)),
                "idle_current_difference_ma": float(
                    1000.0 * (np.mean(pico_current) - np.mean(tek_current))
                ),
                "tek_mean_power_w": float(np.mean(tek_power)),
                "pico_mean_power_w": float(np.mean(pico_power)),
                "idle_power_difference_w": float(
                    np.mean(pico_power) - np.mean(tek_power)
                ),
                "zero_offset_correction_applied": bool(
                    abs(zero_offset_a) > 0.0
                ),
                "zero_offset_applied_a": float(zero_offset_a),
                "zero_offset_applied_ma": float(1000.0 * zero_offset_a),
                "zero_offset_uncertainty_ma": (
                    float(zero_correction_model.get("offset_uncertainty_ma"))
                    if zero_correction_model is not None
                    and zero_correction_model.get("offset_uncertainty_ma") is not None
                    else float("nan")
                ),
                "zero_offset_reference_rate_count": int(
                    zero_correction_model.get("reference_rate_count", 0)
                    if zero_correction_model is not None
                    else 0
                ),
                "zero_offset_reference_pair_count": int(
                    zero_correction_model.get("reference_pair_count", 0)
                    if zero_correction_model is not None
                    else 0
                ),
                "zero_offset_detection_status": (
                    str(zero_correction_model.get("status", "disabled"))
                    if zero_correction_model is not None
                    else "disabled"
                ),
            }
        )
        del (
            tek_raw,
            pico_raw,
            tek_current_raw,
            tek_current,
            pico_current,
            tek_power_raw,
            tek_power,
            pico_power,
        )
        gc.collect()

    assert common_frequencies is not None and native_frequencies is not None
    tek_common_stack = np.vstack(tek_common_psds)
    pico_common_stack = np.vstack(pico_common_psds)
    tek_native_stack = np.vstack(tek_native_psds)
    common_arrays = {
        "frequencies_hz": common_frequencies,
        "tek_idle_psd_w2_per_hz_median": np.median(tek_common_stack, axis=0),
        "tek_idle_psd_w2_per_hz_q05": np.quantile(tek_common_stack, 0.05, axis=0),
        "tek_idle_psd_w2_per_hz_q95": np.quantile(tek_common_stack, 0.95, axis=0),
        "pico_idle_psd_w2_per_hz_median": np.median(pico_common_stack, axis=0),
        "pico_idle_psd_w2_per_hz_q05": np.quantile(pico_common_stack, 0.05, axis=0),
        "pico_idle_psd_w2_per_hz_q95": np.quantile(pico_common_stack, 0.95, axis=0),
    }
    native_arrays = {
        "tek_native_frequencies_hz": native_frequencies,
        "tek_native_idle_psd_w2_per_hz_median": np.median(
            tek_native_stack, axis=0
        ),
        "tek_native_idle_psd_w2_per_hz_q05": np.quantile(
            tek_native_stack, 0.05, axis=0
        ),
        "tek_native_idle_psd_w2_per_hz_q95": np.quantile(
            tek_native_stack, 0.95, axis=0
        ),
    }
    np.savez_compressed(common_path, **common_arrays)
    np.savez_compressed(native_path, **native_arrays)
    write_csv(pair_metrics_path, pair_rows)

    summary: dict[str, Any] = {
        "status": "available",
        "rate_sps": int(rate),
        "directory": str(directory),
        "candidate_pairs": len(pairs),
        "valid_pairs": len(valid_pairs),
        "minimum_pairs": int(cfg.external_idle.minimum_pairs),
        "tek_rate_sps": float(tek_rate),
        "pico_rate_sps": float(pico_rate),
        "common_rate_sps": float(common_rate),
        "source_fingerprint_sha256": source_fingerprint,
        "analysis_config_hash": analysis_hash,
        "zero_offset_correction": {
            "status": (
                zero_correction_model.get("status", "disabled")
                if zero_correction_model is not None
                else "disabled"
            ),
            "correction_applied": bool(
                abs(
                    _zero_offset_for_external_idle(
                        zero_correction_model, rate
                    )
                )
                > 0.0
            ),
            "offset_applied_a": float(
                _zero_offset_for_external_idle(
                    zero_correction_model, rate
                )
            ),
            "model_hash": (
                zero_correction_model.get("model_hash", "")
                if zero_correction_model is not None
                else ""
            ),
        },
        "common_nperseg": int(common_nperseg),
        "common_welch_segments_minimum": int(common_segments),
        "common_segment_policy": common_policy,
        "native_nperseg": int(native_nperseg),
        "native_welch_segments_minimum": int(native_segments),
        "native_segment_policy": native_policy,
    }
    for key in (
        "raw_tek_mean_current_a",
        "raw_pico_mean_current_a",
        "raw_idle_current_difference_ma",
        "raw_tek_mean_power_w",
        "raw_pico_mean_power_w",
        "raw_idle_power_difference_w",
        "tek_mean_current_a",
        "pico_mean_current_a",
        "idle_current_difference_ma",
        "tek_mean_power_w",
        "pico_mean_power_w",
        "idle_power_difference_w",
        "zero_offset_uncertainty_ma",
        "zero_offset_reference_rate_count",
        "zero_offset_reference_pair_count",
        "zero_offset_applied_a",
        "zero_offset_applied_ma",
        "duration_s",
    ):
        summary.update(
            _summary_row(
                np.asarray([float(row[key]) for row in pair_rows]),
                key,
            )
        )
    payload = {
        **summary,
        "summary": summary,
        "common_psd_path": str(common_path),
        "native_psd_path": str(native_path),
    }
    write_json(summary_path, payload)
    return {
        **payload,
        "common": common_arrays,
        "native": native_arrays,
    }


def _block_mean(values: np.ndarray, block: int) -> np.ndarray:
    block = max(1, int(block))
    if block == 1:
        return np.asarray(values, dtype=np.float64)
    count = values.size // block
    if count < 1:
        return np.asarray([float(np.mean(values))], dtype=np.float64)
    return np.asarray(
        values[: count * block].reshape(count, block).mean(axis=1, dtype=np.float64),
        dtype=np.float64,
    )


def _reduce_rate(values: np.ndarray, source_rate: float, maximum_rate: float) -> tuple[np.ndarray, float, int]:
    if source_rate <= maximum_rate:
        return np.asarray(values, dtype=np.float64), float(source_rate), 1
    factor = int(math.ceil(source_rate / maximum_rate))
    reduced = _block_mean(values, factor)
    return reduced, float(source_rate / factor), factor


def _safe_lowpass(values: np.ndarray, fs: float, cutoff_hz: float) -> np.ndarray:
    cutoff = min(float(cutoff_hz), 0.40 * fs)
    if cutoff <= 0.0 or cutoff >= 0.49 * fs or values.size < 64:
        return np.asarray(values, dtype=np.float64)
    sos = butter(4, cutoff, btype="lowpass", fs=fs, output="sos")
    return np.asarray(sosfiltfilt(sos, values), dtype=np.float64)


def _estimate_lag_samples(
    tek: np.ndarray,
    pico: np.ndarray,
    fs: float,
    cfg: ScopeComparisonConfig,
) -> tuple[int, dict[str, Any]]:
    if not cfg.alignment.enabled:
        return 0, {
            "lag_samples": 0,
            "lag_ms": 0.0,
            "analysis_rate_sps": fs,
            "downsample_factor": 1,
            "status": "disabled",
        }

    maximum_rate = min(float(cfg.alignment.analysis_rate_sps), fs)
    tek_ds, analysis_rate, factor = _reduce_rate(tek, fs, maximum_rate)
    pico_ds, pico_rate, pico_factor = _reduce_rate(pico, fs, maximum_rate)
    if abs(analysis_rate - pico_rate) > 1e-9 or factor != pico_factor:
        raise RuntimeError("Internal alignment-rate mismatch")
    n = min(tek_ds.size, pico_ds.size)
    tek_ds = tek_ds[:n]
    pico_ds = pico_ds[:n]
    cutoff = min(cfg.alignment.lowpass_hz, 0.35 * analysis_rate)
    tek_ds = _safe_lowpass(tek_ds, analysis_rate, cutoff)
    pico_ds = _safe_lowpass(pico_ds, analysis_rate, cutoff)
    tek_ds = tek_ds - np.mean(tek_ds)
    pico_ds = pico_ds - np.mean(pico_ds)

    correlation = correlate(pico_ds, tek_ds, mode="full", method="fft")
    lags = correlation_lags(pico_ds.size, tek_ds.size, mode="full")
    max_lag_ds = max(1, int(round(cfg.alignment.max_lag_ms * 1e-3 * analysis_rate)))
    mask = np.abs(lags) <= max_lag_ds
    if not np.any(mask):
        raise RuntimeError("No alignment lags within configured range")
    selected_lags = lags[mask]
    selected_corr = correlation[mask]
    lag_ds = int(selected_lags[int(np.argmax(selected_corr))])
    lag_original = int(round(lag_ds * fs / analysis_rate))
    return lag_original, {
        "lag_samples": lag_original,
        "lag_ms": 1000.0 * lag_original / fs,
        "analysis_rate_sps": analysis_rate,
        "downsample_factor": factor,
        "lag_samples_at_analysis_rate": lag_ds,
        "status": "estimated",
    }


def _aligned_overlap(
    tek: np.ndarray,
    pico: np.ndarray,
    lag_samples: int,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    n = min(tek.size, pico.size)
    tek = tek[:n]
    pico = pico[:n]
    if lag_samples > 0:
        # Positive lag means the Pico waveform occurs later in its record.
        if lag_samples >= n:
            raise ValueError("Alignment lag removes the complete record")
        return tek[: n - lag_samples], pico[lag_samples:n], 0, lag_samples
    if lag_samples < 0:
        shift = -lag_samples
        if shift >= n:
            raise ValueError("Alignment lag removes the complete record")
        return tek[shift:n], pico[: n - shift], shift, 0
    return tek, pico, 0, 0


def _window_lag(
    tek: np.ndarray,
    pico: np.ndarray,
    fs: float,
    seconds: float,
    from_end: bool,
    cfg: ScopeComparisonConfig,
) -> float:
    count = min(tek.size, max(16, int(round(seconds * fs))))
    if from_end:
        x, y = tek[-count:], pico[-count:]
    else:
        x, y = tek[:count], pico[:count]
    lag, _ = _estimate_lag_samples(x, y, fs, cfg)
    return 1000.0 * lag / fs


def _corrcoef(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 2 or y.size < 2:
        return float("nan")
    sx = float(np.std(x))
    sy = float(np.std(y))
    if sx == 0.0 or sy == 0.0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _detect_windows(
    tek: np.ndarray,
    pico: np.ndarray,
    fs: float,
    cfg: ScopeComparisonConfig,
) -> dict[str, Any]:
    duration_s = min(tek.size, pico.size) / fs
    if cfg.windows.mode == "full":
        trigger_s = 0.0
        active_start = 0.0
        active_stop = duration_s
        idle_start = idle_stop = 0.0
        status = "full_record"
    else:
        if cfg.windows.mode == "fixed_trigger":
            trigger_s = float(cfg.windows.trigger_time_s)
            status = "configured_trigger"
        else:
            combined = 0.5 * (tek + pico)
            maximum_detection_rate = min(fs, 20_000.0)
            reduced, detection_rate, factor = _reduce_rate(
                combined, fs, maximum_detection_rate
            )
            requested_smooth_count = max(
                1,
                int(round(cfg.windows.detection_smoothing_ms * 1e-3 * detection_rate)),
            )
            # Preserve enough temporal bins for short high-rate records.  The
            # configured 20-ms smoothing is appropriate for 10-s records but
            # would collapse a 40-ms memory-limited record to only two points.
            maximum_smooth_count = max(1, int(reduced.size // 128))
            smooth_count = min(requested_smooth_count, maximum_smooth_count)
            smoothed = _block_mean(reduced, smooth_count)
            smoothed_rate = detection_rate / smooth_count
            head = smoothed[: max(3, smoothed.size // 10)]
            tail = smoothed[max(0, smoothed.size // 2) :]
            baseline = float(np.median(head))
            active_level = float(np.median(tail))
            delta = active_level - baseline
            search_start = max(1, int(round(0.02 * smoothed.size)))
            search_stop = max(search_start + 1, int(round(0.85 * smoothed.size)))
            if abs(delta) > max(0.02, 0.02 * max(abs(active_level), abs(baseline), 1.0)):
                threshold = baseline + cfg.windows.threshold_fraction * delta
                if delta >= 0:
                    crossings = np.flatnonzero(smoothed[search_start:search_stop] >= threshold)
                else:
                    crossings = np.flatnonzero(smoothed[search_start:search_stop] <= threshold)
            else:
                crossings = np.asarray([], dtype=int)
            if crossings.size:
                index = int(crossings[0] + search_start)
                trigger_s = index / smoothed_rate
                status = "detected_threshold_crossing"
            else:
                derivative = np.abs(np.diff(smoothed))
                if derivative.size == 0:
                    trigger_s = 0.0
                    status = "fallback_record_start"
                else:
                    index = int(np.argmax(derivative[search_start:search_stop]) + search_start + 1)
                    trigger_s = index / smoothed_rate
                    status = "detected_maximum_step"
            status += f"; reduction_factor={factor}; smoothed_rate={smoothed_rate:g}"

        active_start = trigger_s + cfg.windows.guard_after_trigger_s
        active_stop = duration_s - cfg.windows.stop_margin_s
        idle_stop = max(0.0, trigger_s - cfg.windows.idle_gap_s)
        idle_start = max(0.0, idle_stop - cfg.windows.idle_duration_s)
        if active_stop - active_start < cfg.windows.minimum_active_duration_s:
            active_start = min(max(0.0, trigger_s), duration_s)
            active_stop = duration_s
            status += "; active-window fallback"

    return {
        "record_duration_s": duration_s,
        "trigger_time_s": trigger_s,
        "idle_start_s": idle_start,
        "idle_stop_s": idle_stop,
        "active_start_s": active_start,
        "active_stop_s": active_stop,
        "idle_duration_s": max(0.0, idle_stop - idle_start),
        "active_duration_s": max(0.0, active_stop - active_start),
        "status": status,
    }


def _windows_from_shared_trigger(
    duration_s: float,
    trigger_s: float,
    cfg: ScopeComparisonConfig,
    source_run: int,
    detected_trigger_s: float,
) -> dict[str, Any]:
    """Construct identical analysis windows for a hardware-triggered rate set.

    The current-only Parquet exports do not contain the GPIO channel, but every
    record at a given rate was triggered at the same oscilloscope position.  The
    first valid pair therefore anchors the trigger-relative windows for the rate;
    later current-step detections are retained only as a diagnostic.
    """

    trigger_s = float(np.clip(trigger_s, 0.0, duration_s))
    if cfg.windows.mode == "full":
        return {
            "record_duration_s": duration_s,
            "trigger_time_s": trigger_s,
            "detected_trigger_time_s": float(detected_trigger_s),
            "shared_trigger_time_s": trigger_s,
            "shared_trigger_source_run": int(source_run),
            "trigger_detection_residual_ms": 1000.0
            * (detected_trigger_s - trigger_s),
            "trigger_window_policy": "configured_record_start_full_record",
            "idle_start_s": 0.0,
            "idle_stop_s": 0.0,
            "active_start_s": 0.0,
            "active_stop_s": duration_s,
            "idle_duration_s": 0.0,
            "active_duration_s": duration_s,
            "status": "full_record_from_hardware_trigger_at_record_start",
        }
    active_start = trigger_s + cfg.windows.guard_after_trigger_s
    active_stop = duration_s - cfg.windows.stop_margin_s
    idle_stop = max(0.0, trigger_s - cfg.windows.idle_gap_s)
    idle_start = max(0.0, idle_stop - cfg.windows.idle_duration_s)
    status = f"shared_hardware_trigger_anchor_run_{source_run}"
    if active_stop - active_start < cfg.windows.minimum_active_duration_s:
        active_start = min(max(0.0, trigger_s), duration_s)
        active_stop = duration_s
        status += "; active-window fallback"
    return {
        "record_duration_s": duration_s,
        "trigger_time_s": trigger_s,
        "detected_trigger_time_s": float(detected_trigger_s),
        "shared_trigger_time_s": trigger_s,
        "shared_trigger_source_run": int(source_run),
        "trigger_detection_residual_ms": 1000.0 * (detected_trigger_s - trigger_s),
        "trigger_window_policy": "shared_hardware_trigger_position",
        "idle_start_s": idle_start,
        "idle_stop_s": idle_stop,
        "active_start_s": active_start,
        "active_stop_s": active_stop,
        "idle_duration_s": max(0.0, idle_stop - idle_start),
        "active_duration_s": max(0.0, active_stop - active_start),
        "status": status,
    }


def _time_slice(values: np.ndarray, fs: float, start_s: float, stop_s: float) -> np.ndarray:
    start = max(0, int(round(start_s * fs)))
    stop = min(values.size, int(round(stop_s * fs)))
    if stop <= start:
        return np.asarray([], dtype=np.float64)
    return np.asarray(values[start:stop], dtype=np.float64)


def _integral(values: np.ndarray, fs: float) -> float:
    if values.size < 2:
        return 0.0
    return float(trapezoid(values, dx=1.0 / fs))


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values), dtype=np.float64)))


def _nrmse(reference: np.ndarray, candidate: np.ndarray) -> float:
    if reference.size == 0:
        return float("nan")
    rmse = float(np.sqrt(np.mean(np.square(candidate - reference), dtype=np.float64)))
    scale = float(np.quantile(reference, 0.95) - np.quantile(reference, 0.05))
    if scale <= 0:
        scale = _rms(reference)
    return rmse / scale if scale > 0 else float("nan")


def _regression(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float, float]:
    if reference.size < 2 or np.std(reference) == 0:
        return float("nan"), float("nan"), float("nan")
    gain, offset = np.polyfit(reference, candidate, 1)
    predicted = gain * reference + offset
    ss_res = float(np.sum(np.square(candidate - predicted)))
    ss_tot = float(np.sum(np.square(candidate - np.mean(candidate))))
    r2 = float("nan") if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return float(gain), float(offset), r2


def _valid_range_fraction(values: np.ndarray, cfg: ScopeComparisonConfig) -> float:
    low = cfg.voltage_model.valid_current_min_a
    high = cfg.voltage_model.valid_current_max_a
    if low is None or high is None or values.size == 0:
        return 0.0
    return float(np.mean((values < low) | (values > high)))


def _decimate_for_plot(values: np.ndarray, maximum_points: int = 120_000) -> tuple[np.ndarray, int]:
    factor = max(1, int(math.ceil(values.size / maximum_points)))
    return _block_mean(values, factor), factor


def _f_at_cumulative(frequencies: np.ndarray, cumulative: np.ndarray, fraction: float) -> float:
    if frequencies.size == 0 or cumulative.size == 0 or not np.isfinite(cumulative[-1]):
        return float("nan")
    index = int(np.searchsorted(cumulative, fraction, side="left"))
    if index <= 0:
        return float(frequencies[0])
    if index >= frequencies.size:
        return float(frequencies[-1])
    x0, x1 = cumulative[index - 1], cumulative[index]
    f0, f1 = frequencies[index - 1], frequencies[index]
    if x1 == x0:
        return float(f1)
    return float(f0 + (fraction - x0) * (f1 - f0) / (x1 - x0))


def _cumulative_density(frequencies: np.ndarray, density: np.ndarray) -> np.ndarray:
    if frequencies.size < 2:
        return np.zeros_like(frequencies)
    cumulative = cumulative_trapezoid(density, frequencies, initial=0.0)
    total = float(cumulative[-1])
    if total <= 0 or not np.isfinite(total):
        return np.zeros_like(cumulative)
    return cumulative / total


def _density_fraction_below(
    frequencies: np.ndarray,
    density: np.ndarray,
    upper_hz: float,
) -> float:
    total = float(trapezoid(density, frequencies)) if frequencies.size > 1 else 0.0
    if total <= 0:
        return float("nan")
    mask = frequencies <= upper_hz
    if np.count_nonzero(mask) < 2:
        return 0.0
    return float(trapezoid(density[mask], frequencies[mask]) / total)


def _welch_segment_count(
    sample_count: int,
    nperseg: int,
    noverlap: int,
) -> int:
    """Return the number of complete Welch segments.

    A single segment makes magnitude-squared coherence identically one.  The
    count is therefore part of the validity contract rather than a cosmetic
    plotting detail.
    """

    sample_count = int(sample_count)
    nperseg = int(nperseg)
    noverlap = int(noverlap)
    if nperseg <= 0 or sample_count < nperseg:
        return 0
    step = nperseg - noverlap
    if step <= 0:
        return 0
    return 1 + (sample_count - nperseg) // step


def _choose_welch_parameters(
    sample_count: int,
    sample_rate_sps: float,
    cfg: ScopeComparisonConfig,
    *,
    minimum_segments: int,
) -> tuple[int, int, int, str]:
    """Choose the largest segment length that supports enough averages.

    The requested time resolution is retained whenever possible.  For short
    high-rate records the segment length is reduced until at least the
    configured number of Welch segments fits.  If even 32 samples cannot meet
    the target, the best available grid is returned and marked insufficient.
    """

    sample_count = int(sample_count)
    if sample_count < 32:
        return 0, 0, 0, "insufficient_samples"
    requested = min(
        int(cfg.spectral.max_nperseg),
        max(32, int(round(cfg.spectral.segment_duration_s * sample_rate_sps))),
        sample_count,
    )

    def values(nperseg: int) -> tuple[int, int]:
        noverlap = min(
            nperseg - 1,
            int(round(cfg.spectral.overlap_fraction * nperseg)),
        )
        return noverlap, _welch_segment_count(sample_count, nperseg, noverlap)

    noverlap, count = values(requested)
    if count >= minimum_segments:
        return requested, noverlap, count, "requested_segment_duration"

    # Find the largest nperseg that provides the required number of segments.
    low, high = 32, requested
    selected: tuple[int, int, int] | None = None
    while low <= high:
        middle = (low + high) // 2
        middle_overlap, middle_count = values(middle)
        if middle_count >= minimum_segments:
            selected = (middle, middle_overlap, middle_count)
            low = middle + 1
        else:
            high = middle - 1
    if selected is not None:
        return (*selected, "short_record_adaptive")

    # Preserve a valid PSD even when statistical agreement metrics cannot be
    # estimated.  Downstream code suppresses coherence in this case.
    nperseg = min(requested, sample_count)
    noverlap, count = values(nperseg)
    return nperseg, noverlap, count, "insufficient_segments"


def _analysis_density(
    active_psd: np.ndarray,
    idle_psd: np.ndarray,
    idle_available: bool,
) -> tuple[np.ndarray, str, bool]:
    if idle_available:
        return (
            np.maximum(active_psd - idle_psd, 0.0),
            "active_minus_prebenchmark_idle",
            True,
        )
    return (
        np.asarray(active_psd, dtype=np.float64),
        "active_only_mean_centered",
        False,
    )


def _resample_for_spectral(
    values: np.ndarray,
    fs: float,
    maximum_rate: int,
) -> tuple[np.ndarray, float, int]:
    return _reduce_rate(values, fs, float(maximum_rate))


def _spectral_bundle(
    tek_power: np.ndarray,
    pico_power: np.ndarray,
    fs: float,
    windows: dict[str, Any],
    cfg: ScopeComparisonConfig,
    external_idle_reference: dict[str, Any] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], list[dict[str, Any]]]:
    """Paired common-band PSD used to assess PicoScope usability.

    The Tektronix-native spectrum is handled separately and is the primary PSD
    reference in v0.5.6.  This function is deliberately limited to the common
    bandwidth after anti-aliased resampling of the faster source.
    """

    tek_reduced, spectral_rate, factor = _resample_for_spectral(
        tek_power, fs, cfg.spectral.max_analysis_rate_sps
    )
    pico_reduced, pico_rate, pico_factor = _resample_for_spectral(
        pico_power, fs, cfg.spectral.max_analysis_rate_sps
    )
    if abs(spectral_rate - pico_rate) > 1e-9 or factor != pico_factor:
        raise RuntimeError("Spectral source-rate mismatch")

    active_tek = _time_slice(
        tek_reduced, spectral_rate, windows["active_start_s"], windows["active_stop_s"]
    )
    active_pico = _time_slice(
        pico_reduced, spectral_rate, windows["active_start_s"], windows["active_stop_s"]
    )
    idle_tek = _time_slice(
        tek_reduced, spectral_rate, windows["idle_start_s"], windows["idle_stop_s"]
    )
    idle_pico = _time_slice(
        pico_reduced, spectral_rate, windows["idle_start_s"], windows["idle_stop_s"]
    )

    active_minimum_length = min(active_tek.size, active_pico.size)
    nperseg, noverlap, active_segment_count, segment_policy = _choose_welch_parameters(
        active_minimum_length,
        spectral_rate,
        cfg,
        minimum_segments=cfg.spectral.minimum_welch_segments,
    )
    if nperseg < 32:
        raise ValueError("Insufficient active data for Welch PSD")
    kwargs = {
        "fs": spectral_rate,
        "window": "hann",
        "nperseg": nperseg,
        "noverlap": noverlap,
        "detrend": "constant",
        "scaling": "density",
    }
    frequencies, tek_active = welch(active_tek, **kwargs)
    _, pico_active = welch(active_pico, **kwargs)

    idle_minimum_length = min(idle_tek.size, idle_pico.size)
    idle_nperseg, idle_noverlap, idle_segment_count, idle_segment_policy = (
        _choose_welch_parameters(
            idle_minimum_length,
            spectral_rate,
            cfg,
            minimum_segments=cfg.spectral.minimum_idle_welch_segments,
        )
        if idle_minimum_length >= 32
        else (0, 0, 0, "insufficient_samples")
    )
    idle_psd_available = bool(
        idle_nperseg >= 32
        and idle_segment_count >= cfg.spectral.minimum_idle_welch_segments
    )
    idle_reference_source = "same_run_prebenchmark" if idle_psd_available else "none"
    if idle_psd_available:
        idle_kwargs = {
            "fs": spectral_rate,
            "window": "hann",
            "nperseg": idle_nperseg,
            "noverlap": idle_noverlap,
            "detrend": "constant",
            "scaling": "density",
        }
        idle_frequencies, tek_idle_native = welch(idle_tek, **idle_kwargs)
        _, pico_idle_native = welch(idle_pico, **idle_kwargs)
        if (
            idle_frequencies.size == frequencies.size
            and np.allclose(idle_frequencies, frequencies, rtol=0.0, atol=1e-12)
        ):
            tek_idle = tek_idle_native
            pico_idle = pico_idle_native
        else:
            tek_idle = np.interp(frequencies, idle_frequencies, tek_idle_native)
            pico_idle = np.interp(frequencies, idle_frequencies, pico_idle_native)
    elif (
        cfg.external_idle.use_for_psd_when_same_run_unavailable
        and external_idle_reference is not None
        and external_idle_reference.get("status") == "available"
        and isinstance(external_idle_reference.get("common"), dict)
    ):
        external = external_idle_reference["common"]
        external_frequencies = np.asarray(
            external["frequencies_hz"], dtype=np.float64
        )
        tek_idle = np.interp(
            frequencies,
            external_frequencies,
            np.asarray(
                external["tek_idle_psd_w2_per_hz_median"], dtype=np.float64
            ),
            left=np.nan,
            right=np.nan,
        )
        pico_idle = np.interp(
            frequencies,
            external_frequencies,
            np.asarray(
                external["pico_idle_psd_w2_per_hz_median"], dtype=np.float64
            ),
            left=np.nan,
            right=np.nan,
        )
        finite_common = np.isfinite(tek_idle) & np.isfinite(pico_idle)
        if np.any(finite_common):
            tek_idle = np.where(finite_common, tek_idle, 0.0)
            pico_idle = np.where(finite_common, pico_idle, 0.0)
            idle_psd_available = True
            idle_reference_source = "external_rate_matched_median"
            summary = external_idle_reference.get("summary", {})
            idle_nperseg = int(summary.get("common_nperseg", 0))
            idle_segment_count = int(
                summary.get("common_welch_segments_minimum", 0)
            )
            idle_segment_policy = "external_rate_matched_median"
            idle_minimum_length = int(
                round(
                    float(summary.get("duration_s_median", 0.0))
                    * spectral_rate
                )
            )
        else:
            tek_idle = np.full_like(tek_active, np.nan)
            pico_idle = np.full_like(pico_active, np.nan)
    else:
        tek_idle = np.full_like(tek_active, np.nan)
        pico_idle = np.full_like(pico_active, np.nan)

    tek_analysis, spectral_basis, workload_related = _analysis_density(
        tek_active,
        np.nan_to_num(tek_idle, nan=0.0),
        idle_psd_available,
    )
    pico_analysis, _, _ = _analysis_density(
        pico_active,
        np.nan_to_num(pico_idle, nan=0.0),
        idle_psd_available,
    )
    if idle_reference_source == "external_rate_matched_median":
        spectral_basis = "active_minus_external_rate_matched_idle"

    coherence_valid = active_segment_count >= cfg.spectral.minimum_welch_segments
    if coherence_valid:
        coherence_kwargs = dict(kwargs)
        coherence_kwargs.pop("scaling", None)
        _, coherence_values = coherence(active_tek, active_pico, **coherence_kwargs)
        _, cross_density = csd(active_pico, active_tek, **kwargs)
        transfer = np.divide(
            cross_density,
            tek_active,
            out=np.zeros_like(cross_density),
            where=tek_active > 0,
        )
        transfer_db = 20.0 * np.log10(
            np.maximum(np.abs(transfer), np.finfo(float).tiny)
        )
        coherence_status = "ok"
    else:
        coherence_values = np.full_like(frequencies, np.nan, dtype=np.float64)
        transfer_db = np.full_like(frequencies, np.nan, dtype=np.float64)
        coherence_status = "insufficient_welch_segments"

    ratio_floor_tek = max(float(np.nanmax(tek_analysis)) * 1e-8, np.finfo(float).tiny)
    ratio_floor_pico = max(float(np.nanmax(pico_analysis)) * 1e-8, np.finfo(float).tiny)
    ratio_valid = (tek_analysis > ratio_floor_tek) & (pico_analysis > ratio_floor_pico)
    ratio_db = np.full_like(tek_analysis, np.nan, dtype=np.float64)
    ratio_db[ratio_valid] = 10.0 * np.log10(
        pico_analysis[ratio_valid] / tek_analysis[ratio_valid]
    )

    tek_cumulative = _cumulative_density(frequencies, tek_analysis)
    pico_cumulative = _cumulative_density(frequencies, pico_analysis)
    metrics: dict[str, Any] = {
        "spectral_rate_sps": spectral_rate,
        "spectral_downsample_factor": factor,
        "spectral_basis": spectral_basis,
        "workload_related_psd_available": bool(workload_related),
        "nperseg": nperseg,
        "active_nperseg": nperseg,
        "active_welch_segments": int(active_segment_count),
        "active_segment_policy": segment_policy,
        "idle_nperseg": int(idle_nperseg),
        "idle_welch_segments": int(idle_segment_count),
        "idle_segment_policy": idle_segment_policy,
        "idle_psd_available": bool(idle_psd_available),
        "idle_reference_source": idle_reference_source,
        "external_idle_pair_count": int(
            external_idle_reference.get("valid_pairs", 0)
            if external_idle_reference is not None
            else 0
        ),
        "external_idle_source_fingerprint_sha256": str(
            external_idle_reference.get("source_fingerprint_sha256", "")
            if external_idle_reference is not None
            else ""
        ),
        "coherence_status": coherence_status,
        "coherence_welch_segments": int(active_segment_count),
        "frequency_resolution_hz": spectral_rate / nperseg,
        "idle_frequency_resolution_hz": (
            spectral_rate / idle_nperseg if idle_psd_available else float("nan")
        ),
        "nyquist_hz": spectral_rate / 2.0,
        "active_samples": int(active_tek.size),
        "idle_samples": int(
            idle_tek.size
            if idle_reference_source == "same_run_prebenchmark"
            else idle_minimum_length
        ),
        "tek_active_psd_integral_w2": float(trapezoid(tek_active, frequencies)),
        "pico_active_psd_integral_w2": float(trapezoid(pico_active, frequencies)),
        "tek_idle_psd_integral_w2": (
            float(trapezoid(tek_idle, frequencies)) if idle_psd_available else float("nan")
        ),
        "pico_idle_psd_integral_w2": (
            float(trapezoid(pico_idle, frequencies)) if idle_psd_available else float("nan")
        ),
        "tek_analysis_psd_integral_w2": float(trapezoid(tek_analysis, frequencies)),
        "pico_analysis_psd_integral_w2": float(trapezoid(pico_analysis, frequencies)),
        "tek_excess_psd_integral_w2": (
            float(trapezoid(tek_analysis, frequencies)) if workload_related else float("nan")
        ),
        "pico_excess_psd_integral_w2": (
            float(trapezoid(pico_analysis, frequencies)) if workload_related else float("nan")
        ),
    }
    for fraction in cfg.spectral.cumulative_percentiles:
        label = int(round(100 * fraction))
        tek_f = _f_at_cumulative(frequencies, tek_cumulative, fraction)
        pico_f = _f_at_cumulative(frequencies, pico_cumulative, fraction)
        metrics[f"tek_analysis_f{label}_hz"] = tek_f
        metrics[f"pico_analysis_f{label}_hz"] = pico_f
        metrics[f"pico_minus_tek_analysis_f{label}_hz"] = pico_f - tek_f
        metrics[f"pico_vs_tek_analysis_f{label}_relative_pct"] = (
            100.0 * (pico_f - tek_f) / tek_f if tek_f > 0 else float("nan")
        )
        metrics[f"tek_f{label}_hz"] = tek_f if workload_related else float("nan")
        metrics[f"pico_f{label}_hz"] = pico_f if workload_related else float("nan")
        metrics[f"pico_minus_tek_f{label}_hz"] = (
            pico_f - tek_f if workload_related else float("nan")
        )
        metrics[f"pico_vs_tek_f{label}_relative_pct"] = (
            100.0 * (pico_f - tek_f) / tek_f
            if workload_related and tek_f > 0
            else float("nan")
        )

    fixed_edges = [
        0.0, 75.0, 200.0, 1_000.0, 5_000.0, 10_000.0, 20_000.0,
        40_000.0, 77_000.0, 125_000.0, 250_000.0, 500_000.0,
        1_000_000.0, 2_500_000.0, 5_000_000.0, 10_000_000.0,
        25_000_000.0, 50_000_000.0, 62_500_000.0, 100_000_000.0,
        125_000_000.0,
    ]
    edges = sorted(
        {edge for edge in fixed_edges if edge < frequencies[-1]}
        | {float(frequencies[-1])}
    )
    total_tek = float(trapezoid(tek_analysis, frequencies))
    total_pico = float(trapezoid(pico_analysis, frequencies))
    band_rows: list[dict[str, Any]] = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= low) & (frequencies < high)
        if np.count_nonzero(mask) < 2:
            continue
        tek_fraction = (
            float(trapezoid(tek_analysis[mask], frequencies[mask]) / total_tek)
            if total_tek > 0 else float("nan")
        )
        pico_fraction = (
            float(trapezoid(pico_analysis[mask], frequencies[mask]) / total_pico)
            if total_pico > 0 else float("nan")
        )
        valid = mask & (frequencies >= cfg.spectral.minimum_frequency_hz)
        valid_ratio = valid & np.isfinite(ratio_db)
        valid_coherence = valid & np.isfinite(coherence_values)
        row = {
            "band_low_hz": low,
            "band_high_hz": high,
            "band": f"{low:g}-{high:g} Hz",
            "spectral_basis": spectral_basis,
            "tek_analysis_variance_fraction": tek_fraction,
            "pico_analysis_variance_fraction": pico_fraction,
            "analysis_variance_fraction_difference_percentage_points": 100.0 * (pico_fraction - tek_fraction),
            "tek_excess_variance_fraction": tek_fraction if workload_related else float("nan"),
            "pico_excess_variance_fraction": pico_fraction if workload_related else float("nan"),
            "variance_fraction_difference_percentage_points": (
                100.0 * (pico_fraction - tek_fraction) if workload_related else float("nan")
            ),
            "coherence_median": (
                float(np.median(coherence_values[valid_coherence]))
                if np.any(valid_coherence) else float("nan")
            ),
            "coherence_q05": (
                quantile(coherence_values[valid_coherence], 0.05)
                if np.any(valid_coherence) else float("nan")
            ),
            "abs_psd_ratio_db_median": (
                float(np.median(np.abs(ratio_db[valid_ratio])))
                if np.any(valid_ratio) else float("nan")
            ),
            "psd_ratio_db_median": (
                float(np.median(ratio_db[valid_ratio]))
                if np.any(valid_ratio) else float("nan")
            ),
        }
        band_rows.append(row)

    valid_frequency = frequencies >= cfg.spectral.minimum_frequency_hz
    valid_coherence = valid_frequency & np.isfinite(coherence_values)
    valid_ratio = valid_frequency & np.isfinite(ratio_db)
    metrics["coherence_median"] = (
        float(np.median(coherence_values[valid_coherence]))
        if np.any(valid_coherence) else float("nan")
    )
    metrics["coherence_q05"] = (
        quantile(coherence_values[valid_coherence], 0.05)
        if np.any(valid_coherence) else float("nan")
    )
    metrics["abs_analysis_psd_ratio_db_median"] = (
        float(np.median(np.abs(ratio_db[valid_ratio])))
        if np.any(valid_ratio) else float("nan")
    )
    metrics["analysis_psd_ratio_db_median"] = (
        float(np.median(ratio_db[valid_ratio]))
        if np.any(valid_ratio) else float("nan")
    )
    # Backward-compatible names are populated only for true active-minus-idle PSDs.
    metrics["abs_excess_psd_ratio_db_median"] = (
        metrics["abs_analysis_psd_ratio_db_median"] if workload_related else float("nan")
    )
    metrics["excess_psd_ratio_db_median"] = (
        metrics["analysis_psd_ratio_db_median"] if workload_related else float("nan")
    )
    metrics["psd_ratio_valid_bin_fraction"] = float(np.mean(ratio_valid))
    for rate in cfg.spectral.variance_capture_rates_sps:
        upper = rate / 2.0
        tek_fraction = _density_fraction_below(frequencies, tek_analysis, upper)
        pico_fraction = _density_fraction_below(frequencies, pico_analysis, upper)
        metrics[f"tek_analysis_variance_below_nyquist_at_{rate}_sps"] = tek_fraction
        metrics[f"pico_analysis_variance_below_nyquist_at_{rate}_sps"] = pico_fraction
        metrics[f"tek_variance_below_nyquist_at_{rate}_sps"] = (
            tek_fraction if workload_related else float("nan")
        )
        metrics[f"pico_variance_below_nyquist_at_{rate}_sps"] = (
            pico_fraction if workload_related else float("nan")
        )

    nan_density = np.full_like(tek_analysis, np.nan, dtype=np.float64)
    arrays = {
        "frequencies_hz": frequencies,
        "tek_active_psd_w2_per_hz": tek_active,
        "pico_active_psd_w2_per_hz": pico_active,
        "tek_idle_psd_w2_per_hz": tek_idle,
        "pico_idle_psd_w2_per_hz": pico_idle,
        "tek_analysis_psd_w2_per_hz": tek_analysis,
        "pico_analysis_psd_w2_per_hz": pico_analysis,
        "tek_analysis_cumulative": tek_cumulative,
        "pico_analysis_cumulative": pico_cumulative,
        "tek_excess_psd_w2_per_hz": tek_analysis if workload_related else nan_density,
        "pico_excess_psd_w2_per_hz": pico_analysis if workload_related else nan_density,
        "tek_excess_cumulative": tek_cumulative if workload_related else nan_density,
        "pico_excess_cumulative": pico_cumulative if workload_related else nan_density,
        "coherence": coherence_values,
        "transfer_magnitude_db": transfer_db,
        "analysis_psd_ratio_db": ratio_db,
        "excess_psd_ratio_db": ratio_db if workload_related else nan_density,
    }
    return arrays, metrics, band_rows


def _resample_signal(
    values: np.ndarray,
    source_rate_sps: float,
    target_rate_sps: float,
) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return values
    if abs(float(source_rate_sps) - float(target_rate_sps)) <= 1e-9:
        return values
    return np.asarray(
        soxr.resample(
            values,
            float(source_rate_sps),
            float(target_rate_sps),
            quality="VHQ",
        ),
        dtype=np.float64,
    )


def _native_spectral_bundle(
    tek_power: np.ndarray,
    tek_rate_sps: float,
    windows: dict[str, Any],
    pico_rate_sps: float,
    cfg: ScopeComparisonConfig,
    external_idle_reference: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    """Characterise the Tektronix-native spectrum as the primary PSD source."""

    reduced, native_rate, factor = _resample_for_spectral(
        tek_power, tek_rate_sps, cfg.spectral.max_analysis_rate_sps
    )
    active = _time_slice(
        reduced, native_rate, windows["active_start_s"], windows["active_stop_s"]
    )
    idle = _time_slice(
        reduced, native_rate, windows["idle_start_s"], windows["idle_stop_s"]
    )
    nperseg, noverlap, active_segment_count, segment_policy = _choose_welch_parameters(
        active.size,
        native_rate,
        cfg,
        minimum_segments=cfg.spectral.minimum_welch_segments,
    )
    metrics: dict[str, Any] = {
        "tek_native_rate_sps": float(native_rate),
        "tek_native_downsample_factor": int(factor),
        "tek_native_nyquist_hz": float(native_rate / 2.0),
        "tek_native_active_samples": int(active.size),
        "tek_native_idle_samples": int(idle.size),
        "tek_native_active_duration_s": float(active.size / native_rate),
        "tek_native_idle_duration_s": float(idle.size / native_rate),
        "tek_native_pico_nyquist_hz": float(pico_rate_sps / 2.0),
        "tek_native_active_welch_segments": int(active_segment_count),
        "tek_native_segment_policy": segment_policy,
    }
    if nperseg < 32:
        metrics["tek_native_spectral_status"] = "insufficient_active_samples"
        return metrics, None

    kwargs = {
        "fs": native_rate,
        "window": "hann",
        "nperseg": nperseg,
        "noverlap": noverlap,
        "detrend": "constant",
        "scaling": "density",
    }
    frequencies, active_psd = welch(active, **kwargs)

    idle_nperseg, idle_noverlap, idle_segment_count, idle_segment_policy = (
        _choose_welch_parameters(
            idle.size,
            native_rate,
            cfg,
            minimum_segments=cfg.spectral.minimum_idle_welch_segments,
        )
        if idle.size >= 32
        else (0, 0, 0, "insufficient_samples")
    )
    idle_available = bool(
        idle_nperseg >= 32
        and idle_segment_count >= cfg.spectral.minimum_idle_welch_segments
    )
    idle_reference_source = "same_run_prebenchmark" if idle_available else "none"
    if idle_available:
        idle_f, idle_native = welch(
            idle,
            fs=native_rate,
            window="hann",
            nperseg=idle_nperseg,
            noverlap=idle_noverlap,
            detrend="constant",
            scaling="density",
        )
        idle_psd = (
            idle_native
            if idle_f.size == frequencies.size
            and np.allclose(idle_f, frequencies, rtol=0.0, atol=1e-12)
            else np.interp(frequencies, idle_f, idle_native)
        )
    elif (
        cfg.external_idle.use_for_psd_when_same_run_unavailable
        and external_idle_reference is not None
        and external_idle_reference.get("status") == "available"
        and isinstance(external_idle_reference.get("native"), dict)
    ):
        external = external_idle_reference["native"]
        external_frequencies = np.asarray(
            external["tek_native_frequencies_hz"], dtype=np.float64
        )
        idle_psd = np.interp(
            frequencies,
            external_frequencies,
            np.asarray(
                external["tek_native_idle_psd_w2_per_hz_median"],
                dtype=np.float64,
            ),
            left=np.nan,
            right=np.nan,
        )
        finite = np.isfinite(idle_psd)
        if np.any(finite):
            idle_psd = np.where(finite, idle_psd, 0.0)
            idle_available = True
            idle_reference_source = "external_rate_matched_median"
            summary = external_idle_reference.get("summary", {})
            idle_nperseg = int(summary.get("native_nperseg", 0))
            idle_segment_count = int(
                summary.get("native_welch_segments_minimum", 0)
            )
            idle_segment_policy = "external_rate_matched_median"
            metrics["tek_native_idle_samples"] = int(
                round(
                    float(summary.get("duration_s_median", 0.0))
                    * native_rate
                )
            )
            metrics["tek_native_idle_duration_s"] = float(
                summary.get("duration_s_median", 0.0)
            )
        else:
            idle_psd = np.full_like(active_psd, np.nan)
    else:
        idle_psd = np.full_like(active_psd, np.nan)

    analysis_psd, basis, workload_related = _analysis_density(
        active_psd,
        np.nan_to_num(idle_psd, nan=0.0),
        idle_available,
    )
    if idle_reference_source == "external_rate_matched_median":
        basis = "active_minus_external_rate_matched_idle"
    cumulative = _cumulative_density(frequencies, analysis_psd)
    total = float(trapezoid(analysis_psd, frequencies)) if frequencies.size > 1 else 0.0
    below_pico = _density_fraction_below(
        frequencies, analysis_psd, pico_rate_sps / 2.0
    )
    below_77 = _density_fraction_below(frequencies, analysis_psd, 77_000.0)

    metrics.update(
        {
            "tek_native_spectral_status": "ok",
            "tek_native_psd_basis": basis,
            "tek_native_workload_related_psd_available": bool(workload_related),
            "tek_native_nperseg": int(nperseg),
            "tek_native_idle_nperseg": int(idle_nperseg),
            "tek_native_idle_welch_segments": int(idle_segment_count),
            "tek_native_idle_segment_policy": idle_segment_policy,
            "tek_native_idle_psd_available": bool(idle_available),
            "tek_native_idle_reference_source": idle_reference_source,
            "tek_native_external_idle_pair_count": int(
                external_idle_reference.get("valid_pairs", 0)
                if external_idle_reference is not None
                else 0
            ),
            "tek_native_external_idle_source_fingerprint_sha256": str(
                external_idle_reference.get("source_fingerprint_sha256", "")
                if external_idle_reference is not None
                else ""
            ),
            "tek_native_frequency_resolution_hz": float(native_rate / nperseg),
            "tek_native_active_psd_integral_w2": float(
                trapezoid(active_psd, frequencies)
            ),
            "tek_native_idle_psd_integral_w2": (
                float(trapezoid(idle_psd, frequencies))
                if idle_available else float("nan")
            ),
            "tek_native_analysis_psd_integral_w2": total,
            "tek_native_excess_psd_integral_w2": (
                total if workload_related else float("nan")
            ),
            "tek_native_analysis_variance_below_pico_nyquist": below_pico,
            "tek_native_analysis_variance_above_pico_nyquist": (
                1.0 - below_pico if np.isfinite(below_pico) else float("nan")
            ),
            "tek_native_analysis_variance_below_77khz": below_77,
            "tek_native_analysis_variance_above_77khz": (
                1.0 - below_77 if np.isfinite(below_77) else float("nan")
            ),
            "tek_native_variance_below_pico_nyquist": (
                below_pico if workload_related else float("nan")
            ),
            "tek_native_variance_above_pico_nyquist": (
                1.0 - below_pico
                if workload_related and np.isfinite(below_pico)
                else float("nan")
            ),
            "tek_native_variance_below_77khz": (
                below_77 if workload_related else float("nan")
            ),
            "tek_native_variance_above_77khz": (
                1.0 - below_77
                if workload_related and np.isfinite(below_77)
                else float("nan")
            ),
            "tek_native_active_variance_below_pico_nyquist": (
                below_pico if not workload_related else float("nan")
            ),
            "tek_native_active_variance_above_pico_nyquist": (
                1.0 - below_pico
                if not workload_related and np.isfinite(below_pico)
                else float("nan")
            ),
            "tek_native_active_variance_below_77khz": (
                below_77 if not workload_related else float("nan")
            ),
            "tek_native_active_variance_above_77khz": (
                1.0 - below_77
                if not workload_related and np.isfinite(below_77)
                else float("nan")
            ),
        }
    )
    for fraction in cfg.spectral.cumulative_percentiles:
        label = int(round(100 * fraction))
        f_value = _f_at_cumulative(frequencies, cumulative, fraction)
        metrics[f"tek_native_analysis_f{label}_hz"] = f_value
        metrics[f"tek_native_f{label}_hz"] = (
            f_value if workload_related else float("nan")
        )
        metrics[f"tek_native_active_f{label}_hz"] = (
            f_value if not workload_related else float("nan")
        )

    nan_density = np.full_like(analysis_psd, np.nan, dtype=np.float64)
    arrays = {
        "tek_native_frequencies_hz": frequencies,
        "tek_native_active_psd_w2_per_hz": active_psd,
        "tek_native_idle_psd_w2_per_hz": idle_psd,
        "tek_native_analysis_psd_w2_per_hz": analysis_psd,
        "tek_native_analysis_cumulative": cumulative,
        "tek_native_excess_psd_w2_per_hz": (
            analysis_psd if workload_related else nan_density
        ),
        "tek_native_excess_cumulative": (
            cumulative if workload_related else nan_density
        ),
    }
    return metrics, arrays


def _pair_metrics(
    cfg: ScopeComparisonConfig,
    rate: int,
    run: int,
    tek_raw: np.ndarray,
    pico_raw: np.ndarray,
    tek_path: Path,
    pico_path: Path,
    tek_meta: dict[str, Any],
    pico_meta: dict[str, Any],
    shared_trigger_time_s: float | None = None,
    shared_trigger_source_run: int | None = None,
    shared_trigger_anchor_source: str | None = None,
    external_idle_reference: dict[str, Any] | None = None,
    zero_correction_model: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, np.ndarray] | None,
    list[dict[str, Any]],
    dict[str, np.ndarray] | None,
    dict[str, np.ndarray] | None,
]:
    tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
    tek_current_native_raw = _calibrate(tek_raw, cfg.tek)
    pico_current_native_raw = _calibrate(pico_raw, cfg.pico)

    tek_nominal_duration = tek_current_native_raw.size / tek_rate
    pico_nominal_duration = pico_current_native_raw.size / pico_rate
    common_nominal_duration = min(tek_nominal_duration, pico_nominal_duration)
    tek_count = min(
        tek_current_native_raw.size,
        int(round(common_nominal_duration * tek_rate)),
    )
    pico_count = min(
        pico_current_native_raw.size,
        int(round(common_nominal_duration * pico_rate)),
    )
    tek_current_native_raw = tek_current_native_raw[:tek_count]
    pico_current_native_raw = pico_current_native_raw[:pico_count]
    zero_offset_a = _zero_offset_for_rate(zero_correction_model, rate)
    tek_current_native = tek_current_native_raw + zero_offset_a
    pico_current_native = pico_current_native_raw

    raw_tek_voltage_native, raw_tek_power_native = _power_from_current(
        tek_current_native_raw, cfg
    )
    raw_pico_voltage_native, raw_pico_power_native = _power_from_current(
        pico_current_native_raw, cfg
    )
    tek_voltage_native, tek_power_native = _power_from_current(
        tek_current_native, cfg
    )
    pico_voltage_native, pico_power_native = _power_from_current(
        pico_current_native, cfg
    )

    # Preserve raw native-grid integrals before applying the documented additive
    # zero correction.  The corrected values remain the primary selected metrics
    # only when the session model passed all stability checks.
    raw_charge_tek = _integral(tek_current_native_raw, tek_rate)
    raw_charge_pico = _integral(pico_current_native_raw, pico_rate)
    raw_energy_tek = _integral(raw_tek_power_native, tek_rate)
    raw_energy_pico = _integral(raw_pico_power_native, pico_rate)
    raw_charge_error = (
        100.0 * (raw_charge_pico - raw_charge_tek) / raw_charge_tek
        if raw_charge_tek
        else float("nan")
    )
    raw_energy_error = (
        100.0 * (raw_energy_pico - raw_energy_tek) / raw_energy_tek
        if raw_energy_tek
        else float("nan")
    )

    # Native-grid corrected integrals are the selected absolute comparison.  The
    # records cover the same trigger-relative physical duration even when their
    # row counts differ by large factors.
    charge_tek = _integral(tek_current_native, tek_rate)
    charge_pico = _integral(pico_current_native, pico_rate)
    energy_tek = _integral(tek_power_native, tek_rate)
    energy_pico = _integral(pico_power_native, pico_rate)
    charge_error = (
        100.0 * (charge_pico - charge_tek) / charge_tek
        if charge_tek
        else float("nan")
    )
    energy_error = (
        100.0 * (energy_pico - energy_tek) / energy_tek
        if energy_tek
        else float("nan")
    )

    # Paired waveform, coherence, and PSD metrics require one common grid.  The
    # higher-rate source is band-limited and resampled to the lower native rate.
    common_rate = min(tek_rate, pico_rate)
    tek_current_raw_common = _resample_signal(
        tek_current_native_raw, tek_rate, common_rate
    )
    tek_current = _resample_signal(
        tek_current_native, tek_rate, common_rate
    )
    pico_current = _resample_signal(
        pico_current_native, pico_rate, common_rate
    )
    common_count = min(
        tek_current_raw_common.size, tek_current.size, pico_current.size
    )
    tek_current_raw_common = tek_current_raw_common[:common_count]
    tek_current = tek_current[:common_count]
    pico_current = pico_current[:common_count]
    tek_voltage, tek_power = _power_from_current(tek_current, cfg)
    pico_voltage, pico_power = _power_from_current(pico_current, cfg)

    lag_samples, alignment = _estimate_lag_samples(
        tek_current, pico_current, float(common_rate), cfg
    )
    tek_aligned, pico_aligned, tek_start, pico_start = _aligned_overlap(
        tek_current, pico_current, lag_samples
    )
    _, tek_power_aligned = _power_from_current(tek_aligned, cfg)
    _, pico_power_aligned = _power_from_current(pico_aligned, cfg)

    drift_window = min(
        cfg.alignment.drift_window_s,
        max(0.01, 0.25 * common_nominal_duration),
    )
    drift_start_ms = _window_lag(
        tek_current,
        pico_current,
        float(common_rate),
        drift_window,
        False,
        cfg,
    )
    drift_end_ms = _window_lag(
        tek_current,
        pico_current,
        float(common_rate),
        drift_window,
        True,
        cfg,
    )
    drift_ms = drift_end_ms - drift_start_ms
    drift_ppm = (
        1000.0 * drift_ms / common_nominal_duration
        if common_nominal_duration > 0
        else float("nan")
    )

    detected_windows = _detect_windows(
        tek_aligned, pico_aligned, float(common_rate), cfg
    )
    if shared_trigger_time_s is not None and shared_trigger_source_run is not None:
        windows = _windows_from_shared_trigger(
            duration_s=min(tek_aligned.size, pico_aligned.size) / float(common_rate),
            trigger_s=shared_trigger_time_s,
            cfg=cfg,
            source_run=shared_trigger_source_run,
            detected_trigger_s=float(detected_windows["trigger_time_s"]),
        )
        windows["shared_trigger_anchor_source"] = str(
            shared_trigger_anchor_source or "shared_anchor"
        )
    else:
        windows = dict(detected_windows)
        windows.update(
            {
                "detected_trigger_time_s": float(detected_windows["trigger_time_s"]),
                "shared_trigger_time_s": float(detected_windows["trigger_time_s"]),
                "shared_trigger_source_run": int(run),
                "shared_trigger_anchor_source": "first_valid_detection",
                "trigger_detection_residual_ms": 0.0,
                "trigger_window_policy": "detected_anchor_for_hardware_trigger_position",
            }
        )

    comparison_tek = (
        tek_aligned
        if cfg.alignment.apply_to_waveform_metrics
        else tek_current[:common_count]
    )
    comparison_pico = (
        pico_aligned
        if cfg.alignment.apply_to_waveform_metrics
        else pico_current[:common_count]
    )

    # Raw full-record integrals remain separately archived above.  Selected
    # full-record integrals may use the audited additive Tektronix zero
    # correction.  For lower-duty-cycle workloads an idle baseline can further
    # explain a large relative difference caused by a DC term.  The following
    # active-window and incremental metrics remain additional diagnostics; they
    # never overwrite either the raw or selected full-record comparison.
    active_tek_current = _time_slice(
        tek_aligned,
        float(common_rate),
        windows["active_start_s"],
        windows["active_stop_s"],
    )
    active_pico_current = _time_slice(
        pico_aligned,
        float(common_rate),
        windows["active_start_s"],
        windows["active_stop_s"],
    )
    _, active_tek_power = _power_from_current(active_tek_current, cfg)
    _, active_pico_power = _power_from_current(active_pico_current, cfg)
    same_idle_tek_current = _time_slice(
        tek_aligned,
        float(common_rate),
        windows["idle_start_s"],
        windows["idle_stop_s"],
    )
    same_idle_pico_current = _time_slice(
        pico_aligned,
        float(common_rate),
        windows["idle_start_s"],
        windows["idle_stop_s"],
    )

    same_run_idle_tek_current = same_run_idle_pico_current = float("nan")
    same_run_idle_tek_power = same_run_idle_pico_power = float("nan")
    external_idle_tek_current = external_idle_pico_current = float("nan")
    external_idle_tek_power = external_idle_pico_power = float("nan")
    external_idle_summary = (
        external_idle_reference.get("summary", {})
        if external_idle_reference is not None
        else {}
    )
    if external_idle_reference is not None and external_idle_reference.get("status") == "available":
        external_idle_tek_current = float(
            external_idle_summary.get("tek_mean_current_a_median", float("nan"))
        )
        external_idle_pico_current = float(
            external_idle_summary.get("pico_mean_current_a_median", float("nan"))
        )
        external_idle_tek_power = float(
            external_idle_summary.get("tek_mean_power_w_median", float("nan"))
        )
        external_idle_pico_power = float(
            external_idle_summary.get("pico_mean_power_w_median", float("nan"))
        )

    baseline_source = "none"
    baseline_tek_current = baseline_pico_current = float("nan")
    baseline_tek_power = baseline_pico_power = float("nan")
    minimum_baseline_samples = max(32, int(round(0.05 * common_rate)))
    if (
        same_idle_tek_current.size >= minimum_baseline_samples
        and same_idle_pico_current.size >= minimum_baseline_samples
    ):
        _, same_idle_tek_power = _power_from_current(same_idle_tek_current, cfg)
        _, same_idle_pico_power = _power_from_current(same_idle_pico_current, cfg)
        same_run_idle_tek_current = float(np.mean(same_idle_tek_current))
        same_run_idle_pico_current = float(np.mean(same_idle_pico_current))
        same_run_idle_tek_power = float(np.mean(same_idle_tek_power))
        same_run_idle_pico_power = float(np.mean(same_idle_pico_power))
        baseline_tek_current = same_run_idle_tek_current
        baseline_pico_current = same_run_idle_pico_current
        baseline_tek_power = same_run_idle_tek_power
        baseline_pico_power = same_run_idle_pico_power
        baseline_source = "same_run_prebenchmark"
    elif (
        cfg.external_idle.use_for_baseline_diagnostics
        and external_idle_reference is not None
        and external_idle_reference.get("status") == "available"
    ):
        baseline_tek_current = external_idle_tek_current
        baseline_pico_current = external_idle_pico_current
        baseline_tek_power = external_idle_tek_power
        baseline_pico_power = external_idle_pico_power
        if all(
            np.isfinite(value)
            for value in (
                baseline_tek_current,
                baseline_pico_current,
                baseline_tek_power,
                baseline_pico_power,
            )
        ):
            baseline_source = "external_rate_matched_median"

    active_charge_tek = _integral(active_tek_current, float(common_rate))
    active_charge_pico = _integral(active_pico_current, float(common_rate))
    active_energy_tek = _integral(active_tek_power, float(common_rate))
    active_energy_pico = _integral(active_pico_power, float(common_rate))
    active_charge_error = (
        100.0 * (active_charge_pico - active_charge_tek) / active_charge_tek
        if active_charge_tek
        else float("nan")
    )
    active_energy_error = (
        100.0 * (active_energy_pico - active_energy_tek) / active_energy_tek
        if active_energy_tek
        else float("nan")
    )

    incremental_charge_tek = incremental_charge_pico = float("nan")
    incremental_energy_tek = incremental_energy_pico = float("nan")
    incremental_charge_error = incremental_energy_error = float("nan")
    incremental_metrics_status = "unavailable_no_idle_baseline"
    if (
        cfg.external_idle.use_for_incremental_energy
        and baseline_source != "none"
        and active_tek_current.size >= 2
        and active_pico_current.size >= 2
    ):
        incremental_charge_tek = _integral(
            active_tek_current - baseline_tek_current,
            float(common_rate),
        )
        incremental_charge_pico = _integral(
            active_pico_current - baseline_pico_current,
            float(common_rate),
        )
        incremental_energy_tek = _integral(
            active_tek_power - baseline_tek_power,
            float(common_rate),
        )
        incremental_energy_pico = _integral(
            active_pico_power - baseline_pico_power,
            float(common_rate),
        )
        charge_floor = max(1e-9, 0.01 * abs(active_charge_tek))
        energy_floor = max(1e-9, 0.01 * abs(active_energy_tek))
        valid_increment = bool(
            incremental_charge_tek > charge_floor
            and incremental_charge_pico > charge_floor
            and incremental_energy_tek > energy_floor
            and incremental_energy_pico > energy_floor
        )
        if valid_increment:
            incremental_charge_error = 100.0 * (
                incremental_charge_pico - incremental_charge_tek
            ) / incremental_charge_tek
            incremental_energy_error = 100.0 * (
                incremental_energy_pico - incremental_energy_tek
            ) / incremental_energy_tek
            incremental_metrics_status = "valid_positive_idle_subtracted_increment"
        else:
            incremental_charge_error = float("nan")
            incremental_energy_error = float("nan")
            incremental_metrics_status = (
                "invalid_nonpositive_or_too_small_idle_subtracted_increment"
            )

    baseline_current_difference_ma = (
        1000.0 * (baseline_pico_current - baseline_tek_current)
        if baseline_source != "none"
        else float("nan")
    )
    baseline_power_difference_w = (
        baseline_pico_power - baseline_tek_power
        if baseline_source != "none"
        else float("nan")
    )
    baseline_mismatch_detected = bool(
        np.isfinite(baseline_current_difference_ma)
        and abs(baseline_current_difference_ma)
        > cfg.external_idle.maximum_idle_current_difference_ma
    )

    reduced_tek, reduced_rate, factor = _reduce_rate(
        comparison_tek, common_rate, 100_000.0
    )
    reduced_pico, _, _ = _reduce_rate(
        comparison_pico, common_rate, 100_000.0
    )
    reduced_n = min(reduced_tek.size, reduced_pico.size)
    reduced_tek = reduced_tek[:reduced_n]
    reduced_pico = reduced_pico[:reduced_n]

    metrics: dict[str, Any] = {
        "scope_analysis_schema_version": _SCOPE_ANALYSIS_SCHEMA_VERSION,
        "rate_sps": rate,
        "directory_rate_sps": rate,
        "tek_rate_sps": float(tek_rate),
        "pico_rate_sps": float(pico_rate),
        "common_comparison_rate_sps": float(common_rate),
        "common_comparison_nyquist_hz": float(common_rate / 2.0),
        "tek_to_pico_rate_ratio": float(tek_rate / pico_rate),
        "rate_comparison_policy": (
            "native_integrals; anti-aliased resampling to lower source rate "
            "for paired waveform/PSD metrics"
        ),
        "run": run,
        "tek_path": str(tek_path),
        "pico_path": str(pico_path),
        "tek_samples": int(tek_raw.size),
        "pico_samples": int(pico_raw.size),
        "tek_nominal_duration_s": float(tek_nominal_duration),
        "pico_nominal_duration_s": float(pico_nominal_duration),
        "duration_difference_s": float(pico_nominal_duration - tek_nominal_duration),
        "common_nominal_duration_s": float(common_nominal_duration),
        "used_samples": int(common_count),
        "record_duration_nominal_s": float(common_nominal_duration),
        "sample_interval_us": 1e6 / common_rate,
        "tek_sample_interval_ns": 1e9 / tek_rate,
        "pico_sample_interval_ns": 1e9 / pico_rate,
        "tek_raw_unit": cfg.tek.raw_unit,
        "pico_raw_unit": cfg.pico.raw_unit,
        "zero_offset_detection_status": (
            zero_correction_model.get("status", "disabled")
            if zero_correction_model is not None
            else "disabled"
        ),
        "zero_offset_detected": bool(
            zero_correction_model.get("offset_detected", False)
            if zero_correction_model is not None
            else False
        ),
        "zero_offset_correction_applied": bool(abs(zero_offset_a) > 0.0),
        "zero_offset_target_source": (
            zero_correction_model.get("target_source", "tek")
            if zero_correction_model is not None
            else "tek"
        ),
        "zero_offset_reference_source": (
            zero_correction_model.get("reference_source", "none")
            if zero_correction_model is not None
            else "none"
        ),
        "zero_offset_estimate_a": (
            float(zero_correction_model.get("offset_estimate_a"))
            if zero_correction_model is not None
            and zero_correction_model.get("offset_estimate_a") is not None
            else float("nan")
        ),
        "zero_offset_estimate_ma": (
            float(zero_correction_model.get("offset_estimate_ma"))
            if zero_correction_model is not None
            and zero_correction_model.get("offset_estimate_ma") is not None
            else float("nan")
        ),
        "zero_offset_uncertainty_ma": (
            float(zero_correction_model.get("offset_uncertainty_ma"))
            if zero_correction_model is not None
            and zero_correction_model.get("offset_uncertainty_ma") is not None
            else float("nan")
        ),
        "zero_offset_confidence": (
            str(zero_correction_model.get("confidence", "none"))
            if zero_correction_model is not None
            else "none"
        ),
        "zero_offset_reference_rate_count": int(
            zero_correction_model.get("reference_rate_count", 0)
            if zero_correction_model is not None
            else 0
        ),
        "zero_offset_reference_pair_count": int(
            zero_correction_model.get("reference_pair_count", 0)
            if zero_correction_model is not None
            else 0
        ),
        "zero_offset_validation_independence": (
            str(
                zero_correction_model.get(
                    "validation_independence", "not_applicable"
                )
            )
            if zero_correction_model is not None
            else "not_applicable"
        ),
        "zero_offset_applied_a": float(zero_offset_a),
        "zero_offset_applied_ma": float(1000.0 * zero_offset_a),
        "zero_offset_model_hash": (
            zero_correction_model.get("model_hash", "")
            if zero_correction_model is not None
            else ""
        ),
        "zero_offset_reference_independent": bool(
            zero_correction_model.get("independent_reference", False)
            if zero_correction_model is not None
            else False
        ),
        "absolute_comparison_basis": (
            "offset_corrected_"
            + str(
                zero_correction_model.get(
                    "reference_source", "adaptive_zero_offset"
                )
                if zero_correction_model is not None
                else "adaptive_zero_offset"
            )
            + "_salvage"
            if abs(zero_offset_a) > 0.0
            else "raw_calibrated_currents"
        ),
        "absolute_validation_independent": bool(
            zero_correction_model.get("independent_reference", False)
            if abs(zero_offset_a) > 0.0
            and zero_correction_model is not None
            else True
        ),
        "raw_tek_mean_current_a": float(np.mean(tek_current_native_raw)),
        "raw_pico_mean_current_a": float(np.mean(pico_current_native_raw)),
        "raw_mean_current_difference_a": float(
            np.mean(pico_current_native_raw)
            - np.mean(tek_current_native_raw)
        ),
        "raw_mean_current_difference_ma": float(
            1000.0
            * (
                np.mean(pico_current_native_raw)
                - np.mean(tek_current_native_raw)
            )
        ),
        "tek_mean_current_a": float(np.mean(tek_current_native)),
        "pico_mean_current_a": float(np.mean(pico_current_native)),
        "mean_current_difference_a": float(
            np.mean(pico_current_native) - np.mean(tek_current_native)
        ),
        "mean_current_difference_ma": float(
            1000.0 * (np.mean(pico_current_native) - np.mean(tek_current_native))
        ),
        "operating_region": (
            "low_current"
            if float(np.mean(tek_current_native)) < cfg.validation.low_current_threshold_a
            else "nominal_current"
        ),
        "low_current_threshold_a": float(cfg.validation.low_current_threshold_a),
        "tek_rms_current_a": _rms(tek_current_native),
        "pico_rms_current_a": _rms(pico_current_native),
        "tek_min_current_a": float(np.min(tek_current_native)),
        "tek_max_current_a": float(np.max(tek_current_native)),
        "pico_min_current_a": float(np.min(pico_current_native)),
        "pico_max_current_a": float(np.max(pico_current_native)),
        "raw_tek_charge_as": raw_charge_tek,
        "raw_pico_charge_as": raw_charge_pico,
        "raw_pico_vs_tek_charge_error_pct": raw_charge_error,
        "raw_tek_estimated_energy_j": raw_energy_tek,
        "raw_pico_estimated_energy_j": raw_energy_pico,
        "raw_pico_vs_tek_energy_error_pct": raw_energy_error,
        "tek_charge_as": charge_tek,
        "pico_charge_as": charge_pico,
        "pico_vs_tek_charge_error_pct": charge_error,
        "tek_estimated_energy_j": energy_tek,
        "pico_estimated_energy_j": energy_pico,
        "pico_vs_tek_energy_error_pct": energy_error,
        "zero_offset_charge_error_change_pct_points": (
            charge_error - raw_charge_error
            if np.isfinite(charge_error) and np.isfinite(raw_charge_error)
            else float("nan")
        ),
        "zero_offset_energy_error_change_pct_points": (
            energy_error - raw_energy_error
            if np.isfinite(energy_error) and np.isfinite(raw_energy_error)
            else float("nan")
        ),
        "active_window_tek_charge_as": active_charge_tek,
        "active_window_pico_charge_as": active_charge_pico,
        "active_window_charge_error_pct": active_charge_error,
        "active_window_tek_estimated_energy_j": active_energy_tek,
        "active_window_pico_estimated_energy_j": active_energy_pico,
        "active_window_energy_error_pct": active_energy_error,
        "idle_baseline_source": baseline_source,
        "idle_baseline_tek_current_a": baseline_tek_current,
        "idle_baseline_pico_current_a": baseline_pico_current,
        "idle_baseline_current_difference_ma": baseline_current_difference_ma,
        "idle_baseline_tek_power_w": baseline_tek_power,
        "idle_baseline_pico_power_w": baseline_pico_power,
        "idle_baseline_power_difference_w": baseline_power_difference_w,
        "idle_baseline_mismatch_detected": baseline_mismatch_detected,
        "same_run_idle_tek_current_a": same_run_idle_tek_current,
        "same_run_idle_pico_current_a": same_run_idle_pico_current,
        "same_run_idle_current_difference_ma": (
            1000.0 * (same_run_idle_pico_current - same_run_idle_tek_current)
            if np.isfinite(same_run_idle_tek_current)
            and np.isfinite(same_run_idle_pico_current)
            else float("nan")
        ),
        "same_run_idle_tek_power_w": same_run_idle_tek_power,
        "same_run_idle_pico_power_w": same_run_idle_pico_power,
        "external_idle_tek_current_a_median": external_idle_tek_current,
        "external_idle_pico_current_a_median": external_idle_pico_current,
        "external_idle_current_difference_ma_median": (
            1000.0 * (external_idle_pico_current - external_idle_tek_current)
            if np.isfinite(external_idle_tek_current)
            and np.isfinite(external_idle_pico_current)
            else float("nan")
        ),
        "external_idle_tek_power_w_median": external_idle_tek_power,
        "external_idle_pico_power_w_median": external_idle_pico_power,
        "same_run_minus_external_idle_tek_current_ma": (
            1000.0 * (same_run_idle_tek_current - external_idle_tek_current)
            if np.isfinite(same_run_idle_tek_current)
            and np.isfinite(external_idle_tek_current)
            else float("nan")
        ),
        "same_run_minus_external_idle_pico_current_ma": (
            1000.0 * (same_run_idle_pico_current - external_idle_pico_current)
            if np.isfinite(same_run_idle_pico_current)
            and np.isfinite(external_idle_pico_current)
            else float("nan")
        ),
        "incremental_tek_charge_as": incremental_charge_tek,
        "incremental_pico_charge_as": incremental_charge_pico,
        "incremental_charge_error_pct": incremental_charge_error,
        "incremental_tek_estimated_energy_j": incremental_energy_tek,
        "incremental_pico_estimated_energy_j": incremental_energy_pico,
        "incremental_energy_error_pct": incremental_energy_error,
        "incremental_metrics_status": incremental_metrics_status,
        "incremental_metrics_interpretation": (
            "diagnostic_idle_subtracted_active_window; raw_absolute_results_preserved"
            if baseline_source != "none"
            else "unavailable_no_idle_baseline"
        ),
        "external_idle_status": (
            str(external_idle_reference.get("status", "unavailable"))
            if external_idle_reference is not None
            else "disabled"
        ),
        "external_idle_pair_count": int(
            external_idle_reference.get("valid_pairs", 0)
            if external_idle_reference is not None
            else 0
        ),
        "external_idle_source_fingerprint_sha256": str(
            external_idle_reference.get("source_fingerprint_sha256", "")
            if external_idle_reference is not None
            else ""
        ),
        "raw_tek_mean_estimated_voltage_v": float(
            np.mean(raw_tek_voltage_native)
        ),
        "raw_pico_mean_estimated_voltage_v": float(
            np.mean(raw_pico_voltage_native)
        ),
        "tek_mean_estimated_voltage_v": float(np.mean(tek_voltage_native)),
        "pico_mean_estimated_voltage_v": float(np.mean(pico_voltage_native)),
        "tek_voltage_model_outside_range_fraction": _valid_range_fraction(
            tek_current_native, cfg
        ),
        "pico_voltage_model_outside_range_fraction": _valid_range_fraction(
            pico_current_native, cfg
        ),
        "lag_samples": lag_samples,
        "lag_ms": alignment["lag_ms"],
        "alignment_analysis_rate_sps": alignment["analysis_rate_sps"],
        "alignment_status": alignment["status"],
        "drift_start_lag_ms": drift_start_ms,
        "drift_end_lag_ms": drift_end_ms,
        "drift_change_ms": drift_ms,
        "drift_ppm_approx": drift_ppm,
        "aligned_overlap_samples": int(tek_aligned.size),
        "tek_alignment_trim_start_samples": tek_start,
        "pico_alignment_trim_start_samples": pico_start,
        "raw_or_decimated_aligned_correlation": _corrcoef(
            reduced_tek, reduced_pico
        ),
        "aligned_nrmse": _nrmse(reduced_tek, reduced_pico),
        **windows,
    }

    regression_reference = None
    regression_candidate = None
    correlation_candidates: list[tuple[float, float, float, int]] = []
    for window_ms in cfg.averaging_windows_ms:
        block = max(1, int(round(window_ms * 1e-3 * common_rate)))
        tek_binned = _block_mean(comparison_tek, block)
        pico_binned = _block_mean(comparison_pico, block)
        count = min(tek_binned.size, pico_binned.size)
        tek_binned = tek_binned[:count]
        pico_binned = pico_binned[:count]
        label = f"{window_ms:g}ms".replace(".", "p")
        metrics[f"correlation_{label}_window_count"] = int(count)
        enough_windows = count >= cfg.validation.minimum_correlation_windows
        metrics[f"correlation_{label}_status"] = (
            "ok" if enough_windows else "insufficient_windows"
        )
        correlation_value = (
            _corrcoef(tek_binned, pico_binned) if enough_windows else float("nan")
        )
        nrmse_value = (
            _nrmse(tek_binned, pico_binned) if enough_windows else float("nan")
        )
        metrics[f"correlation_{label}"] = correlation_value
        metrics[f"nrmse_{label}"] = nrmse_value
        if enough_windows:
            correlation_candidates.append(
                (float(window_ms), correlation_value, nrmse_value, int(count))
            )
        if regression_reference is None or abs(window_ms - 10.0) < 1e-9:
            regression_reference = tek_binned
            regression_candidate = pico_binned

    if correlation_candidates:
        # Use the longest statistically supported smoothing window.  Short
        # records therefore fall back from 100 ms to 50 or 10 ms instead of
        # producing a meaningless two-point correlation.
        selected_window, selected_corr, selected_nrmse, selected_count = max(
            correlation_candidates, key=lambda item: item[0]
        )
        metrics["selected_correlation_window_ms"] = selected_window
        metrics["selected_correlation"] = selected_corr
        metrics["selected_nrmse"] = selected_nrmse
        metrics["selected_correlation_window_count"] = selected_count
        metrics["selected_correlation_status"] = "ok"
    else:
        metrics["selected_correlation_window_ms"] = float("nan")
        metrics["selected_correlation"] = float("nan")
        metrics["selected_nrmse"] = float("nan")
        metrics["selected_correlation_window_count"] = 0
        metrics["selected_correlation_status"] = "insufficient_windows"

    gain, offset, r2 = _regression(regression_reference, regression_candidate)
    metrics["pico_vs_tek_regression_gain"] = gain
    metrics["pico_vs_tek_regression_offset_a"] = offset
    metrics["pico_vs_tek_regression_r2"] = r2

    spectral_arrays = None
    native_spectral_arrays = None
    band_rows: list[dict[str, Any]] = []
    if cfg.spectral.enabled:
        spectral_arrays, spectral_metrics, band_rows = _spectral_bundle(
            tek_power_aligned,
            pico_power_aligned,
            float(common_rate),
            windows,
            cfg,
            external_idle_reference=external_idle_reference,
        )
        metrics.update(spectral_metrics)
        native_metrics, native_spectral_arrays = _native_spectral_bundle(
            tek_power_native,
            tek_rate,
            windows,
            pico_rate,
            cfg,
            external_idle_reference=external_idle_reference,
        )
        metrics.update(native_metrics)

    representative: dict[str, np.ndarray] | None = None
    if True:
        tek_raw_plot, raw_factor_plot = _decimate_for_plot(
            tek_current_raw_common
        )
        tek_plot, factor_plot = _decimate_for_plot(tek_current)
        pico_plot, _ = _decimate_for_plot(pico_current)
        nplot = min(tek_raw_plot.size, tek_plot.size, pico_plot.size)
        plot_rate = common_rate / factor_plot
        tek_a_plot, aligned_factor = _decimate_for_plot(tek_aligned)
        pico_a_plot, _ = _decimate_for_plot(pico_aligned)
        naplot = min(tek_a_plot.size, pico_a_plot.size)
        representative = {
            "time_raw_s": np.arange(nplot, dtype=np.float64) / plot_rate,
            "tek_current_raw_a": tek_raw_plot[:nplot],
            "tek_current_a": tek_plot[:nplot],
            "pico_current_a": pico_plot[:nplot],
            "zero_offset_applied_a": np.asarray([zero_offset_a]),
            "time_aligned_s": np.arange(naplot, dtype=np.float64)
            / (common_rate / aligned_factor),
            "tek_aligned_current_a": tek_a_plot[:naplot],
            "pico_aligned_current_a": pico_a_plot[:naplot],
            "trigger_time_s": np.asarray([windows["trigger_time_s"]]),
            "idle_start_s": np.asarray([windows["idle_start_s"]]),
            "idle_stop_s": np.asarray([windows["idle_stop_s"]]),
            "active_start_s": np.asarray([windows["active_start_s"]]),
            "active_stop_s": np.asarray([windows["active_stop_s"]]),
            "lag_ms": np.asarray([alignment["lag_ms"]]),
            "tek_rate_sps": np.asarray([tek_rate]),
            "pico_rate_sps": np.asarray([pico_rate]),
            "common_rate_sps": np.asarray([common_rate]),
        }

    metadata = {
        "tek_parquet": tek_meta,
        "pico_parquet": pico_meta,
        "tek_rate_sps": tek_rate,
        "pico_rate_sps": pico_rate,
        "common_comparison_rate_sps": common_rate,
        "alignment": alignment,
        "windows": windows,
        "voltage_model": normalise_for_json(cfg.voltage_model),
        "zero_offset_correction": {
            "model": normalise_for_json(zero_correction_model or {}),
            "offset_applied_a": float(zero_offset_a),
            "raw_metrics_preserved": True,
        },
        "external_idle": {
            "status": (
                external_idle_reference.get("status", "unavailable")
                if external_idle_reference is not None
                else "disabled"
            ),
            "source_fingerprint_sha256": (
                external_idle_reference.get("source_fingerprint_sha256", "")
                if external_idle_reference is not None
                else ""
            ),
            "baseline_source_used": baseline_source,
        },
    }
    return (
        metrics,
        metadata,
        spectral_arrays,
        band_rows,
        representative,
        native_spectral_arrays,
    )


def _summary_row(values: np.ndarray, prefix: str) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    return {
        f"{prefix}_mean": float(np.mean(finite)) if finite.size else float("nan"),
        f"{prefix}_median": float(np.median(finite)) if finite.size else float("nan"),
        f"{prefix}_std": float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0,
        f"{prefix}_q05": quantile(finite, 0.05),
        f"{prefix}_q95": quantile(finite, 0.95),
        f"{prefix}_min": float(np.min(finite)) if finite.size else float("nan"),
        f"{prefix}_max": float(np.max(finite)) if finite.size else float("nan"),
    }


def _aggregate_pair_metrics(rows: list[dict[str, Any]], rate: int) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rate_sps": rate,
        "directory_rate_sps": rate,
        "tek_rate_sps": float(rows[0].get("tek_rate_sps", rate)),
        "pico_rate_sps": float(rows[0].get("pico_rate_sps", rate)),
        "common_comparison_rate_sps": float(
            rows[0].get("common_comparison_rate_sps", rate)
        ),
        "common_comparison_nyquist_hz": float(
            rows[0].get("common_comparison_nyquist_hz", rate / 2.0)
        ),
        "n_pairs": len(rows),
        "run_ids": ",".join(str(row["run"]) for row in rows),
    }
    numeric_keys = [
        "raw_pico_vs_tek_charge_error_pct",
        "raw_pico_vs_tek_energy_error_pct",
        "zero_offset_charge_error_change_pct_points",
        "zero_offset_energy_error_change_pct_points",
        "zero_offset_estimate_a",
        "zero_offset_estimate_ma",
        "zero_offset_applied_a",
        "zero_offset_applied_ma",
        "raw_tek_charge_as",
        "raw_pico_charge_as",
        "raw_tek_estimated_energy_j",
        "raw_pico_estimated_energy_j",
        "raw_tek_mean_current_a",
        "raw_pico_mean_current_a",
        "raw_mean_current_difference_a",
        "raw_mean_current_difference_ma",
        "pico_vs_tek_charge_error_pct",
        "pico_vs_tek_energy_error_pct",
        "active_window_tek_charge_as",
        "active_window_pico_charge_as",
        "active_window_charge_error_pct",
        "active_window_tek_estimated_energy_j",
        "active_window_pico_estimated_energy_j",
        "active_window_energy_error_pct",
        "idle_baseline_tek_current_a",
        "idle_baseline_pico_current_a",
        "idle_baseline_current_difference_ma",
        "idle_baseline_tek_power_w",
        "idle_baseline_pico_power_w",
        "idle_baseline_power_difference_w",
        "same_run_idle_tek_current_a",
        "same_run_idle_pico_current_a",
        "same_run_idle_current_difference_ma",
        "same_run_idle_tek_power_w",
        "same_run_idle_pico_power_w",
        "external_idle_tek_current_a_median",
        "external_idle_pico_current_a_median",
        "external_idle_current_difference_ma_median",
        "external_idle_tek_power_w_median",
        "external_idle_pico_power_w_median",
        "same_run_minus_external_idle_tek_current_ma",
        "same_run_minus_external_idle_pico_current_ma",
        "incremental_tek_charge_as",
        "incremental_pico_charge_as",
        "incremental_charge_error_pct",
        "incremental_tek_estimated_energy_j",
        "incremental_pico_estimated_energy_j",
        "incremental_energy_error_pct",
        "lag_ms",
        "drift_change_ms",
        "drift_ppm_approx",
        "trigger_detection_residual_ms",
        "raw_or_decimated_aligned_correlation",
        "correlation_10ms",
        "correlation_50ms",
        "correlation_100ms",
        "nrmse_10ms",
        "nrmse_50ms",
        "nrmse_100ms",
        "pico_vs_tek_regression_gain",
        "pico_vs_tek_regression_offset_a",
        "pico_vs_tek_regression_r2",
        "tek_charge_as",
        "pico_charge_as",
        "tek_estimated_energy_j",
        "pico_estimated_energy_j",
        "tek_mean_current_a",
        "pico_mean_current_a",
        "mean_current_difference_a",
        "mean_current_difference_ma",
        "selected_correlation_window_ms",
        "selected_correlation",
        "selected_nrmse",
        "selected_correlation_window_count",
        "tek_nominal_duration_s",
        "pico_nominal_duration_s",
        "duration_difference_s",
        "common_nominal_duration_s",
    ]
    for key in numeric_keys:
        values = np.asarray([float(row.get(key, float("nan"))) for row in rows])
        summary.update(_summary_row(values, key))

    summary["raw_abs_charge_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [
                    row.get("raw_pico_vs_tek_charge_error_pct", float("nan"))
                    for row in rows
                ],
                dtype=float,
            )
        ),
        0.95,
    )
    summary["raw_abs_energy_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [
                    row.get("raw_pico_vs_tek_energy_error_pct", float("nan"))
                    for row in rows
                ],
                dtype=float,
            )
        ),
        0.95,
    )
    summary["abs_charge_error_q95_pct"] = quantile(
        np.abs(np.asarray([row["pico_vs_tek_charge_error_pct"] for row in rows], dtype=float)),
        0.95,
    )
    summary["abs_energy_error_q95_pct"] = quantile(
        np.abs(np.asarray([row["pico_vs_tek_energy_error_pct"] for row in rows], dtype=float)),
        0.95,
    )
    summary["active_window_abs_charge_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [row.get("active_window_charge_error_pct", float("nan")) for row in rows],
                dtype=float,
            )
        ),
        0.95,
    )
    summary["active_window_abs_energy_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [row.get("active_window_energy_error_pct", float("nan")) for row in rows],
                dtype=float,
            )
        ),
        0.95,
    )
    summary["incremental_abs_charge_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [row.get("incremental_charge_error_pct", float("nan")) for row in rows],
                dtype=float,
            )
        ),
        0.95,
    )
    summary["incremental_abs_energy_error_q95_pct"] = quantile(
        np.abs(
            np.asarray(
                [row.get("incremental_energy_error_pct", float("nan")) for row in rows],
                dtype=float,
            )
        ),
        0.95,
    )
    baseline_sources = Counter(str(row.get("idle_baseline_source", "none")) for row in rows)
    summary["idle_baseline_source_counts"] = ";".join(
        f"{name}:{count}" for name, count in sorted(baseline_sources.items())
    )
    summary["idle_baseline_available_fraction"] = float(
        np.mean([str(row.get("idle_baseline_source", "none")) != "none" for row in rows])
    )
    summary["idle_baseline_mismatch_fraction"] = float(
        np.mean([bool(row.get("idle_baseline_mismatch_detected", False)) for row in rows])
    )
    correction_statuses = Counter(
        str(row.get("zero_offset_detection_status", "disabled"))
        for row in rows
    )
    summary["zero_offset_detection_status_counts"] = ";".join(
        f"{name}:{count}" for name, count in sorted(correction_statuses.items())
    )
    confidence_counts = Counter(
        str(row.get("zero_offset_confidence", "none")) for row in rows
    )
    summary["zero_offset_confidence_counts"] = ";".join(
        f"{name}:{count}" for name, count in sorted(confidence_counts.items())
    )
    independence_counts = Counter(
        str(row.get("zero_offset_validation_independence", "not_applicable"))
        for row in rows
    )
    summary["zero_offset_validation_independence_counts"] = ";".join(
        f"{name}:{count}" for name, count in sorted(independence_counts.items())
    )
    summary["zero_offset_correction_applied_fraction"] = float(
        np.mean(
            [bool(row.get("zero_offset_correction_applied", False)) for row in rows]
        )
    )
    summary["zero_offset_reference_independent"] = bool(
        all(bool(row.get("zero_offset_reference_independent", False)) for row in rows)
        if rows and any(
            bool(row.get("zero_offset_correction_applied", False)) for row in rows
        )
        else True
    )
    summary["absolute_comparison_basis"] = str(
        rows[0].get("absolute_comparison_basis", "raw_calibrated_currents")
    )
    summary["abs_alignment_q95_ms"] = quantile(
        np.abs(np.asarray([row["lag_ms"] for row in rows], dtype=float)),
        0.95,
    )
    marker_checks = [
        row.get("sample_count_matches_marker")
        for row in rows
        if row.get("sample_count_matches_marker") is not None
    ]
    summary["sample_count_marker_pass_fraction"] = (
        float(np.mean(marker_checks)) if marker_checks else float("nan")
    )

    tek_means = np.asarray([float(row["tek_mean_current_a"]) for row in rows])
    pico_means = np.asarray([float(row["pico_mean_current_a"]) for row in rows])
    gain, offset, r2 = _regression(tek_means, pico_means)
    summary["segment_mean_regression_gain"] = gain
    summary["segment_mean_regression_offset_a"] = offset
    summary["segment_mean_regression_offset_ma"] = 1000.0 * offset
    summary["segment_mean_regression_r2"] = r2

    for region in ("low_current", "nominal_current"):
        selected = [row for row in rows if row.get("operating_region") == region]
        prefix = region
        summary[f"{prefix}_n_pairs"] = len(selected)
        if selected:
            current_delta_ma = np.asarray(
                [float(row["mean_current_difference_ma"]) for row in selected]
            )
            charge_error = np.asarray(
                [float(row["pico_vs_tek_charge_error_pct"]) for row in selected]
            )
            energy_error = np.asarray(
                [float(row["pico_vs_tek_energy_error_pct"]) for row in selected]
            )
            summary.update(_summary_row(current_delta_ma, f"{prefix}_current_difference_ma"))
            summary[f"{prefix}_abs_charge_error_q95_pct"] = quantile(
                np.abs(charge_error), 0.95
            )
            summary[f"{prefix}_abs_energy_error_q95_pct"] = quantile(
                np.abs(energy_error), 0.95
            )
        else:
            summary[f"{prefix}_current_difference_ma_median"] = float("nan")
            summary[f"{prefix}_abs_charge_error_q95_pct"] = float("nan")
            summary[f"{prefix}_abs_energy_error_q95_pct"] = float("nan")
    return summary


def _frequency_resolution(frequencies: np.ndarray) -> float:
    frequencies = np.asarray(frequencies, dtype=np.float64)
    if frequencies.size < 2:
        return float("inf")
    differences = np.diff(frequencies)
    differences = differences[np.isfinite(differences) & (differences > 0)]
    return float(np.median(differences)) if differences.size else float("inf")


def _interpolate_spectral_array(
    source_frequencies: np.ndarray,
    values: np.ndarray,
    target_frequencies: np.ndarray,
) -> np.ndarray:
    """Interpolate a real-valued spectral vector onto a shared frequency grid.

    The paired-scope runs use the same nominal sample rate, but a shorter detected
    idle or active window can change Welch's ``nperseg`` and therefore the number
    of frequency bins.  Aggregation requires a shared grid.  We choose the
    coarsest native grid and interpolate finer spectra down to it, avoiding the
    creation of frequency resolution that is not present in every run.
    """

    source_frequencies = np.asarray(source_frequencies, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    target_frequencies = np.asarray(target_frequencies, dtype=np.float64)
    if source_frequencies.ndim != 1 or values.ndim != 1:
        raise ValueError("Spectral frequency and value arrays must be one-dimensional")
    if source_frequencies.size != values.size:
        raise ValueError(
            f"Spectral array length mismatch: frequencies={source_frequencies.size}, "
            f"values={values.size}"
        )
    if target_frequencies.size == 0:
        return np.asarray([], dtype=np.float64)
    if (
        source_frequencies.size == target_frequencies.size
        and np.allclose(source_frequencies, target_frequencies, rtol=0.0, atol=1e-12)
    ):
        return values.astype(np.float64, copy=True)

    finite = np.isfinite(source_frequencies) & np.isfinite(values)
    if np.count_nonzero(finite) == 0:
        return np.full(target_frequencies.shape, np.nan, dtype=np.float64)
    source_finite = source_frequencies[finite]
    values_finite = values[finite]
    order = np.argsort(source_finite)
    source_finite = source_finite[order]
    values_finite = values_finite[order]
    unique_frequency, unique_indices = np.unique(source_finite, return_index=True)
    values_finite = values_finite[unique_indices]
    if unique_frequency.size == 1:
        result = np.full(target_frequencies.shape, np.nan, dtype=np.float64)
        match = np.isclose(target_frequencies, unique_frequency[0], rtol=0.0, atol=1e-12)
        result[match] = values_finite[0]
        return result

    # Keep bins outside the finite support undefined instead of extrapolating a
    # PSD/coherence/ratio beyond the data that actually exist.
    return np.interp(
        target_frequencies,
        unique_frequency,
        values_finite,
        left=np.nan,
        right=np.nan,
    )


def _aggregate_psd(
    rate_output: Path,
    rate: int,
    spectral_entries: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]],
    band_rows: list[dict[str, Any]],
    cfg: ScopeComparisonConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not spectral_entries:
        return {}, []

    # Select the coarsest native Welch grid that is common to all runs.  This is
    # a deterministic and conservative fallback even when legacy cached results
    # were produced with different ``nperseg`` values.
    grid_candidates: list[tuple[float, int, int, np.ndarray]] = []
    for run, arrays, _ in spectral_entries:
        frequencies = np.asarray(arrays["frequencies_hz"], dtype=np.float64)
        if frequencies.ndim != 1 or frequencies.size < 2:
            raise ValueError(f"Run {run}: invalid PSD frequency grid")
        grid_candidates.append(
            (_frequency_resolution(frequencies), -frequencies.size, run, frequencies)
        )
    grid_candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    _, _, grid_source_run, grid_source = grid_candidates[0]
    common_nyquist = min(
        float(np.asarray(entry[1]["frequencies_hz"], dtype=np.float64)[-1])
        for entry in spectral_entries
    )
    frequencies = np.asarray(
        grid_source[grid_source <= common_nyquist + 1e-12], dtype=np.float64
    )
    if frequencies.size < 2:
        raise ValueError("No common PSD frequency range across paired runs")

    common_keys = set(spectral_entries[0][1])
    for _, arrays, _ in spectral_entries[1:]:
        common_keys.intersection_update(arrays)
    array_keys = [
        key for key in spectral_entries[0][1].keys()
        if key != "frequencies_hz" and key in common_keys
    ]

    harmonisation_rows: list[dict[str, Any]] = []
    harmonised_entries: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]] = []
    any_harmonised = False
    for run, arrays, metrics in spectral_entries:
        source_frequencies = np.asarray(arrays["frequencies_hz"], dtype=np.float64)
        same_grid = (
            source_frequencies.size == frequencies.size
            and np.allclose(source_frequencies, frequencies, rtol=0.0, atol=1e-12)
        )
        any_harmonised = any_harmonised or not same_grid
        harmonised_arrays: dict[str, np.ndarray] = {"frequencies_hz": frequencies}
        for key in array_keys:
            harmonised_arrays[key] = _interpolate_spectral_array(
                source_frequencies,
                np.asarray(arrays[key]),
                frequencies,
            )
        harmonised_entries.append((run, harmonised_arrays, metrics))
        harmonisation_rows.append(
            {
                "rate_sps": rate,
                "run": run,
                "original_bins": int(source_frequencies.size),
                "original_resolution_hz": _frequency_resolution(source_frequencies),
                "original_nyquist_hz": float(source_frequencies[-1]),
                "canonical_bins": int(frequencies.size),
                "canonical_resolution_hz": _frequency_resolution(frequencies),
                "canonical_nyquist_hz": float(frequencies[-1]),
                "canonical_grid_source_run": int(grid_source_run),
                "interpolated": bool(not same_grid),
            }
        )
    write_csv(rate_output / "psd" / "psd_grid_harmonization.csv", harmonisation_rows)
    if any_harmonised:
        LOGGER.warning(
            "PSD grids at %s differed across runs and were conservatively "
            "harmonised to %d bins (%.6g Hz resolution, source run %d)",
            human_rate(rate),
            frequencies.size,
            _frequency_resolution(frequencies),
            grid_source_run,
        )

    aggregate: dict[str, np.ndarray] = {"frequencies_hz": frequencies}
    import warnings
    for key in array_keys:
        stack = np.vstack([entry[1][key] for entry in harmonised_entries])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            aggregate[f"{key}_median"] = np.nanmedian(stack, axis=0)
            aggregate[f"{key}_q05"] = np.nanquantile(stack, 0.05, axis=0)
            aggregate[f"{key}_q95"] = np.nanquantile(stack, 0.95, axis=0)

    # Recompute cumulative curves from the aggregate median analysis PSD.
    # The analysis PSD is active-minus-idle when an idle window exists and
    # otherwise explicitly active-only; the basis is stored in the metrics.
    for prefix in ("tek", "pico"):
        for basis_name in ("analysis", "excess"):
            density_key = f"{prefix}_{basis_name}_psd_w2_per_hz_median"
            cumulative_key = f"{prefix}_{basis_name}_cumulative_median"
            if density_key in aggregate and np.any(np.isfinite(aggregate[density_key])):
                aggregate[cumulative_key] = _cumulative_density(
                    frequencies,
                    np.nan_to_num(aggregate[density_key], nan=0.0),
                )
    np.savez_compressed(rate_output / "psd" / "psd_summary.npz", **aggregate)

    metric_rows = [entry[2] | {"run": entry[0], "rate_sps": rate} for entry in spectral_entries]
    write_csv(rate_output / "psd" / "spectral_metrics_per_pair.csv", metric_rows)
    summary: dict[str, Any] = {
        "rate_sps": rate,
        "n_pairs": len(metric_rows),
        "psd_grid_harmonized": bool(any_harmonised),
        "psd_frequency_grid_bins": int(frequencies.size),
        "psd_frequency_resolution_hz": _frequency_resolution(frequencies),
        "psd_nyquist_hz": float(frequencies[-1]),
        "psd_grid_source_run": int(grid_source_run),
    }
    keys = sorted(
        key
        for key in metric_rows[0]
        if key not in {"run", "rate_sps"}
        and isinstance(metric_rows[0][key], (int, float, np.integer, np.floating, bool))
    )
    for key in keys:
        values = np.asarray([float(row.get(key, float("nan"))) for row in metric_rows], dtype=float)
        summary.update(_summary_row(values, key))

    band_fieldnames = [
        "band_low_hz",
        "band_high_hz",
        "band",
        "spectral_basis",
        "tek_analysis_variance_fraction",
        "pico_analysis_variance_fraction",
        "analysis_variance_fraction_difference_percentage_points",
        "tek_excess_variance_fraction",
        "pico_excess_variance_fraction",
        "variance_fraction_difference_percentage_points",
        "coherence_median",
        "coherence_q05",
        "abs_psd_ratio_db_median",
        "psd_ratio_db_median",
        "run",
        "rate_sps",
    ]
    write_csv(
        rate_output / "psd" / "spectral_band_per_pair.csv",
        band_rows,
        fieldnames=band_fieldnames,
    )
    band_summary: list[dict[str, Any]] = []
    for band in sorted(
        {row["band"] for row in band_rows},
        key=lambda value: next(
            r["band_low_hz"] for r in band_rows if r["band"] == value
        ),
    ):
        selected = [row for row in band_rows if row["band"] == band]
        base = {
            "rate_sps": rate,
            "band": band,
            "band_low_hz": selected[0]["band_low_hz"],
            "band_high_hz": selected[0]["band_high_hz"],
            "n_pairs": len(selected),
            "spectral_basis": Counter(
                str(row.get("spectral_basis", "unknown")) for row in selected
            ).most_common(1)[0][0],
        }
        for key in (
            "tek_analysis_variance_fraction",
            "pico_analysis_variance_fraction",
            "analysis_variance_fraction_difference_percentage_points",
            "tek_excess_variance_fraction",
            "pico_excess_variance_fraction",
            "variance_fraction_difference_percentage_points",
            "coherence_median",
            "coherence_q05",
            "abs_psd_ratio_db_median",
            "psd_ratio_db_median",
        ):
            values = np.asarray([float(row[key]) for row in selected], dtype=float)
            base.update(_summary_row(values, key))
        band_summary.append(base)
    band_summary_fieldnames = [
        "rate_sps",
        "band",
        "band_low_hz",
        "band_high_hz",
        "n_pairs",
        "spectral_basis",
    ]
    for key in (
        "tek_analysis_variance_fraction",
        "pico_analysis_variance_fraction",
        "analysis_variance_fraction_difference_percentage_points",
        "tek_excess_variance_fraction",
        "pico_excess_variance_fraction",
        "variance_fraction_difference_percentage_points",
        "coherence_median",
        "coherence_q05",
        "abs_psd_ratio_db_median",
        "psd_ratio_db_median",
    ):
        band_summary_fieldnames.extend(
            [
                f"{key}_mean",
                f"{key}_median",
                f"{key}_std",
                f"{key}_q05",
                f"{key}_q95",
                f"{key}_min",
                f"{key}_max",
            ]
        )
    write_csv(
        rate_output / "psd" / "spectral_band_summary.csv",
        band_summary,
        fieldnames=band_summary_fieldnames,
    )
    write_csv(rate_output / "psd" / "spectral_metrics_summary.csv", [summary])
    return summary, band_summary


def _aggregate_native_psd(
    rate_output: Path,
    rate: int,
    native_entries: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate Tektronix-native PSDs independently of the PicoScope grid.

    Two aggregates are written:

    - ``tek_native_psd_summary.npz`` contains all valid native Tek records and is
      used for per-rate diagnostics, including active-only short records;
    - ``tek_native_workload_psd_summary.npz`` contains only records with a real
      pre-benchmark idle PSD and is the only aggregate eligible to become the
      primary workload-related Tektronix reference.
    """

    if not native_entries:
        return {}
    candidates: list[tuple[float, int, int, np.ndarray]] = []
    for run, arrays, _ in native_entries:
        frequencies = np.asarray(
            arrays["tek_native_frequencies_hz"], dtype=np.float64
        )
        if frequencies.ndim != 1 or frequencies.size < 2:
            continue
        candidates.append(
            (_frequency_resolution(frequencies), -frequencies.size, run, frequencies)
        )
    if not candidates:
        return {}
    candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    _, _, source_run, source_grid = candidates[0]
    common_nyquist = min(
        float(np.asarray(arrays["tek_native_frequencies_hz"])[-1])
        for _, arrays, _ in native_entries
    )
    frequencies = np.asarray(
        source_grid[source_grid <= common_nyquist + 1e-12], dtype=np.float64
    )
    array_keys = sorted(
        set.intersection(
            *(
                set(arrays.keys()) - {"tek_native_frequencies_hz"}
                for _, arrays, _ in native_entries
            )
        )
    )
    harmonised: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]] = []
    audit_rows: list[dict[str, Any]] = []
    for run, arrays, metrics in native_entries:
        source_f = np.asarray(arrays["tek_native_frequencies_hz"], dtype=np.float64)
        same = source_f.size == frequencies.size and np.allclose(
            source_f, frequencies, rtol=0.0, atol=1e-12
        )
        converted = {"tek_native_frequencies_hz": frequencies}
        for key in array_keys:
            converted[key] = _interpolate_spectral_array(
                source_f, np.asarray(arrays[key]), frequencies
            )
        harmonised.append((run, converted, metrics))
        audit_rows.append(
            {
                "rate_sps": rate,
                "run": run,
                "original_bins": int(source_f.size),
                "canonical_bins": int(frequencies.size),
                "original_resolution_hz": _frequency_resolution(source_f),
                "canonical_resolution_hz": _frequency_resolution(frequencies),
                "canonical_grid_source_run": int(source_run),
                "interpolated": bool(not same),
                "workload_related": bool(
                    metrics.get("tek_native_workload_related_psd_available", False)
                ),
            }
        )
    write_csv(rate_output / "psd" / "tek_native_grid_harmonization.csv", audit_rows)

    def aggregate_group(
        entries: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]]
    ) -> dict[str, np.ndarray]:
        aggregate: dict[str, np.ndarray] = {
            "tek_native_frequencies_hz": frequencies
        }
        import warnings

        for key in array_keys:
            stack = np.vstack([entry[1][key] for entry in entries])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                aggregate[f"{key}_median"] = np.nanmedian(stack, axis=0)
                aggregate[f"{key}_q05"] = np.nanquantile(stack, 0.05, axis=0)
                aggregate[f"{key}_q95"] = np.nanquantile(stack, 0.95, axis=0)

        density_key = "tek_native_analysis_psd_w2_per_hz_median"
        if density_key in aggregate:
            aggregate["tek_native_analysis_cumulative_median"] = _cumulative_density(
                frequencies, np.nan_to_num(aggregate[density_key], nan=0.0)
            )
        excess_key = "tek_native_excess_psd_w2_per_hz_median"
        if excess_key in aggregate and np.any(np.isfinite(aggregate[excess_key])):
            aggregate["tek_native_excess_cumulative_median"] = _cumulative_density(
                frequencies, np.nan_to_num(aggregate[excess_key], nan=0.0)
            )
        return aggregate

    aggregate = aggregate_group(harmonised)
    np.savez_compressed(
        rate_output / "psd" / "tek_native_psd_summary.npz", **aggregate
    )

    workload_harmonised = [
        entry
        for entry in harmonised
        if bool(entry[2].get("tek_native_workload_related_psd_available", False))
    ]
    workload_path = rate_output / "psd" / "tek_native_workload_psd_summary.npz"
    if workload_harmonised:
        workload_aggregate = aggregate_group(workload_harmonised)
        np.savez_compressed(workload_path, **workload_aggregate)
    elif workload_path.exists():
        workload_path.unlink()

    metric_rows = [
        metrics | {"run": run, "rate_sps": rate}
        for run, _, metrics in native_entries
    ]
    write_csv(rate_output / "psd" / "tek_native_metrics_per_pair.csv", metric_rows)
    summary: dict[str, Any] = {
        "rate_sps": rate,
        "n_pairs": len(metric_rows),
        "tek_native_grid_source_run": int(source_run),
        "tek_native_grid_bins": int(frequencies.size),
        "tek_native_grid_resolution_hz": _frequency_resolution(frequencies),
        "tek_native_grid_nyquist_hz": float(frequencies[-1]),
        "tek_native_workload_related_n_pairs": len(workload_harmonised),
        "tek_native_workload_psd_path": (
            str(workload_path) if workload_harmonised else ""
        ),
    }
    numeric_keys = sorted(
        key
        for key in metric_rows[0]
        if key not in {"run", "rate_sps"}
        and isinstance(
            metric_rows[0][key],
            (int, float, np.integer, np.floating, bool),
        )
    )
    for key in numeric_keys:
        values = np.asarray(
            [float(row.get(key, float("nan"))) for row in metric_rows], dtype=float
        )
        summary.update(_summary_row(values, key))

    workload_metric_rows = [
        row
        for row in metric_rows
        if bool(row.get("tek_native_workload_related_psd_available", False))
    ]
    if workload_metric_rows:
        for key in numeric_keys:
            values = np.asarray(
                [float(row.get(key, float("nan"))) for row in workload_metric_rows],
                dtype=float,
            )
            for stat_key, value in _summary_row(values, key).items():
                summary[f"workload_{stat_key}"] = value

    bases = [str(row.get("tek_native_psd_basis", "unknown")) for row in metric_rows]
    summary["tek_native_psd_basis_mode"] = Counter(bases).most_common(1)[0][0]
    summary["tek_native_workload_related_pair_fraction"] = float(
        len(workload_metric_rows) / len(metric_rows)
    )
    write_csv(rate_output / "psd" / "tek_native_metrics_summary.csv", [summary])
    return summary


def _robust_scale(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 1.0
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    if mad > 0:
        return 1.4826 * mad
    spread = float(np.ptp(finite))
    return spread if spread > 0 else max(abs(median), 1.0)


def _select_representative_run(
    rows: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    currents = np.asarray([float(row["tek_mean_current_a"]) for row in rows])
    energies = np.asarray([float(row["tek_estimated_energy_j"]) for row in rows])
    current_median = float(np.median(currents))
    energy_median = float(np.median(energies))
    current_scale = _robust_scale(currents)
    energy_scale = _robust_scale(energies)
    audit: list[dict[str, Any]] = []
    for row in rows:
        current = float(row["tek_mean_current_a"])
        energy = float(row["tek_estimated_energy_j"])
        score = (
            abs(current - current_median) / current_scale
            + 0.5 * abs(energy - energy_median) / energy_scale
        )
        # A low-current segment remains scientifically important but should not
        # silently become the visual representative of the normal operating
        # point when nominal-current segments are available.
        if row.get("operating_region") == "low_current" and any(
            candidate.get("operating_region") == "nominal_current" for candidate in rows
        ):
            score += 10.0
        audit.append(
            {
                "run": int(row["run"]),
                "tek_mean_current_a": current,
                "tek_estimated_energy_j": energy,
                "operating_region": row.get("operating_region", "unknown"),
                "distance_score": float(score),
                "current_median_a": current_median,
                "energy_median_j": energy_median,
            }
        )
    audit.sort(key=lambda item: (float(item["distance_score"]), int(item["run"])))
    return int(audit[0]["run"]), audit


def _write_operating_point_diagnostics(
    output_root: Path,
    rows: list[dict[str, Any]],
    cfg: ScopeComparisonConfig,
) -> dict[str, Any]:
    diagnostics = output_root / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    compact_rows: list[dict[str, Any]] = []
    for row in rows:
        compact_rows.append(
            {
                "rate_sps": int(row["rate_sps"]),
                "tek_rate_sps": float(row.get("tek_rate_sps", row["rate_sps"])),
                "pico_rate_sps": float(row.get("pico_rate_sps", row["rate_sps"])),
                "run": int(row["run"]),
                "duration_s": float(row.get("common_nominal_duration_s", float("nan"))),
                "operating_region": row.get("operating_region", "unknown"),
                "raw_tek_mean_current_a": float(
                    row.get("raw_tek_mean_current_a", float("nan"))
                ),
                "raw_pico_mean_current_a": float(
                    row.get("raw_pico_mean_current_a", float("nan"))
                ),
                "raw_mean_current_difference_ma": float(
                    row.get("raw_mean_current_difference_ma", float("nan"))
                ),
                "raw_pico_vs_tek_charge_error_pct": float(
                    row.get("raw_pico_vs_tek_charge_error_pct", float("nan"))
                ),
                "raw_pico_vs_tek_energy_error_pct": float(
                    row.get("raw_pico_vs_tek_energy_error_pct", float("nan"))
                ),
                "zero_offset_detection_status": str(
                    row.get("zero_offset_detection_status", "disabled")
                ),
                "zero_offset_correction_applied": bool(
                    row.get("zero_offset_correction_applied", False)
                ),
                "zero_offset_applied_ma": float(
                    row.get("zero_offset_applied_ma", 0.0)
                ),
                "absolute_comparison_basis": str(
                    row.get("absolute_comparison_basis", "raw_calibrated_currents")
                ),
                "tek_mean_current_a": float(row["tek_mean_current_a"]),
                "pico_mean_current_a": float(row["pico_mean_current_a"]),
                "mean_current_difference_ma": float(row["mean_current_difference_ma"]),
                "pico_vs_tek_charge_error_pct": float(row["pico_vs_tek_charge_error_pct"]),
                "pico_vs_tek_energy_error_pct": float(row["pico_vs_tek_energy_error_pct"]),
                "active_window_energy_error_pct": float(
                    row.get("active_window_energy_error_pct", float("nan"))
                ),
                "incremental_energy_error_pct": float(
                    row.get("incremental_energy_error_pct", float("nan"))
                ),
                "idle_baseline_source": str(
                    row.get("idle_baseline_source", "none")
                ),
                "idle_baseline_current_difference_ma": float(
                    row.get("idle_baseline_current_difference_ma", float("nan"))
                ),
                "same_run_idle_current_difference_ma": float(
                    row.get("same_run_idle_current_difference_ma", float("nan"))
                ),
                "external_idle_current_difference_ma_median": float(
                    row.get(
                        "external_idle_current_difference_ma_median",
                        float("nan"),
                    )
                ),
                "same_run_minus_external_idle_tek_current_ma": float(
                    row.get(
                        "same_run_minus_external_idle_tek_current_ma",
                        float("nan"),
                    )
                ),
                "same_run_minus_external_idle_pico_current_ma": float(
                    row.get(
                        "same_run_minus_external_idle_pico_current_ma",
                        float("nan"),
                    )
                ),
                "idle_baseline_mismatch_detected": bool(
                    row.get("idle_baseline_mismatch_detected", False)
                ),
                "external_idle_pair_count": int(
                    row.get("external_idle_pair_count", 0)
                ),
                "selected_correlation_window_ms": float(
                    row.get("selected_correlation_window_ms", float("nan"))
                ),
                "selected_correlation": float(
                    row.get("selected_correlation", float("nan"))
                ),
            }
        )
    write_csv(diagnostics / "operating_point_per_pair.csv", compact_rows)

    regression_rows: list[dict[str, Any]] = []
    region_summary: list[dict[str, Any]] = []
    for region in ("all", "nominal_current", "low_current"):
        selected = (
            compact_rows
            if region == "all"
            else [row for row in compact_rows if row["operating_region"] == region]
        )
        if not selected:
            continue
        tek = np.asarray([float(row["tek_mean_current_a"]) for row in selected])
        pico = np.asarray([float(row["pico_mean_current_a"]) for row in selected])
        gain, offset, r2 = _regression(tek, pico)
        regression_rows.append(
            {
                "region": region,
                "n_pairs": len(selected),
                "gain": gain,
                "offset_a": offset,
                "offset_ma": 1000.0 * offset,
                "r2": r2,
                "interpretation": (
                    "diagnostic_gain_fit_not_applied; selected currents may "
                    "include an independently audited additive zero correction"
                ),
            }
        )
        delta_ma = np.asarray(
            [float(row["mean_current_difference_ma"]) for row in selected]
        )
        charge = np.asarray(
            [float(row["pico_vs_tek_charge_error_pct"]) for row in selected]
        )
        energy = np.asarray(
            [float(row["pico_vs_tek_energy_error_pct"]) for row in selected]
        )
        region_summary.append(
            {
                "region": region,
                "n_pairs": len(selected),
                "tek_current_min_a": float(np.min(tek)),
                "tek_current_median_a": float(np.median(tek)),
                "tek_current_max_a": float(np.max(tek)),
                "current_difference_median_ma": float(np.median(delta_ma)),
                "current_difference_q05_ma": quantile(delta_ma, 0.05),
                "current_difference_q95_ma": quantile(delta_ma, 0.95),
                "abs_charge_error_q95_pct": quantile(np.abs(charge), 0.95),
                "abs_energy_error_q95_pct": quantile(np.abs(energy), 0.95),
                "low_current_threshold_a": cfg.validation.low_current_threshold_a,
            }
        )
    write_csv(diagnostics / "segment_mean_regression.csv", regression_rows)
    write_csv(diagnostics / "operating_region_summary.csv", region_summary)
    summary = {
        "low_current_threshold_a": cfg.validation.low_current_threshold_a,
        "n_pairs": len(compact_rows),
        "n_low_current_pairs": sum(
            row["operating_region"] == "low_current" for row in compact_rows
        ),
        "regressions": regression_rows,
        "regions": region_summary,
        "note": (
            "Affine gain/offset fits are diagnostic only and are never applied. "
            "A separate additive Tektronix zero correction may be applied when "
            "several exact-rate paired idle campaigns pass the adaptive safety "
            "gates; raw values remain archived."
        ),
    }
    write_json(diagnostics / "operating_point_diagnostics.json", summary)
    return summary


def _select_primary_tek_reference(
    output_root: Path,
    cross_rows: list[dict[str, Any]],
    cfg: ScopeComparisonConfig,
) -> dict[str, Any]:
    root = output_root / "tek_reference"
    root.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    for row in cross_rows:
        rate = int(float(row["rate_sps"]))
        tek_rate = float(row.get("tek_rate_sps", rate))
        native_path = (
            output_root
            / f"{rate}Sps"
            / "psd"
            / "tek_native_workload_psd_summary.npz"
        )
        workload_fraction = float(
            row.get(
                "native_tek_native_workload_related_pair_fraction",
                float("nan"),
            )
        )
        workload_n_pairs = int(
            float(row.get("native_tek_native_workload_related_n_pairs", 0))
        )
        active_duration = float(
            row.get(
                "native_workload_tek_native_active_duration_s_q05",
                float("nan"),
            )
        )
        idle_duration = float(
            row.get(
                "native_workload_tek_native_idle_duration_s_q05",
                float("nan"),
            )
        )
        active_segments = float(
            row.get(
                "native_workload_tek_native_active_welch_segments_q05",
                float("nan"),
            )
        )
        idle_segments = float(
            row.get(
                "native_workload_tek_native_idle_welch_segments_q05",
                float("nan"),
            )
        )
        reasons: list[str] = []
        if workload_n_pairs < cfg.spectral.primary_reference_min_pairs:
            reasons.append("insufficient_workload_related_pairs")
        if not native_path.is_file():
            reasons.append("missing_native_psd_aggregate")
        if not np.isfinite(workload_fraction) or workload_fraction < 0.8:
            reasons.append("insufficient_idle_subtracted_pairs")
        if not np.isfinite(active_duration) or active_duration < cfg.spectral.primary_reference_min_active_duration_s:
            reasons.append("active_duration_too_short")
        if not np.isfinite(idle_duration) or idle_duration < cfg.spectral.primary_reference_min_idle_duration_s:
            reasons.append("idle_duration_too_short")
        if not np.isfinite(active_segments) or active_segments < cfg.spectral.minimum_welch_segments:
            reasons.append("insufficient_active_welch_segments")
        if not np.isfinite(idle_segments) or idle_segments < cfg.spectral.minimum_idle_welch_segments:
            reasons.append("insufficient_idle_welch_segments")
        candidates.append(
            {
                "rate_sps": rate,
                "tek_rate_sps": tek_rate,
                "pico_rate_sps": float(row.get("pico_rate_sps", rate)),
                "n_pairs": workload_n_pairs,
                "all_valid_pairs": int(row.get("n_pairs", 0)),
                "workload_related_pair_fraction": workload_fraction,
                "active_duration_s_median": active_duration,
                "idle_duration_s_median": idle_duration,
                "active_welch_segments_median": active_segments,
                "idle_welch_segments_median": idle_segments,
                "eligible": not reasons,
                "reasons": ";".join(reasons),
                "native_psd_path": str(native_path),
            }
        )
    write_csv(root / "candidate_rates.csv", candidates)
    eligible = [row for row in candidates if row["eligible"]]
    if not eligible:
        decision = {
            "status": "no_eligible_tek_reference",
            "selection_policy": "highest Tek rate with idle and sufficient Welch support",
            "candidates": candidates,
        }
        write_json(root / "selection.json", decision)
        return decision
    selected = max(eligible, key=lambda row: float(row["tek_rate_sps"]))
    selected_rate = int(selected["rate_sps"])
    selected_cross = next(
        row
        for row in cross_rows
        if int(float(row["rate_sps"])) == selected_rate
    )
    source = Path(str(selected["native_psd_path"]))
    target = root / "tek_primary_psd_summary.npz"
    shutil.copy2(source, target)
    data = np.load(target)
    frequencies = np.asarray(data["tek_native_frequencies_hz"], dtype=np.float64)
    density = np.asarray(
        data["tek_native_analysis_psd_w2_per_hz_median"], dtype=np.float64
    )
    cumulative = _cumulative_density(frequencies, np.nan_to_num(density, nan=0.0))
    aggregate_variance_above_77 = 1.0 - _density_fraction_below(
        frequencies, density, 77_000.0
    )
    aggregate_variance_above_pico = 1.0 - _density_fraction_below(
        frequencies, density, float(selected["pico_rate_sps"]) / 2.0
    )
    aggregate_frequency_metrics: dict[str, float] = {}
    for fraction in cfg.spectral.cumulative_percentiles:
        label = int(round(100 * fraction))
        aggregate_frequency_metrics[f"aggregate_psd_f{label}_hz"] = _f_at_cumulative(
            frequencies, cumulative, fraction
        )

    def cross_stat(metric: str, statistic: str) -> float:
        return _first_finite(
            selected_cross,
            f"native_workload_tek_native_analysis_{metric}_{statistic}",
            f"native_tek_native_analysis_{metric}_{statistic}",
            f"spectral_tek_native_{metric}_{statistic}",
        )

    per_run_f95 = cross_stat("f95_hz", "median")
    per_run_f99 = cross_stat("f99_hz", "median")
    per_run_above_77 = cross_stat("variance_above_77khz", "median")
    per_run_above_pico = cross_stat(
        "variance_above_pico_nyquist", "median"
    )
    metrics: dict[str, Any] = {
        "status": "selected",
        "selection_policy": (
            "highest Tek rate with >= configured pairs, sufficient active data, "
            "a valid same-run or exact-rate external idle reference, and sufficient Welch averages"
        ),
        "selected_rate_sps": selected_rate,
        "selected_tek_rate_sps": float(selected["tek_rate_sps"]),
        "selected_pico_rate_sps": float(selected["pico_rate_sps"]),
        "selected_n_pairs": int(selected["n_pairs"]),
        "psd_basis": str(
            selected_cross.get(
                "native_tek_native_psd_basis_mode",
                "active_minus_valid_idle_reference",
            )
        ),
        "frequency_resolution_hz": _frequency_resolution(frequencies),
        "nyquist_hz": float(frequencies[-1]),
        # Paper statistics use the physical run as the uncertainty unit.  The
        # plotted PSD remains the pointwise median aggregate, while f95/f99 and
        # variance fractions are reported as medians and 5th-95th percentiles
        # across per-run metrics.
        "metric_basis": "median_of_per_run_metrics",
        "f95_hz": per_run_f95,
        "f95_hz_q05": cross_stat("f95_hz", "q05"),
        "f95_hz_q95": cross_stat("f95_hz", "q95"),
        "f99_hz": per_run_f99,
        "f99_hz_q05": cross_stat("f99_hz", "q05"),
        "f99_hz_q95": cross_stat("f99_hz", "q95"),
        "variance_above_77khz": per_run_above_77,
        "variance_above_77khz_q05": cross_stat(
            "variance_above_77khz", "q05"
        ),
        "variance_above_77khz_q95": cross_stat(
            "variance_above_77khz", "q95"
        ),
        "variance_below_77khz": 1.0 - per_run_above_77,
        "variance_above_pico_nyquist": per_run_above_pico,
        "variance_above_pico_nyquist_q05": cross_stat(
            "variance_above_pico_nyquist", "q05"
        ),
        "variance_above_pico_nyquist_q95": cross_stat(
            "variance_above_pico_nyquist", "q95"
        ),
        "variance_below_pico_nyquist": 1.0 - per_run_above_pico,
        "aggregate_psd_variance_above_77khz": aggregate_variance_above_77,
        "aggregate_psd_variance_above_pico_nyquist": aggregate_variance_above_pico,
        **aggregate_frequency_metrics,
    }
    write_json(root / "selection.json", metrics | {"candidates": candidates})
    write_csv(root / "tek_primary_metrics.csv", [metrics])
    return metrics


def _select_pico_usability_rate(
    output_root: Path,
    cross_rows: list[dict[str, Any]],
    cfg: ScopeComparisonConfig,
) -> dict[str, Any]:
    root = output_root / "pico_usability"
    root.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    for row in cross_rows:
        rate = int(float(row["rate_sps"]))
        path = output_root / f"{rate}Sps" / "psd" / "psd_summary.npz"
        workload_fraction = float(
            row.get("spectral_workload_related_psd_available_mean", float("nan"))
        )
        coherence_segments = float(
            row.get("spectral_coherence_welch_segments_median", float("nan"))
        )
        usable = bool(
            path.is_file()
            and np.isfinite(workload_fraction)
            and workload_fraction >= 0.8
            and np.isfinite(coherence_segments)
            and coherence_segments >= cfg.spectral.minimum_welch_segments
        )
        tek_rate = float(row.get("tek_rate_sps", rate))
        candidates.append(
            {
                "rate_sps": rate,
                "tek_rate_sps": tek_rate,
                "pico_rate_sps": float(row.get("pico_rate_sps", rate)),
                "common_rate_sps": float(
                    row.get("common_comparison_rate_sps", rate)
                ),
                "usable": usable,
                "distance_to_preferred_rate_sps": abs(
                    tek_rate - cfg.spectral.paired_validation_preferred_rate_sps
                ),
                "psd_path": str(path),
            }
        )
    usable = [row for row in candidates if row["usable"]]
    if not usable:
        decision = {"status": "no_usable_paired_psd", "candidates": candidates}
        write_json(root / "selection.json", decision)
        return decision
    selected = min(
        usable,
        key=lambda row: (
            float(row["distance_to_preferred_rate_sps"]),
            -float(row["common_rate_sps"]),
        ),
    )
    decision = {
        "status": "selected",
        "selected_rate_sps": int(selected["rate_sps"]),
        "selected_tek_rate_sps": float(selected["tek_rate_sps"]),
        "selected_pico_rate_sps": float(selected["pico_rate_sps"]),
        "selected_common_rate_sps": float(selected["common_rate_sps"]),
        "selection_policy": (
            "paired rate nearest configured 5-MS/s target with pre-benchmark "
            "idle and sufficient Welch segments"
        ),
        "psd_path": selected["psd_path"],
        "candidates": candidates,
    }
    write_json(root / "selection.json", decision)
    return decision



def _read_single_csv_row(path: Path) -> dict[str, str]:
    import csv

    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _first_finite(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            value = float(row.get(key, float("nan")))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            return value
    return float("nan")


def _derive_pico_usability_from_tek_reference(
    output_root: Path,
    tek_reference: dict[str, Any],
    paired_selection: dict[str, Any],
    cfg: ScopeComparisonConfig,
) -> dict[str, Any]:
    """Derive PicoScope usefulness from the Tektronix-primary reference.

    The Tektronix-native PSD is the scientific reference.  A separate, long
    paired acquisition (preferably 5 MS/s versus 5 MS/s) is used to quantify
    which part of that reference is reproduced by the PicoScope/INA225 setup.
    No affine gain/offset correction is applied.
    """

    root = output_root / "pico_usability"
    root.mkdir(parents=True, exist_ok=True)
    if tek_reference.get("status") != "selected":
        result = {
            "status": "missing_tek_reference",
            "note": "No eligible idle-subtracted Tektronix reference was available.",
        }
        write_json(root / "pico_usability.json", result)
        return result
    if paired_selection.get("status") != "selected":
        result = {
            "status": "missing_paired_validation_rate",
            "tek_reference": tek_reference,
        }
        write_json(root / "pico_usability.json", result)
        return result

    rate = int(paired_selection["selected_rate_sps"])
    rate_root = output_root / f"{rate}Sps"
    psd_path = rate_root / "psd" / "psd_summary.npz"
    metrics_row = _read_single_csv_row(
        rate_root / "psd" / "spectral_metrics_summary.csv"
    )
    band_rows = _read_csv_rows(rate_root / "psd" / "spectral_band_summary.csv")
    if not psd_path.is_file():
        result = {
            "status": "missing_paired_psd_aggregate",
            "selected_rate_sps": rate,
        }
        write_json(root / "pico_usability.json", result)
        return result

    shutil.copy2(psd_path, root / "paired_psd_summary.npz")
    data = np.load(psd_path)
    frequencies = np.asarray(data["frequencies_hz"], dtype=np.float64)
    tek_density = np.asarray(
        data["tek_analysis_psd_w2_per_hz_median"], dtype=np.float64
    )
    pico_density = np.asarray(
        data["pico_analysis_psd_w2_per_hz_median"], dtype=np.float64
    )
    tek_cumulative = _cumulative_density(
        frequencies, np.nan_to_num(tek_density, nan=0.0)
    )
    pico_cumulative = _cumulative_density(
        frequencies, np.nan_to_num(pico_density, nan=0.0)
    )
    tek_integral = (
        float(trapezoid(tek_density, frequencies)) if frequencies.size > 1 else 0.0
    )
    pico_integral = (
        float(trapezoid(pico_density, frequencies)) if frequencies.size > 1 else 0.0
    )
    integrated_ratio_db = (
        10.0 * math.log10(pico_integral / tek_integral)
        if tek_integral > 0 and pico_integral > 0
        else float("nan")
    )

    band_audit: list[dict[str, Any]] = []
    for row in sorted(
        band_rows,
        key=lambda item: _first_finite(item, "band_low_hz"),
    ):
        low = _first_finite(row, "band_low_hz")
        high = _first_finite(row, "band_high_hz")
        coherence_value = _first_finite(
            row,
            "coherence_median_median",
            "coherence_median_mean",
            "coherence_median",
        )
        abs_ratio = _first_finite(
            row,
            "abs_psd_ratio_db_median_median",
            "abs_psd_ratio_db_median_mean",
            "abs_psd_ratio_db_median",
        )
        pass_band = bool(
            np.isfinite(high)
            and np.isfinite(coherence_value)
            and np.isfinite(abs_ratio)
            and coherence_value >= cfg.spectral.coherence_threshold
            and abs_ratio <= cfg.spectral.psd_ratio_tolerance_db
        )
        band_audit.append(
            {
                "band": row.get("band", ""),
                "band_low_hz": low,
                "band_high_hz": high,
                "coherence_median": coherence_value,
                "abs_psd_ratio_db_median": abs_ratio,
                "passes_configured_agreement": pass_band,
            }
        )

    # A usable bandwidth must be contiguous from DC/the first predefined band.
    # Taking the maximum of individually passing bands could otherwise jump
    # over a failed intermediate range and overstate the validated bandwidth.
    contiguous_validated: list[dict[str, Any]] = []
    expected_low = 0.0
    for row in band_audit:
        low = float(row["band_low_hz"])
        high = float(row["band_high_hz"])
        contiguous = abs(low - expected_low) <= max(1e-9, 1e-9 * max(1.0, high))
        if not contiguous or not bool(row["passes_configured_agreement"]):
            break
        contiguous_validated.append(row)
        expected_low = high
    write_csv(root / "paired_band_agreement.csv", band_audit)

    low_band_rows = [
        row
        for row in band_audit
        if np.isfinite(float(row["band_high_hz"]))
        and float(row["band_high_hz"]) <= 10_000.0
        and np.isfinite(float(row["coherence_median"]))
        and np.isfinite(float(row["abs_psd_ratio_db_median"]))
    ]
    low_band_coherence = (
        float(np.median([float(row["coherence_median"]) for row in low_band_rows]))
        if low_band_rows
        else float("nan")
    )
    low_band_abs_ratio = (
        float(
            np.median(
                [float(row["abs_psd_ratio_db_median"]) for row in low_band_rows]
            )
        )
        if low_band_rows
        else float("nan")
    )
    validated_band_edge = (
        float(contiguous_validated[-1]["band_high_hz"])
        if contiguous_validated
        else float("nan")
    )
    validated_band_coherence_min = (
        min(float(row["coherence_median"]) for row in contiguous_validated)
        if contiguous_validated
        else float("nan")
    )
    validated_band_abs_ratio_max = (
        max(float(row["abs_psd_ratio_db_median"]) for row in contiguous_validated)
        if contiguous_validated
        else float("nan")
    )

    common_nyquist = float(frequencies[-1]) if frequencies.size else float("nan")

    # Report frequency percentiles with the physical run as the uncertainty
    # unit.  The aggregate pointwise-median PSD remains the plotted curve, but
    # its cumulative threshold is not generally equal to the median of the
    # per-run thresholds.
    paired_tek_f95_per_run = _first_finite(
        metrics_row, "tek_analysis_f95_hz_median"
    )
    paired_tek_f99_per_run = _first_finite(
        metrics_row, "tek_analysis_f99_hz_median"
    )
    paired_pico_f95_per_run = _first_finite(
        metrics_row, "pico_analysis_f95_hz_median"
    )
    paired_pico_f99_per_run = _first_finite(
        metrics_row, "pico_analysis_f99_hz_median"
    )

    result: dict[str, Any] = {
        "status": "selected",
        "interpretation": (
            "Tektronix-native idle-subtracted PSD is the primary reference. "
            "The paired PicoScope result quantifies agreement only within the "
            "shared bandwidth; higher-frequency Tektronix content is reported "
            "separately and is not attributed to the PicoScope."
        ),
        "tek_reference_rate_sps": int(tek_reference["selected_rate_sps"]),
        "tek_reference_native_rate_sps": float(
            tek_reference["selected_tek_rate_sps"]
        ),
        "paired_validation_rate_sps": rate,
        "paired_tek_rate_sps": float(paired_selection["selected_tek_rate_sps"]),
        "paired_pico_rate_sps": float(paired_selection["selected_pico_rate_sps"]),
        "paired_common_rate_sps": float(
            paired_selection["selected_common_rate_sps"]
        ),
        "paired_common_nyquist_hz": common_nyquist,
        "tek_reference_f95_hz": float(tek_reference.get("f95_hz", float("nan"))),
        "tek_reference_f99_hz": float(tek_reference.get("f99_hz", float("nan"))),
        "tek_reference_variance_above_77khz": float(
            tek_reference.get("variance_above_77khz", float("nan"))
        ),
        "tek_reference_variance_above_pico_nyquist": float(
            tek_reference.get("variance_above_pico_nyquist", float("nan"))
        ),
        "tek_reference_variance_captured_by_pico_sampling_ceiling": (
            1.0
            - float(
                tek_reference.get("variance_above_pico_nyquist", float("nan"))
            )
        ),
        "paired_tek_analysis_psd_integral_w2": tek_integral,
        "paired_pico_analysis_psd_integral_w2": pico_integral,
        "paired_pico_to_tek_integrated_psd_ratio_db": integrated_ratio_db,
        "paired_coherence_median": _first_finite(
            metrics_row, "coherence_median_median", "coherence_median_mean"
        ),
        "paired_coherence_q05": _first_finite(
            metrics_row, "coherence_q05_median", "coherence_q05_q05"
        ),
        "paired_abs_psd_ratio_db_median": _first_finite(
            metrics_row,
            "abs_analysis_psd_ratio_db_median_median",
            "abs_analysis_psd_ratio_db_median_mean",
        ),
        "paired_bandwise_coherence_0_10khz_median": low_band_coherence,
        "paired_bandwise_abs_psd_ratio_db_0_10khz_median": low_band_abs_ratio,
        "paired_bandwise_0_10khz_note": (
            "Median of the per-band median values for predefined bands whose "
            "upper edge is at or below 10 kHz; unlike the full-band median, "
            "this summarises the shared low-frequency signal band."
        ),
        "coherence_threshold": cfg.spectral.coherence_threshold,
        "psd_ratio_tolerance_db": cfg.spectral.psd_ratio_tolerance_db,
        "validated_contiguous_band_count": len(contiguous_validated),
        "validated_contiguous_band_edge_hz": validated_band_edge,
        "validated_contiguous_band_coherence_min": validated_band_coherence_min,
        "validated_contiguous_band_abs_psd_ratio_db_max": validated_band_abs_ratio_max,
        # Kept as a compatibility alias for the v0.5.6 paper-artifact path.
        "highest_fixed_band_edge_meeting_agreement_hz": validated_band_edge,
        "highest_fixed_band_note": (
            "Highest contiguous predefined frequency-band edge from DC meeting "
            "the configured coherence and PSD-ratio criteria; this is not an "
            "analogue -3 dB bandwidth estimate."
        ),
    }
    for fraction in cfg.spectral.cumulative_percentiles:
        label = int(round(100 * fraction))
        aggregate_tek_f = _f_at_cumulative(frequencies, tek_cumulative, fraction)
        aggregate_pico_f = _f_at_cumulative(frequencies, pico_cumulative, fraction)
        result[f"paired_median_psd_tek_f{label}_hz"] = aggregate_tek_f
        result[f"paired_median_psd_pico_f{label}_hz"] = aggregate_pico_f

    result.update(
        {
            "paired_metric_basis": "median_of_per_run_metrics",
            "paired_tek_f95_hz": paired_tek_f95_per_run,
            "paired_tek_f99_hz": paired_tek_f99_per_run,
            "paired_pico_f95_hz": paired_pico_f95_per_run,
            "paired_pico_f99_hz": paired_pico_f99_per_run,
            "paired_pico_minus_tek_f95_hz": (
                paired_pico_f95_per_run - paired_tek_f95_per_run
            ),
            "paired_pico_minus_tek_f99_hz": (
                paired_pico_f99_per_run - paired_tek_f99_per_run
            ),
        }
    )

    write_json(root / "pico_usability.json", result)
    write_csv(root / "pico_usability.csv", [result])
    return result


def _validation_decision(
    cfg: ScopeComparisonConfig,
    pair_summary: dict[str, Any],
    spectral_summary: dict[str, Any],
) -> dict[str, Any]:
    marker_values = pair_summary.get("sample_count_marker_pass_fraction")
    selected_correlation = float(
        pair_summary.get("selected_correlation_median", float("nan"))
    )
    checks = {
        "minimum_pair_count": {
            "value": int(pair_summary["n_pairs"]),
            "limit": cfg.validation.minimum_pairs,
            "pass": int(pair_summary["n_pairs"]) >= cfg.validation.minimum_pairs,
        },
        "section_marker_sample_count": {
            "value": marker_values,
            "limit": 1.0,
            "pass": bool(np.isnan(marker_values)) or float(marker_values) == 1.0,
            "note": "NaN means no SectionLength marker was present.",
        },
        "raw_charge_integral_q95_absolute_error_pct": {
            "value": float(
                pair_summary.get("raw_abs_charge_error_q95_pct", float("nan"))
            ),
            "limit": cfg.validation.q95_abs_charge_error_pct,
            "pass": bool(
                np.isfinite(
                    float(
                        pair_summary.get(
                            "raw_abs_charge_error_q95_pct", float("nan")
                        )
                    )
                )
                and float(
                    pair_summary.get(
                        "raw_abs_charge_error_q95_pct", float("nan")
                    )
                )
                <= cfg.validation.q95_abs_charge_error_pct
            ),
            "interpretation": "Uncorrected calibrated currents.",
        },
        "raw_estimated_energy_q95_absolute_error_pct": {
            "value": float(
                pair_summary.get("raw_abs_energy_error_q95_pct", float("nan"))
            ),
            "limit": cfg.validation.q95_abs_energy_error_pct,
            "pass": bool(
                np.isfinite(
                    float(
                        pair_summary.get(
                            "raw_abs_energy_error_q95_pct", float("nan")
                        )
                    )
                )
                and float(
                    pair_summary.get(
                        "raw_abs_energy_error_q95_pct", float("nan")
                    )
                )
                <= cfg.validation.q95_abs_energy_error_pct
            ),
            "interpretation": "Uncorrected calibrated currents.",
        },
        "charge_integral_q95_absolute_error_pct": {
            "value": float(pair_summary["abs_charge_error_q95_pct"]),
            "limit": cfg.validation.q95_abs_charge_error_pct,
            "pass": float(pair_summary["abs_charge_error_q95_pct"])
            <= cfg.validation.q95_abs_charge_error_pct,
        },
        "estimated_energy_q95_absolute_error_pct": {
            "value": float(pair_summary["abs_energy_error_q95_pct"]),
            "limit": cfg.validation.q95_abs_energy_error_pct,
            "pass": float(pair_summary["abs_energy_error_q95_pct"])
            <= cfg.validation.q95_abs_energy_error_pct,
        },
        "alignment_q95_absolute_ms": {
            "value": float(pair_summary["abs_alignment_q95_ms"]),
            "limit": cfg.validation.q95_abs_alignment_ms,
            "pass": float(pair_summary["abs_alignment_q95_ms"])
            <= cfg.validation.q95_abs_alignment_ms,
        },
        "median_selected_window_correlation": {
            "value": selected_correlation,
            "limit": cfg.validation.median_correlation_100ms,
            "pass": bool(np.isfinite(selected_correlation))
            and selected_correlation >= cfg.validation.median_correlation_100ms,
            "note": (
                "Uses the longest averaging window with at least the configured "
                "number of windows; short records fall back to 50 or 10 ms."
            ),
        },
    }
    selected_check_names = (
        "minimum_pair_count",
        "section_marker_sample_count",
        "charge_integral_q95_absolute_error_pct",
        "estimated_energy_q95_absolute_error_pct",
        "alignment_q95_absolute_ms",
        "median_selected_window_correlation",
    )
    time_domain_pass_all = all(checks[name]["pass"] for name in selected_check_names)

    nominal_energy_q95 = float(
        pair_summary.get("nominal_current_abs_energy_error_q95_pct", float("nan"))
    )
    nominal_charge_q95 = float(
        pair_summary.get("nominal_current_abs_charge_error_q95_pct", float("nan"))
    )
    nominal_pass = bool(
        int(pair_summary.get("nominal_current_n_pairs", 0)) >= cfg.validation.minimum_pairs
        and np.isfinite(nominal_energy_q95)
        and np.isfinite(nominal_charge_q95)
        and nominal_energy_q95 <= cfg.validation.q95_abs_energy_error_pct
        and nominal_charge_q95 <= cfg.validation.q95_abs_charge_error_pct
        and checks["alignment_q95_absolute_ms"]["pass"]
        and checks["median_selected_window_correlation"]["pass"]
    )

    nyquist = (
        float(spectral_summary.get("nyquist_hz_median", 0.0))
        if spectral_summary else 0.0
    )
    tek_rate = float(pair_summary.get("tek_rate_sps", pair_summary.get("rate_sps", 0.0)))
    pico_rate = float(pair_summary.get("pico_rate_sps", pair_summary.get("rate_sps", 0.0)))
    workload_fraction = float(
        spectral_summary.get("workload_related_psd_available_mean", float("nan"))
    ) if spectral_summary else float("nan")
    if not spectral_summary:
        spectral_status = "not_run"
    elif nyquist < 77_000:
        spectral_status = "limited_by_common_nyquist_below_77khz"
    elif tek_rate > pico_rate * (1.0 + 1e-12):
        spectral_status = "paired_common_band_plus_tek_native_extension"
    else:
        spectral_status = "paired_extended_bandwidth_available"
    if np.isfinite(workload_fraction) and workload_fraction < 0.8:
        spectral_status += "; active_only_no_reliable_idle"

    low_current_pairs = int(pair_summary.get("low_current_n_pairs", 0))
    low_current_offset_detected = bool(
        low_current_pairs > 0
        and abs(
            float(
                pair_summary.get(
                    "low_current_current_difference_ma_median", float("nan")
                )
            )
        ) >= 5.0
    )
    nominal_pair_count = int(pair_summary.get("nominal_current_n_pairs", 0))
    primary_time_domain_pass = (
        nominal_pass
        if nominal_pair_count >= cfg.validation.minimum_pairs
        else time_domain_pass_all
    )
    primary_time_domain_basis = (
        "nominal_current"
        if nominal_pair_count >= cfg.validation.minimum_pairs
        else "all_segments"
    )
    incremental_energy_q95 = float(
        pair_summary.get("incremental_abs_energy_error_q95_pct", float("nan"))
    )
    incremental_charge_q95 = float(
        pair_summary.get("incremental_abs_charge_error_q95_pct", float("nan"))
    )
    incremental_available = bool(
        np.isfinite(incremental_energy_q95)
        and np.isfinite(incremental_charge_q95)
    )
    baseline_mismatch_fraction = float(
        pair_summary.get("idle_baseline_mismatch_fraction", float("nan"))
    )
    baseline_mismatch_detected = bool(
        np.isfinite(baseline_mismatch_fraction) and baseline_mismatch_fraction > 0.0
    )
    correction_fraction = float(
        pair_summary.get("zero_offset_correction_applied_fraction", 0.0)
    )
    correction_applied = bool(correction_fraction > 0.0)
    correction_independent = bool(
        pair_summary.get("zero_offset_reference_independent", True)
    )
    raw_energy_q95 = float(
        pair_summary.get("raw_abs_energy_error_q95_pct", float("nan"))
    )
    raw_charge_q95 = float(
        pair_summary.get("raw_abs_charge_error_q95_pct", float("nan"))
    )
    return {
        "time_domain_validation_pass": primary_time_domain_pass,
        "time_domain_validation_basis": (
            f"{primary_time_domain_basis}; "
            + (
                "adaptive_offset_corrected"
                if correction_applied
                else "raw_calibrated_currents"
            )
        ),
        "absolute_validation_independent": bool(
            not correction_applied or correction_independent
        ),
        "absolute_validation_status": (
            "corrected_salvage_not_independent"
            if correction_applied and not correction_independent
            else (
                "corrected_with_independent_zero_reference"
                if correction_applied
                else "raw_uncorrected"
            )
        ),
        "zero_offset_correction_applied": correction_applied,
        "zero_offset_reference_independent": correction_independent,
        "zero_offset_detection_status_counts": pair_summary.get(
            "zero_offset_detection_status_counts", "disabled"
        ),
        "raw_charge_q95_absolute_error_pct": raw_charge_q95,
        "raw_estimated_energy_q95_absolute_error_pct": raw_energy_q95,
        "time_domain_validation_pass_all_segments": time_domain_pass_all,
        "time_domain_validation_pass_nominal_current": nominal_pass,
        "low_current_offset_detected": low_current_offset_detected,
        "idle_baseline_mismatch_detected": baseline_mismatch_detected,
        "idle_baseline_mismatch_fraction": baseline_mismatch_fraction,
        "incremental_validation_available": incremental_available,
        "incremental_charge_q95_absolute_error_pct": incremental_charge_q95,
        "incremental_estimated_energy_q95_absolute_error_pct": incremental_energy_q95,
        "incremental_validation_pass": bool(
            incremental_available
            and incremental_charge_q95 <= cfg.validation.q95_abs_charge_error_pct
            and incremental_energy_q95 <= cfg.validation.q95_abs_energy_error_pct
        ),
        "incremental_validation_interpretation": (
            "Diagnostic active-window energy above a same-run or independent "
            "rate-matched idle baseline. It does not replace the raw absolute "
            "current/energy comparison."
        ),
        "spectral_status": spectral_status,
        "checks": checks,
        "operating_region_interpretation": {
            "low_current_threshold_a": cfg.validation.low_current_threshold_a,
            "low_current_pairs": low_current_pairs,
            "nominal_current_pairs": int(
                pair_summary.get("nominal_current_n_pairs", 0)
            ),
            "note": (
                "Low-current segments are retained. A small absolute gain/offset "
                "difference can create a large relative error and is reported "
                "separately rather than removed as an outlier."
            ),
        },
        "interpretation": (
            "Time-domain validation reports raw and selected values separately. "
            "When a stable adaptive zero offset is corrected, raw metrics remain "
            "archived and the selected corrected comparison is explicitly marked "
            "as non-independent if the paired PicoScope idle setup supplied the "
            "reference. The Tektronix-native spectrum remains the primary PSD "
            "reference."
        ),
    }


def _save_representative(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def _plot_pair_overview(rate_output: Path, cfg: ScopeComparisonConfig) -> None:
    path = rate_output / "representative_trace.npz"
    if not path.is_file():
        return
    data = np.load(path)
    time_raw = data["time_raw_s"]
    tek = data["tek_current_a"]
    pico = data["pico_current_a"]
    time_aligned = data["time_aligned_s"]
    tek_a = data["tek_aligned_current_a"]
    pico_a = data["pico_aligned_current_a"]
    trigger = float(data["trigger_time_s"][0])
    active_start = float(data["active_start_s"][0])
    active_stop = float(data["active_stop_s"][0])
    idle_start = float(data["idle_start_s"][0])
    idle_stop = float(data["idle_stop_s"][0])
    lag_ms = float(data["lag_ms"][0])

    fig, axes = plt.subplots(3, 1, figsize=(10.5, 9.0), constrained_layout=True)
    axes[0].plot(time_raw, tek, label=cfg.tek.display_name)
    axes[0].plot(time_raw, pico, label=cfg.pico.display_name)
    axes[0].axvline(trigger, linestyle="--", label="Detected benchmark transition")
    if idle_stop > idle_start:
        axes[0].axvspan(idle_start, idle_stop, alpha=0.15, label="Idle PSD window")
    axes[0].axvspan(active_start, active_stop, alpha=0.10, label="Active PSD window")
    axes[0].set_xlabel("Time in recorded segment (s)")
    axes[0].set_ylabel("Calibrated current (A)")
    axes[0].set_title("Simultaneously triggered current segments")
    axes[0].legend(ncol=2)
    axes[0].grid(True, alpha=0.3)

    zoom_start = max(0.0, trigger - 0.20)
    zoom_stop = min(time_aligned[-1] if time_aligned.size else trigger + 1.0, trigger + 0.80)
    mask = (time_aligned >= zoom_start) & (time_aligned <= zoom_stop)
    axes[1].plot(time_aligned[mask], tek_a[mask], label=cfg.tek.display_name)
    axes[1].plot(time_aligned[mask], pico_a[mask], label=cfg.pico.display_name)
    axes[1].set_xlabel("Aligned time (s)")
    axes[1].set_ylabel("Calibrated current (A)")
    axes[1].set_title(f"Residual alignment around transition (estimated lag {lag_ms:+.3f} ms)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    count = min(tek_a.size, pico_a.size)
    diff = pico_a[:count] - tek_a[:count]
    axes[2].plot(time_aligned[:count], diff)
    axes[2].axhline(0.0, linewidth=0.8)
    axes[2].set_xlabel("Aligned time (s)")
    axes[2].set_ylabel("Pico − Tek current (A)")
    axes[2].set_title("Aligned current difference")
    axes[2].grid(True, alpha=0.3)

    figures = rate_output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / "paired_trace_overview.png", dpi=200)
    fig.savefig(figures / "paired_trace_overview.pdf")
    plt.close(fig)


def _plot_integrals(rate_output: Path) -> None:
    import csv

    with (rate_output / "scope_comparison" / "pair_metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return
    tek_q = np.asarray([float(row["tek_charge_as"]) for row in rows])
    pico_q = np.asarray([float(row["pico_charge_as"]) for row in rows])
    tek_e = np.asarray([float(row["tek_estimated_energy_j"]) for row in rows])
    pico_e = np.asarray([float(row["pico_estimated_energy_j"]) for row in rows])
    mean_current = np.asarray([float(row["tek_mean_current_a"]) for row in rows])
    current_delta_ma = np.asarray(
        [float(row.get("mean_current_difference_ma", "nan")) for row in rows]
    )
    error = 100.0 * (pico_e - tek_e) / tek_e
    threshold = float(rows[0].get("low_current_threshold_a", 0.75))

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.1), constrained_layout=True)
    axes[0].scatter(tek_q, pico_q)
    low = min(tek_q.min(), pico_q.min())
    high = max(tek_q.max(), pico_q.max())
    axes[0].plot([low, high], [low, high], linestyle="--")
    axes[0].set_xlabel("Tek current integral (A·s)")
    axes[0].set_ylabel("Pico current integral (A·s)")
    axes[0].set_title("Charge-equivalent integral")
    axes[0].grid(True, alpha=0.3)

    axes[1].scatter(mean_current, error)
    axes[1].axvspan(0.0, threshold, alpha=0.10, label="Low-current region")
    axes[1].axhline(0.0, linewidth=0.8)
    axes[1].axhline(1.0, linestyle="--", linewidth=0.8, label="±1%")
    axes[1].axhline(-1.0, linestyle="--", linewidth=0.8)
    axes[1].set_xlabel("Tek segment-mean current (A)")
    axes[1].set_ylabel("Pico vs. Tek energy difference (%)")
    axes[1].set_title("Relative error versus operating point")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(fontsize=7)

    axes[2].scatter(mean_current, current_delta_ma)
    axes[2].axvspan(0.0, threshold, alpha=0.10)
    axes[2].axhline(0.0, linewidth=0.8)
    axes[2].set_xlabel("Tek segment-mean current (A)")
    axes[2].set_ylabel("Pico − Tek mean current (mA)")
    axes[2].set_title("Absolute current-path difference")
    axes[2].grid(True, alpha=0.3)

    figures = rate_output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / "integral_and_energy_comparison.png", dpi=200)
    fig.savefig(figures / "integral_and_energy_comparison.pdf")
    plt.close(fig)


def _plot_bland_altman(rate_output: Path) -> None:
    import csv

    with (rate_output / "scope_comparison" / "pair_metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return
    tek = np.asarray([float(row["tek_estimated_energy_j"]) for row in rows])
    pico = np.asarray([float(row["pico_estimated_energy_j"]) for row in rows])
    mean = 0.5 * (tek + pico)
    diff = pico - tek
    bias = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1)) if diff.size > 1 else 0.0

    fig, ax = plt.subplots(figsize=(7.2, 4.3), constrained_layout=True)
    ax.scatter(mean, diff)
    ax.axhline(bias, label=f"Bias {bias:.4g} J")
    ax.axhline(bias + 1.96 * sd, linestyle="--", label="Bias ± 1.96 SD")
    ax.axhline(bias - 1.96 * sd, linestyle="--")
    ax.set_xlabel("Mean estimated segment energy (J)")
    ax.set_ylabel("Pico − Tek estimated energy (J)")
    ax.set_title("Bland–Altman comparison")
    ax.grid(True, alpha=0.3)
    ax.legend()
    figures = rate_output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / "bland_altman_energy.png", dpi=200)
    fig.savefig(figures / "bland_altman_energy.pdf")
    plt.close(fig)


def _thin_for_plot(x: np.ndarray, arrays: Sequence[np.ndarray], max_points: int):
    factor = max(1, int(math.ceil(x.size / max_points)))
    return x[::factor], [array[::factor] for array in arrays]


def _plot_psd(rate_output: Path, cfg: ScopeComparisonConfig) -> None:
    path = rate_output / "psd" / "psd_summary.npz"
    if not path.is_file():
        return
    data = np.load(path)
    f = np.asarray(data["frequencies_hz"], dtype=np.float64)
    keys = [
        "tek_active_psd_w2_per_hz_median",
        "pico_active_psd_w2_per_hz_median",
        "tek_idle_psd_w2_per_hz_median",
        "pico_idle_psd_w2_per_hz_median",
        "tek_analysis_psd_w2_per_hz_median",
        "pico_analysis_psd_w2_per_hz_median",
        "coherence_median",
        "analysis_psd_ratio_db_median",
    ]
    if not set(keys).issubset(data.files):
        return
    arrays = [np.asarray(data[key], dtype=np.float64) for key in keys]
    fp, thinned = _thin_for_plot(f, arrays, cfg.spectral.plot_max_points)
    active_t, active_p, idle_t, idle_p, analysis_t, analysis_p, coh, ratio = thinned
    idle_available = bool(np.any(np.isfinite(idle_t)) and np.any(np.isfinite(idle_p)))
    basis_label = (
        "Active minus pre-benchmark idle"
        if idle_available
        else "Active-only mean-centred PSD (no idle window)"
    )

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), constrained_layout=True)
    tiny = np.finfo(float).tiny
    axes[0, 0].semilogx(
        fp[1:], 10 * np.log10(np.maximum(active_t[1:], tiny)),
        label=cfg.tek.display_name,
    )
    axes[0, 0].semilogx(
        fp[1:], 10 * np.log10(np.maximum(active_p[1:], tiny)),
        label=cfg.pico.display_name,
    )
    axes[0, 0].set_xlabel("Frequency (Hz)")
    axes[0, 0].set_ylabel("Active power PSD (dB W²/Hz)")
    axes[0, 0].set_title("Active estimated-power spectra")
    axes[0, 0].legend()
    axes[0, 0].grid(True, which="both", alpha=0.3)

    if idle_available:
        axes[0, 1].semilogx(
            fp[1:], 10 * np.log10(np.maximum(idle_t[1:], tiny)),
            label=cfg.tek.display_name,
        )
        axes[0, 1].semilogx(
            fp[1:], 10 * np.log10(np.maximum(idle_p[1:], tiny)),
            label=cfg.pico.display_name,
        )
        axes[0, 1].set_title("Pre-benchmark idle spectra")
        axes[0, 1].legend()
    else:
        axes[0, 1].text(
            0.5, 0.5,
            "No pre-benchmark idle window\nActive-only spectral diagnostics",
            transform=axes[0, 1].transAxes,
            ha="center", va="center",
        )
        axes[0, 1].set_title("Idle subtraction unavailable")
    axes[0, 1].set_xlabel("Frequency (Hz)")
    axes[0, 1].set_ylabel("Idle power PSD (dB W²/Hz)")
    axes[0, 1].grid(True, which="both", alpha=0.3)

    finite_coherence = np.isfinite(coh)
    if np.any(finite_coherence):
        axes[1, 0].semilogx(fp[finite_coherence], coh[finite_coherence])
        axes[1, 0].axhline(
            cfg.spectral.coherence_threshold,
            linestyle="--",
            label="Configured threshold",
        )
        axes[1, 0].legend()
    else:
        axes[1, 0].text(
            0.5, 0.5,
            "Coherence suppressed:\ninsufficient Welch segments",
            transform=axes[1, 0].transAxes,
            ha="center", va="center",
        )
    axes[1, 0].set_ylim(-0.02, 1.02)
    axes[1, 0].set_xlabel("Frequency (Hz)")
    axes[1, 0].set_ylabel("Magnitude-squared coherence")
    axes[1, 0].set_title("Aligned active traces")
    axes[1, 0].grid(True, which="both", alpha=0.3)

    finite_ratio = np.isfinite(ratio)
    if np.any(finite_ratio):
        axes[1, 1].semilogx(fp[finite_ratio], ratio[finite_ratio])
    axes[1, 1].axhline(cfg.spectral.psd_ratio_tolerance_db, linestyle="--")
    axes[1, 1].axhline(
        -cfg.spectral.psd_ratio_tolerance_db,
        linestyle="--",
        label="± tolerance",
    )
    axes[1, 1].axhline(0.0, linewidth=0.8)
    axes[1, 1].set_xlabel("Frequency (Hz)")
    axes[1, 1].set_ylabel("Pico/Tek analysis-PSD ratio (dB)")
    axes[1, 1].set_title("Spectral amplitude agreement")
    axes[1, 1].legend()
    axes[1, 1].grid(True, which="both", alpha=0.3)

    figures = rate_output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / "psd_scope_comparison.png", dpi=200)
    fig.savefig(figures / "psd_scope_comparison.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2), constrained_layout=True)
    axes[0].semilogx(
        fp[1:], 10 * np.log10(np.maximum(analysis_t[1:], tiny)),
        label=cfg.tek.display_name,
    )
    axes[0].semilogx(
        fp[1:], 10 * np.log10(np.maximum(analysis_p[1:], tiny)),
        label=cfg.pico.display_name,
    )
    axes[0].set_xlabel("Frequency (Hz)")
    axes[0].set_ylabel("Analysis power PSD (dB W²/Hz)")
    axes[0].set_title(basis_label)
    axes[0].legend()
    axes[0].grid(True, which="both", alpha=0.3)

    tek_cumulative = np.asarray(data["tek_analysis_cumulative_median"])
    pico_cumulative = np.asarray(data["pico_analysis_cumulative_median"])
    fp2, [tek_c, pico_c] = _thin_for_plot(
        f, [tek_cumulative, pico_cumulative], cfg.spectral.plot_max_points
    )
    axes[1].semilogx(fp2[1:], 100.0 * tek_c[1:], label=cfg.tek.display_name)
    axes[1].semilogx(fp2[1:], 100.0 * pico_c[1:], label=cfg.pico.display_name)
    for fraction in cfg.spectral.cumulative_percentiles:
        axes[1].axhline(100.0 * fraction, linestyle="--", linewidth=0.8)
    axes[1].set_xlabel("Frequency (Hz)")
    axes[1].set_ylabel("Cumulative analysis variance (%)")
    axes[1].set_ylim(0, 101)
    axes[1].set_title(
        "Cumulative workload-related variance"
        if idle_available else "Cumulative active-only variance"
    )
    axes[1].legend()
    axes[1].grid(True, which="both", alpha=0.3)
    fig.savefig(figures / "psd_excess_and_cumulative.png", dpi=200)
    fig.savefig(figures / "psd_excess_and_cumulative.pdf")
    plt.close(fig)


def _plot_native_tek_extension(rate_output: Path, cfg: ScopeComparisonConfig) -> None:
    path = rate_output / "psd" / "tek_native_psd_summary.npz"
    if not path.is_file():
        return
    data = np.load(path)
    required = {
        "tek_native_frequencies_hz",
        "tek_native_analysis_psd_w2_per_hz_median",
        "tek_native_analysis_cumulative_median",
    }
    if not required.issubset(set(data.files)):
        return
    f = np.asarray(data["tek_native_frequencies_hz"], dtype=np.float64)
    density = np.asarray(
        data["tek_native_analysis_psd_w2_per_hz_median"], dtype=np.float64
    )
    cumulative = np.asarray(
        data["tek_native_analysis_cumulative_median"], dtype=np.float64
    )
    idle_available = bool(
        "tek_native_idle_psd_w2_per_hz_median" in data.files
        and np.any(np.isfinite(data["tek_native_idle_psd_w2_per_hz_median"]))
    )
    pair_summary_path = rate_output / "scope_comparison" / "pair_summary.csv"
    tek_rate = float("nan")
    pico_rate = float("nan")
    if pair_summary_path.is_file():
        import csv
        with pair_summary_path.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        tek_rate = float(row.get("tek_rate_sps", "nan"))
        pico_rate = float(row.get("pico_rate_sps", "nan"))
    fp, [dp, cp] = _thin_for_plot(
        f, [density, cumulative], cfg.spectral.plot_max_points
    )
    tiny = np.finfo(float).tiny
    figures = rate_output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3), constrained_layout=True)
    axes[0].semilogx(fp[1:], 10.0 * np.log10(np.maximum(dp[1:], tiny)))
    axes[0].axvline(77_000.0, linestyle="--", label="INA225 path: ~77 kHz")
    if np.isfinite(pico_rate):
        axes[0].axvline(
            pico_rate / 2.0,
            linestyle=":",
            label=f"Pico Nyquist: {pico_rate / 2.0 / 1e6:.6g} MHz",
        )
    axes[0].set_xlabel("Frequency (Hz)")
    axes[0].set_ylabel("Tek reference PSD (dB W²/Hz)")
    axes[0].set_title(
        f"Tek native spectrum ({human_rate(tek_rate)} sampling)\n"
        + ("active minus idle" if idle_available else "active-only; no idle subtraction")
    )
    axes[0].grid(True, which="both", alpha=0.3)
    axes[0].legend()

    axes[1].semilogx(fp[1:], 100.0 * cp[1:])
    axes[1].axvline(77_000.0, linestyle="--", label="77 kHz")
    if np.isfinite(pico_rate):
        axes[1].axvline(pico_rate / 2.0, linestyle=":", label="Pico Nyquist")
    axes[1].axhline(95.0, linestyle="--", linewidth=0.8)
    axes[1].axhline(99.0, linestyle="--", linewidth=0.8)
    axes[1].set_xlabel("Frequency (Hz)")
    axes[1].set_ylabel("Cumulative Tek reference variance (%)")
    axes[1].set_ylim(0.0, 101.0)
    axes[1].set_title(
        "Workload-related Tek variance"
        if idle_available else "Active-only Tek variance (diagnostic)"
    )
    axes[1].grid(True, which="both", alpha=0.3)
    axes[1].legend()
    fig.savefig(figures / "tek_native_psd_extension.png", dpi=200)
    fig.savefig(figures / "tek_native_psd_extension.pdf")
    plt.close(fig)



def _write_rate_summary(
    rate_output: Path,
    cfg: ScopeComparisonConfig,
    rate: int,
    pair_rows: list[dict[str, Any]],
    pair_summary: dict[str, Any],
    spectral_summary: dict[str, Any],
    decision: dict[str, Any],
) -> Path:
    tek_rate = float(pair_summary.get("tek_rate_sps", rate))
    pico_rate = float(pair_summary.get("pico_rate_sps", rate))
    common_rate = float(pair_summary.get("common_comparison_rate_sps", min(tek_rate, pico_rate)))
    lines = [
        f"# {cfg.dataset.workload_label}: Tektronix–PicoScope paired-segment comparison ({human_rate(tek_rate)} Tek / {human_rate(pico_rate)} Pico)",
        "",
        f"- Directory/nominal Tek rate: {human_rate(rate)}",
        f"- Actual Tektronix sampling rate: {human_rate(tek_rate)}",
        f"- Actual PicoScope sampling rate: {human_rate(pico_rate)}",
        f"- Paired common-grid rate for waveform, coherence, and PSD comparison: {human_rate(common_rate)}",
        f"- Common comparison Nyquist limit: {common_rate / 2.0 / 1e6:.6g} MHz",
        f"- Paired segments: {len(pair_rows)}",
        f"- Segment duration: median {np.median([row['record_duration_nominal_s'] for row in pair_rows]):.6g} s",
        f"- Median Tek/Pico duration difference: {np.median([row['duration_difference_s'] for row in pair_rows]) * 1e6:+.6g} µs",
        f"- Tek source: {cfg.tek.display_name} ({cfg.tek.raw_unit}; calibration gain {cfg.tek.gain_a_per_raw:g} A/raw)",
        f"- Pico source: {cfg.pico.display_name} ({cfg.pico.raw_unit}; calibration gain {cfg.pico.gain_a_per_raw:g} A/raw)",
        f"- Voltage model: `{cfg.voltage_model.model_type}`, calibration ID `{cfg.voltage_model.calibration_id}`",
        "- Segments are repeated, simultaneously triggered observations; they are not concatenated into an artificial 100-s trace.",
        "",
        "## Time-domain validation",
        "",
        f"- Adaptive zero-offset status: `{pair_summary.get('zero_offset_detection_status_counts', 'disabled')}`",
        f"- Applied additive Tektronix correction: {_format_number_for_summary(float(pair_summary.get('zero_offset_applied_ma_median', float('nan'))), decimals=3, suffix=' mA')}",
        f"- Corrected comparison independent of PicoScope: `{bool(pair_summary.get('zero_offset_reference_independent', True))}`",
        f"- Median raw Pico-vs-Tek current-integral difference: {pair_summary.get('raw_pico_vs_tek_charge_error_pct_median', float('nan')):+.4f}%",
        f"- q95 raw absolute current-integral difference: {pair_summary.get('raw_abs_charge_error_q95_pct', float('nan')):.4f}%",
        f"- Median raw Pico-vs-Tek estimated-energy difference: {pair_summary.get('raw_pico_vs_tek_energy_error_pct_median', float('nan')):+.4f}%",
        f"- q95 raw absolute estimated-energy difference: {pair_summary.get('raw_abs_energy_error_q95_pct', float('nan')):.4f}%",
        f"- Median selected Pico-vs-Tek current-integral difference: {pair_summary['pico_vs_tek_charge_error_pct_median']:+.4f}%",
        f"- q95 selected absolute current-integral difference: {pair_summary['abs_charge_error_q95_pct']:.4f}%",
        f"- Median selected Pico-vs-Tek estimated-energy difference: {pair_summary['pico_vs_tek_energy_error_pct_median']:+.4f}%",
        f"- q95 selected absolute estimated-energy difference: {pair_summary['abs_energy_error_q95_pct']:.4f}%",
        f"- Median residual lag: {pair_summary['lag_ms_median']:+.4f} ms",
        f"- q95 absolute residual lag: {pair_summary['abs_alignment_q95_ms']:.4f} ms",
        f"- Representative run selected near the median operating point: {int(pair_summary.get('representative_run', -1))}",
        f"- Median selected-window correlation: {pair_summary.get('selected_correlation_median', float('nan')):.6f} "
        f"(median window {pair_summary.get('selected_correlation_window_ms_median', float('nan')):.6g} ms)",
        f"- Complete-set time-domain validation pass: `{decision['time_domain_validation_pass_all_segments']}`",
        f"- Nominal-current time-domain validation pass: `{decision['time_domain_validation_pass_nominal_current']}`",
        f"- Low-current offset detected: `{decision['low_current_offset_detected']}`",
        f"- Idle baseline source counts: `{pair_summary.get('idle_baseline_source_counts', 'none')}`",
        f"- Median selected idle-current difference: {_format_number_for_summary(float(pair_summary.get('idle_baseline_current_difference_ma_median', float('nan'))), decimals=3, suffix=' mA')}",
        f"- Idle-baseline mismatch detected: `{decision.get('idle_baseline_mismatch_detected', False)}`",
        f"- q95 absolute active-window estimated-energy difference: {_format_percent_for_summary(float(pair_summary.get('active_window_abs_energy_error_q95_pct', float('nan'))))}",
        f"- q95 absolute idle-subtracted incremental-energy difference: {_format_percent_for_summary(float(pair_summary.get('incremental_abs_energy_error_q95_pct', float('nan'))))}",
        f"- Incremental-energy validation pass: `{decision.get('incremental_validation_pass', False)}`",
        "",
        "Raw full-record current and energy remain archived. When the adaptive zero-offset model passes all safety checks, the unprefixed selected metrics use the additive-corrected Tektronix trace and are explicitly marked as a non-independent post-hoc salvage comparison. Active-window and idle-subtracted incremental values remain additional diagnostics.",
        "",
        "## Spectral validation",
        "",
        f"- Status: `{decision['spectral_status']}`",
    ]
    if spectral_summary:
        lines.extend(
            [
                f"- Spectral Nyquist limit: {spectral_summary.get('nyquist_hz_median', float('nan')) / 1000:.3f} kHz",
                f"- Median active coherence over available bins: {spectral_summary.get('coherence_median_median', float('nan')):.4f}",
                f"- Median absolute excess-PSD ratio: {spectral_summary.get('abs_excess_psd_ratio_db_median_median', float('nan')):.3f} dB",
            ]
        )
        for fraction in cfg.spectral.cumulative_percentiles:
            label = int(round(fraction * 100))
            lines.append(
                f"- Common-band f{label}: Tek median {spectral_summary.get(f'tek_f{label}_hz_median', float('nan')) / 1000:.3f} kHz; "
                f"Pico median {spectral_summary.get(f'pico_f{label}_hz_median', float('nan')) / 1000:.3f} kHz"
            )
        native_workload = bool(
            spectral_summary.get(
                "tek_native_workload_related_psd_available_mean", 0.0
            ) >= 0.8
        )
        native_fraction = spectral_summary.get(
            "tek_native_analysis_variance_above_pico_nyquist_median", float("nan")
        )
        native_above_77 = spectral_summary.get(
            "tek_native_analysis_variance_above_77khz_median", float("nan")
        )
        native_basis = (
            "workload-related active-minus-idle"
            if native_workload else "active-only diagnostic"
        )
        lines.extend(
            [
                f"- Tek-native Nyquist limit: {spectral_summary.get('tek_native_nyquist_hz_median', float('nan')) / 1e6:.6g} MHz",
                f"- Tek-native PSD basis: {native_basis}",
                f"- Tek-native variance above the PicoScope Nyquist limit ({native_basis}): {100.0 * native_fraction:.4f}%",
                f"- Tek-native variance above 77 kHz ({native_basis}): {100.0 * native_above_77:.4f}%",
            ]
        )
    lines.extend(
        [
            "",
            "The paired common-band comparison validates the PicoScope current path, segment integral, and spectral shape only up to the shared Nyquist limit. "
            "Tektronix-native content above the PicoScope Nyquist limit is reported separately as a Tek-only extension and is not presented as paired validation.",
            "",
            "## Main files",
            "",
            "- `scope_comparison/pair_metrics.csv` (raw and selected metrics)",
            "- `../zero_correction/zero_offset_model.json`",
            "- `../zero_correction/zero_offset_pair_evidence.csv`",
            "- `../zero_correction/zero_offset_rate_evidence.csv`",
            "- `scope_comparison/pair_summary.csv`",
            "- `validation/validation_decision.json`",
            "- `psd/psd_summary.npz`",
            "- `psd/tek_native_psd_summary.npz`",
            "- `validation/representative_selection.json`",
            "- `psd/spectral_metrics_summary.csv`",
            "- `psd/spectral_band_summary.csv`",
            "- `figures/psd_scope_comparison.pdf` (common bandwidth)",
            "- `figures/tek_native_psd_extension.pdf` (Tek-only high-frequency extension)",
            "- `figures/`",
            "",
        ]
    )
    path = rate_output / "SCOPE_COMPARISON_SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_manifest(
    cfg: ScopeComparisonConfig,
    config_path: Path,
    selected_runs: Sequence[int] | None,
    rate_dirs: list[tuple[int, Path]],
) -> None:
    manifest = {
        "tool_version": __version__,
        "scope_analysis_schema_version": _SCOPE_ANALYSIS_SCHEMA_VERSION,
        "created_utc": utc_now_iso(),
        "config_path": str(config_path),
        "config": normalise_for_json(cfg),
        "selected_runs": None if selected_runs is None else list(selected_runs),
        "rate_directories": [
            {"rate_sps": rate, "path": str(path)} for rate, path in rate_dirs
        ],
        "package_versions": package_versions(),
        "method_scope": {
            "purpose": (
                "Validate the PicoScope/INA225 current path and its PSD against simultaneously "
                "triggered Tektronix current-probe segments."
            ),
            "segment_interpretation": (
                "Each pair is a repeated observation at the same trigger-relative location. "
                "Pairs are analysed independently and are never concatenated into a longer record."
            ),
            "energy_model": (
                "Power and energy are reconstructed independently for both current traces using "
                "the same configured current-dependent voltage model."
            ),
        },
        "signature": stable_hash(
            {
                "config": normalise_for_json(cfg),
                "selected_runs": selected_runs,
                "rate_dirs": [(rate, str(path)) for rate, path in rate_dirs],
            }
        ),
    }
    write_json(cfg.output_root / "scope_comparison_manifest.json", manifest)


def run_scope_comparison(
    cfg: ScopeComparisonConfig,
    config_path: Path,
    selected_runs: Sequence[int] | None = None,
    force: bool = False,
) -> Path:
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    rate_dirs = discover_rate_directories(cfg)
    _write_manifest(cfg, config_path, selected_runs, rate_dirs)
    cross_rate_rows: list[dict[str, Any]] = []
    all_pair_rows: list[dict[str, Any]] = []
    rate_inventory_rows: list[dict[str, Any]] = []
    skipped_pair_rows: list[dict[str, Any]] = []
    discovery_root = cfg.output_root / "input_discovery"
    discovery_root.mkdir(parents=True, exist_ok=True)
    external_idle_dirs = _external_idle_directory_map(cfg)
    external_idle_overview_rows: list[dict[str, Any]] = []
    zero_correction_model = _build_zero_offset_model(
        cfg,
        external_idle_dirs,
        dict(rate_dirs),
        force=force,
    )
    LOGGER.info(
        "Adaptive zero-offset model: status=%s, detected=%s, applied=%s, "
        "offset=%s mA, uncertainty=%s mA, confidence=%s, reference_rates=%s",
        zero_correction_model.get("status", "unknown"),
        zero_correction_model.get("offset_detected", False),
        zero_correction_model.get("correction_applied", False),
        (
            f"{float(zero_correction_model.get('offset_estimate_ma')):+.3f}"
            if zero_correction_model.get("offset_estimate_ma") is not None
            else "n/a"
        ),
        (
            f"{float(zero_correction_model.get('offset_uncertainty_ma')):.3f}"
            if zero_correction_model.get("offset_uncertainty_ma") is not None
            else "n/a"
        ),
        zero_correction_model.get("confidence", "none"),
        zero_correction_model.get("reference_rates_sps", []),
    )

    for rate, directory in rate_dirs:
        tek_rate_sps, pico_rate_sps = _source_rates_for_directory(cfg, rate)
        rate_output = cfg.output_root / f"{rate}Sps"
        rate_output.mkdir(parents=True, exist_ok=True)
        pairs, inventory = discover_pairs(cfg, directory, selected_runs)
        inventory["rate_sps"] = rate
        inventory["directory_rate_sps"] = rate
        inventory["tek_rate_sps"] = tek_rate_sps
        inventory["pico_rate_sps"] = pico_rate_sps
        inventory["candidate_pair_count"] = len(pairs)
        write_json(rate_output / "validation" / "pair_inventory.json", inventory)

        unpaired_count = 0
        for run in inventory.get("missing_tek_run_ids", []):
            unpaired_count += 1
            skipped_pair_rows.append(
                {
                    "rate_sps": rate,
                    "run": int(run),
                    "tek_path": "",
                    "pico_path": str(directory / cfg.pico.file_pattern.format(run=run)),
                    "status": "skipped",
                    "stage": "discovery",
                    "reason": "missing Tektronix mate",
                }
            )
        for run in inventory.get("missing_pico_run_ids", []):
            unpaired_count += 1
            skipped_pair_rows.append(
                {
                    "rate_sps": rate,
                    "run": int(run),
                    "tek_path": str(directory / cfg.tek.file_pattern.format(run=run)),
                    "pico_path": "",
                    "status": "skipped",
                    "stage": "discovery",
                    "reason": "missing PicoScope mate",
                }
            )

        if not pairs:
            reason = "no_complete_tek_pico_pairs"
            rate_inventory_rows.append(
                {
                    "rate_sps": rate,
                    "tek_rate_sps": tek_rate_sps,
                    "pico_rate_sps": pico_rate_sps,
                    "directory": str(directory),
                    "directory_name": directory.name,
                    "duration_source": "",
                    "tek_expected_rows": None,
                    "pico_expected_rows": None,
                    "expected_duration_s": None,
                    "candidate_pairs": 0,
                    "valid_pairs": 0,
                    "skipped_pairs": unpaired_count,
                    "status": "skipped",
                    "reason": reason,
                }
            )
            LOGGER.warning(
                "Skipping %s at %s: no complete Tek/Pico file pairs found",
                human_rate(rate),
                directory,
            )
            continue

        section_seconds = inventory.get("section_marker_seconds")
        preflight_rows = [
            _preflight_pair(
                cfg,
                rate,
                run,
                tek_path,
                pico_path,
                section_seconds,
            )
            for run, tek_path, pico_path in pairs
        ]
        duration_contract = _apply_auto_duration_inference(
            cfg, rate, section_seconds, preflight_rows
        )
        inventory["duration_contract"] = duration_contract
        write_csv(
            rate_output / "validation" / "pair_preflight.csv",
            preflight_rows,
            fieldnames=[
                "rate_sps",
                "directory_rate_sps",
                "tek_rate_sps",
                "pico_rate_sps",
                "run",
                "tek_path",
                "pico_path",
                "status",
                "reason",
                "tek_rows",
                "pico_rows",
                "tek_file_size_bytes",
                "pico_file_size_bytes",
                "tek_mtime_ns",
                "pico_mtime_ns",
                "tek_ctime_ns",
                "pico_ctime_ns",
                "tek_sampled_sha256",
                "pico_sampled_sha256",
                "source_fingerprint_schema_version",
                "source_fingerprint_sha256",
                "tek_duration_s",
                "pico_duration_s",
                "duration_difference_s",
                "duration_difference_ppm",
                "duration_match_tolerance_s",
                "common_nominal_duration_s",
                "expected_duration_s",
                "tek_expected_rows",
                "pico_expected_rows",
                "duration_source",
                "duration_tolerance_samples",
            ],
        )
        preflight_by_run = {int(row["run"]): row for row in preflight_rows}
        valid_pairs = [
            pair
            for pair in pairs
            if preflight_by_run[pair[0]]["status"] == "valid"
        ]
        preflight_skipped = [
            row for row in preflight_rows if row["status"] != "valid"
        ]
        for row in preflight_skipped:
            row.setdefault("stage", "preflight")
        skipped_pair_rows.extend(preflight_skipped)
        inventory["preflight_valid_run_ids"] = [run for run, _, _ in valid_pairs]
        inventory["preflight_skipped_run_ids"] = [
            int(row["run"]) for row in preflight_skipped
        ]
        write_json(rate_output / "validation" / "pair_inventory.json", inventory)

        if not valid_pairs:
            rate_inventory_rows.append(
                {
                    "rate_sps": rate,
                    "tek_rate_sps": tek_rate_sps,
                    "pico_rate_sps": pico_rate_sps,
                    "directory": str(directory),
                    "directory_name": directory.name,
                    "duration_source": duration_contract.get("duration_source", ""),
                    "tek_expected_rows": duration_contract.get("tek_expected_rows"),
                    "pico_expected_rows": duration_contract.get("pico_expected_rows"),
                    "expected_duration_s": duration_contract.get("expected_duration_s"),
                    "candidate_pairs": len(pairs),
                    "valid_pairs": 0,
                    "skipped_pairs": unpaired_count + len(preflight_skipped),
                    "status": "skipped",
                    "reason": "all_pairs_failed_preflight",
                }
            )
            LOGGER.warning(
                "Skipping %s at %s: all %d candidate pairs are empty, incomplete, "
                "unreadable, or have an unexpected sample count",
                human_rate(rate),
                directory,
                len(pairs),
            )
            continue

        LOGGER.info(
            "Scope comparison at %s: %d valid paired segments from %s "
            "(%d candidate, %d skipped during preflight)",
            human_rate(rate),
            len(valid_pairs),
            directory,
            len(pairs),
            len(preflight_skipped),
        )

        external_idle_reference = _build_external_idle_reference(
            cfg,
            rate,
            external_idle_dirs,
            force=force,
            zero_correction_model=zero_correction_model,
        )
        external_idle_overview_rows.append(
            {
                "rate_sps": int(rate),
                "status": external_idle_reference.get("status", "unavailable"),
                "directory": external_idle_reference.get("directory", ""),
                "candidate_pairs": int(
                    external_idle_reference.get("candidate_pairs", 0)
                ),
                "valid_pairs": int(external_idle_reference.get("valid_pairs", 0)),
                "reason": external_idle_reference.get("reason", ""),
                "source_fingerprint_sha256": external_idle_reference.get(
                    "source_fingerprint_sha256", ""
                ),
                "raw_tek_idle_current_a_median": external_idle_reference.get(
                    "summary", {}
                ).get("raw_tek_mean_current_a_median", float("nan")),
                "raw_pico_idle_current_a_median": external_idle_reference.get(
                    "summary", {}
                ).get("raw_pico_mean_current_a_median", float("nan")),
                "raw_idle_current_difference_ma_median": external_idle_reference.get(
                    "summary", {}
                ).get("raw_idle_current_difference_ma_median", float("nan")),
                "tek_idle_current_a_median": external_idle_reference.get(
                    "summary", {}
                ).get("tek_mean_current_a_median", float("nan")),
                "pico_idle_current_a_median": external_idle_reference.get(
                    "summary", {}
                ).get("pico_mean_current_a_median", float("nan")),
                "idle_current_difference_ma_median": external_idle_reference.get(
                    "summary", {}
                ).get("idle_current_difference_ma_median", float("nan")),
                "zero_offset_correction_applied": bool(
                    external_idle_reference.get(
                        "zero_offset_correction", {}
                    ).get("correction_applied", False)
                ),
                "zero_offset_applied_ma": 1000.0
                * float(
                    external_idle_reference.get(
                        "zero_offset_correction", {}
                    ).get("offset_applied_a", 0.0)
                ),
            }
        )

        pair_rows: list[dict[str, Any]] = []
        cache_audit_rows: list[dict[str, Any]] = []
        analysis_config_hash = stable_hash(
            {
                "scope_config": normalise_for_json(cfg),
                "rate_sps": rate,
                "external_idle_source_fingerprint_sha256": (
                    external_idle_reference.get("source_fingerprint_sha256", "")
                ),
                "zero_offset_model_hash": zero_correction_model.get(
                    "model_hash", ""
                ),
                "zero_offset_applied_a": _zero_offset_for_rate(
                    zero_correction_model, rate
                ),
            }
        )
        spectral_entries: list[tuple[int, dict[str, np.ndarray], dict[str, Any]]] = []
        native_spectral_entries: list[
            tuple[int, dict[str, np.ndarray], dict[str, Any]]
        ] = []
        all_band_rows: list[dict[str, Any]] = []
        metadata_rows: list[dict[str, Any]] = []
        representative_run = int(valid_pairs[0][0])  # replaced after all pairs
        analysis_skipped_count = 0
        duration_values = np.asarray(
            [
                min(
                    float(preflight_by_run[run]["tek_duration_s"]),
                    float(preflight_by_run[run]["pico_duration_s"]),
                )
                for run, _, _ in valid_pairs
            ],
            dtype=np.float64,
        )
        representative_duration_s = float(np.median(duration_values))
        shared_trigger_time_s, shared_trigger_anchor_source = (
            _configured_shared_trigger_time(
                cfg,
                rate,
                representative_duration_s,
            )
        )
        shared_trigger_source_run: int | None = (
            -1 if shared_trigger_time_s is not None else None
        )
        if shared_trigger_time_s is not None:
            LOGGER.info(
                "Using configured trigger position %.6f s (%s) as the shared "
                "hardware-trigger anchor for %s",
                shared_trigger_time_s,
                shared_trigger_anchor_source,
                human_rate(rate),
            )

        for run, tek_path, pico_path in valid_pairs:
            per_pair_dir = rate_output / "scope_comparison" / "per_pair"
            per_pair_dir.mkdir(parents=True, exist_ok=True)
            metrics_path = per_pair_dir / f"run_{run}.json"
            psd_path = rate_output / "psd" / "per_pair" / f"run_{run}.npz"
            native_psd_path = (
                rate_output / "psd" / "native_per_pair" / f"run_{run}.npz"
            )
            bands_path = rate_output / "psd" / "per_pair" / f"run_{run}_bands.csv"
            trace_path = (
                rate_output / "scope_comparison" / "per_pair" / f"run_{run}_trace.npz"
            )
            preflight_row = preflight_by_run[run]
            source_identity = preflight_row.get("source_identity")
            if not isinstance(source_identity, dict):
                source_identity = _pair_source_identity(tek_path, pico_path)
            source_fingerprint = str(source_identity["fingerprint_sha256"])
            required_cache_outputs = [metrics_path, trace_path]
            if cfg.spectral.enabled:
                required_cache_outputs.extend([psd_path, native_psd_path, bands_path])
            representative_path = rate_output / "representative_trace.npz"
            cache_reason = "force_recompute" if force else "no_cache"

            try:
                cache_complete = all(path.is_file() for path in required_cache_outputs)
                if cache_complete and not force:
                    with metrics_path.open("r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    reuse_cache, cache_reason, upgrade_payload = _cache_reuse_status(
                        payload=payload,
                        source_identity=source_identity,
                        analysis_config_hash=analysis_config_hash,
                        required_outputs=required_cache_outputs,
                        shared_trigger_time_s=shared_trigger_time_s,
                    )
                    if reuse_cache:
                        metrics = payload["metrics"]
                        if shared_trigger_time_s is None:
                            shared_trigger_time_s = float(
                                metrics.get("shared_trigger_time_s", metrics["trigger_time_s"])
                            )
                            shared_trigger_source_run = int(
                                metrics.get("shared_trigger_source_run", run)
                            )
                            shared_trigger_anchor_source = str(
                                metrics.get(
                                    "shared_trigger_anchor_source",
                                    "first_valid_detection",
                                )
                            )
                        if section_seconds is not None and "sample_count_matches_marker" not in metrics:
                            tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
                            tek_expected = int(round(float(section_seconds) * tek_rate))
                            pico_expected = int(round(float(section_seconds) * pico_rate))
                            metrics["section_marker_seconds"] = float(section_seconds)
                            metrics["tek_expected_samples_from_marker"] = tek_expected
                            metrics["pico_expected_samples_from_marker"] = pico_expected
                            metrics["sample_count_matches_marker"] = bool(
                                int(metrics["tek_samples"]) == tek_expected
                                and int(metrics["pico_samples"]) == pico_expected
                            )
                        metrics["source_fingerprint_sha256"] = source_fingerprint
                        metrics["analysis_config_hash"] = analysis_config_hash
                        if upgrade_payload:
                            payload["source_fingerprint_schema_version"] = (
                                _SOURCE_FINGERPRINT_SCHEMA_VERSION
                            )
                            payload["source_fingerprint_sha256"] = source_fingerprint
                            payload["source_identity"] = source_identity
                            payload["analysis_config_hash"] = analysis_config_hash
                            payload["metrics"] = metrics
                            write_json(metrics_path, payload)
                        pair_rows.append(metrics)
                        metadata_rows.append(payload["metadata"] | {"run": run, "rate_sps": rate})
                        if cfg.spectral.enabled:
                            arrays = dict(np.load(psd_path))
                            spectral_metrics = {
                                key: value
                                for key, value in metrics.items()
                                if key.startswith(("spectral_", "tek_f", "pico_f", "tek_analysis_", "pico_analysis_", "pico_minus_tek_", "pico_vs_tek_", "workload_related_", "coherence_", "abs_excess_", "abs_analysis_", "analysis_psd_", "excess_psd_", "tek_variance_", "pico_variance_", "nyquist_", "frequency_resolution_", "idle_frequency_resolution_", "nperseg", "active_nperseg", "active_welch_", "idle_nperseg", "idle_welch_", "idle_psd_available", "active_samples", "idle_samples", "tek_native_"))
                            }
                            spectral_entries.append((run, arrays, spectral_metrics))
                            native_arrays = dict(np.load(native_psd_path))
                            native_metrics = {
                                key: value
                                for key, value in metrics.items()
                                if key.startswith("tek_native_")
                            }
                            native_spectral_entries.append(
                                (run, native_arrays, native_metrics)
                            )
                            import csv
                            with bands_path.open("r", encoding="utf-8", newline="") as handle:
                                loaded = list(csv.DictReader(handle))
                            for row in loaded:
                                converted = {key: (float(value) if key not in {"band", "spectral_basis"} else value) for key, value in row.items()}
                                converted["run"] = run
                                converted["rate_sps"] = rate
                                all_band_rows.append(converted)
                        cache_audit_rows.append(
                            {
                                "rate_sps": rate,
                                "run": run,
                                "status": "reused",
                                "reason": cache_reason,
                                "source_fingerprint_sha256": source_fingerprint,
                                "cached_source_fingerprint_sha256": payload.get(
                                    "source_fingerprint_sha256", source_fingerprint
                                ),
                            }
                        )
                        LOGGER.info(
                            "Reused scope-comparison result: %s run %d (%s)",
                            human_rate(rate),
                            run,
                            cache_reason,
                        )
                        _log_pair_result(rate, run, metrics, prefix="Cached run")
                        continue

                    LOGGER.info(
                        "Recomputing scope-comparison result: %s run %d (%s)",
                        human_rate(rate),
                        run,
                        cache_reason,
                    )

                tek_raw, tek_meta = _read_parquet_column(tek_path, cfg.tek.column)
                pico_raw, pico_meta = _read_parquet_column(pico_path, cfg.pico.column)
                loaded_source_identity = _pair_source_identity(
                    tek_path,
                    pico_path,
                    tek_probe=tek_meta,
                    pico_probe=pico_meta,
                )
                if (
                    str(loaded_source_identity["fingerprint_sha256"])
                    != source_fingerprint
                ):
                    raise RuntimeError(
                        "source Parquet file changed between preflight and payload read"
                    )

                # Recheck the properties that can change between footer preflight
                # and payload loading when an acquisition is still writing.
                tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
                if cfg.input_policy.require_equal_sample_counts and tek_raw.size != pico_raw.size:
                    raise ValueError(
                        f"sample-count mismatch after load Tek={tek_raw.size} Pico={pico_raw.size}"
                    )
                tek_duration = tek_raw.size / tek_rate
                pico_duration = pico_raw.size / pico_rate
                common_duration = min(tek_duration, pico_duration)
                duration_tolerance = _duration_match_tolerance_s(
                    cfg, tek_rate, pico_rate, common_duration
                )
                if abs(pico_duration - tek_duration) > duration_tolerance:
                    raise ValueError(
                        "loaded physical record durations do not match: "
                        f"Tek={tek_duration:.12g}s at {tek_rate:g}S/s, "
                        f"Pico={pico_duration:.12g}s at {pico_rate:g}S/s, "
                        f"tolerance={duration_tolerance:.3g}s"
                    )
                tolerance = cfg.input_policy.duration_tolerance_samples
                tek_expected_raw = preflight_row.get("tek_expected_rows")
                pico_expected_raw = preflight_row.get("pico_expected_rows")
                if tek_expected_raw not in (None, ""):
                    tek_expected = int(tek_expected_raw)
                    if abs(tek_raw.size - tek_expected) > tolerance:
                        raise ValueError(
                            f"loaded Tek row count {tek_raw.size} does not match "
                            f"expected {tek_expected} +/- {tolerance}"
                        )
                if pico_expected_raw not in (None, ""):
                    pico_expected = int(pico_expected_raw)
                    if abs(pico_raw.size - pico_expected) > tolerance:
                        raise ValueError(
                            f"loaded Pico row count {pico_raw.size} does not match "
                            f"expected {pico_expected} +/- {tolerance}"
                        )

                result = _pair_metrics(
                    cfg,
                    rate,
                    run,
                    tek_raw,
                    pico_raw,
                    tek_path,
                    pico_path,
                    tek_meta,
                    pico_meta,
                    shared_trigger_time_s=shared_trigger_time_s,
                    shared_trigger_source_run=shared_trigger_source_run,
                    shared_trigger_anchor_source=shared_trigger_anchor_source,
                    external_idle_reference=external_idle_reference,
                    zero_correction_model=zero_correction_model,
                )
                (
                    metrics,
                    metadata,
                    spectral_arrays,
                    band_rows,
                    representative,
                    native_spectral_arrays,
                ) = result
                if shared_trigger_time_s is None:
                    shared_trigger_time_s = float(metrics["shared_trigger_time_s"])
                    shared_trigger_source_run = int(metrics["shared_trigger_source_run"])
                    shared_trigger_anchor_source = str(
                        metrics.get(
                            "shared_trigger_anchor_source",
                            "first_valid_detection",
                        )
                    )
                    LOGGER.info(
                        "Using run %d trigger position %.6f s as the shared "
                        "hardware-trigger anchor for %s",
                        shared_trigger_source_run,
                        shared_trigger_time_s,
                        human_rate(rate),
                    )
                trigger_residual_limit_ms = max(
                    50.0,
                    3.0 * float(cfg.windows.detection_smoothing_ms),
                )
                trigger_residual_ms = float(metrics["trigger_detection_residual_ms"])
                metrics["trigger_detection_consistent"] = bool(
                    abs(trigger_residual_ms) <= trigger_residual_limit_ms
                )
                metrics["trigger_detection_residual_limit_ms"] = trigger_residual_limit_ms
                if (
                    cfg.windows.step_detector_diagnostics
                    and not metrics["trigger_detection_consistent"]
                ):
                    LOGGER.warning(
                        "Run %d at %s: current-step detector differs from the shared "
                        "hardware-trigger position by %+0.3f ms; shared windows are used",
                        run,
                        human_rate(rate),
                        trigger_residual_ms,
                    )
                if section_seconds is not None:
                    tek_rate, pico_rate = _source_rates_for_directory(cfg, rate)
                    tek_expected = int(round(float(section_seconds) * tek_rate))
                    pico_expected = int(round(float(section_seconds) * pico_rate))
                    metrics["section_marker_seconds"] = float(section_seconds)
                    metrics["tek_expected_samples_from_marker"] = tek_expected
                    metrics["pico_expected_samples_from_marker"] = pico_expected
                    metrics["sample_count_matches_marker"] = bool(
                        int(metrics["tek_samples"]) == tek_expected
                        and int(metrics["pico_samples"]) == pico_expected
                    )
                else:
                    metrics["section_marker_seconds"] = None
                    metrics["tek_expected_samples_from_marker"] = None
                    metrics["pico_expected_samples_from_marker"] = None
                    metrics["sample_count_matches_marker"] = None
                metrics["source_fingerprint_sha256"] = source_fingerprint
                metrics["analysis_config_hash"] = analysis_config_hash
                pair_rows.append(metrics)
                metadata_rows.append(metadata | {"run": run, "rate_sps": rate})
                write_json(
                    metrics_path,
                    {
                        "scope_analysis_schema_version": _SCOPE_ANALYSIS_SCHEMA_VERSION,
                        "source_fingerprint_schema_version": (
                            _SOURCE_FINGERPRINT_SCHEMA_VERSION
                        ),
                        "source_fingerprint_sha256": source_fingerprint,
                        "source_identity": source_identity,
                        "analysis_config_hash": analysis_config_hash,
                        "metrics": metrics,
                        "metadata": metadata,
                    },
                )
                if representative is not None:
                    trace_path.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(trace_path, **representative)
                if spectral_arrays is not None:
                    psd_path.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(psd_path, **spectral_arrays)
                    spectral_metrics = {
                        key: value
                        for key, value in metrics.items()
                        if key.startswith(("spectral_", "tek_f", "pico_f", "tek_analysis_", "pico_analysis_", "pico_minus_tek_", "pico_vs_tek_", "workload_related_", "coherence_", "abs_excess_", "abs_analysis_", "analysis_psd_", "excess_psd_", "tek_variance_", "pico_variance_", "nyquist_", "frequency_resolution_", "idle_frequency_resolution_", "nperseg", "active_nperseg", "active_welch_", "idle_nperseg", "idle_welch_", "idle_psd_available", "active_samples", "idle_samples", "tek_native_"))
                    }
                    spectral_entries.append((run, spectral_arrays, spectral_metrics))
                    if native_spectral_arrays is not None:
                        native_psd_path.parent.mkdir(parents=True, exist_ok=True)
                        np.savez_compressed(native_psd_path, **native_spectral_arrays)
                        native_metrics = {
                            key: value
                            for key, value in metrics.items()
                            if key.startswith("tek_native_")
                        }
                        native_spectral_entries.append(
                            (run, native_spectral_arrays, native_metrics)
                        )
                    enriched_bands = [row | {"run": run, "rate_sps": rate} for row in band_rows]
                    all_band_rows.extend(enriched_bands)
                    write_csv(bands_path, enriched_bands)
                cache_audit_rows.append(
                    {
                        "rate_sps": rate,
                        "run": run,
                        "status": "recomputed",
                        "reason": cache_reason,
                        "source_fingerprint_sha256": source_fingerprint,
                        "cached_source_fingerprint_sha256": "",
                    }
                )
                _log_pair_result(rate, run, metrics)
                del tek_raw, pico_raw
                gc.collect()
            except Exception as error:
                skipped = {
                    "rate_sps": rate,
                    "run": run,
                    "tek_path": str(tek_path),
                    "pico_path": str(pico_path),
                    "status": "skipped",
                    "stage": "analysis",
                    "reason": f"{type(error).__name__}: {error}",
                }
                skipped_pair_rows.append(skipped)
                cache_audit_rows.append(
                    {
                        "rate_sps": rate,
                        "run": run,
                        "status": "skipped",
                        "reason": f"{type(error).__name__}: {error}",
                        "source_fingerprint_sha256": source_fingerprint,
                        "cached_source_fingerprint_sha256": "",
                    }
                )
                analysis_skipped_count += 1
                LOGGER.warning(
                    "Skipping run %d at %s because the pair is incomplete or invalid: %s",
                    run,
                    human_rate(rate),
                    error,
                )
                if not cfg.input_policy.ignore_invalid_pairs:
                    raise
                gc.collect()
                continue

        write_csv(
            rate_output / "validation" / "cache_reuse_audit.csv",
            cache_audit_rows,
            fieldnames=[
                "rate_sps",
                "run",
                "status",
                "reason",
                "source_fingerprint_sha256",
                "cached_source_fingerprint_sha256",
            ],
        )

        if not pair_rows:
            rate_inventory_rows.append(
                {
                    "rate_sps": rate,
                    "tek_rate_sps": tek_rate_sps,
                    "pico_rate_sps": pico_rate_sps,
                    "directory": str(directory),
                    "directory_name": directory.name,
                    "duration_source": duration_contract.get("duration_source", ""),
                    "tek_expected_rows": duration_contract.get("tek_expected_rows"),
                    "pico_expected_rows": duration_contract.get("pico_expected_rows"),
                    "expected_duration_s": duration_contract.get("expected_duration_s"),
                    "candidate_pairs": len(pairs),
                    "valid_pairs": 0,
                    "skipped_pairs": unpaired_count + len(preflight_skipped) + analysis_skipped_count,
                    "status": "skipped",
                    "reason": "all_pairs_failed_during_analysis",
                }
            )
            LOGGER.warning(
                "Skipping %s summary: no pair survived analysis",
                human_rate(rate),
            )
            continue

        pair_rows.sort(key=lambda row: int(row["run"]))
        representative_run, representative_audit = _select_representative_run(pair_rows)
        representative_source = (
            rate_output
            / "scope_comparison"
            / "per_pair"
            / f"run_{representative_run}_trace.npz"
        )
        representative_path = rate_output / "representative_trace.npz"
        if representative_source.is_file():
            shutil.copy2(representative_source, representative_path)
        write_json(
            rate_output / "validation" / "representative_selection.json",
            {
                "selected_run": representative_run,
                "selection_policy": (
                    "minimum robust distance to median Tek mean current and "
                    "estimated energy; nominal-current runs preferred"
                ),
                "candidates": representative_audit,
            },
        )
        for row in pair_rows:
            row["is_representative_run"] = int(row["run"]) == representative_run

        write_csv(rate_output / "scope_comparison" / "pair_metrics.csv", pair_rows)
        write_json(rate_output / "validation" / "pair_metadata.json", metadata_rows)
        pair_summary = _aggregate_pair_metrics(pair_rows, rate)
        pair_summary["representative_run"] = representative_run
        write_csv(rate_output / "scope_comparison" / "pair_summary.csv", [pair_summary])
        spectral_summary, _ = _aggregate_psd(
            rate_output,
            rate,
            spectral_entries,
            all_band_rows,
            cfg,
        )
        native_summary = _aggregate_native_psd(
            rate_output, rate, native_spectral_entries
        )
        decision = _validation_decision(cfg, pair_summary, spectral_summary)
        write_json(rate_output / "validation" / "validation_decision.json", decision)
        _plot_pair_overview(rate_output, cfg)
        _plot_integrals(rate_output)
        _plot_bland_altman(rate_output)
        _plot_psd(rate_output, cfg)
        _plot_native_tek_extension(rate_output, cfg)
        summary_path = _write_rate_summary(
            rate_output,
            cfg,
            rate,
            pair_rows,
            pair_summary,
            spectral_summary,
            decision,
        )
        LOGGER.info("Rate summary: %s", summary_path)
        all_pair_rows.extend(pair_rows)
        cross_rate_rows.append(
            {
                **pair_summary,
                **{
                    f"spectral_{key}": value
                    for key, value in spectral_summary.items()
                    if key not in {"rate_sps", "n_pairs"}
                },
                **{
                    f"native_{key}": value
                    for key, value in native_summary.items()
                    if key not in {"rate_sps", "n_pairs"}
                },
                "time_domain_validation_pass": decision["time_domain_validation_pass"],
                "time_domain_validation_pass_all_segments": decision[
                    "time_domain_validation_pass_all_segments"
                ],
                "time_domain_validation_pass_nominal_current": decision[
                    "time_domain_validation_pass_nominal_current"
                ],
                "low_current_offset_detected": decision[
                    "low_current_offset_detected"
                ],
                "idle_baseline_mismatch_detected": decision.get(
                    "idle_baseline_mismatch_detected", False
                ),
                "incremental_validation_available": decision.get(
                    "incremental_validation_available", False
                ),
                "incremental_validation_pass": decision.get(
                    "incremental_validation_pass", False
                ),
                "spectral_status": decision["spectral_status"],
                "rate_output": str(rate_output),
            }
        )
        rate_inventory_rows.append(
            {
                "rate_sps": rate,
                "tek_rate_sps": tek_rate_sps,
                "pico_rate_sps": pico_rate_sps,
                "directory": str(directory),
                "directory_name": directory.name,
                "duration_source": duration_contract.get("duration_source", ""),
                "tek_expected_rows": duration_contract.get("tek_expected_rows"),
                "pico_expected_rows": duration_contract.get("pico_expected_rows"),
                "expected_duration_s": duration_contract.get("expected_duration_s"),
                "candidate_pairs": len(pairs),
                "valid_pairs": len(pair_rows),
                "skipped_pairs": (
                    unpaired_count
                    + len(preflight_skipped)
                    + analysis_skipped_count
                ),
                "status": "processed",
                "reason": "",
            }
        )

    write_csv(
        discovery_root / "rate_inventory.csv",
        rate_inventory_rows,
        fieldnames=[
            "rate_sps",
            "tek_rate_sps",
            "pico_rate_sps",
            "directory",
            "directory_name",
            "duration_source",
            "tek_expected_rows",
            "pico_expected_rows",
            "expected_duration_s",
            "candidate_pairs",
            "valid_pairs",
            "skipped_pairs",
            "status",
            "reason",
        ],
    )
    write_csv(
        discovery_root / "skipped_pairs.csv",
        skipped_pair_rows,
        fieldnames=[
            "rate_sps",
            "tek_rate_sps",
            "pico_rate_sps",
            "run",
            "tek_path",
            "pico_path",
            "status",
            "stage",
            "reason",
            "tek_rows",
            "pico_rows",
            "tek_file_size_bytes",
            "pico_file_size_bytes",
            "tek_duration_s",
            "pico_duration_s",
            "duration_difference_s",
            "duration_match_tolerance_s",
            "expected_duration_s",
            "tek_expected_rows",
            "pico_expected_rows",
            "duration_source",
            "duration_tolerance_samples",
        ],
    )
    write_csv(
        cfg.output_root / "external_idle" / "external_idle_overview.csv",
        external_idle_overview_rows,
        fieldnames=[
            "rate_sps",
            "status",
            "directory",
            "candidate_pairs",
            "valid_pairs",
            "reason",
            "source_fingerprint_sha256",
            "raw_tek_idle_current_a_median",
            "raw_pico_idle_current_a_median",
            "raw_idle_current_difference_ma_median",
            "tek_idle_current_a_median",
            "pico_idle_current_a_median",
            "idle_current_difference_ma_median",
            "zero_offset_correction_applied",
            "zero_offset_applied_ma",
        ],
    )

    if not cross_rate_rows:
        message = (
            f"No valid paired-scope rate directory remained below {cfg.dataset_root}. "
            f"See {discovery_root / 'rate_inventory.csv'} and "
            f"{discovery_root / 'skipped_pairs.csv'}."
        )
        if cfg.input_policy.fail_if_no_valid_rates:
            raise RuntimeError(message)
        LOGGER.warning(message)

    write_csv(
        cfg.output_root / "cross_rate_summary.csv",
        cross_rate_rows,
        fieldnames=None if cross_rate_rows else ["rate_sps"],
    )

    operating_diagnostics: dict[str, Any] = {}
    tek_reference: dict[str, Any] = {}
    paired_selection: dict[str, Any] = {}
    pico_usability: dict[str, Any] = {}
    if cross_rate_rows:
        operating_diagnostics = _write_operating_point_diagnostics(
            cfg.output_root, all_pair_rows, cfg
        )
        tek_reference = _select_primary_tek_reference(
            cfg.output_root, cross_rate_rows, cfg
        )
        paired_selection = _select_pico_usability_rate(
            cfg.output_root, cross_rate_rows, cfg
        )
        pico_usability = _derive_pico_usability_from_tek_reference(
            cfg.output_root, tek_reference, paired_selection, cfg
        )
        write_json(
            cfg.output_root / "scope_analysis_overview.json",
            {
                "tool_version": __version__,
                "adaptive_zero_offset": zero_correction_model,
                "operating_point_diagnostics": operating_diagnostics,
                "tek_primary_reference": tek_reference,
                "paired_pico_validation_selection": paired_selection,
                "pico_usability": pico_usability,
            },
        )

    lines = [
        f"# {cfg.dataset.workload_label}: Tektronix-primary PSD and PicoScope validation",
        "",
        f"Dataset root: `{cfg.dataset_root}`",
        f"Dataset ID: `{cfg.dataset.dataset_id}`",
        "",
        "Each rate directory is analysed independently. The short records are repeated, simultaneously triggered observations and are never concatenated into an artificial long trace.",
        "",
        "The Tektronix-native current-probe measurement is the primary spectral reference. The PicoScope/INA225 setup is evaluated against that reference within the common bandwidth. Above 5 MS/s, the PicoScope remains fixed at 5 MS/s while the Tektronix rate increases.",
        "",
        (
            "Same-run pre-benchmark idle is preferred. When it is unavailable, "
            "the tool may use an independent exact-rate idle median from "
            f"`{cfg.external_idle.dataset_root}`. Raw absolute current and energy "
            "are always preserved; idle-subtracted active-window results are "
            "reported only as additional diagnostics. If the paired idle "
            "campaign reveals a material, bounded and cross-rate-stable additive "
            "Tektronix zero error, a separately marked offset-corrected salvage "
            "result is also emitted."
            if cfg.external_idle.enabled
            else "No external idle fallback is enabled for this data set."
        ),
        "",
        "Empty directories, one-sided pairs, unreadable files, and duration-mismatched pairs are skipped read-only and documented under `input_discovery/`.",
        "",
        "## Adaptive Tektronix zero-offset handling",
        "",
        f"- Status: `{zero_correction_model.get('status', 'disabled')}`",
        f"- Offset detected: `{zero_correction_model.get('offset_detected', False)}`",
        f"- Offset applied: `{zero_correction_model.get('correction_applied', False)}`",
        f"- Estimated offset: {_format_number_for_summary(float(zero_correction_model.get('offset_estimate_ma')) if zero_correction_model.get('offset_estimate_ma') is not None else float('nan'), decimals=3, suffix=' mA')}",
        f"- Applied offset: {_format_number_for_summary(float(zero_correction_model.get('offset_applied_ma', float('nan'))), decimals=3, suffix=' mA')}",
        f"- Estimated uncertainty: {_format_number_for_summary(float(zero_correction_model.get('offset_uncertainty_ma', float('nan'))), decimals=3, suffix=' mA')}",
        f"- Reference rates: `{zero_correction_model.get('reference_rates_sps', [])}`",
        f"- Reference pairs: {int(zero_correction_model.get('reference_pair_count', 0))}",
        f"- Confidence: `{zero_correction_model.get('confidence', 'none')}`",
        f"- Validation independence: `{zero_correction_model.get('validation_independence', 'not_applicable')}`",
        "- The correction is additive only. Raw metrics remain archived and no gain correction is fitted or applied.",
        "",
        "## Time-domain agreement by rate",
        "",
        "| Tek rate | Pico rate | Duration | Pairs | Median raw $\\Delta E$ | q95 raw $|\\Delta E|$ | Median selected $\\Delta E$ | q95 selected $|\\Delta E|$ nominal | Zero correction | q95 incremental $|\\Delta E|$ | Idle source(s) | Median selected $\\Delta I$ | Selected corr. | Window |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in cross_rate_rows:
        nominal_q95 = float(
            row.get("nominal_current_abs_energy_error_q95_pct", float("nan"))
        )
        low_q95 = float(
            row.get("low_current_abs_energy_error_q95_pct", float("nan"))
        )
        lines.append(
            f"| {human_rate(float(row.get('tek_rate_sps', row['rate_sps'])))} | "
            f"{human_rate(float(row.get('pico_rate_sps', row['rate_sps'])))} | "
            f"{float(row.get('common_nominal_duration_s_median', float('nan'))):.6g} s | "
            f"{int(row['n_pairs'])} | "
            f"{_format_percent_for_summary(float(row.get('raw_pico_vs_tek_energy_error_pct_median', float('nan'))), signed=True)} | "
            f"{_format_percent_for_summary(float(row.get('raw_abs_energy_error_q95_pct', float('nan'))))} | "
            f"{_format_percent_for_summary(float(row.get('pico_vs_tek_energy_error_pct_median', float('nan'))), signed=True)} | "
            f"{_format_percent_for_summary(nominal_q95)} | "
            f"{_format_number_for_summary(float(row.get('zero_offset_applied_ma_median', float('nan'))), decimals=3, suffix=' mA')} | "
            f"{_format_percent_for_summary(float(row.get('incremental_abs_energy_error_q95_pct', float('nan'))))} | "
            f"{row.get('idle_baseline_source_counts', 'none')} | "
            f"{_format_number_for_summary(float(row.get('mean_current_difference_ma_median', float('nan'))), decimals=3, suffix=' mA')} | "
            f"{_format_number_for_summary(float(row.get('selected_correlation_median', float('nan'))), decimals=6)} | "
            f"{_format_number_for_summary(float(row.get('selected_correlation_window_ms_median', float('nan'))), decimals=3, suffix=' ms')} |"
        )

    if tek_reference.get("status") == "selected":
        lines.extend(
            [
                "",
                "## Primary Tektronix PSD reference",
                "",
                f"- Selected Tektronix rate: {human_rate(float(tek_reference['selected_tek_rate_sps']))}",
                f"- Simultaneous PicoScope rate: {human_rate(float(tek_reference['selected_pico_rate_sps']))}",
                f"- Paired segments: {int(tek_reference['selected_n_pairs'])}",
                f"- PSD basis: `{tek_reference['psd_basis']}`",
                f"- Tektronix $f_{{95}}$: {float(tek_reference.get('f95_hz', float('nan'))) / 1000.0:.3f} kHz",
                f"- Tektronix $f_{{99}}$: {float(tek_reference.get('f99_hz', float('nan'))) / 1000.0:.3f} kHz",
                f"- Workload-related variance above 77 kHz: {100.0 * float(tek_reference.get('variance_above_77khz', float('nan'))):.3f}%",
                f"- Workload-related variance above the PicoScope Nyquist limit: {100.0 * float(tek_reference.get('variance_above_pico_nyquist', float('nan'))):.5f}%",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Primary Tektronix PSD reference",
                "",
                f"- Selection status: `{tek_reference.get('status', 'not_available')}`",
            ]
        )

    if pico_usability.get("status") == "selected":
        lines.extend(
            [
                "",
                "## PicoScope usability derived from the Tektronix reference",
                "",
                f"- Paired validation: Tek {human_rate(float(pico_usability['paired_tek_rate_sps']))} vs. Pico {human_rate(float(pico_usability['paired_pico_rate_sps']))}",
                f"- Shared Nyquist limit: {float(pico_usability['paired_common_nyquist_hz']) / 1e6:.6g} MHz",
                f"- Tek-reference variance retained below the PicoScope Nyquist limit: {100.0 * float(pico_usability.get('tek_reference_variance_captured_by_pico_sampling_ceiling', float('nan'))):.5f}%",
                f"- Integrated paired PSD ratio (Pico/Tek): {float(pico_usability.get('paired_pico_to_tek_integrated_psd_ratio_db', float('nan'))):+.3f} dB",
                f"- Highest predefined band satisfying the configured coherence and PSD-ratio criteria: {_format_hz_for_summary(float(pico_usability.get('highest_fixed_band_edge_meeting_agreement_hz', float('nan'))))}",
                "- The reported band edge is a validation summary, not an analogue -3 dB bandwidth estimate.",
            ]
        )

    skipped_rates = [row for row in rate_inventory_rows if row["status"] == "skipped"]
    if skipped_rates:
        lines.extend(
            [
                "",
                "## Skipped or still-in-progress rate directories",
                "",
                "| Rate | Reason |",
                "|---:|---|",
            ]
        )
        for row in skipped_rates:
            lines.append(
                f"| {human_rate(float(row['rate_sps']))} | {row['reason']} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Low-current segments remain in the analysis and are reported separately because a small absolute gain/offset mismatch can produce a large relative percentage error. The global affine fits are diagnostic only and are not applied as a calibration correction.",
            "",
            "The same current-dependent voltage model is applied to both current traces. The comparison therefore validates current-path agreement and consistent estimated-energy reconstruction; it does not independently validate the voltage model.",
            "",
            "A large raw percentage difference can be caused by a stable idle/DC baseline mismatch when the workload duty cycle is low. The external-idle and incremental-energy fields diagnose this condition.",
            "",
            (
                "A stable additive Tektronix zero error was detected and corrected "
                f"by {float(zero_correction_model.get('offset_applied_ma', 0.0)):+.3f} mA. "
                "Raw values remain archived. Because the paired PicoScope idle "
                "path supplied the reference, the selected corrected comparison "
                "is a post-hoc salvage result rather than an independent absolute "
                "validation of the PicoScope. No gain correction is applied."
                if zero_correction_model.get("correction_applied", False)
                else f"Adaptive zero-offset status: `{zero_correction_model.get('status', 'disabled')}`; no correction was applied."
            ),
            "",
        ]
    )
    summary = cfg.output_root / "SCOPE_COMPARISON_SUMMARY.md"
    summary.write_text("\n".join(lines), encoding="utf-8")

    if cross_rate_rows:
        # Generate paper-ready figures, tables, macros, and provenance from the
        # completed paired-scope result. Import lazily to avoid a module cycle.
        from .paper_artifacts import generate_scope_documentation_artifacts

        documentation_summary = generate_scope_documentation_artifacts(
            cfg.output_root,
            force=force,
        )
        LOGGER.info("Scope documentation artifacts: %s", documentation_summary)
    LOGGER.info("Scope comparison complete: %s", summary)
    return summary
