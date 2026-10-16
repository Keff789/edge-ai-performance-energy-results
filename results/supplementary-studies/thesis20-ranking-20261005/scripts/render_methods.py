#!/usr/bin/env python3
"""Two deterministic methods-comparison figures, with exact compact source CSVs."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from evaluate_methods import read_csv,write_csv
MODELS=['mobilenet_v3_large','regnet_x_1_6gf','resnet50','yolo11l','yolo26m','yolo26s','yolov7_paper']
LABEL=dict(zip(MODELS,['MobileNetV3-L','RegNetX-1.6GF','ResNet-50','YOLO11l','YOLO26m','YOLO26s','YOLOv7']))
SETUPS=['H8','H10','DeepX'];COLORS={'H8':'#1f77b4','H10':'#d97900','DeepX':'#2c8c51'};MARKERS={'H8':'o','H10':'s','DeepX':'^'}
METHODS=['cut_bytes_only','weighted_score','onnx_real_boundary_hardware_aware','cycle_time_no_handover','stored_predicted_stream_fps','measured_generic_completion']
LABELS={'cut_bytes_only':'Cut payload','weighted_score':'Weighted score','onnx_real_boundary_hardware_aware':'HW fit (H10 profile)','cycle_time_no_handover':'Cycle, no handover','stored_predicted_stream_fps':'Stored stream FPS','measured_generic_completion':'Measured completion','native_oracle':'Native rate oracle','random':'Uniform random'}

def render(source_root,method_root,output_root,deep_root=None):
    deep_root=Path(deep_root) if deep_root is not None else source_root/'deep_analysis'
    table_root=method_root/'tables';F=output_root/'figures';P=output_root/'previews';T=output_root/'tables'
    for d in [F,P,T]:d.mkdir(exist_ok=True,parents=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,'legend.fontsize':7,'xtick.labelsize':7,'ytick.labelsize':7,'axes.grid':True,'grid.alpha':.2,'grid.linewidth':.5,'axes.axisbelow':True,'savefig.bbox':'tight','pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','svg.hashsalt':'thesis20-ranking-methods-20261005'})
    groups=read_csv(table_root/'method_groups.csv');main=[r for r in groups if r['cohort']=='augmented' and r['tier']=='technical']
    method_ids=[m for m in METHODS if any(r['method']==m and r['status'] in ['ok','constant_scores'] for r in main)]
    order=[(m,s) for m in MODELS for s in SETUPS]
    index={(r['model_id'],r['setup_id'],r['method']):r for r in main};registry=[]
    def save(fig,name,rows,caption):
        write_csv(T/(name+'_source.csv'),rows)
        fig.savefig(F/(name+'.pdf'),metadata={'Creator':'THESIS20 offline methods comparison','CreationDate':None,'ModDate':None});fig.savefig(F/(name+'.svg'),metadata={'Date':None});fig.savefig(P/(name+'.png'),dpi=160);plt.close(fig)
        registry.append(dict(figure=name,pdf='figures/'+name+'.pdf',svg='figures/'+name+'.svg',source_csv='tables/'+name+'_source.csv',caption=caption))
    matrix=np.full((len(order),len(method_ids)),np.nan);sources=[]
    for i,(m,s) in enumerate(order):
        for j,method in enumerate(method_ids):
            r=index[(m,s,method)]
            if r.get('L_R') is not None:matrix[i,j]=100*r['L_R']
            sources.append(dict(r,plot_row=i,plot_column=j,plot_L_R_percent=100*r['L_R'] if r.get('L_R') is not None else None))
    fig,ax=plt.subplots(figsize=(7.2,6.1),layout='constrained');cmap=plt.get_cmap('YlOrRd').copy();cmap.set_bad('#dddddd');im=ax.imshow(matrix,cmap=cmap,vmin=0,vmax=100,aspect='auto');ax.grid(False)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v=matrix[i,j];ax.text(j,i,'NA' if np.isnan(v) else f'{v:.1f}',ha='center',va='center',fontsize=7,color='white' if v>57 else 'black')
    headers=[]
    for method in method_ids:
        rr=[r for r in main if r['method']==method and r['status'] in ['ok','constant_scores']];hits=sum(r['top1_hit_tie_aware'] for r in rr)
        headers.append(LABELS[method]+'\n'+f'Top1 {hits}/{len(rr)}')
    ax.set_xticks(range(len(method_ids)),headers,rotation=30,ha='left');ax.xaxis.tick_top()
    ax.set_yticks(range(len(order)),[LABEL[m]+' / '+s+'  n='+str(index[(m,s,method_ids[0])]['n']) for m,s in order])
    for tick,(_,s) in zip(ax.get_yticklabels(),order):tick.set_color(COLORS[s])
    for pos in [2.5,5.5,8.5,11.5,14.5,17.5]:ax.axhline(pos,color='white',lw=1.5)
    cb=fig.colorbar(im,ax=ax,pad=.025,fraction=.035);cb.set_label('Native throughput loss L_R (%)')
    save(fig,'fig01_ranking_methods_loss',sources,'Throughput lost by the Top1 candidate of each existing ranking method, relative to the best measured Native candidate in the same exact model/setup/direction/precision/endpoint group: L_R=1−R_selected/R_best. All 204 augmented technical candidates in 21 groups are retained, including accuracy losses; each column uses the identical candidates in each row. Native and measured Generic completion use medians of three 1000-task repeats. Static methods use frozen graph scores and original score/boundary/case tie order; the archived hardware-fit profile is H10-based even for H8/DeepX. The 12 additions are post-planned. Values are percentages, not request latency. Header Top1 counts use the original stable selection and Native-best tie-aware hit. Handover and GUI-total-latency models lack a historical configured binding and remain unavailable in the tables; historical raw Generic is evaluated separately on the original 192-case intersection, of which 177 cases in 12 groups meet n≥3; the other nine groups remain visible below threshold. No uncertainty bars are drawn; repeat and tie sensitivities are tabulated. No global graph optimum or held-out selector claim is implied.')
    # Different scientific question: energy cost of performance-based selection.
    fig,axs=plt.subplots(1,2,figsize=(7.2,3.6),gridspec_kw={'width_ratios':[1.3,1]},layout='constrained');sources=[]
    methods=method_ids+['native_oracle','random'];primary_ref=[index[(m,s,'measured_generic_completion')] for m,s in order]
    maxpct=0
    for j,method in enumerate(methods):
        rr=primary_ref if method in ['native_oracle','random'] else [index[(m,s,method)] for m,s in order]
        vals=[]
        for i,r in enumerate(rr):
            field='native_oracle_energy_excess_fraction' if method=='native_oracle' else 'random_expected_energy_excess' if method=='random' else 'energy_excess_fraction';v=100*r[field];vals.append(v);maxpct=max(maxpct,v)
            # Deterministic jitter is a point-placement aid, not uncertainty.
            y=j+((i%7)-3)*.035;axs[0].scatter(v,y,marker=MARKERS[r['setup_id']],s=13,color=COLORS[r['setup_id']],alpha=.8)
            sources.append(dict(plot_panel='all_groups',method=method,model_id=r['model_id'],setup_id=r['setup_id'],n=r['n'],energy_excess_percent=v,value_role='analytical_expectation' if method=='random' else 'selected_existing_case',selected_case=r.get('selected_case') if method not in ['native_oracle','random'] else r.get('native_best_case') if method=='native_oracle' else None))
        med=float(np.median(vals));axs[0].plot([med,med],[j-.24,j+.24],color='black',lw=1.2)
    axs[0].set_yticks(range(len(methods)),[LABELS[m] for m in methods]);axs[0].invert_yaxis();axs[0].set_xlim(-1,maxpct*1.07);axs[0].set_xlabel('Energy excess over group minimum (%)');axs[0].set_title('(a) Performance selectors, 21 groups each');axs[0].axvline(0,color='gray',lw=.7)
    e=[r for r in read_csv(deep_root/'tables/energy_cases.csv') if r['model_id']=='resnet50' and r['setup_id']=='H8' and r['execution_mode']=='native_split']
    chosen=defaultdict_list()
    for method in method_ids:
        r=index[('resnet50','H8',method)];chosen[r['selected_case']].append(LABELS[method])
    chosen['b060'].append('Energy minimum');chosen[index[('resnet50','H8','measured_generic_completion')]['native_best_case']].append('Native rate oracle')
    for r in e:
        x,y=r['energy_fps_mean'],r['j_per_task_mean'];axs[1].scatter(x,y,s=22 if r['case_id'] in chosen else 10,color=COLORS['H8'],edgecolors='black' if r['case_id'] in chosen else COLORS['H8'],linewidths=.6)
        if r['case_id'] in chosen:
            # Case IDs keep the narrow panel readable; full method assignment is in the source CSV.
            offset=(4,-13) if r['case_id']=='b119' else (-4,8);annotation=r['case_id']+' (min J)' if r['case_id']=='b060' else r['case_id'];axs[1].annotate(annotation,(x,y),xytext=offset,textcoords='offset points',ha='left' if r['case_id']=='b119' else 'right',fontsize=7)
        sources.append(dict(plot_panel='resnet_h8',model_id=r['model_id'],setup_id=r['setup_id'],case_id=r['case_id'],energy_fps=x,j_per_task=y,accuracy_class=r['accuracy_class'],selected_by=chosen.get(r['case_id'],[])))
    axs[1].set_xlabel('Tasks/s in own energy window');axs[1].set_ylabel('Full-system J/task');axs[1].set_title('(b) ResNet-50 / H8, all 19 candidates')
    fig.legend(handles=[Line2D([],[],marker=MARKERS[s],ls='',color=COLORS[s],label=s) for s in SETUPS],loc='lower center',bbox_to_anchor=(.56,-.08),ncol=3,frameon=False)
    save(fig,'fig02_selector_energy_cost',sources,'Energy cost of throughput-oriented split selection. (a) Each point is one of 21 exact groups; all methods use the same 204 technical candidates. Energy excess is J_selected/min_i(J_i)−1, with J_i the mean of the three existing per-replicate E/N values; black ticks are medians over groups. Native rate oracle selects the measured performance-throughput best; uniform random is an analytical expectation over candidate identities, not a new run. There is no Generic energy measurement. (b) All 19 ResNet-50/H8 candidates in their own energy windows; outlined points are selected by at least one method or an oracle, with exact method-to-case assignments in the figure source CSV. Energy minimum b060 uses 0.042286 J/task at 615.65 task/s; energy-window-rate maximum b031 uses 0.047715 J/task at 626.89 task/s. This is a measured within-group selection tradeoff, not an isolated effect of graph position. Primary energy is calibrated full-system without idle subtraction; no Full references are duplicated. No CIs are drawn; three-repeat and nine energy-repetition comparison sensitivities remain in the tables. When selected and optimal identities coincide, primary selection loss is zero; nonzero cross-repeat ratios of that same case reflect variation only. Accuracy losses remain in panel (a); the stricter reference-close cohort is provided separately.')
    (output_root/'method_figure_index.json').write_text(json.dumps(registry,indent=2)+'\n')
    (output_root/'METHOD_FIGURE_CAPTIONS.md').write_text('# English captions\n\n'+'\n\n'.join('## '+r['figure']+'\n\n'+r['caption'] for r in registry)+'\n')
    print(json.dumps({'main_figures':len(registry)}));return registry

def defaultdict_list():
    from collections import defaultdict
    return defaultdict(list)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',required=True,type=Path);p.add_argument('--method-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--deep-root',type=Path);a=p.parse_args();render(a.source_root,a.method_root,a.output_root,a.deep_root)
