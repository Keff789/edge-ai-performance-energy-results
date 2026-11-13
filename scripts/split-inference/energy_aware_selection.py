#!/usr/bin/env python3
"""Retrospective quality-constrained Native energy selection; no new measurements.

The dataset is the existing PAPER_DATASET.json. Output is additional to all
frozen publication exports. Unrounded selected values and source identities are
retained; display rounding is restricted to TeX/Markdown.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path

LABELS = {'mobilenet_v3_large':'MobileNetV3-L','regnet_x_1_6gf':'RegNet-X',
          'resnet50':'ResNet-50','yolo11l':'YOLO11l','yolo26m':'YOLO26m',
          'yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}
SOURCE_PATH = 'results/split-inference/data/PAPER_DATASET.json'
QUALITY_TOLERANCE = .05

def positive(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0

def admissible(row):
    if row.get('kind')!='split' or row.get('runner')!='native':
        return False
    if not all(row.get(k) is True for k in ['included_joint','included_energy','included_performance']):
        return False
    q,ref=row.get('quality_value'),row.get('quality_reference_value')
    if not positive(ref) or not isinstance(q,(int,float)) or isinstance(q,bool) or not math.isfinite(q):
        return False
    if (ref-q)/ref>QUALITY_TOLERANCE:
        return False
    if 'quality' in row.get('current_observation_metric_updates',[]) and row.get('normal_quality') is not True:
        return False
    return positive(row.get('fps')) and positive(row.get('energy_mj_per_image'))

def select(rows, floor):
    if not positive(floor) or floor>1:
        raise ValueError('throughput floor must lie in (0,1]')
    groups=collections.defaultdict(list)
    for row in rows:
        if admissible(row):groups[(row['model_id'],row['setup_id'])].append(row)
    output=[]
    for (model,setup),group in sorted(groups.items()):
        fastest=min(group,key=lambda r:(-r['fps'],r['uid']))
        qualified=[r for r in group if r['fps']>=floor*fastest['fps']]
        energy=min(qualified,key=lambda r:(r['energy_mj_per_image'],-r['fps'],r['uid']))
        output.append(dict(model=model,setup=setup,candidate_count=len(group),
            minimum_throughput_fraction=floor,minimum_fps=floor*fastest['fps'],
            eligible_within_throughput_floor=len(qualified),
            fastest_case=fastest['case_id'],fastest_uid=fastest['uid'],
            fastest_fps=fastest['fps'],fastest_energy_mj_per_image=fastest['energy_mj_per_image'],
            selected_case=energy['case_id'],selected_uid=energy['uid'],
            selected_fps=energy['fps'],selected_energy_mj_per_image=energy['energy_mj_per_image'],
            fastest_quality=fastest['quality_value'],selected_quality=energy['quality_value'],
            quality_reference=energy['quality_reference_value'],
            fastest_relative_quality_loss=(fastest['quality_reference_value']-fastest['quality_value'])/fastest['quality_reference_value'],
            selected_relative_quality_loss=(energy['quality_reference_value']-energy['quality_value'])/energy['quality_reference_value'],
            throughput_retained_pct=100*energy['fps']/fastest['fps'],
            throughput_loss_pct=100*(1-energy['fps']/fastest['fps']),
            energy_change_pct=100*(energy['energy_mj_per_image']/fastest['energy_mj_per_image']-1),
            energy_reduction_pct=100*(1-energy['energy_mj_per_image']/fastest['energy_mj_per_image']),
            changed=energy['uid']!=fastest['uid']))
    return output

def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def table(rows,language):
    floor=rows[0]['minimum_throughput_fraction'];changed=[r for r in rows if r['changed']]
    if language=='en':
        caption=(f'Retrospective Native energy selection among quality-admissible measured splits with at least {100*floor:g}\\% of the fastest Native throughput in the same model--accelerator combination. Only changed choices are listed. All candidates satisfy the 5\\% CPU-relative quality-loss rule. Energy change refers to the fastest Native split, not to Full execution. The analysis assumes measured throughput and energy for all admitted cuts; it does not evaluate limited-budget energy ranking or statistical significance.')
        headers=r'Combination & Fastest cut & Selected cut & Retained (\%) & \shortstack{Fastest energy\\(mJ/image)} & \shortstack{Selected energy\\(mJ/image)} & \shortstack{Energy change\\(\%)} \\\n'
    else:
        caption=(f'Retrospektive Native-Energieauswahl unter den gemessenen qualitätszulässigen Splits mit mindestens {100*floor:g}\\% des höchsten Native-Durchsatzes derselben Modell--Beschleuniger-Kombination. Nur geänderte Entscheidungen sind aufgeführt. Alle Kandidaten erfüllen die 5\\%-Grenze für den relativen Qualitätsverlust zur CPU-Referenz. Die Energieänderung bezieht sich auf den schnellsten Native-Split, nicht auf Full. Die Analyse setzt Durchsatz- und Energiemessungen für alle zulässigen Schnitte voraus und untersucht weder eine Energie-Rangfolge bei begrenztem Budget noch statistische Signifikanz.')
        headers=r'Kombination & Schnellster Schnitt & Gewählter Schnitt & Erhalten (\%) & \shortstack{Energie schnellster\\(mJ/Bild)} & \shortstack{Energie gewählter\\(mJ/Bild)} & \shortstack{Energieänderung\\(\%)} \\\n'
    lines=[r'\begin{table*}[t]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',r'\caption{'+caption+'}',r'\label{tab:energy-floor-'+str(round(100*floor))+'}',r'\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lllrrrr@{}}',r'\toprule',headers.replace('\\n','\n').rstrip(),r'\midrule']
    for r in changed:
        lines.append(f"{LABELS.get(r['model'],r['model'])}/{r['setup']} & {r['fastest_case']} & {r['selected_case']} & {r['throughput_retained_pct']:.2f} & {r['fastest_energy_mj_per_image']:.2f} & {r['selected_energy_mj_per_image']:.2f} & {r['energy_change_pct']:+.2f} "+r'\\')
    lines.extend([r'\bottomrule',r'\end{tabular*}',r'\end{table*}'])
    return '\n'.join(lines)+'\n'

def reproduce(dataset,output,languages=('en','de')):
    raw=Path(dataset).read_bytes();rows=json.loads(raw)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    results={str(round(100*f)):select(rows,f) for f in [.99,.95]}
    if not all(results.values()):raise ValueError('no eligible Native measurements')
    for language in languages:
        folder=out/'artifacts'/language/'tables';folder.mkdir(parents=True,exist_ok=True)
        for key,selected in results.items():
            stem=folder/('energy_floor_'+key)
            stem.with_suffix('.json').write_text(json.dumps(selected,indent=2,allow_nan=False)+'\n')
            write_csv(stem.with_suffix('.csv'),selected)
            stem.with_suffix('.tex').write_text(table(selected,language))
    summary={key:dict(combinations=len(rs),candidates=sum(r['candidate_count'] for r in rs),changed_choices=sum(r['changed'] for r in rs),maximum_energy_reduction_pct=max(r['energy_reduction_pct'] for r in rs),mean_energy_reduction_pct=sum(r['energy_reduction_pct'] for r in rs)/len(rs),maximum_throughput_loss_pct=max(r['throughput_loss_pct'] for r in rs)) for key,rs in results.items()}
    manifest=dict(schema='retrospective-native-energy-selection-v1',source_path=SOURCE_PATH,source_sha256=hashlib.sha256(raw).hexdigest(),source_git_blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),quality_tolerance=QUALITY_TOLERANCE,selection='minimum measured energy among Native splits with FPS >= floor * maximum admitted Native FPS, within each model/setup',tie_break='energy ascending, FPS descending, UID ascending; fastest uses FPS descending then UID ascending',scope='Measured Native splits only; single-backend Full and Generic are excluded. No new measurements. Numeric admissibility is not statistical equivalence. No end-to-end or limited-budget energy-search cost is evaluated.',summary=summary)
    manifest.update(generator='scripts/split-inference/energy_aware_selection.py',
                    generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    hardware_measurements=False,
                    outputs={str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((out/'artifacts').rglob('*')) if p.is_file()})
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--languages',nargs='+',choices=['en','de'],default=['en','de']);args=p.parse_args()
    print(json.dumps(reproduce(args.dataset,args.output,args.languages),indent=2))
