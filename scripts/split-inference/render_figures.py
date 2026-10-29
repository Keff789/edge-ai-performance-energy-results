#!/usr/bin/env python3
"""Deterministic Matplotlib views of the one selected paper dataset.

No admission/accuracy/hash filters are applied here. A plot requiring two metrics
uses their observed intersection; every omission and plotted UID is recorded.
Run standalone with --output DIR after reproduce.py has written PAPER_DATASET.
"""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, ScalarFormatter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_paper_dataset import PARETO_DEFINITION

SETUPS = ['DeepX', 'H8', 'H10']
NAMES = {'mobilenet_v3_large': 'MobileNet V3 Large', 'regnet_x_1_6gf': 'RegNet X 1.6GF',
         'resnet50': 'ResNet-50', 'yolo11l': 'YOLO11l', 'yolo26m': 'YOLO26m',
         'yolo26s': 'YOLO26s', 'yolov7_paper': 'YOLOv7'}
SHORT = {'mobilenet_v3_large': 'MobileNet V3', 'regnet_x_1_6gf': 'RegNet X',
         'resnet50': 'ResNet-50', 'yolo11l': 'YOLO11l', 'yolo26m': 'YOLO26m',
         'yolo26s': 'YOLO26s', 'yolov7_paper': 'YOLOv7'}
COLORS = {'DeepX': '#247ba0', 'H8': '#da7c30', 'H10': '#679436',
          'native': '#247ba0', 'generic': '#da7c30'}
MARKERS = {'native': 'o', 'generic': '^', 'TRT Full': 'D', 'Vendor Full': 's'}


def read(path):
    return json.loads(path.read_text())


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def measured(row, metric):
    return finite(row.get(metric)) and row[metric] > 0


def label(row):
    if row['kind'] == 'split':
        return row['runner']
    return 'TRT Full' if 'tensorrt' in row['backend'] or row['backend'].endswith('_trt') else 'Vendor Full'


def quality_label(rows):
    metrics = {str(r.get('quality_metric') or '') for r in rows}
    if any(r.get('task') == 'detection' for r in rows) or any('map' in m.lower() for m in metrics):
        return 'COCO mAP@[.50:.95] (%)'
    return 'Top-1 accuracy (%)'


def group(rows, keys):
    result = collections.defaultdict(list)
    for r in rows:
        result[tuple(r[k] for k in keys)].append(r)
    return result


def annotate_tradeoff(ax, selected, points, renderer, fontsize=11):
    """Place text only, without moving any measured coordinate.

    A stable finite search penalizes overlapping labels and observed markers.
    Leader lines bind the labels to their exact observations; the selected text
    offsets are exported alongside their UIDs for inspection.
    """
    font = FontProperties(size=fontsize)
    px_per_pt = ax.figure.dpi / 72
    occupied = []
    plotted = [ax.transData.transform((r['fps'], r['energy_mj_per_image'])) for r in points]
    axes_box = ax.get_window_extent(renderer)
    annotations = []

    def overlap(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))

    for row, text in selected:
        x, y = ax.transData.transform((row['fps'], row['energy_mj_per_image']))
        width, height, descent = renderer.get_text_width_height_descent(text, font, False)
        height += descent + 4 * px_per_pt
        width += 4 * px_per_pt
        candidates = []
        for radius in [9, 18, 30, 44, 62, 82, 108]:
            for direction in [(1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0)]:
                dx, dy = direction[0] * radius, direction[1] * radius
                left = x + dx * px_per_pt - (width if dx < 0 else width / 2 if dx == 0 else 0)
                bottom = y + dy * px_per_pt - (height if dy < 0 else height / 2 if dy == 0 else 0)
                box = (left, bottom, left + width, bottom + height)
                inside = (axes_box.x0 + 3, axes_box.y0 + 3, axes_box.x1 - 3, axes_box.y1 - 3)
                outside = width * height - overlap(box, inside)
                labels = sum(overlap(box, other) for other in occupied)
                markers = sum(overlap(box, (xx - 5, yy - 5, xx + 5, yy + 5)) for xx, yy in plotted)
                score = outside * 10000 + labels * 1000 + markers * 100 + math.hypot(dx, dy)
                candidates.append((score, dx, dy, box))
        _, dx, dy, box = min(candidates, key=lambda candidate: candidate[:3])
        occupied.append(box)
        ax.annotate(text, (row['fps'], row['energy_mj_per_image']),
                    xytext=(dx, dy), textcoords='offset points', fontsize=fontsize,
                    ha='right' if dx < 0 else 'center' if dx == 0 else 'left',
                    va='top' if dy < 0 else 'center' if dy == 0 else 'bottom',
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .92, 'pad': 1.2},
                    arrowprops={'arrowstyle': '-', 'color': '#777777', 'linewidth': .55,
                                'shrinkA': 2, 'shrinkB': 5},
                    annotation_clip=False, zorder=8)
        annotations.append({'uid': row['uid'], 'model': row['model'], 'setup': row['setup'],
                            'label': text, 'text_offset_points': [dx, dy]})
    return annotations


def annotate_fastest_deployments(ax, points, reserved, renderer):
    """Deterministically move labels only; keep every ratio coordinate intact."""
    fontsize = 10
    font = FontProperties(size=fontsize)
    px_per_pt = ax.figure.dpi / 72
    occupied = [tuple(text.get_window_extent(renderer).extents) for text in reserved]
    plotted = [ax.transData.transform((point['x'], point['y'])) for point in points]
    axes_box = ax.get_window_extent(renderer)
    inside = (axes_box.x0 + 4, axes_box.y0 + 4, axes_box.x1 - 4, axes_box.y1 - 4)
    annotations = []

    def overlap(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))

    for point in points:
        text = point['label']
        x, y = ax.transData.transform((point['x'], point['y']))
        lines = text.split('\n')
        width = max(renderer.get_text_width_height_descent(line, font, False)[0]
                    for line in lines) + 6 * px_per_pt
        height = (fontsize * 1.2 * len(lines) + 4) * px_per_pt
        candidates = []
        for radius in [9, 18, 30, 44, 62, 82, 108]:
            for sx, sy in [(1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0)]:
                dx, dy = sx * radius, sy * radius
                left = x + dx * px_per_pt - (width if dx < 0 else width / 2 if dx == 0 else 0)
                bottom = y + dy * px_per_pt - (height if dy < 0 else height / 2 if dy == 0 else 0)
                box = (left, bottom, left + width, bottom + height)
                outside = width * height - overlap(box, inside)
                labels = sum(overlap(box, other) for other in occupied)
                markers = sum(overlap(box, (xx - 6, yy - 6, xx + 6, yy + 6)) for xx, yy in plotted)
                score = outside * 10000 + labels * 1000 + markers * 100 + math.hypot(dx, dy)
                candidates.append((score, dx, dy, box))
        _, dx, dy, box = min(candidates, key=lambda candidate: candidate[:3])
        occupied.append(box)
        ax.annotate(text, (point['x'], point['y']), xytext=(dx, dy),
                    textcoords='offset points', fontsize=fontsize,
                    ha='right' if dx < 0 else 'center' if dx == 0 else 'left',
                    va='top' if dy < 0 else 'center' if dy == 0 else 'bottom',
                    bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .94, 'pad': 1.3},
                    arrowprops={'arrowstyle': '-', 'color': '#777777', 'linewidth': .6,
                                'shrinkA': 2, 'shrinkB': 5}, zorder=8)
        annotations.append({'model': point['model'], 'split_uid': point['split_uid'],
                            'label': text, 'text_offset_points': [dx, dy]})
    return annotations


