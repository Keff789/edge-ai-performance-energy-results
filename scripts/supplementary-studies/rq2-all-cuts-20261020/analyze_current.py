#!/usr/bin/env python3
"""Recompute full measured-cut rankings and exhaustive Native-trial budgets.

Inputs are unchanged exports from the cited public evidence release.
No hardware, model execution, historical graph joins, or new calibration fits.
"""
from pathlib import Path
from math import comb
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent
METHODS = ('boundary_bytes', 'generic', 'calibrated_generic', 'uniform_random')
VIEWS = ('all_measured', 'quality_5pct')

def write_csv(name, records):
    frame = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    frame.to_csv(ROOT / name, index=False, float_format='%.15g')
    return frame

def rho(a, b):
    return float(spearmanr(a, b).statistic) if len(a) > 1 and len(set(a)) > 1 and len(set(b)) > 1 else np.nan

def expected_best(values, k):
    values = sorted(values)
    denominator = comb(len(values), k)
    return sum(value * comb(i, k-1) / denominator for i, value in enumerate(values) if i >= k-1)

def method_order(group, method):
    if method == 'boundary_bytes':
        if not group.feature_graph_identity_verified.all() or group.boundary_bytes.isna().any():
            return None, 'No artifact-bound boundary-byte features for every candidate in this group.'
        return group.sort_values(['boundary_bytes', 'config_id'], ascending=[True, True]), ''
    if method == 'generic':
        return group.sort_values(['generic_fps', 'config_id'], ascending=[False, True]), ''
    if method == 'calibrated_generic':
        if group.predicted_native_fps.isna().any():
            return None, 'Frozen calibrated predictions cover only quality-eligible classifiers; incomplete group coverage.'
        return group.sort_values(['predicted_native_fps', 'config_id'], ascending=[False, True]), ''
    return group, ''

