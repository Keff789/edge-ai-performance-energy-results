#!/usr/bin/env python3
"""Recompute v49 tables from small, hash-bound measurement and bootstrap inputs.

This is table reproduction, not a new hardware/trace/COCO validation. Large
runtime admission lists, predictions, model binaries and raw traces remain in
the referenced preservation archive. Original campaign paths are never opened.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculation_core as core


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def public_json(value):
    if isinstance(value, dict):
        for item in value.values():
            public_json(item)
    elif isinstance(value, list):
        for item in value:
            public_json(item)
    elif isinstance(value, str):
        core.require('/home/' not in value and not re.search(r'\b192\.168\.\d+\.\d+\b', value),
                     'private_machine_path_or_address_in_public_input')


class Inputs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.records = {}

    def path(self, relative):
        path = Path(relative)
        core.require(not path.is_absolute() and '..' not in path.parts, 'relative_input_path_required')
        path = (self.root / path).resolve()
        core.require(path.is_relative_to(self.root), 'input_path_escapes_package')
        return path

    def bytes(self, relative, expected=None):
        path = self.path(relative)
        core.require(path.stat().st_size <= 8_388_608, 'small_input_size_bound_exceeded')
        raw = path.read_bytes()
        sha = digest(raw)
        core.require(expected is None or expected == sha, 'input_hash_mismatch:' + str(relative))
        self.records[str(Path(relative))] = {'path': str(Path(relative)), 'sha256': sha, 'bytes': len(raw)}
        return raw

    def json(self, relative, expected=None):
        value = json.loads(self.bytes(relative, expected))
        public_json(value)
        return value

    def bound(self, binding):
        core.require(re.fullmatch('[0-9a-f]{64}', binding.get('sha256', '')), 'explicit_input_hash_required')
        return self.json(binding['path'], binding['sha256'])


def source_binding(value):
    """Adapt an archive member identity for unchanged aggregation functions."""
    core.require(isinstance(value, dict) and re.fullmatch('[0-9a-f]{64}', value.get('sha256', '')),
                 'measurement_source_hash_required')
    member = value.get('archive_member') or value.get('external_sha256_ref')
    core.require(isinstance(member, str) and member and not Path(member).is_absolute() and '..' not in Path(member).parts,
                 'archive_member_or_external_hash_reference_required')
    return {'path': member, 'sha256': value['sha256']}


def stats(values):
    return core.summary(values)


def validate_catalog(design):
    rows = design['uid_catalog']
    core.require(len(rows) == 14 and len({r['uid'] for r in rows}) == 14, 'fourteen_unique_UIDs_required')
    catalog = {row['uid']: row for row in rows}
    for row in rows:
        core.require(row['kind'] in {'split', 'full'} and row['model'] == row['uid'].split('|')[1], 'catalog_role_model_invalid')
        core.require(bool(row['host']) and bool(row['runtime_backend']), 'explicit_host_and_backend_required')
        if row['kind'] == 'full' and '|native_full_tensorrt|' in row['uid']:
            core.require('tensorrt' in str(row['runtime_backend']).lower(), 'host_accelerator_is_not_TensorRT_full_backend')
    for model in {r['model'] for r in rows}:
        core.require(sorted(r['kind'] for r in rows if r['model'] == model) == ['full', 'split'], 'one_selected_split_and_full_per_model_required')
        full = next(r['uid'] for r in rows if r['model'] == model and r['kind'] == 'full')
        core.require(all(r.get('full_reference_uid', full) == full for r in rows if r['model'] == model),
                     'explicit_full_reference_UID_changed')
    return catalog


def rate_row(fact, catalog, *, supplement=False):
    uid = fact['uid']
    core.require(uid in catalog and fact['setup_id'] == catalog[uid]['setup_id'], 'measurement_UID_setup_changed')
    n = fact['N_completed']
    core.require(type(n) is int and n > 0, 'positive_actual_N_required')
    start, stop = fact['interval_start_ns'], fact['interval_stop_ns']
    core.require(type(start) is int and type(stop) is int and 0 < start < stop, 'actual_native_interval_required')
    duration = fact['native_makespan_including_drain_s'] if supplement else (stop - start) / 1e9
    core.require(core.number(duration) and duration >= 60, 'measurement_plus_drain_duration_invalid')
    core.require(math.isclose(duration, (stop-start)/1e9, rel_tol=0, abs_tol=2e-9),
                 'own_float_and_rounded_native_interval_changed')
    core.require(fact['source_completion_verified'] is True, 'source_END_must_be_preserved')
    core.require(fact.get('A_valid') is True and fact.get('C_valid') is False,
                 'exported_primary_acceptance_and_C0_required')
    for binding in fact['provenance'].values():
        source_binding(binding)
    return {'run_id': fact['run_id'], 'execution_run_id': fact['execution_run_id'],
        'attempt_id': fact['attempt_id'], 'session_id': fact['session_id'], 'uid': uid,
        'model': catalog[uid]['model'], 'measurement_role': catalog[uid]['kind'],
        'host': catalog[uid]['host'], 'runtime_backend': catalog[uid]['runtime_backend'],
        'block': fact['block'], 'position': fact['position'], 'setup_id': fact['setup_id'],
        'completed': n, 'duration_s': duration, 'rate_per_s': n / duration,
        'pipeline_start_monotonic_ns': start, 'pipeline_end_monotonic_ns': stop,
        'duration_basis': 'own_native_float_makespan' if supplement else 'difference_of_rounded_native_monotonic_ns',
        'attempt_file': fact['provenance']['attempt']['archive_member'],
        'A_valid': True, 'B_valid': fact['B_valid'], 'C_valid': False,
        'conditional_energy_j': fact['conditional_energy_j'],
        'conditional_energy_j_per_completion': (fact['conditional_energy_j']/n if fact['conditional_energy_j'] is not None else None),
        'joules_per_completion': None, 'energy_same_interval_verified': False}


def energy_row(fact, rate):
    energy = fact['conditional_energy_j']
    if energy is None:
        return None
    core.require(core.number(energy) and energy > 0, 'positive_conditional_energy_required')
    core.require(fact['candidate_dropped_samples'] == 0 and fact['candidate_raw_counter_discontinuities'] == 0,
                 'energy_sample_gap_cannot_be_filled')
    core.require(fact.get('B_valid') is True and fact.get('target_sample_support_complete', True) is True,
                 'conditional_energy_acceptance_and_sample_support_required')
    return {'run_id': rate['run_id'], 'execution_run_id': rate['execution_run_id'],
        'attempt_id': rate['attempt_id'], 'uid': rate['uid'], 'block': rate['block'],
        **{key: rate[key] for key in ('model', 'measurement_role', 'host', 'runtime_backend', 'setup_id', 'session_id', 'position')},
        'completed': rate['completed'], 'duration_s': rate['duration_s'], 'rate_per_s': rate['rate_per_s'],
        'conditional_energy_j': energy, 'conditional_energy_j_per_completion': energy / rate['completed'],
        'conditional_alignment_envelope_j': fact.get('conditional_alignment_envelope_j'),
        'candidate_dropped_samples': 0, 'candidate_raw_counter_discontinuities': 0,
        'inner_interval_analysis_path': fact['provenance']['analysis']['archive_member'],
        'inner_interval_analysis_sha256': fact['provenance']['analysis']['sha256'],
        'valid_for_final_energy': False}


def block_pairs(rows, catalog, *, energy=False):
    result = []
    for model in sorted({r['model'] for r in catalog.values()}):
        for block in range(1, 6):
            pair = {catalog[row['uid']]['kind']: row for row in rows
                    if catalog[row['uid']]['model'] == model and row['block'] == block}
            if set(pair) != {'split', 'full'}:
                continue
            split, full = pair['split'], pair['full']
            base = {'model': model, 'block': block, 'split_run_id': split['run_id'], 'full_run_id': full['run_id']}
            for kind, row in (('split', split), ('full', full)):
                base.update({kind+'_'+key: row[key] for key in ('uid', 'execution_run_id', 'attempt_id', 'session_id',
                            'host', 'runtime_backend', 'setup_id', 'completed', 'duration_s')})
            base['cross_session'] = split['session_id'] != full['session_id']
            if energy:
                a, b = (row['conditional_energy_j_per_completion'] for row in (split, full))
                base.update(conditional_energy_split_minus_full=a-b, conditional_energy_split_over_full=a/b,
                            valid_for_final_energy=False)
            else:
                base.update(rate_split_minus_full=split['rate_per_s']-full['rate_per_s'],
                            rate_split_over_full=split['rate_per_s']/full['rate_per_s'],
                            energy_split_minus_full=None, energy_split_over_full=None)
            result.append(base)
    return result


def quality_tables(inputs, catalog):
    index = inputs.json('quality/index.json')
    core.require(index['schema'] == 'v49-confirmation-quality-inputs-v1' and len(index['models']) == 7,
                 'seven_paired_quality_inputs_required')
    all_rows, primary, direct = [], [], []
    core.require({item['model'] for item in index['models']} == {row['model'] for row in catalog.values()},
                 'quality_models_must_match_selected_seven')
    for item in index['models']:
        result = inputs.bound(item['result']); plan = inputs.bound(item['plan'])
        core.require(result['plan_sha256'] == item['plan'].get('origin_sha256', item['plan']['sha256']),
                     'original_quality_plan_binding_changed')
        raw = inputs.bytes(item['bootstrap']['path'], item['bootstrap']['sha256'])
        core.require(result['bootstrap_values_sha256'] == item['bootstrap'].get('origin_sha256', item['bootstrap']['sha256']),
                     'original_bootstrap_binding_changed')
        with np.load(io.BytesIO(raw), allow_pickle=False) as stored:
            values, delta = stored['values'], stored['delta']
        core.require(values.ndim == 3 and values.shape[:2] == (1000, 2) and np.isfinite(values).all(),
                     'one_thousand_finite_paired_metric_draws_required')
        core.require(np.array_equal(delta, values[:, 1, :] - values[:, 0, :]), 'paired_delta_must_use_same_draw')
        metrics = ['top1_accuracy'] if values.shape[2] == 1 else ['coco_ap_50_95', 'ap50', 'ap75']
        core.require(set(metrics) == set(result['components']) and values.shape[2] == len(metrics), 'quality_metric_axis_changed')
        core.require(result['B'] == 1000 and result['n_images'] == 5000 and len(set(plan['image_ids'])) == 5000
                     and len(plan['image_ids']) == 5000 and result['seed'] == plan['seed'], 'paired_quality_plan_identity_invalid')
        core.require(plan['frozen_before_first_metric_result'] is True and plan['seed_schema']['B'] == 1000
                     and plan['seed_schema']['n'] == 5000 and plan['seed_schema']['model'] == item['model'] == result['model'],
                     'frozen_quality_seed_schema_changed')
        core.require(result['exact_image_ids_paired'] and result['ground_truth_equal']
                     and result['cpu_relative_intervals_subtracted'] is False, 'direct_paired_quality_scope_changed')
        for kind in ('split', 'full'):
            core.require(catalog[result[kind+'_uid']]['kind'] == kind
                         and catalog[result[kind+'_uid']]['model'] == item['model']
                         and plan['seed_schema'][kind+'_uid'] == result[kind+'_uid'], 'quality_selected_pair_changed')
        bounds = np.percentile(delta, [2.5, 97.5], axis=0, method='linear')
        components = {}
        for j, metric in enumerate(metrics):
            point = result['components'][metric]
            full, split = point['full'], point['split']
            component = {'full': full, 'split': split, 'delta_split_minus_full': split-full,
                'percentile_95_low': float(bounds[0, j]), 'percentile_95_high': float(bounds[1, j]),
                'delta_percentage_points': 100*(split-full), 'low_percentage_points': 100*float(bounds[0, j]),
                'high_percentage_points': 100*float(bounds[1, j])}
            components[metric] = component
            row = dict(model=item['model'], split_uid=result['split_uid'], full_uid=result['full_uid'], metric=metric,
                **component, n_images=5000, B=1000, seed=result['seed'],
                scope='offline paired existing prediction analysis; saved metric draws, conditional on selected pairs')
            all_rows.append(row)
            if j == 0:
                primary.append(row)
        direct.append(dict(model=item['model'], split_uid=result['split_uid'], full_uid=result['full_uid'],
                           components=components, n_images=5000, B=1000, seed=result['seed'],
                           cpu_relative_intervals_subtracted=False))
    return all_rows, primary, direct


def build(measurements, history, design, quality):
    core.require(measurements['schema'] == 'v49-confirmation-measurement-inputs-v1', 'measurement_schema_invalid')
    catalog = validate_catalog(design)
    facts = measurements['primary']; supplements = measurements['supplements']
    core.require(len(facts) == 70 and len({row['run_id'] for row in facts}) == 70, 'seventy_unique_primary_slots_required')
    core.require(len(supplements) == 2 and {row['run_id'] for row in supplements} == {'b04_p09', 'b05_p09'},
                 'two_explicit_energy_supplements_required')
    rates = [rate_row(row, catalog) for row in facts]
    for uid in catalog:
        core.require(sorted(row['block'] for row in rates if row['uid'] == uid) == [1, 2, 3, 4, 5], 'five_primary_replicates_per_UID_required')
    energies = [energy_row(fact, rate) for fact, rate in zip(facts, rates)]
    energies = [row for row in energies if row is not None]
    core.require(len(energies) == 68, 'primary_68_energy_plus_two_null_required')
    pairs = block_pairs(rates, catalog); e_pairs = block_pairs(energies, catalog, energy=True)
    core.require(len(pairs) == 35 and len(e_pairs) == 33, 'primary_pair_counts_changed')
    hist_e, hist_p = [], []
    for row in history['energy']:
        n, duration, energy = row['N_completed'], row['duration_s'], row['energy_j']
        core.require(n > 0 and duration > 0 and energy > 0, 'historical_positive_N_t_E_required')
        hist_e.append(dict(row, rate_per_s=n/duration, reproduced_j_image=energy/n))
    for row in history['performance']:
        rate = row.get('reported_rate_per_s')
        if rate is None:
            rate = row['N_completed']/row['duration_s']
        hist_p.append(dict(row, rate_per_s=rate))
    core.require(len(hist_e) == len(hist_p) == 42, 'historical_42_energy_and42_performance_required')
    selection = history['selection']
    plan = {'runs': [{'run_id': row['run_id'], 'uid': row['uid'], 'block': row['block']} for row in facts]}
    meta = {'conditional_nominal_energy_replicates': energies, 'conditional_nominal_block_pairs': e_pairs}
    models = core.split_full_impacts(plan, {'accepted': rates, 'block_paired_comparisons': pairs},
                                    meta, selection, hist_e, quality)
    primary = {'A_rows': rates, 'B_rows': energies, 'A_pairs': pairs, 'B_pairs': e_pairs, 'models': models}
    attempts, chosen, targets = [], [], []
    own_supplement_rows = []
    original = {row['run_id']: row for row in facts}
    for fact in supplements:
        row = rate_row(fact, catalog, supplement=True); e = energy_row(fact, row)
        core.require(e is not None and fact['A_valid'] is True and fact['B_valid'] is True and fact['C_valid'] is False,
                     'supplement_requires_own_conditional_A_plus_B_and_C0')
        old = original[fact['run_id']]
        core.require(old['conditional_energy_j'] is None and old['uid'] == fact['uid'], 'supplement_must_not_replace_primary_A_or_existing_B')
        attempt = source_binding(fact['provenance']['attempt'])
        targets.append({key: fact[key] for key in ('uid', 'setup_id', 'block', 'position')} |
                       {'logical_run_id': fact['run_id'], 'original_primary_attempt': source_binding(old['provenance']['attempt'])})
        attempts.append({'logical_run_id': fact['run_id'], 'execution_run_id': fact['execution_run_id'],
            'uid': fact['uid'], 'setup_id': fact['setup_id'], 'block': fact['block'], 'position': fact['position'],
            'attempt_id': fact['attempt_id'], 'attempt_number': fact['attempt_number'], 'attempt': attempt,
            'collector_process_started': True, 'physical_source_GO_observed': True, 'runtime_process_started': True,
            'collector_process_identity': fact['collector_process_identity'],
            'physical_source_GO_identity': fact['physical_source_GO_identity_sha256'],
            'runtime_process_identity': fact['runtime_process_identity'],
            'assessment': {'A_valid': True, 'B_valid': True, 'C_valid': False,
                'own_measurement': {'N_completed': row['completed'], 'native_makespan_including_drain_s': row['duration_s'],
                    'rate_per_s': row['rate_per_s'], 'conditional_energy_j': e['conditional_energy_j'],
                    'conditional_energy_per_completed_j': e['conditional_energy_j_per_completion']},
                'source_completion': fact.get('source_completion'), 'observed_gates': fact.get('observed_gates'),
                'model_domain_observation': fact.get('model_domain_observation')}})
        chosen.append({'logical_run_id': fact['run_id'], 'attempt': attempt})
        own_supplement_rows.append(dict(row, conditional_energy_j=e['conditional_energy_j'],
            conditional_energy_j_per_completion=e['conditional_energy_j_per_completion'],
            original_primary_N=old['N_completed'], original_primary_B=None, primary_A_replaced=False))
    aggregate = core.aggregate(primary, targets, attempts, chosen)
    core.require(len(aggregate['coverage_energy_pairs']) == 35
                 and sum(row['contains_supplement'] for row in aggregate['coverage_energy_pairs']) == 2
                 and all(row['cross_session'] for row in aggregate['coverage_energy_pairs'] if row['contains_supplement']),
                 '33_primary_pairs_plus2_cross_session_supplement_pairs_required')
    uid_stats, historical_stats = [], []
    for uid, identity in sorted(catalog.items()):
        r = [row['rate_per_s'] for row in rates if row['uid'] == uid]
        e = [row['conditional_energy_j_per_completion'] for row in energies if row['uid'] == uid]
        entry = {key: identity[key] for key in ('uid', 'model', 'kind', 'setup_id', 'host', 'runtime_backend')}
        entry.update(rate=stats(r), primary_conditional_energy_per_completion=stats(e), C_valid=False)
        uid_stats.append(entry)
        historical_stats.append(dict(uid=uid, energy_per_completion=stats([row['reproduced_j_image'] for row in hist_e if row['uid'] == uid]),
            energy_window_rate=stats([row['rate_per_s'] for row in hist_e if row['uid'] == uid]),
            short_performance_rate=stats([row['rate_per_s'] for row in hist_p if row['uid'] == uid])))
    for item in aggregate['seven_model_impacts']:
        item['split_reference'] = catalog[item['split_uid']]
        item['full_reference'] = catalog[item['full_uid']]
        item['primary_A_rate_statistics'] = {kind: stats([row['rate_per_s'] for row in rates if row['uid'] == item[kind+'_uid']])
                                             for kind in ('split', 'full')}
        item['coverage_energy_median_split_minus_full'] = (item['coverage_energy_statistics']['split']['median']
                                                          - item['coverage_energy_statistics']['full']['median'])
        item['coverage_energy_median_split_over_full'] = (item['coverage_energy_statistics']['split']['median']
                                                         / item['coverage_energy_statistics']['full']['median'])
    return {'aggregate': aggregate, 'rates': rates, 'energies': energies, 'pairs': pairs, 'energy_pairs': e_pairs,
        'supplements': own_supplement_rows, 'uid_statistics': uid_stats,
        'historical_energy': hist_e, 'historical_performance': hist_p, 'historical_statistics': historical_stats,
        'catalog': catalog}


def flat(row):
    return {key: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if isinstance(value, (list, dict)) else value for key, value in row.items()}


def csv_text(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n'); writer.writeheader()
    writer.writerows(flat(row) for row in rows)
    return out.getvalue()


def history_tables(history):
    """Keep administrative placeholders separate from receipt-backed starts."""
    core.require(history['cohorts_pooled'] is False, 'historical_cohorts_must_remain_separate')
    groups = [('primary_R3_chain', history['primary_chain']), ('energy_supplement', history['supplements']),
              ('technical_source_diagnostics', history['technical_diagnostics'])]
    groups += [('excluded_'+name, rows) for name, rows in sorted(history['other_cohorts'].items())]
    rows, accounting = [], []
    for name, attempts in groups:
        starts, go, native = set(), set(), set()
        for attempt in attempts:
            for flag, field, observed in [('collector_process_started', 'collector_process_identity', starts),
                    ('physical_source_GO_observed', 'physical_source_GO_identity_sha256', go),
                    ('runtime_process_started', 'runtime_process_identity', native)]:
                if attempt.get(flag):
                    identity = attempt.get(field)
                    core.require(identity is not None, 'physical_start_receipt_identity_required')
                    key = core.canonical(identity)
                    core.require(key not in observed, 'duplicate_physical_start_in_exported_history')
                    observed.add(key)
            rows.append(dict(attempt, history_scope=name))
        accounting.append({'history_scope': name, 'administrative_records': len(attempts),
            'scientific': name != 'technical_source_diagnostics', 'collector_process_starts': len(starts),
            'physical_GO_starts': len(go), 'runtime_process_starts': len(native),
            'selected_primary_records': sum(row.get('selected_primary') is True for row in attempts),
            'contains_primary_selection': name == 'primary_R3_chain',
            'other_cohorts_pooled_into_primary': False})
    core.require(next(row for row in accounting if row['history_scope'] == 'primary_R3_chain')['collector_process_starts'] == 72,
                 'R3_scientific_start_history_changed')
    return rows, accounting


def metrology_tables(inputs):
    """Reproduce an optional, explicitly hash-bound CH0 evidence addendum.

    These are evidence and calibration-path rows, separate from every numeric
    measurement table. An older input package without the binding still works.
    """
    if not (inputs.root / 'metrology/index.json').is_file():
        return {}
    index = inputs.json('metrology/index.json')
    if 'ch0_joris_alignment' not in index:
        return {}
    core.require(index.get('schema') == 'v49-confirmation-metrology-inputs-v1', 'metrology_index_schema_invalid')
    binding = index['ch0_joris_alignment']
    core.require(isinstance(binding, dict), 'explicit_CH0_alignment_binding_required')
    alignment = inputs.bound(binding)
    core.require(alignment.get('schema') == 'thesis-v49-ch0-joris-evidence-alignment-v1', 'CH0_alignment_schema_invalid')
    claims = alignment.get('claim_matrix')
    paths = alignment.get('per_path_calibration_chain')
    core.require(isinstance(claims, list) and claims
                 and all(isinstance(row, dict) and row.get('status') in {'closed', 'partially_clarified', 'open'} for row in claims),
                 'CH0_claim_matrix_status_invalid')
    core.require(isinstance(paths, list) and paths and all(isinstance(row, dict) for row in paths),
                 'CH0_calibration_chain_rows_required')
    return {'metrology_claims': claims, 'metrology_conversion_paths': paths}


def generate(input_root, output_root):
    output_root = Path(output_root).resolve()
    core.require(not output_root.exists(), 'fresh_external_output_directory_required')
    inputs = Inputs(input_root)
    core.require(not output_root.is_relative_to(inputs.root), 'output_must_be_outside_immutable_inputs')
    origin = inputs.json('origin_provenance.json')
    for row in origin['outputs']:
        inputs.bytes(row['path'], row['sha256'])
    core.require({row['path'] for row in origin['outputs']} >= {'measurements.json', 'history_repeats.json', 'attempt_history.json'},
                 'three_exported_origin_files_must_be_hash_bound')
    if (inputs.root / 'manifest.json').is_file():
        manifest = inputs.json('manifest.json')
        for row in manifest['files']:
            inputs.bytes(row['path'], row['sha256'])
    measurements = inputs.json('measurements.json'); history = inputs.json('history_repeats.json')
    design = inputs.json('design.json'); attempt_history = inputs.json('attempt_history.json')
    q_all, q_primary, direct = quality_tables(inputs, validate_catalog(design))
    data = build(measurements, history, design, direct)
    h_rows, h_accounting = history_tables(attempt_history)
    a = data['aggregate']
    tables = {'primary_measurements': data['rates'], 'primary_uid_statistics': data['uid_statistics'],
        'primary_throughput_pairs': data['pairs'], 'primary_energy': data['energies'],
        'primary_energy_pairs': data['energy_pairs'], 'supplement_measurements': data['supplements'],
        'energy_coverage': a['logical_energy_coverage_records'], 'energy_pairs': a['coverage_energy_pairs'],
        'model_comparisons': a['seven_model_impacts'], 'direct_quality_intervals': q_all,
        'direct_quality_primary': q_primary, 'historical_energy_repeats': data['historical_energy'],
        'historical_performance_repeats': data['historical_performance'], 'historical_uid_statistics': data['historical_statistics'],
        'attempt_history': h_rows, 'attempt_accounting': h_accounting}
    tables.update(metrology_tables(inputs))
    rendered = {}
    for name, rows in tables.items():
        rendered[name+'.json'] = json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n'
        rendered[name+'.csv'] = csv_text(rows)
    coverage = dict(a['counts'], primary_throughput_pairs=len(data['pairs']), primary_energy_pairs=len(data['energy_pairs']),
        primary_cross_session_energy_pairs=sum(row['cross_session'] and not row['contains_supplement'] for row in a['coverage_energy_pairs']),
        all_cross_session_energy_pairs=sum(row['cross_session'] for row in a['coverage_energy_pairs']),
        strict_hardware_revalidation_performed=False, raw_waveform_reintegration_performed=False,
        prediction_metric_recomputation_performed=False)
    rendered['coverage.json'] = json.dumps(coverage, indent=2, sort_keys=True)+'\n'
    source = Path(__file__).with_name('calculation_origins.json')
    provenance = json.loads(source.read_text())
    core.require(digest(Path(core.__file__).read_bytes()) == provenance['generated_module_sha256'], 'reused_calculation_module_changed')
    report = {'schema': 'v49-portable-table-reproduction-v1', 'scope': __doc__,
        'inputs': sorted(inputs.records.values(), key=lambda row: row['path']),
        'calculations': provenance, 'python_dependency': 'Python >=3.10 standard library', 'numpy_version': np.__version__,
        'generator_sources': [{'path': path.name, 'sha256': digest(path.read_bytes())}
                              for path in (Path(__file__), Path(core.__file__), source)],
        'outputs': [{'path': name, 'sha256': digest(text.encode()), 'bytes': len(text.encode())} for name, text in sorted(rendered.items())],
        'counts': coverage, 'new_hardware_or_network_operations': 0}
    rendered['reproduction_manifest.json'] = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n'
    output_root.mkdir(parents=True, exist_ok=False)
    for name, text in rendered.items():
        with (output_root / name).open('x') as stream:
            stream.write(text)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = generate(args.inputs, args.output)
    print(json.dumps({'output': str(args.output), 'counts': result['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
