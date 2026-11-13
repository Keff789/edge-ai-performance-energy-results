"""Pure report statistics from the bundled ONNX Tool three_stage_canary.py.

Copyright (c) 2026 Keff789. MIT; see LICENSE. No runtime/hardware imports.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * float(q)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def summarize(values: Sequence[float]) -> dict[str, Any]:
    data = [float(value) for value in values]
    return {
        "count": len(data),
        "mean": statistics.fmean(data) if data else None,
        "median": percentile(data, 0.5),
        "p05": percentile(data, 0.05),
        "p95": percentile(data, 0.95),
        "min": min(data) if data else None,
        "max": max(data) if data else None,
    }
