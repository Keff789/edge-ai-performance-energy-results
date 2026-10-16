"""Joris layouts (monochrome) plus compact coloured summaries.

Each panel is drawn as its own single-Axes figure and overlaid at the approved
PDF coordinates. No rescaling/cropping of small panels, no new data integration.
"""
from __future__ import annotations
import ast, csv, io, json, math, os, tempfile
from pathlib import Path
from enum import Enum
from typing import Dict
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.cbook import boxplot_stats
from matplotlib.colors import TwoSlopeNorm, Normalize
from matplotlib.patches import Rectangle
from pdf_backend import load_pdf
pdf = load_pdf()
from model import SENSORS,LABELS,VIEW_LABELS,statistics,flags,finite,paper_view

HERE=Path(__file__).resolve().parent
DURATION_LAYOUT=json.loads((HERE/'metadata/duration_layout.json').read_text())
RATE_LAYOUT=json.loads((HERE/'metadata/samplerate_layout.json').read_text())
COLORS={'gemm_fp32':'#1f77b4','gemm_int8':'#ff7f0e','yolo_fp32':'#2ca02c','yolo_int8':'#d62728','llm':'#9467bd',
        'gemm_fp16':'#8c564b','yolo_fp16':'#e377c2','random_pattern_yolo':'#7f7f7f','random_pattern_yolo_adjusted':'#bcbd22',
        'gemm':'#1f77b4','yolo':'#2ca02c'}
SENSOR_COLORS={'pico':'#1f77b4','firmware':'#ff7f0e','jetson':'#2ca02c','shelly':'#d62728','hailo_rt':'#9467bd'}

# Reuse the original function bodies, NOT their CLI/loaders or outlier cutter.
def load_joris_functions():
    result={}
    for name,keep in [('joris_original_plot_sweep_vendor.py',{'plot_as_boxplot'}),
                       ('joris_original_plot_duration_sweep_vendor.py',{'MsmtType','convert_run_data'})]:
        source=(HERE/'vendor'/name).read_text()
        source=source.replace('type Duration = float','Duration = float').replace('type Energy = float','Energy = float')
        tree=ast.parse(source)
        body=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in keep]
        ns={'np':np,'Axes':Axes,'Enum':Enum,'Path':Path,'Dict':Dict,'Duration':float,'Energy':float}
        exec(compile(ast.Module(body=body,type_ignores=[]),name,'exec'),ns)
        result.update({k:ns[k] for k in keep})
    return result
JORIS=load_joris_functions()

def mono():
    plt.rcdefaults()
    plt.rcParams.update({'pdf.fonttype':42,'ps.fonttype':42,'boxplot.medianprops.color':'black',
                         'boxplot.flierprops.markeredgecolor':'black','boxplot.flierprops.markerfacecolor':'none',
                         'axes.prop_cycle':matplotlib.cycler(color=['black'])})

def colour():
    plt.rcdefaults()
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':14,'axes.labelsize':12,
                         'legend.fontsize':10,'xtick.labelsize':10,'ytick.labelsize':10,'axes.axisbelow':True,
                         'grid.alpha':.25,'grid.linewidth':.8,'lines.linewidth':1.7,'pdf.fonttype':42,'ps.fonttype':42})

def overlay(spec,draw,target,dpi=130):
    """Preserve original PDF page size and panel coordinates exactly."""
    target=Path(target).with_suffix('.pdf');target.parent.mkdir(parents=True,exist_ok=True)
    width,height=spec['canvas_pt'];doc=pdf.open();page=doc.new_page(width=width,height=height)
    for i,position in enumerate(spec['axes_normalized']):
        with plt.rc_context(matplotlib.rcParamsDefault):
            mono();fig=plt.figure(figsize=(width/72,height/72));fig.patch.set_alpha(0)
            ax=fig.add_axes(position)
            draw(i,fig,ax)
            buffer=io.BytesIO()
            fig.savefig(buffer,format='pdf',transparent=True,metadata={'CreationDate':None,'ModDate':None})
            plt.close(fig)
        with pdf.open(stream=buffer.getvalue(),filetype='pdf') as panel:
            page.show_pdf_page(page.rect,panel,0)
    doc.subset_fonts()
    pt=target.with_name(target.name+'.part');png=target.with_suffix('.png');nt=png.with_name(png.name+'.part')
    doc.save(pt,deflate=True,garbage=4)
    pix=page.get_pixmap(matrix=pdf.Matrix(dpi/72,dpi/72),alpha=False)
    nt.write_bytes(pix.tobytes('png'));doc.close()
    os.replace(pt,target);os.replace(nt,png)
    return [target,png]

