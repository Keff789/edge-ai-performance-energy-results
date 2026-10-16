#!/usr/bin/env python3
"""Compare frozen ranking methods on exactly matched measured candidates offline."""
from __future__ import annotations
import argparse,csv,importlib.util,itertools,json,math,statistics
from collections import defaultdict
from pathlib import Path
STRATUM=('model_id','setup_id','direction','precision','comparison_backend','output_endpoint_id','boundary_class')
TIERS=('technical','qualitytransfer','reference_close')
MEASURED_COMPLETION='measured_generic_completion'
MEASURED_RAW='measured_generic_raw'

def read_csv(path):
    def convert(v):
        if v=='':return None
        if v in ('True','False'):return v=='True'
        if v[:1] in ('[','{'):
            try:return json.loads(v)
            except ValueError:pass
        try:
            f=float(v)
            return int(f) if math.isfinite(f) and f.is_integer() else f
        except ValueError:return v
    with path.open(newline='') as f:return [{k:convert(v) for k,v in r.items()} for r in csv.DictReader(f)]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,sort_keys=True,separators=(',',':')) if isinstance(v,(dict,list,tuple)) else v for k,v in r.items()})

def import_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def exact_index(rows,fields):
    out={}
    for r in rows:
        key=tuple(r[k] for k in fields)
        if key in out:raise ValueError(f'duplicate exact identity {key}')
        out[key]=r
    return out

def pair_identity(r):return tuple(r[k] for k in ('model_id','case_id','setup_id','comparison_backend'))
def group_key(r):return tuple(str(r.get(k) or '') for k in STRATUM)
def score_key(r):return tuple(r[k] for k in ('model_id','case_id','setup_id','method'))
def utility(score,direction):
    if not isinstance(score,(int,float)) or not math.isfinite(score):return None
    if direction in ('ascending','lower_is_better','min'):return -score
    if direction in ('descending','higher_is_better','max'):return score
    raise ValueError(f'unknown score direction {direction}')

def eligible(r,tier):
    if r['eligible_for_technical_transfer'] is not True:return False
    if tier=='technical':return True
    if r['eligible_for_quality_transfer'] is not True:return False
    return tier=='qualitytransfer' or (r['generic_task_quality_status']=='reference_close' and r['native_task_quality_status']=='reference_close')

def regrets(selected,best):
    if not 0<selected<=best:raise ValueError('requires 0<selected<=best')
    return 1-selected/best,best/selected-1

def random_metrics(native,k):
    n=len(native)
    if not 1<=k<=n:raise ValueError('invalid k')
    best=max(native);m=sum(v==best for v in native);count=math.comb(n,k)
    hit=1-(math.comb(n-m,k) if n-m>=k else 0)/count
    lr=lc=0
    for j,v in enumerate(sorted(native)):
        if j>=k-1:
            weight=math.comb(j,k-1)/count;a,b=regrets(v,best);lr+=weight*a;lc+=weight*b
    return dict(random_native_best_hit_probability=hit,random_expected_L_R=lr,random_expected_L_C=lc,random_native_topk_recall=k/n,random_subset_count=count)

