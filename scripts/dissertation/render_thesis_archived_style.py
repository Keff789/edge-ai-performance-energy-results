#!/usr/bin/env python3
"""Render four thesis assets from archived sources, without new measurements."""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=ROOT)
parser.add_argument('--reference-project', type=Path, default=ROOT/'publications/dissertation/thesis-v56/de/figures')
parser.add_argument('--output', type=Path, default=Path.cwd()/'thesis-archived-style')
args = parser.parse_args()
REPO, REF, OUT = args.repo.resolve(), args.reference_project.resolve(), args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'inputs').mkdir(exist_ok=True)

C = dict(blue='#2E73B6', green='#25896F', orange='#D18432', text='#18354A', secondary='#64798A',
         grid='#DCE4E9', blue_light='#EAF2F9', green_light='#ECF5F1', orange_light='#FCF2E6', neutral='#F3F6F8')
FONT = font_manager.findfont('Nimbus Sans', fallback_to_default=False)
plt.rcParams.update({'font.family':'Nimbus Sans','font.size':11,'axes.labelsize':11,
                     'mathtext.fontset':'custom','mathtext.rm':'Nimbus Sans',
                     'mathtext.it':'Nimbus Sans:italic','mathtext.bf':'Nimbus Sans:bold','mathtext.cal':'Nimbus Sans',
                     'xtick.labelsize':11,'ytick.labelsize':11,'legend.fontsize':10.5,
                     'pdf.fonttype':42,'svg.fonttype':'none','text.color':C['text'],
                     'axes.labelcolor':C['text'],'axes.edgecolor':C['secondary'],
                     'xtick.color':C['text'],'ytick.color':C['text'],
                     'axes.prop_cycle':matplotlib.cycler(color=[C['blue'],C['orange'],C['green']])})
manifest = {'schema':'four-thesis-assets-author-style-v1','font':FONT,'palette':C,
            'measurement_recomputation':False,'analysis_recomputation':False,
            'plot_aggregation':'Existing stage-cost plot_values function retains its original median of reciprocal PC block rates; no analysis definitions or inputs changed.',
            'layout':'Same panels, axes, series, point counts and topology; minor spacing adapts to Nimbus Sans.',
            'source_files':[],'figures':{},'validation':{}}

def source(relative):
    p=REPO/relative
    assert p.is_file(), p
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    dest=OUT/'inputs'/p.name
    if not dest.exists(): shutil.copyfile(p,dest)
    manifest['source_files'].append({'path':relative,'sha256':digest,'copy':'inputs/'+p.name})
    return p

def rows(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))

def reference(name):
    paths=list(REF.rglob(name+'.pdf')); assert len(paths)==1, (name,paths)
    return paths[0]

def style_axes(ax):
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(width=.6,length=3)
    for spine in ax.spines.values(): spine.set_linewidth(.7)
    ax.grid(axis='y',color=C['grid'],linewidth=.6)
    ax.set_axisbelow(True)

def save(fig,name,payload):
    for ext in ('pdf','svg','png'):
        fig.savefig(OUT/(name+'.'+ext),dpi=200,metadata={'Creator':'Archived sources; author-style render'} if ext=='pdf' else None)
    plt.close(fig)
    (OUT/(name+'.data.json')).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    manifest['figures'][name]={'pdf':name+'.pdf','data':name+'.data.json',
                              'reference':str(reference(name)),
                              'reference_sha256':hashlib.sha256(reference(name).read_bytes()).hexdigest()}

def verify_polylines(name,series,logarithmic=False):
    """Check CSV values against published vector paths; never infer plot data from pixels."""
    import fitz
    doc=fitz.open(reference(name))
    candidates=[d for d in doc[0].get_drawings() if d['type']=='s' and all(i[0]=='l' for i in d['items'])]
    checks=[]
    for x,y in series:
        expected=np.column_stack([x,y]); expected=np.log10(expected) if logarithmic else expected
        matches=[]
        for d in candidates:
            if len(d['items'])!=len(expected)-1:continue
            points=np.array([tuple(d['items'][0][1])]+[tuple(i[2]) for i in d['items']])
            residuals=[]
            for k in [0,1]:
                design=np.column_stack([expected[:,k],np.ones(len(expected))])
                coefficients=np.linalg.lstsq(design,points[:,k],rcond=None)[0]
                residuals.append(float(np.max(np.abs(design@coefficients-points[:,k]))))
            matches.append(max(residuals))
        best=min(matches);assert best<0.001,(name,best)
        checks.append({'points':len(expected),'maximum_affine_vector_residual_bp':best})
    manifest['validation'][name]={'archived_values_match_reference_vector_points':True,'series':checks}

