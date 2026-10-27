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
quality_loss, load_public = legacy.quality_loss, legacy.load_public


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


def contract_reasons(row):
    contract = row.get('observation_contract') or {}
    reasons = []
    relation = row.get('pair_compatibility') or {}
    if relation.get('verified') is False:
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


def render(output, numeric_only):
    summary = read(output / 'summary.json')
    with (output / 'analysis/aggregate_curves.csv').open() as stream:
        raw = list(csv.DictReader(stream))
    caption = (f"Native throughput loss on {summary['quality_pair_count']} quality-admitted original Native cuts in "
        f"{summary['quality_group_count']} model/device groups; {summary['quality_singleton_groups']} groups have fewer than two cuts. "
        "Latest actually completed compatible Generic observation, selected before quality. Equal weight per nonempty group; "
        "also report the mean restricted to n>=2. Original graph weights and normalization universes are frozen. "
        "RQ3 fixed420 membership is only an annotation; missing evidence remains unavailable.")
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
        scatter_caption = (f'Generic-to-Native selection on {pair_count} verified paired cuts in {len(points)} model/device groups; '
            f'{singleton_count} groups have fewer than two cuts. ' +
            ('Both Native historical numerical quality and current bound Generic quality pass. ' if key.startswith('quality') else 'No quality filter. ') +
            'Hollow markers denote one candidate, which provides no ranking test. Every nonempty group has equal weight. '
            'Original Native FPS and historical Native quality retain their separate observed contracts.')
        write_json(output / 'figures' / f'{name}.json', dict(points=points, caption=scatter_caption,
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
            points = read(output / 'figures' / f'{name}.json')['points']; fig, ax = plt.subplots(figsize=(3.3, 2.3))
            for setup, marker, color in [('H8', 'o', 'blue'), ('H10', 's', 'yellow'), ('DeepX', '^', 'green')]:
                selected = [r for r in points if r['setup'] == setup]
                ordinary = [r for r in selected if not r['singleton']]
                singleton = [r for r in selected if r['singleton']]
                ax.scatter([r['candidate_count'] for r in ordinary], [r['loss_pct'] for r in ordinary], label=setup,
                           marker=marker, s=24, color=PAPER_PALETTE[color])
                ax.scatter([r['candidate_count'] for r in singleton], [r['loss_pct'] for r in singleton],
                           marker=marker, s=24, facecolors='none', edgecolors=PAPER_PALETTE[color])
            handles, labels = ax.get_legend_handles_labels()
            if any(r['singleton'] for r in points):
                from matplotlib.lines import Line2D
                handles.append(Line2D([], [], marker='o', markerfacecolor='none', markeredgecolor=PAPER_PALETTE['dark_gray'],
                                      linestyle='None', markersize=5))
                labels.append('One candidate (no ranking test)')
            ax.set(xlabel='Verified paired candidates in group', ylabel='Native throughput loss (%)')
            if any(r['singleton'] for r in points):
                lower, upper = ax.get_xlim()
                ax.set_xticks(sorted({1.0} | {tick for tick in ax.get_xticks() if lower <= tick <= upper}))
            ax.legend(handles, labels, frameon=False, fontsize=7); fig.tight_layout()
            legacy.save_figure(fig, output / 'figures' / name); plt.close(fig)
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


def run(output, repo=REPO, numeric_only=False, verify_reference=None, input_path=None):
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
    bindings, graph, data, frozen = load_public(repo)
    fixed = set(observations.get('fixed420_uids', []))
    indexed = defaultdict(list)
    for row in observations['rows']:
        indexed[row['generic_uid']].append(row)
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
            native_quality_scope='Preserved historical normal quality observation; exact selected timed Native endpoint AP is not established by its numeric record alone.',
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
            native_cpu_reference_sha256=row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding', {}).get('cpu_reference_sha256'),
            generic_cpu_reference_sha256=row.get('quality_binding', {}).get('cpu_reference_sha256'),
            preserved_native_quality_reference_binding=row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding'),
            completion_provenance=row.get('completion_provenance'), quality_correction=row.get('quality_correction'),
            typed_quality_import_authorities=row.get('typed_quality_import_authorities', [])))

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
    audit_index = {row['generic_uid']: row for row in audit}
    standalone = []
    for row in observations['rows']:
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
            native_cpu_reference_sha256=row.get('quality_binding', {}).get('preserved_Native_quality_reference_binding', {}).get('cpu_reference_sha256'),
            generic_cpu_reference_sha256=row.get('quality_binding', {}).get('cpu_reference_sha256'),
            pair_quality_exclusion_reasons=pair_audit['quality_exclusion_reasons'] if chosen_for_pair else ['observation_not_selected_for_native_pair'],
            native_quality_scope='Preserved historical normal quality; exact timed Native endpoint AP is not asserted.'))
    families = family_results(pairs, quality, selected, quality_selected, comparison, bindings)
    previous = read(repo / 'results/split-inference/publications/mlsys-r22/data/quality_selection_groups.json')
    imports_complete = bool(accounting is not None and not accounting.get('remaining_actual_quality_import_UIDs') and not any(row['corrected_quality_pending'] for row in audit))
    publication_status = ('complete_with_documented_native_authority_hold' if any(row['unresolved'] for row in coverage) else 'complete_evidence_audit') if imports_complete else ('provisional_unresolved_evidence' if any(row['unresolved'] for row in coverage) else 'complete_evidence_audit')
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
        energy_policy='Original Native, Full and Generic energy records stay in their original dataset. No refreshed Generic rate is paired to old energy as one joint observation.')
    if accounting is not None:
        actual_counts = dict(original_native_cases=len(bindings), generic_sources_found=summary['source_found'],
            actual_performance_candidates=len(observations['rows']), compatible_selected_pairs=len(pairs),
            quality_admitted_pairs=len(quality), excluded=summary['excluded_candidates'], unresolved=summary['unresolved_candidates'],
            new_fps_captured=summary['new_fps_captured'], new_quality_captured=summary['new_quality_captured'],
            corrected_quality_pending=summary['corrected_quality_pending'])
        if actual_counts != accounting['counts']:
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
    write_json(output / 'data/quality_contract_provenance.json', observations.get('completion_provenance', {}))
    render(output, numeric_only)
    validation = dict(result='PASS', validation_scope='Offline importer and evidence accounting only; this does not claim hardware or missing quality PASS.',
        original_native_population_fully_accounted=len(audit) == len(bindings),
        every_original_cut_admitted_excluded_or_unresolved=sum(r['quality_admitted'] + r['excluded'] + r['unresolved'] for r in coverage) == len(bindings),
        final_actual_import_accounting_verified=accounting is not None,
        no_fixed420_admission_filter=True, selection_precedes_quality=True, original_native_and_full_records_modified=False,
        no_new_fps_old_energy_joint_measurement=True, weights_refitted=False)
    if verify_reference:
        validation['published_reference'] = legacy.verify(output, verify_reference)
    write_json(output / 'VALIDATION.json', validation)
    (output / 'README.md').write_text(f"# RQ2 original Native population\n\n{summary['original_native_population']} original Native cuts in {len(coverage)} model/device groups are accounted for. "
        f"{len(pairs)} have a selected valid compatible Generic observation; {len(quality)} pass both Native numerical quality and current bound Generic quality in {len(quality_selected)} groups. "
        f"{summary['excluded_candidates']} are excluded and {summary['unresolved_candidates']} remain unresolved. Publication status: {summary['publication_status']}.\n\n"
        f"`source_snapshot_sha256={manifest['source_snapshot_sha256']}` identifies the historical 192-observation base. "
        "The separate INPUT_MANIFEST.json hash for inputs/observations.json binds the complete current RQ2 input, including "
        f"{summary['outside_rq3_fixed420_pairs']} extra cuts, {summary['new_quality_captured']} new quality captures and {summary['new_fps_captured']} new FPS captures with retained provenance. "
        "The adopted fixed420 ledger d658eb19… is separate current RQ3 authority; it does not replace the RQ2 observations outside that cohort. Historical source hashes retain their original meaning.\n\n"
        "RQ3 fixed420 membership is an annotation. The importer iterates the original Native population and admits valid observations outside that set. "
        "Every group reports original cuts, Generic sources found, compatible selected pairs, recovered compatible observations, actual new FPS captures, actual new quality captures, admissions, exclusions and unresolved counts. "
        "Sources found and actual captures include standalone observations held from pairing. Recovered retains its compatible-selected meaning; remeasured counts new FPS captures only. Quality-only captures are separate and come from actual overlay acquisition provenance. "
        "tables/native_generic_quality_observations.csv retains observed standalone Generic AP/reference/loss even when pair_eligible is false, with exact pair hold reasons. "
        "Missing quality evidence is unavailable, never a measured accuracy loss. Native and Generic values and their own CPU-ONNX references remain separate.\n\n"
        f"The equal-group mean retains its established definition: {summary['mean_final_generic_loss_pct']}; the mean restricted to groups with n>=2 is {summary['mean_final_generic_loss_n_ge_2_pct']}. "
        f"{summary['quality_singleton_groups']} groups have a single admitted cut; zero loss for a singleton provides no ranking evidence. "
        "Old/current Generic choices and complete ranks use exactly the same quality-admitted eligible pairs with both rates available.\n\n"
        f"Actual imports are complete: {summary['actual_imports_complete']}; new FPS captures: {summary['new_fps_captured']}, new quality captures: {summary['new_quality_captured']}, pending quality corrections: {summary['corrected_quality_pending']}. "
        "The documented Native authority hold concerns original historical preprocessing evidence. Fresh Generic FPS and quality are complete; further Generic recapture is not required and cannot establish that historical Native authority.\n\n"
        "Native quality retains its recorded historical metric, which is not asserted to be exact selected timed Native endpoint AP. Current Generic quality evaluates its actual timed completion records against its own CPU-ONNX reference under the unchanged normal policy. Proven additional-NMS differences are source-scoped in data/quality_contract_provenance.json; this quality-definition difference limits interpretation. "
        "Detector quality is COCO AP@[.50:.05:.95]; classification quality is Top-1 accuracy. The evaluator implementation suffix does not change the reported primary metric.\n\n"
        "All graph weights and normalization universes are frozen. Native, Full, historical energy, RQ1, RQ3 and original YOLOv7 case evidence remain unchanged. "
        "Refreshed Generic FPS never inherits historical energy as a joint observation.\n\n"
        "Reproduce with `python scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py --output <empty-dir> --verify`; add `--numeric-only` to omit rendering. "
        "`VALIDATION.json` validates offline accounting and reproduction only. Unresolved scientific evidence remains unresolved in `data/pair_identity_audit.json`.\n")
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--numeric-only', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve(), numeric_only=args.numeric_only, input_path=args.input,
                         verify_reference=REPO / STUDY if args.verify else None), indent=2))
