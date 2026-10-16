from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soxr
from scipy.signal import firwin, kaiserord, oaconvolve

from .config import AnalysisConfig
from .io import MeasurementMetadata
from .utils import LOGGER, read_json, stable_hash, utc_now_iso, write_json


@dataclass(frozen=True)
class CacheInfo:
    data_path: Path
    metadata_path: Path
    sample_rate_sps: int
    sample_count: int
    dtype: str
    duration_s: float


def cache_paths(output_root: Path, rate: int, run: int) -> tuple[Path, Path]:
    base = output_root / "cache" / f"{rate}Sps"
    return base / f"run_{run}.f32", base / f"run_{run}.json"


def open_cache(info: CacheInfo) -> np.memmap:
    dtype = np.dtype(info.dtype)
    return np.memmap(info.data_path, mode="r", dtype=dtype, shape=(info.sample_count,))


def load_cache_info(output_root: Path, rate: int, run: int) -> CacheInfo:
    data_path, meta_path = cache_paths(output_root, rate, run)
    metadata = read_json(meta_path)
    info = CacheInfo(
        data_path=data_path,
        metadata_path=meta_path,
        sample_rate_sps=int(metadata["output_rate_sps"]),
        sample_count=int(metadata["output_samples"]),
        dtype=str(metadata["output_dtype"]),
        duration_s=float(metadata["output_duration_s"]),
    )
    expected_size = info.sample_count * np.dtype(info.dtype).itemsize
    actual_size = data_path.stat().st_size
    if expected_size != actual_size:
        raise RuntimeError(
            f"Cache size mismatch for {data_path}: expected {expected_size}, got {actual_size}"
        )
    return info


