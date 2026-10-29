#!/usr/bin/env python3
"""Export final English or German thesis assets from published measurements.

Only presentation changes. Existing RQ2/staged renderers are reused; no fitting,
quality reclassification, compilation or hardware acquisition is performed.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, shutil, subprocess, sys
from contextlib import nullcontext
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
DEFAULT_PUBLICATION=REPO/'results/publication-builds/generic420-20261027/paper'
DEFAULT_PAIRED=REPO/'results/supplementary-studies/rq2-native-scope-20261027'
DEFAULT_GENERIC=REPO/'results/supplementary-studies/rq3-generic420-detector-corrected-20261027'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def csvrows(p):
    with Path(p).open(newline='') as stream:return list(csv.DictReader(stream))

def table(caption,label,columns,header,rows,extra=''):
    return '\n'.join([r'\begin{table}[!htb]',r'\centering\small\setlength{\tabcolsep}{3pt}',r'\caption{'+caption+'}',r'\label{'+label+'}',extra,r'\begin{tabular}{@{}'+columns+r'@{}}',r'\toprule',header,r'\midrule',*rows,r'\bottomrule',r'\end{tabular}',r'\end{table}',''])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--publication',type=Path,default=DEFAULT_PUBLICATION)
    ap.add_argument('--paired-study',type=Path,default=DEFAULT_PAIRED)
    ap.add_argument('--generic-study',type=Path,default=DEFAULT_GENERIC)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--figure-profile',choices=['paper','dissertation'],default='dissertation')
    ap.add_argument('--language',choices=['en','de'],default='en')
    ap.add_argument('--figures-only',action='store_true',help='Omit the separately maintained thesis tables')
    args=ap.parse_args()
    if args.language == 'de' and not args.figures_only:
        ap.error('German selection export currently requires --figures-only; German thesis tables are maintained separately')
    if args.language == 'de' and args.figure_profile != 'dissertation':
        ap.error('German selection export requires the dissertation figure profile')
    from german_labels import GermanLabels
    labels=GermanLabels(decimal_comma=True) if args.language == 'de' else None
    with labels.active() if labels else nullcontext():
        export(args, labels)

def export(args, labels=None):
    out=args.output.resolve();pub=args.publication.resolve();paired=args.paired_study.resolve();generic=args.generic_study.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    for source in [pub,paired,generic]:
        if out==source or source in out.parents:raise ValueError('Output must be separate from input studies')
    figs=out/'figures';tabs=out/'tables';figs.mkdir(parents=True);tabs.mkdir()
    inputs={};artifacts=[]
    def source(p):
        p=Path(p);inputs[str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)]=sha(p);return p
    def copied(p,target):
        p=source(p);shutil.copy2(p,target);artifacts.append({'file':str(target.relative_to(out)),'source':str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p),'sha256':sha(target)})
    # Current publication figures, not the independent historical confirmation.
    p30=pub/'publications/mlsys-r30';jtab=p30/'tables'
    publication_figures=['fastest_split_baseline_comparison','fastest_deployment_tradeoff','yolov7_h8_case','resnet_h8_energy_current']
    if args.figure_profile == 'dissertation':
        renderer=load('thesis_deployment_figures',REPO/'scripts/split-inference/publication_mlsys_figures.py')
        figure_data=read(source(p30/'figures/FIGURE_DATA.json'))
        renderer.render(out,{},uniform_typography=True,uniform_palette=True,
                        figure_profile=args.figure_profile,figure_data=figure_data,
                        figure_names=publication_figures)
        if figure_data != read(p30/'figures/FIGURE_DATA.json'):
            raise AssertionError('Changed published deployment figure payload')
    else:
        for name in publication_figures:
            copied(p30/'figures'/f'{name}.pdf',figs/f'{name}.pdf')
    # Reuse the same trade-off renderer and exact points, with vertical thesis panels.
    gallery=load('thesis_model_gallery',REPO/'scripts/split-inference/render_figures.py')
    from publication_mlsys_figures import DISSERTATION_STYLE
    import matplotlib.pyplot as plt
    dataset=sorted(read(source(pub/'data/PAPER_DATASET.json')),key=lambda row:row['uid'])
    ids={row['uid']:row for row in dataset};gallery_payload={}
    def save_gallery(fig,name,caption,data,main=False):
        for ext in ['pdf','svg','png']:
            kw={'metadata':{'CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
            fig.savefig(figs/f'{name}.{ext}',dpi=180,**kw)
        plt.close(fig);gallery_payload[name]=data
    with plt.rc_context(DISSERTATION_STYLE):
        gallery.render_tradeoffs(pub,save_gallery,dataset,ids,sorted({r['model_id'] for r in dataset}),figure_profile=args.figure_profile,label_transform=labels.translate if labels else None)
    reference=read(source(pub/'figures/FIGURE_DATA.json'))
    for name,payload in gallery_payload.items():
        actual={k:v for k,v in payload.items() if k!='annotations'}
        expected={k:v for k,v in reference[name].items() if k!='annotations'}
        if actual!=expected:raise AssertionError('Gallery measurements changed: '+name)
    source(pub/'tables/PARETO_POINTS.json')
    (out/'GALLERY_DATA.json').write_text(json.dumps(gallery_payload,indent=2)+'\n')
    # The thesis reports this comparison in its numerical table, without the
    # redundant classifier/detector shortlist plot.
    work=out/'render_work';work.mkdir()
    weighted=work/'paired';shutil.copytree(paired,weighted)
    engine=load('thesis_current_rq2',REPO/'scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py')
    engine.render(weighted,False,figure_profile=args.figure_profile)
    unchanged=[]
    for p in paired.rglob('*'):
        q=weighted/p.relative_to(paired)
        if p.suffix in ('.csv','.json') and q.exists():
            if p.read_bytes()!=q.read_bytes():raise AssertionError('Changed RQ2 numerical payload: '+str(p.relative_to(paired)))
            unchanged.append(str(p.relative_to(paired)))
    for name in ['rq2_weighted_all_models','rq2_generic_selection_loss']:
        for ext in ['pdf','svg','png']:shutil.copy2(weighted/'figures'/f'{name}.{ext}',figs/f'{name}.{ext}')
    staged=work/'staged'
    subprocess.run([sys.executable,str(REPO/'scripts/supplementary-studies/staged-selection/reproduce.py'),'--paired-study',str(paired),'--graph-metadata',str(generic/'inputs/feature_metadata.json'),'--output',str(staged),'--languages',args.language,'--verify','--figure-profile',args.figure_profile],check=True)
    ref=REPO/'results/supplementary-studies/staged-selection'
    for rel in ['data/group_budgets.csv','data/summary.csv','data/summary.json','artifacts/en/figures/staged_selection_budget.csv','artifacts/en/figures/staged_selection_budget.json']:
        target_rel=rel.replace('artifacts/en/',f'artifacts/{args.language}/')
        if rel.endswith('.json'):
            expected,actual=read(ref/rel),read(staged/target_rel)
            if isinstance(expected,dict):expected.pop('language',None);actual.pop('language',None)
            if expected!=actual:raise AssertionError('Changed staged data: '+rel)
        elif (ref/rel).read_bytes()!=(staged/target_rel).read_bytes():raise AssertionError('Changed staged data: '+rel)
        unchanged.append('staged/'+rel)
    for name in ['staged_selection_flow','staged_selection_budget']:
        for ext in ['pdf','svg','png']:shutil.copy2(staged/f'artifacts/{args.language}/figures'/f'{name}.{ext}',figs/f'{name}.{ext}')
    data=read(source(pub/'data/PAPER_DATASET.json'))
    if not args.figures_only:
        shutil.copy2(staged/'artifacts/en/tables/primary_budget.tex',tabs/'staged_budget.tex')
        # Current thesis table layouts generated from final full-precision records.
        byuid={r['uid']:r for r in data}
        winners=read(source(jtab/'best_cases_table.json'))
        model_rows=[]
        for r in winners:
            split=r['split_setup'].replace('DeepX','DX')+'/'+r['split_case']+(r'$^{G}$' if r['split_runner']=='generic' else '')
            model_rows.append(' & '.join([r['label'],r['full_label'].replace('DeepX','DX'),f"{r['full_fps']:.0f}",split,f"{r['split_fps']:.0f}",f"{r['R_global']:.2f}",f"{r['full_mj']:.2f}",f"{r['split_mj']:.2f}"])+r' \\')
        caption=r'Fastest measured Full and split across all tested systems under the 5\% relative quality-loss rule. Superscript G identifies the Generic YOLO11l split; the other six use Native. Energy belongs to these exact throughput-selected configurations. Ratios use unrounded values.'
        (tabs/'global_winners.tex').write_text(table(caption,'tab:evaluation:global_winners','llrlrrrr',r'Model & Full & FPS & Split & FPS & $R_g$ & \shortstack{Full\\mJ/image} & \shortstack{Split\\mJ/image} \\',model_rows))
        qrows=[]
        for r in winners:
            cpu=100*byuid[r['split_uid']]['quality_reference_value']
            qrows.append(' & '.join([r['label'],f'{cpu:.2f}',f"{r['full_quality']:.2f}",f"{r['split_quality']:.2f}",f"{r['quality_difference_pp']:+.2f}"])+r' \\')
        (tabs/'quality.tex').write_text(table(r'Quality of the global throughput winners (\%). Classification uses Top1 and detection uses COCO AP$_{50:95}$. $\Delta q$ is Split minus Full in percentage points. The CPU reference is used for quality eligibility.','tab:review:quality','lrrrr',r'Model & CPU & Full & Split & $\Delta q$ (pp) \\',qrows))
        rows=read(source(jtab/'r14_quality_advantages.json'));body=[]
        for r in rows:
            eligibility=r['eligibility'].replace('<=',r'$\leq$').replace('≤',r'$\leq$').replace('%',r'\%')
            body.append(' & '.join([eligibility]+[str(r[k]) for k in ['native_candidates','admissible_fulls','faster_than_fastest_full','lower_energy_than_fastest_full','both_vs_fastest_full','lower_energy_than_minimum_full']])+r' \\')
        (tabs/'quality_tolerance.tex').write_text(table(r'Same-host Native advantages after filtering both splits and Full alternatives against the CPU quality reference. Each row reselects the fastest and lowest-energy admissible Full. Faster and Lower energy use the same fastest Full. Below min. Full uses the lowest-energy Full.','tab:evaluation:quality_tolerance','lrrrrrr',r'Eligibility & Native cuts & Fulls & Faster & Lower energy & Both & Below min. Full \\',body))
        ranges=read(source(jtab/'r21_winner_repeat_ranges.json'));body=[]
        for r in ranges:
            label=r['label'].replace('DeepX','DX')+(' (Generic)' if r['uid'].startswith('generic|') else '')
            body.append(f"{label} & {r['fps_min']:.0f}--{r['fps_max']:.0f} & {r['energy_min_mj_per_image']:.2f}--{r['energy_max_mj_per_image']:.2f} "+r'\\')
        (tabs/'repeat_ranges.tex').write_text(table(r'Observed minima and maxima over three repetitions for the global winners and additional YOLOv7 Full references. Performance and energy use separate runs. These are observed ranges, not confidence intervals for selected winners. FPS endpoints are rounded to integers.','tab:evaluation:repeat_ranges','lrr',r'Deployment & FPS & mJ/image \\',body))
        full=source(jtab/'full_performance_table.tex').read_text().replace(r'\begin{table*}[t]',r'\begin{table}[!htb]').replace(r'\end{table*}',r'\end{table}').replace(r'\textwidth',r'\linewidth').replace('tab:full-performance','tab:evaluation:full_overview')
        for backend in ['TRT','H8','H10','DeepX']:
            full=full.replace(backend+' FPS',r'\shortstack{'+backend+r'\\FPS}')
        (tabs/'full_overview.tex').write_text(full)
        fits=csvrows(source(generic/'artifacts/en/tables/fit_scopes_all.csv'))
        body=[' & '.join([r['Ranking'],r['1 cut'],r['3 cuts'],r['5 cuts']])+r' \\' for r in fits]
        (tabs/'generic_fit_scopes.tex').write_text(table(r'Mean Generic throughput loss (\%) on 331 quality-admissible cuts in 21 model--accelerator combinations. Every fitted ranking excludes the test model on all accelerators. Budgets count tested cuts per combination.','tab:evaluation:generic_graph_budget','lrrr',r'Ranking & 1 cut & 3 cuts & 5 cuts \\',body))
        copied(generic/'artifacts/en/tables/paper_shared_fold_weights.tex',tabs/'generic_shared_fold_weights.tex')
        copied(generic/'artifacts/en/tables/sensitivity_budget5_fit.tex',tabs/'generic_fit_sensitivity.tex')
        copied(generic/'artifacts/en/tables/paper_fit_scopes.tex',tabs/'generic_fit_scopes_by_task.tex')
        for name in ['generic_fit_scopes_by_task.tex']:
            p=tabs/name;p.write_text(p.read_text().replace('Groups & Ranking','Combinations & Ranking'))
    for rel in ['data/quality_pairs.csv','analysis/aggregate_curves.csv','analysis/complete_rankings.csv']:source(paired/rel)
    source(generic/'inputs/feature_metadata.json')
    for rel in ['scripts/dissertation/german_labels.py','scripts/dissertation/figure_terms.py','scripts/dissertation/locales/figures_de.json','scripts/dissertation/export_thesis_selection.py','scripts/split-inference/render_figures.py','scripts/split-inference/publication_mlsys_figures.py','scripts/supplementary-studies/staged-selection/reproduce.py','scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py']:source(REPO/rel)
    if labels:
        audit=labels.report()
        audit['figures']={str(Path(k).relative_to(out)):v for k,v in audit['figures'].items()}
        (out/'TRANSLATION_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
        if audit['untranslated']:raise AssertionError('Untranslated labels: '+repr(audit['untranslated']))
    energy=[r for r in data if isinstance(r.get('energy_mj_per_image'),(int,float))]
    validation={'status':'PASS','deployment_configurations':len(data),'energy_values':len(energy),'paired_cuts':len(csvrows(paired/'data/quality_pairs.csv')),'staged':read(staged/'VALIDATION.json'),'gallery_models':len(gallery_payload),'gallery_points':sum(len(v['points']) for v in gallery_payload.values()),'gallery_frontier_points':sum(len(g['front_uids']) for v in gallery_payload.values() for g in v['pareto_front']['groups']),'gallery_numeric_payloads_unchanged':True,'deployment_numeric_payload_unchanged':True,'unchanged_payload_count':len(unchanged),'unchanged_payloads':unchanged,'refitting':False,'hardware_measurements':False}
    if (len(data),len(energy),validation['paired_cuts'])!=(451,450,187):raise AssertionError(validation)
    (out/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    paths=[p for p in out.rglob('*') if p.is_file() and 'render_work' not in p.parts and p.name!='MANIFEST.json']
    manifest={'schema':'dissertation-selection-assets-v2','language':args.language,'repository_commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),'published_data_baseline':'aed301819663b5fa27bd5731fb74fef3e46ee927','figure_profile':args.figure_profile,'inputs':inputs,'generator_sha256':sha(Path(__file__)),'note':'Source commit identifies the published numeric data. Local generator changes affect presentation only. Historical confirmation assets are deliberately excluded.','files':{str(p.relative_to(out)):sha(p) for p in paths}}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'status':'PASS','output':str(out),'figures':len(list(figs.glob('*.pdf'))),'tables':len(list(tabs.glob('*.tex'))),'validation':{k:v for k,v in validation.items() if k!='unchanged_payloads'}},indent=2))

if __name__=='__main__':main()
