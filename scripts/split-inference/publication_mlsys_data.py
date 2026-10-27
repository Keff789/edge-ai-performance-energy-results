"""Numerical R22 publication views of the shared, current offline dataset.

Historical selector outcomes and the independent stage experiment retain their
own canonical inputs. This module uses only the standard library, never calls
LaTeX, and does not import a plotting library. Display rounding happens in the
table renderer; every exported numerical row keeps its original precision.
"""
from __future__ import annotations

import collections
import csv
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import tempfile

from build_paper_dataset import emit, positive, read, select_fastest_deployments, write

MODELS = ['mobilenet_v3_large', 'regnet_x_1_6gf', 'resnet50', 'yolo11l', 'yolo26m', 'yolo26s', 'yolov7_paper']
LABELS = dict(zip(MODELS, ['MobileNetV3-L', 'RegNet-X', 'ResNet-50', 'YOLO11l', 'YOLO26m', 'YOLO26s', 'YOLOv7']))
SETUPS = ['H8', 'H10', 'DeepX']
METHODS = ['cut_bytes_only', 'weighted_score', 'onnx_real_boundary_hardware_aware',
           'cycle_time_no_handover', 'stored_predicted_stream_fps', 'measured_generic_completion']
METHOD_LABELS = ['Smallest boundary bytes', 'Weighted graph score', 'H10 accelerator-fit score',
                 'Cycle without handover', 'Streaming-rate heuristic', 'Measured Generic completion']
CURRENT_INPUTS = ['results/split-inference/data/inputs/' + f for f in
                  ['cases.json', 'selected_evidence.json', 'energy_repeats.json']]
HISTORICAL = 'results/supplementary-studies/thesis20-ranking-20261005'
OVERLAY = 'results/supplementary-studies/mlsys-selection-20261007/inputs/analysis'
STAGE = 'results/supplementary-studies/stage-cost-composition'


def csv_rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def average(values):
    values = list(values)
    if not values or any(not isinstance(x, (int,float)) or not math.isfinite(x) for x in values):
        return None
    return math.fsum(values) / len(values)


def family(model):
    return 'classification' if model in MODELS[:3] else 'detection'


def quality_loss(row):
    """CPU-relative numeric quality; cached admission labels are not inputs."""
    q, reference = row.get('quality_value'), row.get('quality_reference_value')
    if not positive(reference) or not isinstance(q, (int, float)) or isinstance(q, bool) or not math.isfinite(q):
        return None
    return (reference - q) / reference


def eligible(row, tolerance=.05):
    loss = quality_loss(row)
    current_quality_admitted = ('quality' not in row.get('current_observation_metric_updates', [])
                                or row.get('normal_quality') is True)
    return current_quality_admitted and loss is not None and loss <= tolerance


def paired_rows(rows, tolerance=None):
    identity = lambda r: (r['model_id'], r['setup_id'], r['backend'], r['case_id'])
    generic = {identity(r): r for r in rows if r['kind'] == 'split' and r['runner'] == 'generic'}
    pairs = []
    for native in sorted(rows, key=lambda r: r['uid']):
        if native['kind'] != 'split' or native['runner'] != 'native':
            continue
        other = generic.get(identity(native))
        if other is None or not positive(native.get('fps')) or not positive(other.get('fps')):
            continue
        if tolerance is not None and not (eligible(native, tolerance) and eligible(other, tolerance)):
            continue
        pairs.append(dict(model=native['model_id'], setup=native['setup_id'], case=native['case_id'],
                          native_uid=native['uid'], generic_uid=other['uid'], native_fps=native['fps'],
                          generic_fps=other['fps'], native_mj_per_image=native['energy_mj_per_image'],
                          generic_mj_per_image=other['energy_mj_per_image'],
                          native_relative_quality_loss=quality_loss(native),
                          generic_relative_quality_loss=quality_loss(other)))
    return pairs


def selection_groups(pairs, model_order=MODELS):
    result = []
    for model in model_order:
        for setup in SETUPS:
            group = [r for r in pairs if (r['model'], r['setup']) == (model, setup)]
            if not group:
                continue
            selected = min(group, key=lambda r: (-r['generic_fps'], r['generic_uid']))
            best = min(group, key=lambda r: (-r['native_fps'], r['native_uid']))
            result.append(dict(model=model, setup=setup, candidate_count=len(group),
                               generic_choice=selected['case'], generic_choice_uid=selected['generic_uid'],
                               selected_native_uid=selected['native_uid'], native_best=best['case'],
                               native_best_uid=best['native_uid'], selected_native_fps=selected['native_fps'],
                               best_native_fps=best['native_fps'],
                               loss_pct=100 * (1 - selected['native_fps'] / best['native_fps']),
                               exact_hit=selected['native_fps'] == best['native_fps'],
                               candidate_uids=sorted(u for r in group for u in [r['native_uid'], r['generic_uid']])))
    return result


def expected_random(values, k):
    """Exact expectation and exact best-hit probability without replacement."""
    values = sorted(values)
    if not values or k <= 0:
        raise ValueError('A nonempty pool and positive shortlist are required')
    n, k = len(values), min(k, len(values))
    denominator = math.comb(n, k)
    expectation = math.fsum(float(Fraction(math.comb(i, k - 1), denominator)) * values[i]
                            for i in range(k - 1, n))
    tied = sum(v == values[-1] for v in values)
    no_hit = Fraction(math.comb(n - tied, k), denominator) if n - tied >= k else Fraction(0)
    return expectation, float(1 - no_hit), denominator