def evaluate_group(rows,rank,planned_n=None):
    """Rows retain original pair order; score tie order is explicit per method."""
    planned_n=len(rows) if planned_n is None else planned_n
    available=[r for r in rows if r.get('utility') is not None]
    out=dict(n=planned_n,n_scored=len(available),n_missing=planned_n-len(available),candidate_ids=[r['case_id'] for r in rows],
        status='incomplete_method_coverage' if len(available)!=planned_n else 'insufficient_candidates' if planned_n<3 else 'ok',
        rho=None,tau_b=None,top1_hit_stable=None,top1_hit_tie_aware=None,L_R=None,L_C=None,selected_case=None,native_best_case=None,
        score_top_ties=None,tie_L_R_min=None,tie_L_R_max=None,tie_L_C_min=None,tie_L_C_max=None,energy_excess_fraction=None,energy_lost_savings_fraction=None,
        energy_selected_j_per_task=None,energy_best_j_per_task=None,energy_best_case=None,energy_top1_hit=None,random_expected_energy_excess=None,
        tie_energy_excess_min=None,tie_energy_excess_max=None,native_oracle_energy_excess_fraction=None)
    if out['status']!='ok':return out
    native=[r['native_fps'] for r in rows];utils=[r['utility'] for r in rows]
    order=sorted(range(len(rows)),key=lambda i:(-utils[i],rows[i]['original_order'],rows[i]['pair_order']))
    selected=order[0];best=max(range(len(rows)),key=lambda i:native[i]);tops=[i for i,v in enumerate(utils) if v==max(utils)];lr,lc=regrets(native[selected],native[best]);tie_losses=[regrets(native[i],native[best]) for i in tops]
    j=[r['j_per_task'] for r in rows];jbest=min(j);ej=j[selected]/jbest-1
    out.update(rho=rank._spearman(utils,native),tau_b=rank._kendall_tau_b(utils,native),top1_hit_stable=selected==best,top1_hit_tie_aware=native[selected]==native[best],
        L_R=lr,L_C=lc,selected_case=rows[selected]['case_id'],native_best_case=rows[best]['case_id'],score_top_ties=len(tops),
        tie_L_R_min=min(v[0] for v in tie_losses),tie_L_R_max=max(v[0] for v in tie_losses),tie_L_C_min=min(v[1] for v in tie_losses),tie_L_C_max=max(v[1] for v in tie_losses),
        energy_excess_fraction=ej,energy_lost_savings_fraction=1-jbest/j[selected],energy_selected_j_per_task=j[selected],energy_best_j_per_task=jbest,energy_best_case=rows[j.index(jbest)]['case_id'],energy_top1_hit=j[selected]==jbest,
        random_expected_energy_excess=statistics.mean(j)/jbest-1,tie_energy_excess_min=min(j[i]/jbest-1 for i in tops),tie_energy_excess_max=max(j[i]/jbest-1 for i in tops),native_oracle_energy_excess_fraction=j[best]/jbest-1,
        **random_metrics(native,1))
    if out['rho'] is None:out['status']='constant_scores'
    return out

def shortlist_metrics(rows,k):
    n=len(rows);native=[r['native_fps'] for r in rows];best=max(native)
    order=sorted(range(n),key=lambda i:(-rows[i]['utility'],rows[i]['original_order'],rows[i]['pair_order']))
    native_order=sorted(range(n),key=lambda i:(-native[i],rows[i]['pair_order']))
    chosen=order[:k];nativetop=native_order[:k];nv=max(native[i] for i in chosen);lr,lc=regrets(nv,best)
    threshold=rows[order[k-1]]['utility'];forced=[i for i in order if rows[i]['utility']>threshold];ties=[i for i in order if rows[i]['utility']==threshold];slots=k-len(forced)
    possibilities=math.comb(len(ties),slots)
    # Best/worst Native value attained across exact boundary-tie resolutions.
    tie_values=sorted(native[i] for i in ties);forced_best=max([native[i] for i in forced],default=0)
    worst_best=max(forced_best,tie_values[slots-1]);best_best=max(forced_best,tie_values[-1]);minlr,minlc=regrets(best_best,best);maxlr,maxlc=regrets(worst_best,best)
    return dict(n=n,k=k,trivial_k_equals_n=k==n,candidate_ids=[rows[i]['case_id'] for i in chosen],native_best_recall=nv==best,native_topk_recall=len(set(chosen)&set(nativetop))/k,
        L_R=lr,L_C=lc,boundary_tie_size=len(ties),boundary_tie_slots=slots,boundary_tie_resolutions=possibilities,tie_L_R_min=minlr,tie_L_R_max=maxlr,tie_L_C_min=minlc,tie_L_C_max=maxlc,**random_metrics(native,k))

