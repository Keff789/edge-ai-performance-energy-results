"""German labels for the maintained author vector schematic.

The source contains outlined glyphs rather than SVG text. Only explicitly
recognized, visible glyph runs are replaced. Diagram paths, arrows, nodes,
colors, clipping paths, and the English source archive remain unchanged.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
SOURCE = Path('publications/mlsys/figure1/source.zip')
MEMBER = 'analysis/system_overview.svg'

# Generic, Native, and GPU are names used identically in both languages.
LABELS = {
    'Broad exploration': 'Breite Suche',
    'Accelerator': 'Beschleuniger',
    'Task ': 'Aufgaben-',
    'Completion': 'abschluss',
    'Input': 'Eingabe',
    '2 tensors': '2 Tensoren',
    'Common implementation:single-or multi-tensor boundaries':
        'Gemeinsame Implementierung: ein oder mehrere Grenztensoren',
    'Deployment measurement': 'Messung im Zielsystem',
    '1 tensor': '1 Tensor',
    'One suffix input:custom model-and backend-specific integration':
        'Ein Suffix-Eingang: modell- und backendspezifische Integration',
}
EXPECTED_COUNTS = {
    'Broad exploration': 1, 'Accelerator': 2, 'Task ': 2,
    'Completion': 2, 'Input': 2, '2 tensors': 1,
    'Common implementation:single-or multi-tensor boundaries': 1,
    'Deployment measurement': 1, '1 tensor': 1,
    'One suffix input:custom model-and backend-specific integration': 1,
}


def _matrix(element):
    value = element.get('transform', '')
    if not value.startswith('matrix(') or not value.endswith(')'):
        raise ValueError('Expected an explicit glyph matrix in schematic source')
    numbers = [float(v) for v in re.split(r'[,\s]+', value[7:-1].strip())]
    if len(numbers) != 6:
        raise ValueError('Invalid schematic glyph matrix')
    return numbers


def _visible_runs(root):
    width, height = (float(root.get(key)) for key in ('width', 'height'))
    baselines = defaultdict(list)
    for element in root.iter():
        if element.tag != f'{{{SVG}}}use' or 'data-text' not in element.attrib:
            continue
        a, b, c, d, x, y = _matrix(element)
        if not (0 <= x < width and 0 < y < height):
            continue
        if b or c or a <= 0 or d >= 0:
            raise ValueError('Unrecognized visible glyph orientation')
        baselines[round(y, 3)].append((x, element))
    runs = []
    for _, items in sorted(baselines.items()):
        run, previous = [], None
        for x, element in sorted(items, key=lambda item: item[0]):
            if previous is not None and x - previous > 15:
                runs.append(run)
                run = []
            run.append(element)
            previous = x
        if run:
            runs.append(run)
    return runs


def _new_label(run, original, translated):
    # TextPath uses the bundled DejaVu Sans, then writes actual outlines. Thus
    # subsequent SVG/PDF readers need no particular installed UI font.
    from matplotlib.font_manager import FontProperties
    from matplotlib.path import Path as MplPath
    from matplotlib.textpath import TextPath
    from matplotlib.transforms import Affine2D

    size, _, _, _, x, baseline = _matrix(run[0])
    last = _matrix(run[-1])
    center = (x + last[4] + 0.5 * size) / 2
    anchor = 'center'
    limit = 44.0
    if original in ('Broad exploration', 'Deployment measurement'):
        center, anchor, limit = 225.0, 'right', 126.0
    elif original == 'Input':
        center, anchor, limit = x, 'left', 20.0
    elif original in ('Task ', 'Completion'):
        center, limit = 212.4, 31.0
    elif original.startswith(('Common implementation:', 'One suffix input:')):
        center, anchor, limit = x, 'left', 228.0
    elif original in ('2 tensors', '1 tensor'):
        limit = 36.0
    font = FontProperties(family='DejaVu Sans', size=size)
    path = TextPath((0, 0), translated, prop=font, size=size)
    bounds = path.get_extents()
    scale = min(1.0, limit / bounds.width)
    # Scale uniformly only where necessary, preserving glyph proportions.
    used_width = bounds.width * scale
    left = center if anchor == 'left' else center - used_width
    if anchor == 'center':
        left = center - used_width / 2
    mapped = path.transformed(Affine2D().scale(scale, -scale).translate(
        left - bounds.x0 * scale, baseline))
    commands = []
    for vertices, code in mapped.iter_segments(curves=True, simplify=False):
        if code == MplPath.CLOSEPOLY:
            commands.append('Z')
        else:
            letter = {MplPath.MOVETO: 'M', MplPath.LINETO: 'L',
                      MplPath.CURVE3: 'Q', MplPath.CURVE4: 'C'}[code]
            commands.append(letter + ' '.join(f'{v:.6f}' for v in vertices))
    element = ET.Element(f'{{{SVG}}}path', {
        'd': ' '.join(commands), 'fill': run[0].get('fill', '#000000'),
        'aria-label': translated, 'data-original-label': original,
        'data-language': 'de',
    })
    geometry = mapped.get_extents()
    if geometry.x0 < 0 or geometry.x1 > 236.07 or geometry.y0 < 0 or geometry.y1 > 185:
        raise ValueError(f'German schematic label exceeds canvas: {translated}')
    return element, {
        'source': original, 'translation': translated,
        'baseline': baseline, 'font_size': float(size * scale),
        'bounds': [float(geometry.x0), float(geometry.y0),
                   float(geometry.x1), float(geometry.y1)],
    }


def render_schematic(repo: Path, output_figures: Path) -> dict:
    """Write German ``system_overview`` SVG/PDF/PNG and return provenance.

    No input is rewritten. The returned metadata belongs in the caller's
    localization manifest alongside the unchanged numerical source payloads.
    """
    import fitz
    repo, output_figures = Path(repo), Path(output_figures)
    archive_path = repo / SOURCE
    with zipfile.ZipFile(archive_path) as archive:
        source = archive.read(MEMBER)
    root = ET.fromstring(source)
    parents = {element: parent for parent in root.iter() for element in parent}
    label_group = ET.Element(f'{{{SVG}}}g', {'id': 'german-labels', 'aria-label':
        'Generic und Native: unterstützte Schnittstellen'})
    observed, records, removed = defaultdict(int), [], 0
    for run in _visible_runs(root):
        original = ''.join(element.attrib['data-text'] for element in run)
        if original in {'Generic', 'Native', 'GPU'}:
            continue
        if original not in LABELS:
            raise ValueError(f'Untranslated visible schematic label: {original!r}')
        element, record = _new_label(run, original, LABELS[original])
        label_group.append(element)
        records.append(record)
        observed[original] += 1
        for glyph in run:
            parents[glyph].remove(glyph)
            removed += 1
    if dict(observed) != EXPECTED_COUNTS:
        raise ValueError(f'Schematic labels changed: {dict(observed)!r}')
    root.append(label_group)
    ET.register_namespace('', SVG)
    ET.register_namespace('xlink', XLINK)
    localized = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    output_figures.mkdir(parents=True, exist_ok=True)
    svg = output_figures / 'system_overview.svg'
    pdf = output_figures / 'system_overview.pdf'
    png = output_figures / 'system_overview.png'
    svg.write_bytes(localized)
    with fitz.open(stream=localized, filetype='svg') as document:
        pdf.write_bytes(document.convert_to_pdf())
    with fitz.open(pdf) as document:
        if len(document) != 1:
            raise ValueError('Schematic must have exactly one page')
        document[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(png)
    return {
        'schema': 'german-author-schematic-v1', 'language': 'de',
        'source_archive': SOURCE.as_posix(), 'source_member': MEMBER,
        'source_archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'source_svg_sha256': hashlib.sha256(source).hexdigest(),
        'font': 'Matplotlib-bundled DejaVu Sans, embedded vector outlines',
        'canvas': [236.07, 185.0], 'replaced_glyphs': removed,
        'labels': records,
        'geometry_policy': 'Only recognized visible label glyphs replaced; diagram geometry unchanged.',
        'output_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (svg, pdf, png)},
    }