def budget_calculations(pairs, quality_pairs):
    group_rows, summaries = [], []
    for scope, pool in [('unrestricted', pairs), ('native_quality_5pct', quality_pairs)]:
        keys = list(dict.fromkeys((r['model'], r['setup']) for r in pool))
        for model, setup in keys:
            group = [r for r in pool if (r['model'], r['setup']) == (model, setup)]
            order = sorted(group, key=lambda r: (-r['generic_fps'], r['generic_uid']))
            best = min(group, key=lambda r: (-r['native_fps'], r['native_uid']))
            for k in [1, 3, 5]:
                shortlist = order[:k]
                chosen = min(shortlist, key=lambda r: (-r['native_fps'], r['native_uid']))
                random_fps, random_hit, count = expected_random([r['native_fps'] for r in group], k)
                group_rows.append(dict(scope=scope, family=family(model), model=model, setup=setup,
                    candidate_count=len(group), requested_k=k, actual_k=min(k, len(group)),
                    generic_shortlist=[r['generic_uid'] for r in shortlist],
                    selected_native_uid=chosen['native_uid'], native_best_uid=best['native_uid'],
                    generic_shortlist_native_choice=chosen['case'], native_best_case=best['case'],
                    native_best_fps=best['native_fps'], generic_best_native_fps=chosen['native_fps'],
                    generic_loss_pct=100 * (1 - chosen['native_fps'] / best['native_fps']),
                    generic_exact_hit=chosen['native_fps'] == best['native_fps'],
                    random_expected_best_fps=random_fps,
                    random_expected_loss_pct=100 * (1 - random_fps / best['native_fps']),
                    random_expected_exact_hit=random_hit, random_subset_count=count,
                    candidate_uids=sorted(u for r in group for u in [r['native_uid'], r['generic_uid']])))
        for fam in ['all', 'classification', 'detection']:
            for k in [1, 3, 5]:
                selected = [r for r in group_rows if r['scope'] == scope and r['requested_k'] == k
                            and (fam == 'all' or r['family'] == fam)]
                if not selected:
                    continue
                summaries.append(dict(scope=scope, family=fam, requested_k=k, groups=len(selected),
                    candidates=sum(r['candidate_count'] for r in selected),
                    actual_k_min=min(r['actual_k'] for r in selected), actual_k_max=max(r['actual_k'] for r in selected),
                    generic_mean_loss_pct=average(r['generic_loss_pct'] for r in selected),
                    random_mean_expected_loss_pct=average(r['random_expected_loss_pct'] for r in selected),
                    generic_exact_hits=sum(r['generic_exact_hit'] for r in selected),
                    random_expected_exact_hits=math.fsum(r['random_expected_exact_hit'] for r in selected)))
    return group_rows, summaries


def advantage_calculations(rows):
    details, summaries = [], []
    for tolerance in [None, .01, .02, .05]:
        gate = 'unrestricted' if tolerance is None else 'quality_' + str(int(100 * tolerance)) + 'pct'
        pool = rows if tolerance is None else [r for r in rows if eligible(r, tolerance)]
        fulls = [r for r in pool if r['kind'] == 'full']
        native = [r for r in pool if r['kind'] == 'split' and r['runner'] == 'native']
        selected = []
        for split in native:
            local = [r for r in fulls if (r['model_id'], r['physical_host']) ==
                     (split['model_id'], split['physical_host']) and positive(r.get('fps'))]
            fast = min(local, key=lambda r: (-r['fps'], r['uid'])) if local else None
            energies = [r for r in local if positive(r.get('energy_j_per_image'))]
            low = min(energies, key=lambda r: (r['energy_j_per_image'], r['uid'])) if energies else None
            faster = split['fps'] > fast['fps'] if fast else None
            lower = split['energy_j_per_image'] < fast['energy_j_per_image'] if fast and positive(fast['energy_j_per_image']) and positive(split['energy_j_per_image']) else None
            selected.append(dict(gate=gate, model=split['model_id'], setup=split['setup_id'],
                split_uid=split['uid'], fastest_full_uid=fast['uid'] if fast else None,
                minimum_energy_full_uid=low['uid'] if low else None,
                faster_than_fastest_full=faster, lower_energy_than_fastest_full=lower,
                both_vs_fastest_full=(faster and lower) if faster is not None and lower is not None else None,
                lower_energy_than_minimum_full=split['energy_j_per_image'] < low['energy_j_per_image'] if low and positive(split['energy_j_per_image']) else None))
        details += selected
        summaries.append(dict(gate=gate, native_candidates=len(native), admissible_fulls=len(fulls),
            **{key: sum(r[key] is True for r in selected) for key in
               ['faster_than_fastest_full', 'lower_energy_than_fastest_full', 'both_vs_fastest_full', 'lower_energy_than_minimum_full']}))
    return details, summaries