def save(fig,path,dpi=160):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    paths=[]
    for ext in ('pdf','png'):
        dest=path.with_suffix('.'+ext);tmp=dest.with_name(dest.name+'.part')
        kw=dict(format=ext,bbox_inches='tight',pad_inches=.12)
        if ext=='png':kw['dpi']=dpi
        else:kw['metadata']={'CreationDate':None,'ModDate':None}
        fig.savefig(tmp,**kw);os.replace(tmp,dest);paths.append(dest)
    plt.close(fig);return paths

def limits_for_boxes(groups,full=False):
    groups=[np.asarray(g,dtype=float) for g in groups if len(g)]
    if not groups:return (0.,1.)
    st=boxplot_stats(groups,whis=(0,100) if full else 1.5)
    lo=min(x['whislo'] for x in st);hi=max(x['whishi'] for x in st)
    pad=max(abs(hi-lo)*.05,max(abs(lo),abs(hi),1)*.005)
    return float(lo-pad),float(hi+pad)

def duration_plot(data,spec,view,kind,target,dpi=130):
    s=spec['id'];grid=data.grid(s);sen=data.sensors(s)
    if len(grid)!=10:raise ValueError('Approved duration geometry expects ten declared duration settings')
    full=kind=='boxplot_full_range'
    allv=[[r['mean_power_W'] for r in data.get(s,view,se,x)] for x in grid for se in sen]
    if kind.startswith('boxplot'):
        limits=limits_for_boxes(allv,full)
        def draw(i,fig,ax):
            t=grid[i]
            # Original conversion preserves named measurement types, then E/T.
            kinds=JORIS['MsmtType'];keys={'pico':kinds.PICO,'firmware':kinds.URECS,'jetson':kinds.JETSON,'shelly':kinds.SHELLY,'hailo_rt':kinds.HAILO}
            by_id={}
            for se in sen:
                for r in data.get(s,view,se,t):by_id.setdefault(r['record_id'],{})[keys[se]]=(r['span_s'],r['energy_J'])
            ds,es=JORIS['convert_run_data'](list(by_id.values()))
            for j,se in enumerate(sen,1):
                if keys[se] in ds:
                    vals=es[keys[se]]/ds[keys[se]]
                    ax.boxplot([vals],positions=[j],widths=min(.5,max(.15,.15*(len(sen)-1))),showfliers=False,whis=(0,100) if full else 1.5)
                else:ax.text(j,1.03,'n=0',transform=ax.get_xaxis_transform(),ha='center',fontsize=8,clip_on=False)
            ax.set_title(format_duration(t));ax.set_xticks(range(1,len(sen)+1),[LABELS[z] for z in sen]);ax.tick_params('x',rotation=90)
            ax.set_xlim(.5,len(sen)+.5);ax.set_ylim(*limits);ax.yaxis.grid(True)
            if i%5==0:ax.set_ylabel('Energy per Second (J/s)',fontsize=12)
            else:ax.tick_params(labelleft=False)
        return overlay(DURATION_LAYOUT['duration_sweep_boxplot'],draw,target,dpi)
    others=[se for se in sen if se!='pico']
    pair={(x,se):data.pair_group(s,view,se,x) for x in grid for se in others}
    vv=[p['energy_paired_median_pct'] for p in pair.values() if p['energy_paired_median_pct'] is not None]
    low=min([0]+vv);high=max([0]+vv);pad=max((high-low)*.05,.1)
    def draw(i,fig,ax):
        t=grid[i]
        for j,se in enumerate(others,1):
            val=pair[t,se]['energy_paired_median_pct']
            if val is not None:ax.bar([j],[val],fill=False,hatch='//',edgecolor='black')
            else:ax.text(j,1.02,'n=0',transform=ax.get_xaxis_transform(),ha='center',fontsize=8,clip_on=False)
        ax.set_xticks(range(1,len(others)+1),[LABELS[z] for z in others]);ax.tick_params('x',rotation=90);ax.set_title(format_duration(t))
        ax.set_xlim(.5,max(1,len(others))+.5);ax.set_ylim(low-pad,high+pad);ax.yaxis.grid(True)
        if i==0:ax.set_ylabel('Percent (%)',fontsize=12)
        else:ax.tick_params(labelleft=False)
    return overlay(DURATION_LAYOUT['duration_sweep_deviations'],draw,target,dpi)