def render_fastest_deployments(output, save):
    """Render both comparisons from the already-selected, unrounded table rows."""
    source_table = 'tables/table3_fastest_deployments.json'
    selected = read(output / source_table)
    identity_keys = ['model', 'split_uid', 'split_setup', 'split_case', 'split_runner',
                     'global_full_uid', 'host_full_uid']

    def identities(row):
        return {key: row.get(key) for key in identity_keys}

    def split_label(row):
        if not row.get('split_uid'):
            return 'No eligible split'
        return f'{row["split_setup"]}/{row["split_case"]} · {row["split_runner"].title()}'

    def missing_reason(row, baseline, energy=False):
        reasons = [row.get('split_missing_reason'), row.get(baseline + '_full_missing_reason')]
        if energy:
            reasons += [row.get('split_energy_missing_reason'),
                        row.get(baseline + '_full_energy_missing_reason')]
        return '; '.join(str(reason) for reason in reasons if reason) or (
            'Missing or nonpositive finite energy for the selected Split or Full'
            if energy else 'Missing positive finite FPS for the selected Split or Full')

    fig, ax = plt.subplots(figsize=(9.8, max(4.8, .64 * len(selected) + 1.2)), layout='constrained')
    payload, omitted = [], []
    ratios = [row[key] for row in selected for key in ['R_global', 'R_host']
              if measured(row, key)]
    lo, hi = min(ratios + [1.0]), max(ratios + [1.0])
    span = max(hi - lo, .8)
    ax.set_xlim(max(0, lo - .15 * span), hi + .15 * span)
    for y, row in enumerate(selected):
        point = dict(identities(row), R_global=row.get('R_global'), R_host=row.get('R_host'),
                     y=y, row_label=SHORT.get(row['model'], row['model']) + '\n' + split_label(row),
                     global_plotted=measured(row, 'R_global'), host_plotted=measured(row, 'R_host'),
                     missing_values=[])
        if point['global_plotted'] and point['host_plotted']:
            ax.plot([point['R_global'], point['R_host']], [y, y], color='#aaaaaa', linewidth=1, zorder=1)
        for baseline, key, marker, color, dy, size in [
                ('global', 'R_global', 'o', COLORS['native'], 8, 44),
                ('host', 'R_host', 'D', COLORS['generic'], -9, 90)]:
            if point[baseline + '_plotted']:
                ax.scatter(point[key], y, marker=marker, s=size,
                           facecolor=color if baseline == 'global' else 'none',
                           edgecolor=color, linewidth=1.4, zorder=4 if baseline == 'global' else 3)
                ax.annotate(f'{point[key]:.2f}×', (point[key], y), xytext=(0, dy),
                            textcoords='offset points', ha='center',
                            va='bottom' if dy > 0 else 'top', fontsize=10, color=color)
            else:
                reason = missing_reason(row, baseline)
                point['missing_values'].append({'metric': key, 'reason': reason})
                omitted.append(dict(identities(row), baseline=baseline, coordinate=key, reason=reason))
                ax.text(.98, y + (-.21 if baseline == 'global' else .21),
                        ('Global' if baseline == 'global' else 'Same-host') + ' Full: missing',
                        transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8, color=color)
        payload.append(point)
    ax.set_yticks(range(len(payload)), [point['row_label'] for point in payload], fontsize=10)
    ax.set_ylim(len(payload) - .45, -.55)
    ax.axvline(1, color='#555555', linewidth=.9, linestyle='--', zorder=0)
    ax.set_xlabel('Selected split throughput / reference Full throughput', fontsize=11)
    ax.tick_params(axis='x', labelsize=10)
    ax.grid(axis='x', alpha=.15)
    ax.set_axisbelow(True)
    ax.set_title('Baseline effect for the fastest observed split\nSame selected split, different Full baselines', fontsize=12, pad=12)
    fig.legend(handles=[
        Line2D([], [], marker='o', color=COLORS['native'], linestyle='none', markersize=6,
               label='Global fastest Full'),
        Line2D([], [], marker='D', markerfacecolor='none', markeredgecolor=COLORS['generic'],
               color=COLORS['generic'], linestyle='none', markersize=8, label='Fastest Full on the split host')],
        loc='outside lower center', ncol=2, frameon=False, fontsize=10)
    save(fig, 'fastest_split_baseline_comparison',
         'Same selected split, different Full baselines: each row reuses the globally fastest observed split '
         'from table3_fastest_deployments, across Native and Generic runners. Blue circles divide its FPS by '
         'the globally fastest observed Full; open orange diamonds use the fastest Full on that split\'s physical host. '
         'Both markers remain at their exact ratio coordinates, including overlap. Labels show factors to two decimal places; '
         'table exports retain unrounded ratios and absolute FPS. The linear reference at one denotes equal throughput. '
         'Each connecting segment illustrates only the changed denominator, not time or a measured optimization step. '
         'Selection is retrospective over the observed candidate set; quality, timed endpoints and parallel execution '
         'can differ. Small differences are not significance tests. Missing candidates or baselines are recorded explicitly.',
         {'source_table': source_table, 'points': payload, 'omitted_points': omitted,
          'x_coordinate': 'split_fps / selected_full_fps', 'x_scale': 'linear', 'reference_x': 1.0}, main=True)

    points, omitted = [], []
    for row in selected:
        point = dict(identities(row), x=row.get('R_global'), y=row.get('energy_ratio_global'),
                     R_global=row.get('R_global'), energy_ratio_global=row.get('energy_ratio_global'),
                     label=SHORT.get(row['model'], row['model']) + '\n' + split_label(row))
        missing = []
        if not measured(row, 'R_global'):
            missing.append({'metric': 'R_global', 'reason': missing_reason(row, 'global')})
        if not measured(row, 'energy_ratio_global'):
            missing.append({'metric': 'energy_ratio_global', 'reason': missing_reason(row, 'global', energy=True)})
        if missing:
            omitted.append(dict(point, missing_values=missing))
        else:
            points.append(point)
    fig, ax = plt.subplots(figsize=(8.4, 5.6), layout='constrained')
    xs, ys = [point['x'] for point in points], [point['y'] for point in points]
    xlo, xhi = min(xs + [1.0]), max(xs + [1.0])
    ylo, yhi = min(ys + [1.0]), max(ys + [1.0])
    xspan, yspan = max(xhi - xlo, .6), max(yhi - ylo, .6)
    ax.set_xlim(max(0, min(.55, xlo - .12 * xspan)), max(1.65, xhi + .16 * xspan))
    ax.set_ylim(max(0, min(.35, ylo - .15 * yspan)), max(1.6, yhi + .16 * yspan))
    for point in points:
        ax.scatter(point['x'], point['y'], marker=MARKERS.get(point['split_runner'], 'o'),
                   s=64, facecolor=COLORS['native'], edgecolor='white', linewidth=.7, zorder=5)
    ax.axvline(1, color='#555555', linewidth=.9, linestyle='--')
    ax.axhline(1, color='#555555', linewidth=.9, linestyle='--')
    ax.set_xlabel('Throughput ratio: selected split / global fastest Full →', fontsize=11)
    ax.set_ylabel('Energy per image ratio: selected split / global fastest Full', fontsize=11)
    ax.tick_params(axis='both', labelsize=10)
    ax.grid(alpha=.12)
    ax.set_axisbelow(True)
    ax.set_title('Fastest observed deployments: throughput and energy\nBoth ratios use the same global Full configuration', fontsize=12, pad=12)
    reserved = []
    for x, y, text, ha, va in [
            (.02, .98, 'Slower\nmore energy', 'left', 'top'),
            (.98, .98, 'Faster\nmore energy', 'right', 'top'),
            (.02, .02, 'Slower\nless energy', 'left', 'bottom'),
            (.98, .02, 'Faster\nless energy', 'right', 'bottom')]:
        reserved.append(ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va,
                                color='#666666', fontsize=9,
                                bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .85, 'pad': 2}))
    if omitted:
        fig.text(.5, .005, f'{len(omitted)} selected model(s) lack a required ratio; see FIGURE_DATA.json.',
                 ha='center', fontsize=8)
    fig.canvas.draw()
    fig.set_layout_engine('none')
    annotations = annotate_fastest_deployments(ax, points, reserved, fig.canvas.get_renderer())
    save(fig, 'fastest_deployment_tradeoff',
         'One point per model compares the throughput-selected split with the throughput-selected global Full '
         'from table3_fastest_deployments. The horizontal coordinate is split FPS / Full FPS; the vertical '
         'coordinate is split J/image / Full J/image, always using exactly the same Full UID. '
         'Right of one is faster, below one uses less energy per completed image. Energy is calibrated host-inclusive '
         'mean per-repeat E/N; it never changes the FPS selection. Text alone is displaced for readability; measured '
         'coordinates are unchanged. Circles denote Native splits and triangles Generic splits; color carries no '
         'quality-pass meaning. This is a retrospective overview of fastest observed configurations, not the full '
         'Pareto front or a minimum-energy selection. Quality, timed endpoints and parallel execution differ; '
         'quadrants do not establish equal accuracy or a causally isolated efficiency gain. Small differences are '
         'not significance tests. Models missing a required ratio remain in the tables and omission records.',
         {'source_table': source_table, 'points': points, 'omitted_points': omitted,
          'x_coordinate': 'R_global', 'y_coordinate': 'energy_ratio_global',
          'reference_x': 1.0, 'reference_y': 1.0, 'annotations': annotations}, main=True)


