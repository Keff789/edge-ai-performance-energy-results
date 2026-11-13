#!/usr/bin/env python3
"""Generate the Phase 2 ranking-method diagnostic Spearman heatmap.

Only rows explicitly marked as
``development_diagnostic_leader_group_eligible`` are visualised.  The script
fails closed if the frozen six-stratum/five-method structure is not present;
it never substitutes global macros or rows from incomplete groups.
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from collections import defaultdict
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "phase2_ranking_mplconfig")
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = ROOT / "local-output" / "dissertation-v56-legacy" / "ranking"

METHOD_ORDER = (
    "cut_bytes_only",
    "weighted_score",
    "cycle_time_no_handover",
    "cycle_time_with_handover",
    "onnx_real_boundary_hardware_aware",
)

METHOD_LABELS = {
    "cut_bytes_only": "Cut bytes\nonly",
    "weighted_score": "Weighted\nscore",
    "cycle_time_no_handover": "Cycle time\nno handover",
    "cycle_time_with_handover": "Cycle time\nwith handover",
    "onnx_real_boundary_hardware_aware": "Hardware-aware\nONNX boundary",
}

MODEL_ORDER = {"resnet50": 0, "yolov7_paper": 1}
MODEL_LABELS = {"resnet50": "ResNet-50", "yolov7_paper": "YOLOv7 Paper"}

DIRECTION_ORDER = {
    "deepx_m1_to_tensorrt": 0,
    "hailo10h_to_tensorrt": 1,
    "hailo8_to_tensorrt": 2,
}

DIRECTION_LABELS = {
    "deepx_m1_to_tensorrt": "DeepX M1 to TensorRT",
    "hailo10h_to_tensorrt": "Hailo-10H to TensorRT",
    "hailo8_to_tensorrt": "Hailo-8 to TensorRT",
}

TRUE_VALUES = {"1", "true", "yes"}


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Input CSV is empty: {path}")
    return rows


def _stratum_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row["model_id"],
        row["direction"],
        row["runner_regime"],
        row["setup_id"],
    )


def _extract_matrix(
    rows: list[dict[str, str]],
) -> tuple[list[tuple[str, str, str, str]], list[list[float]], list[int]]:
    eligible = [
        row
        for row in rows
        if _is_true(row.get("development_diagnostic_leader_group_eligible"))
    ]
    if not eligible:
        raise ValueError("No development-diagnostic leader-group rows are eligible")

    if any("evaluation_role" not in row for row in eligible):
        raise ValueError(
            "Input lacks evaluation_role. Use the full ranking_method_comparison.csv "
            "from the original analysis; the packaged compact result CSV is not a full input."
        )
    if any(row.get("evaluation_role") != "development" for row in eligible):
        raise ValueError("Eligible cohort unexpectedly contains a non-development row")
    if any(row.get("model_id") == "yolo26s" for row in eligible):
        raise ValueError("YOLO26s unexpectedly entered the eligible diagnostic cohort")

    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in eligible:
        key = _stratum_key(row)
        method = row["method_id"]
        if method in grouped[key]:
            raise ValueError(f"Duplicate method {method!r} in stratum {key!r}")
        grouped[key][method] = row

    if len(grouped) != 6:
        raise ValueError(f"Expected exactly six eligible strata, found {len(grouped)}")

    for key, method_rows in grouped.items():
        methods = set(method_rows)
        if methods != set(METHOD_ORDER):
            raise ValueError(
                f"Stratum {key!r} has methods {sorted(methods)!r}; "
                f"expected {sorted(METHOD_ORDER)!r}"
            )

    def sort_key(key: tuple[str, str, str, str]) -> tuple[int, int, str]:
        model, direction, _runner, setup = key
        if model not in MODEL_ORDER or direction not in DIRECTION_ORDER:
            raise ValueError(f"Unexpected eligible stratum: {key!r}")
        return MODEL_ORDER[model], DIRECTION_ORDER[direction], setup

    strata = sorted(grouped, key=sort_key)
    matrix: list[list[float]] = []
    paired_counts: list[int] = []

    for key in strata:
        method_rows = grouped[key]
        values: list[float] = []
        counts: set[int] = set()
        for method in METHOD_ORDER:
            row = method_rows[method]
            raw_value = row.get("diagnostic_spearman_rho", "").strip()
            if not raw_value:
                raise ValueError(f"Missing diagnostic Spearman rho for {key!r}/{method}")
            values.append(float(raw_value))
            counts.add(int(row["diagnostic_paired_candidate_count"]))
        if len(counts) != 1:
            raise ValueError(f"Inconsistent paired-candidate counts in {key!r}: {counts!r}")
        matrix.append(values)
        paired_counts.append(counts.pop())

    return strata, matrix, paired_counts


def _yolo26s_note(rows: list[dict[str, str]]) -> str:
    yolo_rows = [row for row in rows if row.get("model_id") == "yolo26s"]
    if not yolo_rows:
        return "YOLO26s is not present in the source CSV and is not part of this cohort."

    by_stratum: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in yolo_rows:
        if row.get("direction") not in DIRECTION_ORDER or row.get("comparison_backend"):
            continue
        by_stratum.setdefault(_stratum_key(row), row)

    paired = sorted({int(row["diagnostic_paired_candidate_count"]) for row in by_stratum.values()})
    minimum = sorted({int(row["diagnostic_minimum_candidates_required"]) for row in by_stratum.values()})
    coverage = sorted(
        {float(row["diagnostic_candidate_coverage_fraction"]) for row in by_stratum.values()}
    )
    trt_rows = [
        row
        for row in yolo_rows
        if row.get("direction") == "tensorrt_to_tensorrt" and not row.get("comparison_backend")
    ]
    trt_unfrozen = any(not _is_true(row.get("predictions_frozen")) for row in trt_rows)

    if paired == [8] and minimum == [10] and coverage == [0.4]:
        note = (
            "YOLO26s is not part of this eligible cohort: every evaluated stratum "
            "has 8 paired candidates (<10 required) and 40% diagnostic coverage."
        )
    else:
        note = (
            "YOLO26s is not part of this eligible cohort; its strata do not meet "
            "the frozen paired-candidate and diagnostic-coverage requirements."
        )
    if trt_unfrozen:
        note += " Its TensorRT-to-TensorRT row is additionally not frozen."
    return note


def _row_label(key: tuple[str, str, str, str], paired_count: int) -> str:
    model, direction, runner, _setup = key
    if runner != "generic":
        raise ValueError(f"Unexpected runner regime in eligible cohort: {runner!r}")
    return (
        f"{MODEL_LABELS[model]} | {DIRECTION_LABELS[direction]} "
        f"(n={paired_count})"
    )


def generate_figure(
    input_csv: Path, output_dir: Path, output_stem: str,
    data_output_dir: Path | None = None,
) -> None:
    rows = _read_rows(input_csv)
    strata, matrix, paired_counts = _extract_matrix(rows)
    yolo_note = _yolo26s_note(rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{output_stem}.pdf"
    png_path = output_dir / f"{output_stem}.png"
    data_output_dir = data_output_dir if data_output_dir is not None else output_dir
    data_output_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_output_dir / f"{output_stem}.csv"

    compact_fields = (
        "model_id",
        "direction",
        "runner_regime",
        "setup_id",
        "method_id",
        "diagnostic_paired_candidate_count",
        "diagnostic_spearman_rho",
        "diagnostic_kendall_tau_b",
        "development_diagnostic_leader_group_eligible",
    )
    compact_rows = [
        {field: row.get(field, "") for field in compact_fields}
        for row in rows
        if _is_true(row.get("development_diagnostic_leader_group_eligible"))
    ]
    with data_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=compact_fields)
        writer.writeheader()
        writer.writerows(compact_rows)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.0,
            "axes.titlesize": 12.0,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    image = ax.imshow(matrix, cmap="RdBu", vmin=-1.0, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(METHOD_ORDER)), [METHOD_LABELS[m] for m in METHOD_ORDER])
    ax.set_yticks(
        range(len(strata)),
        [_row_label(key, count) for key, count in zip(strata, paired_counts)],
    )
    ax.tick_params(axis="x", length=0, pad=10)
    ax.tick_params(axis="y", length=0, pad=8)

    ax.set_xticks([x - 0.5 for x in range(1, len(METHOD_ORDER))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(strata))], minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.7)
    ax.tick_params(which="minor", bottom=False, left=False)

    for row_index, values in enumerate(matrix):
        best_index = max(range(len(values)), key=values.__getitem__)
        ax.add_patch(
            Rectangle(
                (best_index - 0.48, row_index - 0.48),
                0.96,
                0.96,
                fill=False,
                edgecolor="#111111",
                linewidth=2.0,
            )
        )
        for col_index, value in enumerate(values):
            text_color = "white" if abs(value) >= 0.64 else "#111111"
            ax.text(
                col_index,
                row_index,
                f"{value:.3f}",
                ha="center",
                va="center",
                color=text_color,
                fontsize=9.6,
                fontweight="bold" if col_index == best_index else "normal",
            )

    ax.axhline(2.5, color="#303030", linewidth=2.2)
    for spine in ax.spines.values():
        spine.set_visible(False)

    colorbar = fig.colorbar(image, ax=ax, fraction=0.030, pad=0.030)
    colorbar.set_label(r"Diagnostic Spearman $\rho$", rotation=90, labelpad=10)
    colorbar.outline.set_linewidth(0.6)
    colorbar.set_ticks([-1.0, -0.5, 0.0, 0.5, 1.0])

    fig.suptitle(
        "Phase 2 ranking audit: diagnostic rank correlation by method",
        x=0.02,
        y=0.965,
        ha="left",
        fontsize=16,
        fontweight="bold",
        color="#17212b",
    )
    fig.text(
        0.02,
        0.915,
        "Five frozen methods across exactly six eligible development-diagnostic strata "
        "(higher is better)",
        ha="left",
        fontsize=10.8,
        color="#3f4b57",
    )
    fig.text(
        0.02,
        0.155,
        "Black outline marks the highest diagnostic Spearman correlation within each stratum. "
        "These are development diagnostics, not claim-eligible correlations.",
        ha="left",
        fontsize=9.3,
        color="#3f4b57",
    )
    fig.text(
        0.02,
        0.075,
        yolo_note,
        ha="left",
        va="center",
        fontsize=9.6,
        color="#2b3137",
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "#f2f3f4",
            "edgecolor": "#b4bac0",
            "linewidth": 0.8,
        },
    )
    fig.text(
        0.02,
        0.018,
        f"Source: {input_csv.name}; only "
        "development_diagnostic_leader_group_eligible=True rows and "
        "diagnostic_spearman_rho are plotted.",
        ha="left",
        fontsize=8.2,
        color="#59636e",
    )

    fig.subplots_adjust(left=0.34, right=0.91, top=0.84, bottom=0.25)

    metadata = {
        "Title": "Phase 2 ranking audit: diagnostic Spearman correlation by method",
        "Subject": "Six eligible development-diagnostic strata and five frozen ranking methods",
        "Author": "Generated reproducibly from ranking_method_comparison.csv",
    }
    fig.savefig(pdf_path, bbox_inches="tight", metadata=metadata)
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(pdf_path)
    print(png_path)
    print(data_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="ranking_method_comparison.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Figure output (default: local-output/dissertation-v56-legacy/ranking/figures); "
             "an explicit directory also receives the CSV unless --data-output-dir is set",
    )
    parser.add_argument(
        "--data-output-dir", type=Path,
        help="Separate CSV destination (default: local-output/dissertation-v56-legacy/ranking/daten)",
    )
    parser.add_argument(
        "--output-stem",
        default="phase2_ranking_diagnostic_spearman_six_eligible_strata",
        help="Filename stem for PDF and PNG outputs",
    )
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT / "figures"
    data_dir = args.data_output_dir if args.data_output_dir is not None else (
        args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT / "daten"
    )
    try:
        generate_figure(args.input.resolve(strict=True), output_dir.resolve(),
                        args.output_stem, data_dir.resolve())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
