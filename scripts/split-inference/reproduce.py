#!/usr/bin/env python3
"""One offline CLI for the broad, current Native A4 paper analysis.

Extends the Twix reproduce.py readers and statistical conventions, with a
single broad selection and metric-specific observation coverage. Existing
compact manifests bind the inputs; no whole-archive hashing is performed.
"""
import argparse
import hashlib
import os
import json
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_paper_dataset import build, read, write


def validate_config(c):
    expected = {'source_generation':'deepx_native_a4_20261015',
                'selection':'broad_numeric_observations',
                'performance_aggregation':'stored_cohort_median',
                'energy_aggregation':'mean_per_repeat_E_over_completed_images',
                'energy_basis':'calibrated_host_inclusive_raw',
                'energy_unit':'J/image','table3_runner':'native',
                'baseline_selection':'fastest_observed_full_same_model_and_host',
                'point_summary':'median',
                'equal_model_aggregation':'median_points_per_model_setup_then_mean_setups_per_model_then_mean_models',
                'tie_break':'uid_ascending',
                'pareto_scope':'model_setup_all_observed_deployments',
                'pareto_objectives':{'fps':'maximize','energy_mj_per_image':'minimize'},
                'pareto_quality_veto':False}
    for k,v in expected.items():
        if c.get(k)!=v:
            raise ValueError(f'Unsupported {k}={c.get(k)!r}; this package implements {v!r}')
    assert not any(c.get(k) for k in ['quality_veto','claim_veto','hash_veto']), 'Main selection is broad by design'
    assert isinstance(c['table3_top_n'],int) and c['table3_top_n']>0
    assert set(c['sensitivities']) <= {'broad','both_reference_close','original_strict_flags','exclude_administrative_receipt_gaps'}
    assert set(c['sensitivity_energy_bases']) <= {'raw','existing_comparison'}


