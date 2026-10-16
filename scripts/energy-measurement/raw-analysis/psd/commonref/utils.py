from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import platform
import re
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
import numpy as np
import scipy
import soxr
import yaml


LOGGER = logging.getLogger("commonref")


def setup_logging(output_root: Path, verbose: bool = False) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "analysis.log"

    # Keep ``analysis.log`` limited to the current command while preserving
    # previous runs under timestamped names.  Earlier releases appended all
    # commands to one file, which made a v0.6 run appear to contain v0.5.x
    # tracebacks and results.
    if log_path.is_file() and log_path.stat().st_size > 0:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = log_dir / f"analysis_previous_{stamp}.log"
        counter = 1
        while archive_path.exists():
            archive_path = log_dir / f"analysis_previous_{stamp}_{counter}.log"
            counter += 1
        log_path.replace(archive_path)

    level = logging.DEBUG if verbose else logging.INFO
    LOGGER.setLevel(level)
    LOGGER.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    LOGGER.addHandler(console)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)


def parse_run_spec(spec: str | None, default: Sequence[int]) -> list[int]:
    if spec is None or not spec.strip():
        return list(default)
    result: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_s, stop_s = token.split("-", 1)
            start, stop = int(start_s), int(stop_s)
            if stop < start:
                raise ValueError(f"Invalid run range: {token}")
            result.update(range(start, stop + 1))
        else:
            result.add(int(token))
    return sorted(result)


def normalise_for_json(value: Any) -> Any:
    """Return a strict-JSON-safe representation.

    Python's :mod:`json` encoder otherwise serialises ``NaN`` and infinities
    using non-standard JavaScript tokens.  Those tokens are accepted by
    Python itself but rejected by strict JSON parsers and CI validators.
    Missing/non-finite numerical results are therefore represented as
    ``null`` and rendered as ``n/a`` only in human-facing tables or prose.
    """
    if is_dataclass(value):
        return normalise_for_json(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): normalise_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalise_for_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return [normalise_for_json(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return normalise_for_json(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        normalise_for_json(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(
            normalise_for_json(data),
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    rows_list = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows_list and fieldnames is None:
        raise ValueError(f"Cannot infer CSV fields for empty output: {path}")
    names = list(fieldnames or rows_list[0].keys())
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_list)
    os.replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def discover_rate_directories(dataset_root: Path) -> list[tuple[int, Path]]:
    pattern = re.compile(r"^(\d+)Sps$")
    result: list[tuple[int, Path]] = []
    for path in dataset_root.iterdir():
        if not path.is_dir():
            continue
        match = pattern.fullmatch(path.name)
        if match:
            result.append((int(match.group(1)), path))
    return sorted(result)


def package_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
        "soxr": getattr(soxr, "__version__", "unknown"),
        "pyyaml": yaml.__version__,
    }
    try:
        import pyarrow  # type: ignore
    except ImportError:
        versions["pyarrow"] = "not installed"
    else:
        versions["pyarrow"] = getattr(pyarrow, "__version__", "unknown")
    return versions


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def quantile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.quantile(values, q))


def human_rate(rate: float) -> str:
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:g} MS/s"
    if rate >= 1_000:
        return f"{rate / 1_000:g} kS/s"
    return f"{rate:g} S/s"