def repeat_ranges(rows, energy_repeats, selected_uids):
    by_uid = {r['uid']: r for r in rows}
    result = []
    for uid in dict.fromkeys(selected_uids):
        row = by_uid[uid]
        performance = row.get('fps_samples') or []
        energy = sorted([r for r in energy_repeats if r['uid'] == uid], key=lambda r: r['repeat'])
        if performance:
            assert all(positive(x) for x in performance)
            assert math.isclose(statistics.median(performance), row['fps'], rel_tol=1e-12)
        values = []
        for repeat in energy:
            assert repeat.get('source_sha256'), ('unbound energy repetition', uid)
            images = repeat.get('completed_images', repeat.get('completed_tasks'))
            assert positive(images) and positive(repeat['energy_j'])
            value = repeat['energy_j'] / images
            assert math.isclose(value, repeat['j_per_image'], rel_tol=1e-12)
            values.append(1000 * value)
        assert len({(r['repeat'], r['source_sha256']) for r in energy}) == len(energy)
        if values:
            assert math.isclose(average(values), row['energy_mj_per_image'], rel_tol=1e-12), uid
        result.append(dict(uid=uid, model=row['model_id'], setup=row['setup_id'], backend=row['backend'],
            case=row['case_id'], fps=row['fps'], energy_mj_per_image=row['energy_mj_per_image'],
            fps_repeats=performance, energy_repeats_mj_per_image=values,
            fps_min=min(performance) if performance else None, fps_max=max(performance) if performance else None,
            energy_min_mj_per_image=min(values) if values else None,
            energy_max_mj_per_image=max(values) if values else None,
            performance_generation=row['performance_generation'], energy_generation=row['energy_generation'],
            performance_source_sha256=row['performance_source_sha256'],
            aggregate_energy_source_sha256=row['energy_source_sha256'],
            energy_repeat_source_bindings=[dict(repeat=r['repeat'], source_sha256=r['source_sha256'],
                                               campaign=r.get('campaign'), source=r.get('source')) for r in energy],
            range_semantics='observed minimum and maximum; independent performance and energy runs; not confidence intervals'))
    return result


def historical_calculations(repo):
    """Adapt the historical report-overlay generator's frozen-choice semantics.

    Static selector choices are the existing THESIS20 experiment, not a refit
    against A4. Outcomes are newly calculated from original per-case rates and
    matched energy records; the YOLOv7 report overlay has no matching energy.
    """
    inputs = [OVERLAY + '/evidence/tables/rank_cases.csv', OVERLAY + '/reported_update/reported_results.csv',
              HISTORICAL + '/tables/method_groups.csv', HISTORICAL + '/source/deep_analysis/tables/energy_cases.csv']
    cases = csv_rows(repo / inputs[0])
    reported = {(r['model'], r['setup'], r['case']): r for r in csv_rows(repo / inputs[1])
                if r['configuration_type'] == 'split'}
    for row in cases:
        key = row['model_id'], row['setup_id'], row['case_id']
        row['native_fps'] = float(row['native_completed_task_fps'])
        row['native_source'] = 'archived_completed_campaign'
        if key in reported:
            source = reported[key]
            reps = [float(source['fps_' + str(i)]) for i in [1, 2, 3]]
            assert math.isclose(statistics.median(reps), float(source['fps_median']), abs_tol=5e-7)
            row['native_fps'] = float(source['fps_median'])
            row['native_source'] = 'supplied_report_overlay_20261006'
            row['native_report_source_sha256'] = source['source_sha256']
    choices = [r for r in csv_rows(repo / inputs[2]) if r['cohort'] == 'augmented'
               and r['tier'] == 'technical' and r['method'] in METHODS and r['status'] == 'ok']
    energies = {(r['model_id'], r['setup_id'], r['case_id']): r for r in csv_rows(repo / inputs[3])
                if r['execution_mode'] == 'native_split'}
    groups = []
    for selected in choices:
        model, setup = selected['model_id'], selected['setup_id']
        pool = [r for r in cases if (r['model_id'], r['setup_id']) == (model, setup)
                and r['eligible_for_technical_transfer'] == 'True']
        indexed = {r['case_id']: r for r in pool}
        assert set(indexed) == set(json.loads(selected['candidate_ids']))
        chosen = indexed[selected['selected_case']]
        best = max(r['native_fps'] for r in pool)
        if selected['method'] == 'measured_generic_completion':
            assert float(chosen['generic_completed_task_fps']) == max(float(r['generic_completed_task_fps']) for r in pool)
        energy = None
        energy_uids = []
        if model != 'yolov7_paper':
            matched = [energies[(model, setup, r['case_id'])] for r in pool]
            selected_energy = float(energies[(model, setup, chosen['case_id'])]['j_per_task_mean'])
            energy = selected_energy / min(float(r['j_per_task_mean']) for r in matched) - 1
            energy_uids = [r['case_uid'] for r in matched]
        groups.append(dict(model_id=model, setup_id=setup, method=selected['method'], n=len(pool),
            cohort='augmented', tier='technical', selected_case=chosen['case_id'],
            native_best_case=min(r['case_id'] for r in pool if r['native_fps'] == best),
            selected_native_fps=chosen['native_fps'], native_best_fps=best,
            top1_hit_tie_aware=chosen['native_fps'] == best, L_R=1 - chosen['native_fps'] / best,
            energy_excess_fraction=energy, candidate_ids=sorted(indexed), energy_input_uids=energy_uids,
            performance_basis=chosen['native_source'], source_uid='historical|' + model + '|' + setup + '|' + chosen['case_id'],
            candidate_uids=['historical|' + model + '|' + setup + '|' + case for case in sorted(indexed)],
            selector_basis='frozen THESIS20 selection; outcomes recomputed; no current A4 graph-identity claim'))
    groups.sort(key=lambda r: (MODELS.index(r['model_id']), SETUPS.index(r['setup_id']), METHODS.index(r['method'])))
    summaries = []
    for method, label in zip(METHODS, METHOD_LABELS):
        selected = [r for r in groups if r['method'] == method]
        energies = [r['energy_excess_fraction'] for r in selected if r['energy_excess_fraction'] is not None]
        summaries.append(dict(method=method, label=label, groups=len(selected),
            all_hits=sum(r['top1_hit_tie_aware'] for r in selected),
            classification_hits=sum(r['top1_hit_tie_aware'] for r in selected if family(r['model_id']) == 'classification'),
            detection_hits=sum(r['top1_hit_tie_aware'] for r in selected if family(r['model_id']) == 'detection'),
            median_loss_pct=100 * statistics.median(r['L_R'] for r in selected),
            mean_loss_pct=100 * average(r['L_R'] for r in selected), energy_groups=len(energies),
            mean_energy_excess_pct=100 * average(energies)))
    return groups, summaries, inputs


