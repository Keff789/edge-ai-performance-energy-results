#!/usr/bin/env python3
"""Render the Generic420 study in English and German using the central paper style."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
METHODS = ['boundary_size','weighted_default','global','task','device','task_device']
MAIN = METHODS[:3]
BUDGETS = [1,3,5]
LABELS = {
 'en': {
  'boundary_size':'Boundary size','weighted_default':'Standard weights','global':'Shared fitted weights',
  'task':'Fit by task','device':'Fit by accelerator','task_device':'Fit by task and accelerator',
  'classification':'Classifiers','detection':'Detectors','all':'All models','all_accelerators':'All accelerators',
  'x':'Number of cuts measured, $k$','y':'Mean Generic throughput loss (%)',
  'model':'Model','accelerator':'Accelerator','method':'Ranking','task_header':'Model class',
  'groups':'Groups','candidates':'Eligible cuts','k1':'1 cut','k3':'3 cuts','k5':'5 cuts','mean':'Mean at 1, 3, 5',
  'selected':'Selected','fps_measured':'FPS measured','analysis_eligible':'Quality eligible',
  'quality_fail_measured':'Quality failed','quality_pending_measured':'Quality open',
  'technical_excluded':'Technical exclusion','fps_pending':'FPS open','analysis_group_complete':'Resolved',
  'heldout':'Held-out model','train_models':'Training models','train_groups':'Training groups',
  'train_loss_pct':'Training loss (%)','w_comm':'Communication weight','w_imb':'Imbalance weight','w_ten':'Tensor weight',
  'yes':'Yes','no':'No','preliminary':'Preliminary snapshot',
 },
 'de': {
  'boundary_size':'Datenmenge am Cut','weighted_default':'Standardgewichte','global':'Gemeinsam gelernte Gewichte',
  'task':'Fit je Aufgabe','device':'Fit je Beschleuniger','task_device':'Fit je Aufgabe und Beschleuniger',
  'classification':'Klassifikatoren','detection':'Detektoren','all':'Alle Modelle','all_accelerators':'Alle Beschleuniger',
  'x':'Anzahl gemessener Cuts, $k$','y':'Mittlerer Generic-Durchsatzverlust (%)',
  'model':'Modell','accelerator':'Beschleuniger','method':'Rangfolge','task_header':'Modellklasse',
  'groups':'Gruppen','candidates':'Zulässige Cuts','k1':'1 Cut','k3':'3 Cuts','k5':'5 Cuts','mean':'Mittel bei 1, 3, 5',
  'selected':'Ausgewählt','fps_measured':'FPS gemessen','analysis_eligible':'Qualität zulässig',
  'quality_fail_measured':'Qualität verfehlt','quality_pending_measured':'Qualität offen',
  'technical_excluded':'Technisch ausgeschlossen','fps_pending':'FPS offen','analysis_group_complete':'Abgeschlossen',
  'heldout':'Testmodell','train_models':'Trainingsmodelle','train_groups':'Trainingsgruppen',
  'train_loss_pct':'Trainingsverlust (%)','w_comm':'Kommunikationsgewicht','w_imb':'Ungleichgewichtsgewicht','w_ten':'Tensorgewicht',
  'yes':'Ja','no':'Nein','preliminary':'Vorläufiger Zwischenstand',
 }
}
MODEL_LABELS = {'mobilenet_v3_large':'MobileNetV3-L','regnet_x_1_6gf':'RegNet-X','resnet50':'ResNet-50','yolo11l':'YOLO11l','yolo26m':'YOLO26m','yolo26s':'YOLO26s','yolov7_paper':'YOLOv7'}


def load_style(repo):
    path = repo/'scripts/split-inference/publication_mlsys_figures.py'
    spec=importlib.util.spec_from_file_location('rq3_central_style',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def esc(value):
    if str(value).startswith('$') and str(value).endswith('$'): return str(value)
    return str(value).replace('\\',r'\textbackslash{}').replace('&',r'\&').replace('%',r'\%').replace('_',r'\_').replace('#',r'\#')


def table(path, headers, rows, alignment=None, separators=()):
    """CSV has localized labels; numeric values are identical across languages."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(headers);writer.writerows(rows)
    tex=[r'\begin{tabular}{@{}'+(alignment or 'l'*len(headers))+'@{}}',r'\toprule',' & '.join(esc(h) for h in headers)+r' \\',r'\midrule']
    for idx,row in enumerate(rows):
        if idx in separators:tex.append(r'\midrule')
        tex.append(' & '.join(esc(v) for v in row)+r' \\')
    tex.extend([r'\bottomrule',r'\end{tabular}'])
    path.with_suffix('.tex').write_text('\n'.join(tex)+'\n',encoding='utf-8')