calibration = rows(source('results/energy-measurement/data/tim/validation/calibration/jetson_calibration_verification_rows.csv'))
source('scripts/energy-measurement/plot_calibration.py')
series=[]
fig,ax=plt.subplots(figsize=(4.4,2.6));fig.subplots_adjust(left=.18,right=.98,bottom=.23,top=.97)
payload=[]
for sheet,label,color,marker in [('INA225','PicoScope / INA225','blue','s'),('firmware','u.RECS','orange','o')]:
    rr=[r for r in calibration if r['sheet']==sheet and r['zero_target']=='False'];assert len(rr)==35
    x=[float(r['actual_A']) for r in rr]; y=[float(r['signed_relative_error_pct']) for r in rr]
    series.append((x,y));payload.append({'source_sheet':sheet,'label':label,'x':x,'y':y})
    line,=ax.plot(x,y,color=C[color],marker=marker,ms=2.7,lw=.85,label=label)
    assert np.array_equal(line.get_xdata(),x) and np.array_equal(line.get_ydata(),y)
ax.axhline(0,color=C['secondary'],lw=.6,ls=':');ax.set_xlim(0,3.6)
ax.set(xlabel='Referenzstrom (A)',ylabel='Stromabweichung (%)')
ax.set_yticks([-2,-1.5,-1,-.5,0]);ax.legend(frameon=False,loc='lower right',fontsize=10)
style_axes(ax);verify_polylines('current_verification',series);save(fig,'current_verification',payload)

