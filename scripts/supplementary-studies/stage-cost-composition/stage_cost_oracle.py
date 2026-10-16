"""Pure, label-free arithmetic for the predeclared two-stage experiment.

This module intentionally has no file, process, network or hardware access.
Completion times are seconds on one local monotonic clock; rates count observed
completions, never request latency divided by an in-flight limit.
"""

from dataclasses import dataclass
import math
import statistics


MEASURED_COUNT = 10_000
WARMUP_COUNT = 100
CORE_FIRST = 1_000
CORE_MIDDLE = 5_000
CORE_LAST = 9_000
PRACTICAL_BAND_PCT = 10.0
DRIFT_THRESHOLD_PCT = 5.0


def _positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def completion_rates(timing):
    """Retain arithmetic separately from acceptance; reject malformed clocks.

    All 10,000 observed completion stamps are required for the core estimate.
    IDs need not be ordered; timestamps must be in observed completion order.
    Timestamp ties are allowed when a poll observes several completed requests.
    """
    timestamps = timing.get("completion_times_s", [])
    count = timing.get("measured_completed")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("measured_completed must be a positive integer")
    if not isinstance(timestamps, list) or len(timestamps) != count:
        raise ValueError("completion timestamp count does not match measured_completed")
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
           for t in timestamps):
        raise ValueError("completion timestamps must be finite seconds")
    if any(right < left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("completion timestamps are not in observed completion order")
    start = timing.get("timer_start_s")
    end = timing.get("timer_end_s")
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
           for t in (start, end)):
        raise ValueError("timer endpoints must be finite seconds")
    duration = _positive(end - start, "total duration seconds")
    if timestamps[0] < start or timestamps[-1] > end:
        raise ValueError("completion timestamps lie outside timer endpoints")
    result = {"fps_total": count / duration, "total_duration_s": duration,
              "fps_core": None, "fps_first_half": None, "fps_second_half": None,
              "core_duration_s": None, "drift_relative_pct": None, "drift_flag": None}
    if count != MEASURED_COUNT:
        return result
    first = timestamps[CORE_FIRST - 1]
    middle = timestamps[CORE_MIDDLE - 1]
    last = timestamps[CORE_LAST - 1]
    core_seconds = _positive(last - first, "core duration seconds")
    half1 = (CORE_MIDDLE - CORE_FIRST) / _positive(middle - first, "first half seconds")
    half2 = (CORE_LAST - CORE_MIDDLE) / _positive(last - middle, "second half seconds")
    shift = 100.0 * (half2 / half1 - 1.0)
    result.update(fps_core=(CORE_LAST - CORE_FIRST) / core_seconds,
                  core_duration_s=core_seconds, fps_first_half=half1,
                  fps_second_half=half2, drift_relative_pct=shift,
                  drift_flag=abs(shift) > DRIFT_THRESHOLD_PCT)
    return result


@dataclass(frozen=True)
class ResourceDescriptor:
    descriptor_id: str
    prefix_inflight: int
    fifo_depth: int
    batch_size: int
    handoff_dtype: str
    handoff_layout: str
    prefix_scope: str
    consumer_scope: str
    shared_resources: tuple

    def __post_init__(self):
        if not self.descriptor_id or self.prefix_inflight not in (1, 8):
            raise ValueError("unbound or unsupported prefix resource descriptor")
        if self.fifo_depth != 3 or self.batch_size != 1:
            raise ValueError("resource descriptor differs from fixed FIFO/batch recipe")
        if not all((self.handoff_dtype, self.handoff_layout,
                    self.prefix_scope, self.consumer_scope)):
            raise ValueError("resource descriptor must state representation and included work")


@dataclass(frozen=True)
class StageCapacity:
    case_id: str
    block_id: int
    mode: str
    source_scope: str
    source_path: str
    run_id: str
    config_id: str
    candidate_id: str
    implementation_id: str
    input_recipe_id: str
    input_binding: tuple
    resource_descriptor_id: str
    fps_core: float
    task_valid: bool
    state_comparable: bool


