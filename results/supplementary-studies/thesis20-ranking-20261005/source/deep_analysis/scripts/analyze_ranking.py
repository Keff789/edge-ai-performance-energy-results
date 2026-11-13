#!/usr/bin/env python3
"""Post-hoc B/C ranking, exact random shortlist and repeat sensitivity; no new runs.

Usage: python scripts/analyze_ranking.py --source-root ../ --output-root .
The source root contains the frozen inputs/ and scripts/project_rank_metrics.py.
"""
from __future__ import annotations
import argparse
import csv
import importlib.util
import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

STRATUM = ('model_id', 'setup_id', 'direction', 'precision', 'comparison_backend', 'output_endpoint_id', 'boundary_class')
TIERS = ('technical', 'qualitytransfer', 'reference_close')
NUMERIC = {'generic_completed_task_fps','native_completed_task_fps','historical_generic_raw_fps','native_over_generic_completed_task_ratio','fps','fps_min','fps_max','fps_sd','repetitions','repetition','completed_count','makespan_s','reported_fps','recomputed_fps','throughput_fps'}


def read_csv(path):
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key, value in row.items():
            if value == 'True': row[key] = True
            elif value == 'False': row[key] = False
            elif value == '': row[key] = None
            elif key in NUMERIC: row[key] = float(value)
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, separators=(',',':'), ensure_ascii=False) if isinstance(value,(list,dict)) else value for key,value in row.items()})


def identity(row):
    return row['model_id'], row['case_id'], row['setup_id'], row['comparison_backend']


def unique_index(rows, key=identity):
    result = {}
    for row in rows:
        ident = key(row)
        if ident in result:
            raise ValueError(f'duplicate identity: {ident}')
        result[ident] = row
    return result


def stratum(row):
    return tuple(str(row.get(key) or '') for key in STRATUM)


def admitted(row, tier):
    if row.get('eligible_for_technical_transfer') is not True: return False
    if tier == 'technical': return True
    if row.get('eligible_for_quality_transfer') is not True: return False
    return tier == 'qualitytransfer' or (row.get('generic_task_quality_status') == 'reference_close' and row.get('native_task_quality_status') == 'reference_close')


def regrets(selected, best):
    if selected <= 0 or best <= 0 or selected > best:
        raise ValueError('regret requires 0 < selected <= best')
    return 1 - selected / best, best / selected - 1


def random_shortlist(native_values, k):
    """Exact uniform k-subset expectation; each index remains a distinct candidate.

    Sorted position j is the maximum of C(j,k-1) subsets. Duplicate values are
    harmless: each subset has a unique last sorted position even under ties.
    """
    n = len(native_values)
    if not 1 <= k <= n: raise ValueError('invalid shortlist size')
    best = max(native_values)
    multiplicity = sum(value == best for value in native_values)
    total = math.comb(n,k)
    hit = 1 - (math.comb(n-multiplicity,k) if n-multiplicity >= k else 0) / total
    lr = lc = 0.0
    for j,value in enumerate(sorted(native_values)):
        if j >= k-1:
            weight = math.comb(j,k-1) / total
            loss, cost = regrets(value,best)
            lr += weight * loss
            lc += weight * cost
    return {'random_hit_probability':hit, 'random_expected_L_R':lr, 'random_expected_L_C':lc, 'random_subset_count':total}


