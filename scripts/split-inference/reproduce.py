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
                'fastest_split_selection':'maximum_observed_fps_native_and_generic_all_setups',
                'fastest_full_selection':'maximum_observed_fps_concrete_full_uid',
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
    assert isinstance(c['model_order'], list) and all(isinstance(m, str) for m in c['model_order'])
    assert len(c['model_order']) == len(set(c['model_order'])), 'Duplicate configured model'


def format_fastest_tables(rows):
    """Readable views of the shared absolute-FPS selections; round only here."""
    labels={'mobilenet_v3_large':'MobileNetV3-L','regnet_x_1_6gf':'RegNet-X 1.6GF','resnet50':'ResNet-50',
            'yolo11l':'YOLO11l','yolo26m':'YOLO26m','yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}
    backends={'native_full_tensorrt':'TRT','native_full_deepx':'DeepX',
              'native_full_hailo8':'H8','native_full_hailo10h':'H10'}

    def fmt(value, places=0):
        return 'NA' if value is None else f'{value:.{places}f}'

    def tex(value):
        return str(value).replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')

    def deployment(row, prefix, latex=False):
        if row[prefix + '_uid'] is None:
            return 'NA'
        setup = row[prefix + '_setup'] or row[prefix + '_physical_host'] or 'unknown'
        if prefix == 'split':
            parts = [row['split_runner'].title(), setup + '/' + (row['split_case'] or 'unknown cut')]
        else:
            backend = row[prefix + '_backend'] or 'unknown backend'
            parts = [backends.get(backend, backend), '(' + setup + ' host)']
        if latex:
            return r'\shortstack[l]{' + r'\\'.join(tex(part) for part in parts) + '}'
        return ' '.join(parts)

    common = ('Selection uses unrounded observed cohort FPS across all setups and Native/Generic splits; '
              'exact ties use ascending UID. Energy is the mean calibrated host-inclusive J/image, displayed as mJ/image, '
              'of each exact FPS-selected UID. Energy and quality never veto the FPS selection. '
              'NA denotes a missing candidate or metric, with explicit reasons and full original records in CSV/JSON. '
              'These retrospective deployment comparisons do not imply equal quality, equal timed endpoints, '
              'an isolated split effect or statistically significant differences.')
    a_caption = ('Globally fastest observed Full versus globally fastest observed split, one row per model. '
                 'R_global = split FPS / global Full FPS; delta_E_global (%) = 100 (split energy / global Full energy - 1). '
                 + common)
    b_caption = ('The SAME split selected in Table 3, compared with the fastest Full on its physical host and '
                 'with the globally fastest Full. This table does not reselect the largest relative gain. '
                 'R_host and R_global use the explicitly named Full denominators. ' + common)
    definitions = [
        ('table3_fastest_deployments', 'Table 3: Globally fastest observed deployments', a_caption,
         ['Model','Fastest Full (backend, host)','Full FPS','Full mJ/image','Fastest split (runner, setup/cut)',
          'Split FPS','Split mJ/image','R_global','delta_E_global (%)'],
         'l l r r l r r r r', 'tab:fastest-deployments'),
        ('fastest_split_baselines', 'Selected fastest split: same-host and global Full baselines', b_caption,
         ['Model','Selected split','Split FPS','Fastest same-host Full','Host Full FPS',
          'Globally fastest Full','Global Full FPS','R_host','R_global'],
         'l l r l r l r r r', 'tab:fastest-split-baselines'),
    ]
    output = {}
    tex_headers = {
        'Fastest Full (backend, host)': r'\shortstack{Fastest Full\\(backend, host)}',
        'Fastest split (runner, setup/cut)': r'\shortstack{Fastest split\\(runner, setup/cut)}',
        'Full mJ/image': r'\shortstack{Full\\mJ/image}',
        'Split mJ/image': r'\shortstack{Split\\mJ/image}',
        'Fastest same-host Full': r'\shortstack{Fastest Full\\same host}',
        'Host Full FPS': r'\shortstack{Host Full\\FPS}',
        'Globally fastest Full': r'\shortstack{Globally fastest\\Full}',
        'Global Full FPS': r'\shortstack{Global Full\\FPS}',
        'R_global': r'$R_{\mathrm{global}}$',
        'R_host': r'$R_{\mathrm{host}}$',
        'delta_E_global (%)': r'\shortstack{$\Delta E_{\mathrm{global}}$\\(\%)}',
    }
    for name, title, caption, headers, columns, label in definitions:
        md = ['# ' + title, '', caption, '', '| ' + ' | '.join(headers) + ' |',
              '| ' + ' | '.join('---' if c == 'l' else '---:' for c in columns.split()) + ' |']
        tx = [r'% Requires booktabs. Input inside a table/table* environment after its caption.',
              '% ' + caption, r'\label{' + label + '}',
              r'\begingroup\small\setlength{\tabcolsep}{3pt}',
              r'\begin{tabular}{' + columns + '}', r'\toprule',
              ' & '.join(tex_headers.get(h, tex(h)) for h in headers) + r' \\', r'\midrule']
        for row in rows:
            model = labels.get(row['model'], row['model'])
            if name == 'table3_fastest_deployments':
                values = [model, deployment(row, 'global_full'), fmt(row['global_full_fps']),
                          fmt(row['global_full_mj_per_image'], 2), deployment(row, 'split'),
                          fmt(row['split_fps']), fmt(row['split_mj_per_image'], 2),
                          fmt(row['R_global'], 2), fmt(row['delta_E_global_pct'], 1)]
            else:
                values = [model, deployment(row, 'split'), fmt(row['split_fps']),
                          deployment(row, 'host_full'), fmt(row['host_full_fps']),
                          deployment(row, 'global_full'), fmt(row['global_full_fps']),
                          fmt(row['R_host'], 2), fmt(row['R_global'], 2)]
            md.append('| ' + ' | '.join(values) + ' |')
            tex_values = [tex(value) for value in values]
            deployment_columns = ([(1, 'global_full'), (4, 'split')]
                                  if name == 'table3_fastest_deployments' else
                                  [(1, 'split'), (3, 'host_full'), (5, 'global_full')])
            for column, prefix in deployment_columns:
                tex_values[column] = deployment(row, prefix, latex=True)
            tx.append(' & '.join(tex_values) + r' \\')
        tx += [r'\bottomrule', r'\end{tabular}', r'\endgroup']
        output[name + '.md'] = '\n'.join(md) + '\n'
        output[name + '.tex'] = '\n'.join(tx) + '\n'
    return output


def format_table_index(output):
    """Keep the table catalog part of full and numeric-only reproduction."""
    tables = [
        ('table3_fastest_deployments', 'Recommended Table 3: globally fastest Full versus globally fastest split'),
        ('fastest_split_baselines', 'Same selected fastest split: same-host and global Full baselines'),
        ('baseline_selection', 'Fastest Full and separately minimum-energy Full'),
        ('boundary_cases', 'Actual timed-work boundaries and limits'),
        ('coverage', 'Model/setup/runner coverage'),
        ('energy_repeats', 'Every recorded energy repeat'),
        ('equal_model_summary', 'Equal model weighting'),
        ('full_configurations', 'All host-specific Full deployments'),
        ('model_setup_optima', 'Fastest and minimum-energy configurations by group'),
        ('native_generic_groups', 'Native generic groups'),
        ('native_generic_models', 'Native generic models'),
        ('native_generic_pairs', 'All Native/Generic pairs'),
        ('native_split_full_pairs', 'All Native split/Full comparisons'),
        ('negative_quality', 'Negative quality observations'),
        ('PARETO_POINTS', 'All points: joint model/setup and separate runner fronts'),
        ('pareto', 'Descriptive two-objective front within recorded work cohorts'),
        ('pipeline_repeats', 'Recorded pipeline repeat metadata'),
        ('quality_comparison', 'Quality comparison'),
        ('repeat_uncertainty', 'Repeat counts, ranges, dispersion and energy intervals'),
        ('sensitivity', 'Quality, original flags and energy-basis sensitivities'),
        ('split_full_groups', 'Split full groups'),
        ('split_full_pairs', 'All split/Full comparisons'),
        ('table2_full', 'Full model/backend summary (all host values retained)'),
        ('table3_top2_native', 'Supplement: Top-2 Native splits by relative same-host speedup (historical selection method)'),
    ]
    md = ['# Split-inference tables', '',
          '[Result overview](../README.md) · [Figure gallery](../figures/README.md)', '',
          'CSV is the convenient interchange format; JSON preserves structured fields and exact identities. '
          'Energy is J/image unless a column explicitly uses mJ/image, throughput is images/s, duration is s and power is W. '
          'Quality values are fractions; percentage-point columns are explicitly named. '
          'Existing counts, exclusions and source identifiers are retained.', '',
          'Table 3 and the baseline supplement share the same absolute fastest observed split per model. '
          'The supplement changes only the Full denominator. The separately retained historical Top-2 method '
          'ranks relative same-host speedup and can select different splits.', '',
          '| Table | CSV | JSON | Readable / LaTeX |', '|---|---|---|---|']
    for name, title in tables:
        readable = ('[md](' + name + '.md) · [tex](' + name + '.tex)'
                    if (output/'tables'/(name + '.md')).exists() else '—')
        md.append(f'| {title} | [CSV]({name}.csv) | [JSON]({name}.json) | {readable} |')
    md += ['', 'The complete [deployment dataset](../data/PAPER_DATASET.csv), '
           '[metric sources](../data/METRIC_SOURCES.csv), [measurement generations](../data/MEASUREMENT_GENERATIONS.csv) '
           'and [summary](../data/summary.json) use the same broad selection.']
    (output/'tables'/'README.md').write_text('\n'.join(md) + '\n')


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
    md=['# Supplement: Top-2 Native splits by largest relative same-host speedup','',
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
    fastest = read(T/'table3_fastest_deployments.json')
    assert fastest == read(T/'fastest_split_baselines.json'), 'Both tables must share the selected splits and baselines'
    for name, content in format_fastest_tables(fastest).items():
        (T/name).write_text(content)
    format_table_index(output)


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