def rate_plot(data,spec,view,target,dpi=130):
    s=spec['id'];grid=data.grid(s);vals=[[r['energy_J'] for r in data.get(s,view,'pico',x)] for x in grid]
    st=[statistics(v) for v in vals];reference=np.mean([z['mean'] for z in st if z['mean'] is not None]) if any(vals) else None
    positions=np.arange(1,len(grid)+1)
    def draw(i,fig,ax):
        if i==0:
            if vals and all(len(v)==len(vals[0]) and len(v)>0 for v in vals):JORIS['plot_as_boxplot'](np.asarray(vals),ax)
            else:
                for j,v in enumerate(vals,1):
                    if v:ax.boxplot([v],positions=[j],whis=(0,100),showfliers=False)
                    else:ax.text(j,1.01,'n=0',transform=ax.get_xaxis_transform(),fontsize=6,rotation=90,ha='center')
            ax.set_ylabel('Energy (J)');ax.set_title('Measured energy')
        elif i==1:
            std=[z['cv_pct'] if z['cv_pct'] is not None else np.nan for z in st]
            qd=[50*(z['q75']-z['q25'])/abs(z['mean']) if z['mean'] not in (None,0) and len(v)>1 else np.nan for z,v in zip(st,vals)]
            ax.bar(positions,std,fill=False,edgecolor='black',label='Population standard deviation')
            ax.bar(positions,qd,color='black',label='Semi-interquartile range');ax.legend()
            ax.set_ylabel('Percent (%)');ax.set_title('Within-rate variation (%)')
        else:
            rel=[100*(z['mean']/reference-1) if reference and z['mean'] is not None else np.nan for z in st]
            ax.bar(positions,rel,fill=False,edgecolor='black');ax.set_ylabel('Percent (%)')
            ax.set_title('Rate-group mean relative to the mean of all rate-group means')
        ax.set_xticks(positions,[format_rate(x) for x in grid]);ax.tick_params('x',rotation=90)
        ax.set_xlim(.4,len(grid)+.6);ax.xaxis.grid(True);ax.yaxis.grid(True);ax.set_xlabel('Sample rate')
    return overlay(RATE_LAYOUT,draw,target,dpi)

def static_plot(data,spec,view,target,dpi=130):
    layout=json.loads((HERE/'metadata/static_layout.json').read_text())
    s=spec['id'];available=data.sensors(s)
    sen=[k for k in ('pico','firmware','shelly','jetson','hailo_rt') if k in available]
    def draw(i,fig,ax):
        if i==0:
            for j,se in enumerate(sen,1):
                v=[r['mean_power_W'] for r in data.get(s,view,se,None)]
                if v:ax.boxplot([v],positions=[j],whis=(0,100),showfliers=False)
            ax.set_xticks(range(1,len(sen)+1),[LABELS[z] for z in sen])
            ax.set_xlim(.5,len(sen)+.5);ax.set_ylabel('Energy per Second (J/s)');ax.set_title('Power Overview')
        else:
            other=[se for se in sen if se!='pico']
            for j,se in enumerate(other,1):
                g=data.pair_group(s,view,se,None);v=g['power_paired_median_pct']
                if v is not None:ax.bar([j],[v],hatch='////',fill=False,edgecolor='black')
            ax.set_xticks(range(1,len(other)+1),[LABELS[z] for z in other]);ax.set_xlim(.5,max(1,len(other))+.5)
            ax.set_title('Difference to Picoscope Results');ax.set_ylabel('Percent (%)')
        ax.tick_params('x',rotation=90)
    return overlay(layout,draw,target,dpi)


def format_duration(seconds):
    x=float(seconds)
    if abs(x) < 1e-3:
        return f'{x*1e6:g} µs'
    if abs(x) < 1:
        return f'{x*1e3:g} ms'
    return f'{x:g} s'

def format_rate(rate):
    x=float(rate)
    if abs(x) >= 1e6:
        return f'{x/1e6:g} MS/s'
    if abs(x) >= 1e3:
        return f'{x/1e3:g} kS/s'
    return f'{x:g} S/s'

def axis_label(x,axis):
    return format_duration(x) if axis=='nominal_duration' else format_rate(x)

