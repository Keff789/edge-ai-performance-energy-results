#!/usr/bin/env python3
"""Empirical rule coverage and exact random-subset success for all Native budgets."""
from pathlib import Path
from math import comb
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
METHODS = ('boundary_bytes', 'generic', 'calibrated_generic', 'uniform_random')
THRESHOLDS = (0., 1., 5.)
TARGETS = (.5, .8, 8/9, .9, .95, 1.)

def save(name, records):
    frame = records if isinstance(records,pd.DataFrame) else pd.DataFrame(records)
    frame.to_csv(ROOT/(name+'.csv'),index=False,float_format='%.15g')
    return frame

def order(group, method):
    if method=='boundary_bytes':
        if not group.feature_graph_identity_verified.all() or group.boundary_bytes.isna().any():
            return None,'No artifact-bound byte features for every group member.'
        return group.sort_values(['boundary_bytes','config_id']),''
    if method=='generic':
        return group.sort_values(['generic_fps','config_id'],ascending=[False,True]),''
    if method=='calibrated_generic':
        if group.predicted_native_fps.isna().any():
            return None,'Frozen eligible-classifier predictions do not cover the complete group.'
        return group.sort_values(['predicted_native_fps','config_id'],ascending=[False,True]),''
    return group,''

def probability(n,m,k):
    return 1.-comb(n-m,k)/comb(n,k) if k<=n-m else 1.

