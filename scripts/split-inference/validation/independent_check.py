#!/usr/bin/env python3
"""Recalculate paper core quantities independently, using Python's standard library.

No import of the dataset builder, its metric functions, or the plotting code.
The compact original observations are the numerical authority for this check.
"""
import argparse
import collections
import csv
import json
import math
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text())


def close(actual, expected, label):
    if actual is None or expected is None:
        assert actual is expected, (label, actual, expected)
    else:
        assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12), (label, actual, expected)


def unique(rows, field='uid'):
    mapped = {r[field]: r for r in rows}
    assert len(mapped) == len(rows), ('Duplicate identity', field)
    return mapped


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


GENERATION = 'deepx_native_a4_20261015'
IDENTITY_FIELDS = {'uid','model_id','setup_id','backend','case_id','runner','kind','task'}


def quality_fields(row):
    return {key:value for key,value in row.items() if 'quality' in key}


def repeat_map(rows):
    mapped = {(r['uid'],r['repeat']):r for r in rows}
    assert len(mapped) == len(rows), 'Duplicate UID/repeat identity'
    return mapped


def source_reference(reference, label):
    # Existing archive identifiers are checked as metadata, never opened here.
    assert isinstance(reference,dict), (label,'missing source reference')
    digest = reference.get('sha256')
    assert isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest), (label,'source digest')
    assert reference.get('canonical_path') and reference.get('bytes',0)>0, (label,'source identity')
    return digest


def check_request_latency(latency, completed, label):
    assert latency['status']=='complete' and latency['task_complete'] is True, (label,'request completion')
    assert latency['count']==latency['expected_count']==completed, (label,'request count')
    assert latency['clock']=='perf_counter_ns' and latency['timestamp_unit']=='ns' and latency['unit']=='ms'
    assert latency['semantics']=='prepared_input_to_completed_task'
    assert latency['admission_wait_included'] is True and latency['warmup_included'] is False
    assert latency.get('errors') and all(v==0 for v in latency['errors'].values()), (label,'request errors')
    pairs=latency['pairs']
    assert len(pairs)==completed and len({p[0] for p in pairs})==completed, (label,'request pair identities')
    assert all(len(p)==3 and isinstance(p[1],int) and isinstance(p[2],int) and p[2]>=p[1] for p in pairs)
    durations=sorted((p[2]-p[1])/1_000_000 for p in pairs)
    def quantile(q):
        position=(len(durations)-1)*q
        low,high=math.floor(position),math.ceil(position)
        return durations[low]+(durations[high]-durations[low])*(position-low)
    for field,value in [('min_ms',durations[0]),('max_ms',durations[-1]),
                        ('mean_ms',statistics.mean(durations)),('p50_ms',quantile(.5)),('p95_ms',quantile(.95))]:
        close(latency[field],value,label+' '+field)


def check_a4_repeats(source, targets, energies, pipeline):
    assert len(targets)==75 and len(source)==450, 'A4 publication population'
    expected={u for u,r in source.items() if r['runner']=='native' and r['setup_id']=='DeepX'
              and ((r['kind']=='split' and r['backend']=='deepx_to_trt')
                   or (r['kind']=='full' and r['backend']=='native_full_deepx'))}
    assert targets==expected, 'A4 target selection must use exact Native backend identities'
    assert sum(source[u]['kind']=='split' for u in targets)==68
    assert sum(source[u]['kind']=='full' for u in targets)==7
    all_pipeline=repeat_map(pipeline)
    performance=[r for r in pipeline if r['uid'] in targets]
    selected_energy=[r for u in targets for r in energies[u]]
    assert len(performance)==len(selected_energy)==225
    assert len({r['runtime_instance_id'] for r in performance})==225, 'A4 independent runtime instances'
    assert len({r['raw_sha256'] for r in performance})==225, 'A4 independent performance originals'
    for field in ['source','raw_trace','command_window_binding','workload_completion']:
        assert len({source_reference(r[field],r['uid']+' '+field) for r in selected_energy})==225, ('A4 independent energy originals',field)
    for uid in sorted(targets):
        case=source[uid]
        assert case['deepx_runtime_mode']=='A4' and case['deepx_max_inflight']==4
        assert case['native_refresh']['campaign']==GENERATION
        assert case['native_refresh']['quality_remeasured'] is False
        assert case['native_refresh']['normal_import_complete'] is True
        assert source_reference(case['native_refresh']['performance_summary'],uid+' performance cohort')==case['performance_source_sha256']
        source_reference(case['native_refresh']['energy_source'],uid+' energy cohort')
        scheduling=case['scheduling']
        scheduling=json.loads(scheduling) if isinstance(scheduling,str) else scheduling
        assert scheduling['deepx_runtime_mode']=='A4' and scheduling['deepx_max_inflight']==4
        assert scheduling['host_pending_max']==4
        if case['kind']=='split':
            assert scheduling['queue_depth']==3, (uid,'A4 split FIFO')
        repeats=[all_pipeline[(uid,index)] for index in range(3)]
        assert {r['repeat'] for r in energies[uid]}=={0,1,2}
        assert case['performance_observations']==len(repeats)==len(energies[uid])==3
        assert case['energy_repeat_n']==3
        energy_values=[r['energy_j']/r['completed_tasks'] for r in energies[uid]]
        energy_mean=statistics.mean(energy_values)
        close(case['raw_j_per_task'],energy_mean,uid+' selected mean(E/N)')
        close(case['mean_tasks_per_j'],statistics.mean(r['completed_tasks']/r['energy_j'] for r in energies[uid]),uid+' selected mean(N/E)')
        halfwidth=4.302652729749461*statistics.stdev(energy_values)/math.sqrt(3)
        assert len(case['energy_ci'])==2
        for actual,expected_ci in zip(case['energy_ci'],[energy_mean-halfwidth,energy_mean+halfwidth]):
            close(actual,expected_ci,uid+' selected energy CI')
        for index,row in enumerate(repeats):
            assert row['campaign']==GENERATION and row['deepx_runtime_mode']=='A4' and row['deepx_max_inflight']==4
            for field in ['model_id','setup_id','case_id','kind','task']:
                assert row[field]==case[field], (uid,'performance identity',field)
            assert row['completed_tasks']>0 and row['completed_frames']==row['completed_tasks']
            assert row['stored_makespan_s']>0 and row['warmup_images']>=0
            close(row['makespan_ms'],1000*row['stored_makespan_s'],uid+' makespan units')
            calculated=row['completed_tasks']/row['stored_makespan_s']
            close(row['fps'],calculated,uid+' actual completed count/time FPS')
            close(case['fps_samples'][index],calculated,uid+' selected FPS repeat')
            assert source_reference(row['raw_source'],uid+' performance source')==row['raw_sha256']
            check_request_latency(row['request_latency'],row['completed_tasks'],uid+' request latency')
        for row in energies[uid]:
            assert row['campaign']==GENERATION and row['deepx_runtime_mode']=='A4' and row['deepx_max_inflight']==4
            assert row['logical_repeat']=='repeat:'+str(row['repeat'])
            assert row['source_sha256']==source_reference(row['source'],uid+' energy source')
            close(row['tasks_per_j'],row['completed_tasks']/row['energy_j'],uid+' actual N/E')
            close(row['average_power_w'],row['energy_j']/row['duration_s'],uid+' command-window power')
    return {'generation':GENERATION,'target_cases':len(targets),'performance_processes':len(performance),
            'energy_captures':len(selected_energy),'request_latency_cohorts':len(performance),
            'runtime_policy_scope':'compact A4/max4/FIFO3 metadata; batch/engine/drain admission bound by existing normal source proof'}