def heatmap(comp,axis,view,field,target,dpi=160):
    colour();cc=[q for q in comp if q['axis']==axis and q['window']==view and q['summary']]
    specs=sorted({(q['platform'],q['label'],q['series']) for q in cc});xs=sorted({q['axis_value'] for q in cc});ids=[s[2] for s in specs]
    lookup={(q['series'],q['axis_value']):q for q in cc}
    a=np.full((len(ids),len(xs)),np.nan)
    for i,sid in enumerate(ids):
        for j,x in enumerate(xs):
            q=lookup.get((sid,x));val=q.get(field) if q else None
            if val is not None:a[i,j]=val
    signed=field=='median_relative_pct';bound=5. if axis=='sample_rate' else 20.
    if not signed:bound=5.
    cmap=plt.get_cmap('RdBu_r' if signed else 'YlGnBu').copy();cmap.set_bad('#eeeeee')
    fig=plt.figure(figsize=(max(11.5,len(xs)*.48+5),max(4.5,len(ids)*.36+2.9)))
    ax=fig.add_axes([.29,.30,.62,.56]);norm=TwoSlopeNorm(vmin=-bound,vcenter=0,vmax=bound) if signed else Normalize(0,bound)
    im=ax.imshow(np.ma.masked_invalid(a),aspect='auto',cmap=cmap,norm=norm,interpolation='nearest')
    ax.set_xticks(range(len(xs)),[axis_label(x,axis) for x in xs],rotation=66 if len(xs)>12 else 0,ha='right' if len(xs)>12 else 'center')
    ax.set_yticks(range(len(ids)),[s[1] for s in specs]);ax.tick_params(axis='y',labelsize=9)
    ax.set_xlabel('Native sample rate' if axis=='sample_rate' else 'Requested benchmark duration')
    for i,sid in enumerate(ids):
        for j,x in enumerate(xs):
            q=lookup.get((sid,x))
            if q is None or q.get(field) is None:
                ax.text(j,i,'N/A',ha='center',va='center',fontsize=7,color='.42');continue
            warns=bool(q['flags']) or q['n']<q['n_reported']
            # Compact corner marker instead of full-cell hatching. Values remain visible.
            if warns:ax.text(j+.34,i-.31,'•',ha='center',va='center',fontsize=8,color='black')
            val=q[field]
            if abs(val)>bound:ax.text(j,i,f'{val:.0f}',ha='center',va='center',fontsize=6,color='white')
    metric='energy' if axis=='sample_rate' else 'mean load power'
    desc={'median_relative_pct':f'Median {metric}: relative difference (%)','repeatability_cv_pct':f'Run-to-run {metric} variation: σ / |mean| (%)',
          'q95_absolute_relative_pct':f'Empirical q95 absolute {metric} difference (%)'}[field]
    ax.set_title(desc+'\n'+VIEW_LABELS[view],fontsize=13,pad=13)
    cb=fig.colorbar(im,ax=ax,fraction=.035,pad=.025,extend='both' if signed else 'max');cb.set_label('%')
    ref='2 kS/s' if axis=='sample_rate' else '600 s'
    fig.text(.29,.045,f'Fixed within-series comparator: {ref}; all finite outcomes retained.\n'
             'N/A: unavailable numeric result; dot: retained source or interval note.\n'
             'Direct sweeps comprise separate physical executions; differences include protocol effects.',fontsize=8.5)
    return save(fig,target,dpi)

