#!/usr/bin/env python3
"""Paper-size MLSys R22 views of shared, already computed offline results.

The payload/export functions use only the standard library. Matplotlib is
imported only by render(); numeric-only reproduction therefore emits the same
plot coordinates, identities, omissions and conceptual specification. Geometry
is adapted from the active R22 drawing scripts; their absolute paths, source
pins, implicit LaTeX calls and duplicate measurement joins are not retained.
"""
import csv
import json
import math
from pathlib import Path

MODEL_LABELS = {
    'mobilenet_v3_large': 'MobileNetV3-L', 'regnet_x_1_6gf': 'RegNet-X',
    'resnet50': 'ResNet-50', 'yolo11l': 'YOLO11l', 'yolo26m': 'YOLO26m',
    'yolo26s': 'YOLO26s', 'yolov7_paper': 'YOLOv7',
}
SETUPS = ['H8', 'H10', 'DeepX']
COLORS = {'H8': '#4477AA', 'H10': '#EE7733', 'DeepX': '#228833'}
MARKERS = {'H8': 'o', 'H10': 's', 'DeepX': '^'}
PAPER_STYLE = {
    'font.family': 'serif', 'font.serif': ['STIXGeneral'], 'mathtext.fontset': 'stix',
    'font.size': 8.5, 'axes.titlesize': 9, 'axes.labelsize': 8.5,
    'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 7.5,
    'axes.linewidth': .65, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': False, 'axes.axisbelow': True, 'pdf.fonttype': 42, 'ps.fonttype': 42,
    'pdf.use14corefonts': False, 'ps.useafm': False, 'svg.fonttype': 'none',
    'svg.hashsalt': 'mlsys-r22-publication-20261018', 'savefig.facecolor': 'white',
    'figure.facecolor': 'white', 'text.usetex': False,
}
METHODS = ['cut_bytes_only', 'weighted_score', 'onnx_real_boundary_hardware_aware',
           'cycle_time_no_handover', 'stored_predicted_stream_fps', 'measured_generic_completion']
METHOD_LABELS = ['Cut\npayload', 'Weighted\nscore', 'HW fit\n(H10)',
                 'Cycle\n(no handover)', 'Stored\nstream rate', 'Generic\ncompletion']

# Versioned conceptual geometry, not a measurement dataset. Both runner rows
# deliberately reuse these nodes, edges, hardware placements and cut.
SYSTEM_SPEC = {
    'schema': 'mlsys-r22-same-cut-schematic-v1', 'kind': 'conceptual',
    'canvas': [240, 188], 'cut_x': 151.0,
    'nodes': [[10, 0], [38, 0], [72, 8], [72, -8], [129, 0], [177, 0]],
    'edges': [[0, 1], [1, 2], [1, 3], [2, 4], [3, 4], [4, 5]],
    'prefix_bounds': [23, 151], 'suffix_bounds': [151, 190],
    'completion_bounds': [202, 237],
    'runners': [
        {'name': 'Generic', 'runtime': 'Common runtime', 'y': 130},
        {'name': 'Native', 'runtime': 'Model- and backend-specific runtime', 'y': 57},
    ],
    'heading': 'Paired comparison: same graph and cut',
    'notes': ['Generic also supports multi-tensor boundaries.',
              'Native uses one input to the GPU suffix.'],
    'source': 'scripts/split-inference/publication_mlsys_figures.py:SYSTEM_SPEC',
}