native=rows(source('results/energy-measurement/tables/tim/native_reconstruction.csv'))
source('scripts/energy-measurement/tim/make_foundation_figures.py')
x=[float(r['nominal_duration_s']) for r in native];y=[float(r['native_envelope_Q95_pct']) for r in native]
assert x==[.02,.05,.1,.2,.5,1.,2.,5.,10.]
fig,ax=plt.subplots(figsize=(4.4,2.65));fig.subplots_adjust(left=.18,right=.98,bottom=.23,top=.97)
line,=ax.plot(x,y,'o-',ms=3.5,lw=1.1,color=C['blue'],label='Fest: 2 kS/s')
assert np.array_equal(line.get_xdata(),x) and np.array_equal(line.get_ydata(),y)
ax.axhline(1,ls='--',lw=.85,color=C['orange'],label='1%-Kriterium')
ax.axhline(.5,ls=':',lw=.85,color=C['green'],label='0.5%-Kriterium')
ax.set(xscale='log',yscale='log',xlim=(.015,13),ylim=(.32,16),xlabel='Integrationsintervall',ylabel='Q95-Energiefehler (%)')
ax.xaxis.set_major_locator(FixedLocator([.02,.1,1,10]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{1000*x:g} ms' if x<1 else f'{x:g} s'))
ax.xaxis.set_minor_formatter(NullFormatter());ax.yaxis.set_major_locator(FixedLocator([.5,1,2,5,10]))
ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:g}'));ax.yaxis.set_minor_formatter(NullFormatter())
ax.legend(frameon=False,loc='upper right',fontsize=10)
style_axes(ax);verify_polylines('jetson_rate_duration',[(x,y)],True)
save(fig,'jetson_rate_duration',{'duration_s':x,'native_envelope_Q95_pct':y,'criteria_pct':[1,.5]})

stage_base='results/supplementary-studies/stage-cost-composition/'
analysis=json.loads(source(stage_base+'results/ANALYSIS.json').read_text())
plan=json.loads(source(stage_base+'inputs/PLAN.json').read_text())
comparisons=rows(source(stage_base+'tables/COMPOSITION_COMPARISON.csv'))
renderer=source('scripts/supplementary-studies/stage-cost-composition/render_stage_costs.py')
spec=importlib.util.spec_from_file_location('archived_stage_renderer',renderer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
values=module.plot_values(analysis,plan,comparisons)
fig,ax=plt.subplots(figsize=(4.8,2.7));fig.subplots_adjust(left=.14,right=.99,bottom=.25,top=.85)
xs=np.arange(len(values));width=.22
for offset,key,label,col in [(-width,'P_ms','Produzent P','blue'),(0,'C_ms','Konsument C','orange'),(width,'PC_ms','Pipeline PC','green')]:
    bars=ax.bar(xs+offset,[r[key] for r in values],width,label=label,color=C[col])
    assert [b.get_height() for b in bars]==[r[key] for r in values]
names=[r['label'].replace(' / ','\n').replace('DeepX','DEEPX') for r in values]
ax.set_xticks(xs,names);ax.tick_params(labelsize=8.2)
ax.set_ylabel('Effektives Intervall [ms/Ergebnis]',fontsize=8.2)
ax.set_ylim(0,5);ax.set_yticks([0,1,2,3,4]);ax.set_xlim(-.6,3.6)
ax.legend(frameon=False,loc='lower center',bbox_to_anchor=(.5,1.015),ncol=3,fontsize=8.2,handlelength=1.25,columnspacing=1.1)
style_axes(ax)
import fitz
doc=fitz.open(reference('stage_costs'));rects=[d['rect'] for d in doc[0].get_drawings() if d['type']=='f' and d['fill'] not in (None,(1.,1.,1.)) and d['rect'].height>10]
assert len(rects)==12
heights=np.array([r.height for r in rects]);expected=np.array([r[key] for key in ['P_ms','C_ms','PC_ms'] for r in values])
factor=float(expected@heights/(expected@expected));residual=float(np.max(np.abs(heights-factor*expected)));assert residual<.001
manifest['validation']['stage_costs']={'all_12_bar_values_match_reference_vector_geometry':True,'maximum_scaled_bar_height_residual_bp':residual,'value_extraction':'Existing plot_values function; unchanged archived analysis and comparison inputs.'}
save(fig,'stage_costs',values)

source('scripts/dissertation/legacy-v56/grafiken/generate_redesigned_figures.py')
coords={'A':(.09,.55),'B':(.86,.55),'C1':(1.97,.94),'C2':(1.97,.16),'J':(2.84,.55),'D':(3.62,.55)}
edges=[('A','B'),('B','C1'),('B','C2'),('C1','J'),('C2','J'),('J','D')]
fig=plt.figure(figsize=(4.15,1.42));ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,4.15),ylim=(0,1.42));ax.axis('off')
width,height=.42,.32
for n,(x,y) in coords.items():
    color='blue' if n in ['A','B'] else 'orange' if n in ['C1','C2'] else 'green' if n=='J' else 'secondary'
    fill=C.get(color+'_light',C['neutral'])
    ax.add_patch(FancyBboxPatch((x,y),width,height,boxstyle='round,pad=0,rounding_size=.04',fc=fill,ec=C[color],lw=.8))
    ax.text(x+width/2,y+height/2,n if len(n)==1 else n[0]+'$_'+n[1]+'$',ha='center',va='center',fontsize=9)
for a,b in edges:
    x1,y1=coords[a];x2,y2=coords[b]
    ax.add_patch(FancyArrowPatch((x1+width+.005,y1+height/2),(x2-.005,y2+height/2),arrowstyle='-|>',mutation_scale=7,lw=.8,color=C['secondary'],shrinkA=0,shrinkB=1.4))
ax.plot([1.65,1.65],[.08,1.24],ls='--',lw=1,color=C['secondary'])
ax.text(1.65,1.29,'Schnitt',ha='center',va='center',fontsize=8.5)
doc=fitz.open(reference('dag_cut'));texts=doc[0].get_text().splitlines()
assert set(texts)=={'A','B','C1','C2','J','D','Schnitt'}
assert len([d for d in doc[0].get_drawings() if d['type']=='fs' and len(d['items'])==8])==6
manifest['validation']['dag_cut']={'same_six_nodes':True,'same_six_directed_edges':True,'same_boundary_between_B_and_C1_C2':True,'source':'Earlier conceptual renderer, verified against current thesis labels and vector connections.'}
save(fig,'dag_cut',{'nodes':list(coords),'edges':edges,'cut_after':'B','unique_crossing_tensors':1})
(OUT/'STYLE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'status':'PASS','figures':list(manifest['figures']),'validation':manifest['validation']},indent=2))