def predict_oracle(prefix, consumer, resources):
    """Accept only isolated P/C capacities and a predeclared resource descriptor.

    There is no parameter for pipeline FPS, historical full anchors, queue times
    or correction coefficients. The returned prediction exists before PC labels
    are opened by the evaluator.
    """
    if not isinstance(prefix, StageCapacity) or not isinstance(consumer, StageCapacity):
        raise TypeError("predict_oracle requires validated StageCapacity objects")
    if not isinstance(resources, ResourceDescriptor):
        raise TypeError("predict_oracle requires the predeclared ResourceDescriptor")
    if prefix.mode != "P" or prefix.source_scope != "isolated_prefix":
        raise ValueError("P capacity must come from an isolated prefix process")
    if consumer.mode != "C" or consumer.source_scope != "isolated_consumer":
        raise ValueError("C capacity must come from an isolated consumer process")
    if not prefix.task_valid or not consumer.task_valid:
        raise ValueError("Oracle requires accepted independent stage measurements")
    for attr in ("case_id", "block_id", "config_id", "candidate_id", "implementation_id",
                 "input_recipe_id", "input_binding", "resource_descriptor_id"):
        if getattr(prefix, attr) != getattr(consumer, attr):
            raise ValueError(f"P/C identity mismatch: {attr}")
    if prefix.resource_descriptor_id != resources.descriptor_id:
        raise ValueError("P/C descriptor is not the predeclared descriptor")
    fps_p = _positive(prefix.fps_core, "isolated P core FPS")
    fps_c = _positive(consumer.fps_core, "isolated C core FPS")
    cost_p, cost_c = 1000.0 / fps_p, 1000.0 / fps_c
    return {"case_id": prefix.case_id, "block_id": prefix.block_id,
            "config_id": prefix.config_id, "candidate_id": prefix.candidate_id,
            "implementation_id": prefix.implementation_id,
            "input_recipe_id": prefix.input_recipe_id,
            "resource_descriptor_id": resources.descriptor_id,
            "P_run_id": prefix.run_id, "C_run_id": consumer.run_id,
            "P_source_path": prefix.source_path, "C_source_path": consumer.source_path,
            "fps_P_core": fps_p, "fps_C_core": fps_c,
            "cP_ms": cost_p, "cC_ms": cost_c,
            "cOracle_ms": max(cost_p, cost_c),
            "fps_Oracle_core": min(fps_p, fps_c),
            "predicted_bottleneck": "P" if cost_p > cost_c else "C" if cost_c > cost_p else "P=C",
            "state_comparable": prefix.state_comparable and consumer.state_comparable,
            "model": "two_stage_max_independent_core_costs"}


def compare_prediction(prediction, pipeline_core_fps, pipeline_total_fps):
    """PC labels enter only here, after prediction has been persisted."""
    observed = _positive(pipeline_core_fps, "pipeline core FPS")
    total = _positive(pipeline_total_fps, "pipeline total FPS")
    signed = 100.0 * (prediction["fps_Oracle_core"] / observed - 1.0)
    return {"fps_PC_core": observed, "fps_PC_total": total,
            "signed_error_pct": signed, "absolute_error_pct": abs(signed),
            "cycle_residual_ms": 1000.0 / observed - prediction["cOracle_ms"],
            "within_10pct_band": abs(signed) <= PRACTICAL_BAND_PCT}


def summarize(values):
    """Physical processes are repetitions; missing third processes stay missing."""
    numbers = [float(x) for x in values if x is not None and math.isfinite(x)]
    if not numbers:
        return {"n": 0, "median": None, "min": None, "max": None, "spread_relative_pct": None}
    med = statistics.median(numbers)
    return {"n": len(numbers), "median": med, "min": min(numbers), "max": max(numbers),
            "spread_relative_pct": 100.0 * (max(numbers) - min(numbers)) / abs(med)
            if med else None}
