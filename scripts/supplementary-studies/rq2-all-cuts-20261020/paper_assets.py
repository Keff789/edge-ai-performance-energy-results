#!/usr/bin/env python3
"""English RQ2 paper assets from the full-budget analysis CSVs.

No hardware measurements or fitting. See the enclosing reproduction entry point.
"""
from pathlib import Path
import argparse
import csv
import json
import os
import math
import importlib.util


def load_style():
    path=Path(__file__).resolve().parent/'figure_style.py'
    spec=importlib.util.spec_from_file_location('rq2_figure_style',path)
    style=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    return style


PALETTE = load_style().PALETTE
METHODS = [
    ('cut_bytes_only', 'Bytes', PALETTE['green'], '-', 'o'),
    ('weighted_score', 'Weighted', PALETTE['yellow'], '-', 's'),
    ('onnx_real_boundary_hardware_aware', 'Fit-H10', PALETTE['orange'], '--', '^'),
    ('cycle_time_no_handover', 'Cycle', PALETTE['purple'], ':', 'v'),
    ('stored_predicted_stream_fps', 'Stream', PALETTE['red'], '-.', 'D'),
    ('measured_generic_completion', 'Generic', PALETTE['blue'], '-', 'P'),
    ('uniform_random', 'Random', PALETTE['dark_gray'], '--', None),
]
CURRENT = [
    ('boundary_bytes', 'Bytes', PALETTE['green'], '-', 'o'),
    ('generic', 'Generic', PALETTE['blue'], '-', 'P'),
    ('calibrated_generic', 'Calibrated', PALETTE['orange'], '-.', 's'),
    ('uniform_random', 'Random', PALETTE['dark_gray'], '--', None),
]

def read(root, name):
    with (root/name).open(newline='') as f:
        return list(csv.DictReader(f))

def table_rows(data_root):
    graph=read(data_root,'success/graph_rules/required_budgets.csv')
    current=read(data_root,'success/current/minimum_budgets_for_target_success.csv')
    out=[]
    for key, label, *_ in METHODS[:-1]:
        vals=[]
        for criterion,target in [('exact_optimum','8/9'),('exact_optimum','100%'),
                                 ('within_1pct','100%'),('within_5pct','100%')]:
            r=next(r for r in graph if r['family']=='classification' and r['method']==key
                   and r['criterion']==criterion and r['target_label']==target)
            vals.append(int(r['minimum_requested_k']))
        out.append({'measurement_set':'Graph-score comparison','method':label,
                    **dict(zip(['exact_8of9','exact_9of9','within_1pct_9of9','within_5pct_9of9'],vals))})
    for key,label,*_ in CURRENT[:-1]:
        vals=[]
        for tolerance,target in [(0,8/9),(0,1),(1,1),(5,1)]:
            r=next(r for r in current if r['view']=='quality_5pct' and r['task']=='classification'
                   and r['method']==key and float(r['loss_tolerance_pct'])==tolerance
                   and abs(float(r['target_success_fraction'])-target)<1e-12
                   and r['criterion']=='mean_fixed_group_coverage')
            vals.append(int(r['minimum_max_budget']))
        out.append({'measurement_set':'Deployment comparison, quality-filtered','method':label,
                    **dict(zip(['exact_8of9','exact_9of9','within_1pct_9of9','within_5pct_9of9'],vals))})
    return out

