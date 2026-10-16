#!/usr/bin/env python3
"""Reproduce stage-cost numerical exports, summary tables and vector figures."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from analyse_stage_cost_test import analyse
from render_stage_costs import render_tables

REPOSITORY = SCRIPT_DIR.parents[2]
STUDY = REPOSITORY / "results/supplementary-studies/stage-cost-composition"
EXPORTS = {
    "STAGE_CAPACITIES.csv": "tables/STAGE_CAPACITIES.csv",
    "PIPELINE_MEASUREMENTS.csv": "tables/PIPELINE_MEASUREMENTS.csv",
    "ORACLE_PREDICTIONS.csv": "tables/ORACLE_PREDICTIONS.csv",
    "COMPOSITION_COMPARISON.csv": "tables/COMPOSITION_COMPARISON.csv",
    "results/ANALYSIS.json": "results/ANALYSIS.json",
    "results/ORACLE_PREDICTIONS.json": "results/ORACLE_PREDICTIONS.json",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="fresh output directory outside the repository")
    parser.add_argument("--numeric-only", action="store_true",
                        help="generate numerical exports/tables using only the standard library")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPOSITORY):
        parser.error("output must be outside the repository")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("output must be an empty or nonexistent directory")
    inputs = STUDY / "inputs"
    for path in inputs.rglob("*"):
        if not path.resolve(strict=True).is_relative_to(inputs):
            raise ValueError(f"input path escapes the supplied inputs: {path.name}")
    output.mkdir(parents=True, exist_ok=True)
    # The original evaluator writes within its input tree. Only a disposable
    # copy is writable; the repository's measurements and results stay intact.
    with tempfile.TemporaryDirectory(prefix="stage-cost-", dir=output) as temporary:
        working = Path(temporary) / "experiment"
        shutil.copytree(inputs, working)
        summary = analyse(working)
        differences = []
        for source_name, destination_name in EXPORTS.items():
            source = working / source_name
            destination = output / destination_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if source.read_bytes() != (STUDY / destination_name).read_bytes():
                differences.append(destination_name)
        if summary["errors"] or differences:
            raise RuntimeError(json.dumps({"evaluator_errors": summary["errors"],
                                           "different_exports": differences}))
    analysis = json.loads((output / "results/ANALYSIS.json").read_text())
    plan = json.loads((inputs / "PLAN.json").read_text())
    render_tables(analysis, plan, output / "tables")
    if not args.numeric_only:
        from render_stage_costs import plots
        with (output / "tables/COMPOSITION_COMPARISON.csv").open(newline="") as handle:
            comparisons = list(csv.DictReader(handle))
        with tempfile.TemporaryDirectory(prefix="matplotlib-", dir=output) as config:
            previous = os.environ.get("MPLCONFIGDIR")
            os.environ["MPLCONFIGDIR"] = config
            try:
                plots(analysis, plan, comparisons, output / "figures")
            finally:
                if previous is None:
                    os.environ.pop("MPLCONFIGDIR", None)
                else:
                    os.environ["MPLCONFIGDIR"] = previous
    print(json.dumps({"status": "PASS", "matching_numerical_exports": len(EXPORTS),
                      "measurement_reports": summary["measurement_rows"],
                      "case_aggregates": len(summary["cases"]),
                      "predictions": summary["prediction_rows"],
                      "block_comparisons": summary["comparison_rows"],
                      "overall_decision": summary["overall_decision"],
                      "summary_tables": 3, "figure_files": 0 if args.numeric_only else 6,
                      "scope": "numerical reproduction from supplied reports; no array or hardware revalidation"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