def check_migration_baseline(inputs, source, targets):
    before=unique(read(inputs/'cases.json'))
    assert set(before)==set(source), 'Migration baseline scope'
    for uid in source:
        if uid not in targets:
            assert before[uid]==source[uid], ('Changed non-target direct row',uid)
        assert quality_fields(before[uid])==quality_fields(source[uid]), ('Changed dataset quality',uid)
    evidence=unique(read(inputs/'selected_evidence.json'))
    return {'cases':before,'evidence':evidence}


def check_external_preservation(baseline_inputs, inputs, source, targets):
    baseline=check_migration_baseline(baseline_inputs,source,targets)
    evidence=unique(read(inputs/'selected_evidence.json'))
    assert set(evidence)==set(baseline['evidence']), 'Changed selected-evidence scope'
    for uid,before in baseline['evidence'].items():
        assert quality_fields(before)==quality_fields(evidence[uid]), ('Changed selected quality evidence',uid)
        if uid not in targets:
            assert before==evidence[uid], ('Changed non-target metric source evidence',uid)
    counts={}
    for name in ['pipeline_repeats','energy_repeats']:
        before=repeat_map([r for r in read(baseline_inputs/(name+'.json')) if r['uid'] not in targets])
        after=repeat_map([r for r in read(inputs/(name+'.json')) if r['uid'] not in targets])
        assert before==after, ('Changed non-target repeat originals',name)
        counts[name]=len(after)
    return {'unchanged_direct_rows':len(source)-len(targets),
            'preserved_quality_evidence_rows':len(baseline['evidence']),
            'unchanged_complete_nontarget_evidence_rows':len(source)-len(targets),**counts}


def check_canonical_selection(canonical_inputs, inputs, source, targets):
    canonical=unique(read(canonical_inputs/'cases.json'))
    assert set(canonical)==set(source), 'Canonical selection scope'
    for uid in targets:
        assert all(source[uid].get(k)==v for k,v in canonical[uid].items()), ('A4 canonical direct field',uid)
    counts={}
    for name in ['pipeline_repeats','energy_repeats']:
        actual=repeat_map([r for r in read(inputs/(name+'.json')) if r['uid'] in targets])
        expected=repeat_map([r for r in read(canonical_inputs/(name+'.json')) if r['uid'] in targets])
        assert set(actual)==set(expected), ('A4 canonical repeat scope',name)
        for key,row in expected.items():
            assert all(actual[key].get(k)==v for k,v in row.items()), ('A4 canonical repeat field',name,key)
        counts[name]=len(actual)
    return {'target_cases':len(targets),**counts,'source_scope':'existing canonical selected compact observations; no original rehash'}


