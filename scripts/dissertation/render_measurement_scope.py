#!/usr/bin/env python3
"""Render the physical energy measurement campaign coverage, not reanalyses.

The renderer accepts audited counts. Rates are categorical matrix columns,
not a continuous axis. Sensor channels and numerical windows are not added.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.text import Text
import pandas as pd

INK = '#18354A'
MUTED = '#587084'
BLUE = '#2E73B6'
ORANGE = '#D18432'
GRID = '#DCE4E9'
SERIES = [
    ('Jetson', 'gemm_fp32', 'GEMM-FP32'),
    ('Jetson', 'gemm_fp16', 'GEMM-FP16'),
    ('Jetson', 'gemm_int8', 'GEMM-INT8'),
    ('Jetson', 'yolo_fp32', 'YOLO-FP32'),
    ('Jetson', 'yolo_fp16', 'YOLO-FP16'),
    ('Jetson', 'yolo_int8', 'YOLO-INT8'),
    ('Jetson', 'random_pattern_yolo', 'YOLO variabel'),
    ('Jetson', 'llm', 'Gemma3-12B'),
    ('Hailo', 'gemm', 'GEMM'),
    ('Hailo', 'yolo', 'YOLO'),
    ('Hailo', 'random_pattern_yolo', 'YOLO variabel'),
    ('Hailo', 'llm', 'Sprachmodell'),
]

STYLE = {
    'font.family': 'sans-serif', 'font.sans-serif': ['Nimbus Sans', 'DejaVu Sans'],
    'font.size': 11, 'text.color': INK, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
    'svg.hashsalt': 'energy-measurement-scope-v1', 'figure.facecolor': 'white',
    'savefig.facecolor': 'white',
}


def de_int(n):
    return f'{int(n):,}'.replace(',', '.')


def _matrix(fig, rect, frame, axis, count, rows, columns, rates=False):
    ax = fig.add_axes(rect)
    ax.set_xlim(-.5, len(columns) - .5)
    ys = [i + (.6 if platform == 'Hailo' else 0) for i, (platform, _, _) in enumerate(rows)]
    ax.set_ylim(ys[-1] + .6, -.6)
    ax.set_axis_off()
    lookup = {(str(r.platform), str(r.slug), int(getattr(r, axis))): int(getattr(r, count))
              for r in frame.itertuples()}
    y_trans = ax.get_yaxis_transform()
    for (platform, slug, label), y in zip(rows, ys):
        color = BLUE if platform == 'Jetson' else ORANGE
        ax.text(-.025, y, label, ha='right', va='center', transform=y_trans, fontsize=10.6)
        total = 0
        for x, col in enumerate(columns):
            n = lookup.get((platform, slug, col), 0)
            total += n
            face = color if n == 15 else '#FFFFFF'
            edge = 'white' if n == 15 else (color if n else GRID)
            ax.add_patch(Rectangle((x-.47, y-.39), .94, .78,
                                   facecolor=face, edgecolor=edge, linewidth=.4 if n == 15 else .8))
            if n and n != 15:
                ax.text(x, y, str(n), ha='center', va='center', color=color,
                        fontsize=7.6 if rates else 9.4, fontweight='bold')
            elif not n:
                ax.plot([x-.24,x+.24], [y+.20,y-.20], color=GRID, lw=.9)
        ax.text(1.025, y, de_int(total), ha='left', va='center',
                transform=y_trans, fontsize=10.4, color=MUTED)
    for platform in ['Jetson', 'Hailo']:
        indices = [i for i, row in enumerate(rows) if row[0] == platform]
        y0, y1 = ys[indices[0]], ys[indices[-1]]
        x = -.327
        color = BLUE if platform == 'Jetson' else ORANGE
        ax.plot([x,x], [y0-.35,y1+.35], transform=y_trans, color=color, lw=2, clip_on=False)
        ax.text(x-.025, (y0+y1)/2, platform, ha='center', va='center', rotation=90,
                transform=y_trans, color=color, fontsize=11.4, fontweight='bold')
    ax.text(1.025, -.94, 'Σ', ha='left', va='center', transform=y_trans,
            fontsize=11, color=MUTED)
    bottom = ys[-1] + .8
    if rates:
        for x, value in enumerate(columns):
            scaled = value if value < 1000 else (value/1000 if value < 1e6 else value/1e6)
            label = f'{scaled:g}'.replace('.', ',')
            ax.text(x, bottom, label, rotation=90, va='top', ha='center',
                    fontsize=9.2, clip_on=False)
        unit_y = bottom + 2.45
        for lo, hi, unit in [(0,5,'S/s'),(6,20,'kS/s'),(21,26,'MS/s')]:
            ax.plot([lo-.4,hi+.4], [unit_y-.22,unit_y-.22], color=GRID, lw=.8, clip_on=False)
            ax.text((lo+hi)/2, unit_y, unit, ha='center', va='top', fontsize=10.2)
    else:
        for x, value in enumerate(columns):
            ax.text(x, bottom, str(value), va='top', ha='center', fontsize=10.6, clip_on=False)
        ax.text((len(columns)-1)/2, bottom+1.08, 'Angeforderte Messdauer (s)',
                va='top', ha='center', fontsize=11, clip_on=False)
    return ax


def render_coverage(rate_grid_df, duration_df, output_dir, source_metadata=None):
    if not source_metadata or 'supplementary_cohorts' not in source_metadata:
        raise ValueError('Audited repository provenance is required')
    other = source_metadata['supplementary_cohorts']
    reference_runs = int(other['reference_runs'])
    control_runs = int(other['controlled_rate_runs'])
    pause_runs = int(other['pause_runs_evaluated'])
    if (reference_runs, control_runs, pause_runs) != (59, 12, 6):
        raise ValueError('Reference/control cohorts changed; review the fixed layout')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rates = sorted(map(int, rate_grid_df.rate_sps.unique()))
    durations = sorted(map(int, duration_df.requested_s.unique()))
    rtotal = int(rate_grid_df.n_valid.sum())
    dtotal = int(duration_df.n.sum())
    duration_rows = [row for row in SERIES if row[1] != 'llm']
    if rate_grid_df.duplicated(['platform','slug','rate_sps']).any():
        raise ValueError('Nonunique rate groups')
    if duration_df.duplicated(['platform','slug','requested_s']).any():
        raise ValueError('Nonunique duration groups')
    # A fixed-layout snapshot must be reviewed when its scientific cohort changes.
    assert len(rate_grid_df) == 323 and rtotal == 4842
    assert len(duration_df) == 100 and dtotal == 1472
    assert len(rates) == 27 and len(durations) == 10
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(5.5, 6.85))
        fig.text(.045,.975,'(a) Variation der Erfassungsrate',fontsize=11.5,weight='bold',va='top')
        fig.text(.956,.975,f'{de_int(rtotal)} Ausführungen',fontsize=11.5,weight='bold',va='top',ha='right')
        fig.text(.045,.943,'12 Berechnungsvarianten · 27 Raten · 323 gemessene Kombinationen',
                 fontsize=9.7,color=MUTED,va='top')
        _matrix(fig,[.291,.601,.624,.311],rate_grid_df,'rate_sps','n_valid',SERIES,rates,True)

        fig.text(.045,.487,'(b) Variation der Messdauer',fontsize=11.5,weight='bold',va='top')
        fig.text(.956,.487,f'{de_int(dtotal)} Ausführungen',fontsize=11.5,weight='bold',va='top',ha='right')
        fig.text(.045,.455,'10 Berechnungsvarianten · 10 Messdauern · 100 gemessene Kombinationen',
                 fontsize=9.7,color=MUTED,va='top')
        _matrix(fig,[.291,.166,.624,.259],duration_df,'requested_s','n',duration_rows,durations)

        fig.text(.045,.044,'Gefüllte Zelle: 15 Ausführungen · Zahl: geringere Anzahl · Σ: Summe',
                 fontsize=9.2,color=MUTED,va='top')

        # Extend the canvas for independently acquired reference/control cohorts.
        # Existing matrix geometry and physical type sizes remain unchanged.
        old_height, extra_height = 6.85, 1.15
        new_height = old_height + extra_height
        fig.set_size_inches(5.5, new_height)
        for ax in fig.axes:
            box = ax.get_position()
            ax.set_position([box.x0, (extra_height + box.y0*old_height)/new_height,
                             box.width, box.height*old_height/new_height])
        for text in list(fig.texts):
            x, y = text.get_position()
            text.set_position((x, (extra_height + y*old_height)/new_height))
        fig.add_artist(plt.Line2D([.045,.956],[.140,.140], transform=fig.transFigure,
                                 color=GRID, linewidth=.8))
        fig.text(.045,.126,'(c) Zusätzliche Ausführungen für Referenz und Kontrolle',
                 fontsize=11,weight='bold',va='top')
        for x, n, title, detail in [
            (.045,reference_runs,'Referenzmessungen','6 Varianten,\n2 Oszilloskope parallel'),
            (.370,control_runs,'Kontrolle der Erfassungsrate','250 Inferenzen,\nausbalancierte Abfolge'),
            (.720,pause_runs,'Einfluss der Pausen','20 oder 120 Sekunden\nPause'),
        ]:
            fig.text(x,.092,str(n),fontsize=18,weight='bold',va='top')
            fig.text(x,.055,title,fontsize=9,va='top')
            fig.text(x,.032,detail,fontsize=9.2,color=MUTED,va='top',linespacing=1.15)

        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for text in fig.findobj(match=Text):
            if text.get_visible() and text.get_text().strip():
                box = text.get_window_extent(renderer)
                if not fig.bbox.contains(box.x0,box.y0) or not fig.bbox.contains(box.x1,box.y1):
                    raise ValueError(f'Text outside canvas: {text.get_text()} {box.extents}')
        for ext in ['pdf','svg','png']:
            meta={'CreationDate':None,'ModDate':None} if ext=='pdf' else ({'Date':None} if ext=='svg' else {})
            fig.savefig(out/f'measurement_scope.{ext}',dpi=220,metadata=meta)
        plt.close(fig)
    payload = {
        'figure':'measurement_scope','language':'de',
        'scope':'Two principal acquisition campaigns and three separate reference/control cohorts. Not a complete count of all historical energy experiments.',
        'counting_unit':'One physical benchmark execution with a valid final-window outcome. Multiple sensors and numerical reanalyses are not added.',
        'counts':{'rate_runs':rtotal,'rate_groups':len(rate_grid_df),'duration_runs':dtotal,'duration_groups':len(duration_df),
                  'reference_runs':reference_runs,'controlled_rate_runs':control_runs,'pause_runs':pause_runs},
        'rate_groups':rate_grid_df[['platform','slug','rate_sps','n_valid']].to_dict('records'),
        'duration_groups':duration_df[['platform','slug','requested_s','n']].to_dict('records'),
        'sources':source_metadata or {},
        'display_label_sources': {'Jetson/llm': 'Gemma3-12B is identified in the dissertation excerpt supplied by the user. Repository CSVs label this series llm.'},
    }
    (out/'measurement_scope.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return payload


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2],
                        help='Repository root containing results/energy-measurement')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'output')
    args=parser.parse_args()
    from load_measurement_scope_data import load_coverage
    rate_grid, duration_grid, metadata = load_coverage(args.repository)
    result=render_coverage(rate_grid, duration_grid, args.output, metadata)
    print(json.dumps(result['counts']))
