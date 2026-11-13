#!/usr/bin/env python3
"""Reader-facing layouts of existing ranking summaries; no new measurements.

One axes per chart, default Matplotlib colour cycle, distinct marker shapes.
Input correlations and within-stratum candidate counts are copied unchanged.
"""
from pathlib import Path
import csv
import json
import math

STRATA = [(m, d) for m in ('resnet50','yolov7') for d in
          ('deepx_m1_to_tensorrt','hailo10h_to_tensorrt','hailo8_to_tensorrt')]
METHODS = [
 ('cut_bytes_only','Boundary bytes','o'),
 ('weighted_score','Weighted score','s'),
 ('cycle_time_no_handover','Cycle time: compute only','^'),
 ('cycle_time_with_handover','Cycle time: with handover','D'),
 ('onnx_real_boundary_hardware_aware','Hardware-aware boundary','x'),
]
FEATURES = [
 ('cut_mib','Boundary bytes','o'),
 ('imbalance','50/50 compute imbalance','s'),
 ('flops_right','Static Stage-2 compute','^'),
]
MODEL = {'resnet50':'ResNet50','yolov7':'YOLOv7'}
DIRECTION = {'deepx_m1_to_tensorrt':'DEEPX','hailo10h_to_tensorrt':'Hailo-10H','hailo8_to_tensorrt':'Hailo-8'}


def read(source, name):
    with (source/name).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))


def model_key(row):
    # Source spelling includes the registered name of the YOLOv7 paper model.
    m=row['model_id']
    if m in ('yolov7_paper','yolov7-paper','yolov7_paper_fp32'):
        m='yolov7'
    return m,row['direction']


def chart(rows, components, identity, value, count, name, figures):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    indexed={(model_key(r),r[identity]):r for r in rows}
    expected={(s,c[0]) for s in STRATA for c in components}
    if set(indexed)!=expected or len(indexed)!=len(rows):
        raise ValueError('Unexpected cohort or duplicate row: '+name+str(set(indexed)-expected))
    counts={s:{int(indexed[s,c[0]][count]) for c in components} for s in STRATA}
    if any(len(n)!=1 for n in counts.values()):
        raise ValueError('Methods have different within-stratum counts')
    if any(next(iter(n)) < 10 for n in counts.values()):
        raise ValueError('Candidate count below the eligible-stratum minimum')
    fig,ax=plt.subplots(figsize=(7.0,4.4))
    offsets=[(i-(len(components)-1)/2)*.13 for i in range(len(components))]
    for (key,label,marker),offset in zip(components,offsets):
        values=[float(indexed[s,key][value]) for s in STRATA]
        if not all(math.isfinite(x) and -1<=x<=1 for x in values):
            raise ValueError('Invalid correlation')
        ax.plot(values,[i+offset for i in range(len(STRATA))],linestyle='None',
                marker=marker,markersize=6.0,label=label)
    ax.set_yticks(range(len(STRATA)),[
        f'{MODEL[s[0]]} / {DIRECTION[s[1]]} (n={next(iter(counts[s]))})' for s in STRATA])
    ax.set_ylim(len(STRATA)-.5,-.5)
    ax.set_xlim(-1.03,1.05)
    ax.set_xticks([-1,-.5,0,.5,1])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:g}'))
    ax.set_xlabel("Spearman correlation with Generic runtime",fontsize=11)
    ax.axvline(0,linewidth=.6,linestyle='--')
    ax.grid(axis='x',linewidth=.4,alpha=.35)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.015),ncol=2,frameon=False,
              fontsize=10,columnspacing=1.1,handletextpad=.45,borderaxespad=0)
    ax.tick_params(labelsize=10.5)
    fig.tight_layout(pad=.6)
    figures.mkdir(parents=True,exist_ok=True)
    fig.savefig(figures/(name+'.pdf'),bbox_inches='tight',pad_inches=.025,
                metadata={'CreationDate':None,'ModDate':None})
    fig.savefig(figures/(name+'.png'),dpi=180,bbox_inches='tight',pad_inches=.025)
    fig.savefig(figures/(name+'.svg'),bbox_inches='tight',pad_inches=.025,
                metadata={'Date':None})
    plt.close(fig)
    return {'rows':len(rows),'strata':len(STRATA),'counts':[next(iter(counts[s])) for s in STRATA]}


def render(source, output):
    methods=read(source, 'phase2_ranking_diagnostic_spearman_six_eligible_strata.csv')
    if not all(r['development_diagnostic_leader_group_eligible'].lower()=='true' for r in methods):
        raise ValueError('Unqualified source stratum')
    if not all(r['runner_regime']=='generic' for r in methods):
        raise ValueError('Expected the Generic development cohort')
    proxies=read(source, 'static_proxy_spearman_confirmatory.csv')
    report={
      'ranking_methods':chart(methods,METHODS,'method_id','diagnostic_spearman_rho',
                              'diagnostic_paired_candidate_count','ranking_methods',output/'figures'),
      'ranking_proxies':chart(proxies,FEATURES,'feature','spearman_rho',
                              'paired_candidate_count','ranking_proxies',output/'figures'),
      'scope':'Rendering supplied aggregate correlations; no re-estimation or candidate-level reconstruction.'
    }
    if report['ranking_methods']['counts'] != report['ranking_proxies']['counts']:
        raise ValueError('Method and proxy candidate counts differ')
    (output/'ranking_layout_check.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