def check_pareto(paper, output):
    """Independent exhaustive comparison; never import the sweep implementation."""
    exported = unique(read(output/'tables/PARETO_POINTS.json'))
    assert set(exported) == set(paper), 'Pareto export changed selected population'
    groups = collections.defaultdict(list)
    for uid, row in paper.items():
        point = exported[uid]
        for field, source_field in [('model','model_id'), ('setup','setup_id'), ('case','case_id'),
                                    ('runner','runner'), ('kind','kind'), ('backend','backend')]:
            assert point[field] == row[source_field], ('Pareto grouping/identity', uid, field)
        reasons = []
        for field in ['fps', 'energy_mj_per_image']:
            value = row.get(field)
            if value is None:
                reasons.append('missing_' + field)
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                reasons.append('invalid_' + field)
            elif not math.isfinite(value):
                reasons.append('nonfinite_' + field)
            assert point[field] == (value if finite_number(value) else None), ('Exact Pareto coordinate', uid, field)
        assert point['included'] is (not reasons), ('Pareto numeric-only inclusion', uid)
        assert point['omission_reason'] == (';'.join(reasons) or None), ('Pareto omission reason', uid)
        q = row.get('quality_value')
        assert point['quality_value'] == (q if finite_number(q) else None), ('Exact Pareto quality', uid)
        assert point['quality_percent'] == (100*q if finite_number(q) else None), ('Exact Pareto color', uid)
        assert point['quality_metric'] == row.get('quality_metric'), ('Pareto quality metric', uid)
        if not reasons:
            groups[(row['model_id'], row['setup_id'])].append(uid)
        else:
            assert all(point[k] is None for k in ['pareto_all','pareto_native','pareto_generic','dominated_by_uid'])

    def dominators(uid, population):
        a = paper[uid]
        return sorted(other for other in population
                      if paper[other]['fps'] >= a['fps']
                      and paper[other]['energy_mj_per_image'] <= a['energy_mj_per_image']
                      and (paper[other]['fps'] > a['fps']
                           or paper[other]['energy_mj_per_image'] < a['energy_mj_per_image']))

    front_sizes = []
    for (model, setup), population in sorted(groups.items()):
        for uid in population:
            witnesses = dominators(uid, population)
            assert exported[uid]['pareto_all'] is (not witnesses), ('Pairwise Pareto mismatch', uid)
            assert exported[uid]['dominated_by_uid'] == (witnesses[0] if witnesses else None), ('Pareto witness', uid)
        for runner in ['native', 'generic']:
            splits = [u for u in population if paper[u]['kind'] == 'split' and paper[u]['runner'] == runner]
            for uid in population:
                expected = not dominators(uid, splits) if uid in splits else None
                assert exported[uid]['pareto_' + runner] is expected, ('Runner Pareto mismatch', uid, runner)
        front = [u for u in population if not dominators(u, population)]
        front_sizes.append({'model': model, 'setup': setup, 'observations': len(population),
                            'front_uids': sorted(front), 'front_size': len(front),
                            'front_coordinates': len({(paper[u]['fps'],paper[u]['energy_mj_per_image']) for u in front}),
                            'native_split_front_size': sum(exported[u]['pareto_native'] is True for u in population),
                            'generic_split_front_size': sum(exported[u]['pareto_generic'] is True for u in population)})
    with (output/'tables/PARETO_POINTS.csv').open(newline='') as handle:
        csv_points = unique(list(csv.DictReader(handle)))
    assert set(csv_points) == set(exported), 'CSV/JSON Pareto population differs'
    for uid, point in exported.items():
        assert set(csv_points[uid]) == set(point), ('CSV/JSON Pareto fields', uid)
        for field, value in point.items():
            assert csv_points[uid][field] == ('' if value is None else str(value)), ('CSV/JSON Pareto value', uid, field)
    return exported, {'points': len(exported), 'included': sum(p['included'] for p in exported.values()),
                      'groups': len(groups), 'front_sizes': front_sizes,
                      'algorithm': 'exhaustive pairwise comparison of original unrounded PAPER_DATASET coordinates'}


def check_fastest_deployments(source, paper, fps, energy, output):
    """Select absolute maxima independently from the original repeat aggregates.

    Both exports and every ratio must name the actual measured denominators;
    neither agreement between two tables nor agreement with plots is sufficient.
    """
    table_a = read(output/'tables/table3_fastest_deployments.json')
    table_b = read(output/'tables/fastest_split_baselines.json')
    assert table_a == table_b, 'A/B must share the exact selected splits and Full references'
    selected = unique(table_a, 'model')
    models = {r['model_id'] for r in source.values()}
    order = read(output/'data/analysis_config.json')['model_order']
    expected_order = [m for m in order if m in models] + sorted(models-set(order))
    assert [r['model'] for r in table_a] == expected_order
    host_names = {'DeepX':'orin_nx_deepx_m1_01', 'H8':'orin_nx_hailo8_01',
                  'H10':'orin_nx_hailo10_01'}

    def valid(value):
        return finite_number(value) and value > 0

    def host(uid):
        return host_names.get(source[uid]['setup_id'], source[uid]['setup_id'])

    def maximum(ids):
        candidates = [u for u in ids if valid(fps[u])]
        return min(candidates, key=lambda u: (-fps[u], u)) if candidates else None

    def divide(a, b):
        return a/b if valid(a) and valid(b) else None

    for model in expected_order:
        row = selected[model]
        split = maximum(u for u,r in source.items()
                        if r['model_id']==model and r['kind']=='split'
                        and r['runner'] in {'native','generic'})
        full_ids = [u for u,r in source.items() if r['model_id']==model and r['kind']=='full']
        global_full = maximum(full_ids)
        host_full = maximum(u for u in full_ids if split and host(u)==host(split))
        for prefix,uid in [('split',split), ('global_full',global_full), ('host_full',host_full)]:
            assert row[prefix+'_uid'] == uid, ('Absolute FPS selection',model,prefix)
            if uid is None:
                assert row[prefix+'_missing_reason'], ('Missing candidate must be explicit',model,prefix)
                continue
            assert row[prefix+'_record'] == paper[uid], ('Selected metadata/flags changed',uid)
            for field, original in [('setup','setup_id'),('case','case_id'),('backend','backend'),('runner','runner')]:
                assert row[prefix+'_'+field] == source[uid][original], (uid,field)
            assert row[prefix+'_physical_host'] == host(uid), ('Physical host',uid)
            close(row[prefix+'_fps'],fps[uid],uid+' fastest FPS')
            close(row[prefix+'_energy_j_per_image'],energy[uid],uid+' selected Full/split energy')
            close(row[prefix+'_mj_per_image'],1000*energy[uid] if valid(energy[uid]) else None,uid+' selected mJ/image')
        sf = fps.get(split)
        se = energy.get(split)
        for scope,uid in [('global',global_full),('host',host_full)]:
            bf, be = fps.get(uid), energy.get(uid)
            er = divide(se,be)
            expected = {'R_'+scope:divide(sf,bf), 'G_'+scope:divide(be,se),
                        'energy_ratio_'+scope:er,
                        'delta_E_'+scope+'_pct':100*(er-1) if er is not None else None}
            for field,value in expected.items():
                close(row[field],value,model+' '+field+' from exact UIDs')
        if row['R_host'] is not None:
            assert row['R_global'] <= row['R_host'], ('Global maximum denominator',model)
        if global_full == host_full:
            for metric in ['R','G','energy_ratio']:
                assert row[metric+'_global'] == row[metric+'_host'], ('Identical denominator',model,metric)
            assert row['delta_E_global_pct'] == row['delta_E_host_pct']

    # Check complete CSV payloads, including serialized original metadata.
    for name,rows in [('table3_fastest_deployments',table_a), ('fastest_split_baselines',table_b)]:
        with (output/'tables'/(name+'.csv')).open(newline='') as stream:
            csv_rows = list(csv.DictReader(stream))
        expected_csv = [{k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list,tuple))
                        else '' if v is None else str(v) for k,v in row.items()} for row in rows]
        assert csv_rows == expected_csv, ('CSV/JSON agreement',name)
    return selected


