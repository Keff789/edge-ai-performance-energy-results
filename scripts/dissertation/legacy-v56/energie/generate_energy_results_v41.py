#!/usr/bin/env python3
"""Regenerate historical v41 macros from the frozen Energy Paper CSV artifacts.

These macros are not the active v43 values used by the dissertation.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, default=ROOT / "results" / "supplementary-studies" / "dissertation-v56" / "inputs" / "energie",
                    help="Directory containing the frozen energy CSV inputs")
parser.add_argument("--output-dir", type=Path,
                    default=ROOT / "local-output" / "dissertation-v56-legacy" / "energie_v41" / "tex",
                    help="Destination for historical v41 macros")
args = parser.parse_args()
DATA = args.data_dir.resolve()
OUT = args.output_dir.resolve() / "energy_results_v41.tex"


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fmt(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


pipeline = (DATA / "AUTO_PIPELINE_SUMMARY.md").read_text(encoding="utf-8")
workloads = rows("table_cross_workload_psd_metrics.csv")
sufficiency = rows("table_cross_workload_two_k_sufficiency.csv")
high_rate = rows("table_cross_workload_high_rate_coverage.csv")
idle = rows("table_cross_workload_idle_load_summary.csv")
long_record = rows("long_record_duration_q95.csv")
worst_two_k = rows("multi_workload_two_k_worst_q95.csv")

# The completed automatic-pipeline summary is the canonical inventory source.
paired_records = 673
common_pairs = sum(int(row["n"]) for row in workloads)
workload_count = len(workloads)

# Conservative duration per workload: maximum over the two external setups.
per_workload: dict[str, dict[float, float]] = {}
for row in sufficiency:
    w = row["Workload"]
    tol = float(row["Tolerance [\\%]"])
    duration = float(row["Minimum tested duration [s]"])
    per_workload.setdefault(w, {})[tol] = max(
        per_workload.setdefault(w, {}).get(tol, 0.0), duration
    )

long_by_t = {float(r["duration_s"]): float(r["q95_pct"]) for r in long_record}
worst_by_t = {
    float(r["duration_s"]): float(r["worst_hierarchical_abs_error_q95_pct"])
    for r in worst_two_k
}
max_above_nyquist = max(float(r[">2.5 MHz [\\%]"]) for r in high_rate)
min_captured = min(float(r["Captured below 2.5 MHz [\\%]"]) for r in high_rate)
active_idle = [float(r["Active/idle [dB]"]) for r in idle]

macros: list[tuple[str, str]] = [
    ("EnergyAnalysisToolVersion", "0.8.2"),
    ("EnergyAnalysisSchema", "9"),
    ("EnergyWorkloadCount", str(workload_count)),
    ("EnergyPairedRecordCount", str(paired_records)),
    ("EnergyCommonRatePairCount", str(common_pairs)),
    ("EnergyIdleRunCount", "11"),
    ("EnergyIdleDurationSeconds", "110"),
    ("EnergyTwoKOnePercentDuration", "2"),
    ("EnergyTwoKHalfPercentDuration", "10"),
    ("EnergyTwoKWorstOneSecond", fmt(worst_by_t[1.0], 3)),
    ("EnergyTwoKWorstTwoSeconds", fmt(worst_by_t[2.0], 3)),
    ("EnergyTwoKWorstFiveSeconds", fmt(worst_by_t[5.0], 3)),
    ("EnergyTwoKWorstTenSeconds", fmt(worst_by_t[10.0], 3)),
    ("EnergyHundredMsTekOnePercentRateK", "80"),
    ("EnergyHundredMsPicoOnePercentRateK", "25"),
    ("EnergyTwentyMsTekOnePercentRateK", "160"),
    ("EnergyTwentyMsPicoOnePercentRateK", "80"),
    ("EnergyLongRunCount", "13"),
    ("EnergyLongRunDurationSeconds", "104"),
    ("EnergyLongOneSecondQ", fmt(long_by_t[1.0], 3)),
    ("EnergyLongTwoSecondsQ", fmt(long_by_t[2.0], 3)),
    ("EnergyLongFiveSecondsQ", fmt(long_by_t[5.0], 3)),
    ("EnergyLongTenSecondsQ", fmt(long_by_t[10.0], 3)),
    ("EnergyLongTwentySecondsQ", fmt(long_by_t[20.0], 3)),
    ("EnergyLongFiftySecondsQ", fmt(long_by_t[50.0], 3)),
    ("EnergyLongHundredSecondsQ", fmt(long_by_t[100.0], 3)),
    ("EnergyLongFullQ", fmt(long_by_t[104.0], 3)),
    ("EnergyHighRateMaxAboveNyquist", fmt(max_above_nyquist, 4)),
    ("EnergyHighRateMinCaptured", fmt(min_captured, 4)),
    ("EnergyActiveIdleMinDb", fmt(min(active_idle), 2)),
    ("EnergyActiveIdleMaxDb", fmt(max(active_idle), 2)),
    ("EnergyTekZeroShiftMilliamp", "111.917"),
    ("EnergyTekZeroSpreadMilliamp", "4.092"),
]

prefix = {
    "GEMM-FP32": "EnergyGemmFpThirtyTwo",
    "GEMM-INT8": "EnergyGemmIntEight",
    "YOLO-FP32": "EnergyYoloFpThirtyTwo",
    "YOLO-INT8": "EnergyYoloIntEight",
    "Gemma3-4B": "EnergyGemmaThreeFourB",
    "ResNet-50 FP32": "EnergyResNetFiftyFpThirtyTwo",
}
for row in workloads:
    p = prefix[row["Workload"]]
    macros.extend(
        [
            (p + "PairCount", row["n"]),
            (p + "FiftyKHz", row["$f_{50}$ [kHz]"]),
            (p + "NinetyFiveKHz", row["$f_{95}$ [kHz]"]),
            (p + "NinetyNineKHz", row["$f_{99}$ [kHz]"]),
            (p + "AboveSeventySevenPct", row[">77 kHz [\\%]"]),
            (p + "Entropy", row["Entropy"]),
            (p + "OnePercentDuration", fmt(per_workload[row["Workload"]][1.0], 3)),
            (p + "HalfPercentDuration", fmt(per_workload[row["Workload"]][0.5], 3)),
        ]
    )

lines = [
    "% Auto-generated from the frozen Energy Paper review artifacts.",
    "% Generator: scripts/dissertation/legacy-v56/energie/generate_energy_results_v41.py",
    "% Do not edit numerical values manually; regenerate after replacing canonical CSV inputs.",
]
for name, value in macros:
    lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")
lines.append("")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {OUT}")
