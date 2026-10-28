#!/usr/bin/env python3
"""Retrospective graph -> Generic -> Native selection from published paired data.

This command performs no fitting, hardware measurement or quality reclassification.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_STUDY = REPO / 'results/supplementary-studies/rq2-native-scope-20261027'
DEFAULT_GRAPH_METADATA = REPO / 'results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs/feature_metadata.json'
METHODS = ('bytes', 'weighted_default', 'weighted_cv')
PRIMARY_BUDGETS = (5, 12)
WORKFLOW_EXAMPLE_GENERIC_TESTS = 5
WORKFLOW_EXAMPLE_NATIVE_TESTS = 2


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError('Cannot export an empty table: ' + str(path))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(pairs, ranking_rows, max_budget=20):
    """Rank only by the supplied graph order and observed Generic throughput.

    Native throughput is accessed only to evaluate the chosen final candidates.
    Lexical native_uid resolves tied Generic FPS without looking at Native FPS.
    """
    groups = defaultdict(list)
    by_uid = {}
    for source in pairs:
        row = dict(source)
        uid = row['native_uid']
        if uid in by_uid:
            raise ValueError('Duplicate paired identity: ' + uid)
        for field in ('native_fps', 'generic_fps'):
            row[field] = float(row[field])
            if not math.isfinite(row[field]) or row[field] <= 0:
                raise ValueError('Invalid throughput: ' + uid)
        if str(row.get('quality_eligible', 'True')).lower() not in ('true', '1'):
            raise ValueError('Input contains a quality-ineligible cut: ' + uid)
        by_uid[uid] = row
        groups[row['model'], row['setup']].append(row)
    if not groups:
        raise ValueError('No paired candidates')
    rankings = defaultdict(list)
    for row in ranking_rows:
        if row['method'] in METHODS:
            rankings[row['model'], row['setup'], row['method']].append(row)
    details = []
    for (model, setup), group in sorted(groups.items()):
        tasks = {row['task'] for row in group}
        if len(tasks) != 1:
            raise ValueError('Inconsistent task within group')
        best_native = max(row['native_fps'] for row in group)
        uid_set = {row['native_uid'] for row in group}
        for method in METHODS:
            ordered = sorted(rankings[model, setup, method], key=lambda row: int(row['rank']))
            if len(ordered) != len(group) or {row['native_uid'] for row in ordered} != uid_set:
                raise ValueError(f'Ranking does not cover the eligible group exactly: {model}/{setup}/{method}')
            if [int(row['rank']) for row in ordered] != list(range(1, len(group) + 1)):
                raise ValueError('Ranks must be consecutive and unique')
            graph_rank = [by_uid[row['native_uid']] for row in ordered]
            for k in range(1, max_budget + 1):
                shortlist = graph_rank[:k]
                shortlist_best = max(row['native_fps'] for row in shortlist)
                generic_rank = sorted(shortlist, key=lambda row: (-row['generic_fps'], row['native_uid']))
                policies = (
                    ('direct_graph_all_native', 0, shortlist),
                    ('cascade_native1', 1, generic_rank[:1]),
                    ('cascade_native2', 2, generic_rank[:2]),
                )
                for policy, native_budget, chosen in policies:
                    native_winner = min(chosen, key=lambda row: (-row['native_fps'], row['native_uid']))
                    retained = 100 * native_winner['native_fps'] / best_native
                    loss = 100 * (1 - native_winner['native_fps'] / best_native)
                    details.append(dict(
                        model=model, setup=setup, task=group[0]['task'], candidates=len(group),
                        method=method, k=k, policy=policy, native_budget=native_budget,
                        generic_tests=len(shortlist) if native_budget else 0,
                        native_tests=len(chosen),
                        graph_shortlist=';'.join(row['case'] for row in shortlist),
                        native_tested=';'.join(row['case'] for row in chosen),
                        selected_cut=native_winner['case'], selected_native_fps=native_winner['native_fps'],
                        best_native_fps=best_native, shortlist_best_native_fps=shortlist_best,
                        retained_native_pct=retained, loss_pct=loss,
                        exact_native_winner=int(native_winner['native_fps'] == best_native),
                        within_1pct=int(loss <= 1 + 1e-12), within_5pct=int(loss <= 5 + 1e-12),
                        preserves_shortlist_best=int(native_winner['native_fps'] == shortlist_best),
                    ))
    return details


def aggregate(details):
    output = []
    for task in ('all', 'classification', 'detection'):
        selected = defaultdict(list)
        for row in details:
            if task == 'all' or row['task'] == task:
                selected[row['method'], row['k'], row['policy']].append(row)
        for (method, k, policy), rows in sorted(selected.items()):
            n = len(rows)
            losses = [row['loss_pct'] for row in rows]
            hits = sum(row['exact_native_winner'] for row in rows)
            output.append(dict(
                task=task, method=method, k=k, policy=policy, groups=n,
                candidates=sum(row['candidates'] for row in rows),
                native_budget=rows[0]['native_budget'],
                generic_tests=sum(row['generic_tests'] for row in rows),
                native_tests=sum(row['native_tests'] for row in rows),
                mean_loss_pct=statistics.mean(losses),
                mean_retained_native_pct=statistics.mean(row['retained_native_pct'] for row in rows),
                median_loss_pct=statistics.median(losses), max_loss_pct=max(losses),
                exact_winners=hits, exact_winner_pct=100 * hits / n,
                within_1pct=sum(row['within_1pct'] for row in rows),
                within_5pct=sum(row['within_5pct'] for row in rows),
                shortlist_best_preserved=sum(row['preserves_shortlist_best'] for row in rows),
            ))
    return output


def verify(details, summaries, published):
    """Verify published direct-graph curves and finite-budget accounting."""
    original = {(row['method'], int(row['k'])): row for row in published}
    checks = []
    for row in summaries:
        if row['task'] == 'all' and row['policy'] == 'direct_graph_all_native':
            key = row['method'], row['k']
            if key not in original:
                raise ValueError('Missing published graph comparison: ' + str(key))
            reference = original[key]
            for field in ('mean_loss_pct', 'median_loss_pct', 'max_loss_pct'):
                if not math.isclose(row[field], float(reference[field]), abs_tol=1e-10):
                    raise ValueError(f'Published direct graph mismatch: {key}/{field}')
            for field in ('exact_winners', 'groups'):
                if row[field] != int(reference[field]):
                    raise ValueError(f'Published direct graph count mismatch: {key}/{field}')
            checks.append(key)
    for row in details:
        shortlist_n = min(row['k'], row['candidates'])
        expected_native = shortlist_n if row['native_budget'] == 0 else min(row['native_budget'], shortlist_n)
        if row['native_tests'] != expected_native:
            raise ValueError('Native budget accounting mismatch')
        if row['generic_tests'] != (shortlist_n if row['native_budget'] else 0):
            raise ValueError('Generic budget accounting mismatch')
        if not -1e-10 <= row['loss_pct'] <= 100 + 1e-10:
            raise ValueError('Invalid selection loss')
        if not math.isclose(row['retained_native_pct'] + row['loss_pct'], 100, abs_tol=1e-10):
            raise ValueError('Throughput ratio/loss mismatch')
    return dict(status='PASS', direct_graph_aggregate_checks=len(checks),
                group_policy_budget_checks=len(details),
                fitting_performed=False, hardware_measurements=False)


def number(value, language, digits=2):
    value = f'{value:.{digits}f}'
    return value.replace('.', ',') if language == 'de' else value


def export_tables(output, summaries, details, language):
    table = output / 'artifacts' / language / 'tables'
    table.mkdir(parents=True, exist_ok=True)
    primary = [row for row in summaries if row['task'] == 'all' and row['method'] == 'bytes'
               and row['policy'] == 'cascade_native2' and row['k'] in PRIMARY_BUDGETS]
    write_csv(table / 'primary_budget.csv', primary)
    n = primary[0]['groups']
    if language == 'en':
        caption = ('Staged-selection budgets per model--accelerator combination. Budgets are maxima. Exact winners, mean and '
                   'lowest retained Native throughput refer to the best measured Native cut in each combination. '
                   f'All {n} combinations receive equal weight.')
        header = r'\shortstack{Tests\\Generic + Native} & \shortstack{Exact\\winners} & \shortstack{Mean\\(\%)} & \shortstack{Lowest\\(\%)} \\'
    else:
        caption = ('Testbudgets je Modell--Gerät-Gruppe. Die Budgets sind Höchstwerte. Exakte Treffer sowie der mittlere '
                   'und niedrigste erreichte Native-Durchsatz beziehen sich auf den besten gemessenen Native-Schnitt '
                   f'der jeweiligen Gruppe. Alle {n} Gruppen werden gleich gewichtet.')
        header = r'\shortstack{Tests\\Generic + Native} & \shortstack{Exakte\\Treffer} & \shortstack{Mittel\\(\%)} & \shortstack{Minimum\\(\%)} \\'
    lines = [r'\begin{table}[t]', r'\centering\small', r'\caption{' + caption + '}',
             r'\label{tab:staged-budget}', r'\setlength{\tabcolsep}{3pt}',
             r'\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}crrr@{}}', r'\toprule', header, r'\midrule']
    for row in primary:
        lines.append(f"{row['k']} + 2 & {row['exact_winners']}/{row['groups']} & {number(row['mean_retained_native_pct'], language)} & {number(100-row['max_loss_pct'], language)} " + r'\\')
    lines += [r'\bottomrule', r'\end{tabular*}', r'\end{table}', '']
    (table / 'primary_budget.tex').write_text('\n'.join(lines), encoding='utf-8')
    task_rows = [row for row in summaries if row['method'] == 'bytes' and row['policy'] == 'cascade_native2' and row['k'] in PRIMARY_BUDGETS]
    write_csv(table / 'task_budgets.csv', task_rows)
    group_rows = [row for row in details if row['method'] == 'bytes' and row['policy'] == 'cascade_native2' and row['k'] in PRIMARY_BUDGETS]
    write_csv(table / 'group_budgets.csv', group_rows)
    comparisons = [row for row in summaries if row['task'] == 'all' and row['method'] == 'bytes' and row['k'] in PRIMARY_BUDGETS]
    write_csv(table / 'native_test_comparison.csv', comparisons)
    task_names = {'all': 'All' if language == 'en' else 'Alle',
                  'classification': 'Classifiers' if language == 'en' else 'Klassifikation',
                  'detection': 'Detectors' if language == 'en' else 'Detektion'}
    if language == 'en':
        title = 'Staged selection by task. All rows use Bytes and at most two Native tests per group. Test counts are totals over the reported groups.'
        header = r'Task & $k$ & Groups & Generic tests & Native tests & Exact & Mean retained (\%) & Max. loss (\%) \\'
    else:
        title = 'Stufenweise Auswahl nach Aufgabe. Alle Zeilen verwenden Bytes und höchstens zwei Native-Tests je Gruppe. Die Testzahlen summieren sich über die angegebenen Gruppen.'
        header = r'Aufgabe & $k$ & Gruppen & Generic-Tests & Native-Tests & Exakt & Mittlerer Anteil (\%) & Max. Verlust (\%) \\'
    lines = [r'\begin{table*}[t]', r'\centering\small', r'\caption{' + title + '}',
             r'\label{tab:staged-task-budgets}', r'\begin{tabular}{@{}lrrrrrrr@{}}', r'\toprule', header, r'\midrule']
    for row in task_rows:
        lines.append(f"{task_names[row['task']]} & {row['k']} & {row['groups']} & {row['generic_tests']} & {row['native_tests']} & {row['exact_winners']} & {number(row['mean_retained_native_pct'], language)} & {number(row['max_loss_pct'], language)} " + r'\\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table*}', '']
    (table / 'task_budgets.tex').write_text('\n'.join(lines), encoding='utf-8')


def export_figure(output, summaries, language, figure_profile='paper'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    style_path = REPO / 'scripts/split-inference/publication_mlsys_figures.py'
    spec = importlib.util.spec_from_file_location('staged_selection_style', style_path)
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    plt.rcParams.update(style.DISSERTATION_STYLE if figure_profile == 'dissertation' else style.PAPER_STYLE)
    plt.rcParams['svg.hashsalt'] = 'staged-selection-r41'
    rows = [row for row in summaries if row['task'] == 'all' and row['method'] == 'bytes'
            and row['policy'] in ('cascade_native1', 'cascade_native2') and row['k'] >= 2]
    rows.sort(key=lambda row: (row['native_budget'], row['k']))
    fig, ax = plt.subplots(figsize=(4.65, 2.85) if figure_profile == 'dissertation' else (3.35, 2.55))
    fig.subplots_adjust(left=.18, bottom=.225, right=.97, top=.86)
    for budget, color, linestyle, marker in [(2, 'blue', '-', 'o'), (1, 'orange', '--', 's')]:
        series = [row for row in rows if row['native_budget'] == budget]
        label = (f'{budget} Native tests' if budget == 2 else '1 Native test') if language == 'en' else (f'{budget} Native-Tests' if budget == 2 else '1 Native-Test')
        ax.plot([row['k'] for row in series], [row['mean_retained_native_pct'] for row in series],
                color=style.PAPER_PALETTE[color], linewidth=1.35, linestyle=linestyle,
                marker=marker, markersize=2.3, label=label, zorder=4 if budget == 2 else 3)
    ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.01), ncol=2, frameon=False,
              fontsize=8.5 if figure_profile == 'dissertation' else 7.2, handlelength=1.7, columnspacing=1.1, handletextpad=.45, borderpad=0)

    ax.axhline(100, color='#a7a7a7', linewidth=.6, linestyle=(0, (3, 3)), zorder=1)
    ax.grid(axis='y', color='#dddddd', linewidth=.45, zorder=0)
    minimum = min(row['mean_retained_native_pct'] for row in rows)
    lower = max(0, 5 * math.floor((minimum - 1) / 5))
    ax.set_ylim(lower, 101.5)
    ax.set_xlim(1.6, max(row['k'] for row in rows) + .4)
    ax.set_xticks([2, 5, 10, 12, 15, 20])
    if language == 'en':
        ax.set_xlabel('Max. Generic tests per combination')
        ax.set_ylabel('Mean Native throughput retained (%)')
        connector = 'Generic + 2 Native'
    else:
        ax.set_xlabel('Maximale Generic-Tests je Gruppe')
        ax.set_ylabel('Mittlerer Native-Durchsatzanteil (%)')
        connector = 'Generic + 2 Native'
    for k in PRIMARY_BUDGETS:
        row = next(row for row in rows if row['k'] == k and row['native_budget'] == 2)
        xtext = 9.8 if k == 5 else 14.2
        ytext = lower + (101.5 - lower) * (.31 if k == 5 else .51)
        label = f"{k} {connector}\n{number(row['mean_retained_native_pct'], language)}%"
        ax.scatter([k], [row['mean_retained_native_pct']], s=18, color=style.PAPER_PALETTE['blue'], zorder=4)
        ax.annotate(label, xy=(k, row['mean_retained_native_pct']), xytext=(xtext, ytext),
                    ha='center', va='center', fontsize=9 if figure_profile == 'dissertation' else 8,
                    arrowprops=dict(arrowstyle='-', color='#777777', linewidth=.6),
                    bbox=dict(facecolor='white', edgecolor='none', pad=1.5), zorder=5)
    folder = output / 'artifacts' / language / 'figures'
    folder.mkdir(parents=True, exist_ok=True)
    for suffix in ('pdf', 'svg', 'png'):
        options = {'metadata': {'CreationDate': None, 'ModDate': None}} if suffix == 'pdf' else {}
        if suffix == 'svg':
            options = {'metadata': {'Date': None}}
        fig.savefig(folder / f'staged_selection_budget.{suffix}', dpi=220, **options)
    plt.close(fig)
    write_csv(folder / 'staged_selection_budget.csv', rows)
    write_json(folder / 'staged_selection_budget.json', dict(
        schema='staged-selection-budget-v2', method='bytes', native_test_budgets=[1, 2],
        target='best measured Native throughput within each paired group',
        aggregation='unweighted mean of per-group throughput ratios', language=language,
        points=rows, note='Budgets 2–20 are shown without smoothing or removing non-monotonic changes. Budget 1 is included in the analysis data.'))


def flow_spec(source):
    """Use a recorded graph size as context, without claiming full-graph testing."""
    source = Path(source).resolve()
    metadata = json.loads(source.read_text())
    model = 'yolo11l'
    count = metadata['prediction_sources'][model]['candidate_count']
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError('Graph candidate count must be a positive integer')
    try:
        source_name = str(source.relative_to(REPO))
    except ValueError:
        source_name = source.name
    return dict(schema='staged-selection-flow-v2', kind='illustrative_budget_workflow',
                example_model=model, example_model_label='YOLO11l', graph_candidates=count,
                source=dict(path=source_name, sha256=sha(source)),
                pool_count=None, generic_budget=WORKFLOW_EXAMPLE_GENERIC_TESTS,
                maximum_native_tests=WORKFLOW_EXAMPLE_NATIVE_TESTS, selected_splits=1,
                stage_counts=[count, WORKFLOW_EXAMPLE_GENERIC_TESTS, WORKFLOW_EXAMPLE_NATIVE_TESTS, 1],
                example_budget_measured_for_this_model=False,
                graph_count_scope='Complete workflow graph candidates, before backend support and quality checks.',
                evaluation_scope='Selection outcomes are evaluated separately on the paired candidate pools. The paired detector pools contain three cuts each.',
                geometry_note='Each square represents one option at that illustrative stage. All squares have equal size; process boxes do not encode quantity.')


def export_flow(output, spec_data, language, figure_profile='paper'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    from matplotlib.colors import to_rgb
    style_path = REPO / 'scripts/split-inference/publication_mlsys_figures.py'
    spec = importlib.util.spec_from_file_location('staged_flow_style', style_path)
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    plt.rcParams.update(style.DISSERTATION_STYLE if figure_profile == 'dissertation' else style.PAPER_STYLE)
    plt.rcParams['svg.hashsalt'] = 'staged-selection-flow-r41'
    count, model = spec_data['graph_candidates'], spec_data['example_model_label']
    if language == 'en':
        labels = [
            ('Graph preselection', 'Pool selection + Bytes'),
            ('Generic', 'Measure throughput'),
            ('Native', 'Test the two fastest'),
            ('Selected split', 'Faster Native result'),
        ]
        count_labels = [f'{count} possible cuts', '5 cuts to test', '2 cuts to test', '1 selected cut']
    else:
        labels = [
            ('Graph-Vorauswahl', 'Kandidatenmenge + Bytes'),
            ('Generic', 'Durchsatz messen'),
            ('Native', 'Die zwei schnellsten prüfen'),
            ('Gewählter Split', 'Schnelleres Native-Ergebnis'),
        ]
        count_labels = [f'{count} mögliche Cuts', '5 Cuts testen', '2 Cuts testen', '1 gewählter Cut']
    fig, ax = plt.subplots(figsize=(4.9, 2.2) if figure_profile == 'dissertation' else (7.0, 2.48))
    fig.subplots_adjust(left=.005, right=.995, bottom=.015, top=.985)
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 2.75 if figure_profile == 'dissertation' else 2.48)
    ax.set_aspect('equal')
    ax.axis('off')
    centers = [.875, 2.625, 4.375, 6.125]
    palette = ['blue', 'orange', 'green', 'dark_gray']
    counts = spec_data['stage_counts']
    grid_bottom, step = (1.12 if figure_profile == 'dissertation' else .95), .038
    for i, (center, n, color_name, lines) in enumerate(zip(centers, counts, palette, labels)):
        color = style.PAPER_PALETTE[color_name]
        columns = 25 if i == 0 else n
        rows = math.ceil(n / columns)
        xs = [center + ((j % columns) - (columns - 1) / 2) * step for j in range(n)]
        ys = [grid_bottom + (j // columns) * step for j in range(n)]
        ax.scatter(xs, ys, s=1.8 if figure_profile == 'dissertation' else 3.2, marker='s', c=color, linewidths=0, zorder=2)
        label_y = grid_bottom + rows * step + .12
        ax.text(center, label_y, count_labels[i], ha='center', va='bottom', fontsize=9.5 if figure_profile == 'dissertation' else 10.5, fontweight='bold')
        if i == 0:
            ax.text(center, label_y + .22, model, ha='center', va='bottom', fontsize=9 if figure_profile == 'dissertation' else 9)
        pale = tuple(.94 + .06 * component for component in to_rgb(color))
        width, height, y = (1.52, .68, .10) if figure_profile == 'dissertation' else (1.43, .48, .14)
        ax.add_patch(FancyBboxPatch((center - width / 2, y), width, height,
                                   boxstyle='round,pad=0.025,rounding_size=0.045',
                                   linewidth=.8, edgecolor=color, facecolor=pale))
        title = lines[0]
        subtitle = lines[1]
        if figure_profile == 'dissertation':
            title = title.replace('Graph preselection', 'Graph\npreselection')
            subtitle = subtitle.replace('Pool selection + Bytes', 'Pool + boundary size').replace('Measure throughput', 'Universal runner').replace('Test the two fastest', 'Test top two')
        ax.text(center, y + (.45 if figure_profile == 'dissertation' else .32), title, ha='center', va='center', fontsize=9 if figure_profile == 'dissertation' else 9.5, fontweight='bold')
        ax.text(center, y + (.16 if figure_profile == 'dissertation' else .13), subtitle, ha='center', va='center', fontsize=8.3 if figure_profile == 'dissertation' else 7.4)
    for left, right in zip(centers[:-1], centers[1:]):
        ax.add_patch(FancyArrowPatch((left + .77, .38), (right - .77, .38), arrowstyle='-|>',
                                    mutation_scale=9, linewidth=.8,
                                    color=style.PAPER_PALETTE['dark_gray']))
    folder = output / 'artifacts' / language / 'figures'
    folder.mkdir(parents=True, exist_ok=True)
    for suffix in ('pdf', 'svg', 'png'):
        options = {'metadata': {'CreationDate': None, 'ModDate': None}} if suffix == 'pdf' else {}
        if suffix == 'svg':
            options = {'metadata': {'Date': None}}
        fig.savefig(folder / f'staged_selection_flow.{suffix}', dpi=220, **options)
    plt.close(fig)
    caption = ('Conceptual selection workflow, illustrated with the 615 graph boundaries of YOLO11l. '
               'The five Generic and two Native tests illustrate a budget after candidate-pool construction. '
               'The paired detector evaluation contains three supported cuts per group.' if language == 'en' else
               'Konzeptioneller Auswahlablauf am Beispiel der 615 Graphgrenzen von YOLO11l. '
               'Fünf Generic- und zwei Native-Tests veranschaulichen ein Budget nach Bildung der Kandidatenmenge. '
               'Die gepaarte Detektorauswertung umfasst drei unterstützte Schnitte je Gruppe.')
    write_json(folder / 'staged_selection_flow.json', dict(spec_data, language=language,
                                                          labels=labels, count_labels=count_labels, caption=caption))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paired-study', type=Path, default=DEFAULT_STUDY)
    parser.add_argument('--graph-metadata', type=Path, default=DEFAULT_GRAPH_METADATA,
                        help='Graph metadata supplying the YOLO11l size example in the workflow diagram.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--languages', nargs='+', choices=('en', 'de'), default=['en', 'de'])
    parser.add_argument('--verify', action='store_true', help='Check against the paired study direct graph curves.')
    parser.add_argument('--figure-profile', choices=('paper', 'dissertation'), default='paper',
                        help='Dissertation uses wider axes and larger type. Numerical data are unchanged.')
    args = parser.parse_args()
    source, output = args.paired_study.resolve(), args.output.resolve()
    if output == source or source in output.parents or output in source.parents:
        parser.error('Output must be separate from the paired input study.')
    output.mkdir(parents=True, exist_ok=True)
    sources = [source / 'data/quality_pairs.csv', source / 'analysis/complete_rankings.csv', source / 'analysis/aggregate_curves.csv']
    pairs, ranking = read_csv(sources[0]), read_csv(sources[1])
    details = evaluate(pairs, ranking)
    summaries = aggregate(details)
    validation = verify(details, summaries, read_csv(sources[2])) if args.verify else {'status': 'not_requested'}
    write_csv(output / 'data/group_budgets.csv', details)
    write_csv(output / 'data/summary.csv', summaries)
    write_json(output / 'data/summary.json', summaries)
    write_json(output / 'VALIDATION.json', validation)
    schematic = flow_spec(args.graph_metadata)
    for language in dict.fromkeys(args.languages):
        export_tables(output, summaries, details, language)
        export_figure(output, summaries, language, args.figure_profile)
        export_flow(output, schematic, language, args.figure_profile)
    groups = {(row['model'], row['setup']) for row in pairs}
    primary = [row for row in summaries if row['task'] == 'all' and row['method'] == 'bytes' and row['policy'] == 'cascade_native2' and row['k'] in PRIMARY_BUDGETS]
    info = ['# Graph–Generic–Native selection', '',
            f'This analysis reconstructs staged selection from {len(pairs)} quality-admissible paired cuts in {len(groups)} model–device groups.', '',
            'Order cuts by increasing boundary size, measure up to k cuts with Generic, then measure up to two Generic favourites with Native and retain the faster result.', '',
            '| Maximum Generic + Native tests per group | Exact Native winner | Mean Native throughput retained | Lowest retained throughput |',
            '|---|---:|---:|---:|']
    for row in primary:
        info.append(f"| {row['k']} + 2 | {row['exact_winners']}/{row['groups']} ({row['exact_winner_pct']:.1f}%) | {row['mean_retained_native_pct']:.2f}% | {100-row['max_loss_pct']:.2f}% |")
    worst = min((row for row in details if row['method'] == 'bytes' and row['k'] == 5
                 and row['policy'] == 'cascade_native2'), key=lambda row: row['retained_native_pct'])
    group = [row for row in pairs if (row['model'], row['setup']) == (worst['model'], worst['setup'])]
    best = min(group, key=lambda row: (-float(row['native_fps']), row['native_uid']))
    ordered = sorted((row for row in ranking if row['method'] == 'bytes'
                      and (row['model'], row['setup']) == (worst['model'], worst['setup'])),
                     key=lambda row: int(row['rank']))
    best_rank = next(row for row in ordered if row['native_uid'] == best['native_uid'])
    tied = [row for row in ordered if float(row['score']) == float(best_rank['score'])]
    assert [row['native_uid'] for row in tied] == sorted(row['native_uid'] for row in tied)
    extended = next(row for row in details if row['method'] == 'bytes' and row['k'] == 12
                    and row['policy'] == 'cascade_native2'
                    and (row['model'], row['setup']) == (worst['model'], worst['setup']))
    classifier = [row for row in summaries if row['task'] == 'classification' and row['method'] == 'bytes'
                  and row['policy'] == 'cascade_native2' and row['k'] in PRIMARY_BUDGETS]
    small = next(row for row in primary if row['k'] == 5)
    direct = next(row for row in summaries if row['task'] == 'all' and row['method'] == 'bytes'
                  and row['policy'] == 'direct_graph_all_native' and row['k'] == 5)
    info += ['', f"For classifier groups, the two budgets retain {classifier[0]['mean_retained_native_pct']:.2f}% and "
             f"{classifier[1]['mean_retained_native_pct']:.2f}% of the best Native throughput on average. "
             'Both budgets test all three paired cuts in each detector group and recover its Native winner.', '',
             f"The lowest five-test result is {worst['model']}/{worst['setup']}: {worst['selected_cut']} reaches "
             f"{worst['selected_native_fps']:.2f} FPS, compared with {float(best['native_fps']):.2f} FPS at {best['case']}. "
             f"The best cut has Bytes rank {best_rank['rank']}. Ranks {tied[0]['rank']}–{tied[-1]['rank']} share "
             f"the same {int(float(best_rank['score'])):,}-byte boundary, so the fixed configuration-identity tie order "
             'decides which equal-sized cut enters the five-cut shortlist. '
             f"With twelve Generic tests, the selected cut is {extended['selected_cut']} and retains {extended['retained_native_pct']:.2f}%. "
             'The rankings and per-group choices are preserved in the input rankings and [group results](data/group_budgets.csv).', '',
             f"Testing the same five-cut shortlists directly uses {direct['native_tests']} Native tests and retains "
             f"{direct['mean_retained_native_pct']:.2f}% mean throughput. The staged procedure uses {small['generic_tests']} "
             f"Generic and {small['native_tests']} Native tests for the same result. Fewer Native tests do not establish "
             'a reduction in total testing time. Existing Generic measurements can be reused before Native testing.']
    info += ['', 'The throughput percentage is the equally weighted mean of per-group ratios to the best measured Native cut. It is not the probability of finding that cut. Exact-winner counts are observed successes in this paired set.', '',
             'A group with fewer than k candidates tests all of them. The paired detector groups contain only three cuts. The broader Generic study remains a separate assessment of graph preselection on more detector candidates.', '',
             'The calculation uses previously measured FPS and quality-admissible candidates. Test counts exclude compilation, quality evaluation, fitting and engineering. No total search-time saving is measured.', '',
             'The primary figure compares one and two Native tests over Generic budgets 2–20. The data also include budget one. Non-monotonic changes are retained: a new Generic favourite can displace a stronger Native candidate from the two-test shortlist.', '',
             f'The workflow diagram uses the {schematic["graph_candidates"]} graph boundaries of YOLO11l and an illustrative budget of five Generic tests, two Native tests and one selected split. The bottom row shows the processing stages; equal-sized squares above it show the number of options. Candidate-pool construction and Bytes ranking precede Generic testing. This budget is an illustration, not a measured full-graph selection trial for YOLO11l.', '',
             '[English artifacts](artifacts/en/) · [German artifacts](artifacts/de/) · [Unrounded group data](data/group_budgets.csv) · [Aggregate results](data/summary.csv)', '',
             'Reproduce from the repository root:', '', '```sh',
             'python3 scripts/supplementary-studies/staged-selection/reproduce.py --output local-output/staged-selection --languages en de --verify',
             '```', '']
    (output / 'README.md').write_text('\n'.join(info), encoding='utf-8')
    manifest = dict(schema='staged-selection-v1', paired_cuts=len(pairs), groups=len(groups),
                    primary_method='bytes', primary_generic_budgets=list(PRIMARY_BUDGETS), maximum_native_tests=2,
                    languages=list(dict.fromkeys(args.languages)), figure_profile=args.figure_profile, fitting_performed=False, hardware_measurements=False,
                    inputs={str(path.relative_to(source)): sha(path) for path in sources},
                    schematic_source=schematic['source'],
                    generator_sha256=sha(Path(__file__)),
                    style_sha256=sha(REPO / 'scripts/split-inference/publication_mlsys_figures.py'),
                    files={str(path.relative_to(output)): sha(path) for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'MANIFEST.json'})
    write_json(output / 'MANIFEST.json', manifest)
    print(json.dumps(dict(status='complete', output=str(output), paired_cuts=len(pairs), groups=len(groups), validation=validation)))


if __name__ == '__main__':
    main()
