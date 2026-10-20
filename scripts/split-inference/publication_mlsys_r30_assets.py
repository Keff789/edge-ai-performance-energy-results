#!/usr/bin/env python3
"""Additional R30 publication views of already computed study results.

The payload and table functions use only the standard library. Rendering imports
Matplotlib lazily. No measurements, fitted weights, or rankings are recomputed
here. All returned file names are relative to the supplied publication root.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

from publication_mlsys_figures import MODEL_LABELS, PAPER_PALETTE, PAPER_STYLE


METHODS = [
    ('bytes', 'Bytes', 'green', '-', 'o'),
    ('generic', 'Generic', 'blue', '-', 's'),
    ('weighted_default', 'Weighted (default)', 'yellow', '--', '^'),
    ('weighted_pooled', 'Weighted (fit on all models)', 'dark_gray', '-.', 'v'),
    ('weighted_cv', 'Weighted (model held-out)', 'purple', '-', 'D'),
]
WEIGHTED_CAPTION = (
    'Native throughput loss after testing up to k ranked cuts per model/device '
    'group. All 21 groups receive equal weight at every budget. A group with '
    'fewer than k candidates tests all its candidates. Weighted (default) uses '
    '(1, 3, 0.2). Weighted (fit on all models) is a pooled in-sample '
    'result. Weighted (model held-out) fits six models and evaluates the seventh '
    'on all three devices. Calibrated Generic is omitted because its frozen '
    'predictions cover classifiers only.'
)


def _write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False,
                               allow_nan=False) + '\n', encoding='utf-8')


def _write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(study_results, names):
    # Source names remain portable when the repository is moved.
    return {name: _sha(study_results / name) for name in names}


def _summary(study_results):
    summary = json.loads((study_results / 'summary.json').read_text(encoding='utf-8'))
    scope = summary['scope']
    assert scope['model_device_groups'] == 21
    assert scope['evaluated_quality_pairs'] == 187
    assert scope['classifier_pairs'] == 151 and scope['detector_pairs'] == 36
    assert len(scope['models']) == 7
    return summary


def _save_figure(fig, directory, stem):
    metadata = {
        'pdf': {'Creator': 'MLSys R30 offline renderer', 'Producer': 'Matplotlib',
                'CreationDate': None, 'ModDate': None},
        'svg': {'Creator': 'MLSys R30 offline renderer', 'Date': None},
        'png': {'Software': 'Matplotlib'},
    }
    for extension in ['pdf', 'svg', 'png']:
        options = {'dpi': 300} if extension == 'png' else {}
        fig.savefig(directory / f'{stem}.{extension}', metadata=metadata[extension],
                    **options)


def _figure_asset(stem, label, caption, numeric_only, **metadata):
    extensions = ['json', 'csv'] + ([] if numeric_only else ['pdf', 'svg', 'png'])
    return {stem: dict(kind='figure', label=label, caption=caption,
                      files=[f'figures/{stem}.{ext}' for ext in extensions], **metadata)}


def render_yolo_single_column(output: Path, data: dict, numeric_only=False):
    """Render the approved three-row layout without changing the YOLO payload."""
    output = Path(output)
    directory = output / 'figures'
    directory.mkdir(parents=True, exist_ok=True)
    stem = 'yolov7_h8_case_single_column'
    points = data['points']
    assert [p['configuration'] for p in points] == ['Hailo8 Full', 'TensorRT Full', 'Split b066']
    _write_json(directory / f'{stem}.json', data)
    fields = list(dict.fromkeys(key for row in points for key in row))
    _write_csv(directory / f'{stem}.csv', points, fields)
    asset = _figure_asset(stem, 'fig:yolov7-case', data['caption'], numeric_only,
                          geometry_inches=[3.3, 3.6], source_figure='yolov7_h8_case',
                          data_changed=False, large_figure_changed=False)
    if numeric_only:
        return asset

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator

    panels = [
        ('throughput_fps', '(a) Throughput', 'FPS, higher is better',
         (0, 140), [0, 40, 80, 120], 0),
        ('system_energy_mj_per_image', '(b) System energy', 'mJ/image, lower is better',
         (0, 800), [0, 200, 400, 600], 2),
        ('coco_ap_50_95_percent', r'(c) COCO AP$_{50:95}$', '%, higher is better',
         (0, 60), [0, 20, 40], 2),
    ]
    with plt.rc_context(PAPER_STYLE):
        fig, axes = plt.subplots(3, 1, figsize=(3.3, 3.6))
        fig.subplots_adjust(left=.30, right=.965, bottom=.06, top=.85, hspace=1.10)
        colors = [PAPER_PALETTE[key] for key in ['gray', 'blue', 'green']]
        for ax, (field, title, unit, limits, ticks, precision) in zip(axes, panels):
            values = [point[field] for point in points]
            bars = ax.barh([0, 1, 2], values, height=.58, color=colors,
                           edgecolor='white', linewidth=.35, zorder=3)
            ax.set_xlim(limits)
            ax.set_ylim(2.5, -.5)
            ax.set_yticks([0, 1, 2], [point['configuration'] for point in points])
            ax.xaxis.set_major_locator(FixedLocator(ticks))
            ax.tick_params(axis='y', length=0, pad=4)
            ax.tick_params(axis='x', length=2.5, pad=2)
            ax.spines['left'].set_visible(False)
            ax.grid(axis='x', color='#dddddd', linewidth=.45, zorder=0)
            ax.text(-.415, 1.30, title, transform=ax.transAxes,
                    ha='left', va='bottom', fontsize=9, fontweight='bold')
            ax.text(-.415, 1.03, unit, transform=ax.transAxes,
                    ha='left', va='bottom', fontsize=8)
            for bar, value in zip(bars, values):
                quality_panel = field == 'coco_ap_50_95_percent'
                label_x = 59.5 if quality_panel else value + limits[1] * .022
                ax.text(label_x, bar.get_y() + bar.get_height() / 2,
                        f'{value:.{precision}f}', ha='right' if quality_panel else 'left',
                        va='center', fontsize=8.5)
            if field == 'coco_ap_50_95_percent':
                ax.axvline(data['quality_threshold_percent'], color='#333333',
                           linewidth=.75, linestyle=(0, (3, 2)), zorder=4)
        _save_figure(fig, directory, stem)
        plt.close(fig)
    return asset


def render_weighted(output: Path, study_results: Path, numeric_only=False):
    """Render five current seven-model curves; optimized means pooled in-sample."""
    output, study_results = Path(output), Path(study_results)
    directory = output / 'figures'
    directory.mkdir(parents=True, exist_ok=True)
    stem = 'rq2_weighted_all_models'
    summary = _summary(study_results)
    with (study_results / 'aggregate_curves.csv').open(encoding='utf-8', newline='') as stream:
        raw = list(csv.DictReader(stream))
    series = {}
    rows = []
    for method, label, *_ in METHODS:
        selected = sorted((row for row in raw if row['method'] == method),
                          key=lambda row: int(row['k']))
        assert [int(row['k']) for row in selected] == list(range(1, 21)), method
        assert all(int(row['groups']) == 21 for row in selected), method
        points = [{'k': int(row['k']), 'mean_loss_pct': float(row['mean_loss_pct'])}
                  for row in selected]
        assert all(math.isfinite(row['mean_loss_pct']) for row in points)
        series[method] = points
        rows.extend(dict(method=method, label=label, groups=21, **point) for point in points)
    payload = dict(
        schema='mlsys-r30-weighted-figure-v1', kind='measurement',
        scope=summary['scope'], caption=WEIGHTED_CAPTION, series=series,
        method_labels={method: label for method, label, *_ in METHODS},
        default_weights=summary['default_weights'],
        optimized_weights=summary['pooled_fit']['selected']['weights'],
        optimized_status=summary['pooled_fit_status'], held_out_status=summary['cv_status'],
        budget_protocol=summary['budget_protocol'],
        operation_feature_contract=summary['operation_feature_contract'],
        source_sha256=_sources(study_results, ['aggregate_curves.csv', 'summary.json']))
    _write_json(directory / f'{stem}.json', payload)
    _write_csv(directory / f'{stem}.csv', rows,
               ['method', 'label', 'groups', 'k', 'mean_loss_pct'])
    asset = _figure_asset(stem, 'fig:weighted-all-models', WEIGHTED_CAPTION, numeric_only,
                          geometry_inches=[3.6, 2.95], source_sha256=payload['source_sha256'],
                          optimized_status=summary['pooled_fit_status'],
                          held_out_status=summary['cv_status'])
    if numeric_only:
        return asset

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    with plt.rc_context(PAPER_STYLE):
        fig, ax = plt.subplots(figsize=(3.6, 2.95))
        for method, label, color, line, marker in METHODS:
            points = series[method]
            ax.plot([point['k'] for point in points],
                    [point['mean_loss_pct'] for point in points],
                    label=label, color=PAPER_PALETTE[color], ls=line, lw=1.3,
                    marker=marker, ms=2.6, markevery=[0, 2, 4, 7, 10, 14, 19])
        ax.set_xlim(.8, 20.3)
        ax.set_ylim(bottom=-.25)
        ax.set_xticks([1, 3, 5, 10, 15, 20])
        ax.set_xlabel('Maximum Native trials per group')
        ax.set_ylabel('Mean Native throughput loss (%)')
        ax.set_title('All seven models · 21 model/device groups', fontsize=8.5, pad=7)
        ax.grid(axis='y', color='#dddddd', linewidth=.45)
        ax.legend(loc='upper right', frameon=False, handlelength=2.2,
                  labelspacing=.30, fontsize=7.1)
        fig.subplots_adjust(left=.15, right=.985, bottom=.16, top=.91)
        _save_figure(fig, directory, stem)
        plt.close(fig)
    return asset


def write_weighted_tables(output: Path, study_results: Path):
    """Write compact TeX tables plus unrounded JSON/CSV and selected macros."""
    output, study_results = Path(output), Path(study_results)
    directory = output / 'tables'
    directory.mkdir(parents=True, exist_ok=True)
    summary = _summary(study_results)
    sources = _sources(study_results, ['summary.json', 'key_budget_results.csv', 'fold_weights.csv'])
    lookup = {(row['method'], row['k']): row for row in summary['key_budget_results']}
    budget_rows = []
    for method, label, *_ in METHODS:
        table_label = 'Weighted (joint fit)' if method == 'weighted_pooled' else label
        row = {'method': method, 'label': table_label, 'groups': 21}
        for k in [1, 3, 5]:
            point = lookup[(method, k)]
            assert point['groups'] == 21
            row[f'loss_k{k}_pct'] = point['mean_loss_pct']
        budget_rows.append(row)
    budget_stem = 'r30_weighted_budget_table'
    budget_caption = (
        r'Mean Native throughput loss (\%) over all 21 model/device groups. '
        r'The budget is $k$ trials per group, capped by the available cuts. '
        r'The pooled fit uses all seven models. Model-held-out '
        r'weights exclude the evaluated model on all three devices.')
    _write_json(directory / f'{budget_stem}.json', dict(
        rows=budget_rows, caption=budget_caption, source_sha256=sources,
        optimized_status=summary['pooled_fit_status'], held_out_status=summary['cv_status']))
    _write_csv(directory / f'{budget_stem}.csv', budget_rows,
               ['method', 'label', 'groups', 'loss_k1_pct', 'loss_k3_pct', 'loss_k5_pct'])
    lines = [r'\begin{table}[t]', r'\centering', r'\small',
             r'\setlength{\tabcolsep}{3pt}', r'\caption{' + budget_caption + '}',
             r'\label{tab:weighted-budget}',
             r'\begin{tabular}{@{}l*{3}{D{.}{.}{2}}@{}}', r'\toprule',
             r'Method & \multicolumn{1}{c}{$k=1$} & \multicolumn{1}{c}{$k=3$} & \multicolumn{1}{c}{$k=5$} \\', r'\midrule']
    for row in budget_rows:
        lines.append(row['label'] + ' & ' + ' & '.join(
            f"{row[f'loss_k{k}_pct']:.2f}" for k in [1, 3, 5]) + r' \\')
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{table}', ''])
    (directory / f'{budget_stem}.tex').write_text('\n'.join(lines), encoding='utf-8')

    fold_stem = 'r30_weighted_fold_table'
    folds = summary['folds']
    assert len(folds) == 7 and {row['held_out_model'] for row in folds} == set(summary['scope']['models'])
    fold_rows = [dict(held_out_model=row['held_out_model'],
                      model_label=MODEL_LABELS[row['held_out_model']],
                      w_comm=row['w_comm'], w_imb=row['w_imb'], w_tensors=row['w_tensors'],
                      train_groups=row['train_groups'], test_groups=row['test_groups'])
                 for row in folds]
    assert all(row['train_groups'] == 18 and row['test_groups'] == 3 for row in fold_rows)
    fold_caption = (
        r'Weights fitted with one complete model held out. Each fit uses the '
        r'other six models on all three devices. The communication weight '
        r'fixes the scale. The tensor weight remains fixed because all measured '
        r'cuts have zero tensor penalty.')
    _write_json(directory / f'{fold_stem}.json', dict(rows=fold_rows, caption=fold_caption,
                                                     source_sha256=sources))
    _write_csv(directory / f'{fold_stem}.csv', fold_rows,
               ['held_out_model', 'model_label', 'w_comm', 'w_imb', 'w_tensors',
                'train_groups', 'test_groups'])
    lines = [r'\begin{table}[t]', r'\centering', r'\small',
             r'\caption{' + fold_caption + '}', r'\label{tab:weighted-folds}',
             r'\begin{tabular}{@{}lrD{.}{.}{6}D{.}{.}{1}@{}}',
             r'\toprule', r'Held-out model & {$w_{\rm comm}$} & \multicolumn{1}{c}{$w_{\rm imb}$} & \multicolumn{1}{c}{$w_{\rm ten}$} \\',
             r'\midrule']
    for row in fold_rows:
        lines.append(f"{row['model_label']} & {row['w_comm']:.0f} & {row['w_imb']:.6f} & "
                     f"{row['w_tensors']:.1f}" + r' \\')
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{table}', ''])
    (directory / f'{fold_stem}.tex').write_text('\n'.join(lines), encoding='utf-8')

    weights = summary['pooled_fit']['selected']['weights']
    macros = [
        '% Generated display values; JSON and CSV retain unrounded values.',
        r'\newcommand{\WeightedModelCount}{7}',
        r'\newcommand{\WeightedGroupCount}{21}',
        r'\newcommand{\WeightedCandidateCount}{187}',
        r'\newcommand{\WeightedOptimizedComm}{' + f"{weights['w_comm']:g}" + '}',
        r'\newcommand{\WeightedOptimizedImb}{' + f"{weights['w_imb']:.6f}" + '}',
        r'\newcommand{\WeightedTensorWeight}{' + f"{weights['w_tensors']:g}" + '}',
        '',
    ]
    (directory / 'r30_weighted_macros.tex').write_text('\n'.join(macros), encoding='utf-8')
    operations_stem = 'r30_weighted_operations_table'
    operations_caption = (
        r'Additional analytic operation rules. $L$ is the reduction-vector '
        r'length. TopK selects $K$ values from length $N$. Counts are per vector '
        r'except for elementwise Mod.')
    operations_rows = [
        dict(operation='Stable Softmax', rule='6L - 3', count_unit='per reduction vector'),
        dict(operation='ReduceMax', rule='2(L - 1)', count_unit='per reduction vector'),
        dict(operation='Integer Mod', rule='1', count_unit='per output element'),
        dict(operation='TopK reference', rule='3 * sum(N - j - 1, j=0,...,K-1)',
             count_unit='per vector'),
    ]
    _write_json(directory / f'{operations_stem}.json', dict(
        rows=operations_rows, caption=operations_caption,
        operation_feature_contract=summary['operation_feature_contract'],
        source_sha256={'summary.json': sources['summary.json']}))
    _write_csv(directory / f'{operations_stem}.csv', operations_rows,
               ['operation', 'rule', 'count_unit'])
    lines = [r'\begin{table}[t]', r'\centering', r'\small',
             r'\caption{' + operations_caption + '}', r'\label{tab:weighted-operations}',
             r'\begin{tabular}{@{}ll@{}}', r'\toprule',
             r'Operation & Count \\', r'\midrule',
             r'Stable Softmax & $6L-3$ \\',
             r'ReduceMax & $2(L-1)$ \\',
             r'Integer Mod & One per output element \\',
             r'TopK reference & $3\sum_{j=0}^{K-1}(N-j-1)$ \\',
             r'\bottomrule', r'\end{tabular}', r'\end{table}', '']
    (directory / f'{operations_stem}.tex').write_text('\n'.join(lines), encoding='utf-8')
    assets = {}
    for stem, label, caption in [
        (budget_stem, 'tab:weighted-budget', budget_caption),
        (fold_stem, 'tab:weighted-folds', fold_caption),
        (operations_stem, 'tab:weighted-operations', operations_caption),
    ]:
        assets[stem] = dict(kind='table', label=label, caption=caption,
                            files=[f'tables/{stem}.{ext}' for ext in ['tex', 'json', 'csv']],
                            source_sha256=sources)
    assets['r30_weighted_macros'] = dict(kind='macros',
                                        files=['tables/r30_weighted_macros.tex'],
                                        source_sha256={'summary.json': sources['summary.json']})
    return assets
