#!/usr/bin/env python3
"""Offline RQ2 on its original Native-cut population, independent of RQ3 membership.

Observations are selected by actual completion time before quality is evaluated.
Missing contract, ordering or quality evidence stays explicitly unavailable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = Path('results/supplementary-studies/rq2-native-scope-20261027')
INPUT = STUDY / 'inputs/observations.json'
POLICY = STUDY / 'inputs/OBSERVATION_POLICY_v1.json'
LEGACY_SOURCE = Path('scripts/supplementary-studies/rq2-generic-final-20261027/reproduce.py')
spec = importlib.util.spec_from_file_location('rq2_historical_helpers', REPO / LEGACY_SOURCE)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
OLD, METHODS, LABELS = legacy.OLD, legacy.METHODS, legacy.LABELS
read, sha, write_json, write_csv = legacy.read, legacy.sha, legacy.write_json, legacy.write_csv
quality_loss = legacy.quality_loss


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_public(repo, native_dataset_path=None):
    """Apply explicit current Native bindings while preserving archived cuts."""
    bindings, graph, data, frozen = legacy.load_public(repo)
    dataset = Path(native_dataset_path) if native_dataset_path else Path(repo)/'results/split-inference/data/PAPER_DATASET.json'
    by_native = {row['config_id']: uid for uid, row in bindings.items()}
    for native in read(dataset):
        binding = native.get('current_native_binding')
        if not binding:
            continue
        uid = by_native.get(native['uid'])
        if uid is None or native['runner'] != 'native':
            raise ValueError('A current observation cannot add a Native RQ2 cut')
        original = bindings[uid]
        unsigned = {key: value for key, value in binding.items() if key != 'evidence_sha256'}
        if binding.get('evidence_sha256') != canonical_sha(unsigned):
            raise ValueError('Current Native replacement proof hash differs')
        if binding.get('archived_binding_sha256') != canonical_sha(original):
            raise ValueError('Current Native replacement changes the archived cut identity')
        expected = dict(model_sha256=original['native_resolved_model_sha256'],
            part1_sha256=original['native_part1_artifact_sha256'],
            part2_engine_sha256=original['native_part2_engine_sha256'],
            boundary_id=original['resolved_boundary_id'])
        if any(binding['identity'].get(key) != value for key, value in expected.items()):
            raise ValueError('Current Native executable/graph binding differs')
        if binding.get('performance_source_sha256') != native['performance_source_sha256'] or not binding.get('normal_source_sha256'):
            raise ValueError('Current Native observation lacks its actual source authority')
        if 'performance' in native.get('current_observation_metric_updates', []):
            comparison = binding.get('generic_comparison', {})
            if not comparison.get('performance_source_sha256') or any(not binding['identity'].get(key) or
                    binding['identity'][key] != comparison.get(key) for key in
                    ['preprocessing_sha256', 'prepared_inputs_sha256', 'completed_endpoint_contract_sha256']):
                raise ValueError('Current Native/Generic actual completed-task relation differs')
        replacement = dict(original, native_performance_source_sha256=native['performance_source_sha256'])
        replacement['active_native_replacement_evidence_sha256'] = binding['evidence_sha256']
        bindings[uid], data[native['uid']] = replacement, native
    return bindings, graph, data, frozen


def positive(value):
    try:
        return legacy.positive(value)
    except (ValueError, TypeError, OverflowError):
        return False
CONTRACT_IDENTITIES = ['preprocessing_sha256', 'prepared_inputs_sha256', 'tensor_contract_sha256',
                       'output_interpretation_sha256', 'completion_contract_sha256']
QUALITY_IDENTITIES = CONTRACT_IDENTITIES + ['dataset_sha256', 'image_set_sha256',
                                          'reference_model_sha256', 'evaluator_policy_sha256',
                                          'actual_prediction_runtime_sha256']


def average(values):
    values = list(values)
    return statistics.mean(values) if values else None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def bind(row, original, native):
    """Original exact-artifact checks remain mandatory for every RQ2 cut."""
    try:
        reasons, proof = legacy.bind(row, original, native)
        if original and original.get('active_native_replacement_evidence_sha256'):
            proof['active_native_replacement_evidence_sha256'] = original['active_native_replacement_evidence_sha256']
        relation = row.get('product_reuse_relation') or {}
        if relation.get('verified') is True and relation.get('evidence_sha256') and original and native:
            required = dict(model_sha256=row.get('model_sha256'), setup_id=row.get('setup_id'),
                boundary_id=row.get('boundary_id'), native_part1_sha256=original.get('native_part1_artifact_sha256'),
                native_part2_engine_sha256=original.get('native_part2_engine_sha256'),
                generic_part1_sha256=row.get('artifacts', {}).get('part1_sha256'),
                generic_part2_engine_sha256=row.get('artifacts', {}).get('part2_engine_sha256'))
            proven = all(value and relation.get(key) == value for key, value in required.items())
            proven = proven and all(relation.get(key) is True for key in ['precision_equivalent', 'task_contract_equivalent', 'tensor_identity_equivalent'])
            if proven:
                reasons = [reason for reason in reasons if reason not in ['part1_sha256_missing_or_mismatched',
                    'part2_engine_sha256_missing_or_mismatched', 'native_precision_unproven']]
                proof['product_reuse_evidence_sha256'] = relation['evidence_sha256']
                proof['artifact_equivalence_basis'] = 'explicit_proven_product_reuse_relation'
        return reasons, proof
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return ['observation_identity_evidence_incomplete:' + str(error)], {}


def product_identity(row):
    return dict(model_sha256=row.get('model_sha256'), setup_id=row.get('setup_id'),
                part1_sha256=row.get('artifacts', {}).get('part1_sha256'),
                part2_engine_sha256=row.get('artifacts', {}).get('part2_engine_sha256'))


def reviewed_pairing_basis(row):
    """Read an explicit evidence review without manufacturing missing metadata.

    Ordinary executable, timing and quality checks remain separate. The review
    permits a documented historical recipe gap only for its exact observation.
    """
    reference = row.get('pairing_review') or {}
    if not reference.get('path') or not reference.get('sha256'):
        return None
    root = (REPO / STUDY / 'inputs').resolve()
    path = (root / reference['path']).resolve()
    if path.parent != root or not path.is_file() or sha(path) != reference['sha256']:
        return None
    review = read(path)
    if (review.get('schema') != 'observed-input-pairing-review-v1'
            or review.get('decision') != 'include_with_metadata_note'
            or review.get('full_historical_recipe_binding_verified') is not False):
        return None
    expected = dict(product_identity(row), generic_uid=row.get('generic_uid'),
                    boundary_id=row.get('boundary_id'), completed_at=row.get('completed_at'),
                    performance_source_sha256=row.get('performance_source_sha256'))
    if any(not value or review.get(key) != value for key, value in expected.items()):
        return None
    evidence = {}
    for name in ['historical_b009_exact_guard_receipt.json', 'historical_b009_final_hold.json']:
        source = review.get('evidence', {}).get(name, {})
        p = root / name
        if source.get('path') != name or not p.is_file() or sha(p) != source.get('sha256'):
            return None
        evidence[name] = read(p)
    guard = evidence['historical_b009_exact_guard_receipt.json']
    hold = evidence['historical_b009_final_hold.json']
    boundaries = hold.get('independent_strict_contract_boundaries', {})
    if not (guard.get('prepared_tensor_sha_unchanged') is True
            and guard.get('source_image_sha_unchanged') is True
            and guard.get('Q_prepared_input_sha256') == guard.get('original_prepared_input_sha256')
            and boundaries.get('Native_command_common_original_fields_all_exactly_equal') is True
            and boundaries.get('Native_command_runtime_options_exactly_equal') is True
            and hold.get('generic_uid') == row.get('generic_uid')):
        return None
    return review


def contract_reasons(row):
    contract = row.get('observation_contract') or {}
    reasons = []
    relation = row.get('pair_compatibility') or {}
    if relation.get('verified') is False and reviewed_pairing_basis(row) is None:
        reasons.append('generic_native_pair_compatibility_unresolved:' + relation.get('reason', 'evidence_missing'))
    if row.get('invalidated') is True and (not row.get('invalidation_reason') or not row.get('invalidation_evidence_sha256')):
        reasons.append('implementation_invalidation_evidence_unavailable')
    if contract.get('valid') is not True or not contract.get('contract_evidence_sha256'):
        reasons.append('generic_complete_task_contract_evidence_unavailable')
    if contract.get('proof_type') in ['normal_current_ledger', 'normal_product_pair_admission_plus_actual_three_repetitions']:
        for key in ['ledger_row_sha256', 'identity_verified', 'complete_task_verified']:
            if not contract.get(key):
                reasons.append('normal_current_ledger_' + key + '_unavailable')
        for key, expected in [('independent_processes', 3), ('warmups_per_process', 100), ('completed_tasks_per_process', 1000), ('full_postprocessing', True)]:
            if key in contract and contract[key] != expected:
                reasons.append('generic_measurement_contract_' + key + '_mismatched')
        if row.get('effective_repeats') is not None and (len(row['effective_repeats']) != 3 or not all(positive(x) for x in row['effective_repeats'])):
            reasons.append('generic_three_completed_repetitions_unavailable')
        for key, expected in product_identity(row).items():
            if key in contract.get('product_identity', {}) and contract['product_identity'][key] != expected:
                reasons.append('normal_current_ledger_' + key + '_mismatched')
        if not row.get('performance_source_sha256'):
            reasons.append('generic_performance_source_unavailable')
        if row.get('invalidated') is True:
            reasons.append('demonstrated_implementation_or_assignment_error:' + row.get('invalidation_reason', 'reason_missing'))
        return reasons
    if contract.get('historical_reuse') is not True:
        for key, expected in [('independent_processes', 3), ('warmups_per_process', 100),
                              ('completed_tasks_per_process', 1000), ('full_postprocessing', True)]:
            if contract.get(key) != expected:
                reasons.append('generic_measurement_contract_' + key + '_unverified')
        if len(row.get('effective_repeats', [])) != 3 or not all(positive(x) for x in row.get('effective_repeats', [])):
            reasons.append('generic_three_completed_repetitions_unavailable')
    elif not contract.get('historical_contract_identity_verified'):
        reasons.append('historical_generic_contract_identity_unverified')
    for key in CONTRACT_IDENTITIES:
        if not contract.get(key):
            reasons.append('generic_contract_' + key + '_unavailable')
    if not row.get('performance_source_sha256'):
        reasons.append('generic_performance_source_unavailable')
    if row.get('invalidated') is True:
        reasons.append('demonstrated_implementation_or_assignment_error:' + row.get('invalidation_reason', 'reason_missing'))
    return reasons


def select_observation(candidates, original, native):
    """Choose latest valid compatible completion without reading quality or FPS rank."""
    admitted, audit = [], []
    unproven_invalidation = False
    for row in candidates:
        reasons, proof = bind(row, original, native)
        reasons += contract_reasons(row)
        review = reviewed_pairing_basis(row)
        if review is not None:
            proof.update(pairing_basis=review['basis'], pairing_metadata_note=review['metadata_note'],
                         full_historical_recipe_binding_verified=False)
        unproven_invalidation |= 'implementation_invalidation_evidence_unavailable' in reasons
        if not positive(row.get('effective_generic_fps')):
            reasons.append('generic_throughput_unavailable')
        completed = timestamp(row.get('completed_at'))
        audit.append(dict(observation_id=row.get('observation_id', row.get('performance_source_sha256')),
                          completed_at=row.get('completed_at'), compatible_valid=not reasons,
                          reasons=reasons, actual_completion_time_known=completed is not None))
        if not reasons:
            admitted.append((row, completed, proof))
    if unproven_invalidation:
        return None, {}, audit, ['implementation_invalidation_evidence_unavailable']
    if not admitted:
        detailed = sorted({reason for observation in audit for reason in observation['reasons']})
        return None, {}, audit, ['no_valid_identity_and_complete_task_generic_observation'] + detailed
    if any(completed is None for _, completed, _ in admitted):
        return None, {}, audit, ['actual_generic_completion_order_unresolved']
    latest = max(completed for _, completed, _ in admitted)
    newest = [(row, proof) for row, completed, proof in admitted if completed == latest]
    hashes = {row['performance_source_sha256'] for row, _ in newest}
    if len(hashes) != 1:
        return None, {}, audit, ['different_generic_observations_have_same_completion_time']
    # Duplicate mirrors of the same observation may share a time and hash. A
    # conflict in payload is held, never resolved using quality or throughput.
    payloads = {json.dumps(row, sort_keys=True) for row, _ in newest}
    if len(payloads) != 1:
        return None, {}, audit, ['duplicate_generic_observation_payload_conflict']
    row, proof = newest[0]
    return row, proof, audit, []


def generic_quality(row):
    binding = row.get('quality_binding') or {}
    reasons = []
    if binding.get('proof_type') == 'corrected_normal_quality_pending':
        return dict(status='unavailable', value=None, reference=None, relative_loss=None, admitted=False,
                    reasons=binding.get('normal_exclusion_reasons', ['corrected_normal_N5000_quality_pending']))
    if binding.get('verified') is not True or not binding.get('evidence_sha256'):
        reasons.append('current_generic_quality_binding_unavailable')
    if binding.get('proof_type') in ['normal_current_ledger', 'normal_product_pair_admission_with_actual_artifact_quality_evidence', 'normal_generic_quality_source_with_exact_runtime_equivalence']:
        for key in ['ledger_row_sha256', 'product_identity_verified', 'runtime_artifacts_and_inputs_bound', 'dataset_reference_evaluator_bound']:
            if not binding.get(key):
                reasons.append('normal_current_quality_' + key + '_unavailable')
        for key in ['part1_sha256', 'part2_engine_sha256']:
            if key in binding.get('artifacts', {}) and binding['artifacts'][key] != row.get('artifacts', {}).get(key):
                reasons.append('generic_quality_' + key + '_mismatched')
        if binding.get('model_sha256') and binding['model_sha256'] != row.get('model_sha256'):
            reasons.append('generic_quality_model_sha256_mismatched')
        for key, expected in product_identity(row).items():
            if key in binding.get('product_identity', {}) and binding['product_identity'][key] != expected:
                reasons.append('generic_quality_' + key + '_mismatched')
        if binding.get('reference_runtime') != 'cpu_onnx':
            reasons.append('generic_quality_cpu_onnx_reference_unverified')
        value, reference = binding.get('value'), binding.get('reference')
        return quality_decision(binding, value, reference, reasons)
    identity = binding.get('identity') or {}
    contract = row.get('observation_contract') or {}
    expected = dict(model_sha256=row.get('model_sha256'), setup_id=row.get('setup_id'),
                    part1_sha256=row.get('artifacts', {}).get('part1_sha256'),
                    part2_engine_sha256=row.get('artifacts', {}).get('part2_engine_sha256'))
    expected.update({key: contract.get(key) for key in CONTRACT_IDENTITIES})
    for key, value in expected.items():
        if not value or identity.get(key) != value:
            reasons.append('generic_quality_' + key + '_missing_or_mismatched')
    for key in QUALITY_IDENTITIES:
        if not identity.get(key):
            reasons.append('generic_quality_' + key + '_unavailable')
    if binding.get('reference_runtime') != 'cpu_onnx':
        reasons.append('generic_quality_cpu_onnx_reference_unverified')
    value, reference = binding.get('value'), binding.get('reference')
    return quality_decision(binding, value, reference, reasons)


def quality_decision(binding, value, reference, reasons):
    numeric = (isinstance(value, (int, float)) and not isinstance(value, bool)
               and math.isfinite(value) and positive(reference))
    if not numeric:
        reasons.append('current_generic_quality_numeric_observation_unavailable')
    if reasons:
        # Unbound AP is neither measured accuracy_loss nor admitted quality.
        return dict(status='unavailable', value=None, reference=None, relative_loss=None,
                    admitted=False, reasons=sorted(set(reasons)))
    loss = (float(reference) - value) / float(reference)
    normal = binding.get('normal_admission')
    if not isinstance(normal, bool):
        return dict(status='unavailable', value=value, reference=reference, relative_loss=loss,
                    admitted=False, reasons=['normal_generic_quality_admission_unavailable'])
    admitted = normal and loss <= .05
    return dict(status='reference_close' if admitted else 'accuracy_loss' if loss > .05 else 'normal_quality_gate_failed',
                value=value, reference=reference, relative_loss=loss, admitted=admitted,
                reasons=[] if admitted else ['generic_relative_quality_loss_above_5pct'] if loss > .05 else ['normal_generic_quality_gate_failed'])


def groups(pairs, fps_key='generic_fps'):
    result = legacy.groups(pairs, fps_key)
    for row in result:
        row['ranking_evaluable'] = row['candidate_count'] >= 2
        row['singleton'] = row['candidate_count'] == 1
        row['ranking_note'] = 'fewer than two admitted cuts; zero loss is not ranking evidence' if row['singleton'] else 'at least two admitted cuts'
    return result


def curves(pairs, graph, frozen):
    if pairs:
        group, aggregate, ranks = legacy.curves(pairs, graph, frozen)
    else:
        group, ranks = [], []
        aggregate = [dict(method=m, k=k, mean_loss_pct=None, median_loss_pct=None, max_loss_pct=None,
                          exact_winners=0, groups=0) for m in METHODS for k in range(1, 21)]
    for row in group:
        row.update(ranking_evaluable=row['n'] >= 2, singleton=row['n'] == 1)
    for row in aggregate:
        subset = [r for r in group if r['method'] == row['method'] and r['k'] == row['k'] and r['n'] >= 2]
        row.update(mean_loss_n_ge_2_pct=average(r['loss_pct'] for r in subset), groups_n_ge_2=len(subset),
                   singleton_groups=row['groups'] - len(subset))
    return group, aggregate, ranks


def same_pairs_comparison(pairs):
    eligible = [r for r in pairs if positive(r.get('old_generic_fps'))]
    old, new = groups(eligible, 'old_generic_fps'), groups(eligible)
    index = {(r['model'], r['setup']): r for r in old}
    comparisons = []
    ranks = []
    for row in new:
        prior = index[(row['model'], row['setup'])]
        comparisons.append(dict(model=row['model'], setup=row['setup'], candidate_count=row['candidate_count'],
            ranking_evaluable=row['ranking_evaluable'], singleton=row['singleton'], old_generic_choice=prior['generic_choice'],
            final_generic_choice=row['generic_choice'], old_loss_pct=prior['loss_pct'], final_loss_pct=row['loss_pct'],
            loss_change_pp=row['loss_pct'] - prior['loss_pct']))
        pool = [p for p in eligible if (p['model'], p['setup']) == (row['model'], row['setup'])]
        old_rank = {p['generic_uid']: i for i, p in enumerate(sorted(pool, key=lambda p: (-p['old_generic_fps'], p['generic_uid'])), 1)}
        for i, pair in enumerate(sorted(pool, key=lambda p: (-p['generic_fps'], p['generic_uid'])), 1):
            ranks.append(dict(model=row['model'], setup=row['setup'], generic_uid=pair['generic_uid'], case=pair['case'],
                              old_generic_rank=old_rank[pair['generic_uid']], current_generic_rank=i,
                              old_generic_fps=pair['old_generic_fps'], current_generic_fps=pair['generic_fps'],
                              candidate_count=len(pool), ranking_evaluable=len(pool) >= 2))
    return comparisons, ranks


def family_results(pairs, eligible, selected, quality_selected, comparison, bindings):
    """Existing equal-group selection loss, separated by the recorded task family."""
    task_by_model = {row['model']: row['task'] for row in bindings.values()}
    result = []
    for scope, pool, choices in [('unrestricted', pairs, selected), ('quality_admitted', eligible, quality_selected)]:
        for family in ['all', 'classification', 'detection']:
            members = [row for row in pool if family == 'all' or row['task'] == family]
            rows = [row for row in choices if family == 'all' or task_by_model[row['model']] == family]
            common = [row for row in comparison if family == 'all' or task_by_model[row['model']] == family]
            result.append(dict(scope=scope, family=family,
                original_native_cases=sum(family == 'all' or row['task'] == family for row in bindings.values()),
                paired_candidates=len(members), model_device_groups=len(rows),
                singleton_groups=sum(row['singleton'] for row in rows), groups_n_ge_2=sum(row['ranking_evaluable'] for row in rows),
                mean_loss_pct=average(row['loss_pct'] for row in rows),
                mean_loss_n_ge_2_pct=average(row['loss_pct'] for row in rows if row['ranking_evaluable']),
                exact_winners=sum(row['exact_hit'] for row in rows),
                common_pair_groups=len(common) if scope == 'quality_admitted' else None,
                old_generic_mean_loss_same_pairs_pct=average(row['old_loss_pct'] for row in common) if scope == 'quality_admitted' else None,
                current_generic_mean_loss_same_pairs_pct=average(row['final_loss_pct'] for row in common) if scope == 'quality_admitted' else None))
    return result


def plot_selection_loss(points, language='en'):
    """Show every model/device group; place large losses outside the scale."""
    sys.path.insert(0, str(REPO / 'scripts/split-inference'))
    from publication_mlsys_figures import PAPER_STYLE, PAPER_PALETTE
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    models = ['mobilenet_v3_large', 'regnet_x_1_6gf', 'resnet50',
              'yolo11l', 'yolo26m', 'yolo26s', 'yolov7_paper']
    labels = ['MobileNetV3-L', 'RegNet-X', 'ResNet-50', 'YOLO11l',
              'YOLO26m', 'YOLO26s', 'YOLOv7']
    position = {name: index for index, name in enumerate(models)}
    with plt.rc_context(PAPER_STYLE):
        fig, ax = plt.subplots(figsize=(3.6, 2.62))
        fig.subplots_adjust(left=.30, right=.79, bottom=.18, top=.88)
        handles = []
        for setup, marker, color, offset in [('H8', 'o', 'blue', -.14),
                ('H10', 's', 'orange', 0.), ('DeepX', '^', 'green', .14)]:
            color = PAPER_PALETTE[color]
            handles.append(Line2D([], [], marker=marker, linestyle='none', color=color,
                                  markersize=4.2, label=setup))
            for row in points:
                if row['setup'] != setup or row['model'] not in position:
                    continue
                loss = row['loss_pct']
                y = position[row['model']] + offset
                if loss > 6:
                    # No marker is placed at the right axis boundary: that
                    # would falsely suggest a loss near six percent.
                    ax.annotate('', xy=(1.11, y), xytext=(1.02, y),
                        xycoords=('axes fraction', 'data'),
                        textcoords=('axes fraction', 'data'),
                        arrowprops=dict(arrowstyle='->', color=color, lw=.9),
                        annotation_clip=False)
                    value = f'{loss:.2f}%' if language == 'en' else f'{loss:.2f} %'.replace('.', ',')
                    note = 'off scale' if language == 'en' else 'außerhalb'
                    ax.text(1.14, y, value + '\n' + note, transform=ax.get_yaxis_transform(),
                            ha='left', va='center', fontsize=7, color=color, clip_on=False)
                else:
                    ax.scatter([loss], [y], marker=marker, s=19,
                               facecolors='none' if row.get('singleton') else color,
                               edgecolors=color, linewidths=.7, zorder=3)
        ax.set(xlim=(-.2, 6), ylim=(6.55, -.55), xticks=list(range(7)),
               yticks=list(range(7)), yticklabels=labels,
               xlabel='Native throughput lost (%)' if language == 'en' else 'Native-Durchsatzverlust (%)')
        ax.tick_params(axis='y', labelsize=8, length=3, pad=3)
        ax.grid(axis='x', color='#DDDDDD', linewidth=.55)
        ax.legend(handles=handles, frameon=False, ncol=3, loc='lower center',
                  bbox_to_anchor=(.5, 1.015), columnspacing=1.0, handletextpad=.3,
                  borderaxespad=0., fontsize=8)
        return fig


def render(output, numeric_only):
    summary = read(output / 'summary.json')
    with (output / 'analysis/aggregate_curves.csv').open() as stream:
        raw = list(csv.DictReader(stream))
    caption = (f"Native throughput loss for {summary['quality_pair_count']} quality-admissible cuts in "
        f"{summary['quality_group_count']} model-device groups, with groups weighted equally. "
        "At budget k, we test the first min(k,n) ranked cuts and compare their highest Native throughput "
        "with the best measured Native cut in that group.")
    series = {method: [dict(k=int(r['k']), mean_loss_pct=float(r['mean_loss_pct']) if r['mean_loss_pct'] else None,
        mean_loss_n_ge_2_pct=float(r['mean_loss_n_ge_2_pct']) if r['mean_loss_n_ge_2_pct'] else None)
        for r in raw if r['method'] == method] for method in METHODS}
    write_json(output / 'figures/rq2_weighted_all_models.json', dict(schema='rq2-native-scope-weighted-v1',
        series=series, caption=caption, scope=summary['scope'], method_labels=LABELS,
        source_sha256=sha(output / 'analysis/aggregate_curves.csv')))
    write_csv(output / 'figures/rq2_weighted_all_models.csv', raw)
    with (output / 'analysis/group_curves.csv').open() as stream:
        group_curves = list(csv.DictReader(stream))
    success = []
    for method in METHODS:
        for k in range(1, 21):
            rows = [r for r in group_curves if r['method'] == method and int(r['k']) == k]
            multi = [r for r in rows if int(r['n']) >= 2]
            success.append(dict(method=method, k=k, groups=len(rows), groups_n_ge_2=len(multi),
                exact_success_fraction=average(int(r['exact_winner_found']) for r in rows),
                exact_success_fraction_n_ge_2=average(int(r['exact_winner_found']) for r in multi)))
    write_json(output / 'figures/rq2_native_success.json', dict(points=success, caption=caption, scope=summary['scope']))
    write_csv(output / 'figures/rq2_native_success.csv', success)
    for name, key in [('current_generic_selection_loss', 'selection_groups'), ('quality_generic_selection_loss', 'quality_selection_groups')]:
        points = read(output / 'data' / f'{key}.json')
        pair_count = sum(r['candidate_count'] for r in points)
        singleton_count = sum(r['singleton'] for r in points)
        eligibility = 'quality-admissible paired cuts' if key.startswith('quality') else 'paired cuts before quality filtering'
        scatter_caption = (f'Native throughput lost by selecting the Generic winner in {len(points)} model-device groups '
            f'with {pair_count} {eligibility}. Groups contribute equally. '
            'Arrows outside the 0–6% axis label the larger losses, which remain in the aggregate results.')
        if singleton_count:
            scatter_caption += ' Hollow markers denote groups with only one candidate.'
        write_json(output / 'figures' / f'{name}.json', dict(points=points, caption=scatter_caption,
            plot_layout='model_rows_with_offset_accelerator_markers', x_axis='native_throughput_loss_pct',
            displayed_loss_range_pct=[0, 6], out_of_range_marker_policy='outside_axis_arrow_with_actual_value_no_boundary_marker',
            marker_policy={'one_candidate':'hollow backend marker; no ranking test', 'at_least_two_candidates':'filled backend marker'},
            paired_candidates=sum(r['candidate_count'] for r in points), groups=len(points),
            mean_group_loss_pct=average(r['loss_pct'] for r in points),
            mean_group_loss_n_ge_2_pct=average(r['loss_pct'] for r in points if r['ranking_evaluable']),
            exact_hits=sum(r['exact_hit'] for r in points)))
        write_csv(output / 'figures' / f'{name}.csv', points)
    for ext in ['json', 'csv']:
        shutil.copyfile(output / 'figures' / f'quality_generic_selection_loss.{ext}', output / 'figures' / f'rq2_generic_selection_loss.{ext}')
    budget = []
    for method in METHODS:
        values = {r['k']: r for r in series[method]}
        budget.append(dict(method=method, label=LABELS[method], groups=summary['quality_group_count'],
            **{f'loss_k{k}_pct': values[k]['mean_loss_pct'] for k in [1, 3, 5]},
            **{f'loss_k{k}_n_ge_2_pct': values[k]['mean_loss_n_ge_2_pct'] for k in [1, 3, 5]}))
    write_csv(output / 'tables/r30_weighted_budget_table.csv', budget)
    write_json(output / 'tables/r30_weighted_budget_table.json', dict(rows=budget, caption=caption))
    fmt = lambda value: 'unavailable' if value is None else f'{value:.2f}'
    tex = ['% ' + caption, r'\begin{tabular}{lrrr}', r'\toprule', r'Method & $k=1$ & $k=3$ & $k=5$ \\', r'\midrule']
    tex += [r['label'] + ' & ' + ' & '.join(fmt(r[f'loss_k{k}_pct']) for k in [1, 3, 5]) + r' \\' for r in budget]
    (output / 'tables/r30_weighted_budget_table.tex').write_text('\n'.join(tex + [r'\bottomrule', r'\end{tabular}']) + '\n')
    weights = summary['weights']['shared']
    (output / 'tables/r30_weighted_macros.tex').write_text('\n'.join([
        f'\\newcommand{{\\WeightedModelCount}}{{{len(summary["models"])}}}',
        f'\\newcommand{{\\WeightedGroupCount}}{{{summary["quality_group_count"]}}}',
        f'\\newcommand{{\\WeightedCandidateCount}}{{{summary["quality_pair_count"]}}}',
        f'\\newcommand{{\\WeightedOptimizedComm}}{{{weights["w_comm"]:.6g}}}',
        f'\\newcommand{{\\WeightedOptimizedImb}}{{{weights["w_imb"]:.6g}}}',
        f'\\newcommand{{\\WeightedTensorWeight}}{{{weights["w_tensors"]:.6g}}}']) + '\n')
    required = []
    for method in METHODS:
        for target in [.9, .95, 1.]:
            eligible = [r['k'] for r in success if r['method'] == method and r['exact_success_fraction'] is not None and r['exact_success_fraction'] >= target]
            required.append(dict(method=method, target_success=target, groups=summary['quality_group_count'], minimum_budget=min(eligible) if eligible else None))
    write_csv(output / 'tables/rq2_search_budget_table.csv', required)
    write_json(output / 'tables/rq2_search_budget_table.json', dict(rows=required, caption=caption))
    (output / 'tables/rq2_search_budget_table.tex').write_text('% ' + caption + '\n' + '\n'.join([
        r'\begin{tabular}{lrr}', r'Method & Target & Budget \\'] + [
        f"{LABELS[r['method']]} & {100*r['target_success']:.0f}\\% & {r['minimum_budget'] if r['minimum_budget'] is not None else 'unavailable'} \\\\" for r in required] + [r'\end{tabular}']) + '\n')
    if numeric_only:
        return
    sys.path.insert(0, str(REPO / 'scripts/split-inference'))
    from publication_mlsys_figures import PAPER_STYLE, PAPER_PALETTE
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = ['green', 'blue', 'yellow', 'dark_gray', 'purple']
    with plt.rc_context(PAPER_STYLE):
        for name, points, ylabel, key in [
            ('rq2_weighted_all_models', [dict(method=m, **r) for m in METHODS for r in series[m]], 'Mean Native throughput loss (%)', 'mean_loss_pct'),
            ('rq2_native_success', success, 'Exact Native optimum found (%)', 'exact_success_fraction')]:
            fig, ax = plt.subplots(figsize=(3.6, 2.95))
            for method, color in zip(METHODS, colors):
                selected = [r for r in points if r['method'] == method and r[key] is not None]
                ax.plot([r['k'] for r in selected], [100*r[key] if name == 'rq2_native_success' else r[key] for r in selected], label=LABELS[method], color=PAPER_PALETTE[color], lw=1.2)
            ax.set(xlim=(.8, 20.2), xlabel='Maximum Native trials per group', ylabel=ylabel, xticks=[1, 3, 5, 10, 15, 20])
            ax.legend(frameon=False, fontsize=6); fig.tight_layout()
            legacy.save_figure(fig, output / 'figures' / name); plt.close(fig)
        for name in ['current_generic_selection_loss', 'quality_generic_selection_loss']:
            points = read(output / 'figures' / f'{name}.json')['points']
            fig = plot_selection_loss(points)
            legacy.save_figure(fig, output / 'figures' / name)
            plt.close(fig)
        for ext in ['pdf', 'svg', 'png']:
            shutil.copyfile(output / 'figures' / f'quality_generic_selection_loss.{ext}', output / 'figures' / f'rq2_generic_selection_loss.{ext}')


def acquisition_index(observations):
    """Count actual captures independently of Native pairing or quality outcome."""
    result = defaultdict(lambda: {'fps': set(), 'quality': set()})
    for row in observations['rows']:
        uid = row['generic_uid']
        if (row.get('performance_acquisition_origin') == 'new_capture' and timestamp(row.get('completed_at')) is not None
                and row.get('performance_source_sha256')):
            result[uid]['fps'].add(row['performance_source_sha256'])
        if (row.get('quality_acquisition_origin') == 'new_capture' and timestamp(row.get('quality_completed_at')) is not None
                and row.get('quality_acquisition_source_sha256')):
            result[uid]['quality'].add(row.get('quality_binding', {}).get('evidence_sha256') or row['quality_acquisition_source_sha256'])
    for record in observations.get('assembly', {}).get('performance_overlays', []):
        if (record.get('performance_acquisition_origin') == 'new_capture' and timestamp(record.get('completed_at')) is not None
                and record.get('performance_source_sha256')):
            result[record['generic_uid']]['fps'].add(record['performance_source_sha256'])
    for record in observations.get('assembly', {}).get('overlays', []):
        if (record.get('quality_acquisition_origin') == 'new_capture' and timestamp(record.get('quality_completed_at')) is not None
                and record.get('acquisition_source_sha256')):
            result[record['generic_uid']]['quality'].add(record.get('quality_evidence_sha256') or record['acquisition_source_sha256'])
    return result


def run(output, repo=REPO, numeric_only=False, verify_reference=None, input_path=None, native_dataset_path=None):
    output, repo = Path(output), Path(repo)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose an empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_path) if input_path else repo / INPUT
    observations = read(input_path)
    accounting_path = repo / STUDY / 'ACTUAL_IMPORT_ACCOUNTING.json'
    accounting = read(accounting_path) if accounting_path.is_file() else None
    if accounting is not None and accounting.get('inputs_sha256') != sha(input_path):
        accounting = None
    closure_cases = {row['generic_uid']: row for row in accounting['cases']} if accounting else {}
    bindings, graph, data, frozen = load_public(repo, native_dataset_path)
    current_native = [row for row in data.values() if row.get('current_native_binding')]
    fixed = set(observations.get('fixed420_uids', []))
    indexed = defaultdict(list)
    active_observations = []
    for row in observations['rows']:
        original = bindings.get(row['generic_uid'])
        native = data.get(original['config_id']) if original else None
        binding = (native or {}).get('current_native_binding')
        if binding and 'performance' in native.get('current_observation_metric_updates', []):
            row = copy.deepcopy(row)
            preprocessing = row.get('observation_contract', {}).get('preprocessing_sha256')
            if (preprocessing and preprocessing == binding['identity']['preprocessing_sha256'] and
                    row.get('performance_source_sha256') == binding['generic_comparison']['performance_source_sha256']):
                row['pair_compatibility'] = dict(verified=True, evidence_sha256=binding['evidence_sha256'],
                    basis='new_normal_Native_observation_with_same_actual_Generic_preprocessing')
                row.pop('pairing_review', None)
            else:
                row['pair_compatibility'] = dict(verified=False, reason='current_Native_and_Generic_preprocessing_not_bound')
                row.pop('pairing_review', None)
        indexed[row['generic_uid']].append(row)
        active_observations.append(row)
    acquisitions = acquisition_index(observations)
    audit, pairs = [], []
    for uid, original in sorted(bindings.items()):
        native = data.get(original['config_id'])
        row, proof, observation_audit, reasons = select_observation(indexed[uid], original, native)
        group_identity = dict(generic_uid=uid, model=original['model'], setup=original['setup'], case=original['case'],
                              rq3_fixed420_member=uid in fixed)
        record = dict(**group_identity, original_native_measured=True, candidate_observations=len(indexed[uid]),
                      source_found=bool(indexed[uid]), compatible_selected=row is not None,
                      new_fps_captured=bool(acquisitions[uid]['fps']), new_quality_captured=bool(acquisitions[uid]['quality']),
                      new_fps_capture_observations=len(acquisitions[uid]['fps']), new_quality_capture_observations=len(acquisitions[uid]['quality']),
                      corrected_quality_pending=False,
                      pair_verified=row is not None, exclusion_reasons=reasons, observations=observation_audit, **proof)
        if row is None:
            latest = max(indexed[uid], key=lambda observation: (timestamp(observation.get('completed_at')) or float('-inf'), observation.get('performance_source_sha256', ''))) if indexed[uid] else {}
            record['corrected_quality_pending'] = latest.get('quality_correction', {}).get('status') == 'pending'
            closed = closure_cases.get(uid, {})
            if closed.get('current_pair_hold_explanation'):
                record.update(historical_exclusion_reasons=record['exclusion_reasons'],
                    exclusion_reasons=closed['pair_hold_reasons'], current_pair_hold_explanation=closed['current_pair_hold_explanation'])
            record.update(quality_status='unavailable', quality_eligible=False, status='unresolved',
                          quality_exclusion_reasons=['no_selected_generic_observation'])
            audit.append(record)
            continue
        quality = generic_quality(row)
        native_loss = quality_loss(native)
        native_reasons = ['native_quality_unavailable'] if native_loss is None else ['native_quality_loss_above_5pct'] if native_loss > .05 else []
        if ('quality' in native.get('current_observation_metric_updates', []) and native.get('normal_quality') is not True):
            native_reasons.append('current_native_normal_quality_not_admitted')
        admitted = quality['admitted'] and not native_reasons
        q_reasons = sorted(set(native_reasons + quality['reasons'] + (row.get('quality_binding', {}).get('normal_exclusion_reasons', []) if not quality['admitted'] else [])))
        source = row.get('observation_origin', 'remeasured' if row.get('observation_mode') == 'new_current_job_measurement' else 'recovered')
        record.update(selected_observation_id=row.get('observation_id', row['performance_source_sha256']), completed_at=row['completed_at'],
            observation_origin=source, selected_performance_source_sha256=row['performance_source_sha256'],
            corrected_quality_pending=row.get('quality_correction', {}).get('status') == 'pending',
            quality_status=quality['status'], quality_eligible=admitted,
            quality_exclusion_reasons=q_reasons, status='admitted' if admitted else 'unresolved' if quality['status'] == 'unavailable' or native_loss is None else 'excluded')
        audit.append(record)
        old = data.get(uid, {})
        pairs.append(dict(**group_identity, task=native['task'], native_uid=native['uid'], native_fps=native['fps'],
            generic_fps=float(row['effective_generic_fps']), old_generic_fps=old.get('fps'), boundary_id=row['boundary_id'],
            observation_origin=source, generic_completed_at=row['completed_at'], generic_performance_source_sha256=row['performance_source_sha256'],
            native_quality_metric=native.get('quality_metric'), generic_quality_metric=native.get('quality_metric'),
            native_quality_value=native.get('quality_value'), native_quality_reference_value=native.get('quality_reference_value'),
            native_relative_quality_loss=native_loss, generic_quality_value=quality['value'], generic_quality_reference_value=quality['reference'],
            generic_relative_quality_loss=quality['relative_loss'], generic_quality_status=quality['status'],
            quality_eligible=admitted, quality_exclusion_reasons=q_reasons,
            generic_mj_per_image=None, native_mj_per_image=None,
            energy_status='omitted: refreshed Generic FPS is not a joint measurement with historical energy',
            native_original_precision=proof.get('native_recorded_precision'), comparison_precision=proof.get('comparison_precision'),
            native_performance_source_sha256=native['performance_source_sha256'], native_measurement_boundary=native.get('measurement_boundary'),
            generic_observation_mode=row.get('observation_mode'), endpoint_equivalence_claimed=False,
            pairing_basis=proof.get('pairing_basis', 'artifact_and_recorded_contract_binding'),
            pairing_metadata_note=proof.get('pairing_metadata_note'),
            full_historical_recipe_binding_verified=proof.get('full_historical_recipe_binding_verified'),
            native_quality_scope=('Actual selected timed Native completion records, evaluated by the normal quality workflow.'
                if native.get('quality_timed_endpoint_bound') else 'Preserved historical normal quality observation; exact selected timed Native endpoint AP is not established by its numeric record alone.'),
            native_quality_evidence_sha256=native.get('quality_evidence_sha256'),
            native_quality_source_sha256=native.get('quality_source_sha256'), native_quality_generation=native.get('quality_generation'),
            native_timed_completion_mode=native.get('measured_completion_mode'),
            native_timed_completion_contract_sha256=native.get('completion_contract_sha256'),
            native_recorded_decoder_contract_sha256=native.get('contract_decoder'),
            native_recorded_nms_contract_sha256=native.get('contract_nms'),
            generic_timed_completion_modes=row.get('observation_contract', {}).get('runtime_modes'),
            generic_timed_completion_contract_sha256=row.get('observation_contract', {}).get('complete_task_contract_sha256', row.get('observation_contract', {}).get('completion_contract_sha256')),
            generic_quality_evidence_sha256=row.get('quality_binding', {}).get('evidence_sha256'),
            generic_quality_completed_at=row.get('quality_completed_at'),
            performance_source_epochs=row.get('source_epochs', {}), generic_quality_source_epochs=row.get('quality_binding', {}).get('source_epochs', {}),
            generic_quality_legacy_1pct_decision=row.get('quality_binding', {}).get('legacy_1pct_decision'),
            generic_quality_legacy_1pct_margin_absolute_ap=row.get('quality_binding', {}).get('legacy_1pct_margin_absolute_ap'),
            native_cpu_reference_sha256=native.get('quality_reference_sha256') or row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding', {}).get('cpu_reference_sha256'),
            generic_cpu_reference_sha256=row.get('quality_binding', {}).get('cpu_reference_sha256'),
            preserved_native_quality_reference_binding=row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding'),
            completion_provenance=row.get('completion_provenance'), quality_correction=row.get('quality_correction'),
            typed_quality_import_authorities=row.get('typed_quality_import_authorities', [])))
        if native.get('current_native_binding'):
            pairs[-1].update(native_replacement_evidence_sha256=native['current_native_binding']['evidence_sha256'],
                native_quality_timed_endpoint_bound=native.get('quality_timed_endpoint_bound', False),
                native_performance_source_epochs=native.get('performance_source_epochs', {}),
                native_quality_source_epochs=native.get('quality_source_epochs', {}))
            if row.get('completion_provenance'):
                pairs[-1]['completion_provenance'] = dict(historical=row['completion_provenance'],
                    current_native_quality_timed_endpoint_bound=native.get('quality_timed_endpoint_bound', False),
                    current_native_quality_source_sha256=native.get('quality_source_sha256'))

    quality = [r for r in pairs if r['quality_eligible']]
    selected, quality_selected = groups(pairs), groups(quality)
    comparison, comparison_ranks = same_pairs_comparison(quality)
    group_curves, aggregate, rankings = curves(quality, graph, frozen)
    coverage = []
    for model, setup in sorted({(r['model'], r['setup']) for r in audit}):
        records = [r for r in audit if (r['model'], r['setup']) == (model, setup)]
        matched = [r for r in pairs if (r['model'], r['setup']) == (model, setup)]
        eligible = [r for r in matched if r['quality_eligible']]
        coverage.append(dict(model=model, setup=setup, original=len(records),
            source_found=sum(r['source_found'] for r in records), compatible_selected=len(matched),
            recovered=sum(r['observation_origin'] == 'recovered' for r in matched),
            remeasured=sum(r['new_fps_captured'] for r in records),
            remeasured_compatible_selected=sum(r['observation_origin'] == 'remeasured' for r in matched),
            new_fps_captured=sum(r['new_fps_captured'] for r in records), new_quality_captured=sum(r['new_quality_captured'] for r in records),
            new_fps_capture_observations=sum(r['new_fps_capture_observations'] for r in records),
            new_quality_capture_observations=sum(r['new_quality_capture_observations'] for r in records),
            quality_admitted=len(eligible), excluded=sum(r['status'] == 'excluded' for r in records),
            unresolved=sum(r['status'] == 'unresolved' for r in records), identity_valid_pairs=len(matched),
            quality_pairs=len(eligible), rq3_fixed420_members=sum(r['rq3_fixed420_member'] for r in records),
            outside_rq3_fixed420=sum(not r['rq3_fixed420_member'] for r in records),
            ranking_evaluable=len(eligible) >= 2, singleton=len(eligible) == 1,
            ranking_note='fewer than two admitted cuts; zero loss is not ranking evidence' if len(eligible) < 2 else 'at least two admitted cuts',
            pair_exclusion_reasons=dict(Counter(reason for r in records for reason in r['exclusion_reasons'])),
            quality_exclusion_reasons=dict(Counter(reason for r in records for reason in r['quality_exclusion_reasons'])),
            status='evaluated' if eligible else 'unavailable_no_quality_admitted_pair'))
        if current_native:
            native_group = [row for row in current_native if row['model_id'] == model and row['setup_id'] == setup]
            coverage[-1].update(native_observations_replaced=len(native_group),
                **{'native_new_'+metric+'_captured':sum(metric in row['current_observation_metric_updates'] and
                    row.get(metric+'_acquisition_origin') == 'new_capture' for row in native_group)
                    for metric in ['performance', 'quality', 'energy']})
    audit_index = {row['generic_uid']: row for row in audit}
    standalone = []
    for row in active_observations:
        uid = row['generic_uid']
        original = bindings.get(uid)
        if not original:
            continue
        native = data.get(original['config_id'], {})
        own_quality = generic_quality(row)
        pair_audit = audit_index[uid]
        chosen_for_pair = (pair_audit['pair_verified'] and pair_audit.get('selected_performance_source_sha256') == row.get('performance_source_sha256')
                           and pair_audit.get('completed_at') == row.get('completed_at'))
        own_pair_reasons = bind(row, original, native)[0] + contract_reasons(row)
        if not chosen_for_pair and not own_pair_reasons:
            own_pair_reasons = pair_audit['exclusion_reasons'] if not pair_audit['pair_verified'] else ['not_selected_latest_compatible_generic_observation']
        own_pair_status = pair_audit['status'] if chosen_for_pair else 'not_selected_incompatible_or_unresolved' if any(reason != 'not_selected_latest_compatible_generic_observation' for reason in own_pair_reasons) else 'not_selected_older_compatible'
        closed = closure_cases.get(uid, {})
        historical_pair_reasons = sorted(set(own_pair_reasons))
        if closed.get('current_pair_hold_explanation') and not chosen_for_pair:
            own_pair_reasons = closed['pair_hold_reasons']
        standalone.append(dict(generic_uid=uid, model=row['model'], setup=row['setup'], task=native['task'], case=row['case_id'],
            native_quality_metric=native.get('quality_metric'), generic_quality_metric=native.get('quality_metric'),
            generic_fps=float(row['effective_generic_fps']) if positive(row.get('effective_generic_fps')) else None,
            generic_completed_at=row.get('completed_at'), generic_performance_source_sha256=row.get('performance_source_sha256'),
            performance_acquisition_origin=row.get('performance_acquisition_origin', 'reused_existing'),
            quality_acquisition_origin=row.get('quality_acquisition_origin', 'unknown'),
            generic_quality_value=own_quality['value'], generic_quality_reference_value=own_quality['reference'],
            generic_relative_quality_loss=own_quality['relative_loss'], generic_quality_status=own_quality['status'],
            generic_quality_completed_at=row.get('quality_completed_at'),
            performance_source_epochs=row.get('source_epochs', {}), generic_quality_source_epochs=row.get('quality_binding', {}).get('source_epochs', {}), generic_quality_own_admitted=own_quality['admitted'],
            generic_quality_exclusion_reasons=own_quality['reasons'],
            generic_quality_legacy_1pct_decision=row.get('quality_binding', {}).get('legacy_1pct_decision'),
            generic_quality_legacy_1pct_margin_absolute_ap=row.get('quality_binding', {}).get('legacy_1pct_margin_absolute_ap'),
            typed_quality_import_authorities=row.get('typed_quality_import_authorities', []),
            native_quality_value=native.get('quality_value'),
            native_quality_reference_value=native.get('quality_reference_value'), native_relative_quality_loss=quality_loss(native),
            pair_compatible_selected=chosen_for_pair, pair_eligible=chosen_for_pair and pair_audit['quality_eligible'],
            pair_status=own_pair_status, pair_hold_reasons=sorted(set(own_pair_reasons)),
            historical_pair_hold_reasons=historical_pair_reasons if closed.get('current_pair_hold_explanation') else [],
            current_pair_hold_explanation=closed.get('current_pair_hold_explanation'),
            native_cpu_reference_sha256=native.get('quality_reference_sha256') or row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding', {}).get('cpu_reference_sha256'),
            generic_cpu_reference_sha256=row.get('quality_binding', {}).get('cpu_reference_sha256'),
            pair_quality_exclusion_reasons=pair_audit['quality_exclusion_reasons'] if chosen_for_pair else ['observation_not_selected_for_native_pair'],
            native_quality_scope=('Actual selected timed Native completion records, evaluated by the normal quality workflow.'
                if native.get('quality_timed_endpoint_bound') else 'Preserved historical normal quality; exact timed Native endpoint AP is not asserted.')))
    families = family_results(pairs, quality, selected, quality_selected, comparison, bindings)
    previous = read(repo / 'results/split-inference/publications/mlsys-r22/data/quality_selection_groups.json')
    imports_complete = bool(accounting is not None and not accounting.get('remaining_actual_quality_import_UIDs') and not any(row['corrected_quality_pending'] for row in audit))
    publication_status = 'complete' if imports_complete and not any(row['unresolved'] for row in coverage) else 'incomplete'
    summary = dict(schema='rq2-native-scope-pairs-v1', publication_status=publication_status,
        actual_imports_complete=imports_complete, actual_import_accounting_sha256=sha(accounting_path) if accounting else None,
        quality_metrics={'classification':'top1_accuracy', 'detection':'coco_ap_50_95'}, detection_metric_label='COCO AP@[.50:.05:.95]',
        family_selection_results=families,
        original_native_population=len(bindings), original_native_detector_pairs=sum(r['task'] == 'detection' for r in bindings.values()),
        pair_count=len(pairs), quality_pair_count=len(quality), group_count=len(selected), quality_group_count=len(quality_selected),
        quality_singleton_groups=sum(r['singleton'] for r in quality_selected), quality_groups_n_ge_2=sum(r['ranking_evaluable'] for r in quality_selected),
        models=sorted({r['model'] for r in quality}), classifier_quality_pairs=sum(r['task'] == 'classification' for r in quality),
        detector_quality_pairs=sum(r['task'] == 'detection' for r in quality), final_generic_observations=len(observations['rows']),
        selected_generic_observations=len(pairs), source_found=sum(r['source_found'] for r in audit), compatible_selected=len(pairs),
        new_fps_captured=sum(r['new_fps_captured'] for r in audit), new_quality_captured=sum(r['new_quality_captured'] for r in audit),
        new_fps_capture_observations=sum(r['new_fps_capture_observations'] for r in audit),
        new_quality_capture_observations=sum(r['new_quality_capture_observations'] for r in audit),
        coverage_count_definitions={'source_found':'Original cuts with any recovered Generic source, including standalone observations held from pairing.',
            'compatible_selected':'Original cuts with a selected identity- and complete-task-compatible Generic pair.',
            'recovered':'Compatible selected observations recovered from existing sources; legacy selected-pair meaning retained.',
            'remeasured':'Original cuts with an actual new FPS capture, including standalone captures held from pairing; alias of new_fps_captured.',
            'new_quality_captured':'Original cuts with actual new quality captures declared in hash-bound overlay provenance, independent of FPS acquisition or pair admission.',
            'capture_observations':'Distinct actual capture source observations; repeat captures of one cut remain distinct, duplicate source hashes are counted once.'},
        prior_published_pairs=len(bindings),
        prior_published_quality_pairs=frozen['scope']['all_source_quality_eligible_pairs'],
        excluded_candidates=sum(r['status'] == 'excluded' for r in audit), unresolved_candidates=sum(r['status'] == 'unresolved' for r in audit),
        groups_without_quality_pairs=sum(not r['quality_admitted'] for r in coverage),
        rq3_fixed420_members=sum(r['rq3_fixed420_member'] for r in audit), outside_rq3_fixed420_pairs=sum(not r['rq3_fixed420_member'] for r in pairs),
        exclusion_reasons=dict(Counter(reason for r in audit for reason in r['exclusion_reasons'] + r['quality_exclusion_reasons'])),
        scope='All original artifact-bound measured Native cut identities; RQ3 fixed420 membership is an annotation only. No Native values imputed or remeasured.',
        selection_policy='Latest actually completed identity- and complete-task-contract-compatible valid Generic observation; selection precedes quality admission and never ranks FPS, AP or quality outcome.',
        overall_statistic='Unchanged equal-group mean over nonempty quality-admitted model/device groups; singleton zero loss is not evidence of ranking quality.',
        mean_final_generic_loss_pct=average(r['loss_pct'] for r in quality_selected),
        mean_final_generic_loss_n_ge_2_pct=average(r['loss_pct'] for r in quality_selected if r['ranking_evaluable']),
        same_pairs_comparison_pair_count=len(comparison_ranks), same_pairs_comparison_group_count=len(comparison),
        mean_old_generic_loss_same_pairs_pct=average(r['old_loss_pct'] for r in comparison),
        mean_final_generic_loss_same_pairs_pct=average(r['final_loss_pct'] for r in comparison),
        mean_old_generic_loss_same_pairs_n_ge_2_pct=average(r['old_loss_pct'] for r in comparison if r['ranking_evaluable']),
        mean_final_generic_loss_same_pairs_n_ge_2_pct=average(r['final_loss_pct'] for r in comparison if r['ranking_evaluable']),
        prior_full_quality_scope_mean_loss_pct=average(r['loss_pct'] for r in previous),
        weights={'default': frozen['default_weights'], 'shared': frozen['shared_weights'],
            'model_held_out': {r['held_out_model']: {k: r[k] for k in ['w_comm', 'w_imb', 'w_tensors']} for r in frozen['folds']}},
        weight_policy='All prior vectors and original full graph normalization universes frozen; no fit. Original holdout status describes original training.',
        native_quality_policy='Established historical Native numerical quality metric and <=5% gate retained. Historical Native AP is not asserted to be exact selected timed Native endpoint AP; source-scoped postfilter differences are explicitly reported.',
        generic_quality_policy='Current bound normal Generic quality evaluates actual selected timed completion records against its own existing CPU-ONNX reference and evaluator policy. Invalidated quality assignment evidence remains history; corrected unavailable quality is pending, never physical accuracy_loss.',
        known_quality_timed_contract_difference_cases=[r['generic_uid'] for r in pairs if r.get('completion_provenance')],
        corrected_quality_pending=sum(r['corrected_quality_pending'] for r in audit),
        reviewed_metadata_pairs=sum(bool(r.get('pairing_metadata_note')) for r in pairs),
        energy_policy='Original Native, Full and Generic energy records stay in their original dataset. No refreshed Generic rate is paired to old energy as one joint observation.')
    if current_native:
        summary.update(current_native_dataset_sha256=sha(native_dataset_path or repo/'results/split-inference/data/PAPER_DATASET.json'),
            current_native_replacement_count=len(current_native),
            current_native_replacements=[dict(native_uid=row['uid'], metric_updates=row['current_observation_metric_updates'],
                performance_source_sha256=row['performance_source_sha256'], quality_source_sha256=row.get('quality_source_sha256'),
                energy_source_sha256=row.get('energy_source_sha256'), evidence_sha256=row['current_native_binding']['evidence_sha256'])
                for row in current_native],
            native_quality_policy='Use only own bound current normal quality for explicitly replaced Native observations; missing current quality remains unavailable. Retain historical Native quality and the established <=5% gate for unchanged cuts. Prior values and source-scoped postfilter differences remain archived.',
            prior_actual_accounting_retained_as_history=accounting is not None,
            scope='All original artifact-bound measured Native cut identities; current normal Native observations replace only their source-bound archived predecessors. RQ3 membership remains an annotation; no imputation or new Native cuts.',
            energy_policy='Archived Native/Full/Generic energy observations are preserved. Current curated energy requires its exact selected FPS-source relation; no refreshed Generic rate inherits old energy.')
        summary['historical_quality_timed_contract_difference_cases'] = summary['known_quality_timed_contract_difference_cases']
        summary['known_quality_timed_contract_difference_cases'] = [row['generic_uid'] for row in pairs
            if row.get('completion_provenance') and not row.get('native_quality_timed_endpoint_bound')]
        summary['current_native_external_captures'] = {metric:sum(metric in row['current_observation_metric_updates'] and
            row.get(metric+'_acquisition_origin') == 'new_capture' for row in current_native)
            for metric in ['performance', 'quality', 'energy']}
    if accounting is not None:
        actual_counts = dict(original_native_cases=len(bindings), generic_sources_found=summary['source_found'],
            actual_performance_candidates=len(observations['rows']), compatible_selected_pairs=len(pairs),
            quality_admitted_pairs=len(quality), excluded=summary['excluded_candidates'], unresolved=summary['unresolved_candidates'],
            new_fps_captured=summary['new_fps_captured'], new_quality_captured=summary['new_quality_captured'],
            corrected_quality_pending=summary['corrected_quality_pending'])
        if actual_counts != accounting['counts'] and not current_native:
            raise ValueError('Publication reproduction differs from the bound actual import accounting')
    sources = [OLD / 'inputs/current_graph_feature_inputs.zip', OLD / 'analysis/candidate_features.csv', OLD / 'analysis/summary.json',
               Path('results/split-inference/data/PAPER_DATASET.json'), POLICY]
    if accounting is not None:
        sources.append(STUDY / 'ACTUAL_IMPORT_ACCOUNTING.json')
    try:
        input_name = str(input_path.relative_to(repo))
    except ValueError:
        input_name = str(input_path)
    proof_sources = []
    for path in sorted(input_path.parent.glob('*.json')):
        if path.resolve() == input_path.resolve() or path.resolve() == (repo / POLICY).resolve():
            continue
        try:
            name = str(path.relative_to(repo))
        except ValueError:
            name = str(path)
        proof_sources.append(dict(path=name, sha256=sha(path)))
    if native_dataset_path is not None and sha(native_dataset_path) != sha(repo/'results/split-inference/data/PAPER_DATASET.json'):
        sources = [path for path in sources if str(path) != 'results/split-inference/data/PAPER_DATASET.json']
        proof_sources.append(dict(path='current-curated-build/data/PAPER_DATASET.json', sha256=sha(native_dataset_path)))
    manifest = dict(schema='rq2-native-scope-input-manifest-v1', source_snapshot_sha256=observations.get('source_snapshot_sha256'),
        source_selection_sha256=observations.get('source_selection_sha256'), sources=[dict(path=str(p), sha256=sha(repo / p)) for p in sources] + [dict(path=input_name, sha256=sha(input_path))] + proof_sources)
    write_json(output / 'INPUT_MANIFEST.json', manifest)
    write_json(output / 'summary.json', summary)
    unbound = [dict(generic_uid=uid, reason='no_original_artifact_bound_native_identity', candidate_observations=len(rows)) for uid, rows in sorted(indexed.items()) if uid not in bindings]
    for name, rows in [('current_pairs', pairs), ('quality_pairs', quality), ('selection_groups', selected), ('quality_selection_groups', quality_selected),
                       ('pair_identity_audit', audit), ('old_final_same_pairs_comparison', comparison), ('old_final_same_pairs_rankings', comparison_ranks),
                       ('pair_group_coverage', coverage), ('family_selection_summary', families), ('standalone_generic_observations', standalone), ('non_population_observations', unbound),
                       ('historical_quality_observations', [dict(generic_uid=r['generic_uid'], history=r['quality_history']) for r in observations['rows'] if r.get('quality_history')])]:
        write_json(output / 'data' / f'{name}.json', rows); write_csv(output / 'data' / f'{name}.csv', rows)
    for name, rows in [('pair_group_coverage', coverage), ('family_selection_summary', families), ('native_generic_quality_observations', standalone)]:
        write_json(output / 'tables' / f'{name}.json', rows); write_csv(output / 'tables' / f'{name}.csv', rows)
    for name, rows in [('group_curves', group_curves), ('aggregate_curves', aggregate), ('complete_rankings', rankings),
                       ('key_budget_results', [r for r in aggregate if r['k'] in [1, 3, 5]])]:
        write_csv(output / 'analysis' / f'{name}.csv', rows)
    # One compact sensitivity keeps the pairing judgement inspectable while
    # retaining one main dataset and one set of figures.
    sensitivity, runner_comparison = [], []
    for inclusion, pool in [('included', quality), ('excluded', [r for r in quality if not r.get('pairing_metadata_note')])]:
        for target in ['native', 'generic']:
            target_pool = pool if target == 'native' else [dict(r, native_fps=r['generic_fps']) for r in pool]
            _, totals, _ = curves(target_pool, graph, frozen)
            for item in totals:
                if item['k'] in [1, 2, 3, 4, 5]:
                    sensitivity.append(dict(reviewed_pair=inclusion, target=target, candidates=len(pool),
                        method=item['method'], k=item['k'], groups=item['groups'],
                        mean_loss_pct=item['mean_loss_pct'], exact_winners=item['exact_winners']))
                    if inclusion == 'included':
                        runner_comparison.append(sensitivity[-1])
    write_csv(output / 'data/pairing_sensitivity.csv', sensitivity)
    write_csv(output / 'data/runner_graph_comparison.csv', runner_comparison)
    sys.path.insert(0, str(repo / 'scripts/split-inference'))
    from publication_mlsys_data import budget_calculations
    budget_groups, budgets = budget_calculations(pairs, quality)
    for row in budget_groups:
        row.update(singleton=row['candidate_count'] == 1, ranking_evaluable=row['candidate_count'] >= 2)
    for row in budgets:
        multi = [r for r in budget_groups if r['scope'] == row['scope'] and r['requested_k'] == row['requested_k']
                 and (row['family'] == 'all' or r['family'] == row['family']) and r['ranking_evaluable']]
        row.update(groups_n_ge_2=len(multi), singleton_groups=row['groups'] - len(multi),
                   generic_mean_loss_n_ge_2_pct=average(r['generic_loss_pct'] for r in multi),
                   random_mean_expected_loss_n_ge_2_pct=average(r['random_expected_loss_pct'] for r in multi))
    write_json(output / 'data/budget_groups.json', budget_groups); write_csv(output / 'data/budget_groups.csv', budget_groups)
    for name, rows in [('current_selection_groups', selected), ('r14_budget_details', budgets)]:
        write_json(output / 'tables' / f'{name}.json', rows); write_csv(output / 'tables' / f'{name}.csv', rows)
        if name == 'current_selection_groups':
            headers = ['Model', 'Host', 'n', 'Ranking evaluable', 'G choice', 'N best', 'Selected FPS', 'Best FPS', 'Loss (%)']
            model_labels = {'mobilenet_v3_large':'MobileNetV3-L', 'regnet_x_1_6gf':'RegNet-X', 'resnet50':'ResNet-50',
                'yolo11l':'YOLO11l', 'yolo26m':'YOLO26m', 'yolo26s':'YOLO26s', 'yolov7_paper':'YOLOv7'}
            values = [[model_labels[r['model']], r['setup'], str(r['candidate_count']), str(r['ranking_evaluable']),
                r['generic_choice'], r['native_best'], f"{r['selected_native_fps']:.0f}", f"{r['best_native_fps']:.0f}", f"{r['loss_pct']:.2f}"] for r in rows]
            caption = 'Current Generic selection on original Native cuts without quality filtering. Groups with fewer than two cuts do not establish ranking quality.'
        else:
            headers = ['Eligibility', 'Family', 'Groups', 'Cuts', 'k', 'G loss (%)', 'U loss (%)', 'G hits', 'U hits']
            values = [[r['scope'], r['family'], str(r['groups']), str(r['candidates']), str(r['requested_k']),
                f"{r['generic_mean_loss_pct']:.2f}", f"{r['random_mean_expected_loss_pct']:.2f}", str(r['generic_exact_hits']), f"{r['random_expected_exact_hits']:.3f}"] for r in rows]
            caption = 'Generic ranking and exact uniform sampling on current evidence. Every nonempty group receives equal weight; singleton status is recorded in group data.'
        escape = lambda value: str(value).replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')
        (output / 'tables' / f'{name}.tex').write_text('% ' + caption + '\n' + '\n'.join([
            r'\begin{tabular}{' + 'l' * len(headers) + '}', ' & '.join(escape(v) for v in headers) + r' \\'] + [
            ' & '.join(escape(v) for v in row) + r' \\' for row in values] + [r'\end{tabular}']) + '\n')
        (output / 'tables' / f'{name}.md').write_text(caption + '\n\n' + '\n'.join([
            '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + [
            '| ' + ' | '.join(row) + ' |' for row in values]) + '\n')
    provenance = copy.deepcopy(observations.get('completion_provenance', {}))
    if current_native:
        provenance['current_native_observations'] = [dict(native_uid=row['uid'],
            metric_updates=row['current_observation_metric_updates'],
            performance_source_sha256=row['performance_source_sha256'],
            quality_source_sha256=row.get('quality_source_sha256'),
            quality_timed_endpoint_bound=row.get('quality_timed_endpoint_bound', False),
            binding_evidence_sha256=row['current_native_binding']['evidence_sha256']) for row in current_native]
        provenance['native_gate'] = summary['native_quality_policy']
        provenance['limitation'] = ('Historical additional-NMS evaluations remain archived in cases. '
            'Explicit current Native observations use their own normal selected-timed-completion evaluation; '
            'this replacement is bounded to the listed source identities. Other historical cases remain unassessed here.')
        for case in provenance.get('cases', []):
            native_uid = case['generic_uid'].replace('generic|', 'native|', 1)
            native = data.get(native_uid, {})
            if native.get('quality_timed_endpoint_bound'):
                case['historical_native_quality_retained_as_archive'] = True
                case['current_native_quality_timed_endpoint_bound'] = True
                case['current_native_quality_source_sha256'] = native['quality_source_sha256']
                case['current_native_binding_evidence_sha256'] = native['current_native_binding']['evidence_sha256']
    write_json(output / 'data/quality_contract_provenance.json', provenance)
    render(output, numeric_only)
    validation = dict(result='PASS', validation_scope='Offline importer and evidence accounting only; this does not claim hardware or missing quality PASS.',
        original_native_population_fully_accounted=len(audit) == len(bindings),
        every_original_cut_admitted_excluded_or_unresolved=sum(r['quality_admitted'] + r['excluded'] + r['unresolved'] for r in coverage) == len(bindings),
        final_actual_import_accounting_verified=accounting is not None and actual_counts == accounting['counts'],
        historical_generic_import_accounting_bound=accounting is not None,
        no_fixed420_admission_filter=True, selection_precedes_quality=True, original_native_and_full_records_modified=False,
        current_native_replacements_source_bound=bool(current_native),
        no_new_fps_old_energy_joint_measurement=True, weights_refitted=False)
    if verify_reference:
        validation['published_reference'] = legacy.verify(output, verify_reference)
    write_json(output / 'VALIDATION.json', validation)
    family = {r['family']: r for r in families if r['scope'] == 'quality_admitted'}
    number = lambda value: 'unavailable' if value is None else f'{value:.4f}'
    rows = "\n".join(f"| {label} | {family[key]['paired_candidates']} | {family[key]['model_device_groups']} | {number(family[key]['mean_loss_pct'])} |"
        for key, label in [('all', 'All models'), ('classification', 'Classifiers'), ('detection', 'Detectors')])
    (output / 'README.md').write_text(
        "# Selecting Native splits with Generic\n\n"
        f"The comparison covers {len(bindings)} measured cuts on seven models and three accelerator setups. "
        f"The 5% relative quality-loss rule admits {len(quality)} paired cuts in {len(quality_selected)} model–device groups. "
        f"{summary['excluded_candidates']} cuts exceed this quality limit.\n\n"
        "For each group, Generic recommends its fastest measured cut. We evaluate that recommendation by its Native throughput, "
        "relative to the fastest measured Native cut in the same group. Each group contributes equally.\n\n"
        "| Models | Paired cuts | Groups | Mean Native loss (%) |\n|---|---:|---:|---:|\n" + rows + "\n\n"
        "[Shortlist results](analysis/key_budget_results.csv) show how the loss changes when more than one recommendation can be tested. "
        "[Group results](data/quality_selection_groups.csv) identify the selected cuts. "
        "The [paired observations](data/current_pairs.csv) contain the measurement values and quality decisions. "
        "[Runner comparison](data/runner_graph_comparison.csv) evaluates the same graph shortlists with Generic and Native.\n\n"
        "RQ3 uses a broader candidate set to evaluate graph rankings against Generic throughput. It is available from the "
        "[current study entry](../generic420-closeout-20261027/README.md). The two analyses answer different selection questions within the same study.\n\n"
        "## Reproduce\n\n"
        "```bash\npython3 scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py --output local-output/rq2 --verify\n```\n\n"
        "Run from the repository root. Add `--numeric-only` to omit rendering. "
        "[Measurement notes](DATA_NOTES.md) explain the few retained source differences. "
        "The input manifest and detailed source records support reproduction without making the measurement chronology part of the result.\n\n"
        "<!-- assemble_inputs.py reconstructs historical acquisition sources. It does not apply the published pairing review. "
        "Normal reproduction reads the current observations.json and validates that review separately. -->\n")
    (output / 'DATA_NOTES.md').write_text(
        "# Measurement notes\n\n"
        "H8/YOLOv7/b009 is included using its matching executable artifacts, recorded runtime parameters and retained image/tensor checks. "
        "The complete historical Native preprocessing recipe was not logged, and its missing hash has not been reconstructed. "
        "The source review is in `inputs/PAIRING_REVIEW_b009.json`. "
        "The compact `data/pairing_sensitivity.csv` reports results with and without this pair. "
        "All Generic recommendation losses and the number of Native winners found remain unchanged.\n\n"
        "Quality uses Top-1 accuracy for classifiers and COCO AP50:95 for detectors, relative to the CPU-ONNX reference. "
        "The recorded Native quality evaluations for YOLO26m/b043 on H8 and H10 include an additional NMS step, "
        "which is absent from their timed completion paths. These quality values therefore describe the recorded evaluation pipeline. "
        "Their exact source mapping is retained in `data/quality_contract_provenance.json`.\n\n"
        "Native, Full and energy measurements retain their recorded values. Generic throughput is not combined with energy from a different run. "
        "The archived import receipts preserve the acquisition history; the current input manifest identifies the observations used here.\n")
    if current_native:
        b009 = next((row for row in current_native if row['uid'] == 'native|yolov7_paper|H8|hailo8_to_trt|b009'), None)
        note = ('H8/YOLOv7/b009 uses a new normal Native observation with its actual current preprocessing and completion binding. '
            'The current Generic observation is unchanged. The original Native row and its incomplete historical preprocessing '
            'metadata review remain archived; their missing historical hash has not been reconstructed.\n\n'
            if b009 and 'performance' in b009['current_observation_metric_updates'] else
            'H8/YOLOv7/b009 retains the reviewed executable, runtime and observed-input evidence. '
            'Its complete historical Native preprocessing recipe was not logged and has not been reconstructed. '
            'The review remains in inputs/PAIRING_REVIEW_b009.json; data/pairing_sensitivity.csv reports the paired sensitivity.\n\n')
        (output/'DATA_NOTES.md').write_text('# Measurement notes\n\n' + note +
            'Quality uses Top-1 accuracy for classifiers and COCO AP50:95 for detectors relative to their own CPU-ONNX reference. '
            'The explicitly listed current Native quality observations evaluate actual selected timed completion records. '
            'Prior evaluations with an additional NMS step remain historical evidence in data/quality_contract_provenance.json; '
            'current replacements and all source identities are listed separately. Other cases are not assigned a new quality contract.\n\n'
            'Active deployment rows replace only declared, normally admitted metrics; original observations remain archived. '
            'Full measurements are unchanged. Generic throughput never inherits energy from a different performance observation. '
            'The broad RQ1 deployment dataset retains unchanged Generic FPS/energy observations from their recorded generations; '
            'these are separate observations from the current Generic FPS used in this RQ2 comparison. '
            'The current input manifest and source-bound replacement records identify the observations used here.\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--native-dataset', type=Path, help='Current curated PAPER_DATASET with explicit Native replacement bindings')
    parser.add_argument('--numeric-only', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve(), numeric_only=args.numeric_only, input_path=args.input, native_dataset_path=args.native_dataset,
                         verify_reference=REPO / STUDY if args.verify else None), indent=2))
