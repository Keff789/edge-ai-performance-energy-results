"""Readable views of freshly computed historical MLSys review tables."""
from __future__ import annotations

import csv
import json
from pathlib import Path

MODEL = {
    'mobilenet_v3_large': 'MobileNet-V3-L', 'regnet_x_1_6gf': 'RegNet-X',
    'resnet50': 'ResNet-50', 'yolo11l': 'YOLO11l', 'yolo26m': 'YOLO26m',
    'yolo26s': 'YOLO26s', 'yolov7_paper': 'YOLOv7',
}


def read(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def cell(value):
    return str(value).replace('|', r'\|').replace('\n', ' ')


def write(path, title, note, headers, rows):
    text = ['# ' + title, '', note, '', '| ' + ' | '.join(headers) + ' |',
            '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    text += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    path.write_text('\n'.join(text) + '\n', encoding='utf-8')


def number(value, digits=2, scale=1):
    if value in ('', 'NA'):
        return 'NA'
    return f'{scale * float(value):.{digits}f}'


def build(output_analysis):
    """Read only freshly generated CSVs below this explicit output directory."""
    review = output_analysis / 'review_output'
    vendor = output_analysis / 'vendor_output'
    q = read(review / 'quality_tolerance.csv')
    write(review / 'quality_tolerance.md', 'Quality-tolerance sensitivity',
          '195 historical energy-available split cases, six models. The fastest Native Full '
          'is selected before filtering and held fixed at 1%, 2% and 5%; the local semantic '
          'requirement and both split/Full point estimates must pass. All 18 chosen Fulls pass '
          '1%. Archived labels are unchanged; this is not a confidence-bound decision.',
          ['Relative-loss tolerance', 'Eligible cases', 'Faster Native', 'Lower energy', 'Both'],
          [[number(r['relative_loss_tolerance'], 0, 100) + '%', r['eligible_cases'],
            r['faster_native'], r['lower_energy'], r['improve_both']] for r in q])
    groups = read(review / 'long_window_groups.csv')
    summary = json.loads((review / 'long_window_summary.json').read_text())
    write(review / 'long_window_groups.md', 'Short- and longer-window winners',
          f"{summary['eligible_cases']} eligible cases in {summary['groups']} groups; "
          f"{summary['same_winner_groups']}/18 winners agree. The longer rate is the mean of "
          'per-repeat N/T from the separate energy runs. This comparison of existing runs '
          'is not a controlled thermal or duration experiment.',
          ['Model', 'Setup', 'Candidates', 'Native winner', 'Energy-window winner', 'Same winner'],
          [[MODEL[r['model_id']], r['setup_id'], r['n'], r['native_best_case'],
            r['energy_window_best_case'], r['same_winner']] for r in groups])
    windows = read(review / 'long_window_highlights.csv')
    write(review / 'long_window_highlights.md', 'Longer-window classification examples',
          'The Full identity chosen using short Native performance remains fixed. Native '
          'and energy-window speedups use different measurement windows. FPS are rounded '
          'only for display; the CSV retains full precision.',
          ['Model / cut', 'Setup', 'Native split (FPS)', 'Energy-window split (FPS)',
           'Energy-window Full (FPS)', 'Native speedup', 'Energy-window speedup', 'Split window (s)'],
          [[MODEL[r['model_id']] + '/' + r['case_id'], r['setup_id'],
            number(r['split_native_fps'], 0), number(r['split_energy_window_fps'], 0),
            number(r['baseline_energy_window_fps'], 0), number(r['native_speedup']) + '×',
            number(r['energy_window_speedup']) + '×', number(r['split_duration_s_mean'])] for r in windows])
    quality = read(review / 'quality_highlights.csv')
    write(review / 'quality_highlights.md', 'Quality of headline configurations',
          'Historical archived quality uses paired 95% bootstrap intervals (5,000 examples, '
          '1,000 bootstrap replicates). Admission uses a 5% point-estimate loss threshold. '
          'The two later YOLOv7 headline implementations provide reported labels only; '
          'their numeric quality remains NA. Historical AP is not attached to them.',
          ['Model / setup / cut', 'Metric', 'CPU score (%)', 'Split score (%)', 'Difference (pp)',
           'Difference 95% interval (pp)', 'Relative loss (%)', 'Interval crosses 5%'],
          [[MODEL[r['model_id']] + '/' + r['setup_id'] + '/' + r['case_id'], r['metric'],
            number(r['cpu_reference_score'], 2, 100), number(r['candidate_score'], 2, 100),
            number(r['delta_pp']), '[' + number(r['delta_ci_low_pp']) + ', ' +
            number(r['delta_ci_high_pp']) + ']' if r['delta_ci_low_pp'] != 'NA' else 'NA',
            number(r['relative_loss'], 2, 100), r['ci_crosses_five_percent']] for r in quality])
    calibration = read(review / 'calibration_summary.csv')
    write(review / 'calibration_summary.md', 'Existing energy calibration',
          'Projection of the stored fit and quality gates; no new fit or acquisition. '
          'The zero intercept is fixed. Fit residuals, point spread and repeat variability '
          'do not constitute a complete propagated sensor/reference uncertainty budget. '
          'A shared multiplicative scale cancels within a setup, but nonlinear or '
          'load-dependent error need not cancel.',
          ['Setup', 'Energy cases', 'Rate (samples/s)', 'Scale factor', 'Max fit residual (%)',
           'Point spread (%)', 'Idle drift (W)', 'Stored gate pass', 'Warnings'],
          [[r['setup'], r['current_energy_cases'], r['sample_rate_sps'], number(r['scale_factor'], 6),
            number(r['max_fit_residual_pct']), number(r['point_spread_pct']),
            number(r['idle_drift_w'], 3), r['stored_quality_gate_pass'],
            r['stored_warning_reasons'] or 'None'] for r in calibration])
    coverage = read(vendor / 'vendor_coverage_quality.csv')
    write(vendor / 'vendor_coverage_quality.md', 'Historical vendor feasibility and quality',
          'The historical coverage contains 588 records, including Full/control rows. '
          'The 420 heterogeneous planned base splits are distinct from augmented Native '
          'cases. Native excludes suffixes with part2_input_count != 1. Quality records '
          'and runner completion are different populations. Seven duplicate TensorRT '
          'Full companions are excluded from the 42 unique Full quality records.',
          ['Setup', 'Base planned splits', 'Generic complete', 'Build failed', 'Policy excluded',
           'Native multi-input exclusions', 'Native base complete', 'Native added complete',
           'Split quality close / total', 'Full quality close / unique total'],
          [[r['setup'], r['base_planned_splits'], r['base_generic_completed'], r['base_build_failed'],
            r['base_policy_excluded'], r['native_runner_multi_input_exclusions'],
            r['native_base_completed'], r['native_added_completed'],
            r['quality_split_reference_close'] + ' / ' + r['quality_split_results'],
            r['full_reference_close'] + ' / ' + r['unique_full_quality_results']] for r in coverage])
    for filename, title in [('quality_examples', 'Historical quality examples'),
                            ('full_quality_effects', 'Unique Full quality effects')]:
        rows = read(vendor / (filename + '.csv'))
        write(vendor / (filename + '.md'), title,
              'Archived dataset quality, not new inference. Scores use percent, differences '
              'percentage points, and relative loss percent. The intervals are archived '
              'paired 95% bootstrap intervals. Full TensorRT companions are counted only once.',
              ['Model', 'Setup / backend', 'Case', 'Metric', 'Candidate (%)', 'CPU (%)',
               'Difference (pp)', 'Difference interval (pp)', 'Relative loss (%)', 'Status'],
              [[MODEL[r['model_id']], r['setup_id'] + '/' + r['backend'], r['case_id'], r['metric'],
                number(r['candidate'], 2, 100), number(r['reference'], 2, 100), number(r['delta_pp']),
                '[' + number(r['delta_ci_low_pp']) + ', ' + number(r['delta_ci_high_pp']) + ']',
                number(r['relative_loss'], 2, 100), r['accuracy_class']] for r in rows])
    recovery = read(vendor / 'mobilenet_quality_recovery.csv')
    write(vendor / 'mobilenet_quality_recovery.md', 'MobileNet-V3-L quality recovery',
          'Top1 on the same 5,000 images. Split b027 uses the corresponding accelerator '
          'prefix and TensorRT suffix; this example does not imply general recovery for every cut.',
          ['Setup', 'CPU (%)', 'Accelerator Full (%)', 'Split b027 (%)', 'Recovered (pp)'],
          [[r['setup'], number(r['reference_pct']), number(r['full_pct']),
            number(r['split_pct']), number(r['recovered_pp'])] for r in recovery])
    inventory_root = output_analysis / 'runner_inventory'
    inventory = read(inventory_root / 'single_tensor_inventory.csv')
    write(inventory_root / 'single_tensor_inventory.md', 'Historical single-input suffix inventory',
          'Seven models contain 2,111 enumerated graph cuts and 183 cuts whose suffix has '
          'part2_input_count == 1. The one-crossing-tensor count is shown separately and '
          'does not establish suffix capability. Original graph descriptors are reused; '
          'node counts and topological positions come from the manuscript inventory. '
          'These cuts are a graph inventory, not all measured Native configurations.',
          ['Model', 'Nodes', 'Graph cuts', 'Single-input suffix', 'One crossing tensor',
           'Multi-input suffix', 'Single-input position range'],
          [[MODEL[r['model']], r['nodes'], r['enumerated_cuts'], r['single_input'],
            r['one_cut_tensor'], r['multi_input'],
            number(r['single_position_min'], 3) + '–' + number(r['single_position_max'], 3)]
           for r in inventory])
