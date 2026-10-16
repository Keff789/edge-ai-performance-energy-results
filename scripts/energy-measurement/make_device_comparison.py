#!/usr/bin/env python3
"""Plot the exact PARMA 300-s paired medians; retain spread in companion CSVs.

One chart, 21 markers, 105 distinct executions. No new measurements or fits.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter

import os
ROOT = Path(__file__).resolve().parents[2] / 'results/energy-measurement'
R = Path(os.environ['ENERGY_OUTPUT_ROOT']) / 'device-comparison'
R.mkdir(parents=True, exist_ok=True)
(R / 'generated').mkdir(exist_ok=True)
WORKLOADS = [
    ('gemm_fp32', 'GEMM-FP32'), ('gemm_fp16', 'GEMM-FP16'),
    ('gemm_int8', 'GEMM-INT8'), ('yolo_fp32', 'YOLO-FP32'),
    ('yolo_fp16', 'YOLO-FP16'), ('yolo_int8', 'YOLO-INT8'),
    ('random_pattern_yolo', 'Variable YOLO'),
]
SENSORS = [('firmware', 'u.RECS', 'o'), ('jetson', 'INA3221 telemetry', 's'),
           ('shelly', 'Shelly (scaled AC)', '^')]

def main() -> None:
    (R / 'figures').mkdir(exist_ok=True)
    (R / 'metadata').mkdir(exist_ok=True)
    source = pd.read_csv(ROOT / 'tables/measurement-comparison/parma_device_pair_spread.csv')
    expected = {(w, s) for w, _ in WORKLOADS for s, _, _ in SENSORS}
    if (len(source) != 21 or set(zip(source.slug, source.sensor)) != expected
            or source.duplicated(['slug', 'sensor']).any()
            or not source.n.eq(15).all() or not source.platform.eq('Jetson').all()
            or not np.isfinite(source.paired_median_pct).all()):
        raise ValueError('Expected exactly 21 unique Jetson groups with 15 pairs each.')
    rows = []
    for wi, (slug, workload) in enumerate(WORKLOADS):
        for si, (sensor, name, _) in enumerate(SENSORS):
            row = source[(source.slug == slug) & (source.sensor == sensor)].iloc[0]
            rows.append({'slug': slug, 'workload': workload, 'sensor': sensor,
                         'sensor_name': name, 'n': int(row.n),
                         'paired_median_pct': float(row.paired_median_pct),
                         'row_order': wi, 'sensor_order': si})
    data = pd.DataFrame(rows)
    data.to_csv(R / 'generated/device_pair_medians.csv', index=False)
    # An inverted y-axis places the six continuous workloads above variable YOLO.
    # The separation lies BETWEEN the groups, not below the last data row.
    fig, ax = plt.subplots(figsize=(6.6, 3.25))
    fig.subplots_adjust(left=.19, right=.985, bottom=.17, top=.865)
    ys = np.array([0, 1, 2, 3, 4, 5, 6.35])
    for si, (sensor, label, marker) in enumerate(SENSORS):
        sub = data[data.sensor == sensor].sort_values('row_order')
        ax.plot(sub.paired_median_pct, ys + (si - 1) * .19,
                linestyle='None', marker=marker, markersize=5.2, label=label)
    ax.axvline(0, linestyle='--', linewidth=.75)
    ax.axhline(5.65, linestyle=':', linewidth=.75)
    ax.set_yticks(ys, [name for _, name in WORKLOADS])
    ax.set_ylim(6.95, -.65)
    ax.set_xlim(-7, 3.7)
    ax.set_xticks([-6, -4, -2, 0, 2])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:+g}' if v else '0'))
    ax.set_xlabel('Median mean-power difference from PicoScope (%)', fontsize=9)
    ax.tick_params(axis='both', labelsize=8.5)
    ax.grid(axis='x', linewidth=.4, alpha=.2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.025), ncol=3,
              frameon=False, fontsize=8.3, columnspacing=1.2, handletextpad=.4)
    for ext in ('pdf', 'png', 'svg'):
        options = {'metadata': {'CreationDate': None, 'ModDate': None}} if ext == 'pdf' else {}
        if ext == 'png': options['dpi'] = 240
        fig.savefig(R / f'figures/device_pair_medians.{ext}', **options)
    plt.close(fig)
    report = {'status': 'PASS', 'version': '0.15.1', 'markers': len(data),
              'physical_executions': 105, 'pair_comparisons': 315,
              'statistic': 'median of 15 individual signed mean-power ratios minus one, in percent',
              'percentiles_plotted': False, 'percentiles_retained_in_source': True,
              'source': 'generated/parma_device_pair_spread.csv'}
    (R / 'metadata/DEVICE_FIGURE_QA.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
