#!/usr/bin/env python3
"""Project existing THESIS20 coverage and quality; no new inference/bootstrap.

Invoke with --source-root pointing at the frozen results_snapshot directory.
"""
import argparse
import csv
import json
import hashlib
from collections import Counter
from pathlib import Path


def read(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def build(source, output_root):
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source / 'provenance.json').read_text())
    for name, expected in manifest['sha256'].items():
        payload = (source / name).read_bytes()
        # Reuse the same CSV records already curated in THESIS20. The manuscript
        # serialized them as LF with one trailing blank line; preserve its check.
        original_serialization = ((source / name).read_text().rstrip("\n") + "\n\n").encode()
        assert expected in {hashlib.sha256(payload).hexdigest(),
                            hashlib.sha256(original_serialization).hexdigest()}, name
    coverage = read(source / 'inputs/coverage.csv')
    quality = read(source / 'deep_analysis/tables/quality_effects.csv')
    unsupported = read(source / 'deep_analysis/inputs/native_unsupported.csv')
    native = read(source / 'inputs/native_cases.csv')
    pairs = read(source / 'inputs/completion_pairs.csv')
    aliases = [('H8', 'hailo8_to_tensorrt', 'hailo8'),
               ('H10', 'hailo10_to_tensorrt', 'hailo10h'),
               ('DeepX', 'deepx_m1_to_tensorrt', 'deepx'),
               ('TensorRT control', 'tensorrt', 'tensorrt')]
    summary = []
    for setup, coverage_backend, quality_backend in aliases:
        planned = [r for r in coverage if r['backend'] == coverage_backend and r['variant'] == 'composed']
        qs = [r for r in quality if r['backend'] == quality_backend and r['variant'] == 'split']
        qfull = [r for r in quality if r['backend'] == quality_backend and r['variant'] == 'vendor_full']
        # Seven DeepX TRT full companions duplicate the same Full values under
        # boundary-like IDs; the case_id=full rows define the 21 baseline records.
        if quality_backend == 'tensorrt':
            qfull = [r for r in qfull if r['case_id'] == 'full']
        status = Counter(r['status'] for r in planned)
        qsc = Counter(r['accuracy_class'] for r in qs)
        qfc = Counter(r['accuracy_class'] for r in qfull)
        native_split = [r for r in native if r['setup_id'] == setup and r['execution_mode'] == 'split']
        native_pair = [r for r in pairs if r['setup_id'] == setup]
        excluded = [r for r in unsupported if r['setup_id'] == setup]
        successful = {(r['model_id'], r['case_id']) for r in planned if r['status'] == 'completed'}
        excluded_successful = [r for r in excluded if (r['model_id'], r['case_id']) in successful]
        summary.append(dict(
            setup=setup, quality_backend=quality_backend,
            base_planned_splits=len(planned), base_generic_completed=status['completed'],
            base_build_failed=status['build_failed'], base_policy_excluded=status['policy_excluded'],
            native_runner_multi_input_exclusions=len(excluded),
            generic_completed_but_native_multi_input_excluded=len(excluded_successful),
            native_base_completed=sum(r['cohort'] == 'base' for r in native_split),
            native_added_completed=sum(r['cohort'] == 'augmentation' for r in native_split),
            native_reference_close=sum(r['native_task_quality_status'] == 'reference_close' for r in native_pair),
            native_accuracy_loss=sum(r['native_task_quality_status'] == 'accuracy_loss' for r in native_pair),
            quality_split_results=len(qs), quality_base_split_results=sum(r['cohort']=='base' for r in qs),
            quality_added_split_results=sum(r['cohort']=='augmentation' for r in qs),
            quality_split_reference_close=qsc['reference_close'], quality_split_accuracy_loss=qsc['accuracy_loss'],
            unique_full_quality_results=len(qfull), full_reference_close=qfc['reference_close'],
            full_accuracy_loss=qfc['accuracy_loss']))
    write(output_root / 'vendor_coverage_quality.csv', summary)
    fulls = [r for r in quality if r['variant'] == 'vendor_full' and
             (r['backend'] != 'tensorrt' or r['case_id'] == 'full')]
    cols = ['quality_id', 'model_id', 'setup_id', 'backend', 'case_id', 'metric',
            'candidate', 'reference', 'delta_pp', 'delta_ci_low_pp', 'delta_ci_high_pp',
            'relative_loss', 'relative_loss_ci_low', 'relative_loss_ci_high',
            'accuracy_class', 'uncertainty', 'N', 'B']
    write(output_root / 'full_quality_effects.csv', [{k: r[k] for k in cols} for r in fulls])
    examples = ['base_quality_021', 'base_quality_022', 'base_quality_038',
                'base_quality_000', 'base_quality_007', 'base_quality_174',
                'base_quality_195', 'base_quality_216', 'base_quality_413',
                'base_quality_415', 'base_quality_425', 'base_quality_427']
    write(output_root / 'quality_examples.csv',
          [{**{k: r[k] for k in cols}, 'variant': r['variant']}
           for r in quality if r['quality_id'] in examples])
    recovery = []
    for setup, backend in [('H8', 'hailo8'), ('H10', 'hailo10h'), ('DeepX', 'deepx')]:
        full = [r for r in fulls if r['model_id'] == 'mobilenet_v3_large' and r['backend'] == backend]
        split = [r for r in quality if r['model_id'] == 'mobilenet_v3_large' and r['backend'] == backend and r['variant'] == 'split' and r['case_id'] == 'b027']
        assert len(full) == len(split) == 1
        assert full[0]['reference'] == split[0]['reference']
        recovery.append(dict(setup=setup, reference_pct=100*float(full[0]['reference']), full_pct=100*float(full[0]['candidate']), split_pct=100*float(split[0]['candidate']), recovered_pp=100*(float(split[0]['candidate'])-float(full[0]['candidate']))))
    write(output_root / 'mobilenet_quality_recovery.csv', recovery)
    tex = [r'\begin{table}[t]', r'\caption{Splitting can recover task quality lost in a full accelerator deployment. MobileNetV3 Top1 on the same 5,000 images; CPU ONNX reference: 73.70\%. The split uses b027 and a TensorRT suffix.}', r'\label{tab:vendor-quality}', r'\centering\small', r'\begin{tabular}{lrrr}', r'\toprule', r'Configuration & H8 & H10 & DX\\', r'\midrule']
    for title, field in [('Accelerator Full (\\%)', 'full_pct'), ('Split b027 (\\%)', 'split_pct'), ('Quality recovered (pp)', 'recovered_pp')]:
        tex.append(title + ' & ' + ' & '.join(f"{r[field]:.2f}" for r in recovery) + r'\\')
    tex += [r'\bottomrule', r'\end{tabular}', r'\end{table}', '']
    (output_root / 'vendor_quality_recovery_table.tex').write_text('\n'.join(tex))
    comparison_fields = ['candidate', 'reference', 'delta', 'ci_low', 'ci_high',
                         'accuracy_class', 'relative_loss', 'N', 'B', 'seed',
                         'relative_loss_ci_low', 'relative_loss_ci_high']
    companion_audit = []
    for companion in quality:
        if not (companion['backend'] == 'tensorrt' and companion['variant'] == 'vendor_full'
                and companion['case_id'] != 'full'):
            continue
        targets = [r for r in fulls if all(r[k] == companion[k]
                   for k in ['model_id', 'setup_id', 'backend', 'variant'])]
        assert len(targets) == 1
        target = targets[0]
        assert all(companion[k] == target[k] for k in comparison_fields)
        companion_audit.append(dict(companion_quality_id=companion['quality_id'],
                                    canonical_quality_id=target['quality_id'],
                                    model_id=companion['model_id'], setup_id=companion['setup_id'],
                                    companion_case_id=companion['case_id'],
                                    matching_value_and_policy_fields=len(comparison_fields),
                                    all_values_identical=True))
    write(output_root / 'trt_full_companion_dedup_audit.csv', companion_audit)
    checks = {
        'quality_total': len(quality),
        'heterogeneous_planned_splits': sum(r['base_planned_splits'] for r in summary[:3]),
        'heterogeneous_generic_completed': sum(r['base_generic_completed'] for r in summary[:3]),
        'heterogeneous_build_failures': sum(r['base_build_failed'] for r in summary[:3]),
        'heterogeneous_policy_exclusions': sum(r['base_policy_excluded'] for r in summary[:3]),
        'unique_full_quality_results': len(fulls),
        'distinct_quality_configuration_results': len(quality) - len(companion_audit),
        'trt_duplicate_companions_excluded': sum(r['backend'] == 'tensorrt' and r['variant'] == 'vendor_full'
                                               and r['case_id'] != 'full' for r in quality),
        'native_single_input_exclusions': len(unsupported),
        'native_exclusion_reasons': dict(Counter(r['reason'] for r in unsupported)),
        'losses_by_metric': dict(Counter(r['metric'] for r in quality if r['accuracy_class'] == 'accuracy_loss')),
        'losses_by_variant': dict(Counter(r['variant'] for r in quality if r['accuracy_class'] == 'accuracy_loss')),
        'quality_evaluation_policy': sorted(set((r['N'],r['B'],r['seed']) for r in quality))
    }
    assert checks['heterogeneous_planned_splits'] == 7 * 20 * 3 == 420
    assert checks['heterogeneous_generic_completed'] + checks['heterogeneous_build_failures'] + checks['heterogeneous_policy_exclusions'] == 420
    assert checks['quality_total'] == 560 and checks['unique_full_quality_results'] == 42
    assert checks['native_exclusion_reasons'] == {'part2_input_count_not_one': 228}
    (output_root / 'quality_verification.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    build(args.source_root.resolve(), args.output_root.resolve())