def metric(rows, rank, generic_field='generic_completed_task_fps', native_field='native_completed_task_fps', minimum=3):
    n = len(rows)
    result = dict(n=n,status='insufficient_candidates' if n<minimum else 'ok',rho=None,tau_b=None,pairwise_concordance=None,comparable_pairs=0,top1_hit_stable=None,top1_hit_tie_aware=None,L_R=None,L_C=None,generic_selected_case=None,native_best_case=None,generic_top_ties=0,native_top_ties=0,tie_L_R_min=None,tie_L_R_max=None,tie_L_C_min=None,tie_L_C_max=None)
    if not rows: return result
    generic = [row[generic_field] for row in rows]
    native = [row[native_field] for row in rows]
    concordant, comparable = rank._pairwise_counts(generic,native)
    result['comparable_pairs'] = comparable
    generic_tops = [i for i,v in enumerate(generic) if v == max(generic)]
    native_tops = [i for i,v in enumerate(native) if v == max(native)]
    result.update(generic_top_ties=len(generic_tops),native_top_ties=len(native_tops))
    if n < minimum: return result
    selected, best = generic_tops[0],native_tops[0]  # original stable input order
    lr,lc = regrets(native[selected],native[best])
    losses = [regrets(native[i],native[best]) for i in generic_tops]
    result.update(rho=rank._spearman(generic,native),tau_b=rank._kendall_tau_b(generic,native),pairwise_concordance=concordant/comparable if comparable else None,top1_hit_stable=selected==best,top1_hit_tie_aware=selected in native_tops,L_R=lr,L_C=lc,generic_selected_case=rows[selected]['case_id'],native_best_case=rows[best]['case_id'],tie_L_R_min=min(x[0] for x in losses),tie_L_R_max=max(x[0] for x in losses),tie_L_C_min=min(x[1] for x in losses),tie_L_C_max=max(x[1] for x in losses))
    if result['rho'] is None: result['status']='constant_ranks'
    return result


def raw_join(pairs, raw):
    raw_index = unique_index([dict(row, comparison_backend='deepx' if row['comparison_backend']=='deepx_m1' else row['comparison_backend'], historical_backend_label=row['comparison_backend']) for row in raw if row['variant']=='split'])
    common=[];audit=[]
    for pair in pairs:
        if pair['observation_origin'] != 'base': continue
        rr=raw_index.get(identity(pair))
        embedded=pair.get('historical_generic_raw_fps')
        if rr is None or embedded is None:
            audit.append(dict(zip(('model_id','case_id','setup_id','comparison_backend'),identity(pair)),join_status='missing_raw',used=False))
            continue
        if not math.isclose(embedded,rr['throughput_fps'],rel_tol=1e-12,abs_tol=1e-12):
            raise ValueError(f'raw projection mismatch: {identity(pair)}')
        # The historical input has no precision/endpoint columns populated; the
        # exact frozen completion-plan projection binds the raw number above.
        common.append(dict(pair,historical_generic_raw_fps=rr['throughput_fps']))
        audit.append(dict(zip(('model_id','case_id','setup_id','comparison_backend'),identity(pair)),join_status='unique_identity_and_frozen_projection_match',used=True,raw_endpoint=rr['measurement_endpoint'],historical_backend_label=rr['historical_backend_label'],raw_precision_available=bool(rr.get('precision')),raw_endpoint_id_available=bool(rr.get('endpoint_id')),raw_fps=rr['throughput_fps'],completion_fps=pair['generic_completed_task_fps'],native_fps=pair['native_completed_task_fps']))
    return common,audit