def format_tables(output):
    T=output/'tables'
    t2,t3=read(T/'table2_full.json'),read(T/'table3_top2_native.json')
    labels={'mobilenet_v3_large':'MobileNetV3-L','regnet_x_1_6gf':'RegNet-X 1.6GF','resnet50':'ResNet-50',
            'yolo11l':'YOLO11l','yolo26m':'YOLO26m','yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}
    def fmt(x,n=0):return 'NA' if x is None else f'{x:.{n}f}'
    def tex(s):return str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')
    def rng(r,metric,n=0):return fmt(r['trt_'+metric+'_min'],n)+'–'+fmt(r['trt_'+metric+'_max'],n)
    md=['# Table 2: Full deployments','',
        'TRT spans are the range of the three measured host aggregates, not repeat confidence intervals. Energies are calibrated, host-inclusive mJ/image; throughput is images/s. Full host values and their means are retained in CSV/JSON. Dataset quality and timed-work differences accompany the broad observations.','',
        '| Model | TRT FPS range | TRT mJ/image range | H8 FPS | H8 mJ/image | H10 FPS | H10 mJ/image | DeepX FPS | DeepX mJ/image |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    tx=[r'% Requires booktabs and siunitx; input inside a table/table* environment.',
        r'\begin{tabular}{l cc S[table-format=4.0] S[table-format=4.2] S[table-format=4.0] S[table-format=4.2] S[table-format=4.0] S[table-format=4.2]}',
        r'\toprule',r'Model & TRT FPS range & TRT mJ/image range & {H8 FPS} & {H8 mJ/image} & {H10 FPS} & {H10 mJ/image} & {DeepX FPS} & {DeepX mJ/image} \\',r'\midrule']
    for r in t2:
        values=[labels.get(r['model'],r['model']),rng(r,'fps'),rng(r,'mj',2)]
        values += [fmt(r[s+'_'+m],0 if m=='fps' else 2) for s in ['H8','H10','DeepX'] for m in ['fps','mj']]
        md.append('| '+' | '.join(values)+' |')
        tv=[tex(values[0]),values[1].replace('–','--'),values[2].replace('–','--')]+['{NA}' if v=='NA' else v for v in values[3:]]
        tx.append(' & '.join(tv)+r' \\')
    tx += [r'\bottomrule',r'\end{tabular}']
    (T/'table2_full.md').write_text('\n'.join(md)+'\n');(T/'table2_full.tex').write_text('\n'.join(tx)+'\n')
    md=['# Table 3: Native configurations with the largest observed speedup','',
        'Two Native splits per model ranked from unrounded FPS ratios against the fastest measured Full on the same host; ties use ascending UID. Energy does not alter this ranking. G_n = energy of that same Full / split energy. Selection is retrospective; quality and endpoint differences remain in the dataset.','',
        '| Model | Rank | Setup/cut | Full | Full FPS | Split FPS | Speedup | Split mJ/image | G_n |',
        '|---|---:|---|---|---:|---:|---:|---:|---:|']
    tx=[r'% Requires booktabs and siunitx; input inside a table/table* environment.',
        r'\begin{tabular}{l r l l S[table-format=4.0] S[table-format=4.0] S[table-format=2.2] S[table-format=4.2] S[table-format=2.2]}',
        r'\toprule',r'Model & Rank & Setup/cut & Full & {Full FPS} & {Split FPS} & {Speedup} & {Split mJ/image} & {$G_n$} \\',r'\midrule']
    backend={'native_full_tensorrt':'TRT','native_full_deepx':'DeepX','native_full_hailo8':'H8','native_full_hailo10h':'H10'}
    for r in t3:
        v=[labels.get(r['model'],r['model']),str(r['rank']),r['setup']+'/'+r['case'],backend.get(r['baseline_backend'],r['baseline_backend']),fmt(r['baseline_fps']),fmt(r['split_fps']),fmt(r['speedup'],2),fmt(r['split_mj_per_image'],2),fmt(r['energy_gain_same_full'],2)]
        md.append('| '+' | '.join(v)+' |')
        tx.append(' & '.join([tex(x) for x in v[:4]]+['{NA}' if x=='NA' else x for x in v[4:]])+r' \\')
    tx += [r'\bottomrule',r'\end{tabular}']
    (T/'table3_top2_native.md').write_text('\n'.join(md)+'\n');(T/'table3_top2_native.tex').write_text('\n'.join(tx)+'\n')
    # Supplement tables expose every model/setup group, not just the Top-2.
    opts=read(T/'model_setup_optima.json')
    caption=('Fastest and minimum-energy observed splits within each model/setup/runner. '
             'Candidate counts describe the measured search space. Q is the existing dataset metric in percent: '
             'Top-1 for classifiers and COCO mAP@[.50:.95] for detectors. These metrics are not pooled. '
             'Shared optima are one point; all choices are retrospective. Energy is host-inclusive mJ/image.')
    md=['# Model/setup split optima','',caption,'',
        '| Runner | Model | Setup | Candidates | Fastest cut | FPS | mJ/image | Q (%) | Min-energy cut | FPS | mJ/image | Q (%) | Same point |',
        '|---|---|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|']
    tx=[r'% Requires booktabs, longtable and siunitx. Landscape placement recommended.',
        r'\begingroup\scriptsize\setlength{\tabcolsep}{3pt}',
        r'\begin{longtable}{l l r l S[table-format=4.0] S[table-format=4.2] S[table-format=2.2] l S[table-format=4.0] S[table-format=4.2] S[table-format=2.2] l}',
        r'\caption{'+tex(caption)+r'}\\',r'\toprule',
        r'Model (Q metric) & Setup & $n$ & Fastest cut & {FPS} & {mJ/image} & {Q (\%)} & Min-energy cut & {FPS} & {mJ/image} & {Q (\%)} & Same \\',
        r'\midrule\endhead']
    for runner in ['native','generic']:
        tx.append(r'\multicolumn{12}{l}{\textbf{'+runner.title()+r'}}\\')
        for r in [x for x in opts if x['runner']==runner]:
            metric='Top-1' if r['quality_metric'] in ['top1','top1_accuracy'] else 'mAP'
            label=labels.get(r['model'],r['model'])+' ('+metric+')'
            q=lambda v:fmt(100*v,2) if v is not None else 'NA'
            v=[label,r['setup'],str(r['candidate_count']),r['fastest_case'] or 'NA',fmt(r['fastest_fps']),fmt(r['fastest_mj_per_image'],2),q(r['fastest_quality']),r['lowest_energy_case'] or 'NA',fmt(r['lowest_energy_fps']),fmt(r['lowest_energy_mj_per_image'],2),q(r['lowest_energy_quality']),'yes' if r['same_optimum'] is True else ('no' if r['same_optimum'] is False else 'NA')]
            md.append('| '+' | '.join([runner.title()]+v)+' |')
            tx.append(' & '.join(['{NA}' if x=='NA' else tex(x) for x in v])+r' \\')
    tx += [r'\bottomrule',r'\end{longtable}',r'\endgroup']
    (T/'model_setup_optima.md').write_text('\n'.join(md)+'\n');(T/'model_setup_optima.tex').write_text('\n'.join(tx)+'\n')
    groups=read(T/'native_generic_groups.json')
    caption=('All measured Native/Generic pairs by model and setup. Each win count retains its own denominator; '
             'both-better requires observed FPS and energy. Ratios are Native/Generic; FPS above one and '
             'host-inclusive energy below one favor Native. These are medians across operating points, not repeat intervals.')
    md=['# Native/Generic by model and setup','',caption,'',
        '| Model | Setup | Faster / FPS pairs | Lower energy / energy pairs | Both / joint pairs | Median FPS ratio | Median energy ratio |',
        '|---|---|---:|---:|---:|---:|---:|']
    tx=[r'% Requires booktabs, longtable and siunitx.',r'\begingroup\small',
        r'\begin{longtable}{l l r r r S[table-format=1.3] S[table-format=1.3]}',
        r'\caption{'+tex(caption)+r'}\\',r'\toprule',
        r'Model & Setup & Faster / $n_P$ & Lower energy / $n_E$ & Both / $n_J$ & {Median FPS ratio} & {Median energy ratio} \\',r'\midrule\endhead']
    for r in groups:
        v=[labels.get(r['model'],r['model']),r['setup'],str(r['faster'])+'/'+str(r['n_performance']),str(r['energy_lower'])+'/'+str(r['n_energy']),str(r['both_better'])+'/'+str(r['n_joint']),fmt(r['fps_ratio_median'],3),fmt(r['energy_ratio_median'],3)]
        md.append('| '+' | '.join(v)+' |')
        tx.append(' & '.join(['{NA}' if x=='NA' else tex(x) for x in v])+r' \\')
    tx += [r'\bottomrule',r'\end{longtable}',r'\endgroup']
    (T/'native_generic_groups.md').write_text('\n'.join(md)+'\n');(T/'native_generic_groups.tex').write_text('\n'.join(tx)+'\n')


def main():
    root=Path(__file__).resolve().parent
    expected=root.parents[1]/'results/split-inference'
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs',type=Path,default=expected/'data/inputs')
    ap.add_argument('--config',type=Path,default=root/'config.json')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--numeric-only',action='store_true',help='Regenerate and verify numerical tables without plotting dependencies')
    ap.add_argument('--verify',action='store_true',help='Run independent checks and compare generated scientific artifacts to the checked-in results')
    a=ap.parse_args()
    os.environ.setdefault('MPLCONFIGDIR', str(a.output.resolve().parent / '.matplotlib-cache'))
    assert not a.output.exists() or not any(a.output.iterdir()), 'Use a fresh output directory'
    config=read(a.config);validate_config(config)
    manifest=read(a.inputs/'MANIFEST.json')
    for name,h in manifest.items():
        p=a.inputs/name
        assert p.resolve().is_relative_to(a.inputs.resolve()),name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==h,('input changed',name)
    a.output.mkdir(parents=True,exist_ok=True)
    summary=build(a.inputs,a.output,config)
    format_tables(a.output)
    if not a.numeric_only:
        from render_figures import render
        render(a.output)
        from generate_report import render as report
        report(a.output)
    if a.verify:
        subprocess.run([sys.executable, '-I', '-B', str(root/'validation/test_edge_cases.py')], check=True)
        subprocess.run([sys.executable, '-I', '-B', str(root/'validation/independent_check.py'),
                        '--inputs', str(a.inputs), '--output', str(a.output)], check=True)
        subprocess.run([sys.executable, '-I', '-B', str(root/'verify_reproduction.py'),
                        '--expected', str(expected), '--actual', str(a.output)], check=True)
    print(json.dumps(summary,sort_keys=True),flush=True)

if __name__=='__main__':
    main()
