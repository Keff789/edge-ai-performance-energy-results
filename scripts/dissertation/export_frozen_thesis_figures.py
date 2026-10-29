#!/usr/bin/env python3
"""Export the author's fixed English or German v48 figures with hash checks.

The English profile copies recorded publication PDFs. The German profile copies
four verified counterparts and redraws nine energy layouts from their existing
summary/curve CSVs to avoid compressed labels. No statistics or measurements
are recomputed; existing English outputs remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "publications/dissertation/thesis-v56/en"


def export(output: Path, project: Path | None = None, language: str = "en") -> dict:
    manifests = ["ENERGY_SOURCE_MANIFEST.json", "METHODS_SOURCE_MANIFEST.json"]
    items = [item for name in manifests
             for item in json.loads((SOURCE / name).read_text())["figures"]]
    german_manifest = ROOT / "results/supplementary-studies/dissertation-v56/SOURCE_MANIFEST.json"
    german_items = {item["original_path"]: item for item in
                    json.loads(german_manifest.read_text())["files"]} if language == "de" else {}
    records = []
    for item in items:
        english_source = SOURCE / item["file"]
        source = english_source
        expected_digest = item["sha256"]
        evidence = {}
        if language == "de":
            counterpart = german_items[item["latex_project_path"]]
            source = ROOT / counterpart["repository_path"]
            expected_digest = counterpart["sha256"]
            # Existing German publication PDFs are copied, never visually edited.
            # Equal drawing commands verify the exact marks and scientific layout.
            import fitz
            english, german = fitz.open(english_source), fitz.open(source)
            if len(english) != len(german):
                raise ValueError("Different page counts: " + item["file"])
            vector_counts = []
            numeric_tokens = []
            for en_page, de_page in zip(english, german):
                def vectors(page):
                    return [{k: v for k, v in drawing.items() if k not in ("seqno", "layer")}
                            for drawing in page.get_drawings()]
                en_vectors, de_vectors = vectors(en_page), vectors(de_page)
                if en_page.rect != de_page.rect or en_vectors != de_vectors:
                    raise ValueError("German scientific geometry differs: " + item["file"])
                tokens = lambda page: sorted(re.findall(r"[−-]?\d+(?:[.,]\d+)?", page.get_text()))
                if tokens(en_page) != tokens(de_page):
                    raise ValueError("German numerical labels differ: " + item["file"])
                vector_counts.append(len(en_vectors))
                numeric_tokens.append(len(tokens(en_page)))
            evidence = {"english_reference": str(english_source.relative_to(ROOT)),
                        "english_reference_sha256": item["sha256"],
                        "identical_page_dimensions": True,
                        "identical_vector_drawing_commands": True,
                        "vector_drawing_counts": vector_counts,
                        "identical_numeric_label_tokens": True,
                        "numeric_label_token_counts": numeric_tokens}
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != expected_digest:
            raise ValueError(f"Frozen figure hash mismatch: {item['file']}")
        destination = output / item["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Export hash mismatch: {item['file']}")
        records.append({
            "file": item["file"],
            "source": str(source.relative_to(ROOT)),
            "language": language,
            **evidence,
            "sha256": digest,
            "include_width": item["include_width"],
            "placed_modal_font_bp": item["placed_modal_font_bp"],
        })
    regenerated = None
    if language == "de":
        from render_thesis_energy_de import render
        regenerated = render(output / "figures/energy")
        for record in records:
            name = Path(record["file"]).stem
            if name in regenerated["figures"]:
                prior = {key: record.pop(key) for key in list(record)
                         if key.startswith("identical_") or key in
                         ("vector_drawing_counts", "numeric_label_token_counts", "source")}
                record.update(regenerated["figures"][name])
                record["published_german_counterpart_check"] = prior
                record["generator"] = regenerated["generator"]
                record["generator_sha256"] = regenerated["generator_sha256"]
                record["data_payload"] = "figures/energy/" + record["data_payload"]
            else:
                record["source_kind"] = "published_german_exact_bytes"
        # Font sizes below are evaluated at the actual original thesis width.
        import collections
        import fitz
        for record in records:
            page = fitz.open(output / record["file"])[0]
            width = record["include_width"]
            width_bp = (float(width[:-2]) if width.endswith("bp") else
                        float(width[:-2]) * 72 if width.endswith("in") else
                        356.75381 * 72 / 72.27)
            spans = [span for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            sizes = collections.Counter(round(span["size"], 3) for span in spans)
            record.update(pdf_width_bp=page.rect.width, include_width_bp=width_bp,
                          font_sizes_bp=dict(sizes),
                          smallest_placed_font_bp=min(sizes)*width_bp/page.rect.width,
                          placed_modal_font_bp=sizes.most_common(1)[0][0]*width_bp/page.rect.width)
            if Path(record["file"]).stem == "dag_cut":
                record["smallest_font_note"] = "The smallest glyphs are mathematical C1/C2 subscripts; ordinary labels remain about 8–8.6 pt."
    if project is not None:
        for item in items:
            installed = project / item["latex_project_path"]
            installed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output / item["file"], installed)
    result = {
        "status": "PASS",
        "kind": "fixed_publication_exports" if language == "en" else "checked_publication_exports_and_same_data_renders",
        "language": language,
        "german_source_manifest": str(german_manifest.relative_to(ROOT)) if language == "de" else None,
        "source_manifests": [str((SOURCE / name).relative_to(ROOT)) for name in manifests],
        "figures": records,
        "regenerated_energy_figures": len(regenerated["figures"]) if regenerated else 0,
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
    parser.add_argument("--language", choices=("en", "de"), default="en")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == SOURCE or SOURCE in output.parents:
        parser.error("The output must be separate from the frozen publication source.")
    result = export(output, args.project.resolve() if args.project else None, args.language)
    print(json.dumps({"status": result["status"], "figures": len(result["figures"]),
                      "kind": result["kind"]}))


if __name__ == "__main__":
    main()
