#!/usr/bin/env python3
"""Native success coverage for Graph rules on a shared measured set.

Standard-library-only reproduction from included inputs. Success concerns the
measured Native optimum, or at most 1%/5% throughput loss. Exact optimum means
strict equality with the maximum recorded, unrounded Native FPS; no epsilon.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

METHODS = ['cut_bytes_only','weighted_score','onnx_real_boundary_hardware_aware',
           'cycle_time_no_handover','stored_predicted_stream_fps','measured_generic_completion']
LABELS = dict(zip(METHODS, ['Boundary bytes','Weighted score','H10 fit',
                          'Cycle without handover','Stored stream rate','Generic']))
LABELS['uniform_random'] = 'Uniform random'
TARGETS = [('50%',Fraction(1,2)),('80%',Fraction(4,5)),('8/9',Fraction(8,9)),
           ('90%',Fraction(9,10)),('95%',Fraction(19,20)),('100%',Fraction(1,1))]
TOLERANCES = [('exact_optimum',0),('within_1pct',1),('within_5pct',5)]

def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))

def write(path, rows):
    rows=list(rows)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n')
        w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v,separators=(',',':')) if isinstance(v,(list,dict)) else v for k,v in row.items()})

def accepted(fps, best, tolerance):
    return fps==best if tolerance==0 else fps >= best*(1-tolerance/100)

def order(pool, method):
    if method=='measured_generic_completion':
        return sorted(pool,key=lambda r:(-float(r['generic_fps']),int(r['original_pair_order'])))
    return sorted(pool,key=lambda r:(-float(r['utility_'+method]),
                                    int(r['tie_order_'+method]),int(r['original_pair_order'])))

def run(inputs, output):
    output.mkdir(parents=True,exist_ok=True)
    source=inputs/'graph_rule_cuts.csv'
    rows=read(source)
    assert len(rows)==204
    groups=defaultdict(list)
    for row in rows:groups[(row['model'],row['setup'])].append(row)
    assert len(groups)==21
    first_hits, curves, fractions={},[],{}
    first_rows=[]
    for (model,setup),pool in groups.items():
        n=len(pool);best=max(float(r['native_fps']) for r in pool)
        meta=dict(experiment='Graph rules on a shared measured set',family=pool[0]['family'],model=model,setup=setup,n=n)
        for criterion,tolerance in TOLERANCES:
            good={r['case'] for r in pool if accepted(float(r['native_fps']),best,tolerance)}
            m=len(good)
            assert m>=1
            for method in METHODS:
                ordered=order(pool,method)
                first=next(k for k,r in enumerate(ordered,1) if r['case'] in good)
                first_hits[(model,setup,method,criterion)]=first
                hitrow=ordered[first-1]
                first_rows.append(dict(meta,method=method,method_label=LABELS[method],criterion=criterion,
                    max_loss_pct=tolerance,acceptable_cut_count=m,acceptable_cases=sorted(good),
                    first_hit_k=first,first_hit_case=hitrow['case'],first_hit_native_fps=float(hitrow['native_fps']),
                    native_best_fps=best,first_hit_loss_pct=100*(1-float(hitrow['native_fps'])/best)))
                for k in range(1,n+1):
                    probability=Fraction(int(k>=first),1)
                    fractions[(model,setup,method,criterion,k)]=probability
                    retained=max(float(r['native_fps']) for r in ordered[:k])
                    curves.append(dict(meta,method=method,method_label=LABELS[method],criterion=criterion,
                        max_loss_pct=tolerance,k=k,acceptable_cut_count=m,success_probability=float(probability),
                        probability_numerator=probability.numerator,probability_denominator=probability.denominator,
                        success_type='observed deterministic success',retained_native_fps=retained,
                        selected_cases=[r['case'] for r in ordered[:k]]))
            for k in range(1,n+1):
                denominator=math.comb(n,k)
                miss=math.comb(n-m,k) if n-m>=k else 0
                probability=1-Fraction(miss,denominator)
                fractions[(model,setup,'uniform_random',criterion,k)]=probability
                curves.append(dict(meta,method='uniform_random',method_label=LABELS['uniform_random'],
                    criterion=criterion,max_loss_pct=tolerance,k=k,acceptable_cut_count=m,
                    success_probability=float(probability),probability_numerator=probability.numerator,
                    probability_denominator=probability.denominator,success_type='exact probability without replacement',
                    retained_native_fps='',selected_cases=[]))
    summaries,budgets=[],[]
    for family in ['classification','detection','all']:
        keys=[key for key,pool in groups.items() if family=='all' or pool[0]['family']==family]
        limit=max(len(groups[key]) for key in keys)
        for criterion,tolerance in TOLERANCES:
            for method in METHODS+['uniform_random']:
                agg={}
                for k in range(1,limit+1):
                    hitcount=sum((fractions[(*key,method,criterion,min(k,len(groups[key])))] for key in keys),Fraction(0))
                    coverage=hitcount/len(keys)
                    agg[k]=(coverage,hitcount)
                    summaries.append(dict(experiment='Graph rules on a shared measured set',family=family,
                        method=method,method_label=LABELS[method],criterion=criterion,max_loss_pct=tolerance,
                        requested_k=k,group_count=len(keys),actual_k_min=min(k,min(len(groups[key]) for key in keys)),
                        actual_k_max=min(k,limit),
                        actual_k_mean=sum(min(k,len(groups[key])) for key in keys)/len(keys),
                        actual_k_sum=sum(min(k,len(groups[key])) for key in keys),
                        success_group_count_or_expectation=float(hitcount),
                        coverage=float(coverage),coverage_pct=100*float(coverage),
                        coverage_numerator=coverage.numerator,coverage_denominator=coverage.denominator,
                        coverage_type='exact expected fraction across fixed groups' if method=='uniform_random' else 'observed fraction across fixed groups'))
                for target_label,target in TARGETS:
                    k=next(k for k,(coverage,_) in agg.items() if coverage>=target)
                    coverage,count=agg[k]
                    previous=agg[k-1][0] if k>1 else Fraction(0)
                    budgets.append(dict(experiment='Graph rules on a shared measured set',family=family,
                        method=method,method_label=LABELS[method],criterion=criterion,max_loss_pct=tolerance,
                        target_label=target_label,target_fraction=float(target),minimum_requested_k=k,
                        group_count=len(keys),actual_k_min=min(k,min(len(groups[key]) for key in keys)),
                        actual_k_max=min(k,limit),
                        actual_k_mean=sum(min(k,len(groups[key])) for key in keys)/len(keys),
                        actual_k_sum=sum(min(k,len(groups[key])) for key in keys),
                        success_group_count_or_expectation=float(count),
                        achieved_coverage=float(coverage),previous_k_coverage=float(previous),
                        budget_interpretation='cuts tested per model/setup group; capped at available candidates'))
    write(output/'first_hit_ranks.csv',first_rows)
    write(output/'success_by_group_and_budget.csv',curves)
    write(output/'success_summary.csv',summaries)
    write(output/'required_budgets.csv',budgets)
    availability=read(inputs/'method_availability.csv')
    method_status=[]
    for method in sorted({r['method'] for r in availability}):
        selected=[r for r in availability if r['method']==method]
        method_status.append(dict(method=method,groups=len(selected),available_groups=sum(r['status']=='available' for r in selected),
            statuses=sorted({r['status'] for r in selected}),reasons=sorted({r['reason'] for r in selected}),
            included_in_this_analysis=method in METHODS))
    write(output/'method_availability_summary.csv',method_status)
    provenance=dict(experiment_display='Graph rules on a shared measured set',
        experiment_identity='historical_204_technical_pairs_with_9_YOLOv7_report_overlays',
        source_commit='b10d15992d0ce45d0f81329a5e961cb6207a1d09',pairs=204,classifier_pairs=168,detector_pairs=36,
        classifier_groups=9,detector_groups=12,
        scope='Separate fixed campaign from current Native/A4 analysis. No new experiments or parameter fitting.',
        exact_optimum='strict equality of recorded unrounded Native FPS with maximum; ties count; no numerical epsilon',
        tolerances='At least 99% or 95% of the within-group best recorded Native FPS.',
        random_formula='1 - binom(n-m,k)/binom(n,k), where m is the acceptable-cut count; exact Fraction arithmetic',
        aggregation='Each group equal weight. Actual k=min(requested_k,n). Deterministic observed success or exact random expected success fraction.',
        generalization='Observed empirical coverage is not a probability guarantee for unseen models/devices. Random probabilities are exact only for the fixed measured candidate sets.',
        inputs=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(inputs.iterdir()) if p.is_file()])
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'first_hit_rows':len(first_rows),'group_curve_rows':len(curves),'summary_rows':len(summaries),'budget_rows':len(budgets)},indent=2))
    for criterion,_ in TOLERANCES:
        print('\nCLASSIFICATION',criterion,'budgets 50/80/8-of-9/90/95/100')
        for method in METHODS+['uniform_random']:
            values=[r['minimum_requested_k'] for r in budgets if r['family']=='classification' and r['criterion']==criterion and r['method']==method]
            print(LABELS[method],values)

if __name__=='__main__':
    raise SystemExit('Use reproduce.py --output PATH [--numeric-only] [--verify].')
