"""Deterministic transcription and arithmetic checks of the supplied report only.

This is an analysis intermediate, not a revalidation of unavailable raw data.
"""
from pathlib import Path
from decimal import Decimal, getcontext
import csv
import hashlib
import json
import statistics
import argparse

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "SOURCE_REPORT.txt"


def main():
    getcontext().prec = 32
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    OUTPUT = parser.parse_args().output.resolve()
    repository = ROOT.parents[2]
    if OUTPUT == repository or repository in OUTPUT.parents:
        parser.error("--output must be outside the repository")
    if OUTPUT.exists() and (not OUTPUT.is_dir() or any(OUTPUT.iterdir())):
        parser.error("--output must be a fresh or empty directory")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = SOURCE.read_bytes()
    lines = payload.decode("utf-8").splitlines()
    source_sha = hashlib.sha256(payload).hexdigest()
    D = Decimal
    HALF_UNIT = D("0.0000005")


    def table(header):
        start = next(i for i, line in enumerate(lines) if line == header)
        result = []
        for i in range(start + 2, len(lines)):
            if not lines[i].startswith("|"):
                break
            result.append((i + 1, [s.strip() for s in lines[i].strip("|").split("|")]))
        return start + 1, result


    def rounded_ratio_check(numerator, denominator, reported):
        n, d, r = map(D, (numerator, denominator, reported))
        # Input and reported quotient are each printed to six decimal places.
        lower = (n - HALF_UNIT) / (d + HALF_UNIT)
        upper = (n + HALF_UNIT) / (d - HALF_UNIT)
        return {
            "recomputed_from_displayed_values": str(n / d),
            "reported": reported,
            "absolute_difference": str(abs(n / d - r)),
            "compatible_with_printed_precision": lower <= r + HALF_UNIT and upper >= r - HALF_UNIT,
        }


    split_header, split_rows = table("| Setup | Cut | FPS 1 | FPS 2 | FPS 3 | Median FPS | / TRT Full | / Accelerator Full |")
    full_header, full_rows = table("| Setup | Full-Pfad | FPS 1 | FPS 2 | FPS 3 | Median | Qualität |")
    history_header, history_rows = table("| Setup | Cut | Historischer Median | Neuer Median | Quotient neu / historisch |")
    quality_line = next(i + 1 for i, s in enumerate(lines) if s.startswith("Alle neuen Splitfälle erhalten `reference_close`."))
    assert len(split_rows) == 9 and len(full_rows) == 6 and len(history_rows) == 9

    fulls = {(r[0], r[1]): r for _, r in full_rows}
    trt = {setup: fulls[(setup, "native_full_tensorrt")][5] for setup in ("H8", "H10", "DeepX")}
    vendor_backend = {"H8": "native_full_hailo8", "H10": "native_full_hailo10h", "DeepX": "native_full_deepx"}
    split_backend = {"H8": "hailo8_to_trt", "H10": "hailo10h_to_trt", "DeepX": "deepx_to_trt"}
    checks = {"median_checks": [], "split_ratio_checks": [], "historical_ratio_checks": []}
    records = []


    def base(setup, kind, backend, case, fps, median, quality, lineno):
        median_ok = statistics.median(map(D, fps)) == D(median)
        identifier = f"{setup}__{backend}__{case}"
        checks["median_checks"].append({"record_id": identifier, "pass": median_ok})
        assert median_ok
        return {
            "record_id": identifier,
            "model": "yolov7_paper",
            "setup": setup,
            "configuration_type": kind,
            "backend": backend,
            "case": case,
            "fps_1": fps[0], "fps_2": fps[1], "fps_3": fps[2], "fps_median": median,
            "quality_status": quality,
            "quality_status_basis": "reported_label_not_independently_revalidated",
            "energy_j_per_task": "NA",
            "energy_status": "not_measured",
            "fastest_full_backend": "native_full_tensorrt",
            "fastest_full_fps_median": trt[setup],
            "speedup_vs_fastest_full_reported": "NA",
            "speedup_vs_fastest_full_recomputed": "NA",
            "speedup_vs_accelerator_full_reported": "NA",
            "speedup_vs_accelerator_full_recomputed": "NA",
            "performance_cohort": "new_split_three_process_repeats_reported" if kind == "split" else "reused_optimized_full_prior_performance_task_reported",
            "repetitions_reported": 3,
            "warmup_per_repeat_reported": 100,
            "completed_tasks_per_repeat_reported": 1000,
            "separate_processes_reported": "true",
            "measurement_date": "not_specified_in_supplied_report",
            "source_file": SOURCE.name,
            "source_sha256": source_sha,
            "source_line": lineno,
            "quality_source_line": quality_line if kind == "split" else lineno,
            "verification_scope": "report_transcription_and_arithmetic_only",
        }


    for lineno, r in full_rows:
        setup, backend, f1, f2, f3, median, quality = r
        records.append(base(setup, "full", backend, "full", [f1, f2, f3], median, quality, lineno))

    for lineno, r in split_rows:
        setup, cut, f1, f2, f3, median, rt, ra = r
        record = base(setup, "split", split_backend[setup], cut, [f1, f2, f3], median, "reference_close", lineno)
        for label, denominator, reported in (
            ("fastest_full", trt[setup], rt),
            ("accelerator_full", fulls[(setup, vendor_backend[setup])][5], ra),
        ):
            check = rounded_ratio_check(median, denominator, reported)
            assert check["compatible_with_printed_precision"]
            checks["split_ratio_checks"].append({"record_id": record["record_id"], "reference": label, **check})
            record[f"speedup_vs_{label}_reported"] = reported
            record[f"speedup_vs_{label}_recomputed"] = check["recomputed_from_displayed_values"]
        records.append(record)

    for lineno, r in history_rows:
        setup, cut, old, new, ratio = r
        check = rounded_ratio_check(new, old, ratio)
        assert check["compatible_with_printed_precision"]
        checks["historical_ratio_checks"].append({"setup": setup, "case": cut, "source_line": lineno, **check})

    setup_order = {"H8": 0, "H10": 1, "DeepX": 2}
    records.sort(key=lambda r: (setup_order[r["setup"]], r["configuration_type"] != "full", r["backend"], r["case"]))
    assert len(records) == len({r["record_id"] for r in records}) == 15
    assert all(D(trt[setup]) > D(fulls[(setup, vendor_backend[setup])][5]) for setup in setup_order)
    csv_path = OUTPUT / "reported_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    provenance = {
        "schema": "report_only_yolov7_performance_transcription_v1",
        "source": {"path": SOURCE.name, "sha256": source_sha, "bytes": len(payload)},
        "output": {"path": csv_path.name, "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "records": 15},
        "extraction_script": {"path": Path(__file__).name, "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "evidence_scope": "Only the supplied Markdown report was parsed. Its newly referenced review ZIP, raw reports, code and telemetry were not available for this extraction and were not independently verified.",
        "raw_data_verified": False,
        "quality_labels_verified": False,
        "reported_precision": "FPS and ratios transcribed at six decimals exactly as printed. Recomputed ratios use only displayed values and do not recover full-precision source data.",
        "measurement_date_note": "No absolute measurement date appears in the supplied report. Directory/upload date is not substituted for a measurement date.",
        "source_tables": {"split_header_line": split_header, "full_header_line": full_header, "historical_header_line": history_header, "split_quality_statement_line": quality_line},
        "reported_cohorts": {"new_split_configurations": 9, "new_split_repeats": 27, "reused_full_configurations": 6, "reused_full_repeats": 18, "separate_current_trt_controls": 3, "controls_included_in_repetition_triples": False},
        "energy": {"all_15_current_variants": "not_measured", "csv_missing_value": "NA", "historical_energy_not_joined": True},
        "arithmetic_checks": checks,
        "descriptive_counts_from_displayed_medians": {"splits_above_fastest_full": sum(D(r["speedup_vs_fastest_full_reported"]) > 1 for r in records if r["configuration_type"] == "split"), "split_configurations": 9, "statistical_superiority_claimed": False},
    }
    table_lines = [
        "# Historical YOLOv7 completed-task performance",
        "",
        "Reported three-process repeat medians; 100 warmups and 1,000 completed tasks per repeat. "
        "Six Full alternatives were reused from the earlier performance task. "
        "Three separate Full controls are not included. FPS are rounded here; the CSV retains every reported decimal and repeat.",
        "",
        "| Setup | Path | Median FPS | / Fastest Full | / Accelerator Full | Reported quality | Energy |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for record in records:
        if record["configuration_type"] == "full":
            path = "TensorRT Full" if record["backend"] == "native_full_tensorrt" else "Accelerator Full"
            full_ratio = accelerator_ratio = "—"
        else:
            path = "Split " + record["case"]
            full_ratio = f"{D(record['speedup_vs_fastest_full_reported']):.3f}"
            accelerator_ratio = f"{D(record['speedup_vs_accelerator_full_reported']):.3f}"
        table_lines.append(
            f"| {record['setup']} | {path} | {D(record['fps_median']):.0f} | "
            f"{full_ratio} | {accelerator_ratio}"
            f" | {record['quality_status']} | not measured |"
        )
    table_lines.extend([
        "",
        "The fastest technically comparable Full path was selected before quality filtering. "
        "Small ratios above one do not establish statistical superiority. Quality labels are transcribed from the report, "
        "not independently evaluated. No matching energy measurements are available for this cohort; "
        "energy remains NA and is not joined from later results.",
        "",
        "These final repeats are separate from the short instrumented H10 stage diagnosis. "
        "Its original detailed CSV and hardware profiling scripts are not included; no stage timings are reconstructed here.",
        "",
    ])
    (OUTPUT / "reported_results.md").write_text("\n".join(table_lines), encoding="utf-8")

    provenance_path = OUTPUT / "reported_results.provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "source_sha256": source_sha, "csv_sha256": provenance["output"]["sha256"], "median_checks": len(checks["median_checks"]), "split_ratio_checks": len(checks["split_ratio_checks"]), "historical_ratio_checks": len(checks["historical_ratio_checks"]), "all_checks_pass": True, "outputs": [csv_path.name, str(provenance_path), "reported_results.md"]}, indent=2))


if __name__ == "__main__":
    main()
