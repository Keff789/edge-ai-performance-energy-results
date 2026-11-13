#!/usr/bin/env python3
"""Reproduce the bounded v53 software/provenance audit using compact local inputs.

No network, original archives, model runtime, quality evaluator, bootstrap
resampling or hardware is used. Original-source capture is a separate operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = Path("results/supplementary-studies/thesis-v53-offline-review-20261020")
sys.path.insert(0, str(HERE))
import binding
import operators
import scores
import report


def record(path: Path, base: Path) -> dict:
    raw = path.read_bytes()
    return {"path": path.relative_to(base).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def validate_output(repo: Path, output: Path, verify: bool) -> Path:
    """Only the owned study root, or a fresh directory outside the repo, is writable."""
    repo, output = repo.resolve(), output.resolve()
    canonical = repo / STUDY
    if output == canonical:
        if verify:
            raise ValueError("--verify requires a separate output directory")
        return output
    if output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError("Output must be the owned study root or a fresh external directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("External output must be empty or absent")
    return output


def targeted_tests() -> dict:
    command = [sys.executable, "-I", "-B", "-m", "unittest", "discover",
               "-s", str(HERE), "-p", "test_*.py", "-v"]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    if run.returncode:
        sys.stderr.write(run.stdout + run.stderr)
        raise RuntimeError("Targeted audit tests failed")
    matched = re.search(r"Ran (\d+) tests? in ", run.stderr)
    if matched is None:
        raise RuntimeError("Missing unittest completion receipt")
    tests = []
    for line in run.stderr.splitlines():
        found = re.fullmatch(r"(test_\w+) \(([\w.]+)\) \.\.\. ok", line)
        if found:
            name, owner = found.groups()
            tests.append(owner if owner.endswith("." + name) else owner + "." + name)
    count = int(matched.group(1))
    if len(tests) != count:
        raise RuntimeError("Skipped or unrecorded audit test")
    return {
        "status": "executed_pass", "count": count, "tests": tests,
        "command": "python3 -I -B -m unittest discover -s "
                   + HERE.relative_to(REPO).as_posix() + " -p 'test_*.py' -v",
        "scope": "Only the small regression suite belonging to this audit.",
    }


def build(output: Path, verify: bool = False) -> dict:
    # Import after argument/output validation; this module only reads local facts.
    import paths

    output = validate_output(REPO, output, verify)
    tests = targeted_tests()
    input_files = files_under(REPO / STUDY / "inputs")
    inputs_before = [record(p, REPO) for p in input_files]
    output.mkdir(parents=True, exist_ok=True)
    summaries = {
        "operators": operators.build(REPO, output),
        "scores": scores.build(REPO, output),
        "binding": binding.build(REPO, output),
        "reproduction_paths": paths.build(REPO, output),
    }
    if inputs_before != [record(p, REPO) for p in input_files]:
        raise RuntimeError("Audit inputs changed during reproduction")
    source_context = json.loads((REPO / STUDY / "inputs/source_context.json").read_text())
    source_manifest = {
        "schema": "thesis-v53/source-manifest/v1",
        "task_id": source_context["task_id"],
        "source_context": source_context,
        "audit_inputs": inputs_before,
        "audit_code": [record(p, REPO) for p in files_under(HERE)],
        "component_evidence": {
            name: (STUDY / "inputs" / name / "source_bindings.json").as_posix()
            for name in ("operators", "scores", "binding")
        },
        "reproduction_evidence": (STUDY / "inputs/reproduction").as_posix(),
        "local_source_verification": {
            "operators": "Compact projections, historical counting definitions and candidate bindings checked by operators.py.",
            "scores": "Frozen canonical feature/method/group inputs, copied method definitions and selected archive source members checked by scores.py.",
            "binding": "Projected original hashes and full-UID request/receipt/result cross-links checked by binding.py.",
            "paths": "Recorded successful A commands and exact local input/code/output bindings checked by paths.py.",
        },
        "external_dependencies": {
            "compact_audit": "Python >=3.10 standard library and the existing repository sources only; no network or external paths.",
            "table_reproduction_A": "Existing numerical environment; exact versions and code/input/output receipts in reproduction_paths.json and inputs/reproduction/.",
            "original_graph_verification": "Seven original hash-bound ONNX files and the capture environment, separately identified in inputs/operators/source_bindings.json; not required for compact audit.",
            "original_binding_verification": "Only the explicitly indexed canonical sources and three preserved confirmation archive members; not required for compact audit.",
            "individual_derivation_B": "Exact individual predictions or raw traces plus original evaluators/exporter and environment; status is per route.",
            "physical_repetition_C": "Separate original hardware, runtimes, models, datasets, collector and authorization; inventoried only.",
        },
        "evidence_boundary": "Reproducing a compact projection verifies the audit calculation and its recorded source chain. It does not newly verify absent originals or prove historical process imports.",
    }
    write_json(output / "source_manifest.json", source_manifest)
    report.build(REPO, output)
    git_receipt = json.loads((REPO / STUDY / "inputs/git_status.json").read_text())
    tasks = report.task_statuses(output)
    result_names = sorted({
        "README.md", "source_manifest.json", "thesis_insert.md", "task_closeout.json",
        *(name for value in summaries.values() for name in value["outputs"]),
    })
    closeout = {
        "schema": "thesis-v53/task-closeout/v1",
        "task_id": source_context["task_id"],
        "overall_status": "completed_with_limits",
        "tasks": tasks,
        "tests": tests,
        "inputs_unchanged_during_reproduction": True,
        "input_hashes": inputs_before,
        "code_hashes": source_manifest["audit_code"],
        "result_files": result_names,
        "result_hashes_except_self": [record(output / name, output)
                                     for name in result_names if name != "task_closeout.json"],
        "git": git_receipt,
        "self_reference_policy": "The result file list includes this closeout. It contains neither its own hash nor the future commit that stores it; the Git receipt names only an already existing implementation commit.",
        "scope": source_context["preservation_policy"],
        "actual_execution_boundary": "Compact audit, targeted tests and separately receipted A table reproduction only. B derivations and C physical runs were not executed.",
    }
    write_json(output / "task_closeout.json", closeout)
    if verify:
        canonical = REPO / STUDY
        missing = [name for name in result_names if not (canonical / name).is_file()]
        different = [name for name in result_names if (canonical / name).is_file()
                     and (canonical / name).read_bytes() != (output / name).read_bytes()]
        if missing or different:
            raise RuntimeError(f"Published audit differs: missing={missing}, changed={different}")
    return {"status": "PASS", "scientific_status": closeout["overall_status"],
            "generated_files": len(result_names), "targeted_tests": tests["count"],
            "byte_identical_to_published": verify, "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true",
                        help="Require byte equality with the published audit; use a fresh external output.")
    args = parser.parse_args()
    validate_output(REPO, args.output, args.verify)
    print(json.dumps(build(args.output, args.verify), sort_keys=True))


if __name__ == "__main__":
    main()
