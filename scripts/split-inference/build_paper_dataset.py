#!/usr/bin/env python3
"""Broad Native A4 extension of the frozen Twix/Revision-3 offline analysis.

Keeps the existing JSON/CSV/group/dist/Student-t conventions and THESIS20
quantile implementation. Selection, pairing and baseline choice are calculated
once here and shared by tables, figures and report. No hardware or network code.
"""
import collections
import csv
import json
import math
import statistics
from pathlib import Path
from legacy_energy_methods import quantile

HOSTS = {'DeepX': 'orin_nx_deepx_m1_01', 'H8': 'orin_nx_hailo8_01', 'H10': 'orin_nx_hailo10_01'}
IDENTITY = ('model_id', 'setup_id', 'backend', 'case_id', 'runner')
PARETO_DEFINITION = {
    'dominance': 'B dominates A iff FPS_B >= FPS_A and energy_B <= energy_A, with at least one strict inequality',
    'grouping': ['model', 'setup'],
    'objectives': {'fps': 'maximize', 'energy_mj_per_image': 'minimize'},
    'population': 'all observed deployments with finite FPS and energy, including both Full alternatives',
    'quality_filter': False,
    'runner_front_scope': 'Native or Generic splits only, within the same model/setup',
    'equal_coordinates': 'retain every UID; equal coordinates do not dominate each other',
    'connection': 'straight segments between distinct front coordinates sorted by FPS; no interpolation claim',
}


def read(p):
    return json.loads(Path(p).read_text())


def write(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2, sort_keys=True, allow_nan=False) + '\n')


def table(p, rows):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r)) or ['empty']
    with p.open('w', newline='') as f:
        w = csv.DictWriter(f, fields, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list, tuple)) else v for k, v in r.items()})


def emit(p, rows):
    table(p.with_suffix('.csv'), rows)
    write(p.with_suffix('.json'), rows)


def grouped(rows, keys):
    g = collections.defaultdict(list)
    for r in rows:
        g[tuple(r.get(k) for k in keys)].append(r)
    return sorted(g.items(), key=lambda x: str(x[0]))


def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def positive(x):
    return numeric(x) and x > 0


def _pareto_front_uids(points):
    """Sweep exact coordinates from high FPS to low; retain all tied UIDs."""
    front = set()
    best_energy = math.inf
    previous = None
    coordinate_on_front = False
    for point in sorted(points, key=lambda r: (-r['fps'], r['energy_mj_per_image'], r['uid'])):
        coordinate = (point['fps'], point['energy_mj_per_image'])
        if coordinate != previous:
            coordinate_on_front = point['energy_mj_per_image'] < best_energy
            best_energy = min(best_energy, point['energy_mj_per_image'])
            previous = coordinate
        if coordinate_on_front:
            front.add(point['uid'])
    return front


def pareto_points(rows):
    """Export every selected row and its empirical two-objective front flags.

    Only missing/nonfinite/nonnumeric coordinates omit a point. Quality and all
    original admission/contract flags are deliberately absent from selection.
    This descriptive model/setup front includes Full deployments regardless of
    recorded work differences. The older boundary-specific table is unchanged.
    Nonfinite inputs become JSON null with an explicit reason, never zero.
    """
    points = []
    for row in sorted(rows, key=lambda r: r['uid']):
        reasons = []
        for field in ['fps', 'energy_mj_per_image']:
            value = row.get(field)
            if value is None:
                reasons.append('missing_' + field)
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                reasons.append('invalid_' + field)
            elif not math.isfinite(value):
                reasons.append('nonfinite_' + field)
        quality = row.get('quality_value')
        points.append({
            'uid': row['uid'], 'model': row['model_id'], 'setup': row['setup_id'],
            'runner': row['runner'], 'kind': row['kind'], 'backend': row['backend'],
            'case': row['case_id'],
            'fps': row.get('fps') if numeric(row.get('fps')) else None,
            'energy_mj_per_image': row.get('energy_mj_per_image') if numeric(row.get('energy_mj_per_image')) else None,
            'quality_value': quality if numeric(quality) else None,
            'quality_percent': 100 * quality if numeric(quality) else None,
            'quality_metric': row.get('quality_metric'),
            'included': not reasons, 'omission_reason': ';'.join(reasons) or None,
            'pareto_all': None, 'pareto_native': None, 'pareto_generic': None,
            'dominated_by_uid': None,
        })
    assert len({r['uid'] for r in points}) == len(points), 'duplicate Pareto point identity'
    for _, group in grouped([r for r in points if r['included']], ['model', 'setup']):
        front = _pareto_front_uids(group)
        for row in group:
            row['pareto_all'] = row['uid'] in front
            if not row['pareto_all']:
                # A deterministic, independently inspectable witness, not a
                # quality rank or a substitute for the complete front.
                row['dominated_by_uid'] = min(
                    other['uid'] for other in group
                    if other['fps'] >= row['fps']
                    and other['energy_mj_per_image'] <= row['energy_mj_per_image']
                    and (other['fps'] > row['fps']
                         or other['energy_mj_per_image'] < row['energy_mj_per_image']))
        for runner in ['native', 'generic']:
            splits = [r for r in group if r['kind'] == 'split' and r['runner'] == runner]
            runner_front = _pareto_front_uids(splits)
            for row in splits:
                row['pareto_' + runner] = row['uid'] in runner_front
    return points


def mean(v):
    return statistics.mean(v) if v else None


def ratio(a, b):
    return a / b if positive(a) and positive(b) else None


