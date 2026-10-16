#!/usr/bin/env python3
"""Render historical Native endpoint tables from compact report extracts.

No hardware runtime, tensor reconstruction, new timing or COCO evaluation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY = SCRIPT_DIR.parents[2]
INPUT = REPOSITORY / "results/supplementary-studies/native-endpoint-reconstruction/inputs/reference_extracts.json"
sys.path.insert(0, str(SCRIPT_DIR))
from report_statistics import percentile, summarize
from endpoint_history import render as render_history


def close(actual, expected, field):
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"Source aggregate mismatch for {field}: {actual} != {expected}")


def analyse(data):
    """Recompute only aggregates supported by retained repetition/image rows."""
    serial = data["serial_completion"]
    smoke = data["single_image_three_stage"]
    decoder = data["multi_image_decoder"]
    serial_rows = serial["repetition_records"]
    smoke_rows = smoke["repetitions"]
    images = decoder["rows"]
    if len(serial_rows) != 3 or len(smoke_rows) != 3 or len(images) != 32:
        raise ValueError("Historical cohort must contain 3 + 3 repetitions and 32 decoder images")
    if len({r["runtime_instance_id"] for r in serial_rows}) != 3:
        raise ValueError("Serial runtime repetitions are duplicated")
    if len({r["repetition"] for r in smoke_rows}) != 3 or len({r["image_id"] for r in images}) != 32:
        raise ValueError("Duplicate smoke repetition or decoder image")
    if smoke["corpus"]["selected_count"] != 1 or smoke["measurement_contract"]["images_cycled"] != 1:
        raise ValueError("The retained throughput smoke is a one-image observation")
    if not smoke["quality_oracle_outside_performance_timing"] or smoke["performance_hotloop_contains_crypto_hashing"]:
        raise ValueError("Unexpected verification/timing contract")
    if not decoder["measurement"]["raw_head_collection_is_not_a_performance_measurement"]:
        raise ValueError("Decoder collection must remain separate from pipeline throughput")
    for row in serial_rows:
        if not row["ok"] or not row["postprocess_completion_verified"] or row["completed_frames"] != 1000:
            raise ValueError("Incomplete serial completion repetition")
        close(1000 * row["completed_frames"] / row["makespan_ms"], row["fps_makespan"], "serial FPS")
    for row in smoke_rows:
        if row["return_code"] or not row["runtime_ok"] or not row["measurement_result_parity"]["all_exact"]:
            raise ValueError("Incomplete smoke repetition")
        metrics = row["metrics"]
        if abs(metrics["completed_fps"] / metrics["raw_fps"] - metrics["completed_raw_ratio"]) > 1e-9:
            raise ValueError("Smoke ratio exceeds the source report rounding tolerance")
    for row in images:
        if not all(row[k] for k in ("runtime_ok", "head_mapping_exact", "decode_exact", "final_exact", "parity_exact")):
            raise ValueError("Decoder parity failure in retained report")
        if row["oracle_content_sha256"] != row["fast_content_sha256"]:
            raise ValueError("Decoder detection identities differ")
        close(row["oracle_timing"]["median_ms"] / row["fast_timing"]["median_ms"], row["speedup"], "per-image decoder speedup")
    serial_fps = summarize([r["fps_makespan"] for r in serial_rows])
    raw_fps = summarize([r["metrics"]["raw_fps"] for r in smoke_rows])
    completed_fps = summarize([r["metrics"]["completed_fps"] for r in smoke_rows])
    ratios = summarize([r["metrics"]["completed_raw_ratio"] for r in smoke_rows])
    close(serial_fps["median"], serial["fps_makespan_median"], "serial median")
    for key, actual in (("raw_fps_median", raw_fps["median"]), ("completed_fps_median", completed_fps["median"]), ("completed_raw_ratio_median", ratios["median"])):
        close(actual, smoke["aggregate"][key], key)
    oracle = [r["oracle_timing"]["median_ms"] for r in images]
    fast = [r["fast_timing"]["median_ms"] for r in images]
    speedup = [r["speedup"] for r in images]
    decoder_summary = {
        "images": len(images), "exact_parity_images": sum(r["parity_exact"] for r in images),
        "oracle_median_across_image_medians_ms": statistics.median(oracle),
        "fast_median_across_image_medians_ms": statistics.median(fast),
        "fast_p95_across_image_medians_ms": percentile(fast, .95),
        "fast_max_image_median_ms": max(fast), "median_speedup": statistics.median(speedup),
    }
    for key in decoder_summary.keys() - {"images"}:
        close(decoder_summary[key], decoder["aggregate"][key], key)
    endpoints = [
        {"configuration": "Serial host completion", "images": 1, "repetitions": 3, "frames_per_repetition": 1000,
         "raw_fps_median": None, "completed_fps_median": serial_fps["median"], "completed_fps_min": serial_fps["min"], "completed_fps_max": serial_fps["max"], "completed_raw_ratio_median": None},
        {"configuration": "Three-stage one-image smoke", "images": 1, "repetitions": 3, "frames_per_repetition": 1000,
         "raw_fps_median": raw_fps["median"], "completed_fps_median": completed_fps["median"], "completed_fps_min": completed_fps["min"], "completed_fps_max": completed_fps["max"], "completed_raw_ratio_median": ratios["median"]},
    ]
    image_rows = [{"image_id": r["image_id"], "selection_bin": r["selection_bin"], "oracle_median_ms": r["oracle_timing"]["median_ms"], "fast_median_ms": r["fast_timing"]["median_ms"], "paired_speedup": r["speedup"], "parity_exact": r["parity_exact"], "detections": r["fast_detection_count"]} for r in images]
    summary = {"reproduction_level": data["reproduction_level"], "serial_completion_fps": serial_fps,
               "single_image_three_stage_raw_fps": raw_fps, "single_image_three_stage_completed_fps": completed_fps,
               "single_image_completed_raw_ratio": ratios, "multi_image_decoder": decoder_summary,
               "multi_image_pipeline_throughput_fps": None,
               "missing_throughput_reason": "No 32-image three-stage throughput report is included in these source extracts."}
    return endpoints, image_rows, decoder_summary, summary


def tex_escape(value):
    return str(value).replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("%", "\\%").replace("&", "\\&").replace("#", "\\#")


def write_table(output, name, rows, display, note):
    """Keep full precision in CSV; separately choose readable presentation columns."""
    with (output / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    headers = [label for _, label, _ in display]
    formatted = [["NA" if row[key] is None else fmt(row[key]) for key, _, fmt in display] for row in rows]
    md = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    md += ["| " + " | ".join(row) + " |" for row in formatted]
    (output / f"{name}.md").write_text("\n".join(md) + "\n\n" + note + "\n", encoding="utf-8")
    tex = ["% " + note, "\\begin{tabular}{" + "l" * len(headers) + "}", "\\hline", " & ".join(map(tex_escape, headers)) + r" \\", "\\hline"]
    tex += [" & ".join(map(tex_escape, row)) + r" \\" for row in formatted]
    tex += ["\\hline", "\\end{tabular}"]
    (output / f"{name}.tex").write_text("\n".join(tex) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Fresh or empty directory outside the repository")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        parser.error("--output must be outside the repository")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be fresh or empty")
    if REPOSITORY not in INPUT.resolve().parents:
        parser.error("Input must remain inside the repository")
    endpoints, images, decoder, summary = analyse(json.loads(INPUT.read_text(encoding="utf-8")))
    output.mkdir(parents=True, exist_ok=True)
    integer = lambda v: f"{v:.0f}"
    decimal = lambda v: f"{v:.3f}"
    write_table(output, "endpoint_comparison", endpoints,
                [("configuration", "Configuration", str), ("images", "Images", str), ("raw_fps_median", "Raw FPS", integer), ("completed_fps_median", "Completed FPS", integer), ("completed_raw_ratio_median", "Completed/raw", lambda v: f"{v:.6f}")],
                "Medians of three fresh runtime repetitions. NA means no separately observed raw endpoint. Both rows use one image; execution/preprocessing contracts differ, so this is not a controlled speedup estimate. Full-precision CSV includes observed repeat minima/maxima, not confidence intervals.")
    write_table(output, "decoder_images", images,
                [("image_id", "Image ID", str), ("oracle_median_ms", "Oracle (ms)", decimal), ("fast_median_ms", "Sparse (ms)", decimal), ("paired_speedup", "Paired ratio", decimal), ("parity_exact", "Exact", str)],
                "Each timing is the median of 30 local decoder iterations after five warm-ups; these are decoder timings, not pipeline FPS or COCO quality scores.")
    write_table(output, "decoder_summary", [decoder],
                [("images", "Images", str), ("exact_parity_images", "Exact", str), ("oracle_median_across_image_medians_ms", "Oracle (ms)", decimal), ("fast_median_across_image_medians_ms", "Sparse (ms)", decimal), ("median_speedup", "Paired ratio", decimal)],
                "Median across the 32 image medians; the speedup is the median of paired per-image ratios, not the ratio of the two aggregate medians. P95 and maximum in CSV describe image medians, not per-frame latency tails.")
    pipeline = render_history(output, INPUT.parent, write_table, close)
    summary["multi_image_pipeline_throughput_fps"] = pipeline["completed_fps"]["median"]
    summary["multi_image_pipeline"] = pipeline
    summary.pop("missing_throughput_reason")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("PASS: 3 serial, 3 one-image smoke and 3 32-image pipeline repetitions; 32 decoder images; original aggregates verified; 19 table/JSON exports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