def pick(summary, task='all', device='all', scope='all_available'):
    return summary[(summary.task==task)&(summary.accelerator==device)&(summary.group_scope==scope)]


def values(summary,method):
    return [float(summary[(summary.method==method)&(summary.k==k)].mean_loss_pct.iloc[0]) for k in BUDGETS]


def plot_curves(summary,out,lang,profile,single=False):
    import matplotlib.pyplot as plt
    t=LABELS[lang];plt.rcParams.update(profile.PAPER_STYLE)
    plt.rcParams['svg.hashsalt']='rq3-generic420'
    colors=[profile.PAPER_PALETTE[k] for k in ['blue','orange','green']]
    fig,axes=plt.subplots(2 if single else 1,1 if single else 2,figsize=(3.35,4.6) if single else (6.9,2.9),sharex=True,sharey=True)
    axes=np.ravel(axes)
    for ax,task in zip(axes,['classification','detection']):
        data=pick(summary,task)
        for method,color,marker in zip(MAIN,colors,['o','s','^']):
            ax.plot(BUDGETS,values(data,method),color=color,marker=marker,lw=1.4,ms=4,label=t[method])
        # Panel identifiers, not embedded figure titles; scientific claims live in LaTeX captions.
        ax.text(.97,.97,t[task],ha='right',va='top',transform=ax.transAxes,fontsize=9)
        ax.set_xticks(BUDGETS);ax.set_xlim(.8,5.2);ax.set_ylim(bottom=0)
        ax.grid(axis='y',color='#dddddd',linewidth=.45,zorder=0)
        if not single:ax.set_xlabel(t['x'])
    ymax=max(max(values(pick(summary,task),m)) for task in ['classification','detection'] for m in MAIN)
    for ax in axes: ax.set_ylim(0,ymax*1.15)
    if single:axes[-1].set_xlabel(t['x'])
    fig.supylabel(t['y'],x=.015,fontsize=8.5)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',ncol=1 if single else 3,frameon=False,bbox_to_anchor=(.54,1.0),fontsize=7.5)
    fig.subplots_adjust(left=.18 if single else .10,right=.98,bottom=.10 if single else .19,top=.83 if single else .82,hspace=.20,wspace=.16)
    save_figure(fig,out/('shortlist_loss_single_column' if single else 'shortlist_loss'));plt.close(fig)


def plot_scopes(summary,out,lang,profile):
    import matplotlib.pyplot as plt
    t=LABELS[lang];plt.rcParams.update(profile.PAPER_STYLE)
    colors=[profile.PAPER_PALETTE[k] for k in ['blue','orange','green','purple','yellow','dark_gray']]
    fig,axes=plt.subplots(1,3,figsize=(6.9,2.65),sharey=True,sharex=True)
    xmax=max(values(pick(summary,task),m)[2] for task in ['all','classification','detection'] for m in METHODS)*1.22+1
    for ax,task in zip(axes,['all','classification','detection']):
        s=pick(summary,task);ys=np.arange(len(METHODS))
        vals=[values(s,m)[2] for m in METHODS]
        ax.barh(ys,vals,color=colors,height=.64,zorder=3)
        for y,v in zip(ys,vals):ax.text(v+.25,y,f'{v:.2f}',va='center',fontsize=7)
        ax.set_yticks(ys,[t[m] for m in METHODS]);ax.invert_yaxis();ax.set_xlim(0,xmax)
        ax.text(.97,.99,t[task],ha='right',va='top',transform=ax.transAxes,fontsize=8.5)
        ax.grid(axis='x',color='#dddddd',lw=.45,zorder=0)
    fig.supxlabel(t['y']+' ($k=5$)',fontsize=8.5)
    fig.subplots_adjust(left=.28 if lang=='de' else .22,right=.98,bottom=.19,top=.92,wspace=.27)
    save_figure(fig,out/'fit_scopes_k5');plt.close(fig)


