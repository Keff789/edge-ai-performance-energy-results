#!/usr/bin/env python3
"""Replot selected direct measurements using the original TIM Figures 1.1.0 functions."""
from pathlib import Path
import argparse,csv,json,os
from model import Data,paper_view,selected_comparison_grid,threshold_records

REPO=Path(__file__).resolve().parents[3]
INPUT=REPO/'results/energy-measurement/data/tim'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--overview-only',action='store_true',help='Render only the fourteen overview figures.')
a=p.parse_args();out=a.output.resolve()
if out==REPO or REPO in out.parents:p.error('Choose an output directory outside the repository.')
if out.exists() and any(out.iterdir()):p.error('Choose an empty output directory.')
out.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(out/'matplotlib-cache'))
import render
registry=json.loads((INPUT/'final_direct/series.json').read_text())
with (INPUT/'final_direct/plotted_candidates.csv').open(newline='') as f:
    rows=list(csv.DictReader(f))
for row in rows: row['notes']=row['retained_notes']
# Final TIM primary selection: the completed earlier GPU and adjusted-window
# observations remain individual supplementary views, outside primary overviews.
for spec in registry:
    if spec['platform']=='GPU' or spec['slug']=='random_pattern_yolo_adjusted':
        spec['summary']=False
data=Data(rows,registry)
from verify_conventions import verify
verify(data,REPO/'results/energy-measurement')
comparisons=selected_comparison_grid(data,registry);thresholds=threshold_records(comparisons)
with (INPUT/'validation/controlled/complementary/data/balanced_effects.csv').open(newline='') as f:
    effects=list(csv.DictReader(f))
count=0
if not a.overview_only:
    for spec in registry:
        if spec['section'] not in ('primary','diagnostics'):continue
        sid=spec['id'];view=paper_view(spec)
        if not any(data.get(sid,view,se,x) for se in data.sensors(sid) for x in data.grid(sid)):continue
        part='protocol-controls' if spec['section']=='diagnostics' else 'direct-sweeps'
        stem=out/'figures'/part/spec['platform']/spec['folder']/spec['slug']
        if spec['axis']=='sample_rate' and any(data.get(sid,view,'pico',x) for x in data.grid(sid)):
            render.rate_plot(data,spec,view,stem,130);count+=1
        elif spec['axis']=='nominal_duration':
            for kind in ('boxplot','boxplot_full_range','deviations'):
                if kind=='deviations' and len(data.sensors(sid))<2:continue
                render.duration_plot(data,spec,view,kind,stem.with_name(stem.name+'_duration_sweep_'+kind),130);count+=1
        elif spec['axis']=='static':
            render.static_plot(data,spec,view,stem.with_name(stem.name+'_static_comparison'),130);count+=1
base=out/'figures/direct-overview'
for axis,prefix in [('sample_rate','samplerate'),('nominal_duration','duration')]:
    for field,name in [('median_relative_pct','relative_difference'),('repeatability_cv_pct','repeatability'),('q95_absolute_relative_pct','q95_absolute_difference')]:
        render.heatmap(comparisons,axis,'paper_selected',field,base/(prefix+'_'+name),130);count+=1
    render.threshold_plot([r for r in thresholds if data.registry[r['series']]['summary']],axis,'paper_selected',base/(prefix+'_observed_agreement_limits'),130);count+=1
for platform in ('Jetson','Hailo'):
    render.duration_curves(data,registry,'paper_selected',platform,base/(platform.lower()+'_duration_convergence'),130);count+=1
for metric in ('energy','power'):
    render.device_overview(data,registry,'paper_selected',metric,base/('devices_300s_'+metric),130);count+=1
render.controlled_effect_plot(effects,base/'controlled_gemm_fp16_rate_effects',130);count+=1
render.direct_vs_controlled_plot(data,effects,base/'direct_vs_controlled_gemm_fp16',130);count+=1
assert len(list((out/'figures').rglob('*.pdf')))==count
assert len(list((out/'figures').rglob('*.png')))==count
print(f'PASS: {count} charts from {len(rows)} exported finite window candidates; no raw-waveform reads.')
