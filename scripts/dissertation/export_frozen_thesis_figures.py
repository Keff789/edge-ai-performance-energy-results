#!/usr/bin/env python3
"""Export the author's fixed English v48 energy and method figures with hash checks.

This copies recorded publication PDFs. It does not redraw plots, reconstruct
their composite layout, recompute statistics, or acquire new measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "publications/dissertation/thesis-v56/en"


def export(output: Path, project: Path | None = None) -> dict:
    manifests = ["ENERGY_SOURCE_MANIFEST.json", "METHODS_SOURCE_MANIFEST.json"]
    items = [item for name in manifests
             for item in json.loads((SOURCE / name).read_text())["figures"]]
    records = []
    for item in items:
        source = SOURCE / item["file"]
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Frozen figure hash mismatch: {item['file']}")
        destination = output / item["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Export hash mismatch: {item['file']}")
        if project is not None:
            installed = project / item["latex_project_path"]
            installed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(destination, installed)
        records.append({
            "file": item["file"],
            "sha256": digest,
            "include_width": item["include_width"],
            "placed_modal_font_bp": item["placed_modal_font_bp"],
        })
    result = {
        "status": "PASS",
        "kind": "fixed_publication_exports",
        "source_manifests": [str((SOURCE / name).relative_to(ROOT)) for name in manifests],
        "figures": records,
        "numerical_recomputation": False,
        "project_installed": project is not None,
    }
    (output / "FROZEN_EXPORT.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="Separate output directory for the fixed publication figures")
    parser.add_argument("--project", type=Path,
                        help="Optionally install the checked PDFs at their LaTeX project paths")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == SOURCE or SOURCE in output.parents:
        parser.error("The output must be separate from the frozen publication source.")
    result = export(output, args.project.resolve() if args.project else None)
    print(json.dumps({"status": result["status"], "figures": len(result["figures"]),
                      "kind": result["kind"]}))


if __name__ == "__main__":
    main()
