#!/usr/bin/env python3
"""Regenerate the historical 13-run FP16 curves from bundled exported outcomes."""
from pathlib import Path
import csv
import json
import math
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY = 'historical-fp16-20260809'
INPUTS = REPO / 'results/energy-measurement/data' / STUDY
RUNS = set(range(2, 15))


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path, rows, columns):
    lines = ['| ' + ' | '.join(label for _, label in columns) + ' |',
             '|' + '|'.join('---' for _ in columns) + '|']
    for row in rows:
        values = []
        for key, _ in columns:
            value = row[key]
            values.append(f'{value:.6g}' if isinstance(value, float) else str(value))
        lines.append('| ' + ' | '.join(values) + ' |')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def validate_rows(rows, rate_key, extra_keys=()):
    seen = set()
    groups = {}
    for row in rows:
        run = int(row['run'])
        key = (run, int(row[rate_key]), *(row[k] for k in extra_keys))
        if key in seen:
            raise ValueError(f'Duplicate historical outcome: {key}')
        seen.add(key)
        group = (int(row[rate_key]), *(row[k] for k in extra_keys if k != 'phase_index'))
        groups.setdefault(group, set()).add(run)
    if not groups or any(runs != RUNS for runs in groups.values()):
        raise ValueError('Historical curves must retain exactly run IDs 2–14 per group.')


def reproduce(output):
    # Imports occur only on explicit execution, after the caller sets MPLCONFIGDIR.
    import numpy as np
    import historical_fp16_statistics as statistics
    import historical_fp16_plots as plotting

    out = output / STUDY
    out.mkdir(parents=True)
    metadata = json.loads((INPUTS / 'metadata.json').read_text())
    if metadata['primary_runs'] != sorted(RUNS):
        raise ValueError('Wrong historical cohort.')
    common = read_csv(INPUTS / 'common_trace_raw.csv')
    real = read_csv(INPUTS / 'real_measurements_raw.csv')
    variance = read_csv(INPUTS / 'variance_capture_per_run.csv')
    validate_rows(common, 'target_rate_sps', ('reconstruction_mode', 'phase_index'))
    validate_rows(real, 'directory_rate_sps')
    validate_rows(variance, 'target_rate_sps')
    if (len(common), len(real), len(variance)) != (16159, 351, 351):
        raise ValueError('Unexpected historical input counts.')
    for row in common:
        expected = (float(row['derived_energy_j']) / float(row['reference_energy_j']) - 1) * 100
        if not math.isclose(float(row['error_pct']), expected, abs_tol=5e-14):
            raise ValueError('Energy error inconsistent with retained energies.')
    reference = float(np.median([float(r['energy_j']) for r in real
                                if int(r['directory_rate_sps']) == 5000000]))
    for row in real:
        if float(row['reference_5msps_median_j']) != reference:
            raise ValueError('Independent acquisitions use a fixed 5-MS/s median reference.')
    tables = {
        'common_trace/common_trace_summary': statistics.summarise_common_trace(common),
        'real_measurements/real_measurements_summary': statistics.summarise_real_measurements(real),
        'psd/variance_capture_summary': statistics.summarise_variance(variance),
    }
    if [len(r) for r in tables.values()] != [49, 27, 27]:
        raise ValueError('Unexpected summary counts.')
    for name, rows in tables.items():
        write_csv(out / (name + '.csv'), rows)
    write_markdown(out / 'common_trace/common_trace_summary.md', tables['common_trace/common_trace_summary'], [
        ('reconstruction_mode', 'Reconstruction'), ('target_rate_sps', 'Rate (S/s)'),
        ('n_run_phase_cases', 'Run/phase cases'), ('error_median_pct', 'Median error (%)'),
        ('error_q05_pct', 'Q05 (%)'), ('error_q95_pct', 'Q95 (%)'),
        ('is_high_rate_anchor', 'Bandwidth-saturated anchor')])
    write_markdown(out / 'real_measurements/real_measurements_summary.md', tables['real_measurements/real_measurements_summary'], [
        ('directory_rate_sps', 'Rate (S/s)'), ('n_runs', 'Runs'), ('energy_median_j', 'Median energy (J)'),
        ('error_median_pct', 'Median error (%)'), ('error_q05_pct', 'Q05 (%)'), ('error_q95_pct', 'Q95 (%)')])
    write_markdown(out / 'psd/variance_capture_summary.md', tables['psd/variance_capture_summary'], [
        ('target_rate_sps', 'Rate (S/s)'), ('n_runs', 'Runs'), ('percent_median', 'Median coverage (%)'),
        ('percent_q05', 'Q05 (%)'), ('percent_q95', 'Q95 (%)')])

    with np.load(INPUTS / 'psd_plot_samples.npz', allow_pickle=False) as source:
        curves = {key: source[key] for key in source.files}
    f = curves['frequencies_hz']
    if len(f) != metadata['spectrum_points_retained'] or not np.all(np.diff(f) > 0):
        raise ValueError('Invalid frequency samples.')
    if int(curves['n_runs'][0]) != 13 or int(curves['analysis_rate_sps'][0]) != 1000000:
        raise ValueError('Unexpected PSD cohort or representation rate.')
    keys = [k for k in curves if curves[k].size == f.size]
    for key in keys:
        if not np.isfinite(curves[key]).all() or np.any(curves[key] < 0):
            raise ValueError(f'Invalid PSD values: {key}')
    for key in ('cumulative_median', 'cumulative_q10', 'cumulative_q90'):
        if np.any(np.diff(curves[key]) < -1e-15) or curves[key][-1] != 1:
            raise ValueError(f'Invalid cumulative curve: {key}')
    write_csv(out / 'psd/psd_plot_samples.csv',
              [dict(zip(keys, values)) for values in zip(*(curves[k] for k in keys))])
    psd = dict(metadata['psd'])
    psd['sensitivity_rates_sps'] = []  # No alternate-bandwidth spectra are included.
    cfg = SimpleNamespace(output_root=out, psd=SimpleNamespace(**psd))
    plotting.plot_energy_error(cfg)
    plotting.plot_psd(cfg)
    summary = {'cohort': 'historical primary runs 2–14', 'physical_reference_runs': 13,
               'common_trace_cases': len(common), 'common_trace_summary_rows': 49,
               'independent_acquisition_rows': len(real), 'variance_capture_rows': len(variance),
               'rate_groups': 27, 'spectrum_plot_bins': len(f),
               'median_cumulative_crossings_hz': {
                   str(q): plotting._frequency_at_fraction(f, curves['cumulative_median'], q)
                   for q in (.95, .99)},
               'figure_families': 6, 'formats': ['pdf', 'svg', 'png'],
               'spectral_reproduction': 'Previously aggregated spectral curves; no Welch or raw-signal rerun.'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS: historical FP16: 13 reference runs, 49 error and 27 coverage groups, six PDF/SVG/PNG families.')
