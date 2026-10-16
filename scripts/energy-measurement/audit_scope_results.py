#!/usr/bin/env python3
"""Read-only independent audit of the returned scope CSV hierarchy.

This does not reread raw traces or validate the stored per-record inner Q95.
It recomputes the outer quantile and envelope with an explicit type-7 formula.
All percentages are percentage values; differences between them are pp.

Run with Python 3 from any working directory. Only the standard library is used.
Inputs are the shipped scope and sensitivity CSV exports. All audit outputs
are written to the required --output directory outside the repository.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
OUT = args.output.resolve()
REPO_ROOT = Path(__file__).resolve().parents[2]
ENERGY_ROOT = REPO_ROOT / 'results/energy-measurement'
if OUT == REPO_ROOT or REPO_ROOT in OUT.parents:
    raise SystemExit('Choose an output directory outside the repository.')
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ENERGY_ROOT / 'data/reconstruction/scopes'
ORIGINAL = ENERGY_ROOT / 'data/multi-workload/common_reference/common_reference_summary.csv'
RATES = [50, 85, 150, 240, 400, 680, 1200, 2000, 2500, 3300, 5500, 9400,
         16000, 25000, 45000, 80000, 100000, 125000, 160000]
DURATIONS = [.02, .05, .1, .2, .5, 1., 2., 5., 10.]
TOLERANCES = [.5, 1., 2., 5.]
WORKLOADS = ['gemma3-4b', 'gemmfp32', 'gemmint8', 'resnet50', 'yolofp32', 'yoloint8']
EXPECTED = {(w, s): list(range(9 if w == 'resnet50' else 10))
            for w in WORKLOADS for s in ['pico', 'tek']}


def read_csv(path):
    with path.open(encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def qlinear(values, probability=.95):
    values = sorted(float(x) for x in values)
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError('nonfinite/empty quantile input')
    index = (len(values) - 1) * probability
    low = math.floor(index)
    fraction = index - low
    if fraction == 0:
        return values[low]
    return values[low] + (values[low + 1] - values[low]) * fraction


def groupkey(row):
    return (row['workload'], row['source'], float(row['nominal_duration_s']),
            float(row['rate_sps']))


def ekey(row):
    return float(row['nominal_duration_s']), float(row['rate_sps'])


def persistent(curve, threshold):
    """Lowest eligible rate at which this and every higher tested rate passes."""
    minimum = None
    highest_failure = None
    for rate in sorted(curve, reverse=True):
        if curve[rate] > threshold:
            highest_failure = rate
            break
        minimum = rate
    first_pass = next((r for r in sorted(curve) if curve[r] <= threshold), None)
    return {'min_rate_sps': minimum, 'first_pointwise_pass_sps': first_pass,
            'highest_failing_rate_sps': highest_failure,
            'eligible_rate_count': len(curve)}


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


rows = read_csv(SOURCE / 'scope_per_run.csv')
groups_given = read_csv(SOURCE / 'scope_groups.csv')
envelope_given = read_csv(SOURCE / 'scope_envelope.csv')
summary = json.loads((SOURCE / 'summary.json').read_text(encoding='utf-8'))
original_rows = [r for r in read_csv(ORIGINAL) if r['mode'] == 'phase_only']

groups = defaultdict(list)
for row in rows:
    groups[groupkey(row)].append(row)
assert len(rows) == len({(*groupkey(r), int(r['run_id'])) for r in rows})
assert len(groups_given) == len({groupkey(r) for r in groups_given})
assert len(envelope_given) == len({ekey(r) for r in envelope_given})
assert {groupkey(r) for r in groups_given} == set(groups)

records = {(r['workload'], r['source'], int(r['run_id'])) for r in rows}
assert records == {(w, s, i) for (w, s), ids in EXPECTED.items() for i in ids}
all_combinations = {ekey(r) for r in rows}
missing_grid = sorted({(d, float(r)) for d in DURATIONS for r in RATES} - all_combinations)
assert all_combinations == {ekey(r) for r in envelope_given}
assert missing_grid == [(.02, 50.), (.02, 85.), (.05, 50.)]

recomputed_groups = {}
max_residual = defaultdict(float)
for row in groups_given:
    key = groupkey(row)
    per_run = groups[key]
    ids = sorted(int(r['run_id']) for r in per_run)
    assert ids == EXPECTED[key[:2]]
    assert json.loads(row['expected_ids']) == ids == json.loads(row['used_ids'])
    assert row['complete_requested_cohort'] == 'True'
    assert int(row['n_physical_records']) == len(ids)
    recalculated = {
        'native_hierarchical_Q95_pct': qlinear([r['native_Q95_pct'] for r in per_run]),
        'via_1M_hierarchical_Q95_pct': qlinear([r['via_1M_Q95_pct'] for r in per_run]),
        'native_max_record_Q95_pct': max(float(r['native_Q95_pct']) for r in per_run),
        'via_1M_max_record_Q95_pct': max(float(r['via_1M_Q95_pct']) for r in per_run),
        'max_abs_path_difference_pct': max(float(r['max_abs_path_difference_pct']) for r in per_run),
    }
    recalculated['native_minus_via_Q95_pp'] = (
        recalculated['native_hierarchical_Q95_pct'] - recalculated['via_1M_hierarchical_Q95_pct'])
    for name, value in recalculated.items():
        error = abs(value - float(row[name]))
        max_residual['group_' + name] = max(max_residual['group_' + name], error)
        assert error <= 1e-12, (key, name, error)
    for threshold, name in [(1., 'decision_changed_at_1pct'), (.5, 'decision_changed_at_0p5pct')]:
        changed = ((recalculated['native_hierarchical_Q95_pct'] <= threshold) !=
                   (recalculated['via_1M_hierarchical_Q95_pct'] <= threshold))
        assert str(changed) == row[name]
    recomputed_groups[key] = recalculated

original_groups = {}
original_envelope = defaultdict(list)
for row in original_rows:
    key = (row['workload_id'], row['source'], float(row['duration_s']), float(row['target_rate_sps']))
    assert int(row['physical_run_count']) == len(EXPECTED[key[:2]])
    original_groups[key] = float(row['hierarchical_abs_error_q95_pct'])
    original_envelope[key[2:]].append((float(row['hierarchical_abs_error_q95_pct']), *key[:2]))
assert len(original_groups) == len(original_rows)
assert set(recomputed_groups) - set(original_groups) == {(w, s, .02, 150.) for w, s in EXPECTED}
assert not set(original_groups) - set(recomputed_groups)
assert all(len(x) == 12 for x in original_envelope.values())

envelope = []
for given in envelope_given:
    key = ekey(given)
    relevant = {k: v for k, v in recomputed_groups.items() if k[2:] == key}
    assert len(relevant) == 12
    assert all(given[name] == 'True' for name in ['complete_requested_cohort', 'all_six_paper_workloads_and_ids'])
    assert int(given['n_workload_source_groups']) == 12
    native_key = max(relevant, key=lambda k: relevant[k]['native_hierarchical_Q95_pct'])
    via_key = max(relevant, key=lambda k: relevant[k]['via_1M_hierarchical_Q95_pct'])
    native = relevant[native_key]['native_hierarchical_Q95_pct']
    via = relevant[via_key]['via_1M_hierarchical_Q95_pct']
    for name, val in [('native_envelope_Q95_pct', native), ('via_1M_envelope_Q95_pct', via),
                      ('native_minus_via_Q95_pp', native - via)]:
        error = abs(val - float(given[name]))
        max_residual['envelope_' + name] = max(max_residual['envelope_' + name], error)
        assert error <= 1e-12
    old_tuple = max(original_envelope[key]) if key in original_envelope else (None, None, None)
    old = old_tuple[0]
    result = {
        'duration_s': key[0], 'rate_sps': key[1],
        'native_Q95_pct': native, 'via_1M_Q95_pct': via, 'original_phase_only_Q95_pct': old,
        'native_minus_via_pp': native - via,
        'via_minus_original_pp': via - old if old is not None else None,
        'native_minus_original_pp': native - old if old is not None else None,
        'native_dominant_workload': native_key[0], 'native_dominant_source': native_key[1],
        'via_dominant_workload': via_key[0], 'via_dominant_source': via_key[1],
        'original_dominant_workload': old_tuple[1], 'original_dominant_source': old_tuple[2],
    }
    for threshold in TOLERANCES:
        changed = (native <= threshold) != (via <= threshold)
        result[f'native_via_decision_change_{threshold:g}pct'] = changed
        result[f'via_original_decision_change_{threshold:g}pct'] = (
            (via <= threshold) != (old <= threshold)) if old is not None else None
    assert str(result['native_via_decision_change_1pct']) == given['decision_changed_at_1pct']
    assert str(result['native_via_decision_change_0.5pct']) == given['decision_changed_at_0p5pct']
    envelope.append(result)

summary_env = {(r['nominal_duration_s'], float(r['rate_sps'])): r for r in summary['scope_envelope']}
for row in envelope_given:
    other = summary_env[ekey(row)]
    for name in ['native_envelope_Q95_pct', 'via_1M_envelope_Q95_pct', 'native_minus_via_Q95_pp']:
        assert float(row[name]) == other[name]
assert summary['successful_records'] == len(records) == len(summary['active_record_files']) == 118
assert len(set(summary['active_record_files'])) == 118
assert summary['failed_records'] == 0 and not summary['limitations']
assert set(summary['active_record_files']) == {f'scope_{w}_{s}_{i}.json' for w, s, i in records}

for row in rows:
    assert all(math.isfinite(float(row[name])) for name in
               ['native_Q95_pct', 'via_1M_Q95_pct', 'native_max_pct', 'via_1M_max_pct', 'max_abs_path_difference_pct'])
    assert 0 <= float(row['native_Q95_pct']) <= float(row['native_max_pct'])
    assert 0 <= float(row['via_1M_Q95_pct']) <= float(row['via_1M_max_pct'])
    assert int(row['n_offsets_cases']) + int(row['ineligible_offset_cases']) == 64 * int(row['n_windows'])
    if ekey(row) == (.02, 150.):
        assert (int(row['n_windows']), int(row['n_offsets_cases']), int(row['ineligible_offset_cases'])) == (16, 1, 1023)
    elif ekey(row)[0] == 10.:
        assert (int(row['n_windows']), int(row['n_offsets_cases']), int(row['ineligible_offset_cases'])) == (1, 64, 0)
    else:
        assert (int(row['n_windows']), int(row['n_offsets_cases']), int(row['ineligible_offset_cases'])) == (16, 1024, 0)

minima = []
for duration in DURATIONS:
    relevant = [r for r in envelope if r['duration_s'] == duration]
    curves = {
        'native': {r['rate_sps']: r['native_Q95_pct'] for r in relevant},
        'via_1M': {r['rate_sps']: r['via_1M_Q95_pct'] for r in relevant},
        'original': {r['rate_sps']: r['original_phase_only_Q95_pct'] for r in relevant
                     if r['original_phase_only_Q95_pct'] is not None},
    }
    for threshold in TOLERANCES:
        result = {'duration_s': duration, 'tolerance_pct': threshold}
        for name, curve in curves.items():
            minimum = persistent(curve, threshold)
            for k, val in minimum.items():
                result[f'{name}_{k}'] = val
        result['native_vs_via_persistent_change'] = result['native_min_rate_sps'] != result['via_1M_min_rate_sps']
        result['via_vs_original_persistent_change'] = result['via_1M_min_rate_sps'] != result['original_min_rate_sps']
        minima.append(result)

duration_stats = []
for duration in DURATIONS:
    relevant = [r for r in groups_given if float(r['nominal_duration_s']) == duration]
    duration_stats.append({'nominal_duration_s': duration,
                           'min_actual_duration_s': min(float(r['min_actual_duration_s']) for r in relevant),
                           'max_actual_duration_s': max(float(r['max_actual_duration_s']) for r in relevant),
                           'windows_per_record': 1 if duration == 10 else 16})

point_switches = [r for r in envelope if r['native_via_decision_change_0.5pct'] or r['native_via_decision_change_1pct']]
assert len(point_switches) == 8
other_switches = [r for r in envelope if r['native_via_decision_change_2pct'] or r['native_via_decision_change_5pct']]
max_path_row = max(rows, key=lambda r: float(r['max_abs_path_difference_pct']))
max_reference_row = max(groups_given, key=lambda r: float(r['max_abs_reference_reduction_delta_pct']))
comparisons = [r for r in envelope if r['original_phase_only_Q95_pct'] is not None]
max_via_original = max(comparisons, key=lambda r: abs(r['via_minus_original_pp']))
original_group_differences = [
    {'workload': k[0], 'source': k[1], 'duration_s': k[2], 'rate_sps': k[3],
     'native_Q95_pct': recomputed_groups[k]['native_hierarchical_Q95_pct'],
     'via_1M_Q95_pct': recomputed_groups[k]['via_1M_hierarchical_Q95_pct'],
     'original_Q95_pct': old,
     'via_minus_original_pp': recomputed_groups[k]['via_1M_hierarchical_Q95_pct'] - old}
    for k, old in original_groups.items()]

audit = {
    'scope': 'Audit of supplied aggregates; no raw traces or per-offset JSON files were supplied in this upload.',
    'formula': 'Outer type-7 Q95 over one stored inner Q95 per physical record; max over all 12 workload/source groups; persistent fmin requires this and every higher eligible rate to pass.',
    'verification': {
        'physical_source_records': len(records), 'paired_records': len({(w, i) for w, s, i in records}),
        'per_run_rows': len(rows), 'workload_source_groups': len(EXPECTED),
        'aggregated_group_rows': len(groups_given), 'envelope_rows': len(envelope),
        'rates_sps': RATES, 'durations_s': DURATIONS, 'missing_nominal_grid_pairs': missing_grid,
        'expected_ids': {w: EXPECTED[(w, 'pico')] for w in WORKLOADS},
        'distinct_active_record_filenames': len(set(summary['active_record_files'])),
        'reaggregation_max_absolute_residuals_pp': dict(max_residual),
        'summary_matches_csv': True, 'all_numeric_rows_finite': True,
        'n_offset_cases_sum_per_path': sum(int(r['n_offsets_cases']) for r in rows),
        'n_ineligible_offset_cases_sum': sum(int(r['ineligible_offset_cases']) for r in rows),
        'duration_stats': duration_stats,
        'degenerate_minimum_sample_edge': {'duration_s': .02, 'rate_sps': 150,
            'valid_cases_per_record': 1, 'attempted_cases_per_record': 1024,
            'record_count': 118, 'original_export_contains_cell': False,
            'changes_any_persistent_minimum_at_tested_tolerances': False},
    },
    'persistent_minima': minima,
    'pointwise_envelope_changes_at_0p5_or_1pct': point_switches,
    'pointwise_envelope_changes_at_2_or_5pct': other_switches,
    'path_effects': {
        'max_abs_envelope_Q95_difference_pp': max(abs(r['native_minus_via_pp']) for r in envelope),
        'max_abs_sampled_energy_difference_pp': {**max_path_row, 'note': 'A stored per-record maximum, not independently recomputed from raw offset cases.'},
        'max_abs_reference_reduction_delta_pct': {**max_reference_row, 'note': 'Group field cannot be rederived from the supplied per-run CSV.'},
        'positive_native_minus_via_envelope_cells': sum(r['native_minus_via_pp'] > 0 for r in envelope),
        'negative_native_minus_via_envelope_cells': sum(r['native_minus_via_pp'] < 0 for r in envelope),
    },
    'original_comparison': {
        'mode': 'phase_only', 'matched_group_cells': len(original_groups), 'matched_envelope_cells': len(comparisons),
        'original_file': ORIGINAL.relative_to(REPO_ROOT).as_posix(),
        'maximum_absolute_via_original_envelope_difference': max_via_original,
        'median_absolute_via_original_envelope_difference_pp': qlinear([abs(r['via_minus_original_pp']) for r in comparisons], .5),
        'maximum_absolute_via_original_group_difference': max(original_group_differences, key=lambda r: abs(r['via_minus_original_pp'])),
        'fixed_2kSps_all_durations': [r for r in comparisons if r['rate_sps'] == 2000],
        'two_second_9p4kSps': next(r for r in comparisons if r['duration_s'] == 2 and r['rate_sps'] == 9400),
    },
    'limitations': [
        'The per-record inner Q95, phase grid, calibrated power samples, file provenance and filtering cannot be independently recomputed from these CSVs.',
        'All 118 records and every eligible group are present, but 150 S/s at 20 ms has only one valid case per record.',
        '10 s means 9.999999 s of common measured support, with one distinct window; exact actual durations are recorded above.',
        'Native-via effects are identified within this declared probe; original-via differences also include unmatched original numerical, window or offset conventions.',
        'Persistent minima describe only the eligible tested grid, not all continuous rates or phases.',
    ],
    'source_sha256': {p.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      [SOURCE / 'scope_per_run.csv', SOURCE / 'scope_groups.csv', SOURCE / 'scope_envelope.csv', SOURCE / 'summary.json', ORIGINAL]},
}

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'scope_independent_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
write_csv(OUT / 'scope_persistent_minima.csv', minima)
write_csv(OUT / 'scope_envelope_original_comparison.csv', envelope)

print(json.dumps(audit['verification'], ensure_ascii=False, indent=2))
print('\nPERSISTENT MINIMA: duration | tolerance | original | via1M | native')
for row in minima:
    print(row['duration_s'], row['tolerance_pct'], row['original_min_rate_sps'], row['via_1M_min_rate_sps'], row['native_min_rate_sps'])
print('\nPATH EFFECTS', json.dumps(audit['path_effects'], ensure_ascii=False))
print('\nORIGINAL MAX VIA DIFFERENCE', json.dumps(max_via_original, ensure_ascii=False))
print('\nOTHER POINTWISE SWITCHES', json.dumps(other_switches, ensure_ascii=False))
print('\nSAVED', OUT / 'scope_independent_audit.json', OUT / 'scope_persistent_minima.csv', OUT / 'scope_envelope_original_comparison.csv')
