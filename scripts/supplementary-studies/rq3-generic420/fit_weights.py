#!/usr/bin/env python3
"""Reproduce model-held-out graph weight fitting on the pinned Generic snapshot.

Needs Python, numpy, pandas. Inputs contain only graph features and source-admitted
measurements. No device access, execution, new admissions, or source mutation.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd

SCOPES = ('global', 'task', 'device', 'task_device')
DEFAULT = np.array([1., 3., .2]); DEFAULT /= DEFAULT.sum()
BASELINES = {'boundary_size': np.array([1.,0.,0.]), 'weighted_default':DEFAULT,
             'imbalance_only':np.array([0.,1.,0.]), 'tensor_count_only':np.array([0.,0.,1.])}
BUDGETS = (1,3,5)


def weight_grid(denominator):
    # A nested simplex lattice, including all pure-feature endpoints and the exact default.
    w = np.array([(i/denominator,j/denominator,(denominator-i-j)/denominator)
                  for i in range(denominator+1) for j in range(denominator-i+1)],dtype=float)
    return np.unique(np.vstack([w, DEFAULT]),axis=0)


def make_groups(df, tie_policy="uid"):
    groups=[]
    for (model, device), rows in df[df.analysis_eligible].groupby(['model','accelerator'],sort=True):
        rows=rows.sort_values(['cut_bytes','generic_uid'] if tie_policy=='bytes' else ['generic_uid'],kind='stable').reset_index(drop=True)
        assert rows.task.nunique()==1 and rows.case_id.nunique()==len(rows)
        x=rows[['C','I','T']].to_numpy(float); fps=rows.fps.to_numpy(float)
        assert np.isfinite(x).all() and np.isfinite(fps).all() and (fps>0).all()
        groups.append(dict(model=model,accelerator=device,task=rows.task.iloc[0],
                           rows=rows,x=x,fps=fps,n=len(rows),best=float(fps.max()),
                           complete=bool(rows.analysis_group_complete.iloc[0])))
    return groups


def ranked_metrics(weights, group, ks=range(1,21)):
    w=np.atleast_2d(weights)
    score=np.round(w@group['x'].T,12)
    order=np.argsort(score,axis=1,kind='stable')
    rates=group['fps'][order]
    best=np.maximum.accumulate(rates,axis=1)
    idx=np.array([min(k,group['n'])-1 for k in ks])
    return 1-best[:,idx]/group['best'], order


def training_masks(groups, scope, test_group=None, fit_key=None, held_out_models=None):
    if test_group is not None:
        excluded = held_out_models or [test_group['model']]
        mask=np.array([g['model'] not in excluded for g in groups])
        task=test_group['task']; device=test_group['accelerator']
    else:
        mask=np.ones(len(groups),dtype=bool);task,device=fit_key
    if scope in ('task','task_device'):mask &= np.array([g['task']==task for g in groups])
    if scope in ('device','task_device'):mask &= np.array([g['accelerator']==device for g in groups])
    return mask


def fit_weights(weights, group_losses, groups, mask):
    ids=np.flatnonzero(mask)
    if not len(ids): raise ValueError('Empty training scope')
    objective=group_losses[:,ids].mean(axis=1)
    minimum=float(objective.min())
    optimal=np.flatnonzero(np.abs(objective-minimum)<=1e-12)
    # Tie selection is training-only: widest local gap from every score-equality line,
    # measured within the sum(weights)=1 plane. Coincident feature rows are ignored.
    pairdiff=[]
    for i in ids:
        x=groups[i]['x']
        a,b=np.triu_indices(len(x),1)
        delta=x[a]-x[b]
        projected=delta-delta.mean(axis=1,keepdims=True)
        norm=np.linalg.norm(projected,axis=1)
        valid=norm>1e-12
        pairdiff.extend(delta[valid]/norm[valid,None])
    if len(pairdiff):
        lines=np.unique(np.round(np.array(pairdiff),14),axis=0)
        margins=np.empty(len(optimal))
        for start in range(0,len(optimal),2048):
            chunk=optimal[start:start+2048]
            margins[start:start+len(chunk)]=np.min(np.abs(weights[chunk]@lines.T),axis=1)
    else:margins=np.ones(len(optimal))
    max_margin=float(margins.max())
    candidates=optimal[np.abs(margins-max_margin)<=1e-12]
    distance=((weights[candidates]-DEFAULT)**2).sum(axis=1)
    candidates=candidates[np.abs(distance-distance.min())<=1e-12]
    # np.unique yielded lexicographic C/I/T order. Last tie is deterministic.
    chosen=int(candidates[0])
    return chosen,dict(train_loss=float(objective[chosen]), training_optima_count=int(len(optimal)),
                       training_rank_margin=max_margin,train_groups=int(len(ids)),
                       train_models=sorted({groups[i]['model'] for i in ids}),
                       train_candidates=sum(groups[i]['n'] for i in ids))


def metrics_row(method, weights, group, fold_id, training=None):
    losses,order=ranked_metrics(weights,group)
    rows=[]
    for k in range(1,21):
        selected=order[0,:min(k,group['n'])]
        chosen=selected[np.argmax(group['fps'][selected])]
        l=float(losses[0,k-1])
        rows.append(dict(method=method,fold_id=fold_id,model=group['model'],
                         task=group['task'],accelerator=group['accelerator'],eligible_n=group['n'],
                         group_complete=group['complete'],k=k,tested_n=min(k,group['n']),
                         loss_pct=100*l,exact_hit=bool(l<=1e-12),within_1pct=bool(l<=.01+1e-12),
                         within_5pct=bool(l<=.05+1e-12),best_case=group['rows'].case_id.iloc[np.argmax(group['fps'])],
                         best_fps=group['best'],shortlist_best_case=group['rows'].case_id.iloc[chosen],
                         shortlist_best_fps=float(group['fps'][chosen]),
                         selected_cases=','.join(group['rows'].case_id.iloc[selected]),
                         w_comm=float(weights[0]),w_imb=float(weights[1]),w_ten=float(weights[2]),
                         train_loss_pct=100*training['train_loss'] if training else np.nan))
    return rows


def summarize(rows):
    d=pd.DataFrame(rows);out=[]
    for task in ['all']+sorted(d.task.unique().tolist()):
        for device in ['all']+sorted(d.accelerator.unique().tolist()):
            for completion in ['all_available','complete_groups','more_than_five_candidates']:
                s=d.copy()
                if task!='all':s=s[s.task==task]
                if device!='all':s=s[s.accelerator==device]
                if completion=='complete_groups':s=s[s.group_complete]
                if completion=='more_than_five_candidates':s=s[s.eligible_n>5]
                for (method,k),t in s.groupby(['method','k'],sort=True):
                    out.append(dict(task=task,accelerator=device,group_scope=completion,method=method,k=int(k),
                                    groups=len(t),models=t.model.nunique(),candidates=int(t.eligible_n.sum()),
                                    mean_loss_pct=float(t.loss_pct.mean()),median_loss_pct=float(t.loss_pct.median()),
                                    max_loss_pct=float(t.loss_pct.max()),exact_hits=int(t.exact_hit.sum()),
                                    within_1pct_hits=int(t.within_1pct.sum()),within_5pct_hits=int(t.within_5pct.sum())))
    return pd.DataFrame(out)


def run_one(df, denominator, objective_ks, outdir, family_holdout=False, tie_policy="uid"):
    outdir.mkdir(parents=True,exist_ok=True)
    groups=make_groups(df,tie_policy);w=weight_grid(denominator)
    print(f'{outdir.name}: {len(w)} weights, {len(groups)} groups, budgets {objective_ks}',flush=True)
    loss=np.stack([ranked_metrics(w,g,objective_ks)[0].mean(axis=1) for g in groups],axis=1)
    folds=[]; metrics=[];cache={}
    for scope in SCOPES:
        for g in groups:
            task=g['task'] if scope in ('task','task_device') else 'all'
            device=g['accelerator'] if scope in ('device','task_device') else 'all'
            excluded=['yolo26m','yolo26s'] if family_holdout and g['model'] in ('yolo26m','yolo26s') else [g['model']]
            fold_model='yolo26_family' if len(excluded)>1 else g['model']
            key=(scope,fold_model,task,device)
            if key not in cache:
                mask=training_masks(groups,scope,g,held_out_models=excluded)
                assert all(groups[i]['model'] not in excluded for i in np.flatnonzero(mask))
                idx,info=fit_weights(w,loss,groups,mask)
                fold_id='|'.join(key)
                cache[key]=(idx,info,fold_id)
                folds.append(dict(method=scope,fold_id=fold_id,test_model=fold_model,held_out_models=';'.join(excluded),train_task=task,
                                  train_accelerator=device,w_comm=w[idx,0],w_imb=w[idx,1],w_ten=w[idx,2],
                                  train_loss_pct=100*info['train_loss'],train_groups=info['train_groups'],
                                  train_models=';'.join(info['train_models']),train_model_count=len(info['train_models']),
                                  train_candidates=info['train_candidates'],
                                  training_optima_count=info['training_optima_count'],
                                  training_rank_margin=info['training_rank_margin'],
                                  held_out_model_absent_from_training=True))
            idx,info,fold_id=cache[key]
            metrics.extend(metrics_row(scope,w[idx],g,fold_id,info))
    for name,weight in BASELINES.items():
        for g in groups:metrics.extend(metrics_row(name,weight,g,'fixed_baseline'))
    pd.DataFrame(folds).to_csv(outdir/'fold_weights.csv',index=False)
    pd.DataFrame(metrics).to_csv(outdir/'heldout_metrics.csv',index=False)
    summarize(metrics).to_csv(outdir/'summary.csv',index=False)
    # These full-data fits are descriptive/deployment weights. They never generate held-out claims.
    full=[]
    for scope in SCOPES:
        tasks=sorted({g['task'] for g in groups}) if scope in ('task','task_device') else ['all']
        devices=sorted({g['accelerator'] for g in groups}) if scope in ('device','task_device') else ['all']
        for task in tasks:
            for device in devices:
                mask=training_masks(groups,scope,fit_key=(task,device))
                idx,info=fit_weights(w,loss,groups,mask)
                full.append(dict(method=scope,task=task,accelerator=device,w_comm=w[idx,0],w_imb=w[idx,1],
                                 w_ten=w[idx,2],train_loss_pct=100*info['train_loss'],
                                 train_groups=info['train_groups'],train_models=';'.join(info['train_models']),
                                 training_optima_count=info['training_optima_count'],training_rank_margin=info['training_rank_margin'],
                                 evaluation_role='fit_on_all_available_data_not_holdout'))
    pd.DataFrame(full).to_csv(outdir/'full_data_weights.csv',index=False)
    config=dict(denominator=denominator,grid_step=1/denominator,grid_points=len(w),
                objective_budgets=list(objective_ks),objective='equal mean over model-device groups and listed budgets of 1-best_shortlist_FPS/best_group_FPS',
                score='w_comm*C + w_imb*I + w_ten*T; nonnegative weights sum to one; smaller is preferred',
                tie_rank=('round score to 12 decimals; ascending cut_bytes, then generic_uid; stable sort' if tie_policy=='bytes' else 'round score to 12 decimals; ascending generic_uid; stable sort'),
                tie_fit='minimum training objective, maximum minimum score-line distance on training groups, nearest normalized default, lexicographic weights',
                holdout=('YOLO26m and YOLO26s jointly held out; other models individually' if family_holdout else 'entire model, including all accelerator groups')+'; no test labels or graph pairs used for fitting/tie selection',
                candidate_scope='measured and quality-admitted cuts only; unmeasured excluded; min(k,n)',
                groups=len(groups),models=len({g['model'] for g in groups}),candidates=sum(g['n'] for g in groups),
                limitations='Group coverage is recorded separately; incomplete snapshots exclude pending results. Grid minimizer is not a proof of the continuous global optimum.',
                full_data_weights='descriptive only; evaluated loss is training loss, not generalization')
    (outdir/'fit_config.json').write_text(json.dumps(config,indent=2)+'\n')
    return pd.DataFrame(metrics)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[3]/'results/supplementary-studies/rq3-generic420-20261027/inputs/candidates.csv')
    ap.add_argument('--out',type=Path,default=Path(__file__).parent/'fit_results')
    ap.add_argument('--denominator',type=int,default=400)
    ap.add_argument('--skip-sensitivity',action='store_true')
    args=ap.parse_args()
    if args.denominator<2: raise ValueError('denominator must be at least 2')
    if args.out.exists() and any(args.out.iterdir()): raise ValueError('Use a fresh fit output directory')
    d=pd.read_csv(args.input)
    assert d.generic_uid.is_unique
    primary=run_one(d,args.denominator,BUDGETS,args.out/'primary')
    if not args.skip_sensitivity:
        coarse=run_one(d,args.denominator//2,BUDGETS,args.out/'coarse_grid')
        # Every observation tested against the same holdout; this checks discretization effects.
        cols=['method','model','task','accelerator','k']
        cmp=primary.merge(coarse,on=cols,suffixes=('_fine','_coarse'))
        cmp['loss_delta_pct']=cmp.loss_pct_fine-cmp.loss_pct_coarse
        cmp.to_csv(args.out/'grid_comparison.csv',index=False)
        run_one(d,args.denominator,(5,),args.out/'budget5_fit')
        run_one(d,args.denominator,BUDGETS,args.out/'family_holdout',family_holdout=True)
        run_one(d,args.denominator,BUDGETS,args.out/'tie_secondary_bytes',tie_policy='bytes')
    config={'input':'inputs/candidates.csv','input_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.out/'provenance.json').write_text(json.dumps(config,indent=2)+'\n')
    s=pd.read_csv(args.out/'primary/summary.csv')
    print(s[(s.task=='all')&(s.accelerator=='all')&(s.group_scope=='all_available')&s.k.isin([1,3,5])].to_string(index=False))

if __name__=='__main__':main()