def write_table(data_root, output_dir):
    rows=table_rows(data_root)
    folder=output_dir/'tables'
    folder.mkdir(parents=True,exist_ok=True)
    stem=folder/'rq2_search_budget_table'
    with stem.with_suffix('.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
    stem.with_suffix('.json').write_text(json.dumps(rows,indent=2)+'\n')
    lines=[r'\begin{table*}[t]',r'\centering\small',
        r'\caption{Minimum maximum Native-trial budget per classifier group. Each measurement set contains nine groups. Columns require an exact optimum in eight or nine groups, or a cut within 1\% or 5\% of the Native optimum in all nine. Budgets are capped at each group\textquotesingle s candidate count. Throughput tolerances are separate from the deployment quality filter.}',
        r'\label{tab:rq2-search-budgets}',r'\begin{tabular}{llrrrr}',r'\toprule',
        r'Measurement set & Selector & Exact, 8/9 & Exact, 9/9 & $\leq1\%$, 9/9 & $\leq5\%$, 9/9\\',r'\midrule']
    previous=None
    for r in rows:
        label=r['measurement_set'] if r['measurement_set']!=previous else ''
        if previous and label: lines.append(r'\midrule')
        if label=='Deployment comparison, quality-filtered':label='Deployment comparison'
        lines.append(' & '.join([label,r['method']]+[str(r[k]) for k in ['exact_8of9','exact_9of9','within_1pct_9of9','within_5pct_9of9']])+r'\\')
        previous=r['measurement_set']
    lines += [r'\bottomrule',r'\end{tabular}',r'\end{table*}','']
    stem.with_suffix('.tex').write_text('\n'.join(lines))
    return rows


def scatter_payload(data_root):
    """Preserve the exact R22 scatter coordinates and check the current inputs."""
    reference_path = (Path(__file__).resolve().parents[3] /
        'results/split-inference/publications/mlsys-r22/figures/FIGURE_DATA.json')
    reference = json.loads(reference_path.read_text())['quality_generic_selection_loss']
    rows = [r for r in read(data_root,'current/all_k_group_curves.csv')
            if r['view']=='quality_5pct' and r['method']=='generic' and int(r['k'])==1]
    groups = {(r['model'],r['setup']):r for r in rows}
    winners = {(r['model'],r['setup']):r for r in read(data_root,'current/group_correlations.csv')
               if r['view']=='quality_5pct'}
    assert len(groups)==len(reference['points'])==21
    assert sum(int(r['n']) for r in rows)==reference['paired_candidates']==187
    points=[]
    errors=[]
    fields=['model','setup','candidate_count','exact_hit','generic_choice','generic_choice_uid',
            'native_best','native_best_uid','selected_native_uid','best_native_fps',
            'selected_native_fps','loss_pct','x','y']
    for point in reference['points']:
        key=point['model'],point['setup']
        row=groups[key]
        assert int(row['n'])==point['candidate_count']
        assert json.loads(row['selected_uids'])==[point['selected_native_uid']]
        assert row['retained_case']==point['generic_choice']
        assert point['native_best'] in winners[key]['native_best_case'].split(';')
        assert bool(float(row['winner_coverage']))==point['exact_hit']
        assert math.isclose(float(row['native_best_fps']),point['best_native_fps'],rel_tol=1e-13)
        assert math.isclose(float(row['retained_native_fps_or_expectation']),point['selected_native_fps'],rel_tol=1e-13)
        error=abs(float(row['throughput_loss_pct'])-point['loss_pct'])
        assert error<1e-10,(key,error)
        errors.append(error)
        points.append({field:point[field] for field in fields})
    return {'points':points,'model_order':reference['model_order'],
            'groups':reference['groups'],'paired_candidates':reference['paired_candidates'],
            'exact_hits':reference['exact_hits'],'mean_loss_pct':reference['mean_loss_pct'],
            'scope':'Current quality-eligible deployment pairs; all seven models and three setups.',
            'reference':'results/split-inference/publications/mlsys-r22/figures/FIGURE_DATA.json#quality_generic_selection_loss',
            'verification':{'exact_frozen_point_values_preserved':True,
                            'current_group_count':len(groups),
                            'maximum_csv_rounding_difference_pp':max(errors)}}


def curve(rows,style,x,y,scale=1):
    method,label,*_=style
    values=sorted((r for r in rows if r['method']==method),key=lambda r:int(r[x]))
    assert values,method
    return {'method':method,'label':label,'k':[int(r[x]) for r in values],
            'values':[float(r[y])*scale for r in values]}


def figure_payload(data_root):
    gl=[r for r in read(data_root,'historical/historical_shortlist_summary.csv') if r['family']=='classification']
    cl=[r for r in read(data_root,'current/fixed_group_budget_curves.csv')
        if r['view']=='quality_5pct' and r['task']=='classification' and r['status']=='evaluated']
    gs=[r for r in read(data_root,'success/graph_rules/success_summary.csv') if r['family']=='classification']
    cs=[r for r in read(data_root,'success/current/fixed_group_success_curves.csv')
        if r['view']=='quality_5pct' and r['task']=='classification' and r['status']=='evaluated']
    rho=read(data_root,'historical/historical_rank_correlations.csv')
    models=['mobilenet_v3_large','regnet_x_1_6gf','resnet50']
    setups=['DeepX','H10','H8']
    mat=[[float(next(r['spearman_native'] for r in rho
              if r['model']==m and r['setup']==s and r['method']==method))
          for method,*_ in METHODS[:-1]] for m in models for s in setups]
    return {
        'rq2_shortlist_curves':[curve(cl,s,'max_native_trials','mean_loss_pct') for s in CURRENT],
        'rq2_generic_selection_loss':scatter_payload(data_root),
        'rq2_graph_analysis':{
            'rank_correlations':mat,'models':models,'setups':setups,
            'methods':[s[0] for s in METHODS[:-1]],
            'mean_loss':[curve(gl,s,'requested_k','mean_native_loss_pct') for s in METHODS],
            'success':[[curve([r for r in gs if r['criterion']==criterion],s,'requested_k','coverage',9)
                        for s in METHODS] for criterion in ['exact_optimum','within_5pct']]},
        'rq2_native_success':[[curve([r for r in cs if float(r['loss_tolerance_pct'])==tolerance],
                                    s,'max_native_trials','mean_success_fraction',9)
                              for s in CURRENT] for tolerance in [0,5]],
    }


def run(data_root, output_dir, numeric_only=False, *, excluded_graph_methods=()):
    """Render archived coordinates, optionally hiding graph-series presentation.

    Exclusions affect only the graph-analysis curves and their legend. All
    numerical payloads and historical default rendering remain unchanged.
    """
    excluded_graph_methods = frozenset(excluded_graph_methods)
    unknown = excluded_graph_methods - {method[0] for method in METHODS}
    if unknown:
        raise ValueError('Unknown excluded graph methods: ' + ', '.join(sorted(unknown)))
    data_root,output_dir=Path(data_root),Path(output_dir)
    write_table(data_root,output_dir)
    payload=figure_payload(data_root)
    figures=output_dir/'figures'
    figures.mkdir(parents=True,exist_ok=True)
    (figures/'RQ2_FIGURE_DATA.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    if numeric_only:return
    os.environ.setdefault('MPLCONFIGDIR',str(output_dir.parent/'.rq2-mpl-cache'))
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
    style=load_style()
    style.apply(plt)

    def line(ax,data,definition,phase=0):
        _,label,color,ls,marker=definition
        ax.plot(data['k'],data['values'],label=label,color=color,ls=ls,
                lw=1.6 if label=='Bytes' else 1.2,marker=marker,ms=3,
                markevery=(phase%3,3),zorder=3)

    def axis(ax,success=False):
        ax.set_xlim(.7,20.3)
        ax.set_xticks([1,5,10,15,20])
        style.grid(ax)
        ax.set_xlabel('Maximum Native trials per group')
        if success:
            ax.set_ylim(-.1,9.25)
            ax.set_yticks([0,3,6,9])
            ax.set_ylabel('Successful groups (out of 9)')
        else:
            ax.set_ylim(bottom=-.6)
            ax.set_ylabel('Mean Native throughput loss (%)')

    def save(fig,name):
        fig.savefig(figures/(name+'.pdf'),metadata={'Creator':'RQ2 offline renderer',
                    'Producer':'Matplotlib','CreationDate':None,'ModDate':None})
        fig.savefig(figures/(name+'.svg'),metadata={'Creator':'RQ2 offline renderer','Date':None})
        fig.savefig(figures/(name+'.png'),dpi=240,metadata={'Software':'Matplotlib'})
        plt.close(fig)

    fig,ax=plt.subplots(figsize=(3.3,2.3))
    for i,(data,definition) in enumerate(zip(payload['rq2_shortlist_curves'],CURRENT)):
        line(ax,data,definition,i)
    axis(ax)
    ax.legend(frameon=False,ncol=2,loc='upper right',columnspacing=.8,handlelength=2)
    fig.tight_layout(pad=.35)
    save(fig,'rq2_shortlist_curves')

    data=payload['rq2_generic_selection_loss']
    fig,ax=plt.subplots(figsize=(3.3,2.3))
    for setup in style.SETUPS:
        points=[p for p in data['points'] if p['setup']==setup]
        ax.scatter([p['x'] for p in points],[p['y'] for p in points],label=setup,
                   marker=style.MARKERS[setup],s=18,zorder=3,color=style.COLORS[setup])
    models=data['model_order']
    ax.set_yticks(list(range(len(models)-1,-1,-1)),[style.MODEL_LABELS[m] for m in models])
    maximum=max([70]+[p['x'] for p in data['points']])
    ax.set(xlim=(-2.5,maximum+3),ylim=(-.55,len(models)-.45),xlabel='Native throughput lost (%)')
    ax.xaxis.set_major_locator(MaxNLocator(4,steps=[1,2,5,10]))
    ax.legend(loc='lower left',bbox_to_anchor=(-.02,1.01),ncol=3,frameon=False,
              columnspacing=.8,handletextpad=.35,borderaxespad=0)
    style.grid(ax,axis='x')
    fig.tight_layout(pad=.3)
    save(fig,'rq2_generic_selection_loss')

    data=payload['rq2_graph_analysis']
    fig,axes=plt.subplots(2,2,figsize=(7,6.15))
    mat=np.array(data['rank_correlations'])
    ax=axes[0,0]
    im=ax.imshow(mat,vmin=-1,vmax=1,cmap='BrBG',aspect='auto')
    ax.set_xticks(range(6),[s[1] for s in METHODS[:-1]],rotation=30,ha='right')
    ax.set_yticks(range(9),[m+' / '+s for m in ['MobileNet','RegNet','ResNet'] for s in data['setups']])
    for i in range(9):
        for j in range(6):
            ax.text(j,i,f'{mat[i,j]:+.2f}',ha='center',va='center',fontsize=7,
                    color='white' if abs(mat[i,j])>.55 else '#15232f')
    ax.set_title('(a) Full-ranking agreement',loc='left')
    fig.colorbar(im,ax=ax,pad=.015,fraction=.04,ticks=[-1,0,1],label='Spearman ρ')
    for i,(values,definition) in enumerate(zip(data['mean_loss'],METHODS)):
        if definition[0] in excluded_graph_methods:
            continue
        line(axes[0,1],values,definition,i)
    axis(axes[0,1])
    axes[0,1].set_title('(b) Best retained Native throughput',loc='left')
    for ax,curves,title in [(axes[1,0],data['success'][0],'(c) Exact Native optimum'),
                            (axes[1,1],data['success'][1],'(d) Within 5% of Native optimum')]:
        for i,(values,definition) in enumerate(zip(curves,METHODS)):
            if definition[0] in excluded_graph_methods:
                continue
            line(ax,values,definition,i)
        axis(ax,True)
        ax.set_title(title,loc='left')
    handles=[Line2D([0],[0],color=c,ls=ls,lw=1.5,marker=mk,ms=3,label=label)
             for method,label,c,ls,mk in METHODS if method not in excluded_graph_methods]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.55,1),ncol=4,
               frameon=False,handlelength=2)
    fig.tight_layout(rect=[0,0,1,.92],pad=.6,w_pad=1.7,h_pad=2)
    save(fig,'rq2_graph_analysis')

    fig,axes=plt.subplots(1,2,figsize=(6.8,2.65))
    for ax,curves,title in [(axes[0],payload['rq2_native_success'][0],'(a) Exact Native optimum'),
                            (axes[1],payload['rq2_native_success'][1],'(b) Within 5% of Native optimum')]:
        for i,(values,definition) in enumerate(zip(curves,CURRENT)):
            line(ax,values,definition,i)
        axis(ax,True)
        ax.set_title(title,pad=7)
    handles=[Line2D([0],[0],color=c,ls=ls,lw=1.5,marker=mk,ms=3,label=label)
             for _,label,c,ls,mk in CURRENT]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.53,1),ncol=4,frameon=False)
    fig.tight_layout(rect=[0,0,1,.87],pad=.65,w_pad=1.2)
    save(fig,'rq2_native_success')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--numeric-only',action='store_true')
    args=parser.parse_args()
    run(args.data_root,args.output_dir,args.numeric_only)

