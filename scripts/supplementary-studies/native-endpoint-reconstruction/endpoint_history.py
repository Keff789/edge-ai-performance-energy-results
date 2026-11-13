"""Supplement existing endpoint tables with archived canary and reported summaries."""
import csv
import json
from report_statistics import summarize


def analyse_pipeline(data, close):
    contract = data["measurement_contract"]
    corpus = data["corpus"]
    rows = data["repetitions"]
    if (corpus["selected_count"], contract["images_cycled"], len(rows)) != (32, 32, 3):
        raise ValueError("Expected the three-repetition, 32-image pipeline canary")
    ids = {r["image_id"] for r in corpus["items"]}
    if len(ids) != 32 or len({r["repetition"] for r in rows}) != 3:
        raise ValueError("Duplicate image or repetition")
    if not data["quality_oracle_outside_performance_timing"] or data["performance_hotloop_contains_crypto_hashing"]:
        raise ValueError("Verification must remain outside performance timing")
    if not data["source_ok"] or data["status"] != "PASS_THREE_STAGE_TARGET_MET":
        raise ValueError("The archived canary is not valid")
    postflight = data["postflight_quality_oracle"]
    if (postflight["verified_images"], postflight["exact_images"]) != (32, 32) or not postflight["all_exact"]:
        raise ValueError("Invalid separate postflight")
    if postflight["performance_interpretation"] != "forbidden_verification_only" or postflight["return_code"]:
        raise ValueError("Postflight cannot supply timing observations")
    if (contract["frames_per_repetition"], contract["warmup_frames_fully_drained"]) != (1000, 100):
        raise ValueError("Unexpected work count")
    for row in rows:
        parity = row["measurement_result_parity"]
        metrics = row["metrics"]
        if row["return_code"] or not row["runtime_ok"] or row["callback_errors"] or metrics["callback_failures"]:
            raise ValueError("Invalid timed repetition")
        if not parity["all_exact"] or parity["exact_images"] != 32 or {r["image_id"] for r in parity["rows"]} != ids:
            raise ValueError("Timed output parity does not cover the fixed corpus")
        if not all(r["exact"] and r["actual_detection_count"] == r["expected_detection_count"] for r in parity["rows"]):
            raise ValueError("Per-image parity failure")
        if sum(row["measured_seen_counts"].values()) != 1000:
            raise ValueError("Incomplete measured work")
        if abs(metrics["completed_fps"] / metrics["raw_fps"] - metrics["completed_raw_ratio"]) > 1e-9:
            raise ValueError("Ratio disagrees with rounded source rates")
    summary = {}
    for key, source_key in [("raw_fps", "raw_fps"), ("completed_fps", "completed_detection_fps"),
                             ("completed_raw_ratio", "completed_raw_ratio")]:
        stats = summarize([r["metrics"][key] for r in rows])
        for field, value in stats.items():
            close(value, data["aggregate"][source_key][field], source_key + "/" + field)
        summary[key] = stats
    metrics = [{"repetition": r["repetition"], **r["metrics"], "images": 32,
                "frames": 1000, "exact_parity_images": r["measurement_result_parity"]["exact_images"]} for r in rows]
    return metrics, summary


def render(output, inputs, write_table, close):
    """Read only supplied inputs; all calculations/tables stay in output."""
    paths = [inputs / name for name in ("pipeline_canary_extract.json", "reported_execution_paths.csv", "reported_adapter_checks.csv")]
    if any(not p.resolve().is_relative_to(inputs.resolve()) for p in paths):
        raise ValueError("Endpoint history inputs must stay within the supplied input directory")
    metrics, summary = analyse_pipeline(json.loads(paths[0].read_text()), close)
    decimal = lambda v: f"{float(v):.3f}"
    integer = lambda v: f"{float(v):.0f}"
    write_table(output, "pipeline_canary_repetitions", metrics,
                [("repetition", "Rep", str), ("p1_stage_mean_ms", "P1 ms", decimal),
                 ("p2_stage_mean_ms", "P2 ms", decimal), ("post_mean_ms", "Post ms", decimal),
                 ("raw_fps", "Raw FPS", integer), ("completed_fps", "Completed FPS", integer),
                 ("completed_raw_ratio", "Completed/raw", lambda v: f"{v:.6f}")],
                "Three repetitions of 1,000 measured completions cycling 32 images, after 100 drained warm-ups. "
                "P1/P2/Post values are means within each repetition; observed throughput includes pipeline backpressure. "
                "Raw and completed FPS remain distinct at full precision in CSV. All 32 images pass recorded parity; "
                "the separate postflight is outside timing. These are existing measurements, not a new run.")
    for path, name, display, note in [
        (paths[1], "reported_execution_paths",
         [("execution", "Execution", str), ("p1_mean_ms", "P1 ms", decimal),
          ("p2_mean_ms", "P2 ms", decimal), ("post_mean_ms", "Post ms", decimal), ("fps", "FPS", integer)],
         "Reported manuscript values at their original precision; no underlying repetitions are reconstructed. "
         "For the published pipeline Post is included in P2; the original replay does not separate it; "
         "the current-artifact replay does not time it. NA in Post therefore does not mean zero cost. "
         "Endpoints and input/execution paths differ; these rows do not form a controlled speedup sequence."),
        (paths[2], "reported_adapter_checks",
         [("case", "Case", str), ("p2_rate_per_s", "P2 / s", integer),
          ("completed_rate_per_s", "Completed / s", integer), ("validated_count", "Checks", str)],
         "Reported manuscript summaries. YOLOv7 and YOLO26s validate 32/32 pipeline images, YOLO11l validates "
         "16/16 ORT replay images without accelerator timing, and the last two rows count 300 producer work units. "
         "Producer work units are not complete detector tasks. Source endpoint and validation status remain in CSV.")]:
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            for key in row:
                if row[key] == "":
                    row[key] = None
        write_table(output, name, rows, display, note)
    return summary
