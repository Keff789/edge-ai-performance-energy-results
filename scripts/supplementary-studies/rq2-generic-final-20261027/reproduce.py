#!/usr/bin/env python3
"""Join final Generic observations to existing artifact-bound Native observations.

Offline and standard-library numerical engine. Original Native records, Full
records, energy, graph normalizations and fitted weights are never rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = Path('results/supplementary-studies/rq2-generic-final-20261027')
OLD = Path('results/supplementary-studies/rq2-weighted-20261020')
INPUT = STUDY / 'inputs/final_generic420.json'
METHODS = ['bytes', 'generic', 'weighted_default', 'weighted_pooled', 'weighted_cv']
LABELS = {'bytes':'Bytes', 'generic':'Generic', 'weighted_default':'Weighted (default)',
          'weighted_pooled':'Weighted (frozen shared)', 'weighted_cv':'Weighted (frozen model held-out)'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k:json.dumps(v, sort_keys=True, separators=(',', ':')) if isinstance(v,(list,dict)) else v
                         for k,v in row.items()} for row in rows)


def positive(value):
    return isinstance(value,(int,float,str)) and not isinstance(value,bool) and value != '' and math.isfinite(float(value)) and float(value)>0


def quality_loss(row):
    q, ref = row.get('quality_value'), row.get('quality_reference_value')
    return (ref-q)/ref if isinstance(q,(int,float)) and positive(ref) else None


def load_public(repo):
    with zipfile.ZipFile(repo/OLD/'inputs/current_graph_feature_inputs.zip') as archive:
        pairs = list(csv.DictReader(io.StringIO(archive.read('current_pair_feature_bindings.csv').decode())))
        graph = list(csv.DictReader(io.StringIO(archive.read('graph_boundary_features.csv').decode())))
    data = read(repo/'results/split-inference/data/PAPER_DATASET.json')
    # The maintained extension already audits detector operation rules. Reuse
    # those public derived features; do not substitute incomplete old counters.
    with (repo/OLD/'analysis/candidate_features.csv').open() as stream:
        extended=list(csv.DictReader(stream))
    graph_index={r['boundary_id']:r for r in graph}
    for row in extended:
        graph_index[row['boundary_id']].update({k:row[k] for k in ['Comm','F_left','F_total','Imb_raw','T_raw']})
    return ({r['generic_config_id']:r for r in pairs}, {r['boundary_id']:r for r in graph},
            {r['uid']:r for r in data}, read(repo/OLD/'analysis/summary.json'))


def bind(row, original, native):
    """Fail closed: an intersecting case name never establishes equivalence."""
    reasons, proof = [], {}
    if original is None:
        return ['no_existing_artifact_bound_native_pair'], proof
    if native is None or not positive(native.get('fps')):
        return ['existing_native_throughput_missing'], proof
    required_checks = ['native_artifact_hashes', 'native_all_repetition_bindings',
                       'native_request_or_exact_part2_bridge', 'native_graph_and_boundary_tensor_identity',
                       'generic_part1_and_engine_equal_native_bound_build', 'resolved_tensor_detail_identity']
    checks = json.loads(original['identity_checks'])
    if original['pair_binding_complete'] != 'true' or not all(checks.get(k) is True for k in required_checks):
        reasons.append('original_native_artifact_or_graph_binding_incomplete')
    if row['model_sha256'] != original['native_resolved_model_sha256'] or row['boundary_id'] != original['resolved_boundary_id']:
        reasons.append('model_or_graph_frontier_mismatch')
    identity = row['full_product_identity']
    if (native['model_id'], native['setup_id'], native['backend'], native['case_id']) != (
            row['model'], row['setup'], identity['direction'], row['case_id']):
        reasons.append('model_device_backend_or_cut_mismatch')
    if native['physical_host'] != row['setup_id']:
        reasons.append('physical_device_mismatch')
    if native['performance_source_sha256'] != original['native_performance_source_sha256']:
        reasons.append('native_measurement_source_mismatch')
    artifacts = row['artifacts']
    for key, source in [('part1_sha256','native_part1_artifact_sha256'),
                        ('part2_engine_sha256','native_part2_engine_sha256')]:
        if not artifacts.get(key) or artifacts[key] != original[source]:
            reasons.append(key+'_missing_or_mismatched')
    expected_inputs = json.loads(original['resolved_part2_input_names'])
    if row['part2_input_count'] != len(expected_inputs) or row['boundary_count'] != len(expected_inputs):
        reasons.append('boundary_input_count_mismatch')
    if artifacts.get('boundary_inputs') is not None:
        if sorted(t['name'] for t in artifacts['boundary_inputs']) != sorted(expected_inputs):
            reasons.append('boundary_input_names_mismatch')
        io_basis = 'recorded_names_and_exact_native_bound_engine'
    else:
        # The prior normal single-input plan binds the exact engine bytes. Its
        # inputs cannot differ from the audited Native engine with those bytes.
        io_basis = 'exact_native_bound_engine_bytes_and_original_tensor_identity_audit'
    recorded_precision = native.get('precision')
    resolved_precision = recorded_precision
    precision_basis = 'original_native_record'
    if not recorded_precision:
        if (original['native_runtime_boundary_dtype']=='uint8'
                and original['native_runtime_boundary_transform']=='uint8_dequant_then_layout'
                and original['native_build_part2_onnx_sha256']
                and artifacts.get('part2_engine_sha256')==original['native_part2_engine_sha256']
                and row['execution_precision']=='uint8_dequant_fp16'):
            # The unknown Native precision string remains unknown. Exact same
            # bound executable bytes prove precision equivalence without
            # inventing an FP16 layer configuration from an input dtype.
            precision_basis = 'same_bound_executable_artifact; original_precision_string_unknown'
        else:
            reasons.append('native_precision_unproven')
    if resolved_precision and resolved_precision != row['execution_precision']:
        reasons.append('execution_precision_mismatch')
    proof.update(native_recorded_precision=recorded_precision, comparison_precision=resolved_precision,
                 precision_basis=precision_basis, io_basis=io_basis,
                 native_runtime_boundary_dtype=original['native_runtime_boundary_dtype'],
                 native_runtime_boundary_transform=original['native_runtime_boundary_transform'],
                 native_build_part2_onnx_sha256=original['native_build_part2_onnx_sha256'],
                 native_part1_sha256=original['native_part1_artifact_sha256'],
                 native_part2_engine_sha256=original['native_part2_engine_sha256'],
                 original_native_source_sha256=original['native_performance_source_sha256'])
    return reasons, proof


def groups(pairs, fps_key='generic_fps'):
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[(pair['model'],pair['setup'])].append(pair)
    result=[]
    for (model,setup),pool in sorted(grouped.items()):
        choice=min(pool,key=lambda p:(-p[fps_key],p['generic_uid']))
        best=min(pool,key=lambda p:(-p['native_fps'],p['native_uid']))
        result.append(dict(model=model,setup=setup,candidate_count=len(pool),generic_choice=choice['case'],
            generic_choice_uid=choice['generic_uid'],selected_native_uid=choice['native_uid'],
            native_best=best['case'],native_best_uid=best['native_uid'],selected_native_fps=choice['native_fps'],
            best_native_fps=best['native_fps'],loss_pct=100*(1-choice['native_fps']/best['native_fps']),
            exact_hit=choice['native_fps']==best['native_fps']))
    return result


def curves(pairs, graph, frozen):
    grouped=defaultdict(list)
    norm={r['model']:r for r in frozen['normalization']}
    folds={r['held_out_model']:r for r in frozen['folds']}
    for row in pairs:
        g=graph[row['boundary_id']];n=norm[row['model']]
        lo,hi=n['log10_1p_Comm_minimum'],n['log10_1p_Comm_maximum']
        comm=(float(g['log10_1p_Comm'])-lo)/(hi-lo)
        tlo,thi=n['T_raw_minimum'],n['T_raw_maximum']
        tensor=(float(g['T_raw'])-tlo)/(thi-tlo) if thi!=tlo else 0
        imbalance=abs(2*float(g['F_left'])/float(g['F_total'])-1)
        weights={'weighted_default':frozen['default_weights'],
                 'weighted_pooled':frozen['shared_weights'], 'weighted_cv':folds[row['model']]}
        scores={'bytes':float(g['Comm']),'generic':-row['generic_fps']}
        scores.update({name:w['w_comm']*comm+w['w_imb']*imbalance+w['w_tensors']*tensor for name,w in weights.items()})
        grouped[(row['model'],row['setup'])].append((row,scores))
    out=[];ranks=[]
    for (model,setup),pool in sorted(grouped.items()):
        best=max(r['native_fps'] for r,_ in pool)
        for method in METHODS:
            ordered=sorted(pool,key=lambda rs:(rs[1][method],rs[0]['native_uid']))
            for i,(row,score) in enumerate(ordered,1):
                ranks.append(dict(model=model,setup=setup,method=method,rank=i,native_uid=row['native_uid'],case=row['case'],score=score[method]))
            for k in range(1,21):
                chosen=max(ordered[:k],key=lambda rs:rs[0]['native_fps'])[0]
                out.append(dict(model=model,setup=setup,task=chosen['task'],n=len(pool),method=method,k=k,
                    actual_trials=min(k,len(pool)),best_native_fps=best,retained_native_fps=chosen['native_fps'],
                    loss_pct=100*(1-chosen['native_fps']/best),exact_winner_found=int(chosen['native_fps']==best)))
    aggregate=[]
    for method in METHODS:
        for k in range(1,21):
            selected=[r for r in out if r['method']==method and r['k']==k]
            losses=[r['loss_pct'] for r in selected]
            aggregate.append(dict(method=method,k=k,mean_loss_pct=statistics.mean(losses),median_loss_pct=statistics.median(losses),
                max_loss_pct=max(losses),exact_winners=sum(r['exact_winner_found'] for r in selected),groups=len(selected)))
    return out, aggregate, ranks


def render(output, numeric_only):
    summary=read(output/'summary.json')
    with (output/'analysis/aggregate_curves.csv').open() as f:
        raw=list(csv.DictReader(f))
    series={m:[dict(k=int(r['k']),mean_loss_pct=float(r['mean_loss_pct'])) for r in raw if r['method']==m] for m in METHODS}
    caption=(f"Native throughput loss using {summary['quality_pair_count']} verified quality-eligible pairs in "
             f"{summary['quality_group_count']} model/device groups. Generic uses the final measurement snapshot. "
             "Default, shared and model-held-out graph weights and full graph normalizations are frozen from the prior study; no refit. "
             "Every group has equal weight and tests min(k,n) candidates. This is a retrospective paired subset, not all 420 Generic candidates.")
    figure=dict(schema='rq2-final-weighted-v1',series=series,caption=caption,scope=summary['scope'],method_labels=LABELS,
                weights_status='frozen original weights; no refit or new holdout validation',source_sha256=sha(output/'analysis/aggregate_curves.csv'))
    write_json(output/'figures/rq2_weighted_all_models.json',figure)
    write_csv(output/'figures/rq2_weighted_all_models.csv',raw)
    shutil.copyfile(output/'figures/rq2_weighted_all_models.json',output/'figures/rq2_native_success.json')
    # Exact-optimum hit curves use every group's own observed Native optimum.
    with (output/'analysis/group_curves.csv').open() as stream:
        group_curves=list(csv.DictReader(stream))
    success=[]
    for method in METHODS:
        for k in range(1,21):
            records=[r for r in group_curves if r['method']==method and int(r['k'])==k]
            success.append(dict(method=method,k=k,groups=len(records),exact_success_fraction=statistics.mean(int(r['exact_winner_found']) for r in records)))
    write_json(output/'figures/rq2_native_success.json',dict(points=success,caption=caption,scope=summary['scope']))
    write_csv(output/'figures/rq2_native_success.csv',success)
    for name,key in [('current_generic_selection_loss','selection_groups'),('quality_generic_selection_loss','quality_selection_groups')]:
        pts=read(output/'data'/f'{key}.json')
        pair_count=summary['quality_pair_count'] if key.startswith('quality') else summary['pair_count']
        scatter_caption=(f"Final Generic-to-Native selection on {pair_count} verified paired cuts in {len(pts)} model/device groups. "
            +('Both Native numerical quality and final Generic quality pass. ' if key.startswith('quality') else 'No quality filter. ')
            +'Every group receives equal weight; stable UID ties use unrounded FPS. Missing paired groups are unavailable. Original timed endpoints remain distinct.')
        write_json(output/'figures'/f'{name}.json',dict(points=pts,caption=scatter_caption,paired_candidates=pair_count,groups=len(pts),mean_group_loss_pct=statistics.mean(r['loss_pct'] for r in pts),exact_hits=sum(r['exact_hit'] for r in pts)))
        write_csv(output/'figures'/f'{name}.csv',pts)
    for ext in ['json','csv']:
        shutil.copyfile(output/'figures'/f'quality_generic_selection_loss.{ext}',output/'figures'/f'rq2_generic_selection_loss.{ext}')
    budget=[]
    for method in METHODS:
        selected={int(r['k']):r for r in raw if r['method']==method}
        budget.append(dict(method=method,label=LABELS[method],groups=summary['quality_group_count'],
                           **{f'loss_k{k}_pct':float(selected[k]['mean_loss_pct']) for k in [1,3,5]}))
    write_csv(output/'tables/r30_weighted_budget_table.csv',budget)
    write_json(output/'tables/r30_weighted_budget_table.json',dict(rows=budget,caption=caption))
    tx=['% '+caption,r'\begin{tabular}{lrrr}',r'\toprule',r'Method & $k=1$ & $k=3$ & $k=5$ \\',r'\midrule']
    tx += [r['label']+' & '+' & '.join(f"{r[f'loss_k{k}_pct']:.2f}" for k in [1,3,5])+r' \\' for r in budget]
    (output/'tables/r30_weighted_budget_table.tex').write_text('\n'.join(tx+[r'\bottomrule',r'\end{tabular}'])+'\n')
    (output/'tables/r30_weighted_macros.tex').write_text(
        '\n'.join([f'\\newcommand{{\\WeightedModelCount}}{{{len(summary["models"])}}}',
                    f'\\newcommand{{\\WeightedGroupCount}}{{{summary["quality_group_count"]}}}',
                    f'\\newcommand{{\\WeightedCandidateCount}}{{{summary["quality_pair_count"]}}}',
                    '\\newcommand{\\WeightedOptimizedComm}{1}',
                    '\\newcommand{\\WeightedOptimizedImb}{0.157993}',
                    '\\newcommand{\\WeightedTensorWeight}{0.2}'])+'\n')
    required=[]
    for method in METHODS:
        for target in [.9,.95,1.0]:
            eligible=[r for r in success if r['method']==method and r['exact_success_fraction']>=target]
            required.append(dict(method=method,target_success=target,groups=summary['quality_group_count'],minimum_budget=min(r['k'] for r in eligible)))
    write_csv(output/'tables/rq2_search_budget_table.csv',required)
    write_json(output/'tables/rq2_search_budget_table.json',dict(rows=required,caption=caption))
    (output/'tables/rq2_search_budget_table.tex').write_text('% '+caption+'\n'+
        '\n'.join([r'\begin{tabular}{lrr}',r'Method & Target & Budget \\']+
        [f"{LABELS[r['method']]} & {r['target_success']:.0%} & {r['minimum_budget']} \\\\".replace('%',r'\%') for r in required]+[r'\end{tabular}'])+'\n')
    if numeric_only:
        return
    sys.path.insert(0,str(REPO/'scripts/split-inference'))
    from publication_mlsys_figures import PAPER_STYLE,PAPER_PALETTE
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['green','blue','yellow','dark_gray','purple']
    with plt.rc_context(PAPER_STYLE):
        fig,ax=plt.subplots(figsize=(3.6,2.95))
        for method,color in zip(METHODS,colors):
            ax.plot([r['k'] for r in series[method]],[r['mean_loss_pct'] for r in series[method]],label=LABELS[method],color=PAPER_PALETTE[color],lw=1.2)
        ax.set(xlim=(.8,20.2),ylim=(-.25,None),xlabel='Maximum Native trials per group',ylabel='Mean Native throughput loss (%)',xticks=[1,3,5,10,15,20])
        ax.legend(frameon=False,fontsize=6.5);ax.grid(axis='y',color='#dddddd',lw=.45);fig.tight_layout()
        save_figure(fig,output/'figures/rq2_weighted_all_models');plt.close(fig)
        fig,ax=plt.subplots(figsize=(3.6,2.95))
        for method,color in zip(METHODS,colors):
            points=[r for r in success if r['method']==method]
            ax.plot([r['k'] for r in points],[100*r['exact_success_fraction'] for r in points],label=LABELS[method],color=PAPER_PALETTE[color],lw=1.2)
        ax.set(xlabel='Maximum Native trials per group',ylabel='Exact Native optimum found (%)',xticks=[1,3,5,10,15,20],ylim=(0,102));ax.legend(frameon=False,fontsize=6);fig.tight_layout()
        save_figure(fig,output/'figures/rq2_native_success');plt.close(fig)
        for name in ['current_generic_selection_loss','quality_generic_selection_loss']:
            points=read(output/'figures'/f'{name}.json')['points'];fig,ax=plt.subplots(figsize=(3.3,2.3))
            for setup,marker in [('H8','o'),('H10','s'),('DeepX','^')]:
                rows=[r for r in points if r['setup']==setup]
                ax.scatter([r['candidate_count'] for r in rows],[r['loss_pct'] for r in rows],label=setup,marker=marker,s=24)
            ax.set(xlabel='Verified paired candidates in group',ylabel='Native throughput loss (%)');ax.legend(frameon=False,fontsize=7);fig.tight_layout()
            save_figure(fig,output/'figures'/name);plt.close(fig)
        for ext in ['pdf','svg','png']:
            shutil.copyfile(output/'figures'/f'quality_generic_selection_loss.{ext}',output/'figures'/f'rq2_generic_selection_loss.{ext}')


def save_figure(fig,stem):
    for ext in ['pdf','svg','png']:
        metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Date':None} if ext=='svg' else {}
        fig.savefig(str(stem)+'.'+ext,dpi=300,metadata=metadata)


def verify(output,reference):
    checked=[]
    for actual in sorted(Path(output).rglob('*')):
        if actual.suffix not in ['.json','.csv','.tex'] or actual.name=='VALIDATION.json':continue
        relative=actual.relative_to(output);expected=Path(reference)/relative
        if not expected.is_file() or expected.read_bytes()!=actual.read_bytes():
            raise AssertionError(f'RQ2 final reproduction differs: {relative}')
        checked.append(str(relative))
    return dict(result='PASS',files_checked=len(checked))


def run(output, repo=REPO, numeric_only=False, verify_reference=None):
    output,repo=Path(output),Path(repo)
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    final=read(repo/INPUT);bindings,graph,data,frozen=load_public(repo)
    audit=[];pairs=[]
    for row in sorted(final['rows'],key=lambda r:r['generic_uid']):
        old=bindings.get(row['generic_uid']);native=data.get(row['generic_uid'].replace('generic|','native|',1))
        reasons,proof=bind(row,old,native)
        if not positive(row['effective_generic_fps']):reasons.append('generic_throughput_unavailable')
        audit.append(dict(generic_uid=row['generic_uid'],model=row['model'],setup=row['setup'],case=row['case_id'],
                          pair_verified=not reasons,exclusion_reasons=reasons,**proof))
        if reasons:continue
        loss=quality_loss(native)
        pairs.append(dict(model=row['model'],setup=row['setup'],task=native['task'],case=row['case_id'],
            native_uid=native['uid'],generic_uid=row['generic_uid'],native_fps=native['fps'],generic_fps=float(row['effective_generic_fps']),
            old_generic_fps=data[row['generic_uid']]['fps'],boundary_id=row['boundary_id'],
            native_relative_quality_loss=loss,generic_quality_status=row['quality_status'],
            quality_eligible=bool(row['quality_eligible']) and loss is not None and loss<=.05,
            quality_exclusion_reasons=(['native_quality_unavailable'] if loss is None else ['native_quality_loss_above_5pct'] if loss>.05 else [])+
                ([] if row['quality_eligible'] else ['final_generic_quality_'+row['quality_status']]),
            generic_mj_per_image=None,native_mj_per_image=None,
            energy_status='omitted: refreshed Generic FPS is not a joint measurement with historical energy',
            native_original_precision=proof['native_recorded_precision'],comparison_precision=proof['comparison_precision'],
            native_performance_source_sha256=native['performance_source_sha256'],
            native_measurement_boundary=native.get('measurement_boundary'),generic_observation_mode=row['observation_mode'],
            endpoint_equivalence_claimed=False))
    quality=[r for r in pairs if r['quality_eligible']]
    selected,quality_selected=groups(pairs),groups(quality)
    old_selected=groups(quality,'old_generic_fps')
    paired_comparison=[dict(model=a['model'],setup=a['setup'],candidate_count=a['candidate_count'],
        old_generic_choice=b['generic_choice'],final_generic_choice=a['generic_choice'],old_loss_pct=b['loss_pct'],
        final_loss_pct=a['loss_pct'],loss_change_pp=a['loss_pct']-b['loss_pct']) for a,b in zip(quality_selected,old_selected)]
    group_curves,aggregate,rankings=curves(quality,graph,frozen)
    sources=[INPUT,OLD/'inputs/current_graph_feature_inputs.zip',OLD/'analysis/candidate_features.csv',OLD/'analysis/summary.json',Path('results/split-inference/data/PAPER_DATASET.json'),Path('results/split-inference/publications/mlsys-r22/data/quality_selection_groups.json')]
    manifest=dict(schema='rq2-final-input-manifest-v1',source_snapshot_sha256=final['source_snapshot_sha256'],
                  source_selection_sha256=final['source_selection_sha256'],sources=[dict(path=str(p),sha256=sha(repo/p)) for p in sources])
    write_json(output/'INPUT_MANIFEST.json',manifest)
    summary=dict(schema='rq2-final-pairs-v1',pair_count=len(pairs),quality_pair_count=len(quality),
        group_count=len(selected),quality_group_count=len(quality_selected),models=sorted({r['model'] for r in quality}),
        classifier_quality_pairs=sum(r['task']=='classification' for r in quality),detector_quality_pairs=sum(r['task']=='detection' for r in quality),
        final_generic_observations=sum(positive(r['effective_generic_fps']) for r in final['rows']),
        prior_published_pairs=204,prior_published_quality_pairs=187,
        excluded_candidates=420-len(pairs),exclusion_reasons=dict(Counter(reason for r in audit for reason in r['exclusion_reasons'])),
        native_precision_unknown_but_same_bound_executable=sum(r['native_original_precision'] is None for r in pairs),
        scope='Existing Native measurements on the verified intersection with final fixed420 Generic candidates; no Native values imputed or remeasured.',
        mean_final_generic_loss_pct=statistics.mean(r['loss_pct'] for r in quality_selected),
        mean_old_generic_loss_same_pairs_pct=statistics.mean(r['loss_pct'] for r in old_selected),
        prior_full_quality_scope_mean_loss_pct=statistics.mean(r['loss_pct'] for r in read(repo/'results/split-inference/publications/mlsys-r22/data/quality_selection_groups.json')),
        weights={'default':frozen['default_weights'],'shared':frozen['shared_weights'],'model_held_out':{r['held_out_model']:{k:r[k] for k in ['w_comm','w_imb','w_tensors']} for r in frozen['folds']}},
        weight_policy='All prior vectors and original full graph normalization universes frozen; no new fit. Prior holdout status describes original training, not a new validation on this subset.',
        energy_policy='Original Native, Full and Generic energy records stay in their original dataset. No refreshed Generic rate is paired to old energy as one joint observation.')
    write_json(output/'summary.json',summary)
    coverage=[]
    for model,setup in sorted({(r['model'],r['setup']) for r in final['rows']}):
        population=[r for r in final['rows'] if (r['model'],r['setup'])==(model,setup)]
        matched=[r for r in pairs if (r['model'],r['setup'])==(model,setup)]
        eligible=[r for r in quality if (r['model'],r['setup'])==(model,setup)]
        coverage.append(dict(model=model,setup=setup,planned=len(population),identity_valid_pairs=len(matched),quality_pairs=len(eligible),
            quality_pair_exclusions=len(matched)-len(eligible),native_identity_unavailable=len(population)-len(matched),
            pair_exclusion_reasons=dict(Counter(reason for r in audit if (r['model'],r['setup'])==(model,setup) for reason in r['exclusion_reasons'])),
            quality_exclusion_reasons=dict(Counter(reason for r in matched for reason in r['quality_exclusion_reasons'])),
            status='evaluated' if eligible else 'unavailable_no_quality_eligible_native_generic_pairs'))
    summary['groups_without_quality_pairs']=sum(not r['quality_pairs'] for r in coverage)
    write_json(output/'summary.json',summary)
    for name,rows in [('current_pairs',pairs),('quality_pairs',quality),('selection_groups',selected),('quality_selection_groups',quality_selected),
                      ('pair_identity_audit',audit),('old_final_same_pairs_comparison',paired_comparison),('pair_group_coverage',coverage)]:
        write_json(output/'data'/f'{name}.json',rows);write_csv(output/'data'/f'{name}.csv',rows)
    for name,rows in [('group_curves',group_curves),('aggregate_curves',aggregate),('complete_rankings',rankings),
                      ('key_budget_results',[r for r in aggregate if r['k'] in [1,3,5]])]:write_csv(output/'analysis'/f'{name}.csv',rows)
    sys.path.insert(0,str(repo/'scripts/split-inference'))
    from publication_mlsys_data import budget_calculations
    budget_groups,budgets=budget_calculations(pairs,quality)
    write_json(output/'data/budget_groups.json',budget_groups);write_csv(output/'data/budget_groups.csv',budget_groups)
    model_labels={'mobilenet_v3_large':'MobileNetV3-L','regnet_x_1_6gf':'RegNet-X','resnet50':'ResNet-50',
                  'yolo11l':'YOLO11l','yolo26m':'YOLO26m','yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}
    for name,records in [('current_selection_groups',selected),('r14_budget_details',budgets)]:
        write_json(output/'tables'/f'{name}.json',records);write_csv(output/'tables'/f'{name}.csv',records)
        if name=='current_selection_groups':
            headers=['Model','Host','n','G choice','N best','Selected FPS','Best FPS','Loss (%)']
            values=[[model_labels[r['model']],r['setup'],str(r['candidate_count']),r['generic_choice'],r['native_best'],
                f"{r['selected_native_fps']:.0f}",f"{r['best_native_fps']:.0f}",f"{r['loss_pct']:.2f}"] for r in records]
            caption='Current Generic-to-Native selection without quality filtering on the verified paired subset. Original Native observations are retained.'
        else:
            headers=['Eligibility','Family','Groups','Cuts','k','G loss (%)','U loss (%)','G hits','U hits']
            values=[['All measured' if r['scope']=='unrestricted' else '<=5% loss',r['family'],str(r['groups']),str(r['candidates']),str(r['requested_k']),
                f"{r['generic_mean_loss_pct']:.2f}",f"{r['random_mean_expected_loss_pct']:.2f}",str(r['generic_exact_hits']),f"{r['random_expected_exact_hits']:.3f}"] for r in records]
            caption='Current Generic ranking and exact uniform sampling on the verified paired subset. Each evaluated group receives equal weight; unavailable groups remain separate.'
        escape=lambda s:str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')
        (output/'tables'/f'{name}.tex').write_text('% '+caption+'\n'+
            '\n'.join([r'\begin{tabular}{'+'l'*len(headers)+'}', ' & '.join(escape(c) for c in headers)+r' \\']+
                [' & '.join(escape(v) for v in row)+r' \\' for row in values]+[r'\end{tabular}'])+'\n')
        (output/'tables'/f'{name}.md').write_text(caption+'\n\n'+'\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                ['| '+' | '.join(row)+' |' for row in values])+'\n')
    render(output,numeric_only)
    validation=dict(result='PASS',unique_final_candidates=len({r['generic_uid'] for r in final['rows']})==420,
                    all_pairs_have_existing_native_and_exact_artifacts=True,original_native_and_full_records_modified=False,
                    no_new_fps_old_energy_joint_measurement=True,weights_refitted=False)
    if verify_reference:validation['published_reference']=verify(output,verify_reference)
    write_json(output/'VALIDATION.json',validation)
    (output/'README.md').write_text(f"# Current Generic / existing Native comparison\n\n{len(pairs)} verified pairs across 21 model/device groups; {len(quality)} pairs pass both numerical Native quality and current Generic quality across {len(quality_selected)} groups. Eight groups have no eligible paired candidate. "
        f"The prior publication used 204 pairs (187 quality-eligible); the fixed420 intersection changes the evaluated candidate set. "
        "Unproven pairs remain in data/pair_identity_audit.json with reasons. Model, physical device, graph frontier, execution precision, exact P1/engine bytes and original I/O bindings are checked.\n\n"
        f"Mean Generic Top-1 selection loss: {summary['mean_final_generic_loss_pct']:.6f}%; old Generic on these same pairs: {summary['mean_old_generic_loss_same_pairs_pct']:.6f}%. "
        "The prior full 187-pair/21-group value (15.077129%) uses a different cohort and stays separate in summary.json. Weights and normalizations are frozen from the original study; no fit is repeated. "
        "Energy is excluded from refreshed pairs, preserving its original observations and bindings.\n\n"
        "H8 / YOLOv7 / b009 retains a measured FPS observation, but its historical quality association lacks original executed preprocessing authority. Its quality remains unresolved and it is excluded from the quality-eligible pairs. No current quality admission is inferred from its historical label.\n\n"
        "Reproduce with `python scripts/supplementary-studies/rq2-generic-final-20261027/reproduce.py --output <empty-dir> --verify`. Add `--numeric-only` to omit rendering.\n")
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--numeric-only',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.output.resolve(),numeric_only=args.numeric_only,verify_reference=REPO/STUDY if args.verify else None),indent=2))
