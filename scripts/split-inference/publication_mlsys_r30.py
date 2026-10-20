"""Current MLSys paper profile, preserving the registered frozen R22 view."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

PROFILE = 'mlsys-r30'
STUDY = Path('results/supplementary-studies/rq2-weighted-20261020')
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def current_schematic(repo, output, numeric_only):
    """Render the maintained author vector; this is not the old R22 schematic."""
    source = repo / 'publications/mlsys/figure1/source.zip'
    with zipfile.ZipFile(source) as archive:
        vector = archive.read('analysis/system_overview.svg')
        provenance = json.loads(archive.read('analysis/system_overview_provenance.json'))
    payload = {'kind': 'conceptual_illustration',
               'source': 'publications/mlsys/figure1/source.zip',
               'archive_sha256': digest(source),
               'svg_sha256': hashlib.sha256(vector).hexdigest(),
               'scope': 'Supported boundary capabilities. Paired measurements use the same single-input cut.',
               'source_provenance': provenance}
    figures = output / 'figures'
    (figures / 'system_overview.json').write_text(json.dumps(payload, indent=2) + '\n')
    if not numeric_only:
        import fitz
        (figures / 'system_overview.svg').write_bytes(vector)
        with fitz.open(stream=vector, filetype='svg') as document:
            raw = document.convert_to_pdf()
        (figures / 'system_overview.pdf').write_bytes(raw)
        with fitz.open(stream=raw, filetype='pdf') as document:
            document[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(
                figures / 'system_overview.png')
    return payload


def verify_profile(repo, broad_output):
    output = broad_output / 'publications' / PROFILE
    old = repo / 'results/split-inference/publications/mlsys-r22/figures/FIGURE_DATA.json'
    assert (output / 'data/frozen_r22_figure_data.json').read_bytes() == old.read_bytes()
    frozen = json.loads(old.read_text())
    yolo = json.loads((output / 'figures/yolov7_h8_case_single_column.json').read_text())
    assert yolo == frozen['yolov7_h8_case']
    r22_checked = 0
    for actual in sorted((broad_output / 'publications/mlsys-r22').rglob('*')):
        if actual.suffix not in ['.csv', '.json', '.tex']:
            continue
        expected = repo / 'results/split-inference' / actual.relative_to(broad_output)
        assert actual.read_bytes() == expected.read_bytes(), f'Frozen R22 data changed: {actual.name}'
        r22_checked += 1
    target = repo / 'results/split-inference/publications' / PROFILE
    checked = []
    for folder in ['figures', 'tables', 'data']:
        for actual in sorted((output / folder).glob('*')):
            if actual.suffix not in ['.csv', '.json', '.tex']:
                continue
            name = actual.relative_to(output)
            assert (target / name).is_file(), f'Missing R30 reference: {name}'
            assert actual.read_bytes() == (target / name).read_bytes(), f'R30 differs: {name}'
            checked.append(str(name))
    return {'result': 'PASS', 'files_checked': len(checked), 'frozen_r22_files_checked': r22_checked,
            'frozen_r22_numerical_payload_unchanged': True, 'yolo_payload_unchanged': True}


def build_profile(repo_root, broad_output, numeric_only=False):
    repo, broad_output = Path(repo_root), Path(broad_output)
    output = broad_output / 'publications' / PROFILE
    output.mkdir(parents=True, exist_ok=True)
    frozen = broad_output / 'publications/mlsys-r22'
    for folder in ['data', 'tables']:
        shutil.copytree(frozen / folder, output / folder, dirs_exist_ok=True)
    # This archival evidence report is already retained by R22. Its original
    # source-machine paths are not repeated in the current publication export.
    (output / 'data/r15_evidence_validation.json').unlink()
    (output / 'data/profile_summary.json').unlink()
    from publication_mlsys_data import build
    from publication_mlsys_figures import render, write_figure_data, PAPER_STYLE, PAPER_PALETTE
    from publication_mlsys_r30_assets import render_weighted, render_yolo_single_column, write_weighted_tables
    context = build(repo, broad_output, output)
    if numeric_only:
        _, payload = write_figure_data(output, context)
    else:
        _, payload = render(output, context, uniform_typography=True, uniform_palette=True)
    assert (output / 'figures/FIGURE_DATA.json').read_bytes() == (frozen / 'figures/FIGURE_DATA.json').read_bytes()
    shutil.copyfile(output / 'figures/FIGURE_DATA.json', output / 'data/frozen_r22_figure_data.json')
    assets = render_yolo_single_column(output, payload['yolov7_h8_case'], numeric_only)
    payload['system_overview'] = current_schematic(repo, output, numeric_only)
    (output / 'figures/FIGURE_DATA.json').write_text(json.dumps(payload, sort_keys=True, indent=2) + '\n')

    weighted_source = repo / 'scripts/supplementary-studies/rq2-weighted-20261020/reproduce.py'
    old_source = repo / 'scripts/supplementary-studies/rq2-all-cuts-20261020/reproduce.py'
    with tempfile.TemporaryDirectory(prefix='mlsys-r30-') as temporary:
        work = Path(temporary)
        weighted = module(weighted_source, 'rq2_weighted_reproduce')
        result = weighted.run(work / 'weighted', repo)
        result['published_comparison'] = weighted.verify_published(work / 'weighted', repo)
        (output / 'data/weighted_validation.json').write_text(json.dumps(result, indent=2) + '\n')
        assets.update(render_weighted(output, work / 'weighted/analysis', numeric_only))
        assets.update(write_weighted_tables(output, work / 'weighted/analysis'))
        # The active historical supplementary views keep their original scope.
        # Their temporary engine logs and duplicate datasets are not published.
        legacy = module(old_source, 'rq2_all_cuts_reproduce')
        with contextlib.redirect_stdout(io.StringIO()):
            legacy.run(work / 'all_cuts', numeric_only=numeric_only, verify=True)
        for stem in ['rq2_generic_selection_loss', 'rq2_native_success', 'rq2_graph_analysis']:
            for ext in ([] if numeric_only else ['pdf', 'svg', 'png']):
                shutil.copyfile(work / 'all_cuts/figures' / f'{stem}.{ext}', output / 'figures' / f'{stem}.{ext}')
        shutil.copyfile(work / 'all_cuts/figures/RQ2_FIGURE_DATA.json', output / 'figures/RQ2_FIGURE_DATA.json')
        for path in (work / 'all_cuts/tables').glob('rq2_search_budget_table.*'):
            shutil.copyfile(path, output / 'tables' / path.name)

    core_assets = json.loads((frozen / 'ASSET_MANIFEST.json').read_text())['assets']
    for asset in core_assets:
        asset['repo_targets'] = ['results/split-inference/publications/' + PROFILE + '/' + p
                                 for p in asset['outputs']]
        if asset['asset_id'] == 'fig:runners':
            asset['generator'] = 'scripts/split-inference/publication_mlsys_r30.py:current_schematic'
            asset['caption'] = payload['system_overview']['scope']
            asset['data_generation'] = 'Maintained author vector source, replacing the frozen R22 schematic.'
    manifest = {'profile': PROFILE, 'frozen_profile': 'mlsys-r22',
        'scope': 'Current paper presentation plus the seven-model weighted analysis; original measurements unchanged.',
        'existing_core_assets': core_assets,
        'core_presentation': 'Shared PAPER_STYLE/PAPER_PALETTE; frozen numerical payload stored in data/frozen_r22_figure_data.json.',
        'schematic_override': payload['system_overview'],
        'existing_rq2_assets': {'generator': str(old_source.relative_to(repo)),
                              'figures': ['rq2_generic_selection_loss', 'rq2_native_success', 'rq2_graph_analysis'],
                              'tables': ['rq2_search_budget_table'], 'scope': 'Unchanged separate current/historical cohorts.'},
        'new_assets': assets, 'study': str(STUDY),
        'numeric_only': numeric_only}
    (output / 'ASSET_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'data/profile_summary.json').write_text(json.dumps({
        'profile': PROFILE, 'frozen_numerical_profile': 'mlsys-r22',
        'weighted_scope': result['scope'], 'weighted_weights': result['weights'],
        'new_asset_ids': sorted(assets), 'measurement_changes': False,
        'old_evidence_reference': 'results/split-inference/publications/mlsys-r22/data/r15_evidence_validation.json'
    }, indent=2) + '\n')
    sources = [HERE / 'publication_mlsys_r30.py', HERE / 'publication_mlsys_r30_assets.py',
               HERE / 'publication_mlsys_figures.py', weighted_source, old_source]
    provenance = {'schema': 'mlsys-r30-publication-v1', 'paper_style': PAPER_STYLE,
        'paper_palette': PAPER_PALETTE, 'measurement_changes': False,
        'source_sha256': {str(p.relative_to(repo)): digest(p) for p in sources},
        'input_sha256': {str(STUDY / 'inputs/MANIFEST.json'): digest(repo / STUDY / 'inputs/MANIFEST.json'),
                         'publications/mlsys/figure1/source.zip': digest(repo / 'publications/mlsys/figure1/source.zip')},
        'output_sha256': {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
                          if p.is_file() and p not in [output / 'PROVENANCE.json', output / 'README.md']}}
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (output / 'README.md').write_text('''# MLSys R30 paper assets

Generated with `python -I -B scripts/split-inference/reproduce.py --publication mlsys-r30 --output <empty-directory> --verify`.
Add `--numeric-only` to omit image rendering. The default registered R22 profile remains unchanged.

The core measurement figures use the common paper style and their frozen R22 numerical data.
The author boundary illustration is regenerated from its maintained vector source.
Both wide and single-column YOLOv7 case figures are included, with identical numbers.
The weighted figure and tables use all 187 quality-eligible measured pairs in 21 groups.
Optimized weights are fitted on all seven models; held-out results exclude one entire model at a time.
The new main weighted figure has no Random curve. Existing historical supplementary evidence keeps its original scope.

Inputs, operation rules, fold memberships, exact results and sensitivity checks are in
`results/supplementary-studies/rq2-weighted-20261020`.
`ASSET_MANIFEST.json` maps assets to generators. `PROVENANCE.json` records hashes.
''')
    return manifest
