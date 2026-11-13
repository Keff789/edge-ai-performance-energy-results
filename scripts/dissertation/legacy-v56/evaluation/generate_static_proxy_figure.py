#!/usr/bin/env python3
"""Reproduce the Phase-2 static-proxy rank-correlation figure.

The script joins the frozen graph features from the original development run
with the corrected v2.76.2 Generic performance projection.  It deliberately
uses only the six confirmatory ResNet50/YOLOv7 model-backend strata declared by
the corrected ranking report.  YOLO26s remains outside this figure because its
8/20 audit coverage is below the pre-declared minimum of ten candidates.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = ROOT / "local-output" / "dissertation-v56-legacy" / "ranking"

METHOD_LABELS = {
    "cut_mib": "Boundary bytes",
    "imbalance": "50/50 compute imbalance",
    "flops_right": "Static Stage-2 compute",
}

STRATUM_LABELS = {
    ("resnet50", "deepx_m1_to_tensorrt"): "ResNet50 / DeepX",
    ("resnet50", "hailo10h_to_tensorrt"): "ResNet50 / Hailo-10H",
    ("resnet50", "hailo8_to_tensorrt"): "ResNet50 / Hailo-8",
    ("yolov7_paper", "deepx_m1_to_tensorrt"): "YOLOv7 / DeepX",
    ("yolov7_paper", "hailo10h_to_tensorrt"): "YOLOv7 / Hailo-10H",
    ("yolov7_paper", "hailo8_to_tensorrt"): "YOLOv7 / Hailo-8",
}


def _truth(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _confirmatory_strata(ranking_csv: Path) -> list[tuple[str, str]]:
    rows = _read_csv(ranking_csv)
    strata = {
        (row["model_id"], row["direction"])
        for row in rows
        if _truth(row.get("development_diagnostic_leader_group_eligible"))
    }
    expected = set(STRATUM_LABELS)
    if strata != expected:
        raise ValueError(
            "Confirmatory strata differ from the frozen six-stratum contract: "
            f"expected={sorted(expected)!r}, observed={sorted(strata)!r}"
        )
    return list(STRATUM_LABELS)


def _load_features(predictions_root: Path) -> dict[tuple[str, str], dict[str, float]]:
    features: dict[tuple[str, str], dict[str, float]] = {}
    for model_id in ("resnet50", "yolov7_paper"):
        path = predictions_root / model_id / "analysis" / "predictions_frozen.csv"
        for row in _read_csv(path):
            key = (model_id, row["case_id"])
            features[key] = {
                "cut_mib": float(row["cut_mib"]),
                "imbalance": float(row["imbalance"]),
                "flops_right": float(row["flops_right"]),
            }
    return features


def _load_audit_cases(predictions_root: Path) -> dict[str, set[str]]:
    audit_cases: dict[str, set[str]] = {}
    for model_id in ("resnet50", "yolov7_paper"):
        path = predictions_root / model_id / "analysis" / "final_candidate_plan.json"
        with path.open(encoding="utf-8") as handle:
            plan = json.load(handle)
        rows = plan.get("audit_candidates") or []
        cases = {str(row.get("case_id") or "") for row in rows}
        cases.discard("")
        if len(cases) != 20:
            raise ValueError(f"Expected 20 frozen audit candidates for {model_id}, got {len(cases)}")
        audit_cases[model_id] = cases
    return audit_cases


def _load_cycles(
    performance_csv: Path,
    strata: list[tuple[str, str]],
    audit_cases: dict[str, set[str]],
) -> dict[tuple[str, str], dict[str, float]]:
    allowed = set(strata)
    cycles: dict[tuple[str, str], dict[str, float]] = {key: {} for key in strata}
    for row in _read_csv(performance_csv):
        stratum = (row.get("model_id", ""), row.get("direction", ""))
        if stratum not in allowed:
            continue
        if row.get("runner_regime") != "generic" or not _truth(row.get("runtime_executable")):
            continue
        case_id = row.get("case_id", "")
        cycle = row.get("cycle_ms", "")
        if case_id not in audit_cases[stratum[0]] or cycle in {"", None}:
            continue
        cycles[stratum][case_id] = float(cycle)
    return cycles


def _correlations(
    features: dict[tuple[str, str], dict[str, float]],
    cycles: dict[tuple[str, str], dict[str, float]],
    strata: list[tuple[str, str]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for model_id, direction in strata:
        cases = [
            case_id
            for case_id in cycles[(model_id, direction)]
            if (model_id, case_id) in features
        ]
        if len(cases) < 10:
            raise ValueError(f"Unexpected subminimum stratum {(model_id, direction)}: n={len(cases)}")
        measured = [cycles[(model_id, direction)][case_id] for case_id in cases]
        for feature_name in METHOD_LABELS:
            predicted = [features[(model_id, case_id)][feature_name] for case_id in cases]
            rho = float(spearmanr(predicted, measured).statistic)
            out.append(
                {
                    "model_id": model_id,
                    "direction": direction,
                    "stratum": STRATUM_LABELS[(model_id, direction)],
                    "feature": feature_name,
                    "feature_label": METHOD_LABELS[feature_name],
                    "paired_candidate_count": len(cases),
                    "spearman_rho": rho,
                }
            )
    return out


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot(path_base: Path, rows: list[dict[str, object]]) -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    strata = [STRATUM_LABELS[key] for key in STRATUM_LABELS]
    features = list(METHOD_LABELS)
    matrix = np.array(
        [
            [
                next(
                    float(row["spearman_rho"])
                    for row in rows
                    if row["stratum"] == stratum and row["feature"] == feature
                )
                for feature in features
            ]
            for stratum in strata
        ]
    )

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(7.2, 3.55),
        gridspec_kw={"width_ratios": [2.5, 1.0]},
        constrained_layout=True,
    )

    ax = axes[0]
    image = ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu", aspect="auto")
    ax.set_xticks(
        range(len(features)),
        ["Boundary\nbytes", "50/50 compute\nimbalance", "Static Stage-2\ncompute"],
    )
    ax.set_yticks(range(len(strata)), strata)
    ax.set_title("(a) Rank correlation by confirmatory stratum")
    for row_i in range(matrix.shape[0]):
        for col_i in range(matrix.shape[1]):
            value = matrix[row_i, col_i]
            ax.text(
                col_i,
                row_i,
                f"{value:.2f}",
                ha="center",
                va="center",
                color="white" if abs(value) > 0.58 else "black",
                fontsize=8,
            )
    fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)

    ax = axes[1]
    positions = np.arange(len(features))
    for index, feature in enumerate(features):
        values = matrix[:, index]
        jitter = np.linspace(-0.07, 0.07, len(values))
        ax.scatter(np.full_like(values, positions[index], dtype=float) + jitter, values, s=22, alpha=0.78)
        ax.plot(
            [positions[index] - 0.19, positions[index] + 0.19],
            [float(np.median(values)), float(np.median(values))],
            color="black",
            linewidth=2.0,
        )
    ax.axhline(0, color="0.45", linewidth=0.8)
    ax.set_ylim(-1, 1)
    ax.set_xticks(positions, ["Bytes", "50/50\nbalance", "Stage 2\nops"])
    ax.set_ylabel("Spearman $\\rho$")
    ax.set_title("(b) Six-stratum distribution")
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle(
        "Static graph proxies versus measured Generic cycle time",
        fontsize=11,
    )
    for suffix in ("pdf", "png"):
        fig.savefig(path_base.with_suffix(f".{suffix}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions-root", type=Path, required=True)
    parser.add_argument("--performance-csv", type=Path, required=True)
    parser.add_argument("--ranking-comparison-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        help="Figure output (default: local-output/dissertation-v56-legacy/ranking/figures); "
             "an explicit directory also receives the CSV unless --data-output-dir is set",
    )
    parser.add_argument(
        "--data-output-dir", type=Path,
        help="Separate CSV destination (default: local-output/dissertation-v56-legacy/ranking/daten)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT / "figures"
    data_dir = args.data_output_dir if args.data_output_dir is not None else (
        args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT / "daten"
    )
    for path in (args.predictions_root, args.performance_csv, args.ranking_comparison_csv):
        if not path.exists():
            parser.error(f"Missing external analysis input: {path}")
    strata = _confirmatory_strata(args.ranking_comparison_csv)
    features = _load_features(args.predictions_root)
    audit_cases = _load_audit_cases(args.predictions_root)
    cycles = _load_cycles(args.performance_csv, strata, audit_cases)
    rows = _correlations(features, cycles, strata)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(data_dir / "static_proxy_spearman_confirmatory.csv", rows)
    _plot(output_dir / "static_proxy_spearman_confirmatory", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
