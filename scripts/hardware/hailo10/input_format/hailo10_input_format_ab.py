#!/usr/bin/env python3
"""Isolated Hailo-10H host-input format A/B benchmark.

Variant A supplies FLOAT32 host inputs. Variant B supplies the HEF-native
UINT8/UINT16 inputs. Both variants request the same native output type and use
exactly the same quantized device values. Every submitted InferModel job is
waited for before the next one is submitted: max outstanding jobs is one.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCRIPT_VERSION = "1.0"
NATIVE_TYPE_NAMES = {"UINT8", "UINT16"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if name:
        return str(name).upper()
    return str(value).rsplit(".", 1)[-1].upper()


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
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
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
    rows: list[dict[str, str]] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name") or ""
        if "hailo" in name.lower():
            rows.append({"name": name, "version": distribution.version})
    return sorted(rows, key=lambda row: row["name"].lower())


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


def get_quant_infos(obj: Any) -> list[Any]:
    qinfos = getattr(obj, "quant_infos", None)
    if qinfos is not None:
        return list(qinfos)
    single = getattr(obj, "quant_info", None)
    return [] if single is None else [single]


def shape_record(value: Any) -> list[int] | dict[str, int] | str:
    if value is None:
        return []
    try:
        return [int(item) for item in value]
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
    return (
        sorted_values[lower] * (1.0 - weight)
        + sorted_values[upper] * weight
    )


def duration_summary(samples_ms: list[float]) -> dict[str, Any]:
    ordered = sorted(samples_ms)
    return {
        "samples": len(samples_ms),
        "mean_ms": statistics.fmean(samples_ms),
        "median_ms": statistics.median(samples_ms),
        "stdev_ms": statistics.pstdev(samples_ms),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "p95_ms": percentile(ordered, 0.95),
    }


def numpy_dtype_for_type(format_type: Any) -> np.dtype[Any]:
    mapping = {
        "UINT8": np.dtype(np.uint8),
        "UINT16": np.dtype(np.uint16),
        "FLOAT32": np.dtype(np.float32),
    }
    type_name = enum_name(format_type)
    if type_name not in mapping:
        raise RuntimeError(f"unsupported host format type: {type_name}")
    return mapping[type_name]


def info_record(info: Any) -> dict[str, Any]:
    fmt = getattr(info, "format", None)
    return {
        "name": str(getattr(info, "name", "")),
        "shape": shape_record(getattr(info, "shape", ())),
        "hw_shape": shape_record(getattr(info, "hw_shape", ())),
        "format_type": enum_name(getattr(fmt, "type", "UNKNOWN")),
        "format_order": enum_name(getattr(fmt, "order", "UNKNOWN")),
        "quant_infos": [quant_info_record(qinfo) for qinfo in get_quant_infos(info)],
    }


def direction_contract(
    hef: Any,
    network_group: str,
    direction: str,
) -> list[dict[str, Any]]:
    if direction == "input":
        vstream_infos = list(hef.get_input_vstream_infos())
        low_level_infos = list(hef.get_input_stream_infos(network_group))
    elif direction == "output":
        vstream_infos = list(hef.get_output_vstream_infos())
        low_level_infos = list(hef.get_output_stream_infos(network_group))
    else:
        raise ValueError(f"unknown direction: {direction}")

    low_level_by_name = {
        str(getattr(info, "name", "")): info for info in low_level_infos
    }
    records: list[dict[str, Any]] = []
    for vstream_info in vstream_infos:
        record = info_record(vstream_info)
        try:
            stream_names = [
                str(value)
                for value in hef.get_stream_names_from_vstream_name(
                    record["name"], network_group
                )
            ]
        except Exception as exc:
            stream_names = []
            record["native_stream_resolution_error"] = (
                f"{type(exc).__name__}: {exc}"
            )
        if not stream_names and record["name"] in low_level_by_name:
            stream_names = [record["name"]]

        native_streams = [
            info_record(low_level_by_name[name])
            for name in stream_names
            if name in low_level_by_name
        ]
        native_types = {
            row["format_type"]
            for row in native_streams
            if row["format_type"] in NATIVE_TYPE_NAMES
        }
        record["underlying_stream_names"] = stream_names
        record["underlying_streams"] = native_streams
        record["device_native_format_type"] = (
            next(iter(native_types))
            if len(native_streams) == 1 and len(native_types) == 1
            else None
        )
        records.append(record)
    return records


def inspect_hef(hef_path: Path, hp: Any) -> dict[str, Any]:
    hef = hp.HEF(str(hef_path))
    network_groups = [str(value) for value in hef.get_network_group_names()]
    if len(network_groups) != 1:
        raise RuntimeError(
            f"expected exactly one HEF network group, got {network_groups}"
        )
    network_group = network_groups[0]
    return {
        "network_groups": network_groups,
        "selected_network_group": network_group,
        "inputs": direction_contract(hef, network_group, "input"),
        "outputs": direction_contract(hef, network_group, "output"),
    }


def native_type_map(
    records: list[dict[str, Any]],
    expected_names: list[str],
    FormatType: Any,
    direction: str,
) -> dict[str, Any]:
    by_name = {str(record["name"]): record for record in records}
    result: dict[str, Any] = {}
    for name in expected_names:
        type_name = by_name.get(name, {}).get("device_native_format_type")
        if type_name not in NATIVE_TYPE_NAMES:
            raise RuntimeError(
                f"{direction} {name!r} has no unambiguous native UINT8/UINT16 type"
            )
        if not hasattr(FormatType, type_name):
            raise RuntimeError(
                f"HailoRT FormatType lacks required native type {type_name}"
            )
        result[name] = getattr(FormatType, type_name)
    return result


def quantize_reference(
    values: np.ndarray,
    scale: float,
    zero_point: float,
    dtype: np.dtype[Any],
) -> np.ndarray:
    limits = np.iinfo(dtype)
    quantized = np.rint(values / np.float32(scale) + np.float32(zero_point))
    quantized = np.clip(quantized, limits.min, limits.max)
    return np.ascontiguousarray(quantized.astype(dtype))


def hailort_transform_utils(hp: Any) -> Any:
    transform = getattr(hp, "HailoRTTransformUtils", None)
    if transform is not None:
        return transform
    try:
        from hailo_platform.pyhailort.pyhailort import HailoRTTransformUtils
    except ImportError as exc:
        raise RuntimeError(
            "HailoRTTransformUtils is required to prove equivalent device inputs"
        ) from exc
    return HailoRTTransformUtils


def prepare_equivalent_inputs(
    infer_model: Any,
    native_input_types: dict[str, Any],
    seed: int,
    quantization_repetitions: int,
    hp: Any,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    transform = hailort_transform_utils(hp)
    float_inputs: dict[str, np.ndarray] = {}
    native_inputs: dict[str, np.ndarray] = {}
    records: dict[str, Any] = {}

    for name in infer_model.input_names:
        stream = infer_model.input(name)
        qinfos = list(stream.quant_infos)
        if len(qinfos) != 1:
            raise RuntimeError(
                f"input {name!r}: expected exactly one quant_info, got {len(qinfos)}"
            )
        qinfo = qinfos[0]
        scale = numeric_attr(qinfo, ("qp_scale", "scale"))
        zero_point = numeric_attr(qinfo, ("qp_zp", "zero_point", "zp"))
        if scale is None or scale <= 0.0 or zero_point is None:
            raise RuntimeError(
                f"input {name!r}: invalid quantization parameters "
                f"{quant_info_record(qinfo)}"
            )

        dtype = numpy_dtype_for_type(native_input_types[name])
        limits = np.iinfo(dtype)
        shape = tuple(int(value) for value in stream.shape)
        native = rng.integers(
            limits.min,
            int(limits.max) + 1,
            size=shape,
            dtype=dtype,
        )
        native = np.ascontiguousarray(native)
        floating = np.empty(native.shape, dtype=np.float32, order="C")
        transform.dequantize_output_buffer(
            native,
            floating,
            int(native.size),
            qinfo,
        )

        requantized = np.empty_like(native)
        transform.quantize_input_buffer(
            floating,
            requantized,
            int(floating.size),
            qinfo,
        )
        if not np.array_equal(native, requantized):
            differing = int(np.count_nonzero(native != requantized))
            raise RuntimeError(
                f"input {name!r}: equivalent-input construction failed for "
                f"{differing} element(s)"
            )

        quantization_samples_ms: list[float] = []
        measured = np.empty_like(native)
        for _ in range(quantization_repetitions):
            started = time.perf_counter_ns()
            transform.quantize_input_buffer(
                floating,
                measured,
                int(floating.size),
                qinfo,
            )
            quantization_samples_ms.append(
                (time.perf_counter_ns() - started) / 1_000_000.0
            )
        if not np.array_equal(native, measured):
            raise RuntimeError(
                f"input {name!r}: timed reference quantization changed values"
            )

        float_inputs[name] = floating
        native_inputs[name] = native
        records[name] = {
            "shape": list(shape),
            "native_format_type": enum_name(native_input_types[name]),
            "native_numpy_dtype": str(native.dtype),
            "float_numpy_dtype": str(floating.dtype),
            "native_bytes_per_frame": int(native.nbytes),
            "float32_bytes_per_frame": int(floating.nbytes),
            "host_byte_ratio_float32_over_native": floating.nbytes / native.nbytes,
            "quant_info": quant_info_record(qinfo),
            "equivalent_device_values": True,
            "reference_float32_to_native_quantization": {
                **duration_summary(quantization_samples_ms),
                "method": "HailoRTTransformUtils.quantize_input_buffer",
                "excluded_from_inference_timing": True,
                "output_exactly_matches_native_template": True,
            },
            "manual_formula_roundtrip_exact": bool(
                np.array_equal(
                    native,
                    quantize_reference(floating, scale, zero_point, dtype),
                )
            ),
        }

    return float_inputs, native_inputs, records


def stream_record(stream: Any) -> dict[str, Any]:
    return {
        "shape": [int(value) for value in stream.shape],
        "type": enum_name(stream.format.type),
        "order": enum_name(stream.format.order),
        "is_nms": bool(stream.is_nms),
        "quant_infos": [
            quant_info_record(qinfo) for qinfo in list(stream.quant_infos)
        ],
    }


def run_one_job(
    configured: Any,
    bindings: Any,
    timeout_ms: int,
) -> tuple[float, float, float]:
    total_started = time.perf_counter_ns()
    ready_started = total_started
    configured.wait_for_async_ready(timeout_ms=timeout_ms, frames_count=1)
    ready_finished = time.perf_counter_ns()
    job = configured.run_async([bindings])
    # The next submission is impossible until this wait returns. This is the
    # explicit single-outstanding-job policy required by the experiment.
    job.wait(timeout_ms)
    finished = time.perf_counter_ns()
    return (
        (ready_finished - ready_started) / 1_000_000.0,
        (finished - ready_finished) / 1_000_000.0,
        (finished - total_started) / 1_000_000.0,
    )


def run_variant(
    variant_name: str,
    hef_path: Path,
    input_type_map: dict[str, Any],
    input_templates: dict[str, np.ndarray],
    output_type_map: dict[str, Any],
    args: argparse.Namespace,
    hp: Any,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    started_at = utc_now()
    with hp.VDevice() as vdevice:
        infer_model = vdevice.create_infer_model(str(hef_path))
        for name in infer_model.input_names:
            infer_model.input(name).set_format_type(input_type_map[name])
        for name in infer_model.output_names:
            infer_model.output(name).set_format_type(output_type_map[name])

        input_records = {
            name: {
                **stream_record(infer_model.input(name)),
                "requested_type": enum_name(input_type_map[name]),
                "numpy_dtype": str(input_templates[name].dtype),
                "bytes_per_frame": int(input_templates[name].nbytes),
            }
            for name in infer_model.input_names
        }
        output_records = {
            name: stream_record(infer_model.output(name))
            for name in infer_model.output_names
        }

        with infer_model.configure() as configured:
            async_queue_size = int(configured.get_async_queue_size())
            input_buffers = {
                name: np.ascontiguousarray(input_templates[name].copy())
                for name in infer_model.input_names
            }
            output_buffers: dict[str, np.ndarray] = {}
            for name in infer_model.output_names:
                stream = infer_model.output(name)
                if stream.is_nms:
                    raise RuntimeError(
                        "NMS outputs are unsupported; use a Part1 tensor-boundary HEF"
                    )
                output_buffers[name] = np.empty(
                    tuple(int(value) for value in stream.shape),
                    dtype=numpy_dtype_for_type(output_type_map[name]),
                    order="C",
                )
            bindings = configured.create_bindings(
                input_buffers=input_buffers,
                output_buffers=output_buffers,
            )

            for _ in range(args.warmup):
                run_one_job(configured, bindings, args.timeout_ms)

            latency_samples_ms: list[float] = []
            ready_samples_ms: list[float] = []
            submit_to_complete_samples_ms: list[float] = []
            stream_started = time.perf_counter_ns()
            for _ in range(args.frames):
                ready_ms, submit_ms, total_ms = run_one_job(
                    configured, bindings, args.timeout_ms
                )
                ready_samples_ms.append(ready_ms)
                submit_to_complete_samples_ms.append(submit_ms)
                latency_samples_ms.append(total_ms)
            stream_seconds = (
                time.perf_counter_ns() - stream_started
            ) / 1_000_000_000.0
            captured_outputs = {
                name: np.ascontiguousarray(buffer.copy())
                for name, buffer in output_buffers.items()
            }

    record = {
        "status": "ok",
        "variant": variant_name,
        "started_at": started_at,
        "finished_at": utc_now(),
        "inputs": input_records,
        "outputs": {
            name: {
                **output_records[name],
                "requested_type": enum_name(output_type_map[name]),
                "numpy_dtype": str(captured_outputs[name].dtype),
                "bytes_per_frame": int(captured_outputs[name].nbytes),
            }
            for name in captured_outputs
        },
        "latency": duration_summary(latency_samples_ms),
        "wait_for_ready": duration_summary(ready_samples_ms),
        "submit_to_complete": duration_summary(
            submit_to_complete_samples_ms
        ),
        "single_outstanding_job_stream": {
            "frames": args.frames,
            "elapsed_s": stream_seconds,
            "fps": args.frames / stream_seconds,
            "max_outstanding_jobs": 1,
            "internal_parallelism_enabled": False,
            "available_async_queue_size_not_used": async_queue_size,
        },
        "total_input_bytes_per_frame": sum(
            int(buffer.nbytes) for buffer in input_templates.values()
        ),
        "total_output_bytes_per_frame": sum(
            int(buffer.nbytes) for buffer in captured_outputs.values()
        ),
    }
    return record, captured_outputs


def compare_outputs(
    float_outputs: dict[str, np.ndarray],
    native_outputs: dict[str, np.ndarray],
) -> dict[str, Any]:
    if set(float_outputs) != set(native_outputs):
        return {
            "status": "not_comparable",
            "reason": "output name sets differ",
            "float32_input_outputs": sorted(float_outputs),
            "native_input_outputs": sorted(native_outputs),
        }

    records: dict[str, Any] = {}
    all_exact = True
    for name in sorted(float_outputs):
        reference = float_outputs[name]
        candidate = native_outputs[name]
        if reference.shape != candidate.shape or reference.dtype != candidate.dtype:
            records[name] = {
                "status": "not_comparable",
                "float32_input_shape": list(reference.shape),
                "native_input_shape": list(candidate.shape),
                "float32_input_dtype": str(reference.dtype),
                "native_input_dtype": str(candidate.dtype),
            }
            all_exact = False
            continue
        delta = np.abs(
            reference.astype(np.int64) - candidate.astype(np.int64)
        )
        differing = int(np.count_nonzero(delta))
        exact = differing == 0
        all_exact = all_exact and exact
        records[name] = {
            "status": "ok" if exact else "mismatch",
            "elements": int(delta.size),
            "differing_elements": differing,
            "max_abs_quantized_units": int(np.max(delta)) if delta.size else 0,
            "mean_abs_quantized_units": float(np.mean(delta)) if delta.size else 0.0,
            "exactly_equal": exact,
        }
    return {
        "status": "exact_match" if all_exact else "mismatch",
        "all_outputs_exactly_equal": all_exact,
        "outputs": records,
    }


def comparison_record(
    float_record: dict[str, Any],
    native_record: dict[str, Any],
    equivalent_input_records: dict[str, Any],
) -> dict[str, Any]:
    float_latency = float(float_record["latency"]["mean_ms"])
    native_latency = float(native_record["latency"]["mean_ms"])
    float_fps = float(
        float_record["single_outstanding_job_stream"]["fps"]
    )
    native_fps = float(
        native_record["single_outstanding_job_stream"]["fps"]
    )
    float_bytes = int(float_record["total_input_bytes_per_frame"])
    native_bytes = int(native_record["total_input_bytes_per_frame"])
    external_quantization_ms = sum(
        float(row["reference_float32_to_native_quantization"]["mean_ms"])
        for row in equivalent_input_records.values()
    )
    native_with_external_quantization = native_latency + external_quantization_ms
    return {
        "native_input_vs_float32_input": {
            "latency_speedup_float32_over_native": float_latency / native_latency,
            "latency_reduction_percent": 100.0 * (1.0 - native_latency / float_latency),
            "single_job_fps_speedup_native_over_float32": native_fps / float_fps,
            "single_job_fps_increase_percent": 100.0 * (native_fps / float_fps - 1.0),
            "host_input_byte_reduction_ratio": float_bytes / native_bytes,
            "external_reference_quantization_mean_ms": external_quantization_ms,
            "native_latency_plus_external_quantization_mean_ms": (
                native_with_external_quantization
            ),
            "native_plus_external_quantization_reduction_percent": (
                100.0
                * (1.0 - native_with_external_quantization / float_latency)
            ),
            "note": (
                "external reference quantization is reported separately and is "
                "not included in either InferModel timing"
            ),
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hef", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=27914)
    parser.add_argument("--quantization-repetitions", type=int, default=50)
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    for name in ("frames", "timeout_ms", "quantization_repetitions"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be > 0")
    return args


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {
        "schema": "hailo10_infermodel_input_format_ab/v1",
        "script_version": SCRIPT_VERSION,
        "started_at": utc_now(),
        "status": "running",
        "test_scope": "runtime_microbenchmark_not_scientific_claim",
        "hef": str(args.hef.expanduser().resolve()),
        "parameters": {
            "warmup": args.warmup,
            "frames": args.frames,
            "timeout_ms": args.timeout_ms,
            "seed": args.seed,
            "quantization_repetitions": args.quantization_repetitions,
            "output_host_format": "HEF_NATIVE_UINT8_OR_UINT16_FOR_BOTH_VARIANTS",
            "variant_order": ["float32_input", "native_input"],
            "max_outstanding_jobs": 1,
            "internal_infermodel_parallelism": False,
            "power_mode_changed": False,
            "hardware_power_switching_performed": False,
            "product_modified": False,
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

        hef_contract = inspect_hef(hef_path, hp)
        result["hef_contract"] = hef_contract

        with hp.VDevice() as probe_device:
            probe_model = probe_device.create_infer_model(str(hef_path))
            input_names = [str(value) for value in probe_model.input_names]
            output_names = [str(value) for value in probe_model.output_names]
            if len(input_names) != 1 or len(output_names) != 1:
                raise RuntimeError(
                    "this diagnostic requires exactly one input and one output; "
                    f"got inputs={input_names}, outputs={output_names}"
                )
            native_input_types = native_type_map(
                hef_contract["inputs"], input_names, hp.FormatType, "input"
            )
            native_output_types = native_type_map(
                hef_contract["outputs"], output_names, hp.FormatType, "output"
            )
            float_inputs, native_inputs, equivalent_inputs = (
                prepare_equivalent_inputs(
                    probe_model,
                    native_input_types,
                    args.seed,
                    args.quantization_repetitions,
                    hp,
                )
            )
            result["infermodel_probe"] = {
                "device_ids": [
                    str(value) for value in probe_device.get_physical_devices_ids()
                ],
                "input_names": input_names,
                "output_names": output_names,
                "default_inputs": {
                    name: stream_record(probe_model.input(name))
                    for name in input_names
                },
                "default_outputs": {
                    name: stream_record(probe_model.output(name))
                    for name in output_names
                },
                "resolved_native_input_types": {
                    name: enum_name(value)
                    for name, value in native_input_types.items()
                },
                "resolved_native_output_types": {
                    name: enum_name(value)
                    for name, value in native_output_types.items()
                },
            }

        result["equivalent_inputs"] = equivalent_inputs
        float_input_types = {
            name: hp.FormatType.FLOAT32 for name in input_names
        }

        float_record, float_outputs = run_variant(
            "float32_input",
            hef_path,
            float_input_types,
            float_inputs,
            native_output_types,
            args,
            hp,
        )
        result["variants"]["float32_input"] = float_record

        native_record, native_outputs = run_variant(
            "native_input",
            hef_path,
            native_input_types,
            native_inputs,
            native_output_types,
            args,
            hp,
        )
        result["variants"]["native_input"] = native_record

        correctness = compare_outputs(float_outputs, native_outputs)
        result["correctness"] = correctness
        result["comparison"] = comparison_record(
            float_record, native_record, equivalent_inputs
        )
        if correctness.get("all_outputs_exactly_equal") is True:
            result["status"] = "ok"
            exit_code = 0
        else:
            result["status"] = "output_mismatch"
            result["error"] = (
                "The two host-input formats did not produce identical native outputs"
            )
            exit_code = 3
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
