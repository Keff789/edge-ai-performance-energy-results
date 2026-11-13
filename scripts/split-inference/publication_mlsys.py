"""The registered MLSys R22 view of the existing offline analysis.

The reference inventory is a small source specification, not a manuscript or
an alternative measurement dataset. Numeric modules receive freshly generated
broad outputs and keep their historical cohorts explicit.
"""
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from build_paper_dataset import read, write, emit

PROFILE = 'mlsys-r22'
INPUT_ROOT = Path('results/split-inference/publication-inputs') / PROFILE
OUTPUT_ROOT = Path('publications') / PROFILE


def csv_rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def tex(value):
    replacements = {'&': r'\&', '%': r'\%', '_': r'\_', '#': r'\#'}
    return ''.join(replacements.get(c, c) for c in str(value))


def description_table(output, stem, label, caption, headers, rows, records=None):
    """Render approved methods text or calculated counts, with distinct types."""
    table_dir = output/'tables'
    table_dir.mkdir(parents=True, exist_ok=True)
    if records is None:
        write(table_dir/(stem+'.json'), {'kind':'methods_description', 'headers':headers, 'rows':rows})
    else:
        emit(table_dir/stem, records)
    widths = [.23,.71] if len(headers)==2 else [.22,.31,.40]
    columns = ''.join(r'>{\raggedright\arraybackslash}p{'+str(w)+r'\linewidth}' for w in widths)
    content = [r'\begin{table*}[t]', r'\centering\small',
               r'\caption{'+caption+'}', r'\label{'+label+'}',
               r'\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{@{}'+columns+r'@{}}',
               r'\toprule', ' & '.join(headers)+r' \\', r'\midrule']
    for row in rows:
        content.append(' & '.join(str(v) for v in row)+r' \\')
    content += [r'\bottomrule', r'\end{tabular}', r'\end{table*}']
    (table_dir/(stem+'.tex')).write_text('\n'.join(content)+'\n')
    def plain(v):
        v=str(v).replace(r'\%', '%').replace(r'\_', '_').replace(r'\times','×').replace('$','')
        return re.sub(r'\\(?:texttt|textbf)\{([^}]+)\}',r'\1',v).replace(r'\,',' ').replace('~',' ')
    md=['# '+label, '', plain(caption), '', '| '+' | '.join(headers)+' |',
        '| '+' | '.join(['---']*len(headers))+' |']
    md += ['| '+' | '.join(plain(v).replace('|',r'\|') for v in row)+' |' for row in rows]
    (table_dir/(stem+'.md')).write_text('\n'.join(md)+'\n')
    return ['tables/'+stem+'.'+ext for ext in (['json','md','tex'] if records is None else ['csv','json','md','tex'])]


