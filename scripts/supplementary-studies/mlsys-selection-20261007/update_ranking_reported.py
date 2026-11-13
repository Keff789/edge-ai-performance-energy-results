#!/usr/bin/env python3
"""Recompute selection outcomes using the supplied YOLOv7 report overlay.

No measurements or raw ZIP verification are performed. Original evidence and
methods tables remain historical inputs. Current outputs are in
reported_update/ranking_tables; current plot sources are also refreshed.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import itertools
import json
import shutil

import numpy as np
import pandas as pd

MODEL = 'yolov7_paper'
METHODS = ['cut_bytes_only', 'weighted_score',
           'onnx_real_boundary_hardware_aware', 'cycle_time_no_handover',
           'stored_predicted_stream_fps', 'measured_generic_completion']
MODELS = ['mobilenet_v3_large','regnet_x_1_6gf','resnet50',
          'yolo11l','yolo26m','yolo26s',MODEL]
SETUPS = ['H8','H10','DeepX']
LABELS = dict(zip(MODELS, ['MobileNetV3-Large','RegNetX-1.6GF','ResNet-50',
                          'YOLO11l','YOLO26m','YOLO26s','YOLOv7']))
STRATUM = ['model_id','setup_id','direction','precision','comparison_backend',
           'output_endpoint_id','boundary_class']



def admitted(df, tier):
    mask = df.eligible_for_technical_transfer.eq(True)
    if tier != 'technical':
        mask &= df.eligible_for_quality_transfer.eq(True)
    if tier == 'reference_close':
        mask &= (df.generic_task_quality_status.eq('reference_close') &
                 df.native_task_quality_status.eq('reference_close'))
    return df[mask]


def subset(row, cases):
    df = cases[(cases.model_id == row.model_id) & (cases.setup_id == row.setup_id)]
    if row.cohort == 'base':
        df = df[df.observation_origin.eq('base')]
    return admitted(df, row.tier)


def metrics(df, gfield='generic_completed_task_fps'):
    g = df[gfield].to_numpy(float)
    n = df.native_completed_task_fps.to_numpy(float)
    gt = np.flatnonzero(g == g.max()) if len(g) else []
    nt = np.flatnonzero(n == n.max()) if len(n) else []
    pairs = [(g[i]-g[j], n[i]-n[j]) for i,j in itertools.combinations(range(len(g)),2)]
    comparable = [(x,y) for x,y in pairs if x != 0 and y != 0]
    out = dict(n=len(df), status='insufficient_candidates' if len(df)<3 else 'ok',
               generic_top_ties=len(gt),native_top_ties=len(nt),
               comparable_pairs=len(comparable))
    if len(df)<3:
        return out
    selected, best = int(gt[0]), int(nt[0])
    losses = 1-n[gt]/n[best]
    costs = n[best]/n[gt]-1
    out.update(rho=float(spearmanr(g,n).statistic),
               tau_b=float(kendalltau(g,n).statistic),
               pairwise_concordance=sum(x*y>0 for x,y in comparable)/len(comparable)
                   if comparable else np.nan,
               top1_hit_stable=selected==best, top1_hit_tie_aware=selected in nt,
               L_R=1-n[selected]/n[best], L_C=n[best]/n[selected]-1,
               generic_selected_case=df.iloc[selected].case_id,
               native_best_case=df.iloc[best].case_id,
               tie_L_R_min=min(losses),tie_L_R_max=max(losses),
               tie_L_C_min=min(costs),tie_L_C_max=max(costs))
    return out


def build(source, output, methods_root):
    """Recompute the historical report overlay into explicit output paths."""
    global spearmanr, kendalltau
    from scipy.stats import spearmanr, kendalltau
    A = source
    O = output / "reported_update/ranking_tables"
    O.mkdir(parents=True, exist_ok=True)
    (output / "sections").mkdir(parents=True, exist_ok=True)
    def write(df, filename):
        df.to_csv(O / filename, index=False)
    reported = pd.read_csv(A/'reported_update/reported_results.csv')
    split = reported[reported.configuration_type.eq('split')].copy()
    assert len(split) == 9 and not split.duplicated(['model','setup','case']).any()
    assert set(split.model)=={MODEL}
    cases = pd.read_csv(A/'evidence/tables/rank_cases.csv')
    historical_cases = cases.copy()
    cases['literal_report_endpoint_equal'] = cases.literal_report_endpoint_equal.astype(object)
    cases['native_performance_source'] = 'archived_completed_campaign'
    cases['native_report_source_sha256'] = ''
    cases['current_native_command_sha256'] = ''
    cases['current_native_source_verification'] = 'archived_evidence'
    for _, rr in split.iterrows():
        mask = cases.model_id.eq(rr.model) & cases.setup_id.eq(rr.setup) & cases.case_id.eq(rr.case)
        assert mask.sum()==1
        i = cases.index[mask][0]
        rates = [float(rr[f'fps_{j}']) for j in (1,2,3)]
        assert np.isclose(np.median(rates), rr.fps_median, atol=5e-7)
        for col,value in dict(native_completed_task_fps=rr.fps_median,
                              native_task_quality_status=rr.quality_status,
                              native_min=min(rates),native_max=max(rates),
                              native_repeats=json.dumps(rates),
                              native_performance_source='supplied_report_overlay_20261006',
                              native_report_source_sha256=rr.source_sha256,
                              current_native_source_verification='report_only_no_raw_zip_verification',
                              native_runner=np.nan,native_command_sha256=np.nan,
                              native_report_endpoint_id=np.nan,
                              literal_report_endpoint_equal=np.nan,
                              native_counts=np.nan,native_makespans=np.nan).items():
            cases.loc[i,col]=value
        cases.loc[i,'S'] = rr.fps_median/cases.loc[i,'generic_completed_task_fps']
        cases.loc[i,'native_over_generic_completed_task_ratio'] = cases.loc[i,'S']
    # Check every case against its three recorded repeats. Some archived H8
    # Native point rates were rounded to six decimals; retain that supplied
    # point-estimate convention while ranges use the full-precision repeats.
    for _, row in cases.iterrows():
        for kind in ("generic", "native"):
            values = np.asarray(json.loads(row[kind + "_repeats"]), dtype=float)
            assert len(values) == 3 and np.isfinite(values).all() and (values > 0).all()
            assert np.isclose(np.median(values), row[kind + "_completed_task_fps"],
                              rtol=0, atol=5.00001e-7), (row.model_id, row.setup_id, row.case_id, kind)
    # Retain the pre-existing technical and quality-transfer admission gates. A
    # report's reference_close label does not establish new cross-runner evidence.
    write(cases,'rank_cases.csv')

    groups = pd.read_csv(A/'evidence/tables/rank_groups.csv')
    groups['performance_basis'] = np.where(groups.model_id.eq(MODEL),
        'historical_generic_vs_reported_native', 'archived_completed_campaign')
    for i,row in groups.iterrows():
        # All group metrics are recalculated from preserved candidate records;
        # historical table rows supply only cohort and stratum definitions.
        for key,value in metrics(subset(row,cases)).items():
            groups.loc[i,key] = value
    write(groups,'rank_groups.csv')

    reps = pd.read_csv(A/'evidence/tables/rank_repeat_sensitivity.csv')
    reps['performance_basis'] = np.where(reps.model_id.eq(MODEL),
        'historical_generic_vs_reported_native', 'archived_completed_campaign')
    combinations = []
    for i,row in reps.iterrows():
        df = subset(row,cases).copy()
        per = []
        for gi,ni in itertools.product(range(3),repeat=2):
            rr = df.copy()
            rr['generic_completed_task_fps'] = [json.loads(x)[gi] for x in df.generic_repeats]
            rr['native_completed_task_fps'] = [json.loads(x)[ni] for x in df.native_repeats]
            result = metrics(rr)
            per.append(result)
            if row.model_id == MODEL:
                combinations.append({**{x:row[x] for x in STRATUM+['cohort','tier','family']},
                                     'generic_repeat_index':gi,'native_repeat_index':ni,**result})
        reps.loc[i,'top1_hits'] = sum(x['top1_hit_tie_aware'] for x in per)
        for kind,field in [('generic_selected_cases','generic_selected_case'),
                           ('native_best_cases','native_best_case')]:
            reps.loc[i,kind] = json.dumps(sorted({x[field] for x in per}))
        for field in ['rho','tau_b','L_R','L_C']:
            values = [x[field] for x in per]
            for suffix,func in [('min',min),('max',max),('median',np.median)]:
                reps.loc[i,field+'_'+suffix] = func(values)
    write(reps,'rank_repeat_sensitivity.csv')
    write(pd.DataFrame(combinations),'yolov7_rank_repeat_combinations.csv')

    # Only unchanged classification groups have nontrivial Top2/Top3 shortlists.
    shortlists = pd.read_csv(A/'evidence/tables/rank_shortlists.csv')
    assert not shortlists.model_id.eq(MODEL).any()
    write(shortlists,'rank_shortlists.csv')

    # Generic ranking summaries including the pre-existing quality restrictions.
    summary=[]
    for (cohort,tier),df in groups.groupby(['cohort','tier'],sort=False):
        for family in ['all','classification','detection']:
            eligible=df[df.status.eq('ok')]
            if family!='all': eligible=eligible[eligible.family.eq(family)]
            exclusions={'none':set(),
                'without_regnet_h10':{('regnet_x_1_6gf','H10')},
                'without_resnet_h10':{('resnet50','H10')},
                'without_yolov7_h8':{(MODEL,'H8')},
                'without_three_reported_counterexamples':{
                    ('regnet_x_1_6gf','H10'),('resnet50','H10'),(MODEL,'H8')}}
            for label,exclude in exclusions.items():
                selected=eligible[[tuple(x) not in exclude for x in eligible[['model_id','setup_id']].values]]
                if not len(selected): continue
                r=dict(cohort=cohort,tier=tier,family=family,sensitivity=label,
                       eligible_groups_before=len(eligible),n_groups=len(selected),
                       n_candidates=int(selected.n.sum()),
                       top1_hits=int(selected.top1_hit_tie_aware.eq(True).sum()))
                for field in ['L_R','L_C']:
                    for label2,func in [('median',np.median),('mean',np.mean),('max',max)]:
                        r[label2+'_group_'+field]=func(selected[field])
                summary.append(r)
    write(pd.DataFrame(summary),'rank_dominant_case_sensitivity.csv')

    features=pd.read_csv(A/'evidence/inputs/graph_features.csv')
    features=features[features.model_id.eq(MODEL)].copy()
    def norm(x):
        return (x-x.min())/(x.max()-x.min()) if x.max()!=x.min() else x*0
    features['weighted']=(norm(np.log10(1+features.cut_bytes))+
                          3*norm(abs(2*features.stored_flops_left_ratio-1))+
                          .2*norm((features.n_cut_tensors-1).clip(lower=0)))
    score_fields={'cut_bytes_only':('cut_bytes',-1),
                  'weighted_score':('weighted',-1),
                  'cycle_time_no_handover':('stored_predicted_bottleneck_ms',-1),
                  'stored_predicted_stream_fps':('stored_predicted_stream_fps',1)}
    mg=pd.read_csv(methods_root/'tables/method_groups.csv')
    mg['performance_basis']=np.where(mg.model_id.eq(MODEL),
        'historical_generic_vs_reported_native','archived_completed_campaign')
    mg['rank_metric_basis']='archived_unchanged'
    mg['energy_scope']=np.where(mg.model_id.eq(MODEL),
        'unavailable_current_yolov7_energy','archived_matched_energy')
    for i,row in mg[mg.model_id.eq(MODEL)].iterrows():
        # Current performance cannot be combined with previous energy runs.
        for col in mg.columns:
            if 'energy' in col and col!='energy_scope': mg.loc[i,col]=np.nan
        if row.status!='ok': continue
        df=subset(row,cases).set_index('case_id')
        assert set(df.index)==set(json.loads(row.candidate_ids))
        native=df.native_completed_task_fps
        best=native.idxmax(); selected=row.selected_case
        loss=1-native[selected]/native[best]; cost=native[best]/native[selected]-1
        assert int(row.score_top_ties)==1, 'updated candidates require explicit top-tie identities'
        updates=dict(native_best_case=best,L_R=loss,L_C=cost,
                     top1_hit_stable=selected==best,top1_hit_tie_aware=selected==best,
                     tie_L_R_min=loss,tie_L_R_max=loss,tie_L_C_min=cost,tie_L_C_max=cost,
                     random_expected_L_R=float((1-native/native.max()).mean()),
                     random_expected_L_C=float((native.max()/native-1).mean()),
                     random_native_best_hit_probability=float((native==native.max()).mean()),
                     source_list_order_L_R=1-native[row.source_list_order_selected_case]/native.max())
        if row.method in score_fields:
            field,sign=score_fields[row.method]
            scores=features.set_index('case_id').loc[df.index,field]*sign
            assert scores.idxmax()==selected, 'frozen selection changed unexpectedly'
            old_native=historical_cases[(historical_cases.model_id==MODEL)&
                historical_cases.setup_id.eq(row.setup_id)].set_index('case_id').loc[df.index,'native_completed_task_fps']
            assert np.isclose(spearmanr(scores,old_native).statistic,row.rho)
            assert np.isclose(kendalltau(scores,old_native).statistic,row.tau_b)
            updates.update(rho=float(spearmanr(scores,native).statistic),
                           tau_b=float(kendalltau(scores,native).statistic),
                           rank_metric_basis='recomputed_from_bundled_graph_fields')
        elif row.method=='measured_generic_completion':
            scores=df.generic_completed_task_fps
            assert scores.idxmax()==selected
            updates.update(rho=float(spearmanr(scores,native).statistic),
                           tau_b=float(kendalltau(scores,native).statistic),
                           rank_metric_basis='recomputed_from_historical_generic_rates')
        else:
            # The frozen selected ID remains valid, but the hardware score vector
            # is absent from this package. Do not retain a stale correlation.
            assert row.method=='onnx_real_boundary_hardware_aware'
            updates.update(rho=np.nan,tau_b=np.nan,
                           rank_metric_basis='unavailable_hardware_score_vector_not_bundled')
        for col,value in updates.items(): mg.loc[i,col]=value
    write(mg,'method_groups.csv')

    ms=[]
    for (cohort,tier,method),df in mg.groupby(['cohort','tier','method'],sort=False):
        for family in ['all','classification','detection']:
            current=df if family=='all' else df[df.family.eq(family)]
            valid=current[current.status.eq('ok')]
            r=dict(cohort=cohort,tier=tier,method=method,family=family,
                   group_count=len(current),evaluable_group_count=len(valid),
                   insufficient_group_count=int(current.status.eq('insufficient_candidates').sum()),
                   unavailable_group_count=int(current.status.eq('incomplete_method_coverage').sum()),
                   out_of_scope_group_count=int(current.status.eq('raw_evaluated_only_on_base_intersection').sum()),
                   evaluated_candidate_count=int(valid.n.sum()),
                   top1_hits=int(valid.top1_hit_tie_aware.eq(True).sum()),
                   energy_top1_hits=int(valid.energy_top1_hit.eq(True).sum()),
                   energy_evaluable_group_count=int(valid.energy_excess_fraction.notna().sum()),
                   rank_evaluable_group_count=int(valid.rho.notna().sum()),
                   score_top_tie_groups=int(valid.score_top_ties.gt(1).sum()))
            for field in ['rho','tau_b','L_R','L_C','energy_excess_fraction',
                          'random_expected_L_R','random_expected_L_C','random_expected_energy_excess']:
                values=valid[field].dropna()
                for suffix,func in [('median',np.median),('mean',np.mean),('max',max)]:
                    r[field+'_'+suffix]=func(values) if len(values) else np.nan
            ms.append(r)
    ms=pd.DataFrame(ms)
    write(ms,'method_summary.csv')

    global_selection=pd.read_csv(methods_root/'tables/method_global_selection.csv')
    global_selection['native_performance_basis']='archived_completed_campaign_or_unmeasured'
    for i,row in global_selection[global_selection.model_id.eq(MODEL)].iterrows():
        rr=split[split.setup.eq(row.setup_id)&split.case.eq(row.selected_case_id)]
        if len(rr):
            assert row.completed_measurement_available is True or row.completed_measurement_available==True
            global_selection.loc[i,'native_fps']=rr.iloc[0].fps_median
            global_selection.loc[i,'quality_status']=rr.iloc[0].quality_status
            global_selection.loc[i,'native_performance_basis']='supplied_report_overlay_20261006'
    write(global_selection,'method_global_selection.csv')

    mask=mg.cohort.eq('augmented')&mg.tier.eq('technical')&mg.method.isin(METHODS)
    heat=mg[mask][['model_id','setup_id','method','n','cohort','tier','L_R',
        'selected_case','native_best_case','top1_hit_tie_aware','score_top_ties',
        'tie_L_R_min','tie_L_R_max']]
    assert len(heat)==126
    write(heat,'selector_loss_source.csv')
    current=groups[groups.cohort.eq('augmented')&groups.tier.eq('technical')].copy()
    current_reps=reps[reps.cohort.eq('augmented')&reps.tier.eq('technical')]
    stability=current[['model_id','setup_id','n','cohort','tier','L_R',
                       'generic_selected_case','native_best_case']].merge(
        current_reps[['model_id','setup_id','L_R_min','L_R_max','top1_hits']],
        on=['model_id','setup_id'],validate='one_to_one').rename(columns={
        'L_R_min':'repeat_L_R_min','L_R_max':'repeat_L_R_max','top1_hits':'repeat_top1_hits'})
    write(stability,'generic_stability_source.csv')

    method_labels=[r'Smallest boundary bytes (\cutbytes)',
        r'Historical weighted score (\weighted)',r'Stored H10 accelerator fit (\hardware)',
        r'Heuristic cycle without handover (\cycle)',r'Stored streaming rate (\stream)',
        r'Measured \generic{} completion']
    table=[r'\begin{table*}[t]',
     r'\caption{Selection on fixed candidate sets in 21 model/setup groups. Classification groups contain 17--20 candidates; detection groups contain three. YOLOv7 uses historical Generic measurements and the reported final native campaign; the other models retain their archived measurements. Throughput loss is relative to the native winner. Energy excess uses the 18 groups with matched energy evidence, excluding YOLOv7. Each group has equal weight.}',
     r'\label{tab:selectors}',r'\centering\small',r'\begin{tabular}{lrrrrrr}',r'\toprule',
     r'& \multicolumn{3}{c}{Native Top1 hits} & \multicolumn{2}{c}{Throughput loss $L_R$ (\%)} & Mean energy\\',
     r'\cmidrule(lr){2-4}\cmidrule(lr){5-6}',
     r'Selector & All /21 & Class. /9 & Detect. /12 & Median & Mean & excess /18 (\%)\\',r'\midrule']
    for method,label in zip(METHODS,method_labels):
        ss=ms[(ms.cohort=='augmented')&(ms.tier=='technical')&(ms.method==method)].set_index('family')
        r=ss.loc['all']
        table.append(f'{label} & {int(r.top1_hits)} & {int(ss.loc["classification","top1_hits"])} & '
                     f'{int(ss.loc["detection","top1_hits"])} & {100*r.L_R_median:.2f} & '
                     f'{100*r.L_R_mean:.2f} & {100*r.energy_excess_fraction_mean:.2f}'+r'\\')
    table += [r'\bottomrule',r'\end{tabular}',r'\end{table*}','']
    (output/'sections/ranking_tables.tex').write_text('\n'.join(table))

    tab=[r'\begin{table*}[!t]',
     r'\caption{All 21 technical Generic/Native ranking groups. $n$ counts measured candidates, $\rho$ is within-group Spearman correlation, and $L_R$ is native throughput lost by selecting the Generic winner. G-selected and N-best use three-repeat median rates. The final column enumerates nine dependent Generic/Native repetition combinations, not a confidence interval. YOLOv7 combines historical Generic and reported final native repetitions; other rows retain archived campaigns. DX denotes DeepX M1.}',
     r'\label{tab:allgroups}',r'\centering\small',r'\setlength{\tabcolsep}{3.0pt}',
     r'\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrllr@{}}',r'\toprule',
     r'Model & Setup & $n$ & $\rho$ & $L_R$ (\%) & G-selected & N-best & Repeat $L_R$ range (\%)\\',r'\midrule']
    for model in MODELS:
        for j,setup in enumerate(SETUPS):
            rr=current[(current.model_id==model)&(current.setup_id==setup)].iloc[0]
            ss=stability[(stability.model_id==model)&(stability.setup_id==setup)].iloc[0]
            tab.append(f'{LABELS[model] if j==0 else ""} & {"DX" if setup=="DeepX" else setup} & '
                       f'{int(rr.n)} & {rr.rho:.3f} & {100*rr.L_R:.2f} & {rr.generic_selected_case} & '
                       f'{rr.native_best_case} & {100*ss.repeat_L_R_min:.2f}--{100*ss.repeat_L_R_max:.2f}'+r'\\')
        if model!=MODELS[-1]:tab.append(r'\addlinespace[2pt]')
    tab += [r'\bottomrule',r'\end{tabular*}',r'\end{table*}','']
    (output/'sections/supplement_tables.tex').write_text('\n'.join(tab))

    (O/'README.md').write_text('''# Current report-overlay selection outputs

    These are the active selection metrics for the updated paper. Reproduce with
    the documented study command. The script reads the supplied
    report-derived CSV and the bundled historical tables, retaining candidate and
    quality-transfer gates. It does not inspect a raw ZIP or run inference.

    Nine YOLOv7 native rates and 27 native repetitions are report-based replacements;
    their Generic counterparts are historical. The other 195 native rows are
    unchanged. These comparisons describe selector transfer across recorded
    campaigns, not a controlled same-state runner comparison. Historical command
    hashes, runner IDs, endpoint IDs and makespans are cleared from overlaid rows;
    the report SHA identifies the replacement source. Current energy is unavailable
    for YOLOv7 and excluded from method energy summaries.

    Frozen method selections remain available for every displayed selector. Four
    static methods can also reconstruct their YOLOv7 score vectors from bundled
    graph fields; the stored H10 hardware-fit vector is not bundled, so its updated
    YOLOv7 rank correlations are NA. `rank_evaluable_group_count` reports correlation
    scope, while selection loss/hit scope remains 21 technical groups. This is not a
    refit. Existing historical tables in `analysis/evidence/tables` and
    `analysis/methods/tables` are provenance inputs, not current overlay outputs.
    ''')
    print(ms[(ms.cohort=='augmented')&(ms.tier=='technical')&ms.family.eq('all')&ms.method.isin(METHODS)]
          [['method','top1_hits','L_R_median','L_R_mean','energy_evaluable_group_count','energy_excess_fraction_mean']].to_string(index=False))
    print(stability[stability.model_id.eq(MODEL)].to_string(index=False))