FIGURES = [
    ('system_overview', 'fig:runners', 'main', 3.35, 2.62),
    ('fastest_split_baseline_comparison', 'fig:baseline-effect', 'main', 3.3, 2.45),
    ('fastest_deployment_tradeoff', 'fig:fastest-tradeoff', 'supplement', 4.85, 2.8),
    ('resnet_h8_energy_current', 'fig:resnet-energy', 'main', 3.3, 2.3),
    ('yolov7_h8_case', 'fig:yolov7-case', 'main', 6.9, 2.25),
    ('quality_generic_selection_loss', 'fig:selectors', 'main', 3.3, 2.3),
    ('current_generic_selection_loss', 'fig:supp-unfiltered-selection', 'supplement', 3.3, 2.3),
    ('selector_loss_heatmap', 'fig:historical-selectors', 'supplement', 6.75, 4.4),
]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def positive(value):
    return finite(value) and value > 0


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _uids(value):
    """Collect explicit input identities, without inventing cross-cohort UIDs."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == 'uid' or key.endswith('_uid')) and isinstance(item, str):
                found.add(item)
            elif key.endswith('_uids') and isinstance(item, (list, tuple)):
                found.update(uid for uid in item if isinstance(uid, str))
            else:
                found.update(_uids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_uids(item))
    return sorted(found)


def _point(row, fields):
    return {field: row.get(field) for field in fields}


def build_figure_data(context):
    """Project shared results once; these payloads are also the renderer input."""
    winners = context['winners']
    model_order = [row['model'] for row in winners]
    generation = context.get('source_generation', context.get('data_generation', 'deepx_native_a4_20261015'))
    result = {}

    def add(name, points, caption, cohort='current_deployments', **metadata):
        result[name] = clean(dict(schema='mlsys-r22-figure-v1', kind='measurement',
                                 cohort=cohort, data_generation=generation,
                                 points=points, input_uids=_uids(points),
                                 omitted_points=[], caption=caption, **metadata))

    result['system_overview'] = {
        'schema': 'mlsys-r22-figure-v1', 'kind': 'conceptual',
        'data_generation': 'conceptual-spec-v1', 'input_uids': [],
        'specification': SYSTEM_SPEC,
        'caption': 'Generic and Native execute the same one-input cut. Generic also supports multi-tensor '
                   'boundaries beyond this paired comparison. Native is tailored to the accelerator–GPU '
                   'combination. The shared cut does not imply equal runtime costs.',
    }
    identity = ['model', 'split_uid', 'split_runner', 'split_setup', 'split_case',
                'global_full_uid', 'global_full_backend', 'global_full_setup',
                'global_full_physical_host', 'host_full_uid', 'host_full_setup',
                'host_full_physical_host', 'split_fps', 'global_full_fps', 'host_full_fps',
                'split_energy_j_per_image', 'global_full_energy_j_per_image',
                'host_full_energy_j_per_image']
    baseline, tradeoff, baseline_missing, tradeoff_missing = [], [], [], []
    for i, row in enumerate(winners):
        base = _point(row, identity)
        base.update(label=MODEL_LABELS.get(row['model'], row['model']))
        b = dict(base, R_global=row.get('R_global'), R_host=row.get('R_host'),
                 y=len(winners) - i - 1)
        for key, prefix in [('R_global', 'global'), ('R_host', 'host')]:
            b[prefix + '_plotted'] = positive(row.get(key))
            if not b[prefix + '_plotted']:
                baseline_missing.append(dict(base, coordinate=key,
                    reason=row.get('split_missing_reason') or row.get(prefix + '_full_missing_reason')
                           or 'missing_positive_finite_FPS_ratio'))
        baseline.append(b)
        point = dict(base, x=row.get('R_global'), y=row.get('energy_ratio_global'),
                     R_global=row.get('R_global'), energy_ratio_global=row.get('energy_ratio_global'))
        missing = []
        if not positive(point['x']):
            missing.append({'coordinate': 'R_global', 'reason': row.get('split_missing_reason')
                            or row.get('global_full_missing_reason') or 'missing_positive_finite_FPS_ratio'})
        if not positive(point['y']):
            missing.append({'coordinate': 'energy_ratio_global', 'reason': row.get('split_energy_missing_reason')
                            or row.get('global_full_energy_missing_reason') or 'missing_positive_finite_energy_ratio'})
        if missing:
            tradeoff_missing.append(dict(point, missing_values=missing))
        else:
            tradeoff.append(point)
    broad = context.get('unfiltered_winners')
    unchanged = ([(row['split_uid'], row['global_full_uid']) for row in winners] ==
                 [(row['split_uid'], row['global_full_uid']) for row in broad]) if broad is not None else None
    winner_note = (' Its winners match the broad current view for this generation.' if unchanged is True else
                   ' Its winners differ from the broad current view for this generation.' if unchanged is False else '')
    add('fastest_split_baseline_comparison', baseline,
        'The same selected fastest split with two Full references. A connection changes only the denominator, '
        'not the split or its speed. Global Full means the fastest actual Full configuration across hosts; '
        'same-host Full means the fastest Full on the split\'s physical host. Labels round factors to two decimals; '
        'plot data retain unrounded values and exact UIDs. The paper profile applies the numerical 5% CPU-relative '
        'quality rule.' + winner_note,
        denominator='global_fastest_full_and_same_host_fastest_full', x_scale='linear', reference_x=1.0,
        model_order=model_order)
    result['fastest_split_baseline_comparison']['omitted_points'] = clean(baseline_missing)
    add('fastest_deployment_tradeoff', tradeoff,
        'Throughput and energy of each model\'s fastest split relative to its globally fastest Full. Both axes '
        'use the same exact Full configuration. Right of one is faster and below one uses less energy per image. '
        'These throughput-selected points are not the full Pareto front or an energy-minimum selection. '
        'Quality eligibility does not establish equal accuracy or identical runtime costs. Text positions alone '
        'are displaced for readability; there are no inferred confidence intervals.',
        denominator='global_fastest_full', x_coordinate='R_global', y_coordinate='energy_ratio_global',
        reference_x=1.0, reference_y=1.0, model_order=model_order)
    result['fastest_deployment_tradeoff']['omitted_points'] = clean(tradeoff_missing)

    resnet = []
    for row in sorted(context['resnet_h8'], key=lambda row: row['uid']):
        point = _point(row, ['uid', 'model_id', 'setup_id', 'case_id', 'kind', 'runner', 'backend',
                             'fps', 'energy_mj_per_image', 'quality_value', 'quality_reference_value'])
        point.update(x=row.get('fps'), y=row.get('energy_mj_per_image'))
        resnet.append(point)
    splits = [point for point in resnet if point['kind'] == 'split']
    fast = min((p for p in splits if positive(p['fps'])), key=lambda p: (-p['fps'], p['uid']), default=None)
    low = min((p for p in splits if positive(p['energy_mj_per_image'])),
              key=lambda p: (p['energy_mj_per_image'], p['uid']), default=None)
    add('resnet_h8_energy_current', [p for p in resnet if positive(p['x']) and positive(p['y'])],
        'ResNet-50/H8: current throughput and calibrated system energy for all Native splits and both Full '
        'alternatives. The annotated cuts are selected independently by maximum FPS and minimum energy. '
        'FPS is the stored performance-cohort median; energy is mean per-repeat E/N in mJ/image. Performance '
        'and energy come from separate runs of the same configuration; energy-window rates are not substituted.',
        fastest_split_uid=fast['uid'] if fast else None, lowest_energy_split_uid=low['uid'] if low else None,
        x_coordinate='fps', y_coordinate='energy_mj_per_image')
    result['resnet_h8_energy_current']['omitted_points'] = [
        dict(p, reason='missing_positive_finite_throughput_or_energy') for p in resnet
        if not (positive(p['x']) and positive(p['y']))]

    case = [dict(row) for row in context['yolov7_case']]
    references = {row['reference_coco_ap_50_95_percent'] for row in case
                  if finite(row.get('reference_coco_ap_50_95_percent'))}
    assert len(references) <= 1, 'The YOLOv7 case must use one CPU quality reference'
    add('yolov7_h8_case', case,
        'YOLOv7 on the same H8 host. The selected Native split is compared with Hailo8 Full and TensorRT Full. '
        'The dashed AP line marks at most 5% relative quality loss against CPU ONNX. Bars are point estimates; '
        'available CPU-relative quality intervals are not paired split-minus-Full AP intervals and are not plotted '
        'as such. The global DeepX Full comparison remains a separate denominator in the winner tables.',
        panel_order=['throughput_fps', 'system_energy_mj_per_image', 'coco_ap_50_95_percent'],
        units=['FPS', 'mJ/image', '%'], bar_baseline=0,
        quality_threshold_percent=.95 * next(iter(references)) if references else None,
        error_bars='none; CPU-relative quality intervals do not provide paired Split-minus-Full AP intervals')

    for name, key, scope in [
            ('quality_generic_selection_loss', 'quality_selection_groups', 'both_runners_quality_loss_at_most_5pct_CPU'),
            ('current_generic_selection_loss', 'selection_groups', 'broad_current_pairs_without_quality_filter')]:
        groups = context[key]
        positions = {model: len(model_order) - i - 1 for i, model in enumerate(model_order)}
        points = []
        for row in groups:
            point = dict(row)
            point.update(x=row['loss_pct'], y=positions[row['model']] + {'H8': .16, 'H10': 0, 'DeepX': -.16}[row['setup']])
            points.append(point)
        n = sum(row['candidate_count'] for row in groups)
        mean = math.fsum(row['loss_pct'] for row in groups) / len(groups) if groups else None
        hits = sum(bool(row['exact_hit']) for row in groups)
        caption = (f'Generic-to-Native selection {"after the numerical 5% CPU-relative quality filter" if name.startswith("quality") else "before quality filtering"}, '
                   f'using {n} paired cuts. Each marker shows the Native throughput lost by choosing the Generic '
                   f'winner in one model/setup group. Zero means no loss. There are {hits} exact winner agreements '
                   f'in {len(groups)} groups. Each group receives equal weight; the group mean loss is '
                   f'{format(mean, ".2f") if mean is not None else "NA"}%. Selection uses unrounded FPS and stable UID ties.')
        add(name, points, caption, scope=scope, paired_candidates=n, groups=len(groups), exact_hits=hits,
            mean_loss_pct=mean, mean_weighting='equal_model_setup_groups', model_order=model_order,
            x_coordinate='loss_pct', x_unit='%', y_offset_purpose='separate_setups_within_model_only')
        pair_key = 'quality_pairs' if name.startswith('quality') else 'pairs'
        if pair_key in context:
            result[name]['input_uids'] = _uids(context[pair_key])

    history = [dict(row) for row in context['historical_groups']]
    historical_models = [model for model in model_order if any(row['model_id'] == model for row in history)]
    historical_models += sorted({row['model_id'] for row in history} - set(historical_models))
    group_order = [(model, setup) for model in historical_models for setup in SETUPS
                   if any(row['model_id'] == model and row['setup_id'] == setup for row in history)]
    methods = [method for method in METHODS if any(row['method'] == method for row in history)]
    historical_points = []
    for row in history:
        point = dict(row, loss_pct=100 * row['L_R'],
                     x=methods.index(row['method']), y=group_order.index((row['model_id'], row['setup_id'])))
        historical_points.append(point)
    add('selector_loss_heatmap', historical_points,
        'Historical graph-score comparison: Native throughput loss for six selectors in fixed model/setup groups. '
        'Every column uses the same historical Native reference measurements within a row. Parentheses give candidate '
        'counts; column headers count exact/tie-aware winner agreements. The stored hardware-fit profile is the H10 '
        'profile on every setup. The historical reported YOLOv7 Native overlay and archived Generic records remain '
        'separate from current A4 deployments. No current quality filter is applied to this historical cohort.',
        cohort='historical_graph_score_comparison', group_order=[list(group) for group in group_order],
        methods=methods, x_coordinate='method_index', y_coordinate='historical_group_index',
        color_coordinate='100 * L_R', color_unit='%')
    assets = context.get('assets', {})
    table_sources = {
        'fastest_split_baseline_comparison': 'tab:fastest-split-baselines',
        'fastest_deployment_tradeoff': 'tab:best-cases',
        'selector_loss_heatmap': 'tab:selectors',
    }
    current_inputs = ['results/split-inference/data/inputs/' + filename
                      for filename in ['cases.json', 'selected_evidence.json', 'energy_repeats.json']]
    for name, data in result.items():
        source = assets.get(table_sources.get(name), {})
        data['input_files'] = ([SYSTEM_SPEC['source'].split(':')[0]] if data['kind'] == 'conceptual'
                               else context.get('figure_input_files', {}).get(name,
                                    source.get('input_files', current_inputs)))
        data['input_uids'] = sorted(set(data['input_uids']) | set(_uids(data.get('omitted_points', []))))
        if name in ['fastest_split_baseline_comparison', 'fastest_deployment_tradeoff']:
            data['input_uids'] = source.get('input_uids', _uids(context.get('quality_rows', winners)))
        if name == 'selector_loss_heatmap':
            data['data_generation'] = source.get('data_generation', context.get(
                'historical_generation', 'historical_reported_ranking_overlay'))
    return clean(result)


def figure_index(payload):
    return [dict(name=name, label=label, document=document, main_paper=document == 'main',
                 type=payload[name]['kind'], width_inches=width, height_inches=height,
                 formats=['pdf', 'svg', 'png'], data_formats=['json'] if payload[name]['kind'] == 'conceptual' else ['csv', 'json'],
                 caption=payload[name]['caption'], input_uids=payload[name]['input_uids'],
                 input_files=payload[name]['input_files'],
                 data_generation=payload[name]['data_generation'])
            for name, label, document, width, height in FIGURES]


def write_figure_data(profile_output, context):
    """Emit the complete plot contract even when no plotting library is present."""
    output = Path(profile_output) / 'figures'
    output.mkdir(parents=True, exist_ok=True)
    payload = build_figure_data(context)
    index = figure_index(payload)
    def write_json(path, value):
        path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
    write_json(output / 'FIGURE_DATA.json', payload)
    write_json(output / 'INDEX.json', index)
    for name, data in payload.items():
        write_json(output / (name + '.json'), data)
        if data['kind'] == 'conceptual':
            continue
        rows = data['points'] + [dict(row, omitted=True) for row in data['omitted_points']]
        fields = list(dict.fromkeys(key for row in rows for key in row)) or ['uid']
        with (output / (name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
                                 if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})
    return index, payload


def render(profile_output, context, uniform_typography=False):
    """Render paper figures; preserve the frozen R22 typography by default.

    uniform_typography applies PAPER_STYLE to the statistical heatmap too.
    The conceptual runner schematic keeps its separate sans-serif labels.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    import numpy as np

    index, payload = write_figure_data(profile_output, context)
    output = Path(profile_output) / 'figures'
    styles = PAPER_STYLE
    dimensions = {name: (width, height) for name, _, _, width, height in FIGURES}

    def save(fig, name):
        fig.savefig(output / (name + '.pdf'), metadata={'Creator': 'MLSys R22 offline renderer',
                    'Producer': 'Matplotlib', 'CreationDate': None, 'ModDate': None})
        fig.savefig(output / (name + '.svg'), metadata={'Creator': 'MLSys R22 offline renderer', 'Date': None})
        fig.savefig(output / (name + '.png'), dpi=240, metadata={'Software': 'Matplotlib'})
        plt.close(fig)

    def annotate_points(ax, points, labels, fontsize=8):
        """Stable bounded search for text offsets; data coordinates never move."""
        fig = ax.figure
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        font = FontProperties(family='STIXGeneral', size=fontsize)
        scale = fig.dpi / 72
        axes = ax.get_window_extent(renderer)
        inside = (axes.x0 + 2, axes.y0 + 2, axes.x1 - 2, axes.y1 - 2)
        locations = [ax.transData.transform((p['x'], p['y'])) for p in points]
        occupied = []
        def overlap(a, b):
            return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
        for point, label in zip(points, labels):
            x, y = ax.transData.transform((point['x'], point['y']))
            width = max(renderer.get_text_width_height_descent(line, font, False)[0] for line in label.split('\n')) + 3 * scale
            height = (fontsize * 1.2 * len(label.split('\n')) + 2) * scale
            candidates = []
            for radius in [6, 10, 15, 22, 30, 42, 58]:
                for sx, sy in [(1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0)]:
                    dx, dy = radius * sx, radius * sy
                    left = x + dx * scale - (width if dx < 0 else width / 2 if dx == 0 else 0)
                    bottom = y + dy * scale - (height if dy < 0 else height / 2 if dy == 0 else 0)
                    box = (left, bottom, left + width, bottom + height)
                    score = 10000 * (width * height - overlap(box, inside))
                    score += 1000 * sum(overlap(box, other) for other in occupied)
                    score += 100 * sum(overlap(box, (xx - 4, yy - 4, xx + 4, yy + 4)) for xx, yy in locations)
                    score += math.hypot(dx, dy)
                    candidates.append((score, dx, dy, box))
            _, dx, dy, box = min(candidates, key=lambda candidate: candidate[:3])
            occupied.append(box)
            ax.annotate(label, (point['x'], point['y']), xytext=(dx, dy), textcoords='offset points',
                        ha='right' if dx < 0 else 'center' if dx == 0 else 'left',
                        va='top' if dy < 0 else 'center' if dy == 0 else 'bottom', fontsize=fontsize,
                        bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .92, 'pad': .5},
                        arrowprops={'arrowstyle': '-', 'color': '#777777', 'lw': .45, 'shrinkA': 1, 'shrinkB': 3}, zorder=6)

    with plt.rc_context(styles):
        # The conceptual figure is generated from its versioned source geometry.
        name = 'system_overview'
        spec = payload[name]['specification']
        with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 7}):
            fig = plt.figure(figsize=dimensions[name])
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set(xlim=(0, spec['canvas'][0]), ylim=(0, spec['canvas'][1]))
            ax.axis('off')
            ink, blue, orange, cut_color = '#292929', '#236fa4', '#ba6400', '#466258'
            cut_x = spec['cut_x']
            ax.text(120, 180, spec['heading'], ha='center', va='center', fontsize=7.5, color=ink)
            for runner in spec['runners']:
                y = runner['y']
                ax.text(3, y + 35, runner['name'], fontsize=8.4, fontweight='bold', va='center', color=ink)
                ax.text(237, y + 35, runner['runtime'], fontsize=6.9, ha='right', va='center', color=ink)
                for bounds, face, title, color in [(spec['prefix_bounds'], '#edf4fa', 'Accelerator prefix', blue),
                                                   (spec['suffix_bounds'], '#fff2e4', 'GPU suffix', orange)]:
                    left, right = bounds
                    ax.add_patch(FancyBboxPatch((left, y - 13), right - left, 26,
                                 boxstyle='round,pad=0,rounding_size=2.7', linewidth=0, facecolor=face, zorder=0))
                    ax.text((left + right) / 2, y + 19, title, color=color, fontsize=7.1, ha='center', va='center')
                nodes = [(x, y + offset) for x, offset in spec['nodes']]
                for start, end in [(nodes[a], nodes[b]) for a, b in spec['edges']] + [(nodes[-1], (202, y))]:
                    ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=5,
                                 color=ink, linewidth=.7, shrinkA=3.3, shrinkB=3.3, zorder=2))
                for i, (x, yy) in enumerate(nodes):
                    color = '#777777' if i == 0 else blue if x < cut_x else orange
                    ax.add_patch(Circle((x, yy), radius=2.6 if i == 0 else 3.1, facecolor='white',
                                        edgecolor=color, linewidth=1, zorder=3))
                ax.text(10, y - 21, 'Input', ha='center', va='center', fontsize=6.8, color=ink)
                ax.add_patch(FancyBboxPatch((202, y - 10.5), 35, 21, boxstyle='round,pad=0,rounding_size=2',
                                            linewidth=.65, edgecolor='#888888', facecolor='#f6f6f6', zorder=3))
                ax.text(219.5, y, 'Task\ncompletion', ha='center', va='center', fontsize=6.5, linespacing=1.15, color=ink, zorder=4)
                ax.plot([cut_x, cut_x], [y - 14, y + 14], color=cut_color, lw=.85, ls=(0, (2.2, 2.1)), zorder=4)
                ax.add_patch(Rectangle((cut_x - 2.8, y - 1.8), 5.6, 3.6, facecolor='white', edgecolor=cut_color, lw=.9, zorder=5))
                ax.text(cut_x, y - 21, '1 tensor', ha='center', va='center', fontsize=7, color=cut_color)
            ax.plot([3, 237], [97, 97], color='#dedede', lw=.6)
            for y, text in zip([17, 6], spec['notes']):
                ax.text(120, y, text, ha='center', va='center', fontsize=6.6, color=ink)
            save(fig, name)

        name = 'fastest_split_baseline_comparison'
        data = payload[name]
        fig, ax = plt.subplots(figsize=dimensions[name])
        for point in data['points']:
            xg, xh, y = point['R_global'], point['R_host'], point['y']
            if point['global_plotted'] and point['host_plotted']:
                ax.plot([xg, xh], [y, y], color='#8c8c8c', lw=.8, zorder=1)
            if point['global_plotted']:
                ax.scatter(xg, y, s=22, color='#4477AA', zorder=3)
            if point['host_plotted']:
                ax.plot(xh, y, ls='none', marker='|', ms=10, mew=1.5, color='#EE7733', zorder=4)
            if point['global_plotted'] and point['host_plotted']:
                if xg == xh:
                    ax.annotate(f'{xg:.2f}', (xg, y), xytext=(7, 0), textcoords='offset points', va='center', fontsize=7.5)
                elif xh - xg < .08:
                    ax.annotate(f'{xg:.2f} / {xh:.2f}', (xh, y), xytext=(7, 0), textcoords='offset points', va='center', fontsize=7.5)
                else:
                    ax.annotate(f'{xg:.2f}', (xg, y), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=7.2)
                    ax.annotate(f'{xh:.2f}', (xh, y), xytext=(3, -9), textcoords='offset points', ha='left', fontsize=7.2)
            else:
                for x, valid in [(xg, point['global_plotted']), (xh, point['host_plotted'])]:
                    if valid:
                        ax.annotate(f'{x:.2f}', (x, y), xytext=(7, 0), textcoords='offset points', va='center', fontsize=7.5)
        ratios = [p[key] for p in data['points'] for key in ['R_global', 'R_host'] if positive(p[key])]
        ax.set_yticks([p['y'] for p in data['points']], [p['label'] for p in data['points']])
        ax.axvline(1, ls='--', lw=.65, color='#777777')
        ax.set(xlim=(min([.7] + [x - .1 for x in ratios]), max([4.85] + [x + .5 for x in ratios])),
               ylim=(-.6, len(data['points']) - .5), xlabel='Split throughput / Full throughput')
        ax.xaxis.set_major_locator(MaxNLocator(5, integer=True))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:g}×'))
        ax.legend(handles=[Line2D([], [], ls='none', marker='o', color='#4477AA', ms=4.5, label='Global Full'),
                           Line2D([], [], ls='none', marker='|', color='#EE7733', ms=8, mew=1.5, label='Same-host Full')],
                  loc='lower left', bbox_to_anchor=(-.02, 1.01), ncol=2, frameon=False,
                  columnspacing=.8, handletextpad=.35, borderaxespad=0)
        ax.grid(axis='x', alpha=.13)
        fig.tight_layout(pad=.3)
        save(fig, name)

        name = 'fastest_deployment_tradeoff'
        points = payload[name]['points']
        fig, ax = plt.subplots(figsize=dimensions[name])
        ax.scatter([p['x'] for p in points], [p['y'] for p in points], s=24, color='#4477AA', zorder=3)
        ax.axvline(1, ls='--', lw=.65, color='#777777')
        ax.axhline(1, ls='--', lw=.65, color='#777777')
        xs, ys = [p['x'] for p in points], [p['y'] for p in points]
        ax.set(xlim=(min([.68] + [x - .12 for x in xs]), max([2.8] + [x + .25 for x in xs])),
               ylim=(min([.38] + [y - .1 for y in ys]), max([1.98] + [y + .16 for y in ys])),
               xlabel='Split / globally fastest Full: throughput', ylabel='Split / same Full: energy per image')
        for axis in [ax.xaxis, ax.yaxis]:
            axis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:g}×'))
        ax.grid(alpha=.13)
        fig.tight_layout(pad=.35)
        annotate_points(ax, points, [p['label'] for p in points])
        save(fig, name)

        name = 'resnet_h8_energy_current'
        data = payload[name]
        points = data['points']
        fig, ax = plt.subplots(figsize=dimensions[name])
        for predicate, label, marker, color, size in [
                (lambda p: p['kind'] == 'split', 'Native splits', 'o', '#4477AA', 16),
                (lambda p: p['kind'] != 'split' and 'tensorrt' not in p['backend'], 'H8 Full', 's', '#e69f00', 27),
                (lambda p: p['kind'] != 'split' and 'tensorrt' in p['backend'], 'TensorRT Full', 'D', '#d55e00', 27)]:
            group = [p for p in points if predicate(p)]
            ax.scatter([p['x'] for p in group], [p['y'] for p in group], s=size, marker=marker,
                       color=color, label=label, zorder=3)
        selected = [p for p in points if p['uid'] in {data['fastest_split_uid'], data['lowest_energy_split_uid']}]
        for i, point in enumerate(selected):
            ax.annotate(point['case_id'], (point['x'], point['y']), xytext=(-44, 12 if point['uid'] == data['fastest_split_uid'] else -3),
                        textcoords='offset points', fontsize=8, arrowprops={'arrowstyle': '-', 'lw': .5})
        ys = [p['y'] for p in points]
        ax.set(xlabel='Throughput (FPS)', ylabel='System energy (mJ/image)',
               ylim=(min([36] + [y - 5 for y in ys]), max([139] + [y + 5 for y in ys])))
        ax.legend(fontsize=7.5, frameon=False)
        ax.grid(alpha=.13)
        fig.tight_layout(pad=.35)
        save(fig, name)

        name = 'yolov7_h8_case'
        data = payload[name]
        points = data['points']
        fig, axes = plt.subplots(1, 3, figsize=dimensions[name])
        fig.subplots_adjust(left=.055, right=.99, bottom=.22, top=.78, wspace=.32)
        colors = ['#A7A7A7', '#4477AA', '#228833']
        labels = [p['configuration'].replace(' Full', '\nFull').replace('Split ', 'Split\n') for p in points]
        panels = [
            ('throughput_fps', '(a) Throughput', 'FPS · higher is better', [0, 40, 80, 120], 130, 0),
            ('system_energy_mj_per_image', '(b) System energy', 'mJ/image · lower is better', [0, 200, 400, 600], 720, 2),
            ('coco_ap_50_95_percent', r'(c) COCO AP$_{50:95}$', '% · higher is better', [0, 20, 40], 56, 2),
        ]
        for ax, (field, title, unit, ticks, lower_limit, precision) in zip(axes, panels):
            values = [p[field] for p in points]
            limit = max(lower_limit, max((v for v in values if finite(v)), default=0) * 1.2)
            bars = ax.bar(range(len(points)), [v if finite(v) else math.nan for v in values], width=.57,
                          color=colors, edgecolor='white', linewidth=.35, zorder=3)
            ax.set(ylim=(0, limit), xlim=(-.6, len(points) - .4))
            ax.set_yticks(ticks)
            ax.set_xticks(range(len(points)), labels)
            ax.tick_params(axis='x', length=0, pad=5)
            ax.tick_params(axis='y', length=2.5, pad=2)
            ax.grid(axis='y', color='#dddddd', linewidth=.45, zorder=0)
            ax.set_title(title, pad=25, fontweight='bold')
            ax.text(.5, 1.055, unit, transform=ax.transAxes, ha='center', va='bottom', fontsize=8.8)
            if field == 'coco_ap_50_95_percent' and data['quality_threshold_percent'] is not None:
                ax.axhline(data['quality_threshold_percent'], color='#333333', lw=.75, ls=(0, (3, 2)), zorder=4)
            for bar, value in zip(bars, values):
                if finite(value):
                    offset = 4.3 if field == 'coco_ap_50_95_percent' else limit * .025
                    ax.text(bar.get_x() + bar.get_width() / 2, value + offset, f'{value:.{precision}f}',
                            ha='center', va='bottom', fontsize=9)
                else:
                    ax.text(bar.get_x() + bar.get_width() / 2, 0, 'NA', ha='center', va='bottom', fontsize=9)
        save(fig, name)

        for name in ['quality_generic_selection_loss', 'current_generic_selection_loss']:
            data = payload[name]
            fig, ax = plt.subplots(figsize=dimensions[name])
            for setup in SETUPS:
                points = [p for p in data['points'] if p['setup'] == setup]
                ax.scatter([p['x'] for p in points], [p['y'] for p in points], label=setup,
                           marker=MARKERS[setup], s=18, zorder=3, color=COLORS[setup])
            models = data['model_order']
            ax.set_yticks(list(range(len(models) - 1, -1, -1)), [MODEL_LABELS.get(m, m) for m in models])
            maximum = max([70] + [p['x'] for p in data['points'] if finite(p['x'])])
            ax.set(xlim=(-2.5, maximum + 3), ylim=(-.55, len(models) - .45), xlabel='Native throughput lost (%)')
            ax.xaxis.set_major_locator(MaxNLocator(4, steps=[1, 2, 5, 10]))
            ax.legend(loc='lower left', bbox_to_anchor=(-.02, 1.01), ncol=3, frameon=False,
                      columnspacing=.8, handletextpad=.35, borderaxespad=0)
            ax.grid(axis='x', alpha=.13)
            fig.tight_layout(pad=.3)
            save(fig, name)

        name = 'selector_loss_heatmap'
        data = payload[name]
        groups, methods = data['group_order'], data['methods']
        heatmap_style = PAPER_STYLE if uniform_typography else {
            'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.labelsize': 8}
        with plt.rc_context(heatmap_style):
            matrix = np.full((len(groups), len(methods)), np.nan)
            lookup = {}
            for point in data['points']:
                matrix[point['y'], point['x']] = point['loss_pct']
                lookup[(point['model_id'], point['setup_id'], point['method'])] = point
            fig, ax = plt.subplots(figsize=dimensions[name])
            fig.subplots_adjust(left=.275, right=.895, bottom=.025, top=.85)
            im = ax.imshow(matrix, cmap='YlOrRd', vmin=0, vmax=max(90, np.nanmax(matrix)), aspect='auto', interpolation='nearest')
            ax.grid(False)
            for i in range(len(groups)):
                for j in range(len(methods)):
                    value = matrix[i, j]
                    ax.text(j, i, f'{value:.1f}' if finite(value) else 'NA', ha='center', va='center',
                            fontsize=7.5, color='white' if value >= 49 else '#202020')
            hits = [sum(str(p['top1_hit_tie_aware']).lower() in ['true', '1'] for p in data['points'] if p['method'] == method)
                    for method in methods]
            ax.set_xticks(range(len(methods)), [f'{METHOD_LABELS[METHODS.index(method)]}\n{hit}/{len(groups)} hits'
                                               for method, hit in zip(methods, hits)])
            ax.xaxis.tick_top()
            ax.tick_params(axis='x', length=0, pad=6, labelsize=7.5)
            ax.set_yticks(range(len(groups)), [f'{setup}  ({lookup[(model, setup, methods[0])]["n"]})'
                                              for model, setup in groups])
            ax.tick_params(axis='y', length=0, pad=5, labelsize=7.5)
            for tick, (_, setup) in zip(ax.get_yticklabels(), groups):
                tick.set_color(COLORS[setup])
            for model in dict.fromkeys(model for model, _ in groups):
                positions = [i for i, (m, _) in enumerate(groups) if m == model]
                ax.text(-.175, 1 - (sum(positions) / len(positions) + .5) / len(groups), MODEL_LABELS.get(model, model),
                        transform=ax.transAxes, ha='right', va='center', fontsize=7.5, color='#222222')
                if positions[-1] < len(groups) - 1:
                    ax.axhline(positions[-1] + .5, color='white', lw=1.8)
            for x in range(len(methods) - 1):
                ax.axvline(x + .5, color='white', lw=.55)
            for spine in ax.spines.values():
                spine.set_visible(False)
            color_axes = fig.add_axes([.92, .16, .017, .53])
            colorbar = fig.colorbar(im, cax=color_axes, ticks=[0, 20, 40, 60, 80])
            colorbar.ax.tick_params(labelsize=7.5, width=.5, length=2)
            colorbar.set_label('Native throughput loss (%)', fontsize=8, labelpad=6)
            save(fig, name)
    return index, payload
