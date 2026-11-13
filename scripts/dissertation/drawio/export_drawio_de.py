#!/usr/bin/env python3
"""Export the author's German DrawIO/SVG figures with documented label fixes.

Uploaded sources are read-only. Corrected editable copies live in --working;
only vector PDFs are copied to --project. Mapping comes from the prior figure
origins manifest, so unreferenced supplied diagrams cannot enter the thesis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import fitz

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_label(svg_root, draw_root, cell_id, before, after):
    cell = next(c for c in draw_root.iter("mxCell") if c.get("id") == cell_id)
    assert cell.get("value") == before, (cell_id, cell.get("value"), before)
    cell.set("value", after)
    group = next(e for e in svg_root.iter() if e.get("data-cell-id") == cell_id)
    text = next(group.iter(f"{{{SVG}}}text"))
    lines = after.split("\n")
    tspans = list(text)
    if tspans:
        assert len(tspans) == len(lines), (cell_id, lines)
        for tspan, line in zip(tspans, lines):
            tspan.text = line
    else:
        assert len(lines) == 1
        text.text = after
    return {"cell": cell_id, "old": before, "new": after}


def correct(svg_tree, draw_tree, number):
    root, draw_root = svg_tree.getroot(), draw_tree.getroot()
    changes = []
    if number == "02":
        cells = list(draw_root.iter("mxCell"))
        removed = {c.get("parent") for c in cells if c.get("value") in {"ISP", "H.264"}}
        assert removed == {"hailo8-29", "hailo8-34"}
        while True:
            previous = len(removed)
            removed.update(c.get("id") for c in cells if any(c.get(k) in removed for k in ("parent", "source", "target")))
            if len(removed) == previous:
                break
        for parent in draw_root.iter():
            for child in list(parent):
                if child.tag == "mxCell" and child.get("id") in removed:
                    parent.remove(child)
        for parent in root.iter():
            for child in list(parent):
                if child.get("data-cell-id") in removed:
                    parent.remove(child)
        changes.append({"removed_labels": ["ISP", "H.264"], "removed_cells": sorted(removed), "reason": "Retain the verified prior Hailo-8 correction: these video-processing blocks are unsupported; delete their boxes and connecting arrows too."})
    if number == "13":
        for cell, before, after in (
            ("text-3", "Generisch und nativ: Wahl der Tensorgrenze", "Generic und Native: Wahl der Tensorgrenze"),
            ("text-6", "Generisch", "Generic"),
            ("text-26", "Nativ", "Native"),
        ):
            change = replace_label(root, draw_root, cell, before, after)
            change["reason"] = "Generic and Native are experiment method names and remain untranslated."
            changes.append(change)
    if number == "14":
        for cell in ("text-10", "text-22"):
            change = replace_label(root, draw_root, cell, "Arbeit +\nKalibrierung", "Kompilierter\nTeilgraph")
            change["reason"] = "Retain the verified prior cost-model correction: calibration is not part of timed stage execution."
            changes.append(change)
    if number == "11":
        change = replace_label(root, draw_root, "text-4", "Messgrenzen; Kanalverdrahtung je Messreihe festzulegen", "Systemeingang und nachgelagerte Versorgungspfade")
        change["reason"] = "Retain the verified prior caption correction; describe the finished schematic rather than an unfinished measurement step."
        changes.append(change)
    # A DrawIO compatibility warning is not diagram content. All real labels
    # are native SVG text; remove the browser-only fallback before PDF export.
    for parent in root.iter():
        for child in list(parent):
            if child.tag == f"{{{SVG}}}switch" and "Text is not SVG - cannot display" in "".join(child.itertext()):
                parent.remove(child)
    return changes


def typography(svg_tree, draw_tree, number):
    """Enlarge labels within the supplied design at the final thesis width."""
    root = svg_tree.getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    width = float(root.get("width").removesuffix("px"))
    fraction = .64 if number in {"01", "02", "03", "04"} else 1.
    final_width = 356.75381 * 72 / 72.27 * fraction
    changes = []
    for text in root.iter(f"{{{SVG}}}text"):
        old_text = "\n".join(text.itertext())
        ancestor = text
        cell_id = None
        old_size = None
        while ancestor is not None:
            cell_id = cell_id or ancestor.get("data-cell-id")
            old_size = old_size or ancestor.get("font-size")
            ancestor = parents.get(ancestor)
        if not old_size:
            continue
        old_size = float(old_size.removesuffix("px"))
        if fraction < 1:
            target = 9.5 if old_size >= 42 else 8.5
            if old_text in {"STEU.", "SPEICH.", "RECH."}:
                target = 6.6
        else:
            target = 9.5 if old_size >= 25 else 8.5
        font_px = target * width / final_width
        text.set("font-size", f"{font_px:.3f}px")
        text.set("style", re.sub(r"font-size\s*:[^;]+;?", "", text.get("style", "")) + f";font-size:{font_px:.3f}px")
        tspans = list(text)
        if len(tspans) > 1:
            ys = [float(t.get("y", text.get("y", "0"))) for t in tspans]
            middle = sum(ys) / len(ys)
            for i, tspan in enumerate(tspans):
                tspan.set("y", f"{middle + font_px * 1.15 * (i - (len(tspans) - 1) / 2):.3f}")
        if cell_id:
            cell = next(c for c in draw_tree.getroot().iter("mxCell") if c.get("id") == cell_id)
            cell.set("style", re.sub(r"fontSize=[\d.]+", f"fontSize={font_px:.3f}", cell.get("style", "")))
        changes.append({"cell": cell_id, "text": old_text, "old_css_px": old_size, "new_css_px": round(font_px, 3), "target_final_pt": target})
    return fraction, changes


def refine(svg_tree, draw_tree, number, fraction):
    """Local German line breaks and spacing; all diagram shapes are retained."""
    root = svg_tree.getroot()
    width = float(root.get("width").removesuffix("px"))
    factor = width / (356.75381 * 72 / 72.27 * fraction)
    changes = []
    def edit(cell_id, *, pt=None, lines=None, y=None, x=None, dy=0):
        group = next(g for g in root.iter() if g.get("data-cell-id") == cell_id)
        text = next(group.iter(f"{{{SVG}}}text"))
        cell = next(c for c in draw_tree.getroot().iter("mxCell") if c.get("id") == cell_id)
        old = "\n".join(text.itertext())
        fs = pt * factor if pt else float(text.get("font-size").removesuffix("px"))
        if pt:
            text.set("font-size", f"{fs:.3f}px")
            text.set("style", re.sub(r"font-size\s*:[^;]+;?", "", text.get("style", "")) + f";font-size:{fs:.3f}px")
            cell.set("style", re.sub(r"fontSize=[\d.]+", f"fontSize={fs:.3f}", cell.get("style", "")))
        ts = list(text)
        ys = [float(t.get("y", text.get("y", "0"))) for t in ts] if ts else [float(text.get("y", "0"))]
        middle = (y if y is not None else sum(ys) / len(ys)) + dy
        xx = str(x) if x is not None else text.get("x")
        text.set("x", xx)
        if lines is not None or ts:
            ls = lines.split("\n") if lines is not None else [t.text or "" for t in ts]
            for child in list(text): text.remove(child)
            text.text = None
            for i, line in enumerate(ls):
                ET.SubElement(text, f"{{{SVG}}}tspan", {"x": xx, "y": f"{middle + fs * 1.15 * (i - (len(ls)-1)/2):.3f}"}).text = line
            cell.set("value", "\n".join(ls))
        else:
            text.set("y", f"{middle:.3f}")
        changes.append({"cell": cell_id, "old": old, "new": lines or old, "target_final_pt": pt, "svg_center_baseline_y": middle, "svg_text_x": xx})
    if number == "01":
        edit("orin-35", pt=7.7)
        for cell in ("orin-95", "orin-96", "orin-98", "orin-99", "orin-101", "orin-102"):
            edit(cell, pt=6.6)
        edit("orin-93", dy=-6)
    if number in {"02", "03"}:
        keys = ("hailo8-106", "hailo8-107", "hailo8-108") if number == "02" else ("32", "34", "36", "38", "40", "42")
        for i, cell in enumerate(keys): edit(cell, pt=7.2, lines=("ST.", "SP.", "RE.")[i % 3])
    if number == "03":
        edit("47", pt=7.0, lines="Ressourcenanordnung /\nSchichtzuordnung: schematisch", y=688)
        edit("52", pt=6.8, lines="Maximale\nRechen-\nleistung", y=385)
    if number == "10":
        for cell in ("text-9", "text-13", "text-17", "text-21", "text-30", "text-34", "text-40"):
            edit(cell, pt=8.0, dy=6)
    if number == "11":
        edit("text-14", lines="Spannungs-\nregler")
        edit("text-17", pt=7.8, dy=-6)
        edit("text-18", pt=8.0, dy=5)
        edit("text-10", pt=7.8, lines="im gepaarten\nVersuch", y=421)
        edit("text-21", pt=8.0, y=439)
        edit("text-22", pt=7.7, lines="Getrennte\nVersorgungspfade", y=511)
    if number == "12":
        edit("node-21", pt=7.5, dy=-8)
        for cell, no in (("text-27", 1), ("text-30", 2), ("text-33", 3)):
            edit(cell, pt=7.5, lines=f"Rand-\nknoten\n{no}", y=290)
        edit("text-24", pt=8.0, y=510)
        edit("text-36", pt=8.0, y=478)
        edit("text-37", pt=8.0, y=536)
        edit("text-49", pt=7.4, lines="Unterschiede der\nWerkzeugketten\nDMA / Kopien /\nDatenanordnung", y=526)
    if number == "13":
        edit("text-13", pt=7.5, x=54)
        edit("text-33", pt=7.5, x=54)
        edit("text-43", pt=8.0)
    if number == "14":
        edit("text-9", dy=-12)
        edit("text-21", dy=-12)
        edit("text-10", y=357)
        edit("text-22", y=357)
        edit("text-14", pt=8.0, dy=5)
        edit("text-17", pt=8.0, dy=-9)
        edit("text-18", pt=7.8, lines="Synchronisation +\nWarteschlangen", y=459)
        edit("text-6", pt=8.0)
    if number == "15":
        edit("text-10", pt=8.0, lines="Vor-\nverarbeitung", y=254)
        edit("text-11", pt=7.8, lines="Dekodieren /\nSkalieren", y=325)
        edit("text-18", pt=8.0, lines="Nach-\nverarbeitung", y=254)
        edit("text-19", pt=7.8, lines="NMS /\nObjektverfolgung", y=325)
        edit("text-28", pt=7.8, lines="Flexible\nRechenroutinen", y=490)
        edit("text-31", pt=7.8, lines="Irreguläre\nOperationen", y=490)
        edit("text-21", pt=7.3)
        edit("text-22", pt=7.5, dy=6)
    if number == "16":
        edit("text-11", pt=8.0)
    if number == "17":
        edit("text-8", pt=8.5, lines="ONNX-\nModell", y=245)
        edit("text-9", pt=8.0, y=311)
        edit("text-18", pt=7.3)
        edit("text-21", pt=7.3)
        edit("text-27", pt=7.6, lines="Grenztensor-\ngröße", y=466)
        edit("text-28", pt=7.8, y=518)
        edit("text-30", pt=7.2, dy=-5)
        edit("text-31", pt=7.8, dy=5)
        edit("text-34", pt=8.0, y=453)
        edit("text-35", pt=7.0, lines="Export über\nBedienoberfläche", y=502)
    if number == "24":
        edit("text-44", pt=8.0)
        for cell in ("text-11", "text-15", "text-19", "text-23", "text-27", "text-31"):
            edit(cell, pt=8.0, dy=5)
    if number == "25":
        edit("text-17", pt=7.7, lines="GPU-Werkzeug-\nkette", y=430)
        edit("text-35", y=582)
        edit("text-36", pt=7.8, lines="Warteschlangen,\nSynchronisation, Protokollierung", y=643)
        for cell in ("text-10", "text-24", "text-28"):
            edit(cell, pt=8.0, dy=6)
    if number == "26":
        for cell in ("text-19", "text-23", "text-27", "text-31", "text-53", "text-61"):
            edit(cell, pt=8.0, dy=6)
        edit("text-56", y=360)
        edit("text-57", pt=7.8, lines="Versorgung +\nÜberwachung", y=412)
    if number == "27":
        edit("rail-3", pt=7.8)
    return changes


def sync_drawio_textboxes(svg_tree, draw_tree, source_svg):
    """Make editable label geometry follow SVG line breaks and local offsets.

    Only invisible text boxes change size. Actual colored diagram boxes retain
    their original dimensions and connections.
    """
    def labels(root):
        parents = {c: p for p in root.iter() for c in p}
        result = {}
        for text in root.iter(f"{{{SVG}}}text"):
            ancestor, cell, size, anchor = text, None, None, None
            while ancestor is not None:
                cell = cell or ancestor.get("data-cell-id")
                size = size or ancestor.get("font-size")
                anchor = anchor or ancestor.get("text-anchor")
                ancestor = parents.get(ancestor)
            if cell and size:
                ts = list(text)
                ys = [float(t.get("y", text.get("y", "0"))) for t in ts] if ts else [float(text.get("y", "0"))]
                result[cell] = (text, float(size.removesuffix("px")), anchor or "start", sum(ys)/len(ys))
        return result
    originals = labels(ET.parse(source_svg).getroot())
    updated = labels(svg_tree.getroot())
    for cell in draw_tree.getroot().iter("mxCell"):
        cell_id = cell.get("id")
        if cell_id not in originals or cell_id not in updated:
            continue
        style = cell.get("style", "")
        style = re.sub(r"lineHeight=[^;]*;?", "", style)
        cell.set("style", style + ";lineHeight=1.15;")
        if "strokeColor=none" not in style or "fillColor=none" not in style:
            continue
        geo = cell.find("mxGeometry")
        if geo is None:
            continue
        old_text, old_size, old_anchor, old_middle = originals[cell_id]
        text, size, anchor, middle = updated[cell_id]
        lines = [t.text or "" for t in list(text)] if list(text) else [text.text or ""]
        bold = text.get("font-weight") == "bold" or "fontStyle=1" in style
        font = fitz.Font("hebo" if bold else "helv")
        new_width = max(font.text_length(line, fontsize=size) for line in lines) + 4
        new_height = len(lines) * size * 1.15
        old_width, old_height = float(geo.get("width", "0")), float(geo.get("height", "0"))
        dx = float(text.get("x", "0")) - float(old_text.get("x", "0"))
        dy = middle - old_middle - .35 * (size - old_size)
        x = float(geo.get("x", "0")) + dx
        if anchor == "middle": x += (old_width - new_width) / 2
        if anchor == "end": x += old_width - new_width
        geo.set("x", f"{x:.3f}")
        geo.set("y", f"{float(geo.get('y', '0')) + dy + (old_height-new_height)/2:.3f}")
        geo.set("width", f"{new_width:.3f}")
        geo.set("height", f"{new_height:.3f}")
        cell.set("style", re.sub(r"whiteSpace=[^;]+", "whiteSpace=nowrap", cell.get("style", "")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--working", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--origins", type=Path)
    args = parser.parse_args()
    origins_path = args.origins or args.project / "redaktion/FINAL_FIGURE_ORIGINS.json"
    origins = json.loads(origins_path.read_text())
    selected = [f for f in origins["figures"] if f["source_kind"] == "supplied_drawio7_export"]
    assert len(selected) == 17
    records = []
    for figure in selected:
        number = Path(figure["source_svg"]).name[:2]
        source_svg, = (args.source / "Export_SVG").rglob(number + "_*.svg")
        source_draw, = (args.source / "DrawIO").rglob(number + "_*.drawio")
        svg_tree, draw_tree = ET.parse(source_svg), ET.parse(source_draw)
        changes = correct(svg_tree, draw_tree, number)
        fraction, type_changes = typography(svg_tree, draw_tree, number)
        refinements = refine(svg_tree, draw_tree, number, fraction)
        sync_drawio_textboxes(svg_tree, draw_tree, source_svg)
        work_svg, work_draw = (args.working / path.relative_to(args.source) for path in (source_svg, source_draw))
        for path in (work_svg, work_draw):
            path.parent.mkdir(parents=True, exist_ok=True)
        svg_tree.write(work_svg, encoding="utf-8", xml_declaration=True)
        draw_tree.write(work_draw, encoding="utf-8", xml_declaration=True)
        pdf = args.project / figure["project_asset"]
        pdf.parent.mkdir(parents=True, exist_ok=True)
        old_sha = sha(pdf) if pdf.exists() else None
        command = ["inkscape", str(work_svg), "--export-area-page", "--export-type=pdf", "--export-filename=" + str(pdf)]
        proc = subprocess.run(command, check=True, capture_output=True, text=True)
        doc = fitz.open(pdf)
        assert len(doc) == 1 and not doc[0].get_images()
        page = doc[0]
        text = page.get_text()
        assert "Text is not SVG" not in text
        spans = [s for b in page.get_text("dict")["blocks"] if b["type"] == 0 for line in b["lines"] for s in line["spans"]]
        assert spans, "Export must retain selectable vector text."
        frac = fraction
        display_width = 356.75381 * 72 / 72.27 * frac
        scale = display_width / page.rect.width
        records.append({
            "number": number, "project_asset": figure["project_asset"], "source_language": "Deutsch",
            "source_drawio": str(source_draw), "source_drawio_sha256": sha(source_draw),
            "source_svg": str(source_svg), "source_svg_sha256": sha(source_svg),
            "working_drawio": str(work_draw), "working_drawio_sha256": sha(work_draw),
            "working_svg": str(work_svg), "working_svg_sha256": sha(work_svg),
            "semantic_changes": changes, "rendering_cleanup": "Removed the DrawIO unsupported-SVG-text fallback, if present; actual labels are native SVG text.",
            "typography_changes": type_changes, "recommended_tex_width_fraction": fraction,
            "local_label_refinements": refinements,
            "output_path": str(pdf), "output_sha256": sha(pdf), "prior_manifest_output_sha256": figure["sha256"],
            "export_command": command, "export_stderr": proc.stderr,
            "page_size_pdf_points": [page.rect.width, page.rect.height], "raster_images": 0,
            "fonts": sorted({s["font"] for s in spans}), "measured_tex_width_fraction": frac,
            "text_at_current_tex_size": [{"text": s["text"], "pdf_font_pt": s["size"], "final_font_pt": round(s["size"] * scale, 3)} for s in spans],
            "tex_references": figure["tex_references"], "figure_numbers": figure["figure_numbers"],
        })
    result = {"schema": "german-drawio-figure-export-v1", "date": "2026-10-29", "count": len(records), "gaps": [], "inkscape_version": subprocess.check_output(["inkscape", "--version"], text=True).strip(), "origins_path": str(origins_path), "origins_sha256": sha(origins_path), "figures": sorted(records, key=lambda r: r["number"])}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"exported": len(records), "manifest": str(args.manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
