"""Journal-only plots and tables. Does not import or call the PARMA generator."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import csv
import math
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FixedLocator, NullFormatter, MaxNLocator
from scipy.integrate import trapezoid
from scipy.stats import spearmanr
from .journal_data import Curve, JournalConfig, BANDS, FINE_WINDOWS, safe_name, atomic_npz
from .journal_signal import metrics, cumulative, interval, integrate_band, shape_comparison
from .utils import write_csv, write_json, normalise_for_json


def hz(v, pos=None):
    if abs(v) >= 1e6: return f'{v/1e6:g} MHz'
    if abs(v) >= 1e3: return f'{v/1e3:g} kHz'
    return f'{v:g} Hz'


def fmt(v, digits=3):
    if v is None: return 'n/a'
    if isinstance(v, (float, np.floating)):
        return f'{v:.{digits}f}' if np.isfinite(v) else 'n/a'
    return str(v)


def _finite_values(rows, key):
    result = []
    for r in rows:
        try: value = float(r.get(key))
        except (ValueError, TypeError): continue
        if np.isfinite(value): result.append(value)
    return result


def metric_rows(curves: list[Curve], cfg: JournalConfig):
    rows = []
    for c in curves:
        m = metrics(c.f, c.p, cfg.bandwidth)
        r = {'key':c.key, 'workload_id':c.workload_id, 'label':c.label, 'platform':c.platform,
             'setup':c.setup, 'signal':c.signal, 'basis':c.basis, 'window':c.window,
             'physical_runs':c.meta.get('physical_runs'), 'active_duration_s':c.meta.get('active_duration_s'),
             'measurement_boundary':c.meta.get('measurement_boundary', 'unspecified'),
             'precision':c.meta.get('precision', 'unspecified'),
             'variance_integral':m['variance_integral'],
             'variance_unit':'A2' if c.signal == 'current' else 'W2',
             'curve_statistic':'metrics_of_pointwise_median_PSD',
             'below_nominal_bandwidth_pct':m['below_nominal_bandwidth_pct'],
             'above_nominal_bandwidth_pct':m['above_nominal_bandwidth_pct'],
             'status':m['status']}
        for q in [50, 90, 95, 99]:
            r[f'f{q}_curve_hz'] = m[f'f{q}_hz']
            values = _finite_values(c.per_run, f'f{q}_hz')
            for tag, fraction in [('median', .5), ('q05', .05), ('q95', .95)]:
                r[f'f{q}_{tag}_hz'] = float(np.quantile(values, fraction)) if values else None
        r['per_run_statistic'] = 'median_and_empirical_5_95_percentiles_not_confidence_interval' if c.per_run else 'unavailable'
        rows.append(r)
    return rows


def export_csv(path: Path, rows: list[dict], empty_fields=('status','reason')):
    fields = list(dict.fromkeys(k for r in rows for k in r)) or list(empty_fields)
    cooked = []
    for row in rows:
        row = normalise_for_json(row)
        cooked.append({k:(v if not isinstance(v, (list, dict)) else str(v)) for k, v in row.items()})
    write_csv(path, cooked, fieldnames=fields)


def latex_escape(value):
    s = fmt(value)
    replacements = {'\\':r'\textbackslash{}','_':r'\_','%':r'\%','&':r'\&','#':r'\#',
                    '$':r'\$','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(replacements.get(c,c) for c in s).replace('–','--').replace('−','-')


def table(root: Path, name: str, rows: list[dict], columns: list[tuple[str,str]], caption: str):
    root.mkdir(parents=True, exist_ok=True)
    # Full machine CSV and compact, explicit human tables.
    export_csv(root / f'{name}.csv', rows, [key for key, title in columns])
    md = [caption, '', '| ' + ' | '.join(title for key,title in columns) + ' |',
          '| ' + ' | '.join('---' for _ in columns) + ' |']
    for r in rows: md.append('| ' + ' | '.join(fmt(r.get(k)).replace('|','/') for k,t in columns) + ' |')
    if not rows: md += ['', 'No eligible observations available.']
    (root / f'{name}.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    tex=[]
    chunks=[rows[i:i+22] for i in range(0,len(rows),22)] or [[]]
    for part, chunk in enumerate(chunks,1):
        cap=caption+(f' Part {part}/{len(chunks)}.' if len(chunks)>1 else '')
        tex += [r'\begin{table}[tbp]',r'\centering',r'\small',
            r'\caption{'+latex_escape(cap)+'}',
            r'\label{tab:journal-'+name.replace('_','-')+f'-{part}'+'}',
            r'\begingroup',r'\setbox0=\hbox{%',r'\begin{tabular}{'+'l'*len(columns)+'}',r'\toprule',
            ' & '.join(latex_escape(t) for k,t in columns)+r' \\',r'\midrule']
        tex += [' & '.join(latex_escape(r.get(k)) for k,t in columns)+r' \\' for r in chunk]
        if not chunk:tex.append(r'\multicolumn{'+str(len(columns))+r'}{c}{No eligible observations} \\')
        tex += [r'\bottomrule',r'\end{tabular}}',r'\ifdim\wd0>\linewidth',
                r'\resizebox{\linewidth}{!}{\box0}',r'\else',r'\box0',r'\fi',
                r'\endgroup',r'\end{table}','']
    (root / f'{name}.tex').write_text('\n'.join(tex), encoding='utf-8')


def _indices(f, p, limit, logx=True):
    """Display/export thinning only: preserve local peaks and exact endpoints."""
    if len(f) <= limit: return np.arange(len(f))
    bins = max(10, limit // 4)
    if logx:
        positive = f[f > 0]
        edges = np.geomspace(positive[0], f[-1], bins + 1)
    else: edges = np.linspace(f[0], f[-1], bins+1)
    indexes = [0, len(f)-1]
    bounds = np.searchsorted(f, edges)
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        if hi <= lo: continue
        indexes.extend([int(lo), int(hi-1), int(lo + np.argmax(p[lo:hi])), int(lo + np.argmin(p[lo:hi]))])
    return np.unique(indexes)


def _new(title, ylabel, *, logx=True):
    fig, ax = plt.subplots(figsize=(9.5, 5.9))
    ax.set_title(title, fontsize=13, pad=12)
    ax.set_xlabel('Frequency')
    ax.set_ylabel(ylabel)
    if logx: ax.set_xscale('log')
    ax.xaxis.set_major_formatter(FuncFormatter(hz))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.grid(True, which='major', alpha=.35)
    ax.grid(True, which='minor', axis='x', alpha=.13)
    return fig, ax


def _save(fig, base, caption, index):
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, .09, 1, 1))
    fig.text(.5, .022, caption, ha='center', va='bottom', fontsize=8, wrap=True)
    with matplotlib.rc_context({'pdf.fonttype':42, 'ps.fonttype':42}):
        fig.savefig(base.with_suffix('.pdf'), bbox_inches='tight')
        fig.savefig(base.with_suffix('.png'), bbox_inches='tight', dpi=170)
    plt.close(fig)
    index.append({'figure': str(base), 'caption':caption})


def _mark_bandwidth(ax, cfg):
    ax.axvline(cfg.bandwidth, linestyle=':', linewidth=1.1)


def _curve_order(curves):
    # Rewind the property cycle between setup groups, so the default colors match
    # by workload without hard-coding colors or overriding a user's style.
    order = list(dict.fromkeys((c.platform, c.workload_id, c.window) for c in curves))
    return order, [(setup, [next((c for c in curves if (c.platform, c.workload_id, c.window) == wid and c.setup == setup), None)
                            for wid in order]) for setup in ['tek','pico']]


def spectral_plot(curves, cfg, base, index, *, kind='cdf', conditional=None, title=None):
    curves = [c for c in curves if float(trapezoid(c.p,c.f)) > 0]
    if not curves: return
    units = 'A' if curves[0].signal == 'current' else 'W'
    ylabel = ('Cumulative spectral variance [%]' if kind == 'cdf'
              else ('Normalised PSD [dB re 1/Hz]' if kind == 'normalised_psd' else f'PSD [dB re 1 {units}²/Hz]'))
    fig, ax = _new(title or '', ylabel)
    _, groups = _curve_order(curves)
    both = len({c.setup for c in curves}) > 1
    for setup, items in groups:
        ax.set_prop_cycle(None)
        for c in items:
            if c is None:
                # Maintain style cycle position for missing counterparts.
                ax.plot([],[]); continue
            f,p = c.f,c.p
            if conditional is not None: f,p = interval(f,p,float(f[0]),conditional)
            cc, total = cumulative(f,p)
            if total <= 0: continue
            if kind == 'cdf': y = cc * 100.
            else:
                density = p / total if kind == 'normalised_psd' else p
                floor = float(np.max(density)) * 1e-12
                y = 10. * np.log10(np.maximum(density, floor))
            idx = _indices(f,p,cfg.max_points)
            mask = f[idx] > 0
            label = c.label + (f' — {"Tek" if setup == "tek" else "Pico"}' if both else '')
            ax.plot(f[idx][mask], y[idx][mask], linestyle='-' if setup == 'tek' else '--', linewidth=1.4, label=label)
    if kind == 'cdf':
        ax.set_ylim(0,100)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}%'))
    maximum = conditional if conditional is not None else min(c.f[-1] for c in curves)
    ax.set_xlim(max(1., min(c.f[1] for c in curves)), maximum)
    if conditional is None: _mark_bandwidth(ax,cfg)
    ax.legend(fontsize=8, ncol=2 if len(curves) > 4 else 1, loc='best')
    note = ('Each curve is normalised ONLY within 0–' + hz(conditional) + '; not a passband validation.'
            if conditional is not None else f'Dotted line: {hz(cfg.bandwidth)} nominal analogue bandwidth, not a hard cutoff.')
    if kind != 'cdf': note += '\nDisplay floor: 120 dB below each curve peak; numerical metrics use unmodified densities.'
    note += '\nCurrent/power variance, not integrated energy. Solid: Tek; dashed: Pico.' if both else '\nCurves: pointwise median spectra; percentiles in tables are separately labelled.'
    _save(fig,base,note,index)


def difference_plot(pairs, cfg, base, index, signal, conditional=None):
    fig,ax = _new(f'Pico minus Tek cumulative distribution — {signal}', 'Cumulative difference [percentage points]')
    count=0
    for a,b in pairs:
        d=shape_comparison(a.f,a.p,b.f,b.p,conditional)
        if d['max_abs_difference_pp'] is None: continue
        f,y=d['frequency_hz'],d['difference_pp']; ii=_indices(f,y,cfg.max_points)
        ii=ii[f[ii]>0]
        ax.plot(f[ii],y[ii],label=a.label);count+=1
    if not count: plt.close(fig);return
    ax.axhline(0,linestyle=':',linewidth=1)
    ax.legend(fontsize=8,ncol=2)
    if conditional is None: _mark_bandwidth(ax,cfg)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g} pp'))
    _save(fig,base,'Positive: Pico places a larger fraction below this frequency. Normalisation differs between setups;\nthis is a shape difference, not a percent error in energy.',index)


def band_rows(curves, cfg):
    rows=[]
    for c in curves:
        total=float(trapezoid(c.p,c.f))
        for label,lo,hi in BANDS:
            if hi > c.f[-1] or lo < c.f[0]: continue
            val=integrate_band(c.f,c.p,lo,hi)
            rows.append({'key':c.key,'workload_id':c.workload_id,'label':c.label,'platform':c.platform,
                'setup':c.setup,'signal':c.signal,'basis':c.basis,'window':c.window,'band':label,
                'low_hz':lo,'high_hz':hi,'band_variance':val,'total_variance':total,
                'variance_share_pct':100*val/total if total>0 else None})
    return rows


def plot_bands(curves,cfg,base,index,title):
    curves=[c for c in curves if float(trapezoid(c.p,c.f))>0]
    if not curves: return
    fig,ax=plt.subplots(figsize=(max(9, .55*len(curves)+4),5.8))
    ax.set_title(title,fontsize=13)
    x=np.arange(len(curves));bottom=np.zeros(len(curves))
    for label,lo,hi in BANDS:
        heights=[]
        for c in curves:
            total=float(trapezoid(c.p,c.f))
            val=integrate_band(c.f,c.p,lo,hi) if hi<=c.f[-1] else 0.
            heights.append(100*val/total if total>0 else 0.)
        ax.bar(x,heights,bottom=bottom,label=label,width=.77)
        bottom+=np.asarray(heights)
    ax.set_xticks(x,[c.label + ('\n'+c.setup if len({r.setup for r in curves})>1 else '') for c in curves],rotation=30,ha='right')
    ax.set_ylim(0,100);ax.set_ylabel('Spectral variance share [%]')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}%'))
    ax.legend(fontsize=8,ncol=3,loc='upper center',bbox_to_anchor=(.5,1.18))
    _save(fig,base,'Shares integrate exact band edges on full-resolution spectra and use each setup\'s own total variance.\nThey are not fractions of consumed energy; the 77-kHz edge is not a digital cutoff.',index)


def _pairs(curves,signal,basis='excess'):
    result=[]
    for wid in dict.fromkeys(c.workload_id for c in curves):
        t=next((c for c in curves if c.workload_id==wid and c.setup=='tek' and c.signal==signal and c.basis==basis),None)
        p=next((c for c in curves if c.workload_id==wid and c.setup=='pico' and c.signal==signal and c.basis==basis),None)
        if t is not None and p is not None: result.append((t,p))
    return result


def comparison_rows(curves,cfg):
    rows=[]
    for signal in ['current','power']:
        for basis in ['active','excess']:
            for t,p in _pairs(curves,signal,basis):
                full=shape_comparison(t.f,t.p,p.f,p.p)
                conditional=shape_comparison(t.f,t.p,p.f,p.p,cfg.bandwidth)
                tm,pm=metrics(t.f,t.p,cfg.bandwidth),metrics(p.f,p.p,cfg.bandwidth)
                r={'workload_id':t.workload_id,'label':t.label,'signal':signal,'basis':basis,
                   'max_abs_cdf_difference_pp':full['max_abs_difference_pp'],
                   'conditional_0_77khz_max_abs_cdf_difference_pp':conditional['max_abs_difference_pp'],
                   'pico_to_tek_variance_ratio_db':full['pico_to_tek_variance_ratio_db'],
                   'ratio_interpretation':'ratio_of_PSD_integrals_not_a_transfer_function',
                   'tek_above_77khz_pct':tm['above_nominal_bandwidth_pct'],
                   'pico_above_77khz_pct':pm['above_nominal_bandwidth_pct'],
                   'independent_bandwidth_or_accuracy_validation':False}
                for q in [50,90,95,99]:
                    r[f'tek_f{q}_curve_hz']=tm[f'f{q}_hz'];r[f'pico_f{q}_curve_hz']=pm[f'f{q}_hz']
                    for c in [t,p]:
                        vals=_finite_values(c.per_run,f'f{q}_hz')
                        r[f'{c.setup}_f{q}_median_hz']=float(np.median(vals)) if vals else None
                rows.append(r)
    return rows


def ranking_rows(comparisons):
    rows=[]
    for signal in ['current','power']:
        for q in [50,90,95,99]:
            values=[r for r in comparisons if r['signal']==signal and r['basis']=='excess'
                    and r.get(f'tek_f{q}_median_hz') is not None and r.get(f'pico_f{q}_median_hz') is not None]
            a=[r[f'tek_f{q}_median_hz'] for r in values];b=[r[f'pico_f{q}_median_hz'] for r in values]
            valid=len(values)>=3 and len(set(a))>1 and len(set(b))>1
            rho=float(spearmanr(a,b).statistic) if valid else None
            rows.append({'signal':signal,'metric':f'f{q}','n_workloads':len(values),'spearman_rho':rho,
                         'tek_order_low_to_high':', '.join(r['label'] for r in sorted(values,key=lambda r:r[f'tek_f{q}_median_hz'])),
                         'pico_order_low_to_high':', '.join(r['label'] for r in sorted(values,key=lambda r:r[f'pico_f{q}_median_hz'])),
                         'status':'descriptive_small_sample_no_generalisation' if valid else 'insufficient_or_constant'})
    return rows


def export_curves(root, curves, cfg):
    root.mkdir(parents=True,exist_ok=True)
    for c in curves:
        cc,total=cumulative(c.f,c.p);ii=_indices(c.f,c.p,cfg.max_points)
        rows=[{'frequency_hz':float(c.f[i]), 'density':float(c.p[i]),
               'normalised_density_per_hz':float(c.p[i]/total) if total>0 else None,
               'cumulative_variance_pct':float(100*cc[i]) if total>0 else None} for i in ii]
        export_csv(root / f'{c.key}.csv',rows)
    (root/'README.md').write_text('These are display/review samples of native spectra, not raw time traces.\n'
        'Quantitative tables were calculated from ALL native frequency bins, not these thinned CSVs.\n'
        'Exact native NPZs stay in the original result/cache trees and are identified in the manifest.\n',encoding='utf-8')


def fine_structure(curves,cfg,root,index):
    if not cfg.data.get('fine_structure',True):return
    for label,lo,hi in FINE_WINDOWS:
        eligible=[c for c in curves if c.f[-1]>=hi and float(trapezoid(c.p,c.f))>0]
        if not eligible:continue
        fig,ax=_new(f'Tek / Pico current fine structure — {label}', 'Normalised variance density [% per kHz]',logx=False)
        _,groups=_curve_order(eligible)
        for setup,items in groups:
            ax.set_prop_cycle(None)
            for c in items:
                if c is None:ax.plot([],[]);continue
                f,p=interval(c.f,c.p,lo,hi);total=float(trapezoid(c.p,c.f))
                ii=_indices(f,p,cfg.max_points,False)
                ax.plot(f[ii],p[ii]/total*100000.,linestyle='-' if setup=='tek' else '--',label=c.label+' / '+setup,linewidth=1)
        ax.set_xlim(lo,hi);ax.ticklabel_format(axis='y',style='plain',useOffset=False)
        ax.legend(fontsize=7,ncol=2)
        _save(fig,root/f'tek_vs_pico_fine_{int(lo)}_{int(hi)}hz',
              'Both axes linear. Each PSD is normalised by its full-band total; no deconvolution.\nSolid: Tek; dashed: Pico. Frequency lines are descriptive, not assigned to hardware sources.',index)


def render_paired(curves,cfg,root):
    index=[];out=root/'figures';tables=root/'tables'
    mr=metric_rows(curves,cfg);br=band_rows(curves,cfg);cr=comparison_rows(curves,cfg);rr=ranking_rows(cr)
    export_csv(root/'data'/'all_spectral_metrics.csv',mr)
    export_csv(root/'data'/'frequency_band_metrics.csv',br)
    export_csv(root/'data'/'setup_comparison.csv',cr)
    export_csv(root/'data'/'rankings.csv',rr)
    export_curves(root/'data'/'curves',curves,cfg)
    for signal in ['current','power']:
        excess=[c for c in curves if c.signal==signal and c.basis=='excess']
        pico=[c for c in excess if c.setup=='pico']
        for kind,suffix in [('cdf','cumulative'),('normalised_psd','normalised_psd')]:
            spectral_plot(pico,cfg,out/f'pico_cross_workload_{signal}_{suffix}',index,kind=kind,
                          title=f'PicoScope 5 MS/s — {signal} spectral {"distribution" if kind=="cdf" else "shape"}')
            spectral_plot(excess,cfg,out/f'tek_vs_pico_{signal}_{suffix}_overlay',index,kind=kind,
                          title=f'Tektronix and PicoScope 5 MS/s — {signal}')
        spectral_plot(excess,cfg,out/f'tek_vs_pico_{signal}_conditional_cumulative_0_77khz',index,
                      conditional=cfg.bandwidth,title=f'Tek / Pico — {signal}, common low-band normalisation')
        difference_plot(_pairs(curves,signal),cfg,out/f'tek_vs_pico_{signal}_cumulative_difference',index,signal)
        plot_bands(pico,cfg,out/f'pico_{signal}_frequency_bands',index,f'PicoScope setup — {signal} frequency bands')
        for t,p in _pairs(curves,signal):
            wd=out/'per_workload'/safe_name(t.workload_id)
            spectral_plot([t,p],cfg,wd/f'{signal}_cumulative',index,title=t.label+' — Tek / Pico cumulative distribution')
            spectral_plot([t,p],cfg,wd/f'{signal}_absolute_psd',index,kind='absolute_psd',title=t.label+f' — absolute {signal} PSD')
    fine_structure([c for c in curves if c.signal=='current' and c.basis=='excess'],cfg,out/'fine_structure',index)
    compact=[]
    for r in mr:
        if r['basis']!='excess':continue
        compact.append(dict(r, f50=hz(r['f50_median_hz']) if r['f50_median_hz'] is not None else 'n/a',
            f95=hz(r['f95_median_hz']) if r['f95_median_hz'] is not None else 'n/a',
            f99=hz(r['f99_median_hz']) if r['f99_median_hz'] is not None else 'n/a'))
    table(tables,'table_tek_vs_pico_psd_metrics',compact,
          [('label','Workload'),('setup','Setup'),('signal','Signal'),('f50','f50'),('f95','f95'),('f99','f99'),('physical_runs','Runs')],
          'Per-physical-run percentile medians. Empirical 5–95% ranges and separate median-PSD curve metrics are in all_spectral_metrics.csv.')
    table(tables,'table_pico_usability_summary',cr,
          [('label','Workload'),('signal','Signal'),('basis','Basis'),('max_abs_cdf_difference_pp','Max CDF diff (pp)'),
           ('conditional_0_77khz_max_abs_cdf_difference_pp','Low-band CDF diff (pp)'),('pico_to_tek_variance_ratio_db','Pico/Tek variance (dB)')],
          'Descriptive setup agreement, not an absolute accuracy, coherence, or transfer-function test. Low band is separately normalised at the configured nominal bandwidth.')
    table(tables,'table_tek_vs_pico_frequency_bands',[r for r in br if r['basis']=='excess' and r['signal']=='current'],
          [('label','Workload'),('setup','Setup'),('band','Frequency band'),('variance_share_pct','Variance share (%)')],
          'Current excess-PSD band integrals normalised by each setup\'s full-band total. Not energy shares.')
    table(tables,'table_workload_ranking_stability',rr,[('signal','Signal'),('metric','Metric'),('n_workloads','Workloads'),('spearman_rho','Rank correlation')],
          'Descriptive Spearman rank agreement of per-run median frequency percentiles; no population significance claim.')
    # Explicit normalized and absolute differences in the automatic briefing.
    lines=['# PicoScope versus Tektronix spectral comparison','',
        'Both sources are native-rate PSDs of the same physical paired recordings. No target-rate low-pass or Common-Reference cache is used.',
        '',f'Nominal analogue marker: {hz(cfg.bandwidth)}. Digital Nyquist limit: {hz(cfg.rate/2)}. Neither is a claim of independent usable bandwidth.',
        '', '| Workload | Current CDF maximum difference | Conditional low-band difference | Pico/Tek current variance |',
        '|---|---:|---:|---:|']
    for r in cr:
        if r['signal']=='current' and r['basis']=='excess':
            lines.append(f"| {r['label']} | {fmt(r['max_abs_cdf_difference_pp'])} pp | {fmt(r['conditional_0_77khz_max_abs_cdf_difference_pp'])} pp | {fmt(r['pico_to_tek_variance_ratio_db'])} dB |")
    lines += ['', '## Interpretation limits', '',
        'A full-band CDF normalises every setup separately. Suppressed high-frequency variance can change its low-frequency percentages even when low-band shapes agree. The conditional comparison separates this denominator effect.',
        '', 'The 77-kHz marker does not truncate spectra. Content above it is retained; attenuation is not identical to absence of information. No deconvolution, transfer function, or synthetic coherence is inferred.',
        '', 'Active-minus-idle is a descriptive clipped spectral difference from independent records, not a causal source separation. Current and estimated-power PSDs are separate quantities.',
        '', 'No legacy PARMA figure, table, calibration, offset model, sampling result, or manuscript was changed.']
    (root/'PICO_VS_TEK_PSD_SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return index,mr


def render_platforms(jetson,hailo,cfg,root):
    index=[];mr=metric_rows(hailo,cfg)
    export_csv(root/'data'/'platform_spectral_metrics.csv',mr)
    export_curves(root/'data'/'curves',hailo,cfg)
    rows=[]
    for c in hailo:
        if c.basis!='active':continue
        rows.append({'platform':c.platform,'workload':c.label,'window':c.window,
            'n':c.meta.get('physical_runs'),'duration_s':c.meta.get('active_duration_s'),
            'precision':c.meta.get('precision'),'measurement_boundary':c.meta.get('measurement_boundary'),
            'status':c.meta.get('comparison_status')})
    table(root/'tables','table_cross_platform_inventory',rows,
          [('platform','Platform'),('workload','Workload'),('window','Window'),('n','Runs'),('duration_s','Duration (s)'),
           ('precision','Precision'),('measurement_boundary','Boundary')],
          'Pico power measurements. Unspecified precision or boundary is not inferred from directory names; platform comparisons remain exploratory.')
    full=[c for c in hailo if c.window=='full_record']
    for basis in ['active','excess']:
        h=[c for c in full if c.basis==basis]
        spectral_plot(h,cfg,root/'figures'/f'hailo_power_{basis}_cumulative',index,
                      title=f'Hailo — Pico power, {basis}, full active record')
        spectral_plot(h,cfg,root/'figures'/f'hailo_power_{basis}_psd',index,kind='normalised_psd',
                      title=f'Hailo — Pico power PSD, {basis}')
        j=[c for c in jetson if c.setup=='pico' and c.signal=='power' and c.basis==basis]
        # Prefix matching is shown only when actual upstream durations are known.
        matched_j=[c for c in j if c.meta.get('duration_min_s') is not None
                   and abs(c.meta['duration_min_s']-cfg.matched_duration)<=2/cfg.rate
                   and abs(c.meta['duration_max_s']-cfg.matched_duration)<=2/cfg.rate]
        matched_h=[c for c in hailo if c.window=='matched_prefix' and c.basis==basis]
        if j and h:
            spectral_plot(j+h,cfg,root/'figures'/f'jetson_vs_hailo_pico_power_{basis}_cumulative_exploratory',index,
                          title=f'Jetson / Hailo — Pico power, {basis}\nExploratory: different windows, boundaries or precision may apply')
            spectral_plot(j+h,cfg,root/'figures'/f'jetson_vs_hailo_pico_power_{basis}_conditional_0_77khz',index,
                          conditional=cfg.bandwidth,title=f'Jetson / Hailo — {basis}, conditional low-band shape\nExploratory; not a matched-platform performance comparison')
        if matched_j and matched_h:
            spectral_plot(matched_j+matched_h,cfg,root/'figures'/f'jetson_vs_hailo_pico_power_{basis}_matched_duration',index,
                          title=f'Jetson / Hailo — {cfg.matched_duration:g}-s power spectra\nDuration matched; workload, boundary and state matching still required')
    table(root/'tables','table_hailo_power_psd_metrics',mr,
          [('label','Workload'),('basis','Basis'),('window','Window'),('physical_runs','Runs'),
           ('f50_median_hz','f50 median (Hz)'),('f95_median_hz','f95 median (Hz)'),('f99_median_hz','f99 median (Hz)')],
          'Native power-spectrum percentiles; per-run medians, not percentiles of the aggregate curve. Active-only and idle-subtracted results remain separate.')
    (root/'CROSS_PLATFORM_PSD_SUMMARY.md').write_text(
        '# Cross-platform Pico PSD\n\n'+
        (f'{len(rows)} Hailo workload/window results available. See the inventory and metadata.\n' if rows else
         'No eligible Hailo power spectra are available yet. See the root input audit; no substitute data were generated.\n')+
        '\nLegacy oscilloscope.npy is treated as stored power only after rate, index, duration, shape, and energy-integral checks. '
        'It is not converted back to current, and the Jetson voltage model is never applied to it.\n\n'
        'The complete active interval and a first-duration-matched prefix are separate results. Longer recordings contribute more Welch averages, '
        'not more independent physical runs. Idle comes only from the same Hailo recording, never from Jetson. Missing idle stays active-only.\n\n'
        'The NPY energy comparison checks internal consistency, not instrument calibration. Unknown measurement boundaries, setup settings, host contributions, '
        'and precision remain explicit. A visually different spectrum alone is not proof of an accelerator architecture effect.\n',encoding='utf-8')
    return index,mr


def render_extra_setup_comparisons(curves,cfg,root):
    """Frequency-characteristic and observed PSD-ratio plots; no coherence inferred."""
    index=[];out=root/'figures';rows=[]
    comparisons=comparison_rows(curves,cfg)
    for signal in ['current','power']:
        group=[r for r in comparisons if r['signal']==signal and r['basis']=='excess']
        for q in [50,90,95,99]:
            eligible=[r for r in group if r.get(f'tek_f{q}_median_hz') is not None and r.get(f'pico_f{q}_median_hz') is not None]
            if not eligible:continue
            fig,ax=plt.subplots(figsize=(9.5,5.4))
            x=np.arange(len(eligible))
            ax.plot(x,[r[f'tek_f{q}_median_hz'] for r in eligible],marker='o',label='Tektronix setup')
            ax.plot(x,[r[f'pico_f{q}_median_hz'] for r in eligible],marker='s',linestyle='--',label='PicoScope/INA225 setup')
            ax.set_xticks(x,[r['label'] for r in eligible],rotation=20,ha='right')
            ax.set_yscale('log');ax.yaxis.set_major_formatter(FuncFormatter(hz));ax.yaxis.set_minor_formatter(NullFormatter())
            ax.set_ylabel(f'f{q} frequency');ax.set_title(f'Setup comparison of {signal} f{q}')
            ax.grid(True,which='major',alpha=.3);ax.legend()
            _save(fig,out/f'tek_vs_pico_{signal}_f{q}',
                  'Median of per-physical-run frequency percentiles, not the percentile of the plotted median PSD.\nConnecting lines identify setups; workload categories are not a continuous variable.',index)
        fig,ax=_new(f'Observed Pico/Tek {signal} PSD ratio','Band-integrated PSD ratio [dB]')
        plotted=False
        for t,p in _pairs(curves,signal,'excess'):
            low=max(float(t.f[1]),float(p.f[1]),1.);high=min(float(t.f[-1]),float(p.f[-1]))
            edges=np.r_[0.,np.geomspace(low,high,max(3,int(np.ceil(np.log10(high/low)*24))+1))]
            tot_t=float(trapezoid(t.p,t.f));tot_p=float(trapezoid(p.p,p.f))
            x,y=[],[]
            for a,b in zip(edges[:-1],edges[1:]):
                vt=integrate_band(t.f,t.p,a,b);vp=integrate_band(p.f,p.p,a,b)
                # Relative display relevance gate is not a calibrated noise floor.
                usable=tot_t>0 and tot_p>0 and vt>tot_t*1e-10 and vp>tot_p*1e-10
                db=float(10*np.log10(vp/vt)) if usable else None
                center=(a*b)**.5 if a>0 else b/2
                rows.append({'workload_id':t.workload_id,'label':t.label,'signal':signal,'basis':'excess',
                    'band_low_hz':a,'band_high_hz':b,'tek_band_variance':vt,'pico_band_variance':vp,
                    'pico_to_tek_ratio_db':db,'status':'reported' if usable else 'below_relative_relevance_gate',
                    'relative_gate_fraction':1e-10,'interpretation':'observed_ratio_not_transfer_function'})
                x.append(center);y.append(db if db is not None else np.nan)
            if np.any(np.isfinite(y)):
                ax.plot(x,y,label=t.label,linewidth=1.3);plotted=True
        if plotted:
            ax.axhline(0,linestyle=':',linewidth=1);_mark_bandwidth(ax,cfg)
            ax.legend(fontsize=8,ncol=2)
            _save(fig,out/f'tek_vs_pico_{signal}_observed_psd_ratio',
                'Ratio of absolute excess-variance integrals in logarithmic frequency bins; no per-curve normalisation.\nGaps fail a relative relevance gate, not a calibrated noise criterion. This is not a transfer function.',index)
        else:plt.close(fig)
    export_csv(root/'data'/'observed_psd_ratio_log_bins.csv',rows)
    return index