def _stream_resample_to_binary(
    source: np.ndarray,
    source_rate: float,
    target_rate: float,
    output_path: Path,
    output_dtype: str,
    quality: str,
    chunk_seconds: float,
) -> int:
    if source.ndim != 1:
        raise ValueError("Only one-dimensional power traces are supported")
    if source.size == 0:
        raise ValueError("Cannot resample an empty trace")

    input_dtype = np.dtype(source.dtype)
    if input_dtype not in (np.dtype("float32"), np.dtype("float64")):
        internal_dtype = np.dtype("float64")
    else:
        internal_dtype = input_dtype

    stream = soxr.ResampleStream(
        float(source_rate),
        float(target_rate),
        1,
        dtype=str(internal_dtype),
        quality=quality,
    )

    chunk_samples = max(1, int(round(source_rate * chunk_seconds)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    output_count = 0
    with tmp_path.open("wb") as handle:
        for start in range(0, source.size, chunk_samples):
            stop = min(source.size, start + chunk_samples)
            chunk = np.asarray(source[start:stop], dtype=internal_dtype)
            final = stop == source.size
            result = stream.resample_chunk(chunk, last=final)
            if result.size:
                converted = np.asarray(result, dtype=output_dtype)
                converted.tofile(handle)
                output_count += converted.size

    os.replace(tmp_path, output_path)
    return int(output_count)


def _source_signature(path: Path, sample_count: int, rate: float) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sample_count": int(sample_count),
        "sample_rate_sps": float(rate),
    }


def build_cache_for_run(
    cfg: AnalysisConfig,
    measurement: MeasurementMetadata,
    force: bool = False,
) -> list[CacheInfo]:
    """Build a resumable, descending cache pyramid.

    Each lower cache is generated from the next-higher cache. SoXR provides the
    band-limited rate conversion. The original 5-MS/s NPY remains untouched.
    """

    built: dict[int, CacheInfo] = {}
    raw = np.load(measurement.npy_path, mmap_mode="r")
    source_array: np.ndarray = raw
    source_rate = measurement.sample_rate_sps
    source_path = measurement.npy_path

    for rate in cfg.cache_rates_sps:
        data_path, meta_path = cache_paths(cfg.output_root, rate, measurement.run)
        signature = {
            "source": _source_signature(source_path, source_array.size, source_rate),
            "target_rate_sps": rate,
            "quality": cfg.resampling_quality,
            "output_dtype": cfg.cache_dtype,
            "chunk_seconds": cfg.chunk_seconds,
        }
        signature_hash = stable_hash(signature)

        reusable = False
        if not force and data_path.is_file() and meta_path.is_file():
            metadata = read_json(meta_path)
            reusable = metadata.get("signature_hash") == signature_hash
            if reusable:
                try:
                    info = load_cache_info(cfg.output_root, rate, measurement.run)
                    built[rate] = info
                    LOGGER.info("Cache exists: run %d at %d S/s", measurement.run, rate)
                except Exception as error:
                    LOGGER.warning("Invalid cache will be rebuilt: %s", error)
                    reusable = False

        if not reusable:
            LOGGER.info(
                "Building cache: run %d, %.0f -> %d S/s",
                measurement.run,
                source_rate,
                rate,
            )
            output_count = _stream_resample_to_binary(
                source=source_array,
                source_rate=source_rate,
                target_rate=rate,
                output_path=data_path,
                output_dtype=cfg.cache_dtype,
                quality=cfg.resampling_quality,
                chunk_seconds=cfg.chunk_seconds,
            )
            output_duration = output_count / rate
            source_duration = source_array.size / source_rate
            metadata = {
                "created_utc": utc_now_iso(),
                "run": measurement.run,
                "signature": signature,
                "signature_hash": signature_hash,
                "input_rate_sps": source_rate,
                "input_samples": int(source_array.size),
                "input_duration_s": source_duration,
                "output_rate_sps": rate,
                "output_samples": output_count,
                "output_duration_s": output_duration,
                "output_dtype": cfg.cache_dtype,
                "duration_difference_s": output_duration - source_duration,
            }
            write_json(meta_path, metadata)
            built[rate] = load_cache_info(cfg.output_root, rate, measurement.run)

        source_array = open_cache(built[rate])
        source_rate = float(rate)
        source_path = built[rate].data_path

    return [built[rate] for rate in cfg.cache_rates_sps]


def choose_source_cache(cfg: AnalysisConfig, grid_rate: int, run: int) -> CacheInfo:
    eligible = sorted(rate for rate in cfg.cache_rates_sps if rate >= grid_rate)
    if not eligible:
        raise ValueError(
            f"No cache rate is high enough for phase-grid rate {grid_rate} S/s"
        )
    return load_cache_info(cfg.output_root, eligible[0], run)


def phase_count_for_target(cfg: AnalysisConfig, target_rate: int) -> int:
    requested = cfg.phase_count(target_rate)
    highest_cache = max(cfg.cache_rates_sps)
    maximum = max(1, highest_cache // target_rate)
    return max(1, min(requested, maximum))


def design_phase_antialias_fir(
    target_rate: int,
    grid_rate: int,
    phase_count: int,
    cfg: AnalysisConfig,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    if phase_count <= 1:
        return None, {
            "filter": "SoXR target-rate band-limited resampling",
            "num_taps": 0,
            "passband_hz": None,
            "stopband_hz": target_rate / 2.0,
        }

    nyquist_target = target_rate / 2.0
    passband_hz = cfg.anti_alias.passband_fraction_of_nyquist * nyquist_target
    stopband_hz = cfg.anti_alias.stopband_fraction_of_nyquist * nyquist_target
    transition_width = stopband_hz - passband_hz
    if transition_width <= 0:
        raise ValueError("Anti-alias transition width must be positive")

    normalised_width = transition_width / (grid_rate / 2.0)
    num_taps, beta = kaiserord(cfg.anti_alias.attenuation_db, normalised_width)
    if num_taps % 2 == 0:
        num_taps += 1
    cutoff_hz = 0.5 * (passband_hz + stopband_hz)
    taps = firwin(
        num_taps,
        cutoff=cutoff_hz,
        fs=grid_rate,
        window=("kaiser", beta),
        scale=True,
    )
    return taps, {
        "filter": "linear-phase Kaiser-window FIR",
        "num_taps": int(num_taps),
        "kaiser_beta": float(beta),
        "passband_hz": float(passband_hz),
        "stopband_hz": float(stopband_hz),
        "cutoff_hz": float(cutoff_hz),
        "attenuation_db": cfg.anti_alias.attenuation_db,
    }


def resample_phase_grid(
    source: np.ndarray,
    source_rate: int,
    target_rate: int,
    phase_count: int,
    cfg: AnalysisConfig,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Create an anti-aliased phase grid.

    The output rate is ``target_rate * phase_count``. A target-rate anti-alias
    FIR is applied before interleaved phases are extracted.
    """

    grid_rate = int(target_rate * phase_count)
    if grid_rate > source_rate:
        raise ValueError(
            f"Phase-grid rate {grid_rate} exceeds source rate {source_rate}"
        )

    if grid_rate == source_rate:
        grid = np.asarray(source)
    else:
        grid = np.asarray(
            soxr.resample(
                np.asarray(source),
                float(source_rate),
                float(grid_rate),
                quality=cfg.resampling_quality,
            ),
            dtype=np.float64,
        )

    taps, filter_meta = design_phase_antialias_fir(
        target_rate=target_rate,
        grid_rate=grid_rate,
        phase_count=phase_count,
        cfg=cfg,
    )
    if grid_rate == source_rate and phase_count == 1:
        filter_meta["filter"] = (
            "identity on validated band-limited cache at the target rate"
        )
    if taps is not None:
        grid = oaconvolve(grid, taps, mode="same")

    filter_meta.update(
        {
            "source_rate_sps": source_rate,
            "target_rate_sps": target_rate,
            "phase_count": phase_count,
            "grid_rate_sps": grid_rate,
            "soxr_quality": cfg.resampling_quality,
        }
    )
    return grid, grid_rate, filter_meta


def phase_only_grid(
    source: np.ndarray,
    source_rate: int,
    target_rate: int,
    phase_count: int,
    chunk_points: int = 2_000_000,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Sample a uniform source without a target-rate anti-alias filter.

    The source is the configured high-rate cache. In v0.3 the primary source is
    1 MS/s, while a 250-kS/s source is retained for sensitivity analysis. Linear
    interpolation is used only to place a
    regular phase grid when the rate ratio is non-integer; it is *not* a
    target-rate anti-alias operation. This branch approximates the original
    ``sweep_without_filter`` acquisition policy.
    """

    grid_rate = int(target_rate * phase_count)
    if grid_rate > source_rate:
        raise ValueError(
            f"Phase-only grid rate {grid_rate} exceeds source rate {source_rate}"
        )
    if source.ndim != 1 or source.size < 2:
        raise ValueError("Phase-only source must be a one-dimensional non-trivial trace")

    if grid_rate == source_rate:
        grid = np.asarray(source)
    elif source_rate % grid_rate == 0:
        step = source_rate // grid_rate
        grid = np.asarray(source[::step])
    else:
        ratio = float(source_rate) / float(grid_rate)
        count = int(math.floor((source.size - 1) / ratio)) + 1
        grid = np.empty(count, dtype=np.float64)
        for start in range(0, count, chunk_points):
            stop = min(count, start + chunk_points)
            positions = np.arange(start, stop, dtype=np.float64) * ratio
            left = np.floor(positions).astype(np.int64)
            fraction = positions - left
            right = np.minimum(left + 1, source.size - 1)
            grid[start:stop] = (
                (1.0 - fraction) * np.asarray(source[left], dtype=np.float64)
                + fraction * np.asarray(source[right], dtype=np.float64)
            )

    return grid, grid_rate, {
        "filter": "none; phase-only sampling from configured high-rate cache",
        "num_taps": 0,
        "passband_hz": None,
        "stopband_hz": None,
        "source_rate_sps": source_rate,
        "target_rate_sps": target_rate,
        "phase_count": phase_count,
        "grid_rate_sps": grid_rate,
        "interpolation": "exact stride when possible, otherwise linear time-grid interpolation",
    }


def interpolate_uniform(values: np.ndarray, position: float) -> float:
    if position < 0 or position > values.size - 1:
        raise ValueError(
            f"Interpolation position {position} outside [0, {values.size - 1}]"
        )
    nearest = round(position)
    if abs(position - nearest) < 1e-10:
        return float(values[int(nearest)])
    left = int(math.floor(position))
    fraction = position - left
    return float((1.0 - fraction) * values[left] + fraction * values[left + 1])


def integrate_uniform_fixed_window(
    values: np.ndarray,
    sample_rate: float,
    first_sample_time_s: float,
    start_time_s: float,
    stop_time_s: float,
) -> float:
    if stop_time_s <= start_time_s:
        raise ValueError("stop_time_s must be greater than start_time_s")
    dt = 1.0 / sample_rate
    u_start = (start_time_s - first_sample_time_s) * sample_rate
    u_stop = (stop_time_s - first_sample_time_s) * sample_rate
    if u_start < 0 or u_stop > values.size - 1:
        raise ValueError(
            "Fixed integration window is not fully covered by the resampled trace: "
            f"u_start={u_start}, u_stop={u_stop}, n={values.size}"
        )

    y_start = interpolate_uniform(values, u_start)
    y_stop = interpolate_uniform(values, u_stop)
    first_inside = int(math.ceil(u_start - 1e-12))
    last_inside = int(math.floor(u_stop + 1e-12))

    if first_inside > last_inside:
        return 0.5 * (y_start + y_stop) * (stop_time_s - start_time_s)

    energy = 0.0
    first_inside_time = first_sample_time_s + first_inside * dt
    if first_inside_time > start_time_s + 1e-15:
        energy += 0.5 * (y_start + float(values[first_inside])) * (
            first_inside_time - start_time_s
        )

    if last_inside > first_inside:
        segment = values[first_inside : last_inside + 1]
        energy += dt * (
            0.5 * float(segment[0])
            + float(np.sum(segment[1:-1], dtype=np.float64))
            + 0.5 * float(segment[-1])
        )

    last_inside_time = first_sample_time_s + last_inside * dt
    if stop_time_s > last_inside_time + 1e-15:
        energy += 0.5 * (float(values[last_inside]) + y_stop) * (
            stop_time_s - last_inside_time
        )

    return float(energy)