def stage_calculations(repo):
    script = repo / 'scripts/supplementary-studies/stage-cost-composition'
    spec = importlib.util.spec_from_file_location('mlsys_stage_analysis', script / 'analyse_stage_cost_test.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script))
    try:
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='mlsys-stage-') as temporary:
            copied = Path(temporary) / 'inputs'
            shutil.copytree(repo / STAGE / 'inputs', copied)
            summary = module.analyse(copied, copied / 'derived')
    finally:
        sys.path.remove(str(script))
    assert not summary['errors'], summary['errors']
    rows = []
    for case in summary['cases']:
        metrics = case['metrics']
        rows.append(dict(case_id=case['case_id'], config_id=case['config_id'], cut=case['candidate_id'],
            block_count=case['n'], prefix_fps=metrics['fps_P_core']['median'],
            consumer_fps=metrics['fps_C_core']['median'], pipeline_fps=metrics['fps_PC_core']['median'],
            absolute_error_pct_median=metrics['absolute_error_pct']['median'],
            stage_generation='stage_cost_composition_20261014',
            label=('ResNet/DX ' if case['case_id'].startswith('deepx_') else 'RegNet/H10 ') + case['candidate_id']))
    return rows, summary


def tex_escape(value):
    return (str(value).replace('\\', r'\textbackslash{}').replace('_', r'\_').replace('%', r'\%')
            .replace('&', r'\&').replace('<=', r'$\leq$').replace('>=', r'$\geq$'))


def table_view(rows, columns, caption, label, star=True):
    """Columns are (key, heading, format); numerical payload remains unrounded."""
    def display(row, key, form):
        value = row.get(key)
        if value is None:
            return 'NA'
        text = format(value, form) if form else str(value)
        if key.endswith('_fps') and row.get(key[:-4] + '_passes_5pct') is False:
            text += '*'
        return text
    lines = ['# ' + label.removeprefix('tab:').replace('-', ' ').title(), '', caption, '',
             '| ' + ' | '.join(h for _, h, _ in columns) + ' |',
             '| ' + ' | '.join('---:' if f else '---' for _, _, f in columns) + ' |']
    env, width = ('table*', r'\textwidth') if star else ('table', r'\columnwidth')
    align = ' '.join('r' if f else 'l' for _, _, f in columns)
    def heading(value):
        if value in ['F_P','F_C','F_PC','R_h','R_g']:
            stem, sub = value.split('_')
            return '$' + stem + '_{' + sub + '}$'
        if value.endswith(' mJ/image'):
            return r'\shortstack{' + tex_escape(value[:-9]) + r'\\mJ/image}'
        return tex_escape(value)
    tex = [r'\begin{' + env + '}[t]', r'\centering', r'\caption{' + tex_escape(caption) + '}',
           r'\label{' + label + '}', r'\begingroup\small\setlength{\tabcolsep}{3pt}',
           r'\begin{tabular*}{' + width + r'}{@{\extracolsep{\fill}}' + align + '@{}}', r'\toprule',
           ' & '.join(heading(h) for _, h, _ in columns) + r' \\', r'\midrule']
    for row in rows:
        values = [display(row, key, form) for key, _, form in columns]
        lines.append('| ' + ' | '.join(v.replace('|', r'\|') for v in values) + ' |')
        tex.append(' & '.join(tex_escape(v) for v in values) + r' \\')
    tex += [r'\bottomrule', r'\end{tabular*}', r'\endgroup', r'\end{' + env + '}']
    return '\n'.join(lines) + '\n', '\n'.join(tex) + '\n'


