#!/usr/bin/env python3
"""Combined current-data ARCS score with full graph normalization and model holdout.

No measurements or existing publication files are modified. The implementation
uses ARCS Eq. (5), raw Imb, and the verified regular workflow candidate universe
for normalization. It does not reproduce the old extra normalization of Imb.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

BUDGETS = (1, 3, 5)
DEFAULT_ALPHA = .75
AUDIT = Path('results/split-inference/publication-inputs/mlsys-r22/evidence/r15/audit_regnet/results')
PUBLISHED = Path('results/supplementary-studies/rq2-all-cuts-20261020/current')


def weights(alpha):
    return {'w_comm': 1.0, 'w_imb': float(alpha / (1-alpha)), 'w_tensors': .2} if alpha < 1 else {'w_comm': 0., 'w_imb': 1., 'w_tensors': .2}


def groups(frame):
    return [(key, g.sort_values('config_id').reset_index(drop=True)) for key, g in frame.groupby(['model','setup'], sort=True)]


def weighted_order(g, alpha):
    # Rounding only resolves score equality at computed pairwise breakpoints.
    # Mid-interval representatives are checked against the unrounded ordering.
    score = np.round((1-alpha)*g.comm_normalized.to_numpy() + alpha*g.imbalance.to_numpy(), 12)
    return np.argsort(score, kind='stable')


def objective(group_list, alpha):
    values=[]
    for _,g in group_list:
        fps=g.native_fps.to_numpy()
        retained=np.maximum.accumulate(fps[weighted_order(g,alpha)])
        values.extend(100*(1-retained[min(k,len(g))-1]/fps.max()) for k in BUDGETS)
    return float(np.mean(values))


def optimize(group_list):
    """Evaluate every ordering interval and every boundary on [0,1]."""
    breakpoints={0.,1.}
    for _,g in group_list:
        c=g.comm_normalized.to_numpy();i=g.imbalance.to_numpy()
        for a in range(len(g)):
            for b in range(a):
                dc=c[a]-c[b];di=i[a]-i[b]
                if dc==di:
                    continue
                alpha=float(dc/(dc-di))
                if 0 < alpha < 1:
                    breakpoints.add(alpha)
    points=sorted(breakpoints)
    candidates=[]
    for alpha in points:
        candidates.append({'alpha':alpha,'lower':alpha,'upper':alpha,'width':0.,'kind':'boundary','objective_pct':objective(group_list,alpha)})
    for lo,hi in zip(points,points[1:]):
        if hi-lo < 1e-11:
            continue
        alpha=(lo+hi)/2
        candidates.append({'alpha':alpha,'lower':lo,'upper':hi,'width':hi-lo,'kind':'open_interval','objective_pct':objective(group_list,alpha)})
    optimum=min(c['objective_pct'] for c in candidates)
    equivalent=[c for c in candidates if abs(c['objective_pct']-optimum)<1e-10]
    # Entirely training-based deterministic stability tie-break.
    selected=sorted(equivalent,key=lambda c:(-c['width'],c['alpha']))[0]
    selected=dict(selected, weights=weights(selected['alpha']))
    grid=np.linspace(0,1,1001)
    grid_best=min(objective(group_list,float(a)) for a in grid)
    assert optimum <= grid_best+1e-8
    for _,g in group_list:
        if selected['kind']=='open_interval':
            raw=(1-selected['alpha'])*g.comm_normalized.to_numpy()+selected['alpha']*g.imbalance.to_numpy()
            assert np.array_equal(weighted_order(g,selected['alpha']), np.argsort(raw,kind='stable'))
    return {'selected':selected,'minimum_objective_pct':optimum,'intervals_evaluated':len(candidates),'dense_grid_minimum_pct':grid_best,
            'optimal_regions':equivalent,'objective':'mean percentage Native-throughput loss at k=1,3,5, equal weights over budgets and model/device groups',
            'representative_rule':'midpoint of widest globally optimal open ranking interval; smaller alpha breaks equal-width ties; boundary used only if no equally good interval exists'}


def load_bound_features(repo, export):
    """Join by verified boundary identity, never model/cut labels alone."""
    data=pd.read_csv(repo/AUDIT/'calibration_candidate_audit.csv')
    binding=pd.read_csv(export/'current_pair_feature_bindings.csv')
    graph=pd.read_csv(export/'graph_boundary_features.csv')
    universes=json.loads((export/'normalization_universes.json').read_text())
    assert len(data)==len(binding)==204
    assert data.config_id.is_unique and binding.config_id.is_unique
    assert graph.boundary_id.is_unique and binding.pair_binding_complete.all()
    assert graph.tool_workflow_candidate.equals(graph.stored_candidate_member)
    assert set(data.config_id)==set(binding.config_id)
    audit_index=data.set_index('config_id').sort_index()
    binding_index=binding.set_index('config_id').sort_index()
    for field in ['native_performance_source_sha256','generic_performance_source_sha256','quality_source_sha256']:
        assert audit_index[field].equals(binding_index[field])
    for field in ['native_fps','generic_fps']:
        assert np.allclose(audit_index[field],binding_index[field],rtol=1e-12,atol=1e-12)
    target_models=[model for model,g in graph.groupby('model') if g.feature_complete.all()]
    graph=graph[graph.model.isin(target_models)].copy()
    assert graph.feature_complete.all()
    normalization=[]
    for model,g in graph.groupby('model'):
        universe=g[g.tool_workflow_candidate]
        meta=next(m for m in universes['graphs'] if m['model']==model)['universes']['regular_workflow_candidates']
        assert set(universe.boundary_id)==set(meta['members'])
        record={'model':model,'universe':'regular_workflow_candidates','candidate_count':len(universe),'model_sha256':g.model_sha256.iloc[0]}
        for field,target in [('log10_1p_Comm','comm_normalized'),('T_raw','tensor_penalty')]:
            values=np.log10(1+universe.Comm.to_numpy()) if field=='log10_1p_Comm' else universe[field].to_numpy()
            full_values=np.log10(1+g.Comm.to_numpy()) if field=='log10_1p_Comm' else g[field].to_numpy()
            lo=float(values.min());hi=float(values.max())
            reference=meta['ranges'][field]
            assert reference['complete'] and reference['member_count']==len(universe)
            assert np.isclose(lo,reference['minimum'],rtol=0,atol=1e-12) and np.isclose(hi,reference['maximum'],rtol=0,atol=1e-12)
            graph.loc[g.index,target]=(full_values-lo)/(hi-lo) if hi>lo else 0.
            record[field+'_minimum']=lo;record[field+'_maximum']=hi
        normalization.append(record)
    merged=data.merge(binding[['config_id','resolved_boundary_id','native_resolved_model_sha256','generic_resolved_model_sha256']],on='config_id',validate='one_to_one')
    merged=merged[merged.model.isin(target_models)].copy()
    features=graph[['boundary_id','model_sha256','case','Comm','F_left','F_total','Imb_raw','T_raw','crossing_tensor_count','comm_normalized','tensor_penalty','tool_workflow_candidate']].rename(columns={'model_sha256':'feature_model_sha256','case':'feature_case'})
    merged=merged.merge(features,left_on='resolved_boundary_id',right_on='boundary_id',validate='many_to_one')
    assert len(merged)==int(data.model.isin(target_models).sum()) and merged.tool_workflow_candidate.all()
    assert merged.native_resolved_model_sha256.equals(merged.feature_model_sha256)
    assert merged.generic_resolved_model_sha256.equals(merged.feature_model_sha256)
    assert merged.case.equals(merged.feature_case)
    assert merged.crossing_tensor_count.eq(1).all() and merged.tensor_penalty.eq(0).all()
    classifier=merged[merged.task.eq('classification')]
    assert np.array_equal(classifier.boundary_bytes,classifier.Comm)
    assert np.allclose(classifier.prefix_operations,classifier.F_left,rtol=1e-12,atol=1e-6)
    assert np.allclose(classifier.total_operations,classifier.F_total,rtol=1e-12,atol=1e-6)
    assert np.allclose(classifier.prefix_compute_fraction,classifier.F_left/classifier.F_total,rtol=1e-12,atol=1e-12)
    merged['boundary_bytes']=merged.Comm
    merged['imbalance']=abs(2*merged.F_left/merged.F_total-1)
    merged['current_graph_feature_identity_verified']=True
    merged['current_operation_features_complete']=True
    assert np.allclose(merged.imbalance,merged.Imb_raw,rtol=0,atol=1e-12)
    return merged,normalization


SHARED_RATIO=0.15799266978091375
METHODS=('bytes','generic','weighted_default','weighted_shared','weighted_pooled','weighted_cv')


def run(repo,export,output,allow_incomplete_models=False):
    output.mkdir(parents=True,exist_ok=True)
    all_source=pd.read_csv(repo/AUDIT/'calibration_candidate_audit.csv')
    assert len(all_source)==204 and int(all_source.quality_pass.sum())==187
    data,normalization=load_bound_features(repo,export)
    eligible=data[data.quality_pass].copy()
    gg=groups(eligible)
    model_names=sorted(eligible.model.unique())
    assert len(gg)==3*len(model_names)
    missing_models=sorted(set(all_source.model)-set(model_names))
    if missing_models and not allow_incomplete_models:
        raise ValueError('Complete current operation features are required for all seven models. Missing: '+', '.join(missing_models))
    # Frozen calibration is checked for coverage, never extrapolated.
    prediction_path=repo/AUDIT/'calibration_predictions.csv'
    predictions=pd.read_csv(prediction_path)
    predictions=predictions[predictions.cohort.eq('confirmed')]
    predicted_ids=set(predictions.config_id)
    calibration_missing=eligible.loc[~eligible.config_id.isin(predicted_ids),'config_id'].tolist()
    calibration_available=not calibration_missing
    assert not calibration_available  # Current frozen audit has no detector predictions.
    global_fit=optimize(gg)
    shared_alpha=SHARED_RATIO/(1+SHARED_RATIO)
    folds=[];memberships=[];fits={}
    for model in model_names:
        train=[(k,g) for k,g in gg if k[0]!=model]
        test=[(k,g) for k,g in gg if k[0]==model]
        assert len(train)==3*(len(model_names)-1) and len(test)==3
        train_ids={x for _,g in train for x in g.config_id};test_ids={x for _,g in test for x in g.config_id}
        assert train_ids.isdisjoint(test_ids)
        fit=optimize(train);fits[model]=fit
        alpha=fit['selected']['alpha']
        folds.append({'held_out_model':model,'train_n':len(train_ids),'test_n':len(test_ids),
                      'train_groups':len(train),'test_groups':len(test),'alpha':alpha,**weights(alpha),
                      'train_objective_pct':fit['minimum_objective_pct'],'test_objective_pct':objective(test,alpha),
                      'default_test_objective_pct':objective(test,DEFAULT_ALPHA),
                      'optimal_interval_lower':fit['selected']['lower'],'optimal_interval_upper':fit['selected']['upper']})
        for role,ids in [('train',train_ids),('test',test_ids)]:
            memberships.extend({'held_out_model':model,'role':role,'config_id':uid} for uid in sorted(ids))
    curve=[];rankings=[]
    for (model,setup),g in gg:
        method_orders={'bytes':np.argsort(g.boundary_bytes.to_numpy(),kind='stable'),
                       'generic':np.argsort(-g.generic_fps.to_numpy(),kind='stable'),
                       'weighted_default':weighted_order(g,DEFAULT_ALPHA),
                       'weighted_shared':weighted_order(g,shared_alpha),
                       'weighted_pooled':weighted_order(g,global_fit['selected']['alpha']),
                       'weighted_cv':weighted_order(g,fits[model]['selected']['alpha'])}
        fps=g.native_fps.to_numpy();best=float(fps.max())
        for method,order in method_orders.items():
            retained=np.maximum.accumulate(fps[order])
            for rank,index in enumerate(order,1):
                rankings.append({'model':model,'setup':setup,'method':method,'rank':rank,'config_id':g.config_id.iloc[index],
                                 'case':g.case.iloc[index],'native_fps':g.native_fps.iloc[index]})
            for k in range(1,21):
                value=float(retained[min(k,len(g))-1])
                curve.append({'model':model,'setup':setup,'task':g.task.iloc[0],'n':len(g),'method':method,'k':k,
                              'actual_trials':min(k,len(g)),'best_native_fps':best,'retained_native_fps':value,
                              'loss_pct':max(0.,100*(1-value/best)),'exact_winner_found':int(value==best)})
    curves=pd.DataFrame(curve)
    aggregate=curves.groupby(['method','k'],as_index=False).agg(mean_loss_pct=('loss_pct','mean'),median_loss_pct=('loss_pct','median'),
                           max_loss_pct=('loss_pct','max'),exact_winners=('exact_winner_found','sum'),groups=('model','size'))
    tasks=curves.groupby(['task','method','k'],as_index=False).agg(mean_loss_pct=('loss_pct','mean'),exact_winners=('exact_winner_found','sum'),groups=('model','size'))
    assert aggregate.groups.eq(len(gg)).all()
    for _,g in curves.groupby(['model','setup','method']):
        assert (np.diff(g.loss_pct)<=1e-10).all() and g.loss_pct.iloc[-1]==0
    # Detector groups remain in all budgets; testing all three reaches zero.
    assert curves.loc[curves.task.eq('detection')&curves.k.ge(3),'loss_pct'].eq(0).all()
    # Preserve exact current baseline selections for all available model/groups.
    published=pd.read_csv(repo/PUBLISHED/'all_k_group_curves.csv')
    errors=[]
    for method,old_name in [('bytes','boundary_bytes'),('generic','generic')]:
        reference=published[published.view.eq('quality_5pct')&published.method.eq(old_name)&published.model.isin(model_names)]
        actual=curves[curves.method.eq(method)]
        merged=actual.merge(reference,on=['model','setup','k'],suffixes=('_new','_old'))
        assert len(merged)==(int(eligible[eligible.task.eq('classification')].shape[0]) if method=='bytes' else len(eligible))
        error=float(abs(merged.loss_pct-merged.throughput_loss_pct).max());errors.append(error);assert error<1e-9
    eligible.to_csv(output/'candidate_features.csv',index=False,float_format='%.17g')
    curves.to_csv(output/'group_curves.csv',index=False,float_format='%.17g')
    aggregate.to_csv(output/'aggregate_curves.csv',index=False,float_format='%.17g')
    tasks.to_csv(output/'task_curves.csv',index=False,float_format='%.17g')
    aggregate[aggregate.k.isin(BUDGETS)].to_csv(output/'key_budget_results.csv',index=False,float_format='%.17g')
    pd.DataFrame(folds).to_csv(output/'fold_weights.csv',index=False,float_format='%.17g')
    pd.DataFrame(memberships).to_csv(output/'fold_memberships.csv',index=False)
    pd.DataFrame(rankings).to_csv(output/'complete_rankings.csv',index=False,float_format='%.17g')
    summary={'scope':{'all_source_pairs':204,'all_source_quality_eligible_pairs':187,'evaluated_quality_pairs':len(eligible),
                      'classifier_pairs':int(eligible.task.eq('classification').sum()),'detector_pairs':int(eligible.task.eq('detection').sum()),
                      'model_device_groups':len(gg),'models':model_names,'missing_models_due_incomplete_features':missing_models},
             'normalization':normalization,'normalization_scope':'complete regular workflow candidate universe per current graph',
             'operation_feature_contract':json.loads((export/'validation.json').read_text()).get('operation_proxy_version','original_complete_features'),
             'operation_feature_scope':json.loads((export/'validation.json').read_text()).get('scope','See export validation'),
             'formula':'w_comm*minmax(log10(1+Comm)) + w_imb*Imb_raw + w_tensors*minmax(T_raw)',
             'default_weights':weights(DEFAULT_ALPHA),'shared_weights':weights(shared_alpha),
             'shared_weights_status':'Frozen R28 all-classifier fit. In-sample for classifier measurements; transferred unchanged to detectors.',
             'pooled_fit_status':'Retrospective in-sample optimization on every evaluated model/device group.',
             'cv_status':'Leave one entire model out, including all three devices. Each displayed group uses only its held-out prediction.',
             'calibrated_generic':{'available_for_combined_curve':calibration_available,'confirmed_prediction_count':len(predictions),
                                   'confirmed_detector_prediction_count':int(predictions.model.str.startswith('yolo').sum()),
                                   'missing_evaluated_candidate_count':len(calibration_missing),'missing_ids':calibration_missing,
                                   'action':'No reduced-group aggregate and no imputation; omitted from combined methods.'},
             'budget_protocol':'For every k, keep all groups equally weighted and test min(k,n_group). Detector groups have n=3 and remain at zero loss for k>=3.',
             'objective':'Mean Native throughput loss at k=1,3,5, equal group and budget weights. No alternative objective selected after testing.',
             'tensor_weight_status':'fixed0.2; all evaluated cuts have exactly one crossing tensor and zero tensor penalty',
             'pooled_fit':global_fit,'fold_fits':fits,'folds':folds,
             'key_budget_results':aggregate[aggregate.k.isin(BUDGETS)].to_dict('records'),
             'validation':{'baseline_max_error_pp':max(errors),'all_group_counts_fixed':len(gg),'fold_model_disjoint':True,
                           'curve_monotonic':True,'full_graph_ranges_checked':True,'exact_graph_boundary_identity_join':True,
                           'missing_features_imputed':False,'paper_or_repo_modified':False},
             'repo_input_sha256':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/AUDIT/'calibration_candidate_audit.csv',prediction_path,repo/PUBLISHED/'all_k_group_curves.csv']},
             'export_input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [export/'current_pair_feature_bindings.csv',export/'graph_boundary_features.csv',export/'normalization_universes.json',export/'validation.json']}}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'scope':summary['scope'],'pooled_weights':global_fit['selected']['weights'],'folds':folds,
                      'key_results':summary['key_budget_results'],'calibration_available':calibration_available},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--export',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-incomplete-models',action='store_true',help='Internal intermediate comparison only; never impute missing features.')
    args=parser.parse_args()
    run(args.repo.resolve(),args.export.resolve(),args.output.resolve(),args.allow_incomplete_models)