def threshold_plot(records,axis,view,target,dpi=160):
    colour();rr=[r for r in records if r['axis']==axis and r['window']==view]
    names=sorted({(r['label'],r['series']) for r in rr});eps=[1.,2.,5.];idx={(r['series'],r['tolerance_pct']):r for r in rr}
    fig=plt.figure(figsize=(10,max(4.7,len(names)*.41+2.4)));ax=fig.add_axes([.38,.23,.58,.64])
    colours=['#1f77b4','#ff7f0e','#2ca02c']
    for i,(label,series) in enumerate(names):
        for j,e in enumerate(eps):
            r=idx[series,e];x=r['first_observed_setting'];warns=bool(r['flags']) or r['candidates_incomplete']
            ax.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=colours[j] if x is not None else '#eeeeee',alpha=.14 if x is not None else 1,edgecolor='white',linewidth=1))
            if x is not None:
                text=axis_label(x,axis)+(' •' if warns else '');col=colours[j]
            else:
                text={'not_met_on_observed_grid':'not met','endpoint_only_not_a_threshold':'endpoint only','reference_unavailable_or_n_lt_2':'no comparator'}.get(r['status'],'N/A');col='.4'
            ax.text(j,i,text,ha='center',va='center',fontsize=9,color=col)
    ax.set_yticks(range(len(names)),[a for a,b in names],fontsize=9)
    ax.set_xticks(range(3),['1 %','2 %','5 %']);ax.xaxis.tick_top();ax.tick_params(axis='both',length=0)
    ax.set_xlim(-.5,2.5);ax.set_ylim(len(names)-.5,-.5)
    for spine in ax.spines.values():spine.set_visible(False)
    fig.suptitle('Persistent agreement on the observed grid\n'+VIEW_LABELS[view],fontsize=14,y=.97)
    ref='2 kS/s' if axis=='sample_rate' else '600 s'
    fig.text(.06,.055,'First tested setting meeting the empirical q95 criterion at this and every higher tested setting.\n'
             f'Fixed within-series comparator: {ref}; at least two settings and n ≥ 2. Dot: retained note.\n'
             'Descriptive agreement on the observed grid; not calibrated accuracy or a sampling-rate bound.',fontsize=9)
    return save(fig,target,dpi)

def duration_curves(data,registry,view,platform,target,dpi=160):
    colour();specs=[s for s in registry if s['summary'] and s['axis']=='nominal_duration' and s['platform']==platform]
    fig=plt.figure(figsize=(10.5,5.8));ax=fig.add_axes([.1,.22,.86,.66]);nlines=0
    for spec in specs:
        actual=paper_view(spec) if view=='paper_selected' else view
        ref=data.group(spec['id'],actual,'pico',600.)['power_median']
        if ref is None or ref<=0:continue
        xx=data.grid(spec['id']);gg=[data.group(spec['id'],actual,'pico',x) for x in xx]
        vals=[100*(g['power_median']/ref-1) if g['power_median'] is not None else np.nan for g in gg]
        c=COLORS.get(spec['slug'],'#17becf')
        ax.semilogx(xx,vals,marker='o',markersize=4,color=c,label=spec['label'].split(' / ',1)[1]);nlines+=1
    ax.axhline(0,ls='-',color='.4',lw=.7);ax.axhline(1,ls='--',color='.5',lw=.7);ax.axhline(-1,ls='--',color='.5',lw=.7)
    ticks=sorted({x for spec in specs for x in data.grid(spec['id'])})
    ax.set_xticks(ticks,[format_duration(x) for x in ticks],rotation=35,ha='right')
    ax.set_xlabel('Requested benchmark duration');ax.set_ylabel('Median power relative to the 600-s group (%)')
    ax.set_title(platform+': Duration dependence — '+VIEW_LABELS[view]);ax.grid(True,which='both');ax.legend(ncol=2,fontsize=9)
    fig.text(.10,.055,'All finite outcomes; each workload is normalized separately.\n'
             'Detected load intervals; Hailo variable YOLO uses its recorded interval.',fontsize=9)
    return save(fig,target,dpi)

def device_overview(data,registry,view,metric,target,dpi=160):
    colour();specs=sorted([s for s in registry if s['summary'] and s['axis']=='nominal_duration' and 300 in s['grid']],key=lambda s:s['label'])
    fig=plt.figure(figsize=(12,max(4.5,.47*len(specs)+2.6)));ax=fig.add_axes([.3,.22,.64,.60])
    for i,spec in enumerate(specs):
        actual=paper_view(spec) if view=='paper_selected' else view
        for j,se in enumerate(('firmware','jetson','shelly','hailo_rt')):
            g=data.pair_group(spec['id'],actual,se,300.)
            val=g[metric+'_paired_median_pct'];lo=g[metric+'_paired_q25_pct'];hi=g[metric+'_paired_q75_pct']
            if val is None:continue
            y=i+(j-1.5)*.12
            ax.errorbar([val],[y],xerr=[[val-lo],[hi-val]],fmt='o',markersize=4,color=SENSOR_COLORS[se],capsize=2,
                        markerfacecolor='white' if g['n_flagged'] else SENSOR_COLORS[se])
    ax.axvline(0,color='.4',lw=.8);ax.set_yticks(range(len(specs)),[s['label'] for s in specs],fontsize=9);ax.set_ylim(len(specs)-.5,-.5)
    ax.set_xlabel('Paired '+metric+' difference from PicoScope (%)');ax.grid(True,axis='x');fig.suptitle('Measurement paths at requested 300 s\n'+VIEW_LABELS[view],y=.98,fontsize=14)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([],[],marker='o',color=SENSOR_COLORS[s],label=LABELS[s],ls='') for s in ('firmware','jetson','shelly','hailo_rt')],ncol=4,loc='upper center',bbox_to_anchor=(.5,1.09),fontsize=9)
    fig.text(.10,.065,'Same execution IDs: median of individual paired differences with interquartile interval.\n'
             'Paths retain their own intervals, electrical boundaries and scaling.\n'
             'Open markers: retained note. This is not a synchronized instrument-error estimate.',fontsize=9)
    return save(fig,target,dpi)