def summarize(rows):
    good=[r for r in rows if r['status'] in ('ok','constant_scores')]
    return dict(group_count=len(rows),evaluable_group_count=len(good),insufficient_group_count=sum(r['status']=='insufficient_candidates' for r in rows),unavailable_group_count=sum(r['status']=='incomplete_method_coverage' for r in rows),out_of_scope_group_count=sum(r['status']=='raw_evaluated_only_on_base_intersection' for r in rows),
        evaluated_candidate_count=sum(r['n'] for r in good),top1_hits=sum(r['top1_hit_tie_aware'] for r in good),energy_top1_hits=sum(r['energy_top1_hit'] for r in good),score_top_tie_groups=sum(r['score_top_ties']>1 for r in good),
        **{metric+'_'+agg:(fn([r[metric] for r in good if r[metric] is not None]) if any(r[metric] is not None for r in good) else None) for metric in ['rho','tau_b','L_R','L_C','energy_excess_fraction','random_expected_L_R','random_expected_L_C','random_expected_energy_excess'] for agg,fn in [('median',statistics.median),('mean',statistics.mean),('max',max)]})

def analyze(source,method_root,output,deep_root=None):
    deep_root=Path(deep_root) if deep_root is not None else source/'deep_analysis'
    rank=import_file('released_pure_rank_metrics',source/'scripts/project_rank_metrics.py')
    old=import_file('released_deep_rank_analysis',deep_root/'scripts/analyze_ranking.py')
    pairs=read_csv(source/'inputs/completion_pairs.csv');exact_index(pairs,('model_id','case_id','setup_id','comparison_backend'))
    raw_common,raw_audit=old.raw_join(pairs,read_csv(source/'inputs/generic_raw.csv'));raw_ids={pair_identity(r) for r in raw_common}
    native_cases=exact_index([r for r in read_csv(source/'inputs/native_cases.csv') if r['execution_mode']=='split'],('model_id','case_id','setup_id','comparison_backend'))
    generic_cases=exact_index(read_csv(source/'inputs/generic_cases.csv'),('model_id','case_id','setup_id','comparison_backend'))
    energies=exact_index([r for r in read_csv(deep_root/'tables/energy_cases.csv') if r['execution_mode']=='native_split'],('model_id','case_id','setup_id','comparison_backend'))
    reps=defaultdict(list)
    for r in read_csv(source/'inputs/performance_repeats.csv'):
        if r['execution_mode']=='split':reps[(r['measurement'],pair_identity(r))].append(r)
    ereps=defaultdict(list)
    for r in read_csv(source/'inputs/energy_repeats.csv'):
        if r['case_id']!='full':ereps[pair_identity(r)].append(r)
    case_metrics=[]
    for i,p in enumerate(pairs):
        ident=pair_identity(p);e=energies[ident];ng=native_cases[ident];gg=generic_cases[ident]
        assert ng['precision']==gg['precision']==p['precision']
        assert ng['backend']==gg['backend']==e['backend']==p['direction']
        assert ng['cohort']==gg['cohort']==e['cohort']==p['observation_origin']
        assert p['measurement_boundaries_comparable'] is True
        for record in (ng,gg,e):
            for field in ['direction','boundary_class']:
                if record.get(field) is not None:assert record[field]==p[field]
        # Detection Native report endpoints can be canonicalized differently;
        # preserve the established pair contract instead of inventing literal equality.
        assert gg['endpoint_id']==p['output_endpoint_id']
        assert e['precision']==ng['precision'] and e['endpoint_id']==ng['endpoint_id']
        nr=sorted(reps[('native_completed',ident)],key=lambda r:r['repetition']);gr=sorted(reps[('generic_completed',ident)],key=lambda r:r['repetition']);er=sorted(ereps[ident],key=lambda r:r['repetition'])
        for rr in [nr,gr,er]:assert len(rr)==3 and {r['repetition'] for r in rr}=={0,1,2}
        js=[r['energy_j']/r['completed_count'] for r in er]
        assert math.isclose(statistics.mean(js),e['j_per_task_mean'],rel_tol=1e-12)
        for rr,field in [(nr,'native_completed_task_fps'),(gr,'generic_completed_task_fps')]:assert math.isclose(statistics.median(r['recomputed_fps'] for r in rr),p[field],rel_tol=1e-8)
        case_metrics.append(dict(p,pair_order=i,native_fps=p['native_completed_task_fps'],j_per_task=e['j_per_task_mean'],energy_case_uid=e['case_uid'],energy_physical_scope=e['physical_scope'],energy_window=e['window'],calibration_sha256=e['calibration_sha256'],
            native_repeats=[r['recomputed_fps'] for r in nr],generic_repeats=[r['recomputed_fps'] for r in gr],energy_repeats=js))
    all_scores=read_csv(method_root/'inputs/method_candidate_scores.csv');availability=read_csv(method_root/'inputs/method_availability.csv')
    static_methods=sorted({r['method'] for r in all_scores+availability if r['method'] not in [MEASURED_RAW,MEASURED_COMPLETION]})
    scoremap=exact_index([r for r in all_scores if r['method'] in static_methods],('model_id','case_id','setup_id','method'))
    methods=static_methods+[MEASURED_RAW,MEASURED_COMPLETION]
    groups=[];caseranks=[];shorts=[];reprows=[];repsumm=[];energyreprows=[];energyrepsumm=[];coverage=[];energycross=[]
    grouped=defaultdict(list)
    for c in case_metrics:grouped[group_key(c)].append(c)
    for cohort in ['base','augmented']:
        for gkey,allrows in sorted(grouped.items()):
            cohortrows=[r for r in allrows if cohort=='augmented' or r['observation_origin']=='base']
            for tier in TIERS:
                selected=[r for r in cohortrows if eligible(r,tier)]
                if selected:
                    for field in ['energy_physical_scope','energy_window','calibration_sha256']:assert len({r[field] for r in selected})==1
                for method in methods:
                    meta=dict(zip(STRATUM,gkey),cohort=cohort,tier=tier,method=method,family='detection' if gkey[0].startswith('yolo') else 'classification')
                    if method==MEASURED_RAW and cohort=='augmented':
                        groups.append(dict(meta,n=len(selected),n_scored=sum(pair_identity(r) in raw_ids for r in selected),n_missing=sum(pair_identity(r) not in raw_ids for r in selected),status='raw_evaluated_only_on_base_intersection',candidate_ids=[r['case_id'] for r in selected]));continue
                    rr=[]
                    for c in selected:
                        if method in (MEASURED_RAW,MEASURED_COMPLETION):
                            score=c['generic_completed_task_fps'] if method==MEASURED_COMPLETION else c.get('historical_generic_raw_fps') if pair_identity(c) in raw_ids else None
                            sr=dict(score=score,score_direction='descending',original_order=c['pair_order'],derivation_status='existing_measured_proxy',source_role='original_completed_pair_projection' if method==MEASURED_COMPLETION else 'exact_base_raw_join')
                        else:
                            exact=scoremap.get((c['model_id'],c['case_id'],c['setup_id'],method))
                            shared=scoremap.get((c['model_id'],c['case_id'],'all',method))
                            if exact and shared:raise ValueError('ambiguous exact/shared method score')
                            sr=exact or shared or {}
                        score=sr.get('score');u=utility(score,sr.get('score_direction')) if score is not None else None
                        rr.append(dict(c,score=score,utility=u,original_order=sr.get('original_order',c['pair_order']),score_direction=sr.get('score_direction'),score_source_role=sr.get('source_role'),score_derivation_status=sr.get('derivation_status'),source_list_order=sr.get('source_list_order',c['pair_order'])))
                    result=evaluate_group(rr,rank)
                    if result['status'] in ('ok','constant_scores'):
                        alt=evaluate_group([dict(r,original_order=r['source_list_order']) for r in rr],rank)
                        result.update(source_list_order_selected_case=alt['selected_case'],source_list_order_changes_top1=alt['selected_case']!=result['selected_case'],source_list_order_L_R=alt['L_R'],source_list_order_energy_excess=alt['energy_excess_fraction'])
                    groups.append(dict(meta,quality_excluded_n=len(cohortrows)-len(selected),**result))
                    coverage.append(dict(meta,expected_candidate_ids=[r['case_id'] for r in rr],scored_candidate_ids=[r['case_id'] for r in rr if r['utility'] is not None],missing_candidate_ids=[r['case_id'] for r in rr if r['utility'] is None],n=len(rr),n_scored=result['n_scored'],status=result['status']))
                    ready=result['status'] in ('ok','constant_scores')
                    valid=[r for r in rr if r['utility'] is not None]
                    score_ranks=rank._rank([-r['utility'] for r in valid]);nranks=rank._rank([-r['native_fps'] for r in valid])
                    rmap={r['case_id']:(a,b) for r,a,b in zip(valid,score_ranks,nranks)}
                    for r in rr:
                        a,b=rmap.get(r['case_id'],(None,None));caseranks.append(dict(meta,case_id=r['case_id'],observation_origin=r['observation_origin'],score=r['score'],score_direction=r['score_direction'],original_order=r['original_order'],source_list_order=r['source_list_order'],score_source_role=r['score_source_role'],score_derivation_status=r['score_derivation_status'],method_rank=a,native_rank=b,native_fps=r['native_fps'],j_per_task=r['j_per_task'],energy_case_uid=r['energy_case_uid'],generic_task_quality_status=r['generic_task_quality_status'],native_task_quality_status=r['native_task_quality_status'],full_group_evaluable=ready))
                    if not ready:continue
                    energy_selected=next(r for r in rr if r['case_id']==result['selected_case']);energy_best=next(r for r in rr if r['case_id']==result['energy_best_case'])
                    cross=[]
                    for si,bi in itertools.product(range(3),repeat=2):
                        ex=energy_selected['energy_repeats'][si]/energy_best['energy_repeats'][bi]-1
                        energycross.append(dict(meta,n=len(rr),selected_case=energy_selected['case_id'],mean_energy_best_case=energy_best['case_id'],selected_energy_repetition=si,optimal_energy_repetition=bi,energy_excess_fraction=ex,same_case=energy_selected['case_id']==energy_best['case_id'],comparison_kind='same_case_repeat_ratio_variation_not_selection_penalty' if energy_selected['case_id']==energy_best['case_id'] else 'fixed_selected_vs_mean_optimal_case_repeat_ratio'))
                        cross.append(ex)
                    groups[-1].update(energy_fixed_selection_repeat9_min=min(cross),energy_fixed_selection_repeat9_max=max(cross))
                    for k in (1,2,3):
                        if k<=len(rr):shorts.append(dict(meta,**shortlist_metrics(rr,k)))
                    predictor_indices=range(3) if method==MEASURED_COMPLETION else [None]
                    current=[];energycurrent=[]
                    for pi in predictor_indices:
                        for ni in range(3):
                            trial=[dict(r,utility=r['generic_repeats'][pi] if pi is not None else r['utility'],native_fps=r['native_repeats'][ni]) for r in rr]
                            tr=evaluate_group(trial,rank);row=dict(meta,predictor_repetition=pi,native_repetition=ni,n=len(rr),selected_case=tr['selected_case'],rho=tr['rho'],tau_b=tr['tau_b'],L_R=tr['L_R'],L_C=tr['L_C'],top1_hit=tr['top1_hit_tie_aware']);reprows.append(row);current.append(row)
                        for ei in range(3):
                            trial=[dict(r,utility=r['generic_repeats'][pi] if pi is not None else r['utility'],j_per_task=r['energy_repeats'][ei]) for r in rr]
                            tr=evaluate_group(trial,rank);row=dict(meta,predictor_repetition=pi,energy_repetition=ei,n=len(rr),selected_case=tr['selected_case'],energy_best_case=tr['energy_best_case'],energy_excess_fraction=tr['energy_excess_fraction'],energy_top1_hit=tr['energy_top1_hit']);energyreprows.append(row);energycurrent.append(row)
                    rs=dict(meta,n=len(rr),combination_n=len(current),top1_hits=sum(r['top1_hit'] for r in current),selected_cases=sorted({r['selected_case'] for r in current}))
                    for field in ['rho','tau_b','L_R','L_C']:
                        vv=[r[field] for r in current if r[field] is not None];rs.update({field+'_min':min(vv) if vv else None,field+'_max':max(vv) if vv else None})
                    repsumm.append(rs);energyrepsumm.append(dict(meta,n=len(rr),combination_n=len(energycurrent),energy_top1_hits=sum(r['energy_top1_hit'] for r in energycurrent),energy_excess_min=min(r['energy_excess_fraction'] for r in energycurrent),energy_excess_max=max(r['energy_excess_fraction'] for r in energycurrent),selected_cases=sorted({r['selected_case'] for r in energycurrent}),energy_best_cases=sorted({r['energy_best_case'] for r in energycurrent})))
    summaries=[]
    for cohort,tier,method,family in itertools.product(['base','augmented'],TIERS,methods,['all','classification','detection']):
        rows=[r for r in groups if r['cohort']==cohort and r['tier']==tier and r['method']==method and (family=='all' or r['family']==family)]
        summaries.append(dict(cohort=cohort,tier=tier,method=method,family=family,**summarize(rows)))
    equivalences=[]
    rankvectors=defaultdict(dict)
    for r in caseranks:rankvectors[(r['cohort'],r['tier'],tuple(r[k] for k in STRATUM),r['method'])][r['case_id']]=r['method_rank']
    # Explicit equal-candidate sets among evaluable methods in every primary group.
    checked=0
    for cohort,tier,gkey in itertools.product(['base','augmented'],TIERS,sorted(grouped)):
        rr=[r for r in groups if r['cohort']==cohort and r['tier']==tier and tuple(r[k] for k in STRATUM)==gkey and r['status'] in ('ok','constant_scores')]
        if rr:
            assert all(r['candidate_ids']==rr[0]['candidate_ids'] for r in rr);checked+=1
            for left,right in itertools.combinations(rr,2):
                li=rankvectors[(cohort,tier,gkey,left['method'])];ri=rankvectors[(cohort,tier,gkey,right['method'])]
                equivalences.append(dict(zip(STRATUM,gkey),cohort=cohort,tier=tier,method_a=left['method'],method_b=right['method'],n=left['n'],same_top1=left['selected_case']==right['selected_case'],same_average_rank_vector=li==ri))
    cohort_counts={t:sum(eligible(r,t) for r in pairs) for t in TIERS}
    regression=[r for r in groups if r['cohort']=='augmented' and r['tier']=='technical' and r['method']==MEASURED_COMPLETION]
    assert len(regression)==21 and sum(r['top1_hit_tie_aware'] for r in regression)==10
    tables={'method_groups.csv':groups,'method_case_ranks.csv':caseranks,'method_shortlists.csv':shorts,'method_repeat_combinations.csv':reprows,'method_repeat_sensitivity.csv':repsumm,'method_energy_repeat_combinations.csv':energyreprows,'method_energy_repeat_sensitivity.csv':energyrepsumm,'method_coverage.csv':coverage,'method_summary.csv':summaries,'method_energy_fixed_selection_repeat9.csv':energycross,'method_order_equivalence.csv':equivalences}
    for n,rows in tables.items():write_csv(output/'tables'/n,rows)
    result=dict(posthoc=True,cohort_counts=cohort_counts,base_raw_n=len(raw_common),method_ids=methods,completed_pair_n=len(pairs),generic_completion_regression_top1_hits=10,generic_completion_regression_groups=21,group_candidate_equality_checks=checked,full_references_used=0,
        generated_tables={n:len(rs) for n,rs in tables.items()},primary_summary=[r for r in summaries if r['cohort']=='augmented' and r['tier']=='technical' and r['family']=='all'],
        caveats=['No ranks or correlations pooled across groups. Group summaries give each evaluable exact stratum equal weight.','All methods use identical measured candidates when a full-group metric is reported. Missing methods stay unavailable.','Three repeats are the repeated experiments; tasks and dependent cross-combinations are not independent repeats.','Static prediction provenance and availability are inherited from the method inventory.','Original quality-transfer gates and reference-close filters are preserved.','Energy is mean(E/N) from the existing energy windows, not measured Generic energy.','No Full reference enters this split-selection study; historical Full-attestor source gap does not affect these split-only joins.'])
    output.mkdir(parents=True,exist_ok=True);(output/'method_evaluation_results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('primary_summary','caveats')},indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',required=True,type=Path);p.add_argument('--deep-root',type=Path);p.add_argument('--method-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args();analyze(a.source_root.resolve(),a.method_root.resolve(),a.output_root.resolve(),a.deep_root)