def check(inputs, output, baseline_inputs=None, canonical_inputs=None):
    source = unique(read(inputs/'cases.json'))
    paper = unique(read(output/'data/PAPER_DATASET.json'))
    assert set(paper) == set(source), 'Broad paper selection changed canonical case scope'
    energies = collections.defaultdict(list)
    for r in read(inputs/'energy_repeats.json'):
        assert r['completed_tasks'] > 0 and r['energy_j'] > 0
        close(r['j_per_task'], r['energy_j']/r['completed_tasks'], r['uid']+' repeat E/N')
        energies[r['uid']].append(r)
    fps, energy = {}, {}
    uncertainty=unique(read(output/'tables/repeat_uncertainty.json'))
    pipeline=read(inputs/'pipeline_repeats.json')
    assert read(output/'tables/pipeline_repeats.json')==pipeline, 'Exported performance repeats changed'
    exported_energy=repeat_map(read(output/'tables/energy_repeats.json'))
    assert set(exported_energy)==set(repeat_map(read(inputs/'energy_repeats.json')))
    for uid, row in source.items():
        # Check that the broad representation preserves every original flag/value.
        assert all(paper[uid].get(k) == v for k, v in row.items()), ('Original field changed', uid)
        samples = row.get('fps_samples') or []
        fps[uid] = statistics.median(samples) if samples else row['fps']
        close(paper[uid]['fps'], fps[uid], uid+' median FPS')
        close(paper[uid]['performance_n'], row['performance_observations'], uid+' performance n')
        repeats = energies.get(uid, [])
        energy[uid] = statistics.mean(r['energy_j']/r['completed_tasks'] for r in repeats) if repeats else None
        close(paper[uid]['energy_j_per_image'], energy[uid], uid+' mean(E/N)')
        close(paper[uid]['energy_mj_per_image'], energy[uid]*1000 if energy[uid] is not None else None, uid+' mJ/image')
        close(paper[uid]['energy_n'], len(repeats), uid+' energy n')
        if repeats:
            values=[r['energy_j']/r['completed_tasks'] for r in repeats]
            images_per_joule=statistics.mean(r['completed_tasks']/r['energy_j'] for r in repeats)
            close(paper[uid]['mean_tasks_per_j'],images_per_joule,uid+' original mean(N/E)')
            close(uncertainty[uid]['mean_N_over_E'],images_per_joule,uid+' mean(N/E)')
            close(uncertainty[uid]['reciprocal_mean_E_over_N'],1/energy[uid],uid+' reciprocal mean(E/N)')
            pooled=sum(r['energy_j'] for r in repeats)/sum(r['completed_tasks'] for r in repeats)
            close(uncertainty[uid]['sum_E_over_sum_N'],pooled,uid+' pooled energy')
            close(uncertainty[uid]['sum_N_over_sum_E'],1/pooled,uid+' pooled efficiency')
            for field,value in [('energy_min',min(values)),('energy_max',max(values)),
                                ('energy_cv',statistics.stdev(values)/energy[uid] if len(values)>1 else None),
                                ('energy_total_j',sum(r['energy_j'] for r in repeats)),
                                ('duration_total_s',sum(r['duration_s'] for r in repeats)),
                                ('completed_images_total',sum(r['completed_tasks'] for r in repeats)),
                                ('mean_power_w',statistics.mean(r['energy_j']/r['duration_s'] for r in repeats))]:
                close(uncertainty[uid][field],value,uid+' '+field)
            halfwidth=4.302652729749461*statistics.stdev(values)/math.sqrt(3) if len(values)==3 else None
            expected_ci=[energy[uid]-halfwidth,energy[uid]+halfwidth] if halfwidth is not None else [None,None]
            for field,value in zip(['energy_mean_ci95_low','energy_mean_ci95_high'],expected_ci):
                close(uncertainty[uid][field],value,uid+' '+field)
            assert len(paper[uid]['energy_ci95_mean'])==2
            for actual,value in zip(paper[uid]['energy_ci95_mean'],expected_ci):
                close(actual,value,uid+' paper mean-energy CI')
            for repeat in repeats:
                exported=exported_energy[(uid,repeat['repeat'])]
                assert all(exported.get(k)==v for k,v in repeat.items()), ('Exported energy original changed',uid)
                close(exported['j_per_image'],repeat['energy_j']/repeat['completed_tasks'],uid+' exported E/N')
                close(exported['completed_images'],repeat['completed_tasks'],uid+' exported completed count')
                close(exported['mean_power_w'],repeat['energy_j']/repeat['duration_s'],uid+' exported power')

    # Exact targeted replacement and preservation, independently from the extractor.
    baseline = unique(read(inputs/'baseline_cases.json'))
    a4=(inputs/'native_refresh_provenance.json').exists()
    provenance=read(inputs/('native_refresh_provenance.json' if a4 else 'refresh16_provenance.json'))
    targets = set(provenance['targeted_uids'])
    assert len(targets)==len(provenance['targeted_uids']), 'Duplicate replacement target'
    assert set(baseline) == set(source)
    assert {u for u in source if source[u] != baseline[u]} == targets
    gates = {k for c in source.values() for k in c if 'quality' in k or (not a4 and k in
             ['normal_performance_claim','energy_claim','energy_exclusions'])}
    assert all(source[u].get(k) == baseline[u].get(k) for u in source for k in gates)
    for uid in targets:
        assert source[uid]['performance_observations'] == len(energies[uid]) == 3
        if a4:
            assert set(baseline[uid]) <= IDENTITY_FIELDS | set(quality_fields(baseline[uid])), ('Old target metrics retained in verification fixture',uid)
            assert all(baseline[uid].get(k)==source[uid].get(k) for k in IDENTITY_FIELDS)
    a4_report=check_a4_repeats(source,targets,energies,pipeline) if a4 else None
    preservation=check_external_preservation(baseline_inputs,inputs,source,targets) if baseline_inputs else None
    canonical=check_canonical_selection(canonical_inputs,inputs,source,targets) if canonical_inputs else None

    evidence = unique(read(inputs/'selected_evidence.json'))
    assert set(evidence)==set(source), 'Selected quality evidence must cover every deployment identity'
    for uid, e in evidence.items():
        for field,value in quality_fields(e).items():
            if field not in source[uid]:
                assert paper[uid].get(field)==value, ('Selected quality evidence field changed',uid,field)
        for field in ['quality_value','quality_reference_value','quality_numeric_relative_loss','quality_cached_loss_disagrees']:
            assert paper[uid].get(field) == e.get(field), (uid, field)

    # Recreate all host-specific Full alternatives; choose the FPS maximum before
    # looking at energy, then rank Native splits using unrounded values and UID.
    fulls = collections.defaultdict(list)
    models = set()
    for uid, row in source.items():
        models.add(row['model_id'])
        if row['kind'] == 'full':
            fulls[(row['model_id'], row['setup_id'])].append(uid)
    expected_top = {}
    for model in sorted(models):
        candidates = []
        for uid, row in source.items():
            if row['model_id'] != model or row['runner'] != 'native' or row['kind'] != 'split' or fps[uid] is None:
                continue
            available = [u for u in fulls[(model, row['setup_id'])] if fps[u] is not None]
            if not available:
                continue
            baseline_uid = sorted(available, key=lambda u: (-fps[u], u))[0]
            candidates.append((fps[uid]/fps[baseline_uid], uid, baseline_uid))
        expected_top[model] = sorted(candidates, key=lambda x: (-x[0],x[1]))[:2]
    table3 = read(output/'tables/table3_top2_native.json')
    observed_top = collections.defaultdict(list)
    for r in table3:
        uid, base = r['split_uid'], r['baseline_uid']
        observed_top[source[uid]['model_id']].append((uid,base))
        close(r['split_fps'], fps[uid], uid+' table3 split FPS')
        close(r['baseline_fps'], fps[base], uid+' table3 Full FPS')
        close(r['speedup'], fps[uid]/fps[base], uid+' table3 speedup')
        close(r['split_mj_per_image'], energy[uid]*1000, uid+' table3 energy')
        close(r['energy_gain_same_full'], energy[base]/energy[uid], uid+' table3 same-Full G_n')
        assert source[uid]['setup_id'] == source[base]['setup_id']
    for model, tuples in expected_top.items():
        assert observed_top[model] == [(u,b) for _,u,b in tuples], (model, observed_top[model], tuples)

    # Table 2 ranges span three host aggregates, not the underlying repeats.
    table2 = read(output/'tables/table2_full.json')
    assert {r['model'] for r in table2} == models
    for row in table2:
        model = row['model']
        tf = [uid for uid,c in source.items() if c['model_id']==model and c['kind']=='full'
              and c['backend']=='native_full_tensorrt']
        assert row['trt_host_count'] == len(tf)
        for unit,values in [('fps',[fps[u] for u in tf]),('mj',[1000*energy[u] for u in tf])]:
            for suffix,fn in [('min',min),('max',max),('mean',statistics.mean)]:
                close(row['trt_'+unit+'_'+suffix],fn(values),model+' TRT '+unit+' '+suffix)
        for setup in ['DeepX','H8','H10']:
            for trt in [True,False]:
                ids=[u for u in fulls[(model,setup)] if (source[u]['backend']=='native_full_tensorrt')==trt]
                assert len(ids)==1
                label=('trt_' if trt else '')+setup
                assert row[label+'_uid']==ids[0]
                close(row[label+'_fps'],fps[ids[0]],model+' '+label+' FPS')
                close(row[label+'_mj'],1000*energy[ids[0]],model+' '+label+' mJ/image')

    pairs = read(output/'tables/split_full_pairs.json')
    pair_ids = {(r['split_uid'], r['baseline_uid']) for r in pairs}
    expected_pair_ids={(u,b) for u,s in source.items() if s['kind']=='split'
                       for b in fulls[(s['model_id'],s['setup_id'])]}
    assert pair_ids==expected_pair_ids and len(pair_ids)==len(pairs)
    for r in pairs:
        u,b = r['split_uid'],r['baseline_uid']
        close(r['fps_ratio'],fps[u]/fps[b],u+' split/Full FPS')
        close(r['energy_ratio'],energy[u]/energy[b],u+' split/Full energy')
        close(r['energy_gain_same_full'],energy[b]/energy[u],u+' split/Full G_n')
    prior_contracts = read(inputs/'split_full_contracts.json')
    contract_map={(r['split_uid'],r['baseline_uid']):r for r in prior_contracts}
    for r in pairs:
        prior=contract_map.get((r['split_uid'],r['baseline_uid']))
        assert r['source_claim_flag']==(prior.get('claim_comparable') if prior else None)
        assert r['semantic_comparable']==(prior.get('semantic_comparable') if prior else None)
        assert r['original_semantic_reasons']==(prior.get('semantic_comparison_reasons',[]) if prior else [])
    required28 = {(r['split_uid'],r['baseline_uid']) for r in prior_contracts
                  if r.get('claim_comparable') and not r.get('semantic_comparable')}
    assert required28 <= pair_ids, ('Previously excluded Full pairs missing', required28-pair_ids)
    required3 = [r for r in source.values() if r['setup_id']=='H10' and r['task']=='classification'
                 and r['backend']=='native_full_tensorrt' and not r['normal_performance_claim']]
    for r in required3:
        assert paper[r['uid']]['fps'] is not None and not paper[r['uid']]['normal_performance_claim']

    ng = read(output/'tables/native_generic_pairs.json')
    groups = collections.defaultdict(list)
    for r in ng:
        n,g=r['native_uid'],r['generic_uid']
        assert source[n]['runner']=='native' and source[g]['runner']=='generic'
        assert all(source[n][k]==source[g][k] for k in ['model_id','setup_id','backend','case_id'])
        close(r['fps_ratio'],fps[n]/fps[g],n+' Native/Generic FPS')
        close(r['energy_ratio'],energy[n]/energy[g],n+' Native/Generic energy')
        groups[(source[n]['model_id'],source[n]['setup_id'])].append(r)
    medians = {key:{metric:statistics.median(r[metric] for r in rr)
                    for metric in ['fps_ratio','energy_ratio']} for key,rr in groups.items()}
    equal=read(output/'tables/equal_model_summary.json')
    for row in equal:
        for metric in ['fps_ratio','energy_ratio']:
            if row['setup']=='all':
                model_means=[statistics.mean(vals[metric] for (m,s),vals in medians.items() if m==model)
                             for model in sorted({m for m,s in medians})]
                expected=statistics.mean(model_means)
            else:
                expected=statistics.mean(vals[metric] for (m,s),vals in medians.items() if s==row['setup'])
            close(row[metric],expected,row['setup']+' equal-model '+metric)

    fastest_deployments = check_fastest_deployments(source, paper, fps, energy, output)
    summary=read(output/'data/summary.json')
    # Independently select every split optimum; plot/table agreement alone is insufficient.
    optima=read(output/'tables/model_setup_optima.json')
    populations=collections.defaultdict(list)
    for uid,row in source.items():
        if row['kind']=='split':
            populations[(row['model_id'],row['setup_id'],row['runner'])].append(uid)
    assert len(optima)==len(populations)
    assert {(r['model'],r['setup'],r['runner']) for r in optima}==set(populations)
    for row in optima:
        ids=populations[(row['model'],row['setup'],row['runner'])]
        fastest=min(ids,key=lambda u:(-fps[u],u))
        lowest=min(ids,key=lambda u:(energy[u],u))
        assert row['candidate_count']==len(ids) and row['multiple_candidates'] is (len(ids)>1)
        assert row['fastest_uid']==fastest and row['lowest_energy_uid']==lowest
        assert row['same_optimum'] is (fastest==lowest)
        for prefix,uid in [('fastest',fastest),('lowest_energy',lowest)]:
            close(row[prefix+'_fps'],fps[uid],uid+' optimum FPS')
            close(row[prefix+'_mj_per_image'],1000*energy[uid],uid+' optimum energy')
    assert summary['cases']==len(paper)
    assert summary['performance_coverage']==sum(v is not None for v in fps.values())
    assert summary['energy_coverage']==sum(v is not None for v in energy.values())
    assert summary['native_generic']['n_pairs']==len(ng)
    assert summary['all_runner_split_full']['n_pairs']==len(pairs)
    assert summary['historical_strict_excluded_pairs_retained']==len(required28)
    assert summary['nonclaim_performance_full_values_retained']==sum(r['kind']=='full' and not r['normal_performance_claim'] and fps[u] is not None for u,r in source.items())
    pareto, pareto_report = check_pareto(paper, output)

    # Figures retain an explicit payload of the points actually drawn. Check its
    # identities and values against this independently reconstructed population.
    figure_count=0
    figure_path=output/'figures/FIGURE_DATA.json'
    if figure_path.exists():
        figures=read(figure_path)
        figure_count=len(figures)
        baseline_figure = figures['fastest_split_baseline_comparison']
        tradeoff_figure = figures['fastest_deployment_tradeoff']
        for figure in [baseline_figure, tradeoff_figure]:
            assert figure['source_table'] == 'tables/table3_fastest_deployments.json'
            assert figure['reference_x'] == 1
        assert baseline_figure['x_scale'] == 'linear'
        assert tradeoff_figure['reference_y'] == 1
        assert tradeoff_figure['x_coordinate'] == 'R_global'
        assert tradeoff_figure['y_coordinate'] == 'energy_ratio_global'
        assert [p['model'] for p in baseline_figure['points']] == list(fastest_deployments)
        expected_missing = set()
        identity_fields = ['split_uid','global_full_uid','host_full_uid',
                           'split_setup','split_case','split_runner']
        for index,point in enumerate(baseline_figure['points']):
            row = fastest_deployments[point['model']]
            assert point['y'] == index
            assert all(point[k] == row[k] for k in identity_fields)
            missing = set()
            for scope in ['global','host']:
                metric = 'R_'+scope
                assert point[metric] == row[metric], ('Baseline plot coordinate',point['model'],metric)
                present = row[metric] is not None
                assert point[scope+'_plotted'] is present
                if not present:
                    missing.add(metric)
                    expected_missing.add((point['model'],scope,metric))
            assert {m['metric'] for m in point['missing_values']} == missing
            assert all(m['reason'] for m in point['missing_values'])
        assert {(p['model'],p['baseline'],p['coordinate']) for p in baseline_figure['omitted_points']} == expected_missing
        assert all(p['reason'] for p in baseline_figure['omitted_points'])
        plotted = unique(tradeoff_figure['points'], 'model')
        omitted = unique(tradeoff_figure['omitted_points'], 'model')
        expected_plotted = {m for m,r in fastest_deployments.items()
                            if r['R_global'] is not None and r['energy_ratio_global'] is not None}
        assert set(plotted) == expected_plotted
        assert set(omitted) == set(fastest_deployments)-expected_plotted
        for model,point in {**plotted,**omitted}.items():
            row = fastest_deployments[model]
            assert all(point[k] == row[k] for k in identity_fields)
            assert point['x'] == point['R_global'] == row['R_global'], ('Tradeoff FPS coordinate',model)
            assert point['y'] == point['energy_ratio_global'] == row['energy_ratio_global'], ('Tradeoff energy coordinate',model)
            if model in omitted:
                assert {v['metric'] for v in point['missing_values']} == {
                    k for k in ['R_global','energy_ratio_global'] if row[k] is None}
                assert all(v['reason'] for v in point['missing_values'])
        annotations = unique(tradeoff_figure['annotations'], 'model')
        assert set(annotations) == expected_plotted
        for model,annotation in annotations.items():
            assert annotation['split_uid'] == fastest_deployments[model]['split_uid']
            assert len(annotation['text_offset_points']) == 2
            assert all(finite_number(v) for v in annotation['text_offset_points'])
        full_ids={u for ids in fulls.values() for u in ids}
        for name,key,values in [('01_full_throughput','fps',fps),('02_full_energy','energy_mj_per_image',{u:1000*v for u,v in energy.items()})]:
            f=figures[name]
            assert set(f['scope_uids'])==full_ids
            assert {r['uid'] for r in f['points']}==full_ids
            for point in f['points']:
                close(point['value'],values[point['uid']],name+' '+point['uid'])
        for name in ['03a_native_generic_pooled','03c_native_generic_model_setup']:
            assert figures[name]['pairs']==ng
        for point in figures['03b_native_generic_equal_model']['model_setup_medians']:
            for metric in ['fps_ratio','energy_ratio']:
                close(point[metric],medians[(point['model'],point['setup'])][metric],'figure model/setup median')
        for point in figures['03b_native_generic_equal_model']['model_means_over_setups']:
            for metric in ['fps_ratio','energy_ratio']:
                expected=statistics.mean(vals[metric] for (m,s),vals in medians.items() if m==point['model'])
                close(point[metric],expected,'figure model mean over setups')
        equal_map={r['setup']:r for r in equal}
        for point in figures['03b_native_generic_equal_model']['setup_summaries']:
            t=equal_map['all' if point['setup']=='All' else point['setup']]
            close(point['mean_model_setup_medians'],t[point['metric']],'figure equal-model summary')
            assert point['n_models']==t['n_models']
        for model in sorted(models):
            ids={u for u,r in source.items() if r['model_id']==model}
            f=figures['04_tradeoff_'+model]
            plotted={u for u in ids if pareto[u]['included']}
            assert set(f['scope_uids'])==ids and set(unique(f['points']))==plotted
            assert set(f['omitted_uids'])==ids-plotted
            assert unique(f['omitted_points'])=={u:pareto[u] for u in ids-plotted}
            for point in f['points']:
                assert all(point[k]==v for k,v in pareto[point['uid']].items()), ('Exact plot/export point',point['uid'])
                close(point['fps'],fps[point['uid']],'figure tradeoff FPS')
                close(point['energy_mj_per_image'],1000*energy[point['uid']],'figure tradeoff energy')
                q=paper[point['uid']].get('quality_value')
                close(point['quality_percent'],100*q if q is not None else None,'figure tradeoff quality')
            front_payload=f['pareto_front']
            assert front_payload['grouping']==['model','setup']
            assert front_payload['objectives']=={'fps':'maximize','energy_mj_per_image':'minimize'}
            assert front_payload['quality_filter'] is False
            groups={(g['model'],g['setup']):g for g in front_payload['groups']}
            assert len(groups)==len(front_payload['groups'])
            assert set(groups)=={(model,paper[u]['setup_id']) for u in ids}
            expected_annotations=set()
            for (m,setup),group in groups.items():
                population={u for u in plotted if paper[u]['setup_id']==setup}
                front={u for u in population if pareto[u]['pareto_all']}
                coordinates=sorted({(paper[u]['fps'],paper[u]['energy_mj_per_image']) for u in front})
                assert sorted(group['front_uids'])==sorted(front), ('Figure front UIDs',m,setup)
                assert group['front_coordinates']==[{'fps':x,'energy_mj_per_image':y} for x,y in coordinates]
                assert group['n_observations']==len(population)
                assert group['n_front_uids']==len(front)
                assert group['n_front_coordinates']==len(coordinates)
                assert group['line_drawn'] is (len(coordinates)>1), ('Singleton front must have no line',m,setup)
                for uid in population:
                    if paper[uid]['kind']=='full':
                        label='TRT Full' if paper[uid]['backend']=='native_full_tensorrt' else 'Vendor Full'
                        expected_annotations.add((uid,label))
                for runner in ['native','generic']:
                    candidates=[u for u in population if paper[u]['kind']=='split' and paper[u]['runner']==runner]
                    if not candidates:
                        continue
                    fastest=min(candidates,key=lambda u:(-paper[u]['fps'],u))
                    lowest=min(candidates,key=lambda u:(paper[u]['energy_mj_per_image'],u))
                    prefix=runner[0].upper()+' '
                    if fastest==lowest:
                        expected_annotations.add((fastest,prefix+'F=E '+paper[fastest]['case_id']))
                    else:
                        expected_annotations.add((fastest,prefix+'F '+paper[fastest]['case_id']))
                        expected_annotations.add((lowest,prefix+'E '+paper[lowest]['case_id']))
            annotations=f['annotations']
            assert {(a['uid'],a['label']) for a in annotations}==expected_annotations, ('Figure F/E/Full annotations',model)
            assert len(annotations)==len(expected_annotations), ('Duplicate plot annotation',model)
            for a in annotations:
                assert a['model']==model and a['setup']==paper[a['uid']]['setup_id']
                assert len(a['text_offset_points'])==2 and all(finite_number(v) for v in a['text_offset_points'])
            qf=figures['06_quality_'+model]
            assert set(qf['scope_uids'])==ids
            for point in qf['points']:
                d=paper[point['uid']]
                close(point['quality_percent'],100*d['quality_value'],'figure absolute quality')
                close(point['reference_percent'],100*d['quality_reference_value'],'figure reference quality')
        f=figures['06_quality_reference_comparison']
        assert set(f['scope_uids'])==set(paper)
        quality_ids={u for u,r in paper.items() if r.get('quality_value') is not None and r.get('quality_reference_value') is not None}
        assert {r['uid'] for r in f['points']}==quality_ids
        assert set(f['missing_numeric_quality_uids'])==set(paper)-quality_ids
        for point in f['points']:
            d=paper[point['uid']]
            close(point['difference_percentage_points'],100*(d['quality_value']-d['quality_reference_value']),'figure quality percentage-point difference')
        optima=read(output/'tables/model_setup_optima.json')
        table_optima={(r['model'],r['setup'],r['runner']):r for r in optima}
        for r in figures['05_fastest_vs_min_energy']['optima']:
            t=table_optima[(r['model'],r['setup'],r['runner'])]
            assert all(r[k]==t[k] for k in ['candidate_count','fastest_uid','lowest_energy_uid','same_optimum'])
    return {'status':'PASS', 'dataset_cases':len(paper), 'energy_repeat_checks':sum(map(len,energies.values())),
            'fps_cohort_checks':len(fps), 'refresh_replacements':len(targets),
            'unchanged_complete_non_target_rows':len(source)-len(targets),
            'preserved_quality_rows':len(source),
            'metric_admission_preservation_scope':('A4 targets use actual canonical admission flags; all dataset-quality fields preserved'
                                                   if a4 else 'original quality and metric-admission gates preserved'),
            'full_configurations':sum(map(len,fulls.values())), 'table2_model_rows':len(table2),'table3_rows':len(table3),
            'native_generic_pairs':len(ng),'split_full_pairs':len(pairs),'verified_split_optima_groups':len(optima),
            'figure_payloads_checked':figure_count, 'fastest_deployment_models_checked':len(fastest_deployments),
            'pareto':pareto_report,'a4_repeats':a4_report,
            'external_migration_preservation':preservation,'canonical_selection_comparison':canonical,
            'restored_full_pairs_checked':len(required28), 'restored_h10_trt_classifier_values_checked':len(required3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--baseline-inputs',type=Path,help='Optional external pre-migration compact inputs, for the one-time full preservation audit')
    parser.add_argument('--canonical-inputs',type=Path,help='Optional active canonical compact inputs, for the one-time exact A4 source comparison')
    args = parser.parse_args()
    result = check(args.inputs,args.output,args.baseline_inputs,args.canonical_inputs)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
