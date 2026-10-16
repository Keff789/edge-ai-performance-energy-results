from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .utils import load_yaml


@dataclass(frozen=True)
class MeasurementMetadata:
    run: int
    sample_rate_sps: float
    energy_j: float
    duration_s: float
    start_idx: int
    stop_idx: int
    npy_path: Path
    yaml_path: Path
    use_voltage: bool | None
    measurement_type: str | None

    @property
    def start_time_s(self) -> float:
        return self.start_idx / self.sample_rate_sps

    @property
    def stop_time_s(self) -> float:
        return self.stop_idx / self.sample_rate_sps

    @property
    def active_sample_count(self) -> int:
        return self.stop_idx - self.start_idx + 1


def load_measurement(run_dir: Path) -> MeasurementMetadata:
    if not run_dir.name.isdigit():
        raise ValueError(f"Run directory must be numeric: {run_dir}")
    run = int(run_dir.name)
    yaml_path = run_dir / "results.yaml"
    npy_path = run_dir / "oscilloscope.npy"
    if not yaml_path.is_file():
        raise FileNotFoundError(yaml_path)
    if not npy_path.is_file():
        raise FileNotFoundError(npy_path)

    data = load_yaml(yaml_path)
    osc = data.get("oscilloscope_results")
    if not isinstance(osc, dict):
        raise ValueError(f"Missing oscilloscope_results in {yaml_path}")
    results = osc.get("results")
    if not isinstance(results, dict):
        raise ValueError(f"Missing oscilloscope_results.results in {yaml_path}")

    start_stop = results.get("start_stop_idx")
    if not isinstance(start_stop, list) or len(start_stop) != 2:
        raise ValueError(f"Invalid start_stop_idx in {yaml_path}")

    return MeasurementMetadata(
        run=run,
        sample_rate_sps=float(osc["sample_rate"]),
        energy_j=float(results["energy"]),
        duration_s=float(results["duration"]),
        start_idx=int(start_stop[0]),
        stop_idx=int(start_stop[1]),
        npy_path=npy_path,
        yaml_path=yaml_path,
        use_voltage=None if "use_voltage" not in osc else bool(osc["use_voltage"]),
        measurement_type=None if "msmt_type" not in osc else str(osc["msmt_type"]),
    )


def validate_measurement(meta: MeasurementMetadata, expected_rate: float | None = None) -> dict[str, Any]:
    power = np.load(meta.npy_path, mmap_mode="r")
    issues: list[str] = []
    if power.ndim != 1:
        issues.append(f"ndim={power.ndim}")
    if not (0 <= meta.start_idx <= meta.stop_idx < power.size):
        issues.append("invalid start/stop indices")
    active_duration = meta.active_sample_count / meta.sample_rate_sps
    tolerance = max(1.0 / meta.sample_rate_sps, 1e-9)
    if abs(active_duration - meta.duration_s) > tolerance:
        issues.append(
            f"duration mismatch: yaml={meta.duration_s}, indices={active_duration}"
        )
    if expected_rate is not None and abs(meta.sample_rate_sps - expected_rate) > 1e-6:
        issues.append(f"unexpected sample rate {meta.sample_rate_sps}")
    if not np.isfinite(meta.energy_j):
        issues.append("non-finite energy")

    return {
        "run": meta.run,
        "samples": int(power.size),
        "dtype": str(power.dtype),
        "total_duration_s": float(power.size / meta.sample_rate_sps),
        "start_time_s": meta.start_time_s,
        "stop_time_s": meta.stop_time_s,
        "active_duration_from_indices_s": active_duration,
        "yaml_duration_s": meta.duration_s,
        "energy_j": meta.energy_j,
        "issues": issues,
        "valid": not issues,
    }
