#!/usr/bin/env python3
"""Reproduce historical MLSys selection, quality and feasibility supplements."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

SCRIPT = Path(__file__).resolve().parent
REPOSITORY = SCRIPT.parents[2]
STUDY = REPOSITORY / "results/supplementary-studies/mlsys-selection-20261007"
HISTORICAL = REPOSITORY / "results/supplementary-studies/thesis20-ranking-20261005"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def readable_tables(analysis, figures):
    """Readable views retain full-precision data in adjacent CSVs."""
    import pandas as pd

    def table(frame, labels, path, introduction):
        columns = list(labels)
        lines = [introduction, "", "| " + " | ".join(labels.values()) + " |",
                 "| " + " | ".join("---" for _ in columns) + " |"]
        for _, row in frame.iterrows():
            cells = []
            for key in columns:
                value = row[key]
                if pd.isna(value): value = "NA"
                elif key.endswith("_pct"): value = f"{value:.2f}%"
                elif key.endswith("_fps"): value = f"{value:.0f}"
                elif key.endswith("_mj"): value = f"{value:.1f}"
                elif isinstance(value, float): value = f"{value:.3f}"
                cells.append(str(value).replace("|", "\\|"))
            lines.append("| " + " | ".join(cells) + " |")
        path.write_text("\n".join(lines) + "\n")

    rank = analysis / "reported_update/ranking_tables"
    rows = pd.read_csv(rank / "generic_stability_source.csv")
    for source in ("L_R", "repeat_L_R_min", "repeat_L_R_max"):
        rows[source + "_pct"] = 100 * rows[source]
    table(rows, {"model_id":"Model", "setup_id":"Setup", "n":"Candidates",
        "generic_selected_case":"Generic selection", "native_best_case":"Native best",
        "L_R_pct":"Rate loss", "repeat_L_R_min_pct":"Repeat minimum",
        "repeat_L_R_max_pct":"Repeat maximum", "repeat_top1_hits":"Hits / 9 combinations"},
        rank / "generic_stability.md", "# Selection stability\n\nRanges span nine dependent Generic/Native repeat combinations, not confidence intervals.")
    rows = pd.read_csv(rank / "method_summary.csv")
    rows = rows[rows.cohort.eq("augmented") & rows.tier.eq("technical") & rows.family.eq("all")]
    rows = rows[rows.method.isin(load("paper_plots_labels", SCRIPT / "render_paper_figures.py").METHODS)]
    for source in ("L_R_mean", "L_R_median", "energy_excess_fraction_mean"):
        rows[source + "_pct"] = 100 * rows[source]
    table(rows, {"method":"Selector", "top1_hits":"Native hits / 21",
        "L_R_median_pct":"Median loss", "L_R_mean_pct":"Mean loss",
        "energy_excess_fraction_mean_pct":"Mean energy excess (18 groups)"},
        rank / "selector_summary.md", "# Selector summary\n\nGroups receive equal weight. YOLOv7 has no matching energy in the later report overlay.")
    rows = pd.read_csv(analysis / "best_cases_output/top2_per_model_fastest_full_native_speedup.csv")
    rows["split_energy_mj"] = 1000 * rows.split_j_per_task
    table(rows, {"model_id":"Model", "setup_id":"Setup", "case_id":"Cut",
        "baseline_kind":"Fixed fastest Full", "baseline_native_fps":"Full FPS",
        "split_native_fps":"Split FPS", "native_speedup":"Speedup",
        "split_energy_mj":"Split mJ/task", "efficiency_gain":"Energy gain"},
        analysis / "best_cases_output/fastest_full_highlights.md",
        "# Largest gains over the fastest Full\n\nThe fastest Full is selected by Native throughput before quality filtering; the same Full identity supplies energy where available. Performance and energy use separate windows.")
    rows = pd.read_csv(figures / "resnet_energy_source.csv")
    rows["energy_mj"] = 1000 * rows.j_per_task_mean
    rows["energy_window_fps"] = rows.energy_fps_mean
    table(rows, {"case_id":"Case", "backend":"Backend", "energy_window_fps":"Own-window tasks/s",
        "energy_mj":"Full-system mJ/task", "selected_by":"Selected by"},
        figures / "resnet_energy.md", "# ResNet-50 / H8\n\n19 splits and two distinct Full references; the CSV retains all observed repeat minima/maxima.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="Fresh or empty directory outside the curated repository")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        parser.error("--output must be outside the curated repository")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be a fresh or empty directory")
    for path in (STUDY / "inputs").rglob("*"):
        if path.is_file() and REPOSITORY not in path.resolve().parents:
            parser.error(f"input leaves curated repository: {path}")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(output / ".matplotlib")
    (output / ".tmp").mkdir()
    os.environ["TMPDIR"] = str(output / ".tmp")
    tempfile.tempdir = str(output / ".tmp")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SCRIPT))
    sys.path.insert(0, str(HISTORICAL / "scripts"))
    inputs = STUDY / "inputs/analysis"
    analysis = output / "analysis"
    analysis.mkdir()

    # Shared existing THESIS20 functions rebuild static scores and the historical
    # method tables. Their original inputs and historical published results stay intact.
    scores = load("historical_scores", HISTORICAL / "scripts/reproduce_method_scores.py")
    methods = load("historical_methods", HISTORICAL / "scripts/evaluate_methods.py")
    shared_output = output / "historical-methods"
    scores.analyze(HISTORICAL, HISTORICAL / "source", shared_output)
    methods.analyze(HISTORICAL / "source", shared_output, shared_output)

    from build_best_cases import build as best_cases
    from update_ranking_reported import build as ranking
    from build_review_additions import build as review
    from derive_vendor_quality import build as vendor
    from reproduce_runner_inventory import build as inventory
    from render_paper_figures import render
    from render_review_tables import build as review_tables
    best_cases(inputs / "best_cases_inputs", analysis / "best_cases_output",
               inputs / "reported_update/reported_results.csv")
    ranking(inputs, analysis, shared_output)
    review(STUDY / "inputs", analysis / "review_output", analysis)
    vendor(inputs / "vendor_inputs", analysis / "vendor_output")
    inventory(inputs, analysis / "runner_inventory")
    review_tables(analysis)
    figure_count = render(inputs, analysis, output / "figures")
    readable_tables(analysis, output / "figures")
    print(json.dumps({"status":"PASS", "figure_families":figure_count,
        "technical_candidates":204, "groups":21, "energy_pairs":390,
        "report_overlay_energy":"unavailable", "output":str(output)}, indent=2))


if __name__ == "__main__":
    main()
