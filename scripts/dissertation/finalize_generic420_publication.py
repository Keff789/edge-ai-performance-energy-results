#!/usr/bin/env python3
"""Index existing English dissertation sources and verify the final bilingual build."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    repo = args.repo.resolve()
    active = repo / 'results/publication-builds/generic420-20261027'
    paper = active / 'paper'
    rq2 = repo / 'results/supplementary-studies/rq2-native-scope-20261027'
    rq3 = repo / 'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'
    archived = paper / 'publications/mlsys-r22/data/r15_evidence_validation.json'
    archived_source = repo / 'results/split-inference/publications/mlsys-r22/data/r15_evidence_validation.json'
    assert archived.read_bytes() == archived_source.read_bytes()
    if not archived.is_symlink():
        archived.unlink()
        archived.symlink_to(os.path.relpath(archived_source, archived.parent))
    de = json.loads((active / 'dissertation-de/ASSET_MANIFEST.json').read_text())
    english_assets = {}
    for kind in ['figures', 'tables']:
        for asset in de[kind]:
            source = repo / asset['source']
            assert source.is_file(), asset['source']
            assert sha(source) == asset['source_sha256'], asset['source']
            english_assets[asset['source']] = {'sha256': sha(source), 'bundle': asset['bundle'], 'kind': kind}
    for source in sorted((paper / 'rq3-generic420/en').rglob('*')):
        if source.is_file():
            english_assets[str(source.relative_to(repo))] = {'sha256': sha(source), 'bundle': 'rq3-generic420', 'kind': 'localized_artifact'}
    english = active / 'dissertation-en'
    manifest = {'schema': 'dissertation-english-source-index-v1', 'language': 'en',
        'scope': 'Complete English split-inference, current and frozen paper profiles, registered dissertation supplements, and corrected Generic420 artifacts.',
        'source_policy': 'English assets use the existing English renderers and recorded supplementary exports; the German translation does not alter their measurements.',
        'current_rq2_study': str(rq2.relative_to(repo)), 'current_rq3_study': str(rq3.relative_to(repo)),
        'files': dict(sorted(english_assets.items()))}
    write(english / 'ASSET_MANIFEST.json', manifest)
    lines = ['# English dissertation figures and tables', '',
        'The complete English split and paper build is in [paper](../paper). The same current RQ2 and corrected RQ3 studies feed the English and German outputs. Original RQ1, Native, Full and energy observations retain their recorded values.', '',
        'The source index below links the existing English artifacts for every registered dissertation bundle. Historical supplementary studies keep their own populations and captions. `ASSET_MANIFEST.json` records each selected file and its SHA256.', '',
        '| Bundle | Files | Source |', '|---|---:|---|']
    for bundle in sorted({entry['bundle'] for entry in english_assets.values()}):
        files = [repo / name for name, entry in english_assets.items() if entry['bundle'] == bundle]
        common = Path(os.path.commonpath([str(path.parent) for path in files]))
        lines.append(f'| {bundle} | {len(files)} | [English artifacts]({os.path.relpath(common, english)}) |')
    lines += ['', 'The [German dissertation export](../dissertation-de/README.md) records translation coverage and numerical checks. Both wide and single-column YOLOv7 b066 figures use the frozen original values.', '',
        'Recreate this source index and the integration verification after the normal paper and German dissertation builds:', '',
        '```sh', 'python -I -B scripts/dissertation/finalize_generic420_publication.py', '```', '',
        'The complete preceding commands, including both `--rq2-study` and `--generic420-study`, are recorded in [INTEGRATION_VALIDATION.json](../INTEGRATION_VALIDATION.json).', '']
    (english / 'README.md').write_text('\n'.join(lines))
    frozen = repo / 'results/split-inference/publications/mlsys-r22'
    checked = []
    for actual in sorted((paper / 'publications/mlsys-r22').rglob('*')):
        if actual.suffix in ['.csv', '.json', '.tex']:
            assert actual.read_bytes() == (frozen / actual.relative_to(paper / 'publications/mlsys-r22')).read_bytes(), str(actual)
            checked.append(str(actual.relative_to(paper)))
    original_yolo = json.loads((frozen / 'figures/FIGURE_DATA.json').read_text())['yolov7_h8_case']
    r30 = paper / 'publications/mlsys-r30'
    r30_manifest = json.loads((r30 / 'ASSET_MANIFEST.json').read_text())
    for asset in r30_manifest['existing_core_assets']:
        assert asset['repo_targets'] == [str(r30.relative_to(repo) / name) for name in asset['outputs']]
    assert r30_manifest['existing_rq2_assets']['graph_display']['excluded_methods'] == ['uniform_random']
    for source in [r30 / 'figures/rq2_graph_analysis.svg', paper / 'de/mlsys-r30/figures/rq2_graph_analysis.svg', active / 'dissertation-de/mlsys-r30/figures/rq2_graph_analysis.svg']:
        assert 'Random' not in source.read_text() and 'Zufall' not in source.read_text(), str(source)
    assert json.loads((r30 / 'figures/FIGURE_DATA.json').read_text())['yolov7_h8_case'] == original_yolo
    assert json.loads((r30 / 'figures/yolov7_h8_case_single_column.json').read_text()) == original_yolo
    copied_rq2 = []
    for folder in ['data', 'figures', 'tables']:
        for source in sorted((rq2 / folder).glob('*')):
            if source.is_file():
                target = r30 / source.relative_to(rq2)
                assert target.is_file(), str(target)
                if source.suffix in ['.csv', '.json', '.tex', '.md']:
                    assert source.read_bytes() == target.read_bytes(), str(target)
                    copied_rq2.append(str(target.relative_to(repo)))
    assert (r30 / 'data/rq2_final_summary.json').read_bytes() == (rq2 / 'summary.json').read_bytes()
    for base in [paper / 'de', active / 'dissertation-de']:
        audit = json.loads((base / 'TRANSLATION_AUDIT.json').read_text())
        assert not audit['figures']['untranslated'], str(base)
        assert all(not row['report']['untranslated'] for row in audit['tables']), str(base)
        for stem in ['yolov7_h8_case', 'yolov7_h8_case_single_column']:
            for suffix in ['pdf', 'svg', 'png']:
                assert (base / 'mlsys-r30/figures' / f'{stem}.{suffix}').is_file()
    private = []
    for source in active.rglob('*'):
        if source.is_symlink():
            assert source == archived and source.resolve() == archived_source.resolve()
            continue
        if source.suffix in ['.json', '.md', '.tex', '.csv']:
            text = source.read_text()
            if any(token in text for token in ['/home/', '/tmp/', '/mnt/', 'Worktrees/']):
                private.append(str(source.relative_to(repo)))
    assert not private, private[:10]
    rq2_summary = json.loads((rq2 / 'summary.json').read_text())
    rq3_manifest = json.loads((rq3 / 'MANIFEST.json').read_text())
    rq3_verified_files = 0
    for bundle in [paper / 'rq3-generic420', active / 'dissertation-de/rq3-generic420']:
        rendered = json.loads((bundle / 'MANIFEST.json').read_text())
        assert rendered['counts'] == rq3_manifest['counts'], str(bundle)
        for name, expected in rendered['files'].items():
            source = bundle / name
            assert source.resolve().is_relative_to(bundle.resolve())
            assert sha(source) == expected, str(source)
            rq3_verified_files += 1
    report = {'schema': 'bilingual-publication-integration-verification-v1', 'status': 'PASS',
        'rq2_study': str(rq2.relative_to(repo)), 'rq2_input_manifest_sha256': sha(rq2 / 'INPUT_MANIFEST.json'),
        'rq2_summary_sha256': sha(rq2 / 'summary.json'), 'rq2_scope': rq2_summary,
        'rq3_study': str(rq3.relative_to(repo)), 'rq3_manifest_sha256': sha(rq3 / 'MANIFEST.json'),
        'rq3_counts': rq3_manifest['counts'],
        'rq3_manifest_files_verified': rq3_verified_files,
        'frozen_r22_numerical_files_checked': len(checked), 'rq2_current_files_exact': len(copied_rq2),
        'b066_wide_single_numerical_payload_unchanged': True,
        'current_r30_output_targets_verified': True,
        'active_rq2_graph_random_curve_absent': True,
        'b066_points': original_yolo['points'], 'english_dissertation_source_files': len(english_assets),
        'private_paths_found': private, 'new_measurements_by_publication_build': 0,
        'archival_evidence_reference': str(archived_source.relative_to(repo)),
        'finalization_source_sha256': sha(Path(__file__).resolve()),
        'commands': [
            'python -I -B scripts/split-inference/reproduce.py --publication mlsys-r30 --languages en de --rq2-study results/supplementary-studies/rq2-native-scope-20261027 --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027 --output results/publication-builds/generic420-20261027/paper --verify',
            'python -I -B scripts/dissertation/reproduce.py --source results/publication-builds/generic420-20261027/paper --rq2-study results/supplementary-studies/rq2-native-scope-20261027 --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027 --output results/publication-builds/generic420-20261027/dissertation-de --verify',
            'python -I -B scripts/dissertation/finalize_generic420_publication.py']}
    write(active / 'INTEGRATION_VALIDATION.json', report)
    print(json.dumps({key: report[key] for key in ['status', 'frozen_r22_numerical_files_checked', 'rq2_current_files_exact', 'english_dissertation_source_files', 'rq3_counts']}))


if __name__ == '__main__':
    main()