def save_figure(fig,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ['pdf','svg','png']:
        kwargs={'dpi':220} if ext=='png' else {}
        metadata={'Creator':'Results artifact tool: rq3-generic420'}
        if ext=='pdf':metadata.update(CreationDate=None,ModDate=None)
        if ext=='svg':metadata.update(Date=None)
        saved=path.with_suffix('.'+ext)
        fig.savefig(saved,metadata=metadata,**kwargs)
        if ext=='svg':
            # Matplotlib emits trailing indentation inside multiline path data.
            # Canonicalize whitespace for clean Git diffs without changing geometry.
            saved.write_text('\n'.join(line.rstrip() for line in saved.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')


def captions(lang, counts):
    if lang=='en':
        return {
         'shortlist_loss':f"Graph-based selection against measured Generic throughput. Curves show the mean throughput loss after measuring the first $k$ ranked cuts and retaining the fastest, for classifiers and detectors separately. A budget of 1, 3, or 5 means that many cuts are measured, not that many models are held out. Groups with fewer candidates use all available cuts. The shared score is trained on the other models, excluding the test model on all accelerators. One ranking per test model is evaluated at all three budgets. The training objective averages losses at 1, 3, and 5 cuts. Groups contribute equally. Available conditional snapshot: {counts['eligible']} quality-eligible cuts in {counts['nonempty_eligible_groups']} model--accelerator groups. Measured quality failures ({counts['quality_fail_measured']}) and pending quality decisions ({counts['quality_pending_measured']}) are excluded; pending decisions keep the quality universe incomplete.",
         'fit_scopes_k5':"Mean Generic throughput loss with a budget of five cuts. Shared weights are compared with separate fits by task, accelerator, or their combination. Every fit holds out the complete test model on all accelerators and is trained on the mean loss at budgets 1, 3, and 5. Values describe the available quality-eligible snapshot, not new Native measurements."
        }
    return {
     'shortlist_loss':f"Graphbasierte Auswahl anhand des gemessenen Generic-Durchsatzes. Die Kurven zeigen den mittleren Durchsatzverlust, nachdem die ersten $k$ Cuts einer Rangfolge gemessen und der schnellste ausgewählt wurden. Klassifikatoren und Detektoren werden getrennt ausgewertet. Ein Budget von 1, 3 oder 5 bezeichnet die Zahl gemessener Cuts, nicht die Zahl zurückgehaltener Modelle. Bei weniger Kandidaten werden alle verfügbaren Cuts verwendet. Der gemeinsame Score wird auf den anderen Modellen trainiert; das Testmodell ist auf allen Beschleunigern ausgeschlossen. Dieselbe Rangfolge wird für alle drei Budgets ausgewertet. Das Trainingsziel mittelt die Verluste bei 1, 3 und 5 Cuts. Jede Gruppe erhält das gleiche Gewicht. Verfügbarer bedingter Zwischenstand: {counts['eligible']} qualitätszulässige Cuts in {counts['nonempty_eligible_groups']} Modell--Beschleuniger-Gruppen. Gemessene Qualitätsfehler ({counts['quality_fail_measured']}) und offene Qualitätsentscheidungen ({counts['quality_pending_measured']}) werden ausgeschlossen; bei offenen Entscheidungen bleibt die Qualitätsmenge unvollständig.",
     'fit_scopes_k5':"Mittlerer Generic-Durchsatzverlust bei einem Budget von fünf Cuts. Gemeinsame Gewichte werden mit getrennten Fits je Aufgabe, Beschleuniger und deren Kombination verglichen. In jedem Fit ist das gesamte Testmodell auf allen Beschleunigern ausgeschlossen. Das Trainingsziel mittelt die Verluste bei 1, 3 und 5 Cuts. Die Werte beschreiben den verfügbaren qualitätszulässigen Zwischenstand und sind keine neuen Native-Messungen."
    }


def render(study, output, *, repo=REPO, languages=('en','de'), numeric_only=False):
    study=Path(study);output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('Use a fresh artifact output directory')
    summary=pd.read_csv(study/'fit_results/primary/summary.csv')
    folds=pd.read_csv(study/'fit_results/primary/fold_weights.csv')
    full=pd.read_csv(study/'fit_results/primary/full_data_weights.csv')
    coverage=pd.read_csv(study/'inputs/coverage.csv')
    meta=json.loads((study/'inputs/feature_metadata.json').read_text());counts=meta['counts']
    output.mkdir(parents=True,exist_ok=True)
    payload={
      'schema':'generic420-publication-v1','status':meta.get('status','preliminary'),
      'counts':counts,'target':'measured quality-eligible Generic throughput',
      'budgets':BUDGETS,'training_budgets':BUDGETS,'main_methods':MAIN,
      'source_sha256':{str(p.relative_to(study)):sha(p) for p in [study/'inputs/candidates.csv',study/'fit_results/primary/summary.csv',study/'fit_results/primary/fold_weights.csv']},
      'curves':summary[(summary.accelerator=='all')&(summary.group_scope=='all_available')&summary.method.isin(MAIN)&summary.k.isin(BUDGETS)].to_dict(orient='records'),
      'figure_titles':False,'languages':list(languages),
    }
    (output/'FIGURE_DATA.json').write_text(json.dumps(payload,indent=2)+'\n')
    if not numeric_only:profile=load_style(Path(repo))
    for lang in languages:
        t=LABELS[lang];out=output/lang;tables=out/'tables';tables.mkdir(parents=True)
        for task in ['all','classification','detection']:
            s=pick(summary,task);rows=[]
            for method in METHODS:
                v=values(s,method);r=s[(s.method==method)&(s.k==1)].iloc[0]
                rows.append([t[method],int(r.groups),int(r.candidates),*[f'{x:.2f}' for x in v],f'{np.mean(v):.2f}'])
            table(tables/f'fit_scopes_{task}',[t['method'],t['groups'],t['candidates'],t['k1'],t['k3'],t['k5'],t['mean']],rows)
            compact_rows=[[t[m],*[f'{v:.2f}' for v in values(s,m)]] for m in METHODS]
            table(tables/f'fit_scopes_compact_{task}',[t['method'],t['k1'],t['k3'],t['k5']],compact_rows)
            if task=='all':
                main_rows=[[t[m],*[f'{v:.2f}' for v in values(s,m)]] for m in MAIN]
                table(tables/'paper_main_budget',[t['method'],t['k1'],t['k3'],t['k5']],main_rows,alignment='lrrr')
            for device in ['H8','H10','DeepX']:
                s=pick(summary,task,device)
                if s.empty:continue
                rows=[[t[m],*[f'{v:.2f}' for v in values(s,m)]] for m in METHODS]
                table(tables/f'fit_scopes_{task}_{device}',[t['method'],t['k1'],t['k3'],t['k5']],rows)
        rows=[]
        for task in ['all','classification','detection']:
            ss=pick(summary,task)
            n=int(ss[(ss.method=='global')&(ss.k==1)].groups.iloc[0])
            for i,method in enumerate(METHODS):
                v=values(ss,method)
                rows.append([f'{t[task]} ({n})' if i==0 else '',t[method],*[f'{x:.2f}' for x in v],f'{np.mean(v):.2f}'])
        table(tables/'paper_fit_scopes',[t['groups'],t['method'],t['k1'],t['k3'],t['k5'],t['mean']],rows,alignment='llrrrr',separators=(6,12))
        rows=[[MODEL_LABELS[r.test_model],f'{r.w_comm:.4f}',f'{r.w_imb:.4f}',f'{r.w_ten:.4f}'] for r in folds[folds.method=='global'].itertuples()]
        table(tables/'paper_shared_fold_weights',[t['heldout'],r'$w_{\rm comm}$',r'$w_{\rm imb}$',r'$w_{\rm ten}$'],rows,alignment='lrrr')
        # Full coverage table preserves empty eligible groups and open work.
        cs=['selected','fps_measured','analysis_eligible','quality_fail_measured','quality_pending_measured','technical_excluded','fps_pending']
        rows=[[MODEL_LABELS[r.model],r.accelerator,*[int(getattr(r,c)) for c in cs],t['yes'] if r.analysis_group_complete else t['no']] for r in coverage.itertuples()]
        table(tables/'coverage',[t['model'],t['accelerator'],*[t[c] for c in cs],t['analysis_group_complete']],rows)
        for method in ['global','task','device','task_device']:
            fs=folds[folds.method==method]
            rows=[[MODEL_LABELS.get(r.test_model,r.test_model),t.get(r.train_task,r.train_task),t['all_accelerators'] if r.train_accelerator=='all' else r.train_accelerator,
                   f'{r.w_comm:.4f}',f'{r.w_imb:.4f}',f'{r.w_ten:.4f}',int(r.train_groups),f'{r.train_loss_pct:.2f}'] for r in fs.itertuples()]
            table(tables/f'fold_weights_{method}',[t['heldout'],t['task_header'],t['accelerator'],r'$w_C$',r'$w_I$',r'$w_T$',t['train_groups'],t['train_loss_pct']],rows)
        rows=[[t[r.method],t.get(r.task,r.task),t['all_accelerators'] if r.accelerator=='all' else r.accelerator,f'{r.w_comm:.4f}',f'{r.w_imb:.4f}',f'{r.w_ten:.4f}',f'{r.train_loss_pct:.2f}'] for r in full.itertuples()]
        table(tables/'full_data_weights_descriptive',[t['method'],t['task_header'],t['accelerator'],r'$w_C$',r'$w_I$',r'$w_T$',t['train_loss_pct']],rows)
        for variant in ['coarse_grid','budget5_fit','family_holdout','tie_secondary_bytes']:
            source=study/'fit_results'/variant/'summary.csv'
            if not source.exists():continue
            variant_summary=pd.read_csv(source);rows=[]
            for task in ['all','classification','detection']:
                ss=pick(variant_summary,task)
                for method in METHODS:
                    rows.append([t[task],t[method],*[f'{v:.2f}' for v in values(ss,method)]])
            table(tables/('sensitivity_'+variant),[t['task_header'],t['method'],t['k1'],t['k3'],t['k5']],rows)
        caps=captions(lang,counts)
        (out/'captions.json').write_text(json.dumps(caps,indent=2,ensure_ascii=False)+'\n')
        lines=[]
        for name in ['shortlist_loss','shortlist_loss_single_column','fit_scopes_k5']:
            caption=caps['shortlist_loss' if name.startswith('shortlist_loss') else name]
            lines.extend(['% '+name,r'\begin{figure*}[t]' if name!='shortlist_loss_single_column' else r'\begin{figure}[t]',r'\centering',r'\includegraphics[width=\textwidth]{figures/'+name+'.pdf}' if name!='shortlist_loss_single_column' else r'\includegraphics[width=\columnwidth]{figures/'+name+'.pdf}',r'\caption{'+caption+'}',r'\label{fig:rq3-'+name.replace('_','-')+'}',r'\end{figure*}' if name!='shortlist_loss_single_column' else r'\end{figure}',''])
        (out/'figure_includes.tex').write_text('\n'.join(lines),encoding='utf-8')
        if not numeric_only:
            figures=out/'figures';figures.mkdir()
            plot_curves(summary,figures,lang,profile);plot_curves(summary,figures,lang,profile,single=True);plot_scopes(summary,figures,lang,profile)
    files=[p for p in output.rglob('*') if p.is_file()]
    manifest={'schema':'generic420-artifacts-v1','status':payload['status'],'counts':counts,'numeric_only':numeric_only,'files':{p.relative_to(output).as_posix():sha(p) for p in sorted(files)}}
    (output/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--repo',type=Path,default=REPO);ap.add_argument('--languages',nargs='+',choices=['en','de'],default=['en','de']);ap.add_argument('--numeric-only',action='store_true')
    a=ap.parse_args();manifest=render(a.study,a.out,repo=a.repo,languages=a.languages,numeric_only=a.numeric_only)
    print(json.dumps({'status':manifest['status'],'files':len(manifest['files']),'counts':manifest['counts']}))

if __name__=='__main__':main()
