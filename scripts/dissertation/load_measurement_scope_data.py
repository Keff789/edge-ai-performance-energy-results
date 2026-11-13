#!/usr/bin/env python3
"""Load the measurement-coverage overview from existing repository CSVs.

Only inventory selection and physical-run counts are computed here. No signal,
energy, spectral, or statistical measurement result is recomputed. Multiple
sensor comparisons and numerical reanalyses do not create additional runs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


ENERGY = Path('results/energy-measurement')
SOURCES = {
    'rate_candidates': ENERGY / 'data/tim/final_direct/groups_all_candidates.csv',
    'window_policy': ENERGY / 'data/tim/final_direct/paper_window_policy.csv',
    'rate_summary': ENERGY / 'tables/tim/direct_rates.csv',
    'duration_summary': ENERGY / 'tables/tim/duration.csv',
    'duration_pairs': ENERGY / 'tables/tim/paired_all_durations.csv',
    'reference_inventory': ENERGY / 'data/tim/validation/multi_workload/workload_inventory.csv',
    'rate_control': ENERGY / 'data/tim/validation/controlled/complementary/data/combined_runs.csv',
    'pause_control': ENERGY / 'data/tim/pause/pause_runs.csv',
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer_column(frame, field):
    values = pd.to_numeric(frame[field], errors='raise')
    _require(values.notna().all() and values.mod(1).eq(0).all(),
             f'{field} must contain finite integers')
    frame[field] = values.astype('int64')


def _boolean_column(frame, field):
    values = frame[field].astype(str).str.lower()
    _require(values.isin(['true', 'false']).all(), f'Invalid Boolean column: {field}')
    return values.eq('true')


def load_coverage(repo_root):
    """Return (rate_grid, duration_grid, provenance) for render_coverage()."""
    root = Path(repo_root)
    frames = {}
    hashes = {}
    for key, relative in SOURCES.items():
        path = root / relative
        hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
        frames[key] = pd.read_csv(path, float_precision='round_trip')

    # direct_rates identifies the twelve published rate series and their exact
    # final-window policy. Candidate tables contain alternative windows, which
    # must not be added as if they were separate physical executions.
    summary = frames['rate_summary']
    _require(not summary.duplicated(['platform', 'slug']).any(),
             'Repeated rate-series identifiers')
    _require(not summary.duplicated(['series', 'window']).any(),
             'Repeated rate-series/window selections')
    selected_policy = summary.merge(
        frames['window_policy'][['series', 'paper_window']],
        on='series', how='left', validate='one_to_one')
    _require(selected_policy.window.eq(selected_policy.paper_window).all(),
             'direct_rates and paper_window_policy disagree')
    rate_rows = frames['rate_candidates'].merge(
        summary[['platform', 'slug', 'series', 'window']],
        on=['series', 'window'], how='inner', validate='many_to_one')
    rate_rows = rate_rows.loc[rate_rows.sensor.eq('pico')].copy()
    rate_rows = rate_rows.rename(columns={'axis_value': 'rate_sps', 'n': 'n_valid'})
    for field in ['rate_sps', 'n_valid', 'n_reported']:
        _integer_column(rate_rows, field)
    _require(not rate_rows.duplicated(['platform', 'slug', 'rate_sps']).any(),
             'Rate grid contains duplicate physical groups')
    _require(rate_rows.n_valid.ge(0).all() and
             rate_rows.n_valid.le(rate_rows.n_reported).all(),
             'Invalid valid/reported execution counts')
    for row in rate_rows.itertuples():
        run_ids = [] if pd.isna(row.run_ids) else str(row.run_ids).split(',')
        _require(len(run_ids) == len(set(run_ids)) == row.n_valid,
                 f'Rate group has inconsistent valid execution IDs: {row.series}/{row.rate_sps}')
    observed = rate_rows.groupby(['platform', 'slug']).agg(
        counted_rates=('rate_sps', 'size'), counted_runs=('n_valid', 'sum')).reset_index()
    check = summary.merge(observed, on=['platform', 'slug'],
                          how='left', validate='one_to_one')
    _require(check.rates.eq(check.counted_rates).all() and
             check.finite_runs.eq(check.counted_runs).all(),
             'Rate grid disagrees with published direct_rates counts')
    rate_grid = rate_rows[['platform', 'slug', 'rate_sps', 'n_valid']].sort_values(
        ['platform', 'slug', 'rate_sps']).reset_index(drop=True)

    # duration.csv already counts physical runs. Cross-check these counts by
    # collapsing the simultaneous sensor comparisons to their execution IDs.
    duration = frames['duration_summary'].copy()
    for field in ['requested_s', 'n']:
        _integer_column(duration, field)
    duration_keys = ['platform', 'slug', 'series', 'window', 'requested_s']
    _require(not duration.duplicated(duration_keys).any(),
             'Duration summary contains duplicate groups')
    pairs = frames['duration_pairs'].copy()
    _integer_column(pairs, 'requested_s')
    execution_keys = duration_keys + ['record_id']
    _require(pairs.record_id.notna().all(), 'Missing duration execution IDs')
    _require(not pairs.duplicated(execution_keys + ['sensor']).any(),
             'Repeated sensor comparison for a duration execution')
    physical = pairs[execution_keys].drop_duplicates()
    duration_counts = physical.groupby(duration_keys).size().rename('counted_runs').reset_index()
    check = duration.merge(duration_counts, on=duration_keys, how='outer',
                           validate='one_to_one', indicator=True)
    _require(check['_merge'].eq('both').all() and check.n.eq(check.counted_runs).all(),
             'Duration summary disagrees with unique physical execution counts')
    duration_grid = duration[['platform', 'slug', 'requested_s', 'n']].sort_values(
        ['platform', 'slug', 'requested_s']).reset_index(drop=True)

    reference = frames['reference_inventory']
    reference = reference.loc[_boolean_column(reference, 'include_in_paper') &
                              _boolean_column(reference, 'common_reference_ready')].copy()
    _require(not reference.duplicated('workload_id').any(),
             'Duplicate reference-inventory calculation')
    _integer_column(reference, 'common_rate_valid_pairs')
    reference_runs = int(reference.common_rate_valid_pairs.sum())
    control = frames['rate_control']
    _require(not control.duplicated(['session', 'index']).any(),
             'Duplicate controlled-rate execution')
    _require(control.TRT_queries.eq(250).all() and
             set(control.rate_Sps) == {2000, 5000000},
             'Controlled-rate protocol differs from the figure description')
    pauses = frames['pause_control']
    _require(not pauses.duplicated('index').any(), 'Duplicate pause execution')
    evaluated_pauses = pauses.loc[~_boolean_column(pauses, 'conditioning')]
    _require(set(evaluated_pauses.pause_s) == {20, 120},
             'Pause conditions differ from the figure description')

    metadata = {
        'source_inputs': hashes,
        'counting_unit': 'One physical benchmark execution with a valid final-window outcome.',
        'selection_rules': {
            'rate_grid': 'Series/window from direct_rates.csv, checked against paper_window_policy.csv; pico rows from groups_all_candidates.csv; n counts valid executions.',
            'duration_grid': 'n from duration.csv, independently checked against unique (platform, slug, series, window, requested_s, record_id) in paired_all_durations.csv.',
            'reference': 'Sum of common_rate_valid_pairs for include_in_paper and common_reference_ready rows in workload_inventory.csv; each instrument pair counts once.',
            'rate_control': 'Unique (session, index) rows in combined_runs.csv.',
            'pause_control': 'Rows in pause_runs.csv with conditioning=False.',
        },
        'counts': {
            'rate_groups': len(rate_grid),
            'rate_runs_valid': int(rate_grid.n_valid.sum()),
            'rate_runs_reported': int(rate_rows.n_reported.sum()),
            'duration_groups': len(duration_grid),
            'duration_runs': int(duration_grid.n.sum()),
            'duration_sensor_comparisons': len(pairs),
        },
        'supplementary_cohorts': {
            'reference_runs': reference_runs,
            'reference_instrument_traces': 2 * reference_runs,
            'controlled_rate_runs': len(control),
            'pause_runs_evaluated': len(evaluated_pauses),
            'pause_conditioning_runs_excluded': len(pauses) - len(evaluated_pauses),
        },
        'reference_by_calculation': reference[
            ['workload_id', 'common_rate_valid_pairs']].to_dict('records'),
        'overlap_policy': 'The 15 long-interval FP16 traces, 30 Hailo spectral traces, and 225 fixed-window reanalyses are subsets of the rate campaign and are not counted again. No overall total across campaigns is claimed.',
        'measurement_statistics_recomputed': False,
        'processing': 'Inventory filtering, execution-ID deduplication, integer count aggregation, and consistency checks only.',
    }
    return rate_grid, duration_grid, metadata
