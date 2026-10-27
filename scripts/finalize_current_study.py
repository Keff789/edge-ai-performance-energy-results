#!/usr/bin/env python3
"""Refresh the current study overview and file index after artifact generation."""
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
    labels = {'all': 'All models', 'classification': 'Classifiers', 'detection': 'Detectors'}
    lines = ['# Split selection: current results', '',
        'Seven vision models are evaluated on Jetson Orin NX systems paired with Hailo-8, Hailo-10H or DeepX DX-M1. '
        'The study examines deployment benefits, selection with Generic, and graph-based shortlists.', '',
        '| Question | Data and results |', '|---|---|',
        '| RQ1: When does splitting improve deployment? | [Split and Full comparisons](../../split-inference/tables/fastest_split_baselines.md), including throughput, quality and energy. |',
        '| RQ2: Can Generic select a fast Native cut? | [Paired comparison](../rq2-native-scope-20261027/README.md) on 204 cuts, with 187 passing the quality rule. |',
        '| RQ3: How well do graph scores narrow the search? | [Graph-score comparison](../rq3-generic420-detector-corrected-20261027/README.md) on 331 quality-admissible cuts. |', '',
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
        'Both selection analyses apply the 5% relative quality-loss rule. RQ2 evaluates Native throughput and RQ3 Generic throughput. '
        'The [measurement notes](../rq2-native-scope-20261027/DATA_NOTES.md) record source details that affect interpretation. '
        'The paired b009 observation is included using the reviewed executable and input evidence. '
        'Removing it leaves all Generic recommendation results unchanged. '
        'Energy comparisons use measurements of the same runtime configuration.', '',
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
    active['source_snapshot_unchanged'] = True
    active['publication_update'] = 'Consolidated paired comparison and retrospective graph–Generic–Native selection; no new hardware measurements.'
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
        'RQ1_and_b066_values_unchanged': integration['b066_wide_single_numerical_payload_unchanged'],
        'new_hardware_measurements': False})
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
    write(CLOSURE / 'closure_b009.json', b009)
    old = read(CLOSURE / 'MANIFEST.json')
    manifest = {key: old[key] for key in ['ledger_sha256', 'selection_sha256', 'snapshot_id',
        'export_manifest_sha256', 'used_tool_revisions', 'tool_environment', 'raw_preservation_complete']}
    manifest.update(schema='current-split-study-release-v2', status='complete', counts=counts,
        rq2_counts={'planned': q2['original_native_population'], 'paired': q2['pair_count'],
            'quality_admitted': q2['quality_pair_count'], 'quality_excluded': q2['excluded_candidates'],
            'groups': q2['quality_group_count'], 'unresolved': q2['unresolved_candidates']},
        active_pointer='results/ACTIVE_GENERIC420.json',
        native_full_energy_measurements_unchanged=True, new_hardware_measurements_by_this_update=False,
        RQ1_YOLOv7_case_numerical_evidence_unchanged=True,
        source_backup='PORTABLE_BACKUP_RECEIPT.json describes the retained measurement sources, not a new mirror of this publication update.',
        git_commit_binding='The containing Git commit identifies this publication update.',
        measurement_notes=str((RQ2 / 'DATA_NOTES.md').relative_to(REPO)))
    manifest['staged_selection'] = str(STAGED.relative_to(REPO))
    paths = set()
    for root in [RQ2, RQ3, STAGED, BUILD, CLOSURE]:
        paths.update(p for p in root.rglob('*') if p.is_file() and p != CLOSURE / 'MANIFEST.json'
            and not any(part.startswith('.') or part == '__pycache__' for part in p.relative_to(root).parts))
    paths.add(REPO / 'results/ACTIVE_GENERIC420.json')
    manifest['output_files'] = {str(p.relative_to(REPO)): info(p) for p in sorted(paths)}
    source_paths = {p for p in (REPO / 'scripts').rglob('*.py') if '__pycache__' not in p.parts}
    manifest['source_files'] = {str(p.relative_to(REPO)): info(p) for p in sorted(source_paths)}
    write(CLOSURE / 'MANIFEST.json', manifest)
    print(json.dumps({'status': 'PASS', 'rq2_pairs': q2['quality_pair_count'], 'rq3_cuts': counts['eligible'], 'indexed_files': len(paths)}))


if __name__ == '__main__':
    main()