def analyze(source_root, output_root):
    spec=importlib.util.spec_from_file_location('frozen_rank_metrics', source_root/'scripts/project_rank_metrics.py')
    rank=importlib.util.module_from_spec(spec);spec.loader.exec_module(rank)
    pairs=read_csv(source_root/'inputs/completion_pairs.csv')
    native=read_csv(source_root/'inputs/native_cases.csv')
    generic=read_csv(source_root/'inputs/generic_cases.csv')
    repeats=read_csv(source_root/'inputs/performance_repeats.csv')
    raw=read_csv(source_root/'inputs/generic_raw.csv')
    unique_index(pairs)
    nmap=unique_index([r for r in native if r['execution_mode']=='split'])
    gmap=unique_index(generic)
    if set(nmap)!=set(gmap) or set(nmap)!=set(unique_index(pairs)):
        raise ValueError('completed pair identity mismatch')
    repmap=defaultdict(list)
    for rep in repeats:
        if rep['execution_mode']=='split': repmap[(rep['measurement'],identity(rep))].append(rep)
        if not math.isclose(rep['completed_count']/rep['makespan_s'],rep['reported_fps'],rel_tol=1e-8,abs_tol=1e-6):
            raise ValueError('count/makespan mismatch')
    case_rows=[]
    for pair in pairs:
        nn=nmap[identity(pair)];gg=gmap[identity(pair)]
        for record in (nn,gg):
            if record['precision'] != pair['precision']:
                raise ValueError('precision mismatch')
        if gg['endpoint_id'] != pair['output_endpoint_id']:
            raise ValueError('generic pair endpoint mismatch')
        nr=sorted(repmap[('native_completed',identity(pair))],key=lambda r:r['repetition'])
        gr=sorted(repmap[('generic_completed',identity(pair))],key=lambda r:r['repetition'])
        if len(nr)!=3 or len(gr)!=3 or len({r['repetition'] for r in nr})!=3 or len({r['repetition'] for r in gr})!=3:
            raise ValueError('requires exactly three distinct repeats per runner')
        for reps,field in ((nr,'native_completed_task_fps'),(gr,'generic_completed_task_fps')):
            if not math.isclose(statistics.median(x['recomputed_fps'] for x in reps),pair[field],rel_tol=1e-8,abs_tol=1e-6): raise ValueError('median mismatch')
        case_rows.append(dict(pair,native_report_endpoint_id=nn['endpoint_id'],generic_report_endpoint_id=gg['endpoint_id'],literal_report_endpoint_equal=nn['endpoint_id']==gg['endpoint_id'],native_runner=nn.get('source_runner'),native_command_sha256=nn.get('command_sha256'),S=pair['native_completed_task_fps']/pair['generic_completed_task_fps'],native_min=min(r['recomputed_fps'] for r in nr),native_max=max(r['recomputed_fps'] for r in nr),generic_min=min(r['recomputed_fps'] for r in gr),generic_max=max(r['recomputed_fps'] for r in gr),native_repeats=[r['recomputed_fps'] for r in nr],generic_repeats=[r['recomputed_fps'] for r in gr],native_counts=[r['completed_count'] for r in nr],generic_counts=[r['completed_count'] for r in gr],native_makespans=[r['makespan_s'] for r in nr],generic_makespans=[r['makespan_s'] for r in gr]))
    common,join_audit=raw_join(pairs,raw)
    groups=[];shortlists=[];rep_rows=[];rep_summary=[];proxy=[]
    for cohort,cohort_pairs in [('base',[r for r in pairs if r['observation_origin']=='base']),('augmented',pairs)]:
        grouped=defaultdict(list)
        for row in cohort_pairs: grouped[stratum(row)].append(row)
        for keys,all_rows in sorted(grouped.items()):
            for tier in TIERS:
                rows=[r for r in all_rows if admitted(r,tier)]
                meta=dict(zip(STRATUM,keys),cohort=cohort,tier=tier,family='detection' if keys[0].startswith('yolo') else 'classification')
                groups.append(dict(meta,planned_n=len(all_rows),excluded_n=len(all_rows)-len(rows),**metric(rows,rank)))
                if len(rows)>=4:
                    ordered=sorted(rows,key=lambda r:-r['generic_completed_task_fps'])
                    best=max(r['native_completed_task_fps'] for r in rows)
                    for k in (2,3):
                        shortlist=ordered[:k]
                        selected=max(shortlist,key=lambda r:r['native_completed_task_fps'])
                        lr,lc=regrets(selected['native_completed_task_fps'],best)
                        random=random_shortlist([r['native_completed_task_fps'] for r in rows],k)
                        shortlists.append(dict(meta,n=len(rows),k=k,candidates=[r['case_id'] for r in shortlist],contains_native_best=selected['native_completed_task_fps']==best,L_R=lr,L_C=lc,**random,improvement_over_random_L_R=random['random_expected_L_R']-lr,improvement_over_random_L_C=random['random_expected_L_C']-lc))
                if len(rows)>=3:
                    current=[]
                    for gi,ni in itertools.product(range(3),repeat=2):
                        rr=[]
                        for row in rows:
                            gr=sorted(repmap[('generic_completed',identity(row))],key=lambda r:r['repetition'])
                            nr=sorted(repmap[('native_completed',identity(row))],key=lambda r:r['repetition'])
                            rr.append(dict(row,generic_completed_task_fps=gr[gi]['recomputed_fps'],native_completed_task_fps=nr[ni]['recomputed_fps']))
                        result=dict(meta,generic_repetition_index=gi,native_repetition_index=ni,**metric(rr,rank));rep_rows.append(result);current.append(result)
                    summary=dict(meta,n=len(rows),combination_count=len(current),top1_hits=sum(r['top1_hit_tie_aware'] for r in current),generic_selected_cases=sorted({r['generic_selected_case'] for r in current}),native_best_cases=sorted({r['native_best_case'] for r in current}))
                    for field in ('rho','tau_b','L_R','L_C'):
                        vv=[r[field] for r in current if r[field] is not None]
                        summary.update({field+'_min':min(vv) if vv else None,field+'_max':max(vv) if vv else None,field+'_median':statistics.median(vv) if vv else None})
                    rep_summary.append(summary)
    grouped=defaultdict(list)
    for row in common:grouped[stratum(row)].append(row)
    for keys,all_rows in sorted(grouped.items()):
        for tier in TIERS:
            rows=[r for r in all_rows if admitted(r,tier)]
            meta=dict(zip(STRATUM,keys),tier=tier,n_common=len(rows))
            historical=metric(rows,rank,generic_field='historical_generic_raw_fps'); completed=metric(rows,rank)
            rr=dict(meta,case_ids=[r['case_id'] for r in rows],**{'raw_'+k:v for k,v in historical.items()},**{'completion_'+k:v for k,v in completed.items()})
            for name in ('rho','tau_b','L_R','L_C'):
                rr['delta_completion_minus_raw_'+name]=completed[name]-historical[name] if completed[name] is not None and historical[name] is not None else None
            proxy.append(rr)
    sensitivity=[]
    exclusions=[('none',set()),('without_regnet_h10',{('regnet_x_1_6gf','H10')}),('without_resnet_h10',{('resnet50','H10')}),('without_yolov7_h8',{('yolov7_paper','H8')}),('without_three_reported_counterexamples',{('regnet_x_1_6gf','H10'),('resnet50','H10'),('yolov7_paper','H8')})]
    for cohort,tier,family in itertools.product(('base','augmented'),TIERS,('all','classification','detection')):
        eligible=[r for r in groups if r['cohort']==cohort and r['tier']==tier and r['n']>=3 and (family=='all' or r['family']==family)]
        for label,exclude in exclusions:
            selected=[r for r in eligible if (r['model_id'],r['setup_id']) not in exclude]
            if not selected:continue
            sensitivity.append(dict(cohort=cohort,tier=tier,family=family,sensitivity=label,eligible_groups_before=len(eligible),n_groups=len(selected),n_candidates=sum(r['n'] for r in selected),top1_hits=sum(r['top1_hit_tie_aware'] for r in selected),median_group_L_R=statistics.median(r['L_R'] for r in selected),median_group_L_C=statistics.median(r['L_C'] for r in selected),mean_group_L_R=statistics.mean(r['L_R'] for r in selected),mean_group_L_C=statistics.mean(r['L_C'] for r in selected),max_group_L_R=max(r['L_R'] for r in selected),max_group_L_C=max(r['L_C'] for r in selected)))
    tables={'rank_cases.csv':case_rows,'rank_groups.csv':groups,'rank_shortlists.csv':shortlists,'rank_repeat_combinations.csv':rep_rows,'rank_repeat_sensitivity.csv':rep_summary,'rank_raw_join_audit.csv':join_audit,'rank_proxy_comparison.csv':proxy,'rank_dominant_case_sensitivity.csv':sensitivity}
    for name,rows in tables.items():write_csv(output_root/'tables'/name,rows)
    findings={'posthoc':True,'source_role':'frozen_public_analysis','counts':{'technical':sum(admitted(r,'technical') for r in pairs),'qualitytransfer':sum(admitted(r,'qualitytransfer') for r in pairs),'reference_close':sum(admitted(r,'reference_close') for r in pairs),'base':sum(r['observation_origin']=='base' for r in pairs),'augmentation':sum(r['observation_origin']=='augmentation' for r in pairs),'exact_raw_common':len(common)},'sensitivity':sensitivity,'tables':{name:len(rows) for name,rows in tables.items()},'full_references_used':0,'historical_attestor_gap_effect_on_these_split_rankings':'not_applicable_no_full_reference_used','tie_rule':'exact equality, average ranks; stable source row order for original Top1, additional tie-aware hit','random_shortlist':'exact expectation of uniform k-subsets without replacement; oracle best Native within shortlist','repeat_rule':'nine dependent combinations of three observed repeats; no confidence interval','raw_identity_limit':'raw CSV has no populated precision or endpoint IDs; explicit deepx_m1-to-deepx alias and model/case/setup/backend unique join additionally verifies the frozen original-plan raw FPS projection','cohort_rules':{'technical':'existing technical gate','qualitytransfer':'technical and existing qualitytransfer gate; includes accuracy_loss','reference_close':'qualitytransfer and both runner statuses reference_close'},'caveat':'runtime_conditions_comparable remains false; no causal isolation or held-out selector accuracy'}
    (output_root/'ranking_results.json').write_text(json.dumps(findings,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'counts':findings['counts'],'tables':findings['tables']},indent=2))



