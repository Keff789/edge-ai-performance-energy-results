#!/usr/bin/env python3
"""Isolated Hailo-10H InferModel host-output format A/B benchmark.

Variant A requests FLOAT32 outputs. Variant B keeps the HEF-native UINT8 or
UINT16 output type. The HEF, inputs, warm-up, frame count and in-flight depth
remain identical. This script neither changes the HEF nor the product source.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCRIPT_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if name:
        return str(name).upper()
    text = str(value)
    return text.rsplit(".", 1)[-1].upper()


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


def command_output(argv: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
        return {
            "available": True,
            "returncode": completed.returncode,
            "output": completed.stdout.strip(),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": str(exc)}


def hailo_distributions() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or ""
        if "hailo" in name.lower():
            result.append({"name": name, "version": dist.version})
    return sorted(result, key=lambda row: row["name"].lower())


def numeric_attr(obj: Any, names: Iterable[str]) -> float | None:
    for name in names:
        if not hasattr(obj, name):
            continue
        value = getattr(obj, name)
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def quant_info_record(qinfo: Any) -> dict[str, Any]:
    return {
        "scale": numeric_attr(qinfo, ("qp_scale", "scale")),
        "zero_point": numeric_attr(qinfo, ("qp_zp", "zero_point", "zp")),
        "limvals_min": numeric_attr(qinfo, ("limvals_min",)),
        "limvals_max": numeric_attr(qinfo, ("limvals_max",)),
        "repr": repr(qinfo),
    }


def shape_record(value: Any) -> list[int] | dict[str, int] | str:
    if value is None:
        return []
    try:
        return [int(v) for v in value]
    except TypeError:
        fields: dict[str, int] = {}
        for name in ("height", "width", "features", "size"):
            if hasattr(value, name):
                try:
                    fields[name] = int(getattr(value, name))
                except (TypeError, ValueError):
                    pass
        return fields if fields else str(value)


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return math.nan
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def latency_summary(samples_ms: list[float]) -> dict[str, Any]:
    ordered = sorted(samples_ms)
    return {
        "frames": len(samples_ms),
        "mean_ms": statistics.fmean(samples_ms),
        "median_ms": statistics.median(samples_ms),
        "stdev_ms": statistics.pstdev(samples_ms),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "p95_ms": percentile(ordered, 0.95),
    }


def type_to_dtype(format_type: Any, FormatType: Any) -> np.dtype[Any]:
    name = enum_name(format_type)
    mapping = {
        "UINT8": np.dtype(np.uint8),
        "UINT16": np.dtype(np.uint16),
        "FLOAT32": np.dtype(np.float32),
    }
    if name not in mapping:
        raise RuntimeError(f"unsupported host output format type: {name}")
    return mapping[name]


def get_stream_format_record(stream: Any) -> dict[str, Any]:
    fmt = stream.format
    return {
        "type": enum_name(getattr(fmt, "type", "UNKNOWN")),
        "order": enum_name(getattr(fmt, "order", "UNKNOWN")),
        "shape": [int(v) for v in stream.shape],
        "is_nms": bool(stream.is_nms),
    }


def inspect_hef(hef_path: Path, hp: Any) -> dict[str, Any]:
    hef = hp.HEF(str(hef_path))
    network_groups = [str(v) for v in hef.get_network_group_names()]
    if not network_groups:
        raise RuntimeError("HEF contains no network group")
    network_group = network_groups[0]
    low_level_outputs = list(hef.get_output_stream_infos(network_group))
    low_level_by_name = {
        str(getattr(info, "name", "")): info for info in low_level_outputs
    }

    def info_record(info: Any) -> dict[str, Any]:
        fmt = getattr(info, "format", None)
        qinfos = getattr(info, "quant_infos", None)
        if qinfos is None:
            single = getattr(info, "quant_info", None)
            qinfos = [] if single is None else [single]
        return {
            "name": str(getattr(info, "name", "")),
            "shape": shape_record(getattr(info, "shape", ())),
            "hw_shape": shape_record(getattr(info, "hw_shape", ())),
            "hw_frame_size": jsonable(getattr(info, "hw_frame_size", None)),
            "hw_data_bytes": jsonable(getattr(info, "hw_data_bytes", None)),
            "format_type": enum_name(getattr(fmt, "type", "UNKNOWN")),
            "format_order": enum_name(getattr(fmt, "order", "UNKNOWN")),
            "quant_infos": [quant_info_record(q) for q in qinfos],
        }

    output_records: list[dict[str, Any]] = []
    for info in hef.get_output_vstream_infos():
        record = info_record(info)
        try:
            stream_names = [
                str(v)
                for v in hef.get_stream_names_from_vstream_name(
                    record["name"], network_group
                )
            ]
        except Exception as exc:
            stream_names = []
            record["native_stream_resolution_error"] = f"{type(exc).__name__}: {exc}"
        native_streams = [
            info_record(low_level_by_name[name])
            for name in stream_names
            if name in low_level_by_name
        ]
        record["underlying_stream_names"] = stream_names
        record["underlying_streams"] = native_streams
        native_types = {
            row["format_type"]
            for row in native_streams
            if row["format_type"] in {"UINT8", "UINT16"}
        }
        record["device_native_format_type"] = (
            next(iter(native_types))
            if len(native_streams) == 1 and len(native_types) == 1
            else None
        )
        output_records.append(record)

    return {
        "network_groups": network_groups,
        "selected_network_group": network_group,
        "inputs": [info_record(v) for v in hef.get_input_vstream_infos()],
        "outputs": output_records,
        "low_level_outputs": [info_record(v) for v in low_level_outputs],
    }


def native_candidate_maps(
    default_output_types: dict[str, str],
    hef_info: dict[str, Any],
    FormatType: Any,
) -> list[dict[str, Any]]:
    hef_types = {
        row["name"]: row.get("device_native_format_type")
        for row in hef_info.get("outputs", [])
    }
    known: dict[str, Any] = {}
    for name, default_name in default_output_types.items():
        # The low-level stream is authoritative for the device-native type.
        # A vstream default may already describe a host-side FLOAT32 format.
        type_name = hef_types.get(name) or "UNKNOWN"
        if type_name not in {"UINT8", "UINT16"}:
            type_name = default_name
        if type_name in {"UINT8", "UINT16"}:
            known[name] = getattr(FormatType, type_name)

    # Do not guess UINT8/UINT16 and do not use AUTO. The B arm must be the
    # explicit native HEF type so that it cannot silently benchmark another
    # host-side conversion.
    return [known] if len(known) == len(default_output_types) else []


def allocate_bindings(
    configured: Any,
    infer_model: Any,
    output_types: dict[str, Any],
    input_seed: int,
    count: int,
    FormatType: Any,
) -> tuple[list[Any], list[dict[str, np.ndarray]], list[dict[str, np.ndarray]]]:
    input_templates: dict[str, np.ndarray] = {}
    rng = np.random.default_rng(input_seed)
    for name in infer_model.input_names:
        shape = tuple(int(v) for v in infer_model.input(name).shape)
        input_templates[name] = np.ascontiguousarray(
            rng.random(shape, dtype=np.float32)
        )

    bindings_list: list[Any] = []
    input_sets: list[dict[str, np.ndarray]] = []
    output_sets: list[dict[str, np.ndarray]] = []
    for _ in range(count):
        inputs = {
            name: np.ascontiguousarray(template.copy())
            for name, template in input_templates.items()
        }
        outputs: dict[str, np.ndarray] = {}
        for name in infer_model.output_names:
            stream = infer_model.output(name)
            if stream.is_nms:
                raise RuntimeError(
                    "NMS outputs are intentionally unsupported by this format microbenchmark; "
                    "use a Part1 HEF with a tensor boundary"
                )
            shape = tuple(int(v) for v in stream.shape)
            dtype = type_to_dtype(output_types[name], FormatType)
            outputs[name] = np.empty(shape, dtype=dtype, order="C")
        bindings = configured.create_bindings(
            input_buffers=inputs,
            output_buffers=outputs,
        )
        bindings_list.append(bindings)
        input_sets.append(inputs)
        output_sets.append(outputs)
    return bindings_list, input_sets, output_sets


def wait_and_run(configured: Any, bindings: Any, timeout_ms: int) -> None:
    configured.wait_for_async_ready(timeout_ms=timeout_ms, frames_count=1)
    job = configured.run_async([bindings])
    job.wait(timeout_ms)


def dequantize_output(
    raw: np.ndarray,
    qinfos: list[Any],
    hp: Any,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    if raw.dtype == np.float32:
        return raw.copy(), {"method": "already_float32", "mean_ms": 0.0}
    if len(qinfos) != 1:
        return None, {
            "method": "unavailable",
            "reason": f"expected exactly one quant_info, got {len(qinfos)}",
        }

    qinfo = qinfos[0]
    repetitions = 20
    durations: list[float] = []
    last: np.ndarray | None = None
    transform = getattr(hp, "HailoRTTransformUtils", None)
    if transform is None:
        try:
            from hailo_platform.pyhailort.pyhailort import HailoRTTransformUtils

            transform = HailoRTTransformUtils
        except ImportError:
            transform = None
    if transform is not None:
        try:
            for _ in range(repetitions):
                dst = np.empty(raw.shape, dtype=np.float32, order="C")
                started = time.perf_counter_ns()
                transform.dequantize_output_buffer(
                    raw,
                    dst,
                    int(raw.size),
                    qinfo,
                )
                durations.append((time.perf_counter_ns() - started) / 1_000_000.0)
                last = dst
            return last, {
                "method": "HailoRTTransformUtils.dequantize_output_buffer",
                "repetitions": repetitions,
                "mean_ms": statistics.fmean(durations),
                "p95_ms": percentile(sorted(durations), 0.95),
            }
        except Exception as exc:  # compatibility fallback below
            transform_error = f"{type(exc).__name__}: {exc}"
    else:
        transform_error = "HailoRTTransformUtils not exported"

    scale = numeric_attr(qinfo, ("qp_scale", "scale"))
    zero_point = numeric_attr(qinfo, ("qp_zp", "zero_point", "zp"))
    if scale is None or zero_point is None:
        return None, {
            "method": "unavailable",
            "reason": transform_error,
            "quant_info": quant_info_record(qinfo),
        }

    for _ in range(repetitions):
        started = time.perf_counter_ns()
        last = (raw.astype(np.float32) - np.float32(zero_point)) * np.float32(scale)
        durations.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return last, {
        "method": "manual_single_qp",
        "hailort_transform_error": transform_error,
        "repetitions": repetitions,
        "mean_ms": statistics.fmean(durations),
        "p95_ms": percentile(sorted(durations), 0.95),
    }


@dataclass
class VariantRun:
    record: dict[str, Any]
    captured_outputs: dict[str, np.ndarray]
    dequantized_outputs: dict[str, np.ndarray]


def run_variant(
    name: str,
    hef_path: Path,
    output_type_map: dict[str, Any],
    args: argparse.Namespace,
    hp: Any,
) -> VariantRun:
    FormatType = hp.FormatType
    started_at = utc_now()
    with hp.VDevice() as vdevice:
        infer_model = vdevice.create_infer_model(str(hef_path))
        for input_name in infer_model.input_names:
            infer_model.input(input_name).set_format_type(FormatType.FLOAT32)
        for output_name, format_type in output_type_map.items():
            infer_model.output(output_name).set_format_type(format_type)

        input_records = {
            stream_name: get_stream_format_record(infer_model.input(stream_name))
            for stream_name in infer_model.input_names
        }
        output_records = {
            stream_name: get_stream_format_record(infer_model.output(stream_name))
            for stream_name in infer_model.output_names
        }
        qinfos = {
            stream_name: list(infer_model.output(stream_name).quant_infos)
            for stream_name in infer_model.output_names
        }

        with infer_model.configure() as configured:
            async_queue_size = int(configured.get_async_queue_size())
            slot_count = min(max(1, args.inflight), async_queue_size)
            if slot_count <= 0:
                raise RuntimeError(
                    f"ConfiguredInferModel returned invalid async queue size: {async_queue_size}"
                )
            bindings, _, output_sets = allocate_bindings(
                configured,
                infer_model,
                output_type_map,
                args.seed,
                slot_count,
                FormatType,
            )

            for index in range(args.warmup):
                wait_and_run(configured, bindings[index % slot_count], args.timeout_ms)

            latency_samples: list[float] = []
            latency_binding = bindings[0]
            for _ in range(args.latency_frames):
                started = time.perf_counter_ns()
                wait_and_run(configured, latency_binding, args.timeout_ms)
                latency_samples.append(
                    (time.perf_counter_ns() - started) / 1_000_000.0
                )

            jobs: list[Any | None] = [None] * slot_count
            throughput_started = time.perf_counter_ns()
            for frame_index in range(args.throughput_frames):
                slot = frame_index % slot_count
                previous = jobs[slot]
                if previous is not None:
                    previous.wait(args.timeout_ms)
                configured.wait_for_async_ready(
                    timeout_ms=args.timeout_ms,
                    frames_count=1,
                )
                jobs[slot] = configured.run_async([bindings[slot]])
            for job in jobs:
                if job is not None:
                    job.wait(args.timeout_ms)
            throughput_seconds = (
                time.perf_counter_ns() - throughput_started
            ) / 1_000_000_000.0

            # One unmeasured capture after all timed work.
            wait_and_run(configured, bindings[0], args.timeout_ms)
            captured = {
                output_name: np.ascontiguousarray(output_sets[0][output_name].copy())
                for output_name in infer_model.output_names
            }

            dequantized: dict[str, np.ndarray] = {}
            dequant_records: dict[str, Any] = {}
            for output_name, raw in captured.items():
                converted, conversion_record = dequantize_output(
                    raw,
                    qinfos[output_name],
                    hp,
                )
                dequant_records[output_name] = conversion_record
                if converted is not None:
                    dequantized[output_name] = converted

    output_bytes = {
        output_name: int(array.nbytes) for output_name, array in captured.items()
    }
    record = {
        "status": "ok",
        "variant": name,
        "started_at": started_at,
        "finished_at": utc_now(),
        "inputs": input_records,
        "outputs": {
            output_name: {
                **output_records[output_name],
                "requested_type": enum_name(output_type_map[output_name]),
                "numpy_dtype": str(captured[output_name].dtype),
                "bytes_per_frame": output_bytes[output_name],
                "quant_infos": [quant_info_record(q) for q in qinfos[output_name]],
                "dequantization": dequant_records[output_name],
            }
            for output_name in captured
        },
        "total_output_bytes_per_frame": sum(output_bytes.values()),
        "latency": latency_summary(latency_samples),
        "throughput": {
            "frames": args.throughput_frames,
            "requested_inflight": args.inflight,
            "effective_inflight": slot_count,
            "async_queue_size": async_queue_size,
            "elapsed_s": throughput_seconds,
            "fps": args.throughput_frames / throughput_seconds,
        },
    }
    return VariantRun(record, captured, dequantized)


def compare_outputs(
    float_run: VariantRun,
    native_run: VariantRun,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "compared", "outputs": {}}
    float_names = set(float_run.captured_outputs)
    native_names = set(native_run.captured_outputs)
    if float_names != native_names:
        return {
            "status": "not_comparable",
            "reason": "output name sets differ",
            "float32_outputs": sorted(float_names),
            "native_outputs": sorted(native_names),
        }

    for name in sorted(float_names):
        reference = float_run.captured_outputs[name].astype(np.float32, copy=False)
        candidate = native_run.dequantized_outputs.get(name)
        if candidate is None:
            result["outputs"][name] = {
                "status": "not_comparable",
                "reason": "native output could not be dequantized",
            }
            result["status"] = "partial"
            continue
        if reference.shape != candidate.shape:
            result["outputs"][name] = {
                "status": "not_comparable",
                "reason": "shape mismatch",
                "float32_shape": list(reference.shape),
                "native_dequantized_shape": list(candidate.shape),
            }
            result["status"] = "partial"
            continue
        delta = np.abs(reference - candidate)
        qrecords = native_run.record["outputs"][name]["quant_infos"]
        scales = [row.get("scale") for row in qrecords if row.get("scale") is not None]
        atol = max([1e-5] + [abs(float(scale)) * 1.05 for scale in scales])
        result["outputs"][name] = {
            "status": "ok",
            "elements": int(delta.size),
            "max_abs": float(np.max(delta)) if delta.size else 0.0,
            "mean_abs": float(np.mean(delta)) if delta.size else 0.0,
            "rmse": float(np.sqrt(np.mean(np.square(delta)))) if delta.size else 0.0,
            "allclose_atol": atol,
            "allclose": bool(np.allclose(reference, candidate, rtol=1e-5, atol=atol)),
        }
    return result


def ratio_record(float_run: VariantRun, native_run: VariantRun) -> dict[str, Any]:
    float_latency = float_run.record["latency"]["mean_ms"]
    native_latency = native_run.record["latency"]["mean_ms"]
    float_fps = float_run.record["throughput"]["fps"]
    native_fps = native_run.record["throughput"]["fps"]
    float_bytes = float_run.record["total_output_bytes_per_frame"]
    native_bytes = native_run.record["total_output_bytes_per_frame"]
    return {
        "latency_speedup_float32_over_native": float_latency / native_latency,
        "throughput_speedup_native_over_float32": native_fps / float_fps,
        "host_output_byte_reduction_ratio": float_bytes / native_bytes,
        "latency_reduction_percent": 100.0 * (1.0 - native_latency / float_latency),
        "throughput_increase_percent": 100.0 * (native_fps / float_fps - 1.0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hef", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--latency-frames", type=int, default=50)
    parser.add_argument("--throughput-frames", type=int, default=200)
    parser.add_argument("--inflight", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=27914)
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    for name in ("latency_frames", "throughput_frames", "inflight", "timeout_ms"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be > 0")
    return args


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {
        "schema": "hailo10_infermodel_format_ab/v1",
        "script_version": SCRIPT_VERSION,
        "started_at": utc_now(),
        "status": "running",
        "test_scope": "runtime_microbenchmark_not_scientific_claim",
        "hef": str(args.hef.expanduser().resolve()),
        "parameters": {
            "warmup": args.warmup,
            "latency_frames": args.latency_frames,
            "throughput_frames": args.throughput_frames,
            "inflight": args.inflight,
            "timeout_ms": args.timeout_ms,
            "seed": args.seed,
            "input_host_format": "FLOAT32",
            "power_mode_changed": False,
        },
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": sys.version,
            "executable": sys.executable,
            "numpy": np.__version__,
            "hailo_distributions": hailo_distributions(),
            "hailortcli_version": command_output(["hailortcli", "--version"]),
            "nvpmodel": command_output(["nvpmodel", "-q"]),
            "jetson_clocks": command_output(["jetson_clocks", "--show"]),
        },
        "variants": {},
        "native_attempts": [],
    }
    exit_code = 1
    try:
        hef_path = Path(result["hef"])
        if not hef_path.is_file():
            raise FileNotFoundError(f"HEF does not exist: {hef_path}")

        import hailo_platform as hp

        required = ("VDevice", "HEF", "FormatType")
        missing = [name for name in required if not hasattr(hp, name)]
        if missing:
            raise RuntimeError(f"hailo_platform lacks required API: {missing}")
        result["environment"]["hailo_platform_file"] = str(
            Path(hp.__file__).resolve()
        )
        result["environment"]["hailo_platform_version"] = str(
            getattr(hp, "__version__", "UNKNOWN")
        )
        result["environment"]["format_types"] = [
            name for name in dir(hp.FormatType) if name.isupper()
        ]
        result["hef_contract"] = inspect_hef(hef_path, hp)

        with hp.VDevice() as probe_device:
            probe_model = probe_device.create_infer_model(str(hef_path))
            output_names = [str(v) for v in probe_model.output_names]
            default_output_types = {
                name: enum_name(probe_model.output(name).format.type)
                for name in output_names
            }
            result["infermodel_probe"] = {
                "device_ids": [str(v) for v in probe_device.get_physical_devices_ids()],
                "input_names": [str(v) for v in probe_model.input_names],
                "output_names": output_names,
                "default_output_types": default_output_types,
                "default_outputs": {
                    name: get_stream_format_record(probe_model.output(name))
                    for name in output_names
                },
            }

        float_map = {name: hp.FormatType.FLOAT32 for name in output_names}
        float_run = run_variant("float32", hef_path, float_map, args, hp)
        result["variants"]["float32"] = float_run.record

        native_run: VariantRun | None = None
        candidates = native_candidate_maps(
            default_output_types,
            result["hef_contract"],
            hp.FormatType,
        )
        if not candidates:
            result["native_attempts"].append(
                {
                    "status": "unsupported",
                    "reason": "native HEF output type could not be resolved explicitly as UINT8 or UINT16",
                    "default_output_types": default_output_types,
                    "hef_output_types": {
                        row["name"]: row.get("device_native_format_type")
                        for row in result["hef_contract"].get("outputs", [])
                    },
                }
            )
        for candidate in candidates:
            attempt = {
                "requested_types": {
                    name: enum_name(value) for name, value in candidate.items()
                }
            }
            try:
                native_run = run_variant("native", hef_path, candidate, args, hp)
                attempt["status"] = "ok"
                result["native_attempts"].append(attempt)
                break
            except Exception as exc:
                attempt.update(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                result["native_attempts"].append(attempt)
                gc.collect()

        if native_run is None:
            result["status"] = "native_format_unsupported"
            result["error"] = "No native UINT8/UINT16 InferModel output configuration succeeded"
            exit_code = 2
        else:
            result["variants"]["native"] = native_run.record
            result["correctness"] = compare_outputs(float_run, native_run)
            result["comparison"] = {
                "native_vs_float32": ratio_record(float_run, native_run)
            }
            result["status"] = "ok"
            exit_code = 0
    except Exception as exc:
        result.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        exit_code = 1
    finally:
        result["finished_at"] = utc_now()
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(jsonable(result), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(jsonable(result), indent=2, sort_keys=True))
        print(f"RESULT_JSON={output_path}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
