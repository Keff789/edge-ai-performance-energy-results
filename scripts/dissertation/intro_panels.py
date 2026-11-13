#!/usr/bin/env python3
"""Export standalone EN/DE panels from the author-supplied MLSys overview.

The source geometry and photograph come from the editable paper figure. Only
panel headings, viewport, physical size and German labels change. This offline
renderer does not use measurement data or modify the submitted paper assets.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'publications/dissertation/intro-panels/source'
SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
PANELS = {
    'urecs_modular_hardware': {
        'heading': '(a) Modular u.RECS hardware', 'viewbox': [20, 52, 330, 346], 'width_in': 3.0,
        'de': 'Modulare u.RECS-Trägerplatine. Die Markierungen zeigen die vorgesehenen Positionen für SMARC, Jetson NX und KI-Beschleunigermodule.',
        'en': 'Modular u.RECS carrier board. The overlays identify the intended locations for SMARC, Jetson NX and AI accelerator modules.',
    },
    'accelerator_gpu_execution': {
        'heading': '(b) Evaluated execution', 'viewbox': [358, 40, 634, 137], 'width_in': 4.9,
        'de': 'Ausführung einer Inferenz auf Beschleuniger und GPU. Das Präfix läuft auf dem externen Beschleuniger. Seine Grenztensoren gelangen über PCIe in Host-Puffer und anschließend per CUDA-Transfer zum TensorRT-Suffix. Die erforderliche Nachverarbeitung gehört zur Fertigstellung des Ergebnisses.',
        'en': 'Accelerator–GPU inference. The external accelerator executes the prefix. Its boundary tensors pass through PCIe and host buffers before a CUDA transfer to the TensorRT suffix. Completing the result includes the required output processing.',
    },
    'runner_interfaces': {
        'heading': '(c) Runner interfaces', 'viewbox': [358, 232, 634, 163], 'width_in': 4.9,
        'de': 'Unterstützte Tensorgrenzen von Generic und Native. Generic verbindet Teilgraphen mit einem oder mehreren Grenztensoren. Die aktuelle Native-Implementierung erwartet genau einen Eingang des GPU-Suffixes. Die Beispiele zeigen unterschiedliche mögliche Schnitte. Im gepaarten Vergleich verwenden beide Ausführungsmodule denselben kompatiblen Schnitt.',
        'en': 'Boundary interfaces supported by Generic and Native. Generic connects subgraphs with one or several boundary tensors. The current Native implementation accepts exactly one GPU-suffix input. These examples show different possible cuts; the paired comparison uses the same compatible cut in both runners.',
    },
}
GERMAN = {
    'AI': 'KI-', 'accel.': 'Modul', 'AI accel.': 'KI-Modul',
    'Prepared input': 'Vorbereitete Eingabe', 'Accelerator': 'Beschleuniger',
    'prefix': 'Präfix', 'buffers': 'Puffer', 'GPU suffix': 'GPU-Suffix',
    'Task': 'Ergebnis', 'completion': 'fertigstellen',
    'CUDA transfer': 'CUDA-Transfer', 'Input': 'Eingabe',
    '2 tensors': '2 Tensoren', '1 tensor': '1 Tensor',
}
UNCHANGED = {'SMARC', 'CPU/FPGA', 'Jetson NX', 'CPU/GPU', 'Jetson Orin NX',
             'Host', 'TensorRT', 'PCIe', 'Generic', 'Native', 'GPU'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_source(source):
    provenance = json.loads((source / 'SOURCE.json').read_text())
    if digest(source / 'mlsys_figure1.svg') != provenance['svg_sha256']:
        raise ValueError('Author SVG source changed; review the source mapping first')
    if digest(source / 'urecs_board_original.png') != provenance['image_sha256']:
        raise ValueError('Author photograph changed')
    root = ET.parse(source / 'mlsys_figure1.svg').getroot()
    headings = [e.text for e in root if e.tag == f'{{{SVG}}}text' and (e.text or '').startswith(('(a)', '(b)', '(c)'))]
    if headings != [v['heading'] for v in PANELS.values()]:
        raise ValueError('Unexpected source panel boundaries')
    # The original photograph remains losslessly available in source/. JPEG
    # encoding keeps figure PDFs compact, without resampling the photograph.
    image_bytes = io.BytesIO()
    with Image.open(source / 'urecs_board_original.png') as photograph:
        photograph.convert('RGB').save(image_bytes, format='JPEG', quality=95,
                                       subsampling=0, optimize=True)
    return root, image_bytes.getvalue(), provenance


def panel_svg(root, panel, language, image_bytes):
    spec = PANELS[panel]
    children = list(root)
    start = next(i for i, e in enumerate(children) if e.text == spec['heading']) + 1
    end = next((i for i in range(start, len(children))
                if children[i].tag == f'{{{SVG}}}text'
                and (children[i].text or '').startswith(('(a)', '(b)', '(c)'))), len(children))
    x, y, width, height = spec['viewbox']
    physical_width = 72 * spec['width_in']
    result = ET.Element(f'{{{SVG}}}svg', {
        'version': '1.1', 'width': f'{physical_width:.6f}pt',
        'height': f'{physical_width * height / width:.6f}pt',
        'viewBox': f'{x} {y} {width} {height}',
        'role': 'img', 'aria-label': spec[language],
    })
    result.append(ET.Element(f'{{{SVG}}}rect', {
        'x': str(x), 'y': str(y), 'width': str(width), 'height': str(height), 'fill': 'white'}))
    if panel == 'urecs_modular_hardware':
        result.append(copy.deepcopy(next(e for e in children if e.tag == f'{{{SVG}}}defs')))
    for original in children[start:end]:
        element = copy.deepcopy(original)
        if element.tag == f'{{{SVG}}}image':
            key = next(k for k in element.attrib if k.endswith('href'))
            element.set(key, 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode())
        if element.tag == f'{{{SVG}}}text' and language == 'de':
            text = element.text or ''
            if text not in GERMAN and text not in UNCHANGED:
                raise ValueError(f'Unmapped source label: {text}')
            element.text = GERMAN.get(text, text)
            if text == 'Prepared input':
                # German is longer. Two lines retain the source arrow and box.
                element.text = 'Vorbereitete'
                element.set('y', '58.4')
                result.append(element)
                element = copy.deepcopy(element)
                element.text = 'Eingabe'
                element.set('y', '77.4')
            elif text == 'Input':
                # Keep the longer German label inside its half of the panel.
                element.set('x', str(float(element.get('x')) - 6))
                element.set('text-anchor', 'start')
        result.append(element)
    ET.register_namespace('', SVG)
    ET.register_namespace('xlink', XLINK)
    return ET.tostring(result, encoding='utf-8', xml_declaration=True)


def export_panel(svg, directory, panel, language):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f'{panel}.svg').write_bytes(svg)
    with fitz.open(stream=svg, filetype='svg') as vector:
        pdf_bytes = vector.convert_to_pdf()
    with fitz.open(stream=pdf_bytes, filetype='pdf') as document:
        document.set_metadata({'title': PANELS[panel][language],
                               'creator': 'intro_panels.py; author-supplied MLSys SVG'})
        if len(document) != 1:
            raise ValueError('Each figure must have one page')
        pdf = directory / f'{panel}.pdf'
        pdf.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
        document[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).save(directory / f'{panel}.png')
    (directory / f'{panel}_caption.tex').write_text(PANELS[panel][language] + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--languages', nargs='+', choices=['en', 'de'], default=['en', 'de'])
    args = parser.parse_args()
    root, image_bytes, provenance = load_source(args.source)
    languages = list(dict.fromkeys(args.languages))
    for language in languages:
        for panel in PANELS:
            export_panel(panel_svg(root, panel, language, image_bytes),
                         args.output / 'artifacts' / language / 'figures', panel, language)
    lines = ['# Standalone hardware and runtime illustrations', '',
             'The three panels reuse the author-supplied editable MLSys Figure 1. '
             'The original paper figure is unchanged. Each standalone panel has a '
             'matching English/German export and no panel letter or internal figure heading.', '',
             '| Panel | Natural width | Files |', '|---|---:|---|']
    for panel, spec in PANELS.items():
        links = ' · '.join(f'[{language.upper()} PDF](artifacts/{language}/figures/{panel}.pdf)' for language in languages)
        lines.append(f'| {panel} | {spec["width_in"]:.1f} in | {links} |')
    lines += ['', 'The SVG source retains the original vector geometry and references '
              'the original photograph in a separate lossless PNG. Exports encode that '
              'photograph as JPEG at quality 95 without resampling; annotations remain vectors. '
              'German labels are translated locally, including one line break for prepared input. '
              'The hardware overlays indicate module locations on an unpopulated carrier.', '',
              '```sh', 'python3 scripts/dissertation/intro_panels.py --output local-output/intro-panels --languages en de',
              '```', '', 'Only the finished PDFs are needed by the dissertation. Source files and this generator stay in the Results repository.', '']
    (args.output / 'README.md').write_text('\n'.join(lines))
    manifest = {'schema': 'standalone-mlsys-panels-v1', 'languages': languages,
                'generator': {'path': 'scripts/dissertation/intro_panels.py', 'sha256': digest(__file__)},
                'source': provenance, 'panel_geometry': PANELS,
                'rendered_photo_jpeg_sha256': hashlib.sha256(image_bytes).hexdigest(),
                'outputs': [{'path': str(p.relative_to(args.output)), 'sha256': digest(p)}
                            for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json']}
    (args.output / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'complete', 'panels': list(PANELS), 'languages': languages, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
