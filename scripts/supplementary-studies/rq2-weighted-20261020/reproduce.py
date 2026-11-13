#!/usr/bin/env python3
"""Rebuild current seven-model weighted rankings from compact offline inputs."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = Path('results/supplementary-studies/rq2-weighted-20261020')
SOURCE_COMMIT = 'd323645da002b5e24949d6106429c078e509a00b'
sys.path.insert(0, str(HERE))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack_inputs(repo, destination):
    folder = repo / STUDY / 'inputs'
    manifest = json.loads((folder / 'MANIFEST.json').read_text())
    archive = folder / manifest['archive']
    assert digest(archive) == manifest['archive_sha256'], 'Changed graph input archive'
    expected = {row['path']: row for row in manifest['members']}
    with zipfile.ZipFile(archive) as stream:
        assert set(stream.namelist()) == set(expected), 'Unexpected archive member'
        for name, row in expected.items():
            target = destination / name
            assert target.resolve().is_relative_to(destination.resolve())
            raw = stream.read(name)
            assert hashlib.sha256(raw).hexdigest() == row['sha256']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    return manifest


def verify_published(output, repo=REPO):
    reference = repo / STUDY
    checked = []
    for folder in ['analysis', 'features']:
        for actual in sorted((output / folder).rglob('*')):
            if not actual.is_file():
                continue
            name = actual.relative_to(output)
            expected = reference / name
            assert expected.is_file(), f'Missing published reference: {name}'
            assert actual.read_bytes() == expected.read_bytes(), f'Reproduction differs: {name}'
            checked.append(str(name))
    assert checked, 'No numerical artifacts checked'
    return {'result': 'PASS', 'files_checked': len(checked), 'files': checked,
            'mode': 'Exact scientific CSV/JSON and derived-feature comparison'}


def run(output, repo=REPO, verify=False):
    output, repo = Path(output).resolve(), Path(repo).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    import augment_graph_features
    import analyze_weighted
    import check_sensitivity
    with tempfile.TemporaryDirectory(prefix='rq2-weighted-') as temporary:
        work = Path(temporary)
        manifest = unpack_inputs(repo, work / 'source')
        # Engines print detailed reports. Their data files are the public record;
        # temporary paths and execution logs are deliberately not published.
        with contextlib.redirect_stdout(io.StringIO()):
            augment_graph_features.main(work / 'source', work / 'derived')
            analyze_weighted.run(repo, work / 'derived', output / 'analysis')
            check_sensitivity.run(repo, work / 'derived', output / 'analysis')
        features = output / 'features'
        features.mkdir()
        for name in ['graph_boundary_features.csv', 'normalization_universes.json',
                     'validation.json', 'node_operation_audit.json',
                     'added_operation_nodes.json', 'provenance.json']:
            shutil.copyfile(work / 'derived' / name, features / name)
    summary = json.loads((output / 'analysis/summary.json').read_text())
    assert summary['scope']['evaluated_quality_pairs'] == 187
    assert summary['scope']['classifier_pairs'] == 151
    assert summary['scope']['detector_pairs'] == 36
    assert summary['scope']['model_device_groups'] == 21
    assert len(summary['folds']) == 7
    assert summary['validation']['fold_model_disjoint']
    assert not summary['validation']['missing_features_imputed']
    sources = sorted(HERE.glob('*.py'))
    provenance = {
        'schema': 'rq2-weighted-reproduction-v1', 'source_baseline_commit': SOURCE_COMMIT,
        'generator': str(HERE.relative_to(repo) / 'reproduce.py'),
        'operation_proxy_version': augment_graph_features.VERSION,
        'original_graph_input_manifest': str(STUDY / 'inputs/MANIFEST.json'),
        'original_archive_sha256': manifest['archive_sha256'],
        'source_sha256': {str(p.relative_to(repo)): digest(p) for p in sources},
        'measurement_inputs_sha256': summary['repo_input_sha256'],
        'derived_sha256': {str(p.relative_to(output)): digest(p)
                           for p in sorted(output.rglob('*')) if p.is_file()},
        'scope': '187 quality-eligible measured pairs in 21 equal model/device groups. '
                 'Seven whole-model holdouts. The pooled optimum is explicitly in-sample. '
                 'The operation extension is a new analytic proxy, not recovered historical rules.',
        'deduplication': 'Original graph inputs, bindings, license and capture provenance exist once '
                         'in the compact input archive. Derived sensitivity features are temporary; '
                         'their fixed-weight ranking checks are exported in analysis.',
    }
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    result = {'scope': summary['scope'], 'weights': summary['pooled_fit']['selected']['weights'],
              'model_holdout_folds': len(summary['folds']), 'validation': summary['validation']}
    if verify:
        result['published_comparison'] = verify_published(output, repo)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output, verify=args.verify), indent=2))