def main():
    audit = pd.read_csv(ROOT / 'inputs/calibration_candidate_audit.csv')
    predictions = pd.read_csv(ROOT / 'inputs/calibration_predictions.csv')
    predictions = predictions[predictions.cohort.eq('confirmed')]
    published = pd.read_csv(ROOT / 'inputs/published_calibration_groups.csv')
    assert len(audit) == 204 and audit.config_id.nunique() == 204
    assert audit.quality_pass.sum() == 187
    assert audit.feature_graph_identity_verified.sum() == 168
    assert predictions.config_id.nunique() == len(predictions) == 151
    candidates = audit.merge(predictions[['config_id', 'predicted_native_fps']], on='config_id', how='left', validate='one_to_one')
    write_csv('all_measured_candidates.csv', candidates)
    rankings, correlations, curves, availability = [], [], [], []
    for view in VIEWS:
        cohort = candidates if view == 'all_measured' else candidates[candidates.quality_pass]
        for (model, setup), group in cohort.groupby(['model', 'setup'], sort=True):
            group = group.copy()
            n = len(group)
            task = group.task.iloc[0]
            best = group.native_fps.max()
            byte_ok = group.feature_graph_identity_verified.all() and group.boundary_bytes.notna().all()
            base = dict(view=view, model=model, setup=setup, task=task, n=n)
            correl = dict(base,
                rho_bytes_native=rho(-group.boundary_bytes, group.native_fps) if byte_ok else np.nan,
                rho_bytes_generic=rho(-group.boundary_bytes, group.generic_fps) if byte_ok else np.nan,
                rho_generic_native=rho(group.generic_fps, group.native_fps),
                byte_features_available=bool(byte_ok),
                byte_unavailability_reason='' if byte_ok else 'Detector graph-byte bindings are absent from the current calibration audit.',
                unique_boundary_sizes=group.boundary_bytes.nunique() if byte_ok else 0,
                native_best_fps=best,
                native_best_case=';'.join(group.loc[group.native_fps.eq(best), 'case']))
            for metric, ascending in [('native_fps',False),('generic_fps',False),('boundary_bytes',True),('predicted_native_fps',False)]:
                group[metric+'_rank_average'] = group[metric].rank(method='average',ascending=ascending)
            group['view'] = view
            group['group_n'] = n
            group['native_relative_loss_pct'] = 100*(1-group.native_fps/best)
            for method in METHODS:
                ordered, reason = method_order(group, method)
                available = ordered is not None
                availability.append(dict(base,method=method,available=available,reason=reason))
                if not available:
                    group[method+'_selection_rank'] = np.nan
                    correl[method+'_native_winner_first_rank'] = np.nan
                    correl[method+'_trials_to_loss_le_5pct'] = np.nan
                    continue
                if method != 'uniform_random':
                    ranks = pd.Series(range(1,n+1),index=ordered.index)
                    group[method+'_selection_rank'] = ranks
                    correl[method+'_native_winner_first_rank'] = int(ranks[ordered.native_fps.eq(best)].min())
                    correl[method+'_trials_to_loss_le_5pct'] = int(ranks[ordered.native_fps.ge(.95*best)].min())
                for k in range(1,n+1):
                    if method == 'uniform_random':
                        retained = expected_best(group.native_fps,k)
                        optimum_count = int(group.native_fps.eq(best).sum())
                        winner_coverage = 1 - (comb(n-optimum_count,k)/comb(n,k) if k<=n-optimum_count else 0)
                        selected = []
                        retained_case = ''
                    else:
                        chosen = ordered.iloc[:k]
                        retained = chosen.native_fps.max()
                        winner_coverage = float(retained == best)
                        selected = chosen.config_id.tolist()
                        retained_case = ';'.join(chosen.loc[chosen.native_fps.eq(retained),'case'])
                    curves.append(dict(base,method=method,k=k,native_trials=k,native_best_fps=best,
                        retained_native_fps_or_expectation=retained,
                        throughput_loss_pct=max(0.,100*(1-retained/best)),winner_coverage=winner_coverage,
                        selected_uids=json.dumps(selected),retained_case=retained_case,
                        random_subset_count=comb(n,k) if method=='uniform_random' else np.nan))
            rankings.append(group)
            correlations.append(correl)
    rank_frame = write_csv('full_candidate_rankings.csv',pd.concat(rankings,ignore_index=True))
    corr_frame = write_csv('group_correlations.csv',correlations)
    curve_frame = write_csv('all_k_group_curves.csv',curves)
    avail_frame = write_csv('method_availability.csv',availability)
    aggregates=[]
    for view in VIEWS:
        for task in ['classification','detection']:
            groups=corr_frame[corr_frame.view.eq(view)&corr_frame.task.eq(task)]
            group_count=len(groups)
            assert group_count==(9 if task=='classification' else 12)
            for method in METHODS:
                valid=avail_frame[avail_frame.view.eq(view)&avail_frame.task.eq(task)&avail_frame.method.eq(method)]
                valid_count=int(valid.available.sum())
                for k_max in range(1,int(groups.n.max())+1):
                    effective=[min(k_max,int(n)) for n in groups.n]
                    row=dict(view=view,task=task,method=method,max_native_trials=k_max,
                        fixed_group_count=group_count,available_group_count=valid_count,
                        status='evaluated' if valid_count==group_count else 'unavailable_incomplete_group_coverage',
                        effective_trials_min=min(effective),effective_trials_max=max(effective),
                        effective_trials_mean=float(np.mean(effective)),effective_trials_sum=sum(effective))
                    if valid_count==group_count:
                        losses=[];hits=[]
                        for g in groups.itertuples():
                            r=curve_frame[curve_frame.view.eq(view)&curve_frame.model.eq(g.model)&curve_frame.setup.eq(g.setup)&curve_frame.method.eq(method)&curve_frame.k.eq(min(k_max,g.n))]
                            assert len(r)==1
                            losses.append(float(r.throughput_loss_pct.iloc[0]));hits.append(float(r.winner_coverage.iloc[0]))
                        row.update(mean_loss_pct=float(np.mean(losses)),median_loss_pct=float(np.median(losses)),max_loss_pct=max(losses),winner_coverage_sum=sum(hits))
                    aggregates.append(row)
    aggregate_frame=write_csv('fixed_group_budget_curves.csv',aggregates)
    corr_summary=corr_frame.groupby(['view','task'])[['rho_bytes_native','rho_bytes_generic','rho_generic_native']].agg(['count','mean','median','min','max'])
    corr_summary.columns=['_'.join(c) for c in corr_summary.columns]
    write_csv('correlation_summary.csv',corr_summary.reset_index())
    validation=[]
    method_map={'boundary_bytes_only_recomputed':'boundary_bytes','generic':'generic','calibrated_generic':'calibrated_generic','uniform_random':'uniform_random'}
    for r in published[published.task.eq('classification')&published.status.eq('evaluated')].itertuples():
        measured=curve_frame[curve_frame.view.eq('quality_5pct')&curve_frame.model.eq(r.model)&curve_frame.setup.eq(r.setup)&curve_frame.method.eq(method_map[r.method])&curve_frame.k.eq(r.k)]
        assert len(measured)==1
        error=abs(float(measured.throughput_loss_pct.iloc[0])-r.regret_pct)
        assert error<1e-9,(r,error)
        validation.append(dict(model=r.model,setup=r.setup,method=method_map[r.method],k=r.k,published_loss_pct=r.regret_pct,recomputed_loss_pct=float(measured.throughput_loss_pct.iloc[0]),absolute_error_pp=error))
    write_csv('published_k135_validation.csv',validation)
    report=dict(measured_pairs=len(candidates),quality_eligible_pairs=int(candidates.quality_pass.sum()),
        classifier_pairs_all=168,classifier_pairs_quality=151,detector_pairs=36,
        detector_boundary_features_available=0,full_ranking_rows=len(rank_frame),group_correlations=len(corr_frame),
        all_k_group_curve_rows=len(curve_frame),published_k135_comparisons=len(validation),
        max_published_absolute_error_pp=max(r['absolute_error_pp'] for r in validation),
        boundary_score='ascending logical boundary bytes; ties use ascending configuration identity',
        rank_correlation='Spearman average ranks; corr(-boundary_bytes,FPS), so positive means smaller boundary accompanies higher throughput',
        aggregation='Equal weight across fixed nine classifier groups (or twelve detector groups). k_eff=min(max_native_trials,n). No aggregate over a reduced subset when a method lacks any group.',
        budget_scope='Native trials in the evaluated group only. Generic acquisition, calibration training, compilation and quality evaluation are additional and excluded. Uniform-random values are exact expectations over all distinct subsets.',
        calibrated_scope='Frozen published architecture-held-out predictions; no new fitting or extrapolation to the 17 quality-excluded classifier cuts or any detector.',
        source_commit='b10d15992d0ce45d0f81329a5e961cb6207a1d09',
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'inputs').glob('*.csv'))})
    (ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    structured = dict(summary=report,
        correlations=json.loads(corr_frame.to_json(orient='records',double_precision=15)),
        group_budget_curves=json.loads(curve_frame.drop(columns=['selected_uids']).to_json(orient='records',double_precision=15)),
        fixed_group_budget_curves=json.loads(aggregate_frame.to_json(orient='records',double_precision=15)),
        method_availability=json.loads(avail_frame.to_json(orient='records',double_precision=15)))
    (ROOT/'analysis_results.json').write_text(json.dumps(structured,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2))
    print(corr_summary.to_string())
    print(aggregate_frame[aggregate_frame.task.eq('classification')&aggregate_frame.max_native_trials.isin([1,3,5,10,15,20])][['view','method','max_native_trials','available_group_count','mean_loss_pct','effective_trials_min','effective_trials_max']].to_string(index=False))

if __name__=='__main__':
    raise SystemExit('Use reproduce.py --output PATH [--numeric-only] [--verify].')