def build(repo_root, broad_output, profile_output):
    repo, broad, output = map(Path, [repo_root, broad_output, profile_output])
    output.mkdir(parents=True, exist_ok=True)
    rows = read(broad / 'data/PAPER_DATASET.json')
    current_observations = (broad/'data/current_observation_binding.json').is_file()
    config = read(broad / 'data/analysis_config.json')
    models = config['model_order']
    index = {r['uid']: r for r in rows}
    admitted = [r for r in rows if eligible(r)]
    winners = select_fastest_deployments(admitted, models)
    broad_winners = select_fastest_deployments(rows, models)
    pairs, quality_pairs = paired_rows(rows), paired_rows(rows, .05)
    groups, quality_groups = selection_groups(pairs, models), selection_groups(quality_pairs, models)
    budget_groups, budgets = budget_calculations(pairs, quality_pairs)
    advantage_rows, advantages = advantage_calculations(rows)
    fulls = [r for r in rows if r['kind'] == 'full']
    native = [r for r in rows if r['kind'] == 'split' and r['runner'] == 'native']
    assets = {}

    def publish(stem, label, data, columns, caption, input_uids, input_files=CURRENT_INPUTS,
                generation=None, star=True):
        path = output / 'tables' / stem
        emit(path, data)
        md, tex = table_view(data, columns, caption, label, star)
        path.with_suffix('.md').write_text(md)
        path.with_suffix('.tex').write_text(tex)
        assets[label] = dict(reference_file='sections/' + stem + '.tex',
            outputs=['tables/' + stem + '.' + ext for ext in ['csv', 'json', 'md', 'tex']],
            input_uids=sorted(set(input_uids)), input_files=list(input_files),
            data_generation=generation or config['source_generation'],
            generator='scripts/split-inference/publication_mlsys_data.py',
            verification='UID joins, independent numerical reference checks, table render and deterministic byte comparison')

    def full_label(record):
        return 'TRT (' + record['setup_id'] + ')' if record['backend'] == 'native_full_tensorrt' else record['setup_id']

    winner_rows = []
    for r in winners:
        split, full = r['split_record'], r['global_full_record']
        winner_rows.append(dict(model=r['model'], label=LABELS.get(r['model'], r['model']),
            split_uid=r['split_uid'], full_uid=r['global_full_uid'], host_full_uid=r['host_full_uid'],
            split_setup=r['split_setup'], split_case=r['split_case'], split_runner=r['split_runner'],
            split_label=(r['split_runner'].title()+' ' if current_observations else '') + r['split_setup'] + '/' + r['split_case'], full_label=full_label(full),
            split_fps=r['split_fps'], full_fps=r['global_full_fps'],
            split_mj=r['split_mj_per_image'], full_mj=r['global_full_mj_per_image'],
            split_quality=100 * split['quality_value'], full_quality=100 * full['quality_value'],
            split_quality_loss=100 * quality_loss(split), full_quality_loss=100 * quality_loss(full),
            R_global=r['R_global'], R_host=r['R_host'], G_global=r['G_global'], G_host=r['G_host'],
            throughput_gain_pct=100 * (r['R_global'] - 1), energy_change_pct=r['delta_E_global_pct'],
            energy_ratio=r['energy_ratio_global'], host_full_label=full_label(r['host_full_record']),
            host_full_fps=r['host_full_fps'], quality_difference_pp=100 * (split['quality_value'] - full['quality_value'])))
    current_uids = [r['uid'] for r in rows]
    winner_uids = [u for r in winner_rows for u in [r['split_uid'], r['full_uid'], r['host_full_uid']]]
    publish('best_cases_table', 'tab:best-cases', winner_rows,
        [('label','Model',''),('full_label','Fastest Full',''),('full_fps','FPS','.0f'),('split_label','Fastest split',''),
         ('split_fps','FPS','.0f'),('throughput_gain_pct','FPS gain (%)','+.1f'),('energy_change_pct','Energy change (%)','+.1f')],
        'Fastest observed Full and split across all setups among configurations with at most 5% numeric CPU-relative quality loss. '
        'Changes use unrounded values. Energy belongs to these same throughput-selected configurations; negative energy change means less energy per image.', current_uids)
    publish('r16_winner_energy_details', 'tab:winner-energy', winner_rows,
        [('label','Model',''),('full_label','Full',''),('full_mj','mJ/image','.2f'),('split_label','Split',''),
         ('split_mj','mJ/image','.2f'),('energy_change_pct','Energy change (%)','+.1f')],
        'Absolute calibrated system energy of the same global throughput-selected Full and split. These are actual configurations, not host averages.', winner_uids)
    publish('fastest_split_baselines','tab:fastest-split-baselines',winner_rows,
        [('label','Model',''),('split_label','Selected split',''),('split_fps','FPS','.0f'),('host_full_label','Host Full',''),
         ('host_full_fps','FPS','.0f'),('full_label','Global Full',''),('full_fps','FPS','.0f'),('R_host','R_h','.2f'),('R_global','R_g','.2f')],
        'The same selected split with two Full references. R_h uses its physical host; R_g uses the globally fastest Full. '
        'The split is not reselected by relative gain. The comparison describes a baseline choice, not an optimization step.', current_uids)
    full_overview, full_details = [], []
    for model in models:
        model_fulls = [r for r in fulls if r['model_id'] == model]
        trt = [r for r in model_fulls if r['backend'] == 'native_full_tensorrt']
        summary = dict(model=model, label=LABELS.get(model, model), trt_fps=average(r['fps'] for r in trt),
                       trt_mj=average(r['energy_mj_per_image'] for r in trt), trt_uids=[r['uid'] for r in trt])
        for setup in SETUPS:
            local = [r for r in model_fulls if r['setup_id'] == setup]
            accel = next(r for r in local if r['backend'] != 'native_full_tensorrt')
            tensor = next(r for r in local if r['backend'] == 'native_full_tensorrt')
            summary.update({setup + '_fps': accel['fps'], setup + '_mj': accel['energy_mj_per_image'],
                            setup + '_uid': accel['uid'], setup + '_passes_5pct': eligible(accel)})
            full_details.append(dict(model=model, label=LABELS.get(model, model), setup=setup,
                accel_uid=accel['uid'], trt_uid=tensor['uid'], accel_fps=accel['fps'],
                accel_mj=accel['energy_mj_per_image'], accel_quality=100 * accel['quality_value'],
                accel_passes_5pct=eligible(accel), trt_fps=tensor['fps'], trt_mj=tensor['energy_mj_per_image'],
                trt_quality=100 * tensor['quality_value'], trt_passes_5pct=eligible(tensor)))
        full_overview.append(summary)
    publish('full_performance_table', 'tab:full-performance', full_overview,
        [('label','Model',''),('trt_fps','TRT FPS','.0f'),('trt_mj','TRT mJ/image','.2f')] +
        [(s + '_' + field, s + (' FPS' if field == 'fps' else ' mJ/image'), '.0f' if field == 'fps' else '.2f')
         for s in SETUPS for field in ['fps','mj']],
        'Full throughput and calibrated system energy. TensorRT columns are arithmetic means of the three host-specific FPS medians and mean energies. '
        'Winner comparisons use concrete Full configurations. * marks more than 5% numeric CPU-relative quality loss. '
        'Numeric quality eligibility is retained for every actual Full in the CSV/JSON.', [r['uid'] for r in fulls])
    publish('current_full_details','tab:current-full-details',full_details,
        [('label','Model',''),('setup','Host',''),('accel_fps','Accel. FPS','.0f'),('accel_mj','mJ/image','.2f'),
         ('accel_quality','q (%)','.2f'),('trt_fps','TRT FPS','.0f'),('trt_mj','mJ/image','.2f'),('trt_quality','q (%)','.2f')],
        'All actual Full alternatives on each host. Quality q is Top1 for classifiers and COCO AP50:95 for detectors, in percent. '
        '* marks more than 5% numeric CPU-relative quality loss.', [r['uid'] for r in fulls])
    quality_rows = [dict(r, comparison='global throughput winners') for r in winner_rows]
    vendor = []
    for setup in SETUPS:
        full = next(r for r in fulls if r['model_id'] == 'mobilenet_v3_large' and r['setup_id'] == setup and r['backend'] != 'native_full_tensorrt')
        split = next(r for r in native if r['model_id'] == 'mobilenet_v3_large' and r['setup_id'] == setup and r['case_id'] == 'b027')
        row = dict(setup=setup, full_uid=full['uid'], split_uid=split['uid'], full_quality=100 * full['quality_value'],
                   split_quality=100 * split['quality_value'], quality_difference_pp=100 * (split['quality_value'] - full['quality_value']),
                   reference_quality=100 * split['quality_reference_value'], quality_metric=split['quality_metric'],
                   quality_n=split['quality_n'])
        vendor.append(row)
        if setup in ['H8','H10']:
            quality_rows.append(dict(row, label='MobileNet / ' + setup, comparison='same-host Hailo Full'))
    publish('r14_winner_quality','tab:winner-quality',quality_rows,
        [('label','Model / setup',''),('full_quality','Full q (%)','.2f'),('split_quality','Split q (%)','.2f'),('quality_difference_pp','Delta q (pp)','+.2f')],
        'Top1 for classifiers and AP50:95 for detectors. The first rows use global throughput winners admitted by the 5% CPU-relative quality rule. '
        'The final MobileNet rows compare b027 to Hailo Fulls on the same host; those Fulls fail the rule. Direct quality differences are split minus the stated Full.',
        winner_uids + [u for r in vendor for u in [r['full_uid'],r['split_uid']]], star=False)
    publish('vendor_quality_recovery_table','tab:vendor-quality',vendor,
        [('setup','Host',''),('full_quality','Accel. Full (%)','.2f'),('split_quality','Split b027 (%)','.2f'),('quality_difference_pp','Recovered (pp)','+.2f')],
        f"MobileNetV3 Top1 on the same {vendor[0]['quality_n']:,} images, CPU ONNX reference {vendor[0]['reference_quality']:.2f}%. Current A4-bound b027 with TensorRT suffix. "
        'This current view preserves the separate historical vendor table and its older source generation.',
        [u for r in vendor for u in [r['full_uid'],r['split_uid']]], star=False)
    publish('current_quality_highlights','tab:current-quality',winner_rows,
        [('label','Model',''),('split_label','Split',''),('split_quality','q (%)','.2f'),('split_quality_loss','Loss (%)','.2f'),
         ('full_label','Full',''),('full_quality','q (%)','.2f'),('full_quality_loss','Loss (%)','.2f')],
        'Numeric CPU-relative quality loss of the same global throughput winners. Negative loss is a higher point estimate, not a significant improvement.', winner_uids)
    top = read(broad / 'tables/table3_top2_native.json')
    top_rows = [dict(r, label=LABELS.get(r['model'],r['model']), split_label=r['setup'] + '/' + r['case']) for r in top]
    publish('current_top2_relative','tab:current-top2-relative',top_rows,
        [('label','Model',''),('rank','Rank','d'),('split_label','Setup/cut',''),('baseline_fps','Full FPS','.0f'),('split_fps','Split FPS','.0f'),
         ('speedup','R_h','.2f'),('split_mj_per_image','mJ/image','.2f'),('energy_gain_same_full','G','.2f')],
        'Two Native splits per model with the largest relative throughput gain over the fastest Full on the same host. '
        'This separately retained broad selection is unfiltered and differs from absolute-FPS selection. G uses energy of that same Full.', current_uids)
    yolov7 = [dict(r) for r in pairs if r['model'] == 'yolov7_paper']
    yolov7.sort(key=lambda r: (SETUPS.index(r['setup']),r['case']))
    publish('yolov7_completed_table','tab:yolov7-completion',yolov7,
        [('setup','Host',''),('case','Cut',''),('generic_fps','G FPS','.0f'),('native_fps','N FPS','.0f'),('native_mj_per_image','N mJ/image','.2f')],
        'YOLOv7 deployment comparison on the measured cuts. Generic and Native performance are stored cohort medians; energy is Native calibrated system energy.',
        [u for r in yolov7 for u in [r['native_uid'],r['generic_uid']]], star=False)
    display_groups = [dict(r,label=LABELS.get(r['model'],r['model'])) for r in groups]
    publish('current_selection_groups','tab:current-selection-groups',display_groups,
        [('label','Model',''),('setup','Host',''),('candidate_count','n','d'),('generic_choice','G choice',''),('native_best','N best',''),
         ('selected_native_fps','Selected FPS','.0f'),('best_native_fps','Best FPS','.0f'),('loss_pct','Loss (%)','.2f')],
        'Unfiltered Generic-to-Native selection, one model/setup group per row. Loss is Native throughput lost by choosing the Generic winner. Choices use unrounded FPS.',
        [u for r in groups for u in r['candidate_uids']])
    advantage_display = [dict(r, eligibility='All measured' if r['gate']=='unrestricted' else
                              '<=' + r['gate'].split('_')[1].replace('pct','%') + ' loss') for r in advantages]
    publish('r14_quality_advantages','tab:quality-advantages',advantage_display,
        [('eligibility','Eligibility',''),('native_candidates','Native cuts','d'),('admissible_fulls','Fulls','d'),
         ('faster_than_fastest_full','Faster','d'),('lower_energy_than_fastest_full','Less energy','d'),
         ('both_vs_fastest_full','Both','d'),('lower_energy_than_minimum_full','Below min. Full','d')],
        'Same-host advantages after filtering both Native splits and Full alternatives by recomputed CPU-relative quality loss. '
        'Fastest and minimum-energy Fulls are reselected within each admitted set. Faster and less energy use the same fastest Full.', current_uids)
    budget_display = [dict(r,eligibility='All measured' if r['scope']=='unrestricted' else '<=5% loss') for r in budgets]
    publish('r14_budget_details','tab:budget-details',budget_display,
        [('eligibility','Eligibility',''),('family','Family',''),('groups','Groups','d'),('candidates','Cuts','d'),('requested_k','k','d'),
         ('generic_mean_loss_pct','G loss (%)','.2f'),('random_mean_expected_loss_pct','U loss (%)','.2f'),
         ('generic_exact_hits','G hits','d'),('random_expected_exact_hits','U hits','.3f')],
        'Finite-budget selection: Generic orders candidates, then the fastest of k measured Native candidates is retained. '
        'Uniform sampling uses exact subset probabilities without replacement. Group means have equal weight. Budgets are capped at candidate count; '
        'therefore a requested k=5 in a three-cut detection group still measures three candidates. Quality eligibility is retrospective.', current_uids)
    case_rows = []
    for kind, backend, case, label in [('full','native_full_hailo8','full','Hailo8 Full'),
                                      ('full','native_full_tensorrt','full','TensorRT Full'),
                                      ('split','hailo8_to_trt','b066','Split b066')]:
        r = next(r for r in rows if (r['model_id'],r['setup_id'],r['runner'],r['kind'],r['backend'],r['case_id']) ==
                 ('yolov7_paper','H8','native',kind,backend,case))
        case_rows.append(dict(configuration=label,uid=r['uid'],model=r['model_id'],setup=r['setup_id'],runner=r['runner'],case=r['case_id'],
            throughput_fps=r['fps'],system_energy_mj_per_image=r['energy_mj_per_image'],
            coco_ap_50_95_percent=100*r['quality_value'],reference_coco_ap_50_95_percent=100*r['quality_reference_value'],
            relative_quality_loss=quality_loss(r),passes_5pct=eligible(r),quality_n=r['quality_n'],
            normal_performance_claim=r['normal_performance_claim'],energy_claim=r['energy_claim'],
            quality_bound_result_sha256=r['quality_bound_result_sha256']))
    repeat_uids = [u for r in winner_rows for u in [r['full_uid'],r['split_uid']]] + [r['uid'] for r in case_rows[:2]]
    ranges = repeat_ranges(rows,read(broad / 'tables/energy_repeats.json'),repeat_uids)
    for r in ranges:
        r['label'] = LABELS.get(r['model'],r['model']) + ' / ' + (
            'TRT ('+r['setup']+')' if r['backend']=='native_full_tensorrt' else
            r['setup']+' Full' if r['case']=='full' else r['setup']+'/'+r['case'])
        r['fps_range'] = 'NA' if r['fps_min'] is None else f"{r['fps_min']:.0f}--{r['fps_max']:.0f}"
        r['energy_range'] = 'NA' if r['energy_min_mj_per_image'] is None else f"{r['energy_min_mj_per_image']:.2f}--{r['energy_max_mj_per_image']:.2f}"
    publish('r21_winner_repeat_ranges','tab:winner-repeat-ranges',ranges,
        [('label','Deployment',''),('fps_range','FPS',''),('energy_range','mJ/image','')],
        'Observed repetition minima and maxima for global winners and additional YOLOv7/H8 Full references. '
        'Performance and energy use separate runs; these ranges are not confidence intervals. The original Refresh16 YOLO26s/H8 b021 repetitions complete the R22 extract gap.', repeat_uids,star=False)
    historical_groups,historical_summary,historical_inputs = historical_calculations(repo)
    history_denominators = {fam:len({(r['model_id'],r['setup_id']) for r in historical_groups
                                     if fam=='all' or family(r['model_id'])==fam})
                            for fam in ['all','classification','detection']}
    publish('ranking_tables','tab:selectors',historical_summary,
        [('label','Selector',''),('all_hits','All /'+str(history_denominators['all']),'d'),
         ('classification_hits','Class. /'+str(history_denominators['classification']),'d'),
         ('detection_hits','Detect. /'+str(history_denominators['detection']),'d'),
         ('median_loss_pct','Median loss (%)','.2f'),('mean_loss_pct','Mean loss (%)','.2f'),
         ('mean_energy_excess_pct','Energy /'+str(historical_summary[0]['energy_groups'])+' (%)','.2f')],
        'Historical six-selector experiment on fixed candidate sets. YOLOv7 uses historical Generic and the reported Native campaign; '
        'other models retain archived measurements. Frozen selector choices are not refitted. Energy uses matched groups excluding YOLOv7. Every group has equal weight.',
        [u for r in historical_groups for u in r['candidate_uids']+r['energy_input_uids']],historical_inputs,
        generation='THESIS20_20261005_with_reported_YOLOv7_20261006')
    stage_rows,stage_summary = stage_calculations(repo)
    publish('stage_cost_summary','tab:stage-costs',stage_rows,
        [('label','Model/cut',''),('prefix_fps','F_P','.0f'),('consumer_fps','F_C','.0f'),('pipeline_fps','F_PC','.0f'),('absolute_error_pct_median','Error (%)','.2f')],
        'Independent four-cut stage-cost experiment. Median producer, consumer and pipeline completion rates over three blocks. '
        'Prediction is min(F_P,F_C); error is the median blockwise absolute percentage error. This cohort is separate from deployment and scheduling data.',
        [r['config_id'] for r in stage_rows],
        [str(p.relative_to(repo)) for p in sorted((repo / STAGE / 'inputs').rglob('*.json'))],
        generation='stage_cost_composition_20261014',star=False)
    quality_audit=[dict(uid=r['uid'],model=r['model_id'],setup=r['setup_id'],kind=r['kind'],runner=r['runner'],
                        quality_value=r.get('quality_value'),quality_reference_value=r.get('quality_reference_value'),
                        recomputed_relative_loss=quality_loss(r),passes_5pct=eligible(r)) for r in rows]
    for name,data in [('numeric_quality_audit',quality_audit),('current_pairs',pairs),('quality_pairs',quality_pairs),
                      ('quality_selection_groups',quality_groups),('budget_groups',budget_groups),('native_advantage_cases',advantage_rows),
                      ('historical_selector_groups',historical_groups)]:
        emit(output / 'data' / name,data)
    summary=dict(source_generation=config['source_generation'],configurations=len(rows),quality_eligible=len(admitted),
        eligible_native_splits=sum(r['kind']=='split' and r['runner']=='native' for r in admitted),
        eligible_generic_splits=sum(r['kind']=='split' and r['runner']=='generic' for r in admitted),
        eligible_fulls=sum(r['kind']=='full' for r in admitted),
        paired_candidates=len(pairs),quality_paired_candidates=len(quality_pairs),quality_groups=len(quality_groups),
        quality_exact_hits=sum(r['exact_hit'] for r in quality_groups),quality_mean_loss_pct=average(r['loss_pct'] for r in quality_groups),
        global_winners_unchanged_at_5pct=[(r['split_uid'],r['global_full_uid']) for r in winners]==[(r['split_uid'],r['global_full_uid']) for r in broad_winners],
        globally_faster_models=sum(r['R_global']>1 for r in winners),
        globally_faster_and_less_energy_models=sum(r['R_global']>1 and r['energy_ratio_global'] is not None
                                                  and r['energy_ratio_global']<1 for r in winners),
        fps_repeat_count=sum(len(r['fps_repeats']) for r in ranges),energy_repeat_count=sum(len(r['energy_repeats_mj_per_image']) for r in ranges),
        family_selection={fam:dict(groups=len(selected),pairs=sum(r['candidate_count'] for r in selected),
            exact_hits=sum(r['exact_hit'] for r in selected),mean_loss_pct=average(r['loss_pct'] for r in selected))
            for fam in ['classification','detection'] for selected in [[r for r in quality_groups if family(r['model'])==fam]]})
    write(output/'data/summary.json',summary)
    return dict(assets=assets,summary=summary,rows=rows,quality_rows=admitted,winners=winners,unfiltered_winners=broad_winners,
        selection_groups=groups,quality_selection_groups=quality_groups,pairs=pairs,quality_pairs=quality_pairs,
        budget_groups=budget_groups,budget_summary=budgets,yolov7_case=case_rows,
        resnet_h8=[r for r in rows if r['model_id']=='resnet50' and r['setup_id']=='H8' and r['runner']=='native'],
        historical_groups=historical_groups,stage_summary=stage_summary,source_generation=config['source_generation'],
        figure_input_files={name:(historical_inputs if name=='selector_loss_heatmap' else CURRENT_INPUTS)
                           for name in ['fastest_split_baseline_comparison','fastest_deployment_tradeoff',
                                        'yolov7_h8_case','resnet_h8_energy_current','quality_generic_selection_loss',
                                        'current_generic_selection_loss','selector_loss_heatmap']},
        dataset_source='results/split-inference/data/PAPER_DATASET.json')