def render_tradeoffs(output, save, rows, ids, models, figure_profile='paper', label_transform=None):
    # The same exported observations and flags drive every trade-off panel.
    pareto = read(output / 'tables' / 'PARETO_POINTS.json')
    assert {r['uid'] for r in pareto} == set(ids), 'Pareto table/dataset identities differ'
    for point in pareto:
        if point['included']:
            source = ids[point['uid']]
            assert point['fps'] == source['fps']
            assert point['energy_mj_per_image'] == source['energy_mj_per_image']
            assert point['quality_value'] == (source.get('quality_value') if finite(source.get('quality_value')) else None)
    tradeoff_setups = ['H8', 'H10', 'DeepX']
    for model in models:
        mr = [r for r in rows if r['model_id'] == model]
        model_points = [r for r in pareto if r['model'] == model]
        qv = [r['quality_percent'] for r in model_points if r['included'] and r['quality_percent'] is not None]
        norm = Normalize(min(qv) if qv else 0, max(qv) if qv and max(qv)>min(qv) else (min(qv)+1 if qv else 100))
        cmap = plt.get_cmap('viridis')
        # At 7-inch manuscript width, 11/12-point text remains 7.7/8.4 point.
        # These settings are local so the established quality views are intact.
        if figure_profile == 'dissertation':
            fig, axes = plt.subplots(len(tradeoff_setups), 1, figsize=(4.8, 5.8))
            fig.subplots_adjust(left=.13, right=.81, bottom=.15, top=.925, hspace=.66)
        else:
            fig, axes = plt.subplots(1, len(tradeoff_setups), figsize=(10.0, 5.5), layout='constrained')
        payload, front_groups, pending_annotations = [], [], []
        for ax, setup in zip(axes, tradeoff_setups):
            sr = [r for r in model_points if r['setup'] == setup]
            good = [r for r in sr if r['included']]
            front = [r for r in good if r['pareto_all']]
            coordinates = sorted({(r['fps'], r['energy_mj_per_image']) for r in front})
            if len(coordinates) >= 2:
                ax.plot([xy[0] for xy in coordinates], [xy[1] for xy in coordinates],
                        color='#444444', linewidth=.85, zorder=1)
            front_groups.append({'model': model, 'setup': setup,
                                 'front_uids': [r['uid'] for r in front],
                                 'front_coordinates': [{'fps': x, 'energy_mj_per_image': y} for x, y in coordinates],
                                 'n_observations': len(good), 'n_front_uids': len(front),
                                 'n_front_coordinates': len(coordinates), 'line_drawn': len(coordinates) >= 2})
            for r in good:
                q = r['quality_percent']
                size = 66 if r['kind'] != 'split' else 31
                ax.scatter(r['fps'], r['energy_mj_per_image'], marker=MARKERS[label(r)],
                           s=size,
                           facecolor=cmap(norm(q)) if q is not None else '#b5b5b5',
                           edgecolor='#222222', linewidth=.4, alpha=.9,
                           zorder=4 if r['kind'] != 'split' else 2)
                if r['pareto_all']:
                    ax.scatter(r['fps'], r['energy_mj_per_image'], marker=MARKERS[label(r)],
                               s=size + 60, facecolor='none', edgecolor='#111111', linewidth=1.1, zorder=6)
                source = ids[r['uid']]
                payload.append(dict(r, endpoint_notes=source.get('endpoint_notes', source.get('execution_notes', []))))
            selected_labels = [(r, 'TRT Full' if label(r) == 'TRT Full' else 'Vendor Full')
                               for r in good if r['kind'] != 'split']
            for runner in ['native', 'generic']:
                candidates = [r for r in good if r['kind'] == 'split' and r['runner'] == runner]
                if not candidates:
                    continue
                fastest = min(candidates, key=lambda r:(-r['fps'], r['uid']))
                lowest = min(candidates, key=lambda r:(r['energy_mj_per_image'], r['uid']))
                prefix = 'N' if runner == 'native' else 'G'
                if fastest['uid'] == lowest['uid']:
                    selected_labels.append((fastest, f'{prefix} F=E {fastest["case"]}'))
                else:
                    selected_labels.extend([(fastest, f'{prefix} F {fastest["case"]}'),
                                            (lowest, f'{prefix} E {lowest["case"]}')])
            if figure_profile == 'dissertation':
                ax.set_title(f'{setup}   n={len(good)} · front={len(front)}', fontsize=9, loc='left', pad=4)
            else:
                ax.set_title(f'{setup}\nn={len(good)} · front={len(front)}', fontsize=12)
            ax.tick_params(axis='both', labelsize=8.5 if figure_profile == 'dissertation' else 11)
            if good and min(r['fps'] for r in good)>0 and max(r['fps'] for r in good)/min(r['fps'] for r in good)>12:
                ax.set_xscale('log')
                ax.xaxis.set_major_formatter(ScalarFormatter())
                ax.set_xlabel('Log scale', fontsize=11)
            if good and min(r['energy_mj_per_image'] for r in good)>0 and max(r['energy_mj_per_image'] for r in good)/min(r['energy_mj_per_image'] for r in good)>12:
                ax.set_yscale('log')
                ax.yaxis.set_major_formatter(ScalarFormatter())
                ax.set_ylabel('Log scale', fontsize=11)
            else:
                ax.yaxis.set_major_locator(MaxNLocator(4))
            if ax.get_xscale() == 'linear':
                ax.xaxis.set_major_locator(MaxNLocator(4))
            ax.margins(x=.22, y=.22)
            ax.grid(alpha=.16, linewidth=.6)
            ax.set_axisbelow(True)
            if figure_profile == 'dissertation':
                ax.set_xlabel('Throughput (images/s)' + (' · log scale' if ax.get_xscale() == 'log' else ''), fontsize=9)
                ax.set_ylabel('Energy (mJ/image)' + ('\nlog scale' if ax.get_yscale() == 'log' else ''), fontsize=9)
            # Localized labels must be measured in their displayed language
            # before the bounded annotation-placement search.
            if label_transform is not None:
                selected_labels = [(row, label_transform(text)) for row, text in selected_labels]
            pending_annotations.append((ax, selected_labels, good))
        handles = [Line2D([], [], marker=MARKERS[k], color='none', markerfacecolor='#aaaaaa',
                          markeredgecolor='#222222', label=k.title() if k in ['native','generic'] else k,
                          markersize=6) for k in MARKERS]
        handles.append(Line2D([], [], marker='o', color='none', markerfacecolor='none',
                              markeredgecolor='#111111', markeredgewidth=1.1, markersize=9,
                              label='Empirical Pareto point'))
        if any(r['included'] and r['quality_percent'] is None for r in model_points):
            handles.append(Line2D([], [], marker='o', color='none', markerfacecolor='#b5b5b5',
                                  markeredgecolor='#222222', markersize=6, label='Quality missing'))
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        if figure_profile == 'dissertation':
            fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .005),
                       ncol=3, frameon=False, fontsize=9, columnspacing=1.2, handletextpad=.45)
            colorbar_x = .865 if label_transform is not None else .87
            colorbar = fig.colorbar(sm, cax=fig.add_axes([colorbar_x, .22, .027, .58]))
            colorbar.set_label(quality_label(mr), fontsize=9)
            colorbar.ax.tick_params(labelsize=8.5)
            fig.suptitle('F: fastest · E: lowest energy · N/G: Native/Generic', y=.985, fontsize=8.5)
        else:
            fig.legend(handles=handles, loc='outside lower center', ncol=3, frameon=False, fontsize=11)
            colorbar = fig.colorbar(sm, ax=axes, shrink=.82, pad=.018)
            colorbar.set_label(quality_label(mr), fontsize=12)
            colorbar.ax.tick_params(labelsize=11)
            axes[1].set_xlabel('Throughput (images/s) →' +
                               ('\nH10: log scale' if axes[1].get_xscale() == 'log' else ''), fontsize=12)
            fig.supylabel('Host-inclusive energy (mJ/image) ↓', fontsize=12)
            fig.suptitle(NAMES.get(model, model) + '\nF: fastest · E: lowest energy · N/G: Native/Generic', fontsize=13)
        colorbar.solids.set_rasterized(False)
        colorbar.solids.set_edgecolor('face')
        # Freeze the solved layout before selecting text offsets, so the offsets
        # remain identical across the vector and PNG backends.
        fig.canvas.draw()
        fig.set_layout_engine('none')
        annotations = []
        for ax, selected, good in pending_annotations:
            annotations.extend(annotate_tradeoff(ax, selected, good, fig.canvas.get_renderer(),
                                                 fontsize=8.5 if figure_profile == 'dissertation' else 11))
        cap = ('All ' + str(len(payload)) + ' observed deployments of ' + NAMES.get(model, model) +
               ', by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale '
               '(gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. '
               'Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. '
               'Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. '
               'Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. '
               'Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes.')
        if any(r.get('task') == 'detection' for r in mr):
            cap += (' Native detector oracles are outside timing; Generic records decoded NMS; '
                    'Fulls retain their recorded host-tail or normalization work.')
        save(fig, '04_tradeoff_' + model, cap,
             {'scope_uids': [r['uid'] for r in mr], 'points': payload,
              'omitted_uids': [r['uid'] for r in model_points if not r['included']],
              'omitted_points': [r for r in model_points if not r['included']],
              'pareto_front': dict(PARETO_DEFINITION, groups=front_groups),
              'quality_color_scale': {'metric': quality_label(mr), 'min_percent': norm.vmin, 'max_percent': norm.vmax,
                                      'shared_across_setups': True, 'missing_color': '#b5b5b5'},
              'annotations': annotations}, main=model == 'regnet_x_1_6gf')