def main():
    data=pd.read_csv(ROOT/'inputs/calibration_candidate_audit.csv')
    prediction=pd.read_csv(ROOT/'inputs/calibration_predictions.csv')
    prediction=prediction[prediction.cohort.eq('confirmed')]
    data=data.merge(prediction[['config_id','predicted_native_fps']],on='config_id',how='left',validate='one_to_one')
    assert len(data)==204 and data.quality_pass.sum()==187
    rows=[];first=[];availability=[]
    for view in ('all_measured','quality_5pct'):
        cohort=data if view=='all_measured' else data[data.quality_pass]
        for (model,setup),group in cohort.groupby(['model','setup'],sort=True):
            n=len(group);best=group.native_fps.max()
            base=dict(view=view,task=group.task.iloc[0],model=model,setup=setup,n=n,native_best_fps=best)
            for method in METHODS:
                ordered,reason=order(group,method)
                available=ordered is not None
                availability.append(dict(base,method=method,available=available,unavailability_reason=reason))
                for threshold in THRESHOLDS:
                    bound=best*(1-threshold/100)
                    acceptable=group.native_fps.ge(bound)
                    m=int(acceptable.sum())
                    b=dict(base,method=method,loss_tolerance_pct=threshold,acceptable_candidate_count=m)
                    if not available:
                        first.append(dict(b,status='unavailable',first_successful_rank=np.nan,unavailability_reason=reason))
                        continue
                    if method!='uniform_random':
                        first_rank=int(np.flatnonzero(ordered.native_fps.ge(bound).to_numpy())[0])+1
                        successful_case=ordered.iloc[first_rank-1].case
                        first.append(dict(b,status='evaluated',first_successful_rank=first_rank,first_successful_case=successful_case))
                    for k in range(1,n+1):
                        success=probability(n,m,k) if method=='uniform_random' else float(k>=first_rank)
                        rows.append(dict(b,k=k,native_trials=k,success_fraction=success,
                            interpretation='exact_random_subset_probability' if method=='uniform_random' else 'observed_deterministic_success'))
    group_curves=save('group_success_curves',rows)
    first_hits=save('group_first_success',first)
    avail=save('method_availability',availability)
    aggregates=[]
    for view in ('all_measured','quality_5pct'):
        for task in ('classification','detection'):
            groups=avail[avail.view.eq(view)&avail.task.eq(task)&avail.method.eq('generic')]
            total=len(groups);assert total==(9 if task=='classification' else 12)
            for method in METHODS:
                valid=avail[avail.view.eq(view)&avail.task.eq(task)&avail.method.eq(method)]
                count=int(valid.available.sum())
                for threshold in THRESHOLDS:
                    for k in range(1,int(groups.n.max())+1):
                        actual=[min(k,int(n)) for n in groups.n]
                        b=dict(view=view,task=task,method=method,loss_tolerance_pct=threshold,max_native_trials=k,
                            fixed_group_count=total,available_group_count=count,
                            status='evaluated' if count==total else 'unavailable_incomplete_group_coverage',
                            actual_trials_min=min(actual),actual_trials_max=max(actual),
                            actual_trials_mean=float(np.mean(actual)),actual_trials_sum=sum(actual))
                        if count==total:
                            successes=[]
                            for g in groups.itertuples():
                                r=group_curves[group_curves.view.eq(view)&group_curves.model.eq(g.model)&group_curves.setup.eq(g.setup)&group_curves.method.eq(method)&group_curves.loss_tolerance_pct.eq(threshold)&group_curves.k.eq(min(k,g.n))]
                                assert len(r)==1
                                successes.append(float(r.success_fraction.iloc[0]))
                            b.update(mean_success_fraction=float(np.mean(successes)),success_group_sum=sum(successes),
                                minimum_group_success_fraction=min(successes),maximum_group_success_fraction=max(successes),
                                interpretation='mean_exact_random_probability_over_fixed_groups' if method=='uniform_random' else 'observed_fraction_of_fixed_groups')
                        aggregates.append(b)
    agg=save('fixed_group_success_curves',aggregates)
    targets=[]
    for (view,task,method,threshold),group in agg.groupby(['view','task','method','loss_tolerance_pct'],sort=True):
        for target in TARGETS:
            base=dict(view=view,task=task,method=method,loss_tolerance_pct=threshold,target_success_fraction=target,
                fixed_group_count=int(group.fixed_group_count.iloc[0]),available_group_count=int(group.available_group_count.iloc[0]))
            for criterion,column in [('mean_fixed_group_coverage','mean_success_fraction'),('every_group_probability','minimum_group_success_fraction')]:
                eligible=group[group[column].ge(target-1e-12)].sort_values('max_native_trials')
                if eligible.empty:
                    targets.append(dict(base,criterion=criterion,status='unavailable',minimum_max_budget=np.nan))
                    continue
                x=eligible.iloc[0]
                row=dict(base,criterion=criterion,status='evaluated',minimum_max_budget=int(x.max_native_trials))
                for c in ['mean_success_fraction','success_group_sum','minimum_group_success_fraction','actual_trials_min','actual_trials_max','actual_trials_mean','actual_trials_sum']:
                    row[c]=float(x[c])
                targets.append(row)
    target_frame=save('minimum_budgets_for_target_success',targets)
    random_targets=[]
    for key,group in group_curves[group_curves.method.eq('uniform_random')].groupby(['view','task','model','setup','loss_tolerance_pct'],sort=True):
        group=group.sort_values('k')
        for target in TARGETS:
            x=group[group.success_fraction.ge(target-1e-12)].iloc[0]
            random_targets.append(dict(view=key[0],task=key[1],model=key[2],setup=key[3],loss_tolerance_pct=key[4],
                n=int(x.n),acceptable_candidate_count=int(x.acceptable_candidate_count),target_success_fraction=target,
                minimum_native_trials=int(x.k),exact_success_probability=float(x.success_fraction)))
    random_frame=save('random_group_target_budgets',random_targets)
    for key,group in group_curves.groupby(['view','model','setup','method','loss_tolerance_pct']):
        group=group.sort_values('k')
        assert len(group)==int(group.n.iloc[0])
        assert group.success_fraction.between(0,1).all()
        assert (group.success_fraction.diff().dropna()>=-1e-12).all()
        assert group.success_fraction.iloc[-1]==1.
        if key[3]=='uniform_random':
            assert abs(group.success_fraction.iloc[0]-group.acceptable_candidate_count.iloc[0]/group.n.iloc[0])<1e-12
    summary=dict(measured_pairs=204,quality_eligible_pairs=187,byte_feature_pairs_all=168,byte_feature_pairs_quality=151,
        group_curve_rows=len(group_curves),fixed_group_curve_rows=len(agg),thresholds_pct=THRESHOLDS,targets=TARGETS,
        success_definition='At least one tested cut has Native FPS >= (1-tolerance/100)*the best measured Native FPS in the same group and view.',
        exact_random_probability='1 - C(n-m,k)/C(n,k), where m is the number of acceptable candidates; sampled without replacement.',
        deterministic_interpretation='Observed coverage across these fixed model/device groups, not a statistical estimate of future-model success probability.',
        average_random_interpretation='Exact random success probability averaged equally over these finite groups; every_group_probability uses the worst group instead.',
        actual_budget='k_effective=min(max_native_trials,n). Counts evaluated Native trials only, not failed compilations or graph-universe candidates.',
        additional_costs='Generic acquisition, frozen calibration training, quality evaluation and compilation are additional and excluded.',
        calibrated_scope='Published frozen eligible-classifier predictions only. No fitting or extrapolation.',
        tie_handling='Ascending configuration identity after byte size or descending predicted/measured FPS. No future-outcome tie breaking.',
        source_commit='b10d15992d0ce45d0f81329a5e961cb6207a1d09',
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'inputs').glob('*.csv'))},validation='All success curves complete, bounded, monotone, and equal to one at exhaustive measurement. Random k=1 equals m/n.')
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    structured=dict(summary=summary)
    for name,frame in [('group_curves',group_curves),('group_first_success',first_hits),('fixed_group_curves',agg),('minimum_budgets',target_frame),('random_group_targets',random_frame),('availability',avail)]:
        structured[name]=json.loads(frame.to_json(orient='records',double_precision=15))
    (ROOT/'success_results.json').write_text(json.dumps(structured,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))
    print(target_frame[target_frame.view.eq('quality_5pct')&target_frame.task.eq('classification')&target_frame.criterion.eq('mean_fixed_group_coverage')][['method','loss_tolerance_pct','target_success_fraction','minimum_max_budget','mean_success_fraction','actual_trials_mean','actual_trials_sum']].to_string(index=False))

if __name__=='__main__':
    raise SystemExit('Use reproduce.py --output PATH [--numeric-only] [--verify].')
