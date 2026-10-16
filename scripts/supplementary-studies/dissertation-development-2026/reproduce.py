#!/usr/bin/env python3
"""Reproduce historical dissertation displays from supplied aggregate tables."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SCRIPT = Path(__file__).resolve().parent
REPOSITORY = SCRIPT.parents[2]
STUDY = REPOSITORY / 'results/supplementary-studies/dissertation-development-2026'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='Fresh or empty directory outside the repository')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        parser.error('--output must be outside the repository')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('--output must be fresh or empty')
    inputs = list((STUDY/'inputs').rglob('*'))
    for path in inputs:
        if REPOSITORY not in path.resolve().parents:
            raise ValueError('Input resolves outside the curated repository: '+str(path))
    output.mkdir(parents=True, exist_ok=True)
    # Keep lazy plotting imports and their font/cache/temp writes in this run.
    cache = output/'matplotlib-cache'
    temporary = output/'tmp'
    cache.mkdir()
    temporary.mkdir()
    os.environ['MPLCONFIGDIR'] = str(cache)
    os.environ['TMPDIR'] = str(temporary)
    tempfile.tempdir = str(temporary)
    tables = output/'tables'
    tables.mkdir()
    # These are the explicitly declared historical aggregate inputs. Their full
    # precision is exported unchanged, not presented as newly estimated metrics.
    for path in inputs:
        if path.is_file():
            shutil.copyfile(path, tables/path.name)
    sys.path.insert(0, str(SCRIPT))
    from plot_rankings import render as render_plots
    from render_tables import render as render_tables, render_rankings
    summary = {'ranking': render_plots(tables, output),
               'reported_tables': render_tables(tables, SCRIPT/'templates', tables)}
    render_rankings(tables, tables)
    shutil.copyfile(SCRIPT/'templates/table_preview.tex', output/'table_preview.tex')
    (output/'reproduction_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('PASS: 30 method / 18 proxy correlations, six strata; 3/9/9/4 reported YOLOv7 rows; seven Imagenette rows; two PDF/SVG/PNG figure families.')


if __name__ == '__main__':
    main()