def render(output):
    output = Path(output)
    dataset_path = output / 'data' / 'PAPER_DATASET.json'
    if not dataset_path.exists():
        dataset_path = output / 'tables' / 'PAPER_DATASET.json'
    rows = sorted(read(dataset_path), key=lambda r: r['uid'])
    ids = {r['uid']: r for r in rows}
    assert len(ids) == len(rows)
    models = sorted({r['model_id'] for r in rows})
    out = output / 'figures'
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'svg.hashsalt': 'paper_after_refresh16_20261013',
                         'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.titlesize': 10, 'axes.labelsize': 9,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'ps.fonttype': 42,
                         'savefig.facecolor': 'white'})
    figure_data = {}
    captions = {}
    index = []

    def save(fig, name, caption, data, main=False):
        fig.savefig(out / (name + '.svg'), metadata={'Date': None, 'Creator': 'Matplotlib'})
        fig.savefig(out / (name + '.pdf'), metadata={'CreationDate': None, 'ModDate': None,
                                                   'Creator': 'Matplotlib', 'Producer': 'Matplotlib'})
        fig.savefig(out / (name + '.png'), dpi=150, metadata={'Software': 'Matplotlib'})
        plt.close(fig)
        captions[name] = caption
        figure_data[name] = data
        index.append({'name': name, 'main_paper': main, 'formats': ['pdf', 'svg', 'png'],
                      'caption': caption})

    # The same six host/backend observations per model feed both Full views.
    full = [r for r in rows if r['kind'] != 'split']
    full_order = [(setup, backend) for setup in SETUPS for backend in ['TRT Full', 'Vendor Full']]
    for number, metric, axis, word in [
        ('01', 'fps', 'Throughput (images/s)', 'throughput'),
        ('02', 'energy_mj_per_image', 'Host-inclusive raw energy (mJ/image)', 'energy')]:
        fig, axes = plt.subplots(2, 4, figsize=(15, 7.6), layout='constrained')
        payload = []
        for ax, model in zip(axes.flat, models):
            available = [r for r in full if r['model_id'] == model]
            vals, labels, colors, errs = [], [], [], []
            for setup, backend in full_order:
                rr = [r for r in available if r['setup_id'] == setup and label(r) == backend]
                assert len(rr) <= 1, (model, setup, backend)
                r = rr[0] if rr else None
                nkey = 'performance_n' if metric == 'fps' else 'energy_n'
                n = r.get(nkey) if r else 0
                vals.append(r[metric] if r and measured(r, metric) else math.nan)
                labels.append(f'{setup} / {"TRT" if backend == "TRT Full" else setup}\n(n={n})')
                colors.append(COLORS[setup])
                if r and measured(r, metric):
                    item = {'uid': r['uid'], 'model': model, 'setup': setup, 'backend': backend,
                            'value': r[metric], 'n': n}
                    if metric == 'fps' and len(r.get('fps_samples', [])) > 1:
                        lo, hi = min(r['fps_samples']), max(r['fps_samples'])
                        errs.append((r[metric] - lo, hi - r[metric]))
                        item.update(repeat_min=lo, repeat_max=hi)
                    else:
                        errs.append((0, 0))
                    payload.append(item)
                else:
                    errs.append((0, 0))
            bars = ax.barh(range(len(vals)), vals, color=colors, alpha=.85, height=.66)
            for j, bar in enumerate(bars):
                if j % 2 == 0:
                    bar.set_hatch('///')
                    bar.set_edgecolor('white')
            if metric == 'fps':
                ax.errorbar(vals, range(len(vals)), xerr=np.array(errs).T, fmt='none',
                            ecolor='#333333', capsize=2, linewidth=.8)
            for j, v in enumerate(vals):
                if finite(v):
                    ax.text(v + errs[j][1], j, f' {v:.0f}' if metric == 'fps' else f' {v:.2f}',
                            ha='left', va='center', fontsize=7)
                else:
                    ax.text(0, j, 'missing', va='center', fontsize=7)
            ax.set_yticks(range(len(labels)), labels, fontsize=7.5)
            ax.invert_yaxis()
            ax.set_title(NAMES.get(model, model))
            ax.set_xlabel(axis)
            ax.margins(x=.25)
            ax.grid(axis='x', alpha=.15)
            ax.set_axisbelow(True)
        for ax in list(axes.flat)[len(models):]:
            ax.axis('off')
        axes.flat[-1].text(0, .9, 'Host labels: DeepX, H8, H10\nTRT is measured separately on each host.\n\nHatched bars: host-matched TRT Full\nSolid bars: accelerator Vendor Full\n\nn = actual metric repeat count',
                           transform=axes.flat[-1].transAxes, va='top', fontsize=10)
        fig.suptitle(f'All measured Full configurations: {word} (n={len(payload)}/{len(full)})')
        cap = (f'Full {word} for all {len(full)} selected model/backend/host identities; '
               f'{len(payload)} have this metric. Host-specific TRT values are separate. '
               'No quality, claim, sample-count or hash admission filter is applied. ')
        cap += ('Whiskers show the observed performance-repeat minimum and maximum, not a confidence interval; historical n=1 has no whisker.'
                if metric == 'fps' else 'Bars use mean of per-repeat calibrated raw E/N, including the host; n is the actual sensor-repeat count. This is mJ per completed image, not energy divided by FPS.')
        save(fig, f'{number}_full_{word}', cap, {'scope_uids': [r['uid'] for r in full],
             'metric': metric, 'points': payload}, main=True)

    # Pair identities only; no dependency on energy eligibility for throughput.
    ng_path = output / 'tables' / 'native_generic_pairs.json'
    if ng_path.exists():
        ng = read(ng_path)
    else:
        paired = group([r for r in rows if r['kind'] == 'split'], ['model_id', 'setup_id', 'case_id'])
        ng = []
        for (model, setup, case), rr in sorted(paired.items()):
            byrunner = {r['runner']: r for r in rr}
            if set(byrunner) >= {'native', 'generic'}:
                n, g = byrunner['native'], byrunner['generic']
                ng.append({'model': model, 'setup': setup, 'case': case,
                           'native_uid': n['uid'], 'generic_uid': g['uid'],
                           'fps_ratio': n['fps']/g['fps'] if measured(n, 'fps') and measured(g, 'fps') else None,
                           'energy_ratio': n['energy_mj_per_image']/g['energy_mj_per_image'] if measured(n, 'energy_mj_per_image') and measured(g, 'energy_mj_per_image') else None})
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4), layout='constrained')
    for ax, metric, xlabel in zip(axes, ['fps_ratio', 'energy_ratio'],
                                ['Native / Generic throughput (higher favors Native)',
                                 'Native / Generic J/image (lower favors Native)']):
        for setup in SETUPS:
            values = sorted(r[metric] for r in ng if r['setup'] == setup and finite(r.get(metric)))
            if values:
                ax.step(values, np.arange(1, len(values)+1)/len(values), where='post',
                        color=COLORS[setup], label=f'{setup}, n={len(values)}')
        ax.axvline(1, color='#555555', linewidth=.8)
        ax.set(xlabel=xlabel, ylabel='Cumulative fraction of split pairs', ylim=(0, 1.02))
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.legend(loc='lower right' if metric == 'fps_ratio' else 'upper left', fontsize=8)
        ax.grid(alpha=.15)
    fig.suptitle('Native versus Generic: point-pooled distributions')
    save(fig, '03a_native_generic_pooled',
         'Point-pooled empirical distributions of Native/Generic throughput and host-inclusive raw J/image ratios. Each split pair has one vote; models with more measured splits have more points here. The two axes use their own observed metric pairs. A ratio of one indicates equality.',
         {'pairs': ng, 'aggregation': 'point_pooled'}, main=True)

    # Each model/setup median contributes once before model aggregation.
    balanced = []
    groups = group(ng, ['model', 'setup'])
    for (model, setup), rr in sorted(groups.items()):
        item = {'model': model, 'setup': setup}
        for metric in ['fps_ratio', 'energy_ratio']:
            values = [r[metric] for r in rr if finite(r.get(metric))]
            item[metric] = statistics.median(values) if values else None
            item[metric + '_n'] = len(values)
        balanced.append(item)
    per_model = []
    for (model,), rr in sorted(group(balanced, ['model']).items()):
        item = {'model': model, 'setup': 'All'}
        for metric in ['fps_ratio', 'energy_ratio']:
            values = [r[metric] for r in rr if finite(r[metric])]
            item[metric] = statistics.mean(values) if values else None
            item[metric + '_n_setups'] = len(values)
        per_model.append(item)
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.2), layout='constrained')
    summary = []
    for ax, metric, title in zip(axes, ['fps_ratio', 'energy_ratio'],
                               ['Throughput: higher favors Native', 'J/image: lower favors Native']):
        for i, setup in enumerate(SETUPS + ['All']):
            rr = [r for r in balanced + per_model if r['setup'] == setup and finite(r[metric])]
            values = [r[metric] for r in rr]
            if values:
                center = statistics.mean(values)
                color = COLORS.get(setup, '#555555')
                ax.plot([i-.3, i+.3], [center, center], color=color, linewidth=3)
                for j, r in enumerate(rr):
                    dx = (j - (len(rr)-1)/2)*.065
                    ax.scatter(i+dx, r[metric], color=color, edgecolor='white', s=45, zorder=3)
                summary.append({'setup': setup, 'metric': metric, 'n_models': len(rr),
                                'mean_model_setup_medians': center})
                ax.annotate(f'{center:.3f}\n{len(rr)} models', (i, max(values)), xytext=(0, 10),
                            textcoords='offset points', ha='center', fontsize=8)
        ax.axhline(1, color='#555555', linewidth=.8)
        ax.set_xticks(range(len(SETUPS) + 1), SETUPS + ['All'])
        ax.set_title(title)
        ax.set_ylabel('Native / Generic ratio')
        ax.yaxis.set_major_locator(MaxNLocator(6))
        ax.margins(y=.35)
        ax.grid(axis='y', alpha=.15)
    fig.suptitle('Equal model weighting: model/setup medians, then arithmetic mean across models')
    save(fig, '03b_native_generic_equal_model',
         'One dot is the median ratio within a model/setup. Horizontal bars are arithmetic means of these model medians within each setup, so each observed model has equal weight. In All, each dot first averages the setup medians for one model, then the bar averages across models. Metric-specific pair counts and all model medians are in figures/FIGURE_DATA.json. This differs intentionally from the point-pooled distribution.',
         {'model_setup_medians': balanced, 'model_means_over_setups': per_model, 'setup_summaries': summary,
          'aggregation': 'median_within_model_setup_then_mean_setups_per_model_then_mean_models'}, main=True)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 8.4), layout='constrained')
    categories = [(model, setup) for model in models for setup in SETUPS if (model, setup) in groups]
    for ax, metric, title in zip(axes, ['fps_ratio', 'energy_ratio'], ['Throughput Native / Generic', 'J/image Native / Generic']):
        for y, key in enumerate(categories):
            rr = [r for r in groups[key] if finite(r.get(metric))]
            values = sorted(r[metric] for r in rr)
            if values:
                ax.scatter(values, np.linspace(y-.18, y+.18, len(values)), color=COLORS[key[1]], alpha=.6, s=12)
                ax.scatter(statistics.median(values), y, marker='|', color='black', s=100, zorder=4)
        ax.axvline(1, color='#555555', linewidth=.8)
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.set_yticks(range(len(categories)), [f'{SHORT.get(m,m)} / {s}' for m,s in categories], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel(title)
        ax.grid(axis='x', alpha=.15)
    fig.suptitle('All model/setup Native–Generic pairs; black tick = group median')
    save(fig, '03c_native_generic_model_setup',
         'All observed Native/Generic ratios by model/setup. Every dot is one paired split, spread vertically only for readability; the black tick marks the within-group median. No point is removed because of quality or old admission flags.',
         {'pairs': ng, 'model_setup_medians': balanced})

    render_tradeoffs(output, save, rows, ids, models)

    # Optima cover every runner and group; count candidates independently per axis.
    optima = []
    for (model, setup, runner), rr in sorted(group([r for r in rows if r['kind']=='split'], ['model_id','setup_id','runner']).items()):
        pr = [r for r in rr if measured(r,'fps')]
        er = [r for r in rr if measured(r,'energy_mj_per_image')]
        fast = min(pr,key=lambda r:(-r['fps'],r['uid'])) if pr else None
        low = min(er,key=lambda r:(r['energy_mj_per_image'],r['uid'])) if er else None
        optima.append({'model':model,'setup':setup,'runner':runner,'candidate_count':len(rr),
                       'performance_candidates':len(pr),'energy_candidates':len(er),
                       'fastest_uid':fast['uid'] if fast else None,'lowest_energy_uid':low['uid'] if low else None,
                       'same_optimum':fast['uid']==low['uid'] if fast and low else None,
                       'fastest_quality_value':fast.get('quality_value') if fast else None,
                       'lowest_quality_value':low.get('quality_value') if low else None,
                       'fps_ratio':fast['fps']/low['fps'] if fast and low and measured(low,'fps') else None,
                       'energy_ratio':fast['energy_mj_per_image']/low['energy_mj_per_image'] if fast and low and measured(fast,'energy_mj_per_image') else None})
    optima.sort(key=lambda r: (r['model'], SETUPS.index(r['setup']), r['runner']))
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 9), layout='constrained')
    for ax, runner in zip(axes, ['native','generic']):
        rr = [r for r in optima if r['runner']==runner]
        for y,r in enumerate(rr):
            if finite(r['fps_ratio']):
                ax.scatter(r['fps_ratio'],y-.11,marker='o',s=35,color=COLORS['native'])
            if finite(r['energy_ratio']):
                ax.scatter(r['energy_ratio'],y+.11,marker='s',s=32,color=COLORS['generic'])
            if finite(r['fps_ratio']) and finite(r['energy_ratio']):
                ax.plot([r['fps_ratio'],r['energy_ratio']],[y-.11,y+.11],color='#cccccc',zorder=0)
        ax.set_yticks(range(len(rr)),[f'{SHORT.get(r["model"],r["model"])} / {r["setup"]}  '
                                     f'n={r["performance_candidates"]}/{r["energy_candidates"]}' + ('  =' if r['same_optimum'] else '') for r in rr],fontsize=8)
        ax.invert_yaxis()
        ax.axvline(1,color='#555555',linewidth=.8)
        ratios = [r[k] for r in optima for k in ['fps_ratio', 'energy_ratio'] if finite(r[k])]
        if ratios and max(ratios)/min(ratios)>4:
            ax.set_xscale('log')
            ax.xaxis.set_major_formatter(ScalarFormatter())
        elif ratios:
            ax.set_xlim(.98, max(1.05, max(ratios)*1.035))
            ax.xaxis.set_major_locator(MaxNLocator(6, steps=[1, 2, 5, 10]))
        ax.set_title(runner.title())
        ax.set_xlabel('Fastest split / minimum-energy split')
        ax.grid(axis='x',alpha=.15)
        ax.margins(x=.2)
    fig.legend(handles=[Line2D([],[],marker='o',color=COLORS['native'],linestyle='none',label='Throughput ratio'),
                        Line2D([],[],marker='s',color=COLORS['generic'],linestyle='none',label='J/image ratio')],
               loc='outside lower center',ncol=2,frameon=False)
    fig.suptitle('Fastest versus minimum-energy split\nn = throughput/energy candidates; = marks the same selected point')
    save(fig,'05_fastest_vs_min_energy',
         'Fastest and minimum-energy splits selected independently within each model/setup/runner with stable UID tie-breaking. Blue circles compare throughput; orange squares compare host-inclusive J/image, always fastest divided by minimum-energy split. Labels show performance/energy candidate counts and an equals sign when one observed point realizes both optima. Groups with one candidate are visible and do not constitute independent evidence for a conflict. Quality values and selected identities are retained in FIGURE_DATA.json.',
         {'optima':optima},main=True)

    # Quality overview uses percentage-point differences, with tasks separated.
    fig, axes = plt.subplots(1,2,figsize=(13.4,7.8),layout='constrained')
    qp=[]
    for ax, task, metric_title in zip(axes,['classification','detection'],['Top-1 accuracy difference (percentage points)','COCO mAP@[.50:.95] difference (percentage points)']):
        cats=[(m,s) for m in models for s in SETUPS if any(r['model_id']==m and r['setup_id']==s and r.get('task')==task for r in rows)]
        for y,(model,setup) in enumerate(cats):
            rr=[r for r in rows if r['model_id']==model and r['setup_id']==setup and r.get('task')==task
                and finite(r.get('quality_value')) and finite(r.get('quality_reference_value'))]
            bytype=group(rr,['kind','runner'])
            for (_,runner), selected in sorted(bytype.items()):
                for j,r in enumerate(selected):
                    delta=100*(r['quality_value']-r['quality_reference_value'])
                    typ=label(r)
                    offset = (-.14 if runner=='native' else .14) + ((j/(len(selected)-1)-.5)*.12 if len(selected)>1 else 0)
                    ax.scatter(delta,y+offset,marker=MARKERS[typ],s=36 if r['kind']!='split' else 14,
                               facecolor=COLORS.get(runner,'#555555') if r['kind']=='split' else ('#222222' if typ=='TRT Full' else COLORS[setup]),
                               edgecolor='white',linewidth=.3,alpha=.75,zorder=4 if r['kind']!='split' else 2)
                    qp.append({'uid':r['uid'],'quality_metric':r.get('quality_metric'),
                               'quality_value':r['quality_value'],'reference_value':r['quality_reference_value'],
                               'difference_percentage_points':delta,'quality_n':r.get('quality_n')})
        ax.axvline(0,color='#555555',linewidth=.8)
        ax.set_yticks(range(len(cats)),[f'{SHORT.get(m,m)} / {s}' for m,s in cats],fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel(metric_title)
        ax.set_title(task.title()+' — candidate minus its reference')
        ax.grid(axis='x',alpha=.15)
        ax.margins(x=.1)
    fig.legend(handles=[Line2D([],[],marker='o',color=COLORS['native'],linestyle='none',label='Native split'),
                        Line2D([],[],marker='^',color=COLORS['generic'],linestyle='none',label='Generic split'),
                        Line2D([],[],marker='s',color='#679436',linestyle='none',label='Vendor Full (setup color)'),
                        Line2D([],[],marker='D',color='#222222',linestyle='none',label='TRT Full')],
               loc='outside lower center',ncol=4,frameon=False)
    fig.suptitle(f'Existing dataset quality: {len(qp)}/{len(rows)} numerical candidate/reference observations\nNegative values are retained; zero denotes each observation’s model reference')
    save(fig,'06_quality_reference_comparison',
         'Selected existing dataset quality minus the corresponding model reference, in percentage points. Top-1 and COCO mAP@[.50:.95] are kept on separate axes. All numerical Native/Generic split and Full evaluations are retained, including Hailo Full losses and split improvements. Values are reused evidence, not new quality measurements. Missing quality is not filled from output-PASS or a historical favorable assessment. References can have different evaluation scopes; sample counts and exact source fields remain in the dataset.',
         {'scope_uids':[r['uid'] for r in rows],'points':qp,
          'missing_numeric_quality_uids':[r['uid'] for r in rows if not (finite(r.get('quality_value')) and finite(r.get('quality_reference_value')))]},main=True)

    # Absolute quality views permit direct Split/Vendor/Reference inspection.
    for model in models:
        mr=[r for r in rows if r['model_id']==model]
        fig,axes=plt.subplots(1,3,figsize=(13.8,4.4),sharey=True,layout='constrained')
        payload=[]
        for ax,setup in zip(axes,SETUPS):
            sr=[r for r in mr if r['setup_id']==setup]
            cases=sorted({r['case_id'] for r in sr if r['kind']=='split'})
            xpos={case:j for j,case in enumerate(cases)}
            qn=0
            for r in sr:
                if not finite(r.get('quality_value')):
                    continue
                q=100*r['quality_value']; qn+=1
                payload.append({'uid':r['uid'],'quality_percent':q,
                                'reference_percent':100*r['quality_reference_value'] if finite(r.get('quality_reference_value')) else None,
                                'quality_n':r.get('quality_n'),'quality_metric':r.get('quality_metric')})
                if r['kind']=='split':
                    x=xpos[r['case_id']]+(-.08 if r['runner']=='native' else .08)
                    ax.scatter(x,q,marker=MARKERS[r['runner']],s=25,color=COLORS[r['runner']],alpha=.8)
                    if finite(r.get('quality_reference_value')):
                        ax.scatter(x,100*r['quality_reference_value'],marker='_',color='#555555',s=30,linewidth=.8,zorder=0)
                else:
                    is_trt=label(r)=='TRT Full'
                    ax.axhline(q,color='#555555' if is_trt else COLORS[setup],linestyle=':' if is_trt else '--',linewidth=1.2)
                    ax.text(.98,q,'TRT Full' if is_trt else setup+' Full',transform=ax.get_yaxis_transform(),
                            ha='right',va='bottom',fontsize=7,bbox={'facecolor':'white','edgecolor':'none','alpha':.7,'pad':.3})
            step=max(1,math.ceil(len(cases)/9))
            tickcases=cases[::step]
            ax.set_xticks([xpos[c] for c in tickcases],tickcases,rotation=45,ha='right',fontsize=7)
            ax.set(title=f'{setup}: quality {qn}/{len(sr)}',xlabel='Measured split ID')
            if ax is axes[0]:
                ax.set_ylabel(quality_label(sr))
            ax.grid(axis='y',alpha=.15)
            ax.margins(y=.22)
        fig.legend(handles=[Line2D([],[],marker='o',color=COLORS['native'],linestyle='none',label='Native split'),
                            Line2D([],[],marker='^',color=COLORS['generic'],linestyle='none',label='Generic split'),
                            Line2D([],[],marker='_',color='#555555',linestyle='none',label='Per-point reference'),
                            Line2D([],[],color='#555555',linestyle=':',label='TRT Full'),
                            Line2D([],[],color='#679436',linestyle='--',label='Vendor Full')],
                   loc='outside lower center',ncol=5,frameon=False)
        fig.suptitle(NAMES.get(model,model)+': selected existing dataset quality')
        save(fig,'06_quality_'+model,
             'Absolute selected dataset quality for '+NAMES.get(model,model)+'. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.',
             {'scope_uids':[r['uid'] for r in mr],'points':payload})

    render_fastest_deployments(output, save)

    write(out/'FIGURE_DATA.json',figure_data)
    write(out/'INDEX.json',index)
    text=['# Figure captions','', 'All figures are generated from PAPER_DATASET and its derived comparison tables. SVG/PDF are vector outputs; PNG files are previews. Broad observed selection; no quality/claim/hash gate.','']
    for item in index:
        text += ['## '+item['name'],'',captions[item['name']],'']
    (output/'CAPTIONS.md').write_text('\n'.join(text)+'\n')
    # Original paper-selection README omitted from generated artifacts.
    # (out/'README.md').write_text('# Figures\n\nMain-paper candidates: '+', '.join('`'+i['name']+'`' for i in index if i['main_paper'])+'.\n\nThe complete per-model trade-off and quality views, plus model/setup Native–Generic detail, are intended for the dissertation/supplement. Every figure has PDF, SVG and PNG formats. Captions are in `../CAPTIONS.md`; plotted values and identities are in `FIGURE_DATA.json`.\n')
    return index


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='Existing output directory containing PAPER_DATASET.json')
    args=parser.parse_args()
    render(args.output)
