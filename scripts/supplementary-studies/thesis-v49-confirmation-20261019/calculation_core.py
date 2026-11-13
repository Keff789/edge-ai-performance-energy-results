"""Unmodified campaign calculation functions, without acquisition/audit I/O.

These functions aggregate exported measurement facts. They do not revalidate
raw traces, runtime admission records or physical electrical qualification.
See calculation_origins.json for exact source-file and function hashes.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import statistics


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def direction(value):
    return None if value is None else 'split_higher' if value > 0 else 'split_lower' if value < 0 else 'equal'


def direction_effect(reference, observed):
    if reference is None or observed is None:
        return 'unavailable'
    if direction(reference) == direction(observed):
        return 'same_observed_direction'
    return 'opposite_observed_direction' if reference * observed < 0 else 'different_including_equality'


def summary(values):
    return {'n': len(values), 'mean': statistics.mean(values) if values else None,
            'median': statistics.median(values) if values else None,
            'observed_min': min(values) if values else None, 'observed_max': max(values) if values else None}


def session(row):
    identity = row.get('attempt_id')
    if identity:
        return identity.split(':', 1)[0]
    return str(Path(row.get('attempt_file', row.get('inner_interval_analysis_path', ''))).parent.parent)


def binding_identity(row):
    return str(Path(row['path']).resolve()),row['sha256']


def aggregate(primary, targets, attempts, selected):
    """Supplement N/t and E/N stay separate from every original A row."""
    rates = {row['run_id']: row for row in primary['A_rows']}
    energies = {row['run_id']: row for row in primary['B_rows']}
    require(len(targets) == 2 and len({row['logical_run_id'] for row in targets}) == 2, 'exactly_two_distinct_targets_required')
    target_map = {row['logical_run_id']: row for row in targets}
    require(set(target_map) == set(rates)-set(energies), 'targets_must_be_exact_primary_B_null_slots')
    require(len(selected) == 2 and {row['logical_run_id'] for row in selected} == set(target_map), 'two_selected_or_null_target_records_required')
    collector_ids, go_ids, runtime_ids, duplicate_starts = set(), set(), set(), []
    first_collector_receipt={}
    started_by_target = {key: set() for key in target_map}
    for item in attempts:
        logical = item['logical_run_id']
        require(logical in target_map, 'attempt_outside_declared_supplement_targets')
        for name in ('uid', 'setup_id', 'block', 'position'):
            require(item[name] == target_map[logical][name], 'attempt_target_identity_changed:' + name)
        identity = item.get('collector_process_identity')
        if item.get('collector_process_started'):
            require(isinstance(identity, list) and len(identity) == 2 and all(type(v) is int and v > 0 for v in identity), 'actual_collector_PID_and_start_required')
            key = tuple(identity)
            if key in collector_ids:
                duplicate_starts.append(item['attempt'])
            collector_ids.add(key)
            first_collector_receipt.setdefault(key,binding_identity(item['attempt']))
            started_by_target[logical].add(key)
        for flag, key, seen in [('physical_source_GO_observed', 'physical_source_GO_identity', go_ids),
                                ('runtime_process_started', 'runtime_process_identity', runtime_ids)]:
            if item.get(flag):
                require(item.get(key) is not None, 'positive_start_flag_requires_identity:' + key)
                seen.add(canonical(item[key]))
    require(all(len(value) <= 3 for value in started_by_target.values()), 'maximum_three_new_physical_starts_per_target_exceeded')
    accepted, target_records = [], []
    for logical, target in target_map.items():
        original = rates[logical]
        require(original['uid'] == target['uid'] and original['block'] == target['block'], 'primary_target_UID_block_changed')
        rows = sorted([row for row in attempts if row['logical_run_id'] == logical], key=lambda row: row['attempt_number'])
        require(all(type(row['attempt_number']) is int and row['attempt_number']>0 for row in rows),'positive_logical_attempt_numbers_required')
        require(len({row['attempt_number'] for row in rows}) == len(rows), 'duplicate_logical_attempt_number')
        first = next((row for row in rows if row['assessment'].get('A_valid') is True and row['assessment'].get('B_valid') is True), None)
        chosen = next(row for row in selected if row['logical_run_id'] == logical)
        require((chosen.get('attempt') is None) == (first is None), 'selection_must_be_first_strict_A_plus_B_or_null')
        if first is not None:
            require(binding_identity(chosen['attempt']) == binding_identity(first['attempt']), 'later_or_value_selected_supplement_forbidden')
            require(first.get('collector_process_started') and first.get('physical_source_GO_observed')
                    and first.get('runtime_process_started'), 'accepted_supplement_requires_three_actual_start_receipts')
            require(first_collector_receipt[tuple(first['collector_process_identity'])]==binding_identity(first['attempt']),
                    'accepted_supplement_reuses_a_previous_collector_identity')
            own = first['assessment']['own_measurement']
            N, duration, E, EN = (own['N_completed'], own['native_makespan_including_drain_s'],
                                  own['conditional_energy_j'], own['conditional_energy_per_completed_j'])
            require(type(N) is int and N > 0 and all(number(v) and v > 0 for v in (duration, E, EN)), 'finite_own_N_t_E_required')
            require(math.isclose(E/N, EN, rel_tol=1e-12), 'supplement_E_over_N_must_use_own_N')
            require(math.isclose(N/duration, own['rate_per_s'], rel_tol=1e-10), 'supplement_rate_must_use_own_duration')
            accepted.append({'kind': 'supplement', 'run_id': logical, 'uid': target['uid'], 'block': target['block'],
                'attempt_id': first['attempt_id'], 'execution_run_id': first['execution_run_id'], 'attempt': first['attempt'],
                'session_id': first['attempt_id'].split(':', 1)[0], 'N_completed': N, 'duration_s': duration,
                'rate_per_s': N/duration, 'conditional_energy_j': E, 'conditional_energy_j_per_completion': EN,
                'source_completion': first['assessment'].get('source_completion'),
                'observed_gates': first['assessment'].get('observed_gates'),
                'model_domain_observation': first['assessment'].get('model_domain_observation'),
                'valid_for_final_energy': False, 'original_A_replaced': False})
        target_records.append({'logical_run_id': logical, 'uid': target['uid'], 'block': target['block'],
            'original_primary_attempt': target['original_primary_attempt'], 'primary_A': copy.deepcopy(original),
            'primary_B': None, 'supplement': copy.deepcopy(accepted[-1]) if first is not None else None,
            'new_physical_starts': len(started_by_target[logical]), 'attempt_count': len(rows)})
    all_energy = []
    for row in primary['B_rows']:
        enriched = copy.deepcopy(row)
        enriched.update(kind='primary', session_id=session(rates[row['run_id']]),
                        attempt_id=rates[row['run_id']].get('attempt_id'),
                        execution_run_id=rates[row['run_id']].get('execution_run_id',row['run_id']))
        all_energy.append(enriched)
    all_energy += copy.deepcopy(accepted)
    require(len({row['run_id'] for row in all_energy}) == len(all_energy), 'duplicate_logical_energy_coverage')
    pairs, impacts = [], []
    for model in primary['models']:
        uids = {'split': model['split_uid'], 'full': model['full_uid']}
        per_kind = {kind: [row for row in all_energy if row['uid'] == uid] for kind, uid in uids.items()}
        for block in range(1, 6):
            split = next((row for row in per_kind['split'] if row['block'] == block), None)
            full = next((row for row in per_kind['full'] if row['block'] == block), None)
            if split is None or full is None:
                continue
            contains = split['kind'] == 'supplement' or full['kind'] == 'supplement'
            cross_session = split['session_id'] != full['session_id']
            require(not contains or cross_session, 'new_supplement_pair_must_be_explicitly_cross_session')
            sv, fv = split['conditional_energy_j_per_completion'], full['conditional_energy_j_per_completion']
            pairs.append({'model': model['model'], 'block': block, 'split': split, 'full': full,
                'contains_supplement': contains, 'cross_session': cross_session,
                'conditional_energy_split_minus_full': sv-fv, 'conditional_energy_split_over_full': sv/fv,
                'pair_scope': 'logical block correspondence across separate acquisition sessions' if contains else 'unchanged primary energy acquisitions',
                'primary_A_pair_changed': False, 'valid_for_final_energy': False})
        stats = {kind: summary([row['conditional_energy_j_per_completion'] for row in rows]) for kind, rows in per_kind.items()}
        mean = stats['split']['mean']-stats['full']['mean'] if all(stats[k]['n'] for k in stats) else None
        primary_delta = model['conditional_energy_mean']['split_minus_full_j_per_completion']
        historical_delta = model['historical_thesis_energy_mean']['split_minus_full_j_per_completion']
        impacts.append({'model': model['model'], 'split_uid': uids['split'], 'full_uid': uids['full'],
            'primary_A_rate_summaries_unchanged': copy.deepcopy(model['rate_summaries']),
            'primary_A_pairs_unchanged': copy.deepcopy(model['rate_block_pairs']),
            'primary_rate_effect_on_historical_direction_unchanged': model['rate_effect_on_historical_point_direction'],
            'historical_energy_mean': copy.deepcopy(model['historical_thesis_energy_mean']),
            'primary68_energy_mean': copy.deepcopy(model['conditional_energy_mean']),
            'coverage_energy_statistics': stats, 'coverage_energy_mean_split_minus_full': mean,
            'coverage_energy_mean_split_over_full': stats['split']['mean']/stats['full']['mean'] if mean is not None else None,
            'primary_energy_direction': direction(primary_delta), 'historical_energy_direction': direction(historical_delta),
            'coverage_energy_direction': direction(mean), 'effect_vs_primary68': direction_effect(primary_delta, mean),
            'effect_vs_historical_mean': direction_effect(historical_delta, mean),
            'aggregation': 'arithmetic means of own per-acquisition E/N; primary68 plus separate accepted supplements',
            'same_session_five_pair_energy_confirmation_claimed': False, 'statistical_significance_claimed': False,
            'valid_for_final_energy': False})
    return {'primary_A_rows_unchanged': copy.deepcopy(primary['A_rows']),
            'primary_B_rows_unchanged': copy.deepcopy(primary['B_rows']),
            'primary_A_pairs_unchanged': copy.deepcopy(primary['A_pairs']),
            'primary_B_pairs_unchanged': copy.deepcopy(primary['B_pairs']),
            'target_records': target_records, 'all_supplement_attempts': copy.deepcopy(attempts),
            'accepted_supplements': accepted, 'logical_energy_coverage_records': all_energy,
            'coverage_energy_pairs': pairs, 'seven_model_impacts': impacts,
            'counts': {'primary_A': 70, 'primary_B': 68, 'primary_C': 0,
                'supplement_physical_starts': len(collector_ids), 'supplement_GO_starts': len(go_ids),
                'supplement_native_starts': len(runtime_ids), 'supplement_valid_A_plus_B': len(accepted),
                'logical_energy_coverage': len(all_energy), 'logical_energy_pairs': len(pairs),
                'new_cross_session_energy_pairs': sum(row['contains_supplement'] for row in pairs),
                'fully_qualified_absolute_energy': 0}, 'duplicate_start_receipt_bindings': duplicate_starts,
            'method': 'Supplement A is not pooled into the primary A statistics; E/N uses its own new N. Primary B-null remains null. Logical B coverage is 68 primary acquisitions plus separately identified supplements.'}


def split_full_impacts(plan,summary,meta,selection,historical_energy,direct_quality):
    """Describe all seven selected pairs, including opposite observed signs."""
    def span(values):
        return {'n':len(values),'median':statistics.median(values) if values else None,
                'observed_min':min(values) if values else None,'observed_max':max(values) if values else None}
    def direction(value):return None if value is None else 'split_higher' if value>0 else 'split_lower' if value<0 else 'equal'
    def effect(old,new):
        return ('nicht verfügbar' if old is None or new is None else 'gleiche beobachtete Richtung' if direction(old)==direction(new)
                else 'entgegengesetzte beobachtete Richtung' if old*new<0 else 'abweichende beobachtete Richtung einschließlich Gleichstand')
    def mean_energy(split_values,full_values):
        split_mean=statistics.mean(split_values) if split_values else None
        full_mean=statistics.mean(full_values) if full_values else None
        return {'aggregation':'arithmetic_mean_of_per_repeat_E_over_N','split_n':len(split_values),'full_n':len(full_values),
                'split_mean_j_per_completion':split_mean,'full_mean_j_per_completion':full_mean,
                'split_minus_full_j_per_completion':split_mean-full_mean if split_mean is not None and full_mean is not None else None,
                'split_over_full':split_mean/full_mean if split_mean is not None and full_mean not in (None,0) else None}
    selected={r['uid']:r for r in selection};models=sorted({r['uid'].split('|')[1] for r in plan['runs']});rows=[]
    for model in models:
        uids=sorted({r['uid'] for r in plan['runs'] if r['uid'].split('|')[1]==model})
        split=next(uid for uid in uids if uid.split('|')[-1]!='full');full=next(uid for uid in uids if uid.split('|')[-1]=='full')
        rate_cases={kind:[r for r in summary['accepted'] if r['uid']==uid] for kind,uid in [('split',split),('full',full)]}
        energy_cases={kind:[r for r in meta['conditional_nominal_energy_replicates'] if r['uid']==uid] for kind,uid in [('split',split),('full',full)]}
        stats={kind:span([r['rate_per_s'] for r in values]) for kind,values in rate_cases.items()}
        nominal={kind:span([r['conditional_energy_j_per_completion'] for r in values]) for kind,values in energy_cases.items()}
        old_rate=selected[split].get('fps');old_full=selected[full].get('fps')
        old_rate_delta=old_rate-old_full if old_rate is not None and old_full is not None else None
        old_e={kind:[float(r['reproduced_j_image']) for r in historical_energy if r['uid']==uid] for kind,uid in [('split',split),('full',full)]}
        old_e_delta=statistics.median(old_e['split'])-statistics.median(old_e['full']) if all(old_e.values()) else None
        thesis_energy_mean=mean_energy(old_e['split'],old_e['full'])
        new_energy_mean=mean_energy([r['conditional_energy_j_per_completion'] for r in energy_cases['split']],
                                    [r['conditional_energy_j_per_completion'] for r in energy_cases['full']])
        rate_delta=stats['split']['median']-stats['full']['median'] if all(stats[k]['n'] for k in stats) else None
        nominal_delta=nominal['split']['median']-nominal['full']['median'] if all(nominal[k]['n'] for k in nominal) else None
        pairs=[r for r in summary['block_paired_comparisons'] if r['model']==model]
        nominal_pairs=[r for r in meta['conditional_nominal_block_pairs'] if r['model']==model]
        quality=next((r for r in direct_quality if r['model']==model),None)
        rows.append({'model':model,'split_uid':split,'full_uid':full,'all_valid_rate_replicates':rate_cases,
                     'rate_summaries':stats,'rate_difference_of_available_case_medians':rate_delta,
                     'rate_ratio_of_available_case_medians':stats['split']['median']/stats['full']['median'] if rate_delta is not None else None,
                     'rate_block_pairs':pairs,'paired_rate_differences':span([r['rate_split_minus_full'] for r in pairs]),
                     'paired_rate_ratios':span([r['rate_split_over_full'] for r in pairs]),
                     'rate_paired_sign_counts':{'split_faster':sum(r['rate_split_minus_full']>0 for r in pairs),'split_slower':sum(r['rate_split_minus_full']<0 for r in pairs),'equal':sum(r['rate_split_minus_full']==0 for r in pairs)},
                     'five_block_rate_confirmation_complete':len(pairs)==5 and all(stats[k]['n']==5 for k in stats),
                     'historical_performance_rate_split_minus_full':old_rate_delta,
                     'rate_effect_on_historical_point_direction':effect(old_rate_delta,rate_delta),
                     'conditional_energy_replicates':energy_cases,'conditional_energy_summaries':nominal,
                     'conditional_energy_difference_of_available_case_medians':nominal_delta,
                     'conditional_energy_block_pairs':nominal_pairs,
                     'paired_conditional_energy_differences':span([r['conditional_energy_split_minus_full'] for r in nominal_pairs]),
                     'historical_nominal_energy_split_minus_full':old_e_delta,
                     'historical_nominal_energy_aggregation':'median_of_three_historical_per_repeat_E_over_N_values; not the thesis mean aggregate',
                     'historical_thesis_energy_mean':thesis_energy_mean,'conditional_energy_mean':new_energy_mean,
                     'conditional_energy_effect_on_historical_point_direction':effect(thesis_energy_mean['split_minus_full_j_per_completion'],new_energy_mean['split_minus_full_j_per_completion']),
                     'conditional_energy_effect_aggregation':'historical_thesis_arithmetic_mean_vs_new_arithmetic_mean',
                     'conditional_energy_effect_on_historical_replicate_median_direction':effect(old_e_delta,nominal_delta),
                     'absolute_energy_comparison_status':'bestätigt' if len(pairs)==5 and all(r['energy_split_minus_full'] is not None for r in pairs) else 'nicht verfügbar',
                     'existing_direct_quality_interval':quality,'quality_recomputed_in_resume':False,
                     'scope':'Alle gültigen Einzelwerte der gebundenen R3-Auswahl. Richtung ist deskriptiv; bei fehlenden Blöcken keine Fünffachbestätigung oder Signifikanzbehauptung. Bedingte Energie ist keine absolute Energiequalifikation.'})
    return rows