def build_methods(repo_root, broad_output, output):
    spec=read(repo_root/INPUT_ROOT/'methods_spec.json')
    inventory=read(repo_root/INPUT_ROOT/'asset_spec.json')
    references={r['label']:r for r in inventory['occurrences']}
    data=read(broad_output/'data/PAPER_DATASET.json')
    assets={}
    generator='scripts/split-inference/publication_mlsys.py:build_methods'
    def register(label,stem,headers,display,records,inputs,uids,generation):
        reference=references[label]
        outputs=description_table(output,stem,label,reference['reference_caption'],headers,display,records)
        assets[label]={'reference_file':reference['tex_path'], 'outputs':outputs,
                       'input_uids':sorted(uids), 'input_files':inputs,
                       'data_generation':generation, 'generator':generator,
                       'verification':'Source specification for methods; independently counted original rows for cohort/model inventories.'}
    for label,item in spec.items():
        rows=[[str(v).replace(r'Section~\ref{sec:supp-energy}', 'the separate historical energy study')
               for v in row] for row in item['rows']]
        register(label,item['stem'],item['headers'],rows,None,
                 [str(INPUT_ROOT/'methods_spec.json')],[],'R22 recorded methods specification')
    models=read(broad_output/'data/analysis_config.json')['model_order']
    native=[r for r in data if r['kind']=='split' and r['runner']=='native']
    generic=[r for r in data if r['kind']=='split' and r['runner']=='generic']
    identity=lambda r:(r['model_id'],r['setup_id'],r['backend'],r['case_id'])
    pairs={identity(r) for r in native}&{identity(r) for r in generic}
    counts={'models':len({r['model_id'] for r in data}), 'physical_setups':len({r['physical_host'] for r in data}),
            'native_splits':len(native),'generic_splits':len(generic),
            'full_alternatives':sum(r['kind']=='full' for r in data),'configurations':len(data),
            'paired_cuts':len(pairs),'model_setup_groups':len({(r['model_id'],r['setup_id']) for r in native})}
    display=[['Models / physical setups',f'{counts["models"]} / {counts["physical_setups"]}'],
             ['Native splits / Generic splits',f'{counts["native_splits"]} / {counts["generic_splits"]}'],
             ['Full alternatives',counts['full_alternatives']], ['Deployment configurations',counts['configurations']],
             ['Paired Native/Generic cuts',counts['paired_cuts']], ['Model/setup groups',counts['model_setup_groups']]]
    register('tab:cohorts','cohorts',['Quantity','Count'],display,
             [{'quantity':k,'count':v} for k,v in counts.items()],['results/split-inference/data/PAPER_DATASET.json'],
             [r['uid'] for r in data],'deepx_native_a4_20261015')
    graph_path='results/supplementary-studies/mlsys-selection-20261007/inputs/analysis/evidence/inputs/graph_features.csv'
    graph=csv_rows(repo_root/graph_path)
    assert len({(r['model_id'],r['case_id']) for r in graph})==len(graph), 'Duplicate graph boundary'
    labels={'mobilenet_v3_large':'MobileNetV3-Large','regnet_x_1_6gf':'RegNetX-1.6GF',
            'resnet50':'ResNet-50','yolo11l':'YOLO11l','yolo26m':'YOLO26m',
            'yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}
    model_rows=[]
    for model in models:
        by_setup=collections.Counter(r['setup_id'] for r in native if r['model_id']==model)
        assert len(set(by_setup.values()))==1, ('Unequal model/setup coverage needs explicit presentation',model)
        model_rows.append({'model':model,'graph_cuts':sum(r['model_id']==model for r in graph),
                           'native_splits_per_setup':next(iter(by_setup.values())), 'native_counts_by_setup':dict(by_setup)})
    display=[[labels.get(r['model'],r['model']),r['graph_cuts'],r['native_splits_per_setup']] for r in model_rows]
    display += [['Total',sum(r['graph_cuts'] for r in model_rows),sum(r['native_splits_per_setup'] for r in model_rows)]]
    register('tab:models','models',['Model','Graph cuts','Native splits/setup'],display,model_rows,
             [graph_path,'results/split-inference/data/PAPER_DATASET.json'],[r['uid'] for r in native],
             'Historical graph inventory; current A4 measured Native identities')
    return assets


def historical_window_check(repo_root, broad_output, output):
    """Adapt the R21 check to canonical inputs; never mix mean(N/T) with FPS medians."""
    repeat_path='results/supplementary-studies/mlsys-selection-20261007/inputs/analysis/best_cases_inputs/energy_repeats.csv'
    cases_path='results/supplementary-studies/thesis20-ranking-20261005/source/deep_analysis/tables/energy_cases.csv'
    repeats=csv_rows(repo_root/repeat_path);cases=csv_rows(repo_root/cases_path)
    def summarize(row):
        rr=[r for r in repeats if r['case_uid']==row['case_uid']]
        assert len(rr)==3
        for r in rr:
            assert math.isclose(float(r['recomputed_j_per_task']),float(r['energy_j'])/float(r['completed_count']),rel_tol=1e-12)
        return {'uid':row['case_uid'], 'fps':statistics.mean(float(r['completed_count'])/float(r['active_duration_s']) for r in rr),
                'energy_mj':1000*statistics.mean(float(r['recomputed_j_per_task']) for r in rr),
                'rate_basis':'mean of per-energy-window completed_count / duration'}
    fulls=[r for r in cases if r['model_id']=='yolo11l' and r['case_id']=='full']
    allowed=[summarize(r) for r in fulls if float(r['quality_relative_loss'])<=.05]
    old_full=min(allowed,key=lambda r:(-r['fps'],r['uid']))
    old_split=summarize(next(r for r in cases if r['model_id']=='yolo11l' and r['setup_id']=='H10' and r['case_id']=='b062'))
    current={r['uid']:r for r in read(broad_output/'data/PAPER_DATASET.json')}
    chosen=['native|yolo11l|H10|hailo10h_to_trt|b062','native|yolo11l|DeepX|native_full_deepx|full']
    now=[{'uid':u,'fps':current[u]['fps'],'energy_mj':current[u]['energy_mj_per_image'],
          'rate_basis':'independent performance cohort median'} for u in chosen]
    result={'historical_same_window':{'split':old_split,'full':old_full,'full_candidates':len(fulls),
                                    'quality_admissible_fulls':len(allowed),
                                    'throughput_gain_pct':100*(old_split['fps']/old_full['fps']-1),
                                    'energy_change_pct':100*(old_split['energy_mj']/old_full['energy_mj']-1)},
            'current_deployment_candidate_check':{'split':now[0],'full':now[1],
                                                'full_still_faster_and_lower_energy':now[0]['fps']<now[1]['fps'] and now[0]['energy_mj']>now[1]['energy_mj']},
            'input_files':[repeat_path,cases_path,'results/split-inference/data/PAPER_DATASET.json'],
            'source_mapping':'Canonical historical energy_cases.csv differs from the R22 copy only in its final line ending; CSV records are identical.',
            'scope':'Historical energy-window rates and current performance medians remain separate cohorts.'}
    write(output/'data/historical_yolo11l_windows.json',result)
    return result


def asset_manifest(repo_root, output, assets, figure_index):
    spec=read(repo_root/INPUT_ROOT/'asset_spec.json')
    for figure in figure_index:
        name=figure['name']
        label=figure['label']
        formats=figure['formats']+figure.get('data_formats',[])
        assert label not in assets, ('Duplicate asset label',label)
        assets[label]={'outputs':['figures/'+name+'.'+fmt for fmt in formats],
                       'caption':figure['caption'],
                       'input_uids':figure.get('input_uids',[]),
                       'input_files':figure.get('input_files',[]),
                       'data_generation':figure['data_generation'],
                       'generator':'scripts/split-inference/publication_mlsys_figures.py',
                       'verification':'Exact plotted coordinates and UID/source checks; deterministic PDF/SVG/PNG byte comparison; source specification for conceptual schematic.'}
    occurrences=spec['occurrences']
    required={r['label'] for r in occurrences}
    assert required==set(assets), ('Incomplete R22 asset coverage',sorted(required-set(assets)),sorted(set(assets)-required))
    manifest=[]
    for label in dict.fromkeys(r['label'] for r in occurrences):
        uses=[r for r in occurrences if r['label']==label]
        entry=dict(assets[label],asset_id=label,kind=uses[0]['kind'],
                   description=uses[0]['description'],occurrences=uses,
                   reference_archive=spec['reference_archive'],reference_sha256=spec['reference_sha256'])
        entry['reference_file']=uses[0]['tex_path']
        entry['repo_targets']=['results/split-inference/'+str(OUTPUT_ROOT/p) for p in entry['outputs']]
        assert entry['generator'] and entry['data_generation'] and entry['verification']
        manifest.append(entry)
    result={'profile':PROFILE,'reference_archive':spec['reference_archive'],
            'reference_sha256':spec['reference_sha256'],'reference_commit':spec['audit_commit'],
            'occurrence_count':len(occurrences),'unique_asset_count':len(manifest),
            'figure_count':sum(a['kind']=='figure' for a in manifest),
            'table_count':sum(a['kind']=='table' for a in manifest),'assets':manifest}
    write(output/'ASSET_MANIFEST.json',result)
    return result


def profile_documentation(output, manifest):
    assets=manifest['assets']
    intro=('This registered R22 profile is generated by the existing split-inference reproduction command. '
           'Its quality-filtered selection view uses numerical CPU-relative loss ≤5%; the broad 450-deployment '
           'analysis and its unfiltered Pareto views remain separate. Historical ranking, energy-window, '
           'stage-cost and scheduling studies retain their own cohorts.')
    lines=['# MLSys R22 publication assets','',intro,'',
           f'{manifest["unique_asset_count"]} unique assets ({manifest["figure_count"]} figures and {manifest["table_count"]} tables), '
           f'used in {manifest["occurrence_count"]} active main/supplement occurrences. The stage-cost table is computed once and used in both documents.','',
           '[Asset manifest](ASSET_MANIFEST.json) · [Reference differences](REFERENCE_DIFFERENCES.md) · '
           '[Tables](tables/README.md) · [Figure gallery](figures/README.md) · '
           '[Reproduction instructions](../../../../scripts/split-inference/README.md)','',
           '| R22 label | Reference document | Asset |','|---|---|---|']
    table_lines=['# R22 tables','',intro,'','| Table | Outputs |','|---|---|']
    figure_lines=['# R22 figure gallery','',intro,'']
    for asset in assets:
        paths=asset['outputs']
        docs=', '.join(dict.fromkeys(r['document'] for r in asset['occurrences']))
        primary=next((p for p in paths if p.endswith('.md')),next((p for p in paths if p.endswith('.pdf')),paths[0]))
        lines.append(f'| `{asset["asset_id"]}` | {docs} | [{asset["description"]}]({primary}) |')
        if asset['kind']=='table':
            links=' · '.join(f'[{Path(p).suffix[1:].upper()}]({Path(p).name})' for p in paths)
            table_lines.append(f'| {asset["description"]} | {links} |')
        else:
            png=next(p for p in paths if p.endswith('.png'))
            figure_lines += ['## '+asset['description'],'',f'![{asset["description"]}]({Path(png).name})','',
                            ' · '.join(f'[{Path(p).suffix[1:].upper()}]({Path(p).name})' for p in paths),'',
                            asset['caption'],'',
                            'R22 label: `'+asset['asset_id']+'`. Generation: '+asset['data_generation']+'.','']
    (output/'README.md').write_text('\n'.join(lines)+'\n')
    (output/'tables/README.md').write_text('\n'.join(table_lines)+'\n')
    (output/'figures/README.md').write_text('\n'.join(figure_lines)+'\n')
    differences='''# R22 reference differences

The reference manuscript remains unchanged. Numeric results are calculated from the repository inputs; paper PDF bytes are not used as regenerated-data targets.

| Output | Reference issue | Resolution and source |
|---|---|---|
| `vendor_quality_recovery_table` | The older THESIS20 generator uses DeepX MobileNet b027 quality 0.7222, producing 72.22% and +0.50 pp. The active R22 table already uses the current 0.7218. | Bind the new export to the current Native b027 and Full UIDs in `PAPER_DATASET`, yielding 72.18% and +0.46 pp. Check H8 and H10 likewise; retain the historical table in its original study. This corrects generator binding, not the active paper value. |
| `r21_winner_repeat_ranges` | R22 prints a dash for YOLO26s/H8 b021 split energy because its compact extract lacks three repeats. | The exact UID `native|yolo26s|H8|hailo8_to_trt|b021` has three source-bound `refresh16_20261013` energy repeats in the canonical energy-repeat export. The generated complete range is 157.56–157.72 mJ/image; its mean remains unchanged. These are original samples, not inferred confidence limits or new measurements. |

Paper-sized layouts, stable rendering metadata, standalone table labels and publication navigation are export adaptations. Numerical CSV/JSON values retain full precision, while paper display rounds FPS to integers and energy to mJ/image. Observed three-repeat ranges are minima/maxima, not confidence intervals. CPU-relative quality intervals are not paired split-minus-Full intervals.

The current source audit projections are verified offline from their compact published contents; optional reconstruction from the original large archives is a separate provenance check. Existing historical mean(N/T) energy-window rates are recomputed separately from current performance medians in `data/historical_yolo11l_windows.json`. No unresolved numerical reference differences were identified by the registered checks.
'''
    (output/'REFERENCE_DIFFERENCES.md').write_text(differences)


def build_profile(repo_root, broad_output, numeric_only=False):
    """One registered export, called by reproduce.py in both modes."""
    repo_root,broad_output=Path(repo_root),Path(broad_output)
    output=broad_output/OUTPUT_ROOT
    output.mkdir(parents=True,exist_ok=True)
    from publication_mlsys_data import build as build_data
    from publication_mlsys_evidence import build as build_evidence
    from publication_mlsys_figures import write_figure_data, render
    context=build_data(repo_root,broad_output,output)
    evidence=build_evidence(repo_root,broad_output,output)
    assets={}
    for group in [context['assets'],evidence['assets'],build_methods(repo_root,broad_output,output)]:
        assert not (assets.keys() & group.keys()), ('Duplicate table asset',assets.keys() & group.keys())
        assets.update(group)
    historical_window_check(repo_root,broad_output,output)
    figure_index,_=write_figure_data(output,context)
    if not numeric_only:
        render(output,context)
    manifest=asset_manifest(repo_root,output,assets,figure_index)
    profile_documentation(output,manifest)
    write(output/'data/profile_summary.json',{'profile':PROFILE,
          'reference_occurrences':manifest['occurrence_count'], 'unique_assets':manifest['unique_asset_count'],
          'figures':manifest['figure_count'],'tables':manifest['table_count'],
          'evidence':evidence['validation'],
          'scientific_scope':'Current broad data with a separate numerical 5% quality view; independent historical/scheduling/stage cohorts.'})
    return manifest