def extract_path_evidence(private_index, private_replay_root, output_root):
    """Optional bounded projection of nine case records; never executes source code."""
    targets = {('regnet_x_1_6gf','b052','H10'),('regnet_x_1_6gf','b123','H10'),('resnet50','b002','H10'),('resnet50','b095','H10'),('yolov7_paper','b044','H8'),('yolov7_paper','b066','H8'),('mobilenet_v3_large','b027','H8'),('mobilenet_v3_large','b001','DeepX'),('yolov7_paper','b066','H10')}
    setup_map={'orin_nx_hailo8_01':'H8','orin_nx_hailo10_01':'H10','orin_nx_deepx_m1_01':'DeepX'}
    sources=json.loads(private_index.read_text())['selected_native_sources']
    generic_sources={}
    for cohort in ('base','augmentation'):
        rows=json.loads((private_replay_root/cohort/'generic_completion_observations.json').read_text())['rows']
        for row in rows:
            key=(row['model_id'],row['case_id'],setup_map[row['setup_id']])
            if key in targets:generic_sources[key]=(cohort,row)
    evidence=[]
    for source in sources:
        model,case,setup,*_=source['identity'];key=(model,case,setup_map[setup])
        if key not in targets:continue
        contract=source['native_command_contract'];report=json.loads(Path(source['report']).read_text());cohort,observation=generic_sources[key]
        generic=json.loads(Path(observation['result_path']).read_text());rep=generic['repetitions'][0]
        binding=generic['input_binding'];options=contract['runtime_options']
        native_artifacts=contract['artifacts'];generic_artifacts=generic['expected_runtime_artifacts']
        prepared=[value.get('sha256') for name,value in native_artifacts.items() if 'prepared_input' in name or name=='prepared_feed']
        generic_prepared=binding.get('prepared_input',{}).get('sha256')
        native_engine=native_artifacts.get('engine',{}).get('sha256');generic_engine=generic_artifacts.get('engine',{}).get('sha256')
        native_hef=native_artifacts.get('hef',{}).get('sha256');generic_hef=generic_artifacts.get('part1_runtime',{}).get('sha256')
        endpoint_contract=options.get('completion_execution_contract') or {}
        row=dict(model_id=model,case_id=case,setup_id=setup_map[setup],cohort=cohort,precision=contract['precision'],native_source_role='BASE' if source['cohort']=='base' else 'YOLO',native_report_relative='native_producers/'+source['report'].split('/native_producers/',1)[1],generic_source_role='COMPLETION192' if cohort=='base' else 'YOLO',generic_source_filename=Path(observation['result_path']).name,native_command_sha256=contract['contract_sha256'],native_runner=contract['runner'],native_runner_sha256=contract['runner_sha256'],native_producer=report.get('producer_impl'),native_queue_depth=options.get('queue_depth'),native_inflight=options.get('inflight'),native_post_queue_depth=options.get('post_queue_depth'),native_measurement_boundary=report.get('measurement_boundary'),native_preprocessing_included=report.get('preprocessing_included'),native_postprocess_included=report.get('postprocess_included'),native_completed_stage=report.get('completed_task_stage'),native_completion_execution_policy=endpoint_contract.get('execution_policy'),native_postprocess_policy=(endpoint_contract.get('processor_contract') or {}).get('execution_policy'),native_completion_runtime_mode=report.get('completion_runtime_mode'),native_completion_oracle_location=report.get('quality_oracle_location'),native_warmup=options.get('warmup'),native_frames=options.get('frames'),generic_worker_count=rep.get('worker_count'),generic_queue_depth=rep.get('queue_depth'),generic_measurement_boundary=rep.get('measurement_boundary'),generic_fill_drain_included=rep.get('fill_and_drain_included'),generic_preprocessing_timed=rep.get('preprocessing_timed'),generic_postprocess_timed=rep.get('postprocess_timed'),generic_materialization_timed=rep.get('output_materialization_timed'),generic_warmup=rep.get('warmup_completed_count'),generic_frames=rep.get('completed_task_count'),generic_created_at=generic.get('created_at'),generic_completed_at=generic.get('completed_at'),native_wallclock_timestamp=None,source_image_sha_equal=contract.get('input_image_sha256')==binding.get('source_image_sha256'),prepared_input_sha_equal=generic_prepared in prepared if prepared and generic_prepared else None,engine_sha_equal=native_engine==generic_engine if native_engine and generic_engine else None,part1_sha_equal=native_hef==generic_hef if native_hef and generic_hef else None,generic_batch_size=binding.get('batch_size'),generic_input_sequence=binding.get('sequence'),thread_affinity_equality=None,thermal_equality=None,clock_equality=None)
        for field in ('p1_ms','p1_effective_cycle_ms','consumer_effective_cycle_ms','fifo_put_block_ms','queue_wait_ms','handoff_ms','p2_run_ms','completion_tail_ms','trt_input_bytes'):
            row['native_report_last_or_summary_'+field]=report.get(field)
        evidence.append(row)
    if len(evidence)!=len(targets):raise ValueError('countercase evidence missing')
    write_csv(output_root/'inputs/ranking_path_evidence.csv',sorted(evidence,key=lambda r:(r['model_id'],r['setup_id'],r['case_id'])))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--private-source-index',type=Path)
    parser.add_argument('--private-replay-root',type=Path)
    args=parser.parse_args();args.output_root.mkdir(parents=True,exist_ok=True)
    if args.private_source_index or args.private_replay_root:
        if not (args.private_source_index and args.private_replay_root):parser.error('both private projection arguments are required')
        extract_path_evidence(args.private_source_index,args.private_replay_root,args.output_root)
    analyze(args.source_root,args.output_root)

if __name__=='__main__':main()
