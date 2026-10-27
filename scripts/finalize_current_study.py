#!/usr/bin/env python3
"""Refresh the current study overview and file index after artifact generation."""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLOSURE = REPO / 'results/supplementary-studies/generic420-closeout-20261027'
RQ2 = REPO / 'results/supplementary-studies/rq2-native-scope-20261027'
RQ3 = REPO / 'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'
STAGED = REPO / 'results/supplementary-studies/staged-selection'
BUILD = REPO / 'results/publication-builds/generic420-20261027'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def info(path):
    raw = path.read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-evidence', type=Path,
        help='Fresh current-source/backup closure metadata; required after current observations change.')
    args = parser.parse_args()
    q2, q3 = read(RQ2 / 'summary.json'), read(RQ3 / 'MANIFEST.json')
    integration = read(BUILD / 'INTEGRATION_VALIDATION.json')
    assert integration['status'] == 'PASS'
    assert integration['rq2_summary_sha256'] == info(RQ2 / 'summary.json')['sha256']
    assert integration['rq3_manifest_sha256'] == info(RQ3 / 'MANIFEST.json')['sha256']
    assert integration['staged_selection_manifest_sha256'] == info(STAGED / 'MANIFEST.json')['sha256']
    assert integration['staged_selection_validation']['status'] == 'PASS'
    assert integration['staged_selection_en_de_numerics_identical']
    assert q2['unresolved_candidates'] == q2['corrected_quality_pending'] == 0
    counts = q3['counts']
    assert counts['fps_pending'] == counts['quality_pending_measured'] == 0
    families = [r for r in q2['family_selection_results'] if r['scope'] == 'quality_admitted']
    deployments = read(REPO/'results/split-inference/data/PAPER_DATASET.json')
    current_binding_path = REPO/'results/split-inference/data/current_observation_binding.json'
    current_binding = read(current_binding_path) if current_binding_path.is_file() else {}
    assert not current_binding.get('pending_packages'), 'Declared current measurement packages are still pending'
    current = [row for row in deployments if row.get('current_observation_metric_updates')]
    prior_release = read(CLOSURE/'MANIFEST.json')
    generic_core = prior_release.get('generic420_core', prior_release)
    source_keys = ['ledger_sha256', 'selection_sha256', 'snapshot_id', 'export_manifest_sha256',
        'used_tool_revisions', 'tool_environment', 'raw_preservation_complete']
    release_evidence = None
    if current:
        if args.release_evidence is None:
            raise ValueError('Current observations require fresh --release-evidence; prior snapshot/backup metadata cannot certify new captures')
        release_evidence = read(args.release_evidence)
        if release_evidence.get('raw_preservation_complete') is not False:
            raise ValueError('The accepted historical raw limitation remains false globally; current packages have their own preservation scope')
        if release_evidence['current_dataset_sha256'] != info(REPO/'results/split-inference/data/PAPER_DATASET.json')['sha256']:
            raise ValueError('Release evidence does not bind the current deployment dataset')
        if release_evidence['current_observations_sha256'] != current_binding['observations_sha256']:
            raise ValueError('Release evidence does not bind the current replacement input')
        receipts = release_evidence.get('current_measurement_package_preservation_receipts')
        if release_evidence.get('current_measurement_packages_raw_preserved') is not True or not receipts:
            raise ValueError('Current measurement-package raw preservation is not closed')
        covered = (set(receipts) if isinstance(receipts, dict) else
            {label for receipt in receipts for label in
             ([receipt['package_label']] if receipt.get('package_label') else receipt.get('packages', []))})
        if not set(current_binding.get('expected_packages', [])) <= covered:
            raise ValueError('Current preservation receipts do not cover every declared package')
        if any(release_evidence[key] != generic_core[key] for key in ['ledger_sha256','selection_sha256']):
            raise ValueError('The frozen Generic420 core changed')
        if any(key not in release_evidence for key in source_keys) or not all(release_evidence.get(key)
                for key in source_keys if key != 'raw_preservation_complete'):
            raise ValueError('Current snapshot/tool/source metadata is incomplete')
    capture_count = sum(row.get(metric+'_acquisition_origin') == 'new_capture'
        for row in current for metric in row['current_observation_metric_updates'])
    native_changed = any(row['runner'] == 'native' for row in current)
    energy_changed = any('energy' in row['current_observation_metric_updates'] or
        ('performance' in row['current_observation_metric_updates'] and row.get('energy_source_sha256') is None)
        for row in current)
    b009_current = next((row for row in current if (row['model_id'], row['setup_id'], row['case_id'], row['runner'])
        == ('yolov7_paper', 'H8', 'b009', 'native')), None)
    b009_fresh = bool(b009_current and 'performance' in b009_current['current_observation_metric_updates'])
    labels = {'all': 'All models', 'classification': 'Classifiers', 'detection': 'Detectors'}
    lines = ['# Split selection: current results', '',
        'Seven vision models are evaluated on Jetson Orin NX systems paired with Hailo-8, Hailo-10H or DeepX DX-M1. '
        'The study examines deployment benefits, selection with Generic, and graph-based shortlists. '
        'The [study overview](../../../docs/current-study.md) explains the common design, candidate sets and exclusions.', '',
        '| Question | Data and results |', '|---|---|',
        '| RQ1: When does splitting improve deployment? | [Split and Full comparisons](../../split-inference/tables/fastest_split_baselines.md), including throughput, quality and energy. |',
        f"| RQ2: Can Generic select a fast Native cut? | [Paired comparison](../rq2-native-scope-20261027/README.md) on {q2['original_native_population']} cuts, with {q2['quality_pair_count']} passing the quality rule. |",
        f"| RQ3: How well do graph scores narrow the search? | [Graph-score comparison](../rq3-generic420-detector-corrected-20261027/README.md) on {counts['eligible']} quality-admissible cuts. |", '',
        '## Generic recommendations', '',
        'Each model–device group contributes equally. Loss is measured against its fastest Native cut.', '',
        '| Models | Admitted pairs | Groups | Mean Native loss (%) |', '|---|---:|---:|---:|']
    for row in families:
        lines.append(f"| {labels[row['family']]} | {row['paired_candidates']} | {row['model_device_groups']} | {row['mean_loss_pct']:.4f} |")
    lines += ['', 'The [staged selection analysis](../staged-selection/README.md) combines graph-based preselection, '
        'Generic measurements, and one or two final Native tests. Its budget curves and tables use the same paired candidates.', '']
    lines += ['', '## Coverage and interpretation', '',
        f"The paired set contains {q2['original_native_population']} cuts. The quality rule excludes {q2['excluded_candidates']}. "
        'The broader graph-score set selects 20 cuts per model and accelerator, including multi-tensor boundaries. '
        f"Of {counts['selected']} planned configurations, {counts['fps_measured']} have throughput measurements, "
        f"{counts['technical_excluded']} cannot be executed, and {counts['quality_fail_measured']} measured cuts exceed the quality limit. "
        'The [coverage table](closure_matrix.csv) gives the counts for each group.', '',
        f"Of the paired cuts, {q2['rq3_fixed420_members']} also belong to the {counts['selected']}-candidate set and "
        f"{q2['outside_rq3_fixed420_pairs']} are additional paired cuts. The two sets are not independent totals. "
        'All planned cases are resolved; technical and quality exclusions are completed outcomes.', '',
        'Both selection analyses apply the 5% relative quality-loss rule. RQ2 evaluates Native throughput and RQ3 Generic throughput. '
        'Energy comparisons use measurements of the same runtime configuration. '
        'The [measurement notes](../rq2-native-scope-20261027/DATA_NOTES.md) retain configuration-level source details.', '',
        '## Figures, tables and reproduction', '',
        '[Paper figures and tables](../../publication-builds/generic420-20261027/paper/README.md) · '
        '[German dissertation collection](../../publication-builds/generic420-20261027/dissertation-de/README.md) · '
        '[English dissertation collection](../../publication-builds/generic420-20261027/dissertation-en/README.md)', '',
        'From the repository root:', '', '```bash',
        'python3 scripts/reproduce_current.py --output local-output/current --languages en de', '```', '',
        'The command regenerates the analyses and English/German outputs from the published inputs. '
        'It performs no hardware measurements. Requirements are listed in [the analysis instructions](../../../scripts/README.md).', '',
        'The machine-readable input and output manifests retain source identities. '
        'Earlier profiles and diagnostic experiments are indexed in [the archive](../../../docs/archival_studies.md).', '']
    (CLOSURE / 'README.md').write_text('\n'.join(lines))
    active = read(REPO / 'results/ACTIVE_GENERIC420.json')
    active['status'] = 'complete'
    active.pop('rq2_remaining_gap', None)
    active['measurement_notes'] = str((RQ2 / 'DATA_NOTES.md').relative_to(REPO))
    active['reproduce'] = 'python3 scripts/reproduce_current.py --output local-output/current --languages en de'
    active['staged_selection'] = str(STAGED.relative_to(REPO))
    active['source_snapshot_unchanged'] = not bool(current)
    active['generic420_core_unchanged'] = True
    if release_evidence:
        active['current_source_snapshot_id'] = release_evidence['snapshot_id']
        active['current_observations_sha256'] = release_evidence['current_observations_sha256']
        active['current_dataset_sha256'] = release_evidence['current_dataset_sha256']
        active['generic420_core_snapshot_id'] = generic_core['snapshot_id']
    active['publication_update'] = ('Current source-bound deployment observations, paired comparison and retrospective graph–Generic–Native selection.'
        if current else 'Consolidated paired comparison and retrospective graph–Generic–Native selection; no new hardware measurements.')
    active['current_external_capture_count'] = capture_count
    if current_binding:
        active['current_observation_packages'] = {key:current_binding.get(key, [])
            for key in ['expected_packages', 'accepted_packages', 'pending_packages']}
    active['hardware_measurements_performed_by_generator'] = False
    write(REPO / 'results/ACTIVE_GENERIC420.json', active)
    write(CLOSURE / 'RQ2_VALIDATION.json', {
        'schema': 'rq2-current-validation-v2', 'result': 'PASS',
        'summary_sha256': info(RQ2 / 'summary.json')['sha256'],
        'study_validation': read(RQ2 / 'VALIDATION.json'),
        'original_native_cases': q2['original_native_population'],
        'paired_cases': q2['pair_count'], 'quality_pairs': q2['quality_pair_count'],
        'quality_groups': q2['quality_group_count'], 'quality_excluded': q2['excluded_candidates'],
        'reviewed_metadata_pairs': q2['reviewed_metadata_pairs'],
        'family_selection_results': families,
        'sensitivity': str((RQ2 / 'data/pairing_sensitivity.csv').relative_to(REPO))})
    v3 = read(CLOSURE / 'RQ3_VALIDATION.json')
    v3['manifest_file_hashes'][str((RQ3 / 'MANIFEST.json').relative_to(REPO))] = info(RQ3 / 'MANIFEST.json')['sha256']
    write(CLOSURE / 'RQ3_VALIDATION.json', v3)
    write(CLOSURE / 'PUBLICATION_VALIDATION.json', {
        'schema': 'current-publication-validation-v2', 'status': 'PASS',
        'integration': str((BUILD / 'INTEGRATION_VALIDATION.json').relative_to(REPO)),
        'integration_sha256': info(BUILD / 'INTEGRATION_VALIDATION.json')['sha256'],
        'staged_selection': str(STAGED.relative_to(REPO)),
        'staged_selection_manifest_sha256': info(STAGED / 'MANIFEST.json')['sha256'],
        'RQ1_values_unchanged': not bool(current),
        'b066_values_unchanged': integration['b066_wide_single_numerical_payload_unchanged'],
        'new_hardware_measurements': capture_count > 0,
        'hardware_measurements_performed_by_generator': False,
        'current_external_capture_count': capture_count})
    changes = read(CLOSURE / 'RESULT_CHANGES.json')
    changes['rq2'] = q2
    changes['current_pairing_review'] = str((RQ2 / 'inputs/PAIRING_REVIEW_b009.json').relative_to(REPO))
    changes['current_pairing_sensitivity'] = str((RQ2 / 'data/pairing_sensitivity.csv').relative_to(REPO))
    changes['staged_selection_primary_budgets'] = integration['staged_selection_primary_budgets']
    write(CLOSURE / 'RESULT_CHANGES.json', changes)
    b009 = read(CLOSURE / 'closure_b009.json')
    b009['current_rq2_inclusion'] = {'included': True, 'basis': 'Reviewed executable, runtime and observed-input evidence.',
        'historical_full_recipe_binding_verified': False,
        'review': str((RQ2 / 'inputs/PAIRING_REVIEW_b009.json').relative_to(REPO))}
    if b009_fresh:
        b009['current_rq2_inclusion'].update(basis='New normally admitted Native observation with actual current input/completion binding.',
            current_recipe_binding_verified=True, current_native_binding=b009_current['current_native_binding'],
            historical_review_retained=True)
    write(CLOSURE / 'closure_b009.json', b009)
    manifest = {key:(release_evidence or prior_release)[key] for key in source_keys}
    if release_evidence:
        manifest['generic420_core'] = {key:generic_core[key] for key in
            ['ledger_sha256','selection_sha256','snapshot_id','export_manifest_sha256']}
        manifest['current_source_closure'] = dict(evidence_sha256=info(args.release_evidence)['sha256'],
            current_dataset_sha256=release_evidence['current_dataset_sha256'],
            current_observations_sha256=release_evidence['current_observations_sha256'],
            current_measurement_packages_raw_preserved=True,
            preservation_receipts=release_evidence['current_measurement_package_preservation_receipts'])
        manifest['historical_raw_preservation_limitation'] = release_evidence.get('historical_raw_preservation_limitation',
            prior_release.get('historical_raw_preservation_limitation',
                'Known prior raw limitations are retained in PORTABLE_BACKUP_RECEIPT.json; current package preservation is reported separately.'))
    manifest.update(schema='current-split-study-release-v2', status='complete', counts=counts,
        rq2_counts={'planned': q2['original_native_population'], 'paired': q2['pair_count'],
            'quality_admitted': q2['quality_pair_count'], 'quality_excluded': q2['excluded_candidates'],
            'groups': q2['quality_group_count'], 'unresolved': q2['unresolved_candidates']},
        active_pointer='results/ACTIVE_GENERIC420.json',
        native_full_energy_measurements_unchanged=not (native_changed or energy_changed),
        native_measurements_unchanged=not native_changed, full_measurements_unchanged=True,
        energy_measurements_unchanged=not energy_changed,
        new_hardware_measurements_by_this_update=capture_count > 0,
        hardware_measurements_performed_by_generator=False, current_external_capture_count=capture_count,
        RQ1_YOLOv7_case_numerical_evidence_unchanged=not any(row['model_id']=='yolov7_paper' and row['setup_id']=='H8' for row in current),
        RQ1_b066_numerical_evidence_unchanged=integration['b066_wide_single_numerical_payload_unchanged'],
        source_backup=('Current source closure binds the new metric sources and exact preservation receipts; the frozen Generic420 core is retained separately.'
            if current else 'PORTABLE_BACKUP_RECEIPT.json describes the retained measurement sources, not a new mirror of this publication update.'),
        git_commit_binding='The containing Git commit identifies this publication update.',
        measurement_notes=str((RQ2 / 'DATA_NOTES.md').relative_to(REPO)))
    manifest['staged_selection'] = str(STAGED.relative_to(REPO))
    paths = set()
    for root in [RQ2, RQ3, STAGED, BUILD, CLOSURE]:
        paths.update(p for p in root.rglob('*') if p.is_file() and p != CLOSURE / 'MANIFEST.json'
            and not any(part.startswith('.') or part == '__pycache__' for part in p.relative_to(root).parts))
    broad = REPO/'results/split-inference'
    broad_manifest = broad/'BROAD_GENERATED_MANIFEST.json'
    if current and not broad_manifest.is_file():
        raise ValueError('Current broad generated/input inventory is missing')
    if broad_manifest.is_file():
        paths.add(broad_manifest)
        inventory = read(broad_manifest)
        for prefix, entries in [(broad, inventory['output_files']), (REPO, inventory['input_sources'])]:
            for name, expected in entries.items():
                path = (prefix/name).resolve()
                if not path.is_relative_to(REPO) or not path.is_file() or info(path) != expected:
                    raise ValueError('Current broad file is missing or differs from its inventory: '+name)
                paths.add(path)
    # Exact referenced archive inputs are included without mirroring entire
    # historical study trees or treating them as new measurements.
    for source in read(RQ2/'INPUT_MANIFEST.json')['sources']:
        path = (REPO/source['path']).resolve()
        if path.is_relative_to(REPO) and path.is_file():
            if info(path)['sha256'] != source['sha256']:
                raise ValueError('RQ2 referenced input changed: '+source['path'])
            paths.add(path)
    for name in ['README.md','scripts/README.md','scripts/split-inference/README.md',
            'scripts/split-inference/CURRENT_OBSERVATIONS.md','scripts/split-inference/config.json',
            'scripts/dissertation/README.md','publications/mlsys/README.md','publications/dissertation/README.md',
            'docs/archival_studies.md','docs/current-study.md']:
        if (REPO/name).is_file():
            paths.add(REPO/name)
    for directory in ['scripts/split-inference','scripts/dissertation',
            'scripts/supplementary-studies/rq2-native-scope-20261027',
            'scripts/supplementary-studies/rq3-generic420','scripts/supplementary-studies/staged-selection']:
        paths.update(path for path in (REPO/directory).glob('requirements*.txt') if path.is_file())
        if (REPO/directory/'README.md').is_file():
            paths.add(REPO/directory/'README.md')
    paths.update((REPO/'scripts/dissertation/locales').glob('*.json'))
    paths.add(REPO / 'results/ACTIVE_GENERIC420.json')
    manifest['output_files'] = {str(p.relative_to(REPO)): info(p) for p in sorted(paths)}
    source_paths = {p for p in (REPO / 'scripts').rglob('*.py') if '__pycache__' not in p.parts}
    manifest['source_files'] = {str(p.relative_to(REPO)): info(p) for p in sorted(source_paths)}
    write(CLOSURE / 'MANIFEST.json', manifest)
    print(json.dumps({'status': 'PASS', 'rq2_pairs': q2['quality_pair_count'], 'rq3_cuts': counts['eligible'], 'indexed_files': len(paths)}))


if __name__ == '__main__':
    main()
