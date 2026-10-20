#!/usr/bin/env python3
"""English RQ2 paper assets from the full-budget analysis CSVs.

No hardware measurements or fitting. See the enclosing reproduction entry point.
"""
from pathlib import Path
import argparse
import csv
import json
import os

METHODS = [
    ('cut_bytes_only', 'Bytes', '#007f73', '-', 'o'),
    ('weighted_score', 'Weighted', '#d68b0f', '-', 's'),
    ('onnx_real_boundary_hardware_aware', 'Fit-H10', '#ae4779', '--', '^'),
    ('cycle_time_no_handover', 'Cycle', '#7553aa', ':', 'v'),
    ('stored_predicted_stream_fps', 'Stream', '#cd563b', '-.', 'D'),
    ('measured_generic_completion', 'Generic', '#3555a2', '-', 'P'),
    ('uniform_random', 'Random', '#676c72', '--', None),
]
CURRENT = [
    ('boundary_bytes', 'Bytes', '#007f73', '-', 'o'),
    ('generic', 'Generic', '#3555a2', '-', 'P'),
    ('calibrated_generic', 'Calibrated', '#b55e32', '-.', 's'),
    ('uniform_random', 'Random', '#676c72', '--', None),
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

def run(data_root, output_dir, numeric_only=False):
    data_root,output_dir=Path(data_root),Path(output_dir)
    write_table(data_root,output_dir)
    if numeric_only:return
    os.environ.setdefault('MPLCONFIGDIR',str(output_dir.parent/'.rq2-mpl-cache'))
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':8,
        'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,
        'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none',
        'svg.hashsalt':'rq2-all-cuts-20261020','pdf.compression':9})
    figures=output_dir/'figures';figures.mkdir(parents=True,exist_ok=True)
    gl=[r for r in read(data_root,'historical/historical_shortlist_summary.csv') if r['family']=='classification']
    cl=[r for r in read(data_root,'current/fixed_group_budget_curves.csv')
        if r['view']=='quality_5pct' and r['task']=='classification' and r['status']=='evaluated']
    gs=[r for r in read(data_root,'success/graph_rules/success_summary.csv') if r['family']=='classification']
    cs=[r for r in read(data_root,'success/current/fixed_group_success_curves.csv')
        if r['view']=='quality_5pct' and r['task']=='classification' and r['status']=='evaluated']
    rho=read(data_root,'historical/historical_rank_correlations.csv')
    payload={}
    def line(ax,rows,style,x,y,scale=1,phase=0):
        method,label,color,ls,marker=style
        values=sorted((r for r in rows if r['method']==method),key=lambda r:int(r[x]))
        assert values,method
        xs=[int(r[x]) for r in values];ys=[float(r[y])*scale for r in values]
        ax.plot(xs,ys,label=label,color=color,ls=ls,lw=1.6 if label=='Bytes' else 1.2,
                marker=marker,ms=3,markevery=(phase%3,3),alpha=.98)
        return {'method':method,'label':label,'k':xs,'values':ys}
    def axis(ax,success=False):
        ax.set_xlim(.7,20.3);ax.set_xticks([1,5,10,15,20])
        ax.grid(axis='y',alpha=.2)
        ax.set_xlabel('Maximum Native trials per group')
        if success:
            ax.set_ylim(-.1,9.25);ax.set_yticks([0,3,6,9])
            ax.set_ylabel('Successful groups (out of 9)')
        else:
            ax.set_ylim(bottom=-.6);ax.set_ylabel('Mean Native throughput loss (%)')
    def save(fig,name):
        fig.savefig(figures/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None})
        fig.savefig(figures/(name+'.svg'),metadata={'Date':None})
        fig.savefig(figures/(name+'.png'),dpi=200)
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(6.8,2.20))
    records=[]
    for ax,rows,styles,x,title in [(axes[0],gl,METHODS,'requested_k','(a) Graph-score comparison · 168 cuts'),
             (axes[1],cl,CURRENT,'max_native_trials','(b) Deployment comparison · 151 eligible cuts')]:
        pp=[]
        for i,s in enumerate(styles):pp.append(line(ax,rows,s,x,'mean_native_loss_pct' if ax is axes[0] else 'mean_loss_pct',phase=i))
        axis(ax);ax.set_title(title,pad=7)
        ax.legend(frameon=False,fontsize=6.1,ncol=2,loc='upper right',columnspacing=.8,handlelength=2)
        records.append(pp)
    fig.tight_layout(pad=.65,w_pad=1.2)
    save(fig,'rq2_shortlist_curves');payload['rq2_shortlist_curves']=records

    fig,axes=plt.subplots(2,2,figsize=(7,6.15))
    models=['mobilenet_v3_large','regnet_x_1_6gf','resnet50'];setups=['DeepX','H10','H8']
    mat=np.array([[float(next(r['spearman_native'] for r in rho if r['model']==m and r['setup']==s and r['method']==method))
                  for method,*_ in METHODS[:-1]] for m in models for s in setups])
    ax=axes[0,0];im=ax.imshow(mat,vmin=-1,vmax=1,cmap='BrBG',aspect='auto')
    ax.set_xticks(range(6),[s[1] for s in METHODS[:-1]],rotation=30,ha='right',fontsize=6.5)
    ax.set_yticks(range(9),[m+' / '+s for m in ['MobileNet','RegNet','ResNet'] for s in setups],fontsize=6.5)
    for i in range(9):
        for j in range(6):ax.text(j,i,f'{mat[i,j]:+.2f}',ha='center',va='center',fontsize=5.8,color='white' if abs(mat[i,j])>.55 else '#15232f')
    ax.set_title('(a) Full-ranking agreement',loc='left')
    fig.colorbar(im,ax=ax,pad=.015,fraction=.04,ticks=[-1,0,1],label='Spearman ρ')
    pp=[]
    for i,s in enumerate(METHODS):pp.append(line(axes[0,1],gl,s,'requested_k','mean_native_loss_pct',phase=i))
    axis(axes[0,1]);axes[0,1].set_title('(b) Best retained Native throughput',loc='left')
    success=[]
    for ax,criterion,title in [(axes[1,0],'exact_optimum','(c) Exact Native optimum'),(axes[1,1],'within_5pct','(d) Within 5% of Native optimum')]:
        ss=[]
        for i,s in enumerate(METHODS):ss.append(line(ax,[r for r in gs if r['criterion']==criterion],s,'requested_k','coverage',9,i))
        axis(ax,True);ax.set_title(title,loc='left');success.append(ss)
    handles=[Line2D([0],[0],color=c,ls=ls,lw=1.5,marker=mk,ms=3,label=label) for _,label,c,ls,mk in METHODS]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.55,1),ncol=4,frameon=False,fontsize=7,handlelength=2)
    fig.tight_layout(rect=[0,0,1,.92],pad=.6,w_pad=1.7,h_pad=2)
    save(fig,'rq2_graph_analysis')
    payload['rq2_graph_analysis']={'rank_correlations':mat.tolist(),'models':models,'setups':setups,'methods':[s[0] for s in METHODS[:-1]],'mean_loss':pp,'success':success}

    fig,axes=plt.subplots(1,2,figsize=(6.8,2.65));ss=[]
    for ax,tolerance,title in [(axes[0],0,'(a) Exact Native optimum'),(axes[1],5,'(b) Within 5% of Native optimum')]:
        part=[]
        for i,s in enumerate(CURRENT):part.append(line(ax,[r for r in cs if float(r['loss_tolerance_pct'])==tolerance],s,'max_native_trials','mean_success_fraction',9,i))
        axis(ax,True);ax.set_title(title,pad=7);ss.append(part)
    handles=[Line2D([0],[0],color=c,ls=ls,lw=1.5,marker=mk,ms=3,label=label) for _,label,c,ls,mk in CURRENT]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.53,1),ncol=4,frameon=False,fontsize=7)
    fig.tight_layout(rect=[0,0,1,.87],pad=.65,w_pad=1.2)
    save(fig,'rq2_native_success');payload['rq2_native_success']=ss
    (figures/'RQ2_FIGURE_DATA.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--numeric-only',action='store_true')
    args=parser.parse_args()
    run(args.data_root,args.output_dir,args.numeric_only)