def controlled_effect_plot(effect_rows,target,dpi=160):
    colour();wanted=['pico_load_20_80_mean_power_W','pico_dynamic_W','vdd_load_W','TRT_time_s']
    labels={'pico_load_20_80_mean_power_W':'Pico load','pico_dynamic_W':'Pico load − baseline','vdd_load_W':'Jetson VDD_IN','TRT_time_s':'TensorRT runtime'}
    lookup={r['metric']:r for r in effect_rows};rows=[lookup[k] for k in wanted]
    y=np.arange(len(rows));x=np.array([float(r['balanced_effect_percent_of_2kSps_mean']) for r in rows])
    lo=np.array([float(r['ci95_low_percent_of_2kSps_mean']) for r in rows]);hi=np.array([float(r['ci95_high_percent_of_2kSps_mean']) for r in rows])
    fig=plt.figure(figsize=(9.4,4.8));ax=fig.add_axes([.28,.20,.68,.68])
    ax.errorbar(x,y,xerr=np.vstack([x-lo,hi-x]),fmt='o',capsize=4,color='#1f77b4')
    ax.axvline(0,color='.35',lw=.9);ax.set_yticks(y,[labels[r['metric']] for r in rows]);ax.set_xlabel('Position-balanced effect: 5 MS/s − 2 kS/s (%)')
    ax.set_title('Controlled GEMM-FP16 diagnostic');ax.grid(True,axis='x');ax.invert_yaxis()
    fig.text(.08,.045,'Two complementary six-run sessions, 250 queries, 120-s process gaps.\n95% t intervals from the fixed additive model; not a dynamic uncertainty budget.',fontsize=9)
    return save(fig,target,dpi)

def direct_vs_controlled_plot(data,effect_rows,target,dpi=160):
    colour();sid='historical/sweep_without_filter/gemm/fp16'
    g2=data.group(sid,'envelope_0.5','pico',2000.);g5=data.group(sid,'envelope_0.5','pico',5000000.)
    direct=100*(g5['energy_median']/g2['energy_median']-1)
    lookup={r['metric']:r for r in effect_rows};ctrl=lookup['pico_load_20_80_mean_power_W'];vdd=lookup['vdd_load_W']
    labels=['Recorded direct sweep\n(separate executions)','Controlled Pico test\n(position-balanced)','Jetson VDD_IN\n(position-balanced)']
    vals=[direct,float(ctrl['balanced_effect_percent_of_2kSps_mean']),float(vdd['balanced_effect_percent_of_2kSps_mean'])]
    fig=plt.figure(figsize=(9.8,5.2));ax=fig.add_axes([.12,.27,.84,.61])
    colors=['#d62728','#1f77b4','#2ca02c'];ax.bar(range(3),vals,color=colors,alpha=.82)
    ymin=min(vals)-.28;ymax=max(.22,max(vals)+.18);ax.set_ylim(ymin,ymax)
    ax.axhline(0,color='.35',lw=.9);ax.set_xticks(range(3),labels);ax.set_ylabel('5 MS/s relative to 2 kS/s (%)')
    ax.set_title('GEMM FP16: direct sweep and controlled diagnostic');ax.grid(True,axis='y')
    span=ymax-ymin
    for i,v in enumerate(vals):
        offset=.025*span if v>=0 else -.025*span
        ax.text(i,v+offset,f'{v:+.3f} %',ha='center',va='bottom' if v>=0 else 'top',fontsize=10)
    fig.text(.10,.05,'The direct sweep includes session, order, baseline and acquisition effects.\nThe control tests the rate-associated residual within its fixed protocol.',fontsize=9)
    return save(fig,target,dpi)
