#!/usr/bin/env python3
"""Additional compact review tables from the source-derived winner export.

Preserves every established publication output. This presentation-only export
does not select deployments, repeat measurements, or change quality admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from build_paper_dataset import emit
from publication_mlsys_data import MODELS, table_view

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'scripts/dissertation'))
from german_tables import translate_markdown, translate_tex

STEM = 'best_cases_quality_table'
LABEL = 'tab:best-cases-quality'
COLUMNS = [
    ('label', 'Model', ''), ('full_label', 'Fastest Full', ''),
    ('full_fps', 'FPS', '.0f'), ('split_label', 'Fastest split', ''),
    ('split_fps', 'FPS', '.0f'), ('throughput_gain_pct', 'FPS gain (%)', '+.1f'),
    ('energy_change_pct', 'Energy change (%)', '+.1f'),
    ('quality_difference_pp', 'Delta q (pp)', '+.2f'),
]
CAPTION = (
    'Fastest measured single-backend Full and split across all setups among configurations '
    'with at most 5% numeric CPU-relative quality loss. Changes use unrounded values. '
    'Energy belongs to these same throughput-selected configurations; negative energy change '
    'means less energy per image. Delta q is split minus Full in percentage points: Top1 '
    'for classifiers and COCO AP50:95 for detectors. Passing the quality threshold does '
    'not establish statistical equivalence. YOLO11l uses Generic; the other selected splits use Native.'
)


def winner_rows(source):
    """Use the upstream selection and retain all full-precision identity fields."""
    rows = [row for row in json.loads(Path(source).read_text())
            if row.get('comparison') == 'global throughput winners']
    if len(rows) != len(MODELS) or [row['model'] for row in rows] != MODELS:
        raise ValueError('Expected one source-selected global winner per model in publication order')
    for row in rows:
        for field in ('full_uid', 'split_uid', 'full_label', 'split_label'):
            if not row.get(field):
                raise ValueError('Missing deployment identity: ' + field)
        for key, _, form in COLUMNS:
            if form and (isinstance(row.get(key), bool)
                         or not isinstance(row.get(key), (int, float))
                         or not math.isfinite(row[key])):
                raise ValueError('Non-finite winner measurement: ' + key)
        if not math.isclose(row['quality_difference_pp'],
                            row['split_quality'] - row['full_quality'], abs_tol=1e-10):
            raise ValueError('Quality delta does not match the selected split and Full')
        if max(row['split_quality_loss'], row['full_quality_loss']) > 5 + 1e-10:
            raise ValueError('Source winner exceeds the 5% relative quality-loss threshold')
        if not math.isclose(row['throughput_gain_pct'],
                            100 * (row['split_fps'] / row['full_fps'] - 1), abs_tol=1e-10):
            raise ValueError('Throughput gain does not match the selected split and Full')
        if not math.isclose(row['energy_change_pct'],
                            100 * (row['split_mj'] / row['full_mj'] - 1), abs_tol=1e-10):
            raise ValueError('Energy change does not match the selected split and Full')
    return rows


def build(source, output, languages=('en', 'de')):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source.parent or output in source.parents:
        raise ValueError('Additional outputs must not replace their source directory')
    rows = winner_rows(source)
    display_rows = [dict(row, split_label=row['split_setup'] + '/' + row['split_case']) for row in rows]
    markdown, tex = table_view(display_rows, COLUMNS, CAPTION, LABEL)
    tex = tex.replace(r'FPS gain (\%)', r'\shortstack{FPS gain\\(\%)}')
    tex = tex.replace(r'Energy change (\%)', r'\shortstack{Energy change\\(\%)}')
    tex = tex.replace('Delta q (pp)', r'\shortstack{$\Delta q$\\(pp)}')
    files = {}
    for language in languages:
        target = output / 'artifacts' / language / 'tables'
        target.mkdir(parents=True, exist_ok=True)
        emit(target / STEM, rows)
        (target / (STEM + '.md')).write_text(
            markdown if language == 'en' else translate_markdown(markdown), encoding='utf-8')
        (target / (STEM + '.tex')).write_text(
            tex if language == 'en' else translate_tex(tex), encoding='utf-8')
        for path in sorted(target.glob(STEM + '.*')):
            files[str(path.relative_to(output))] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        'schema': 'mlsys-review-tables-v1',
        'source': (str(source.relative_to(REPO)) if source.is_relative_to(REPO)
                   else 'tables/r14_winner_quality.json'),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'generator': 'scripts/split-inference/render_review_tables.py',
        'rows': len(rows), 'languages': list(languages),
        'selection': 'source-selected global throughput winners; no reselection',
        'quality_delta': '100*(split q - Full q), in percentage points',
        'full_reference': 'single-backend Full',
        'hardware_measurements': False, 'existing_exports_modified': False,
        'outputs': files,
    }
    (output / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--winner-quality', type=Path,
                        default=REPO / 'results/split-inference/publications/mlsys-r30/tables/r14_winner_quality.json')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--languages', nargs='+', choices=['en', 'de'], default=['en', 'de'])
    args = parser.parse_args()
    result = build(args.winner_quality, args.output, tuple(dict.fromkeys(args.languages)))
    print(json.dumps({'status': 'PASS', 'rows': result['rows'], 'outputs': len(result['outputs'])}))


if __name__ == '__main__':
    main()