def select_fastest_deployments(rows, model_order):
    """Select one absolute-FPS split and its two concrete Full baselines.

    Selection uses the unrounded stored cohort FPS, across Native and Generic.
    Energy, quality, endpoint and admission flags never select or veto a point.
    Both table views and both new figures consume these same joined rows.
    """
    observed_models = {r['model_id'] for r in rows}
    models = list(dict.fromkeys(m for m in model_order if m in observed_models))
    models += sorted(observed_models - set(models))

    def fastest(candidates):
        valid = [r for r in candidates if positive(r.get('fps'))]
        return (min(valid, key=lambda r: (-r['fps'], r['uid'])) if valid else None,
                len(valid))

    def host(row):
        if not row:
            return None
        return row.get('physical_host') or HOSTS.get(row.get('setup_id'), row.get('setup_id')) or None

    def safe_record(value):
        # Strict JSON represents nonfinite missing observations as null. The
        # source rows remain unchanged; missing-energy reasons stay explicit.
        if isinstance(value, dict):
            return {k: safe_record(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [safe_record(v) for v in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def energy_reason(value):
        if value is None:
            return 'missing_energy_j_per_image'
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return 'invalid_energy_j_per_image'
        if not math.isfinite(value):
            return 'nonfinite_energy_j_per_image'
        if value <= 0:
            return 'nonpositive_energy_j_per_image'
        return None

    def selected_fields(prefix, selected, missing_reason):
        record = selected or {}
        energy = record.get('energy_j_per_image')
        reason = energy_reason(energy) if selected else missing_reason
        return {
            prefix + '_uid': record.get('uid'),
            prefix + '_runner': record.get('runner'),
            prefix + '_backend': record.get('backend'),
            prefix + '_setup': record.get('setup_id'),
            prefix + '_physical_host': host(selected),
            prefix + '_case': record.get('case_id'),
            prefix + '_fps': record.get('fps'),
            prefix + '_energy_j_per_image': energy if positive(energy) else None,
            prefix + '_mj_per_image': 1000 * energy if positive(energy) else None,
            prefix + '_missing_reason': missing_reason,
            prefix + '_energy_missing_reason': reason,
            # All recorded runtime/endpoints, quality, classes, flags and
            # provenance remain inspectable in JSON and the JSON-valued CSV cell.
            prefix + '_record': safe_record(selected),
        }

    selected = []
    for model in models:
        group = [r for r in rows if r['model_id'] == model]
        split, split_n = fastest([r for r in group if r['kind'] == 'split'
                                  and r['runner'] in {'native', 'generic'}])
        fulls = [r for r in group if r['kind'] == 'full']
        global_full, global_n = fastest(fulls)
        split_host = host(split)
        host_full, host_n = fastest([r for r in fulls if split_host is not None
                                    and host(r) == split_host])
        split_reason = None if split else 'no_valid_positive_fps_split'
        global_reason = None if global_full else 'no_valid_positive_fps_full'
        host_reason = (None if host_full else
                       'no_selected_split' if split is None else
                       'missing_split_host_identity' if split_host is None else
                       'no_valid_positive_fps_full_on_split_host')
        row = {
            'model': model,
            'split_candidate_count': split_n,
            'global_full_candidate_count': global_n,
            'host_full_candidate_count': host_n,
            **selected_fields('split', split, split_reason),
            **selected_fields('global_full', global_full, global_reason),
            **selected_fields('host_full', host_full, host_reason),
            'selection': 'retrospective_maximum_unrounded_observed_FPS; native_and_generic; exact_ties_uid_ascending',
            'comparison_scope': 'observed deployments; no equal-quality, endpoint-equivalence or isolated-split-effect claim',
        }
        for name in ['global', 'host']:
            prefix = name + '_full'
            row['R_' + name] = ratio(row['split_fps'], row[prefix + '_fps'])
            row['G_' + name] = ratio(row[prefix + '_energy_j_per_image'], row['split_energy_j_per_image'])
            energy_ratio = ratio(row['split_energy_j_per_image'], row[prefix + '_energy_j_per_image'])
            row['energy_ratio_' + name] = energy_ratio
            row['delta_E_' + name + '_pct'] = 100 * (energy_ratio - 1) if energy_ratio is not None else None
        if row['R_global'] is not None and row['R_host'] is not None:
            assert row['R_global'] <= row['R_host'], ('Full baseline ordering', model)
        selected.append(row)
    return selected


def dist(v, prefix):
    v = [x for x in v if numeric(x)]
    return {prefix + '_' + name: quantile(v, q) for name, q in [('min', 0), ('q25', .25), ('median', .5), ('q75', .75), ('max', 1)]}


def ci(v):
    # Original Twix convention: no invented interval for historical singles.
    if len(v) != 3:
        return [None, None]
    m = statistics.mean(v)
    h = 4.302652729749461 * statistics.stdev(v) / math.sqrt(3)
    return [m-h, m+h]


def select_metric(candidates, metric, identity):
    """Latest genuinely completed metric, by recorded completion time, never mtime.

    `identity` contains all binding dimensions required by the caller (host,
    runtime, cut, input and endpoint where known). Empty/failed newer reports do
    not shadow valid older observations. Quality is an independent metric.
    """
    valid = numeric if metric in {'quality_value', 'accuracy', 'map', 'quality_relative_loss'} else positive
    eligible = [r for r in candidates if all(r.get(k) == v for k, v in identity.items())
                and r.get('completed') is True and valid(r.get(metric))]
    if not eligible:
        return None
    return sorted(eligible, key=lambda r: (r.get('completed_at', ''), r.get('source_id', '')), reverse=True)[0]


def energy_statistics(repeats):
    """Recalculate image-normalized energy from E and completed-image counts."""
    if not repeats:
        return {'n_energy': 0, 'mean_E_over_N': None, 'mean_N_over_E': None,
                'reciprocal_mean_E_over_N': None, 'sum_E_over_sum_N': None,
                'sum_N_over_sum_E': None, 'energy_mean_ci95_low': None,
                'energy_mean_ci95_high': None, 'energy_min': None, 'energy_max': None,
                'energy_cv': None, 'energy_total_j': None, 'duration_total_s': None,
                'completed_images_total': None, 'mean_power_w': None}
    seen = set()
    for r in repeats:
        # Sensor observation IDs, not exports or report count, define repeats.
        key = (r.get('repeat'), r.get('source_sha256'))
        assert key not in seen, ('duplicate energy repeat', r.get('uid'), key)
        seen.add(key)
        assert positive(r.get('energy_j')) and positive(r.get('completed_tasks')), r
        assert positive(r.get('duration_s')), r
    e = [r['energy_j'] for r in repeats]
    n = [r['completed_tasks'] for r in repeats]
    v = [a/b for a, b in zip(e, n)]
    t = [r['duration_s'] for r in repeats]
    for r, x in zip(repeats, v):
        if r.get('j_per_task') is not None:
            assert math.isclose(x, r['j_per_task'], rel_tol=1e-10), ('E/N mismatch', r['uid'])
    lo, hi = ci(v)
    return {'n_energy': len(repeats), 'mean_E_over_N': mean(v),
            'mean_N_over_E': mean([b/a for a, b in zip(e, n)]),
            'reciprocal_mean_E_over_N': 1/mean(v), 'sum_E_over_sum_N': sum(e)/sum(n),
            'sum_N_over_sum_E': sum(n)/sum(e), 'energy_mean_ci95_low': lo,
            'energy_mean_ci95_high': hi, 'energy_min': min(v), 'energy_max': max(v),
            'energy_cv': statistics.stdev(v)/mean(v) if len(v)>1 else None,
            'energy_total_j': sum(e), 'duration_total_s': sum(t),
            'completed_images_total': sum(n), 'mean_power_w': mean([a/b for a,b in zip(e,t)])}


def comparison_summary(rows):
    perf = [r for r in rows if positive(r.get('fps_ratio'))]
    energy = [r for r in rows if positive(r.get('energy_ratio'))]
    joint = [r for r in perf if positive(r.get('energy_ratio'))]
    return {'n_pairs': len(rows), 'n_performance': len(perf), 'n_energy': len(energy),
            'n_joint': len(joint), 'faster': sum(r['fps_ratio']>1 for r in perf),
            'energy_lower': sum(r['energy_ratio']<1 for r in energy),
            'both_better': sum(r['fps_ratio']>1 and r['energy_ratio']<1 for r in joint),
            **dist([r['fps_ratio'] for r in perf], 'fps_ratio'),
            **dist([r['energy_ratio'] for r in energy], 'energy_ratio')}


def equal_model_summary(rows):
    """Median per model/setup; equally weight setups, then equally weight models."""
    group_rows = []
    for (model, setup), rs in grouped(rows, ['model', 'setup']):
        group_rows.append({'model': model, 'setup': setup, **comparison_summary(rs)})
    model_rows = []
    for (model,), rs in grouped(group_rows, ['model']):
        model_rows.append({'model': model, 'n_setups': len(rs),
                           'fps_ratio': mean([r['fps_ratio_median'] for r in rs if r['fps_ratio_median'] is not None]),
                           'energy_ratio': mean([r['energy_ratio_median'] for r in rs if r['energy_ratio_median'] is not None])})
    out = []
    for setup in ['all'] + sorted({r['setup'] for r in group_rows}):
        rs = model_rows if setup == 'all' else [dict(r, fps_ratio=r['fps_ratio_median'], energy_ratio=r['energy_ratio_median']) for r in group_rows if r['setup']==setup]
        pv = [r['fps_ratio'] for r in rs if r['fps_ratio'] is not None]
        ev = [r['energy_ratio'] for r in rs if r['energy_ratio'] is not None]
        out.append({'setup': setup, 'n_models': len(rs), 'n_performance_models': len(pv),
                    'n_energy_models': len(ev), 'fps_ratio': mean(pv), 'energy_ratio': mean(ev),
                    'aggregation': 'median_points_per_model_setup_then_mean_setups_per_model_then_mean_models'})
    return group_rows, model_rows, out


def build(inputs, output, config, current_observations=None):
    I, O = Path(inputs), Path(output)
    T = O/'tables'
    C = read(I/'cases.json')
    assert len({r['uid'] for r in C}) == len(C), 'duplicate operating-point identity'
    assert len({tuple(r.get(k) for k in IDENTITY) for r in C}) == len(C)
    E = {r['uid']: r for r in read(I/'selected_evidence.json')}
    ER = read(I/'energy_repeats.json')
    P = read(I/'pipeline_repeats.json')
    replacement_path = (None if current_observations is False else
        Path(current_observations) if current_observations else I/'current_observations.json')
    if current_observations not in (None, False) and not replacement_path.is_file():
        raise FileNotFoundError('Current observation input does not exist: ' + str(replacement_path))
    replacement_history = []
    if replacement_path is not None and replacement_path.is_file():
        from current_observations import apply_replacements
        C, selected, ER, P, replacement_history = apply_replacements(C, list(E.values()), ER, P,
            read(replacement_path), replacement_path.parent)
        E = {row['uid']: row for row in selected}
    archived = {row['uid']: row for row in replacement_history}
    R = collections.defaultdict(list)
    for r in ER:
        R[r['uid']].append(r)
    assert set(R) <= {r['uid'] for r in C}
    data, uncertainty, sources, generations, energy_rows = [], [], [], [], []
    for c in sorted(C, key=lambda r:r['uid']):
        ev = E.get(c['uid'], {})
        rr = sorted(R[c['uid']], key=lambda r:r['repeat'])
        es = energy_statistics(rr)
        fs = c.get('fps_samples') or []
        if fs:
            assert len(fs) == c['performance_observations']
            assert all(positive(v) for v in fs)
            if positive(c.get('fps')):
                assert math.isclose(statistics.median(fs), c['fps'], rel_tol=1e-10), c['uid']
        if rr and c.get('raw_j_per_task') is not None:
            assert math.isclose(es['mean_E_over_N'], c['raw_j_per_task'], rel_tol=1e-10), c['uid']
        energy = es['mean_E_over_N'] if rr else c.get('raw_j_per_task')
        # Preserve selected historical single energy as an observation, never synthesize repeats.
        energy_n = len(rr) if rr else (c.get('energy_repeat_n') or (1 if positive(energy) else 0))
        d = dict(c)
        for k, v in ev.items():
            if k not in c:
                d[k] = v
        d.update(physical_host=HOSTS.get(c['setup_id'], c['setup_id']),
                 energy_j_per_image=energy, energy_mj_per_image=1000*energy if positive(energy) else None,
                 performance_n=c.get('performance_observations', len(fs)) if positive(c.get('fps')) else 0,
                 energy_n=energy_n, included_performance=positive(c.get('fps')),
                 included_energy=positive(energy), included_joint=positive(c.get('fps')) and positive(energy),
                 inclusion_meaning='selected observed metric; no retroactive endpoint-equivalence claim',
                 image_count_basis='completed_tasks is completed images; detection box count is not used',
                 endpoint_notes=ev.get('execution_notes', []),
                 energy_ci95_mean=ci([r['energy_j']/r['completed_tasks'] for r in rr]),
                 fps_min=min(fs) if fs else c.get('fps'), fps_max=max(fs) if fs else c.get('fps'))
        if numeric(d.get('quality_value')) and numeric(d.get('quality_reference_value')):
            d['quality_reference_delta_percentage_points'] = 100*(d['quality_value']-d['quality_reference_value'])
        else:
            d['quality_reference_delta_percentage_points'] = None
        if c['uid'] in archived and archived[c['uid']]['case'] is not None:
            prior = dict(archived[c['uid']]['case'])
            for key, value in archived[c['uid']]['selected_evidence'].items():
                prior.setdefault(key, value)
            prior['physical_host'] = HOSTS.get(prior['setup_id'], prior['setup_id'])
            prior['energy_j_per_image'] = prior.get('raw_j_per_task')
            prior['energy_mj_per_image'] = 1000*prior['raw_j_per_task'] if positive(prior.get('raw_j_per_task')) else None
            d['archived_deployment_record'] = prior
        data.append(d)
        uncertainty.append({'uid': c['uid'], 'model': c['model_id'], 'setup': c['setup_id'], 'runner': c['runner'],
                            'stored_fps': c.get('fps'), 'n_performance': d['performance_n'],
                            'fps_min': d['fps_min'], 'fps_max': d['fps_max'],
                            'fps_cv': statistics.stdev(fs)/mean(fs) if len(fs)>1 else None,
                            'fps_ci': None, 'fps_interval_kind': 'observed repeat range; no median CI',
                            **es, 'energy_independence_unit': 'original_sensor_repeat',
                            'energy_unit': 'J/image'})
        for r in rr:
            energy_rows.append(dict(r, completed_images=r['completed_tasks'],
                                    j_per_image=r['energy_j']/r['completed_tasks'],
                                    mean_power_w=r['energy_j']/r['duration_s'],
                                    source_metric='E_calibrated / N_completed_images'))
        for metric, value, n in [('performance', d['fps'], d['performance_n']), ('energy', energy, energy_n), ('quality', d.get('quality_value'), d.get('quality_n'))]:
            sources.append({'uid': c['uid'], 'metric': metric, 'value': value,
                            'unit': {'performance':'image/s','energy':'J/image','quality':d.get('quality_metric')}[metric],
                            'source': d.get(metric+'_source'), 'source_sha256': d.get('quality_evidence_sha256') if metric=='quality' else d.get(metric+'_source_sha256'),
                            'original_current_quality_source_sha256': c.get('quality_source_sha256') if metric=='quality' else None,
                            'original_field': d.get(metric+'_original_field'), 'generation': d.get(metric+'_generation'),
                            'runtime': d.get('runtime', c['backend']), 'repeat_or_image_n': n,
                            'remeasured_in_refresh16': (bool(c.get('refresh16')) and not bool(c.get('native_refresh'))
                                and metric not in c.get('current_observation_metric_updates', []) and value is not None) if metric!='quality' else False,
                            'remeasured_in_native_a4': (bool(c.get('native_refresh')) and
                                metric not in c.get('current_observation_metric_updates', []) and value is not None) if metric!='quality' else False,
                            'repeat_sources': [r.get('source_sha256') for r in rr] if metric=='energy' else None})
        generations.append({'uid': c['uid'], 'performance_generation': d.get('performance_generation'),
                            'energy_generation': d.get('energy_generation'), 'quality_generation': d.get('quality_generation'),
                            'performance_source': d.get('performance_source'), 'energy_source': d.get('energy_source'),
                            'quality_source': d.get('quality_source'), 'new_performance': bool(c.get('native_refresh')),
                            'new_energy': bool(c.get('native_refresh')), 'new_quality': False,
                            'mixed_generations': len({d.get(x+'_generation') for x in ['performance','energy','quality']})>1})
    M = {r['uid']:r for r in data}
    emit(O/'data'/'PAPER_DATASET', data)
    if replacement_history:
        document = read(replacement_path)
        expected_packages = document.get('expected_packages', [])
        accepted_packages = sorted(metric['package_label'] for row in document['observations']
            for metric in row['metrics'].values() if metric.get('package_label'))
        write(O/'data/current_observation_history.json', replacement_history)
        write(O/'data/current_observation_inputs.json', document)
        import hashlib
        write(O/'data/current_observation_binding.json', dict(
            schema='current-deployment-input-binding-v1',
            observations_sha256=hashlib.sha256(replacement_path.read_bytes()).hexdigest(),
            sources=document['sources'], expected_packages=expected_packages,
            accepted_packages=accepted_packages, pending_packages=sorted(set(expected_packages)-set(accepted_packages)),
            prior_rows_preserved=True, hardware_measurements_performed_by_generator=False))
    emit(T/'PARETO_POINTS', pareto_points(data))
    emit(O/'data'/'METRIC_SOURCES', sources)
    emit(O/'data'/'MEASUREMENT_GENERATIONS', generations)
    emit(T/'repeat_uncertainty', uncertainty)
    emit(T/'energy_repeats', energy_rows)
    emit(T/'pipeline_repeats', P)
    fulls = [r for r in data if r['kind']=='full']
    emit(T/'full_configurations', fulls)
    coverage = []
    for k, rs in grouped(data, ['model_id','setup_id','runner','kind']):
        coverage.append(dict(zip(['model','setup','runner','kind'], k), n_cases=len(rs),
                             performance_n=sum(r['included_performance'] for r in rs),
                             energy_n=sum(r['included_energy'] for r in rs), joint_n=sum(r['included_joint'] for r in rs),
                             quality_n=sum(numeric(r.get('quality_value')) for r in rs),
                             accuracy_loss=sum(r['quality_class']=='accuracy_loss' for r in rs)))
    emit(T/'coverage', coverage)
    emit(T/'negative_quality', [r for r in data if r['quality_class']=='accuracy_loss' or (r.get('quality_numeric_relative_loss') or 0)>.05])
    emit(T/'boundary_cases', [r for r in data if not r.get('normal_energy') or not r.get('normal_performance_claim')])
    byidentity = {(r['runner'], r['model_id'], r['setup_id'], r['backend'], r['case_id']):r for r in data}
    ng = []
    for n in data:
        if n['kind']!='split' or n['runner']!='native':
            continue
        g = byidentity.get(('generic', n['model_id'], n['setup_id'], n['backend'], n['case_id']))
        if not g:
            continue
        nr, gr = R[n['uid']], R[g['uid']]
        fr = [x/y for x in n['fps_samples'] for y in g['fps_samples'] if positive(x) and positive(y)]
        er = [x['j_per_task']/y['j_per_task'] for x in nr for y in gr]
        ng.append({'model': n['model_id'], 'setup': n['setup_id'], 'case': n['case_id'],
                   'native_uid': n['uid'], 'generic_uid': g['uid'],
                   'native_fps': n['fps'], 'generic_fps': g['fps'], 'fps_ratio': ratio(n['fps'], g['fps']),
                   'native_raw_mj': n['energy_mj_per_image'], 'generic_raw_mj': g['energy_mj_per_image'],
                   'energy_ratio': ratio(n['energy_j_per_image'],g['energy_j_per_image']),
                   'comparison_energy_ratio': ratio(n['comparison_j_per_task'],g['comparison_j_per_task']),
                   'performance_included': n['included_performance'] and g['included_performance'],
                   'energy_included': n['included_energy'] and g['included_energy'],
                   'original_strict_performance': n['normal_performance_claim'] and g['normal_performance_claim'],
                   'original_strict_energy': n['normal_energy'] and g['normal_energy'],
                   'both_reference_close': n['quality_class']==g['quality_class']=='reference_close',
                   'administrative_quality_receipt_gap': n['administrative_quality_receipt_gap'] or g['administrative_quality_receipt_gap'],
                   'native_quality': n.get('quality_value'), 'generic_quality': g.get('quality_value'),
                   'quality_metric': n.get('quality_metric'),
                   'fps_repeat_ratio_min': min(fr) if fr else None, 'fps_repeat_ratio_max': max(fr) if fr else None,
                   'energy_repeat_ratio_min': min(er) if er else None,'energy_repeat_ratio_max': max(er) if er else None,
                   'native_endpoint_notes': n['endpoint_notes'], 'generic_endpoint_notes': g['endpoint_notes']})
    emit(T/'native_generic_pairs', ng)
    ng_groups, ng_models, ng_equal = equal_model_summary(ng)
    emit(T/'native_generic_groups', ng_groups)
    emit(T/'native_generic_models', ng_models)
    emit(T/'equal_model_summary', ng_equal)
    contracts = {(p['split_uid'],p['baseline_uid']):p for p in read(I/'split_full_contracts.json')}
    pairs = []
    for s in data:
        if s['kind']!='split':
            continue
        for b in fulls:
            if (s['model_id'],s['setup_id']) != (b['model_id'],b['setup_id']):
                continue
            p = contracts.get((s['uid'],b['uid']))
            perf = ratio(s['fps'],b['fps'])
            energy = ratio(s['energy_j_per_image'],b['energy_j_per_image'])
            pairs.append({'model':s['model_id'],'setup':s['setup_id'],'runner':s['runner'],'case':s['case_id'],
                          'split_uid':s['uid'],'baseline_uid':b['uid'],'baseline_backend':b['backend'],
                          'baseline_kind':'tensorrt_full' if b['backend']=='native_full_tensorrt' else 'vendor_full',
                          'split_fps':s['fps'],'baseline_fps':b['fps'],'fps_ratio':perf,
                          'split_raw_mj':s['energy_mj_per_image'],'baseline_raw_mj':b['energy_mj_per_image'],
                          'energy_ratio':energy,'energy_gain_same_full':ratio(b['energy_j_per_image'],s['energy_j_per_image']),
                          'comparison_energy_ratio':ratio(s['comparison_j_per_task'],b['comparison_j_per_task']),
                          'baseline_energy_comparison_basis':b.get('comparison_basis'),
                          'performance_included':perf is not None,'energy_included':energy is not None,
                          'source_claim_flag':p.get('claim_comparable') if p else None,
                          'semantic_comparable':p.get('semantic_comparable') if p else None,
                          'original_contract_present':p is not None,
                          'original_comparison_reasons':p.get('comparison_reasons',[]) if p else [],
                          'original_semantic_reasons':p.get('semantic_comparison_reasons',[]) if p else [],
                          'original_strict_performance':bool(p and p.get('claim_comparable') and p.get('semantic_comparable') and s['normal_performance_claim'] and b['normal_performance_claim']),
                          'original_strict_energy':bool(p and p.get('claim_comparable') and p.get('semantic_comparable') and s['normal_energy'] and b['normal_energy']),
                          'both_reference_close':s['quality_class']==b['quality_class']=='reference_close',
                          'administrative_quality_receipt_gap':s['administrative_quality_receipt_gap'] or b['administrative_quality_receipt_gap'],
                          'split_quality':s.get('quality_value'),'baseline_quality':b.get('quality_value'),
                          'split_endpoint_notes':s['endpoint_notes'],'baseline_endpoint_notes':b['endpoint_notes'],
                          'comparison_scope':'observed deployment differences; endpoint equivalence not implied'})
    emit(T/'split_full_pairs',pairs)
    native_pairs = [r for r in pairs if r['runner']=='native']
    emit(T/'native_split_full_pairs',native_pairs)
    sf_groups = []
    for k,rs in grouped(pairs,['model','setup','runner','baseline_kind']):
        sf_groups.append(dict(zip(['model','setup','runner','baseline_kind'],k),**comparison_summary(rs)))
    emit(T/'split_full_groups',sf_groups)
    choices=[]
    for s in [r for r in data if r['kind']=='split']:
        bs = [b for b in fulls if (b['model_id'],b['setup_id'])==(s['model_id'],s['setup_id'])]
        ps = [b for b in bs if positive(b['fps'])]
        es = [b for b in bs if positive(b['energy_j_per_image'])]
        fast = sorted(ps,key=lambda r:(-r['fps'],r['uid']))[0] if ps else None
        low = sorted(es,key=lambda r:(r['energy_j_per_image'],r['uid']))[0] if es else None
        choices.append({'split_uid':s['uid'],'model':s['model_id'],'setup':s['setup_id'],'runner':s['runner'],'case':s['case_id'],
                        'split_fps':s['fps'],'split_mj_per_image':s['energy_mj_per_image'],
                        'baseline_uid':fast['uid'] if fast else None,'baseline_backend':fast['backend'] if fast else None,
                        'baseline_fps':fast['fps'] if fast else None,'baseline_mj_per_image':fast['energy_mj_per_image'] if fast else None,
                        'speedup':ratio(s['fps'],fast['fps']) if fast else None,
                        'speedup_vs_fastest_full':ratio(s['fps'],fast['fps']) if fast else None,
                        'energy_gain_same_full':ratio(fast['energy_j_per_image'],s['energy_j_per_image']) if fast else None,
                        'lowest_energy_full_uid':low['uid'] if low else None,
                        'lowest_full_mj_per_image':low['energy_mj_per_image'] if low else None,
                        'energy_ratio_vs_lowest_full':ratio(s['energy_j_per_image'],low['energy_j_per_image']) if low else None,
                        'performance_full_candidates':len(ps),'energy_full_candidates':len(es),
                        'quality_metric':s.get('quality_metric'),'quality_value':s.get('quality_value'),
                        'quality_relative_loss':s['quality_relative_loss'],'quality_numeric_relative_loss':s.get('quality_numeric_relative_loss')})
    emit(T/'baseline_selection',choices)
    top=[]
    for (model,),rs in grouped([r for r in choices if r['runner']==config['table3_runner'] and positive(r['speedup'])],['model']):
        for rank,r in enumerate(sorted(rs,key=lambda r:(-r['speedup'],r['split_uid']))[:config['table3_top_n']],1):
            top.append(dict(r,rank=rank,native_candidate_count=len(rs),selection='retrospective_top_FPS_ratio; energy never selects or vetoes'))
    emit(T/'table3_top2_native',top)
    fastest_deployments = select_fastest_deployments(data, config['model_order'])
    emit(T/'table3_fastest_deployments', fastest_deployments)
    emit(T/'fastest_split_baselines', fastest_deployments)
    t2=[]
    for (model,),rs in grouped(fulls,['model_id']):
        trt=[r for r in rs if r['backend']=='native_full_tensorrt']
        row={'model':model,'trt_host_count':len(trt),'trt_fps_min':min((r['fps'] for r in trt if positive(r['fps'])),default=None),
             'trt_fps_max':max((r['fps'] for r in trt if positive(r['fps'])),default=None),
             'trt_fps_mean':mean([r['fps'] for r in trt if positive(r['fps'])]),
             'trt_mj_min':min((r['energy_mj_per_image'] for r in trt if positive(r['energy_mj_per_image'])),default=None),
             'trt_mj_max':max((r['energy_mj_per_image'] for r in trt if positive(r['energy_mj_per_image'])),default=None),
             'trt_mj_mean':mean([r['energy_mj_per_image'] for r in trt if positive(r['energy_mj_per_image'])]),
             'trt_range_kind':'range of measured host aggregates, not repeat CI'}
        for setup in sorted(HOSTS):
            ts=[r for r in trt if r['setup_id']==setup]
            vs=[r for r in rs if r['setup_id']==setup and r['backend']!='native_full_tensorrt']
            for label,vals in [('trt_'+setup,ts),(setup,vs)]:
                assert len(vals)<=1
                r=vals[0] if vals else {}
                row.update({label+'_uid':r.get('uid'),label+'_fps':r.get('fps'),label+'_mj':r.get('energy_mj_per_image')})
        t2.append(row)
    emit(T/'table2_full',t2)
    optima=[]
    for (model,setup,runner),rs in grouped([r for r in data if r['kind']=='split'],['model_id','setup_id','runner']):
        ps=[r for r in rs if r['included_performance']];es=[r for r in rs if r['included_energy']]
        fast=sorted(ps,key=lambda r:(-r['fps'],r['uid']))[0] if ps else None
        low=sorted(es,key=lambda r:(r['energy_j_per_image'],r['uid']))[0] if es else None
        optima.append({'model':model,'setup':setup,'runner':runner,'candidate_count':len(rs),
                       'performance_n':len(ps),'energy_n':len(es),'joint_n':sum(r['included_joint'] for r in rs),
                       'multiple_candidates':len(rs)>1,'fastest_uid':fast['uid'] if fast else None,
                       'lowest_energy_uid':low['uid'] if low else None,'same_optimum':fast['uid']==low['uid'] if fast and low else None,
                       'fastest_case':fast['case_id'] if fast else None,'fastest_fps':fast['fps'] if fast else None,
                       'fastest_mj_per_image':fast['energy_mj_per_image'] if fast else None,
                       'fastest_quality':fast.get('quality_value') if fast else None,
                       'lowest_energy_case':low['case_id'] if low else None,'lowest_energy_fps':low['fps'] if low else None,
                       'lowest_energy_mj_per_image':low['energy_mj_per_image'] if low else None,
                       'lowest_energy_quality':low.get('quality_value') if low else None,
                       'quality_metric':rs[0].get('quality_metric')})
    emit(T/'model_setup_optima',optima)
    quality=[]
    for s in [r for r in data if r['kind']=='split']:
        vendor=[r for r in fulls if (r['model_id'],r['setup_id'])==(s['model_id'],s['setup_id']) and r['backend']!='native_full_tensorrt']
        b=vendor[0] if vendor else {}
        compatible=s.get('quality_metric') is not None and s.get('quality_metric')==b.get('quality_metric')
        sv,bv=s.get('quality_value'),b.get('quality_value')
        quality.append({'uid':s['uid'],'model':s['model_id'],'setup':s['setup_id'],'runner':s['runner'],'case':s['case_id'],
                        'quality_metric':s.get('quality_metric'),'split_quality':sv,'reference_quality':s.get('quality_reference_value'),
                        'vendor_full_uid':b.get('uid'),'vendor_full_quality':bv if compatible else None,
                        'split_minus_vendor_percentage_points':100*(sv-bv) if compatible and numeric(sv) and numeric(bv) else None,
                        'split_minus_reference_percentage_points':s.get('quality_reference_delta_percentage_points'),
                        'current_cached_relative_loss':s['quality_relative_loss'],'selected_numeric_relative_loss':s.get('quality_numeric_relative_loss'),
                        'quality_class':s['quality_class'],'cached_loss_disagrees':s.get('quality_cached_loss_disagrees'),
                        'quality_n':s.get('quality_n'),'vendor_quality_n':b.get('quality_n')})
    emit(T/'quality_comparison',quality)
    sensitivities=[]
    for comparison,rows in [('native_generic',ng),('native_split_all_full',native_pairs),('native_split_vendor_full',[r for r in native_pairs if r['baseline_kind']=='vendor_full']),('native_split_tensorrt_full',[r for r in native_pairs if r['baseline_kind']=='tensorrt_full'])]:
        for pop in config['sensitivities']:
            for basis in config['sensitivity_energy_bases']:
                selected=[]
                for r in rows:
                    if pop=='both_reference_close' and not r['both_reference_close']:continue
                    if pop=='exclude_administrative_receipt_gaps' and r['administrative_quality_receipt_gap']:continue
                    x=dict(r)
                    if basis=='existing_comparison':x['energy_ratio']=x['comparison_energy_ratio']
                    if pop=='original_strict_flags':
                        if not x['original_strict_performance']:x['fps_ratio']=None
                        if not x['original_strict_energy']:x['energy_ratio']=None
                    selected.append(x)
                sensitivities.append({'comparison':comparison,'population':pop,'energy_basis':basis,**comparison_summary(selected)})
    emit(T/'sensitivity',sensitivities)
    # Descriptive Pareto sets are restricted to observed model/host/runner and
    # the recorded timed completion mode/boundary. Quality is NOT optimized.
    pareto=[]
    pfields=['model_id','setup_id','runner','measured_completion_mode','measurement_boundary','energy_scope','energy_window']
    for k,rs in grouped([r for r in data if r['included_joint']],pfields):
        for r in rs:
            known_boundary = all(r.get(f) is not None for f in pfields)
            dominates=[x['uid'] for x in rs if known_boundary and x['fps']>=r['fps'] and x['energy_j_per_image']<=r['energy_j_per_image'] and (x['fps']>r['fps'] or x['energy_j_per_image']<r['energy_j_per_image'])]
            pareto.append({'uid':r['uid'],'model':r['model_id'],'setup':r['setup_id'],'runner':r['runner'],
                           'cohort_fields':dict(zip(pfields,k)),'cohort_n':len(rs),'fps':r['fps'],
                           'raw_mj':r['energy_mj_per_image'],'pareto':not dominates if known_boundary else None,'dominated_by':dominates,
                           'comparability_recorded':known_boundary,
                           'objectives':'maximize observed images/s; minimize host-inclusive J/image',
                           'quality_constraint':'none; quality and endpoint notes remain separate; no equal-quality claim'})
    emit(T/'pareto',pareto)
    native_choices=[r for r in choices if r['runner']=='native']
    pc=[r for r in native_choices if positive(r['speedup'])]
    ec=[r for r in native_choices if positive(r['energy_ratio_vs_lowest_full'])]
    no=[r for r in optima if r['runner']=='native']
    multi=[r for r in no if r['multiple_candidates'] and r['same_optimum'] is not None]
    summary={'cases':len(data),'native':sum(r['runner']=='native' for r in data),
             'generic':sum(r['runner']=='generic' for r in data),
             'performance_coverage':sum(r['included_performance'] for r in data),
             'energy_coverage':sum(r['included_energy'] for r in data),'joint_coverage':sum(r['included_joint'] for r in data),
             'quality_numeric_coverage':sum(numeric(r.get('quality_value')) for r in data),
             'full_coverage':{'configurations':len(fulls),'performance':sum(r['included_performance'] for r in fulls),'energy':sum(r['included_energy'] for r in fulls)},
             'source_generation':config.get('source_generation'),
             'refresh16_cases':sum(bool(r.get('refresh16')) and not bool(r.get('native_refresh')) for r in data),
             'native_a4_cases':sum(bool(r.get('native_refresh')) for r in data),
             'updated_cases':sum(bool(r.get('native_refresh')) for r in data),
             'unchanged_cases':sum(not r.get('native_refresh') for r in data),
             'new_quality_evaluations':0,'quality_cached_loss_disagreements':sum(bool(r.get('quality_cached_loss_disagrees')) for r in data),
             'quality_loss':dict(collections.Counter(r['runner'] for r in data if r['quality_class']=='accuracy_loss')),
             'negative_numeric_quality_over_5_percent':sum((r.get('quality_numeric_relative_loss') or 0)>.05 for r in data),
             'native_generic':comparison_summary(ng),'native_generic_equal_model':ng_equal,
             'native_split_full':comparison_summary(native_pairs),'all_runner_split_full':comparison_summary(pairs),
             'fastest_full_comparison':{'splits':len(pc),'faster':sum(r['speedup']>1 for r in pc),**dist([r['speedup'] for r in pc],'speedup')},
             'lowest_full_energy_comparison':{'splits':len(ec),'lower':sum(r['energy_ratio_vs_lowest_full']<1 for r in ec),**dist([r['energy_ratio_vs_lowest_full'] for r in ec],'ratio')},
             'table3_rows':len(top),'table3_max_speedup':max((r['speedup'] for r in top),default=None),
             'optima':{'groups':len(no),'multi_candidate_groups':len(multi),'multi_candidate_conflicts':sum(not r['same_optimum'] for r in multi),
                       'multi_candidate_same':sum(r['same_optimum'] for r in multi),'single_candidate_groups':sum(not r['multiple_candidates'] for r in no)},
             'historical_strict_excluded_pairs_retained':sum(r['source_claim_flag'] is True and r['semantic_comparable'] is False for r in native_pairs),
             'nonclaim_performance_full_values_retained':sum(r['included_performance'] and not r['normal_performance_claim'] for r in fulls),
             'normalization_direction_changes':sum(positive(r['energy_ratio']) and positive(r['comparison_energy_ratio']) and (r['energy_ratio']<1)!=(r['comparison_energy_ratio']<1) for r in native_pairs),
             'generations':{axis:dict(collections.Counter(r.get(axis+'_generation','unknown') for r in data)) for axis in ['performance','energy','quality']},
             'missing_fields':{'performance_uids':[r['uid'] for r in data if not r['included_performance']],
                               'energy_uids':[r['uid'] for r in data if not r['included_energy']],
                               'quality_uids':[r['uid'] for r in data if not numeric(r.get('quality_value'))]},
             'energy_unit':'J/image','display_energy_unit':'mJ/image','posthoc_only':True,
             'selection':'broad numeric observations; original flags and work differences retained'}
    if replacement_history:
        replacements = [row for row in data if row.get('current_observation_metric_updates')]
        summary.update(current_observation_replacements=len(replacements),
            current_added_deployments=sum(row['case'] is None for row in replacement_history),
            current_external_captures={metric:sum(metric in row['current_observation_metric_updates'] and
                row.get(metric+'_acquisition_origin') == 'new_capture' for row in replacements)
                for metric in ['performance', 'quality', 'energy']},
            hardware_measurements_performed_by_generator=False,
            current_observation_packages=dict(expected=expected_packages, accepted=accepted_packages,
                pending=sorted(set(expected_packages)-set(accepted_packages))))
        summary['new_quality_evaluations'] = summary['current_external_captures']['quality']
    write(O/'data'/'summary.json',summary)
    write(O/'data'/'analysis_config.json',config)
    return summary
