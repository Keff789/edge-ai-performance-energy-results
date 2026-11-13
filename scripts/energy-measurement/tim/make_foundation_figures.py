#!/usr/bin/env python3
"""Self-contained journal foundation: tables and plots from existing summaries.

Uses the final native/all-15 definitions already selected by generate_results.py.
No new recordings, raw integrations, calibration fits or PSD estimates are made.
Each chart has one axes. Colours are the Matplotlib defaults; marker shapes and
line styles distinguish measurement paths. Exact quantiles remain in the CSVs.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from paths import ROOT, G, F, T


def finish(fig, name):
    fig.tight_layout(pad=0.6)
    fig.savefig(F/(name+'.pdf'), metadata={'CreationDate':None,'ModDate':None},
                bbox_inches='tight', pad_inches=0.03)
    fig.savefig(F/(name+'.png'), dpi=210, bbox_inches='tight', pad_inches=0.03)
    plt.close(fig)


def clean_axes(ax, grid_axis='x'):
    ax.tick_params(labelsize=9)
    ax.spines[['top','right']].set_visible(False)
    ax.grid(True, alpha=.18, axis=grid_axis)


def table_file(path, columns, header, lines):
    path.write_text('\\begin{tabular}{@{}'+columns+'@{}}\n\\toprule\n'+header+
                    ' \\\\\n\\midrule\n'+'\n'.join(lines)+'\n\\bottomrule\n\\end{tabular}\n',
                    encoding='utf-8')


def main():
    for d in (G,F,T): d.mkdir(exist_ok=True)
    native = pd.read_csv(G/'native_reconstruction.csv').sort_values('nominal_duration_s')
    expected = [.02,.05,.1,.2,.5,1.,2.,5.,10.]
    if not np.allclose(native.nominal_duration_s,expected):
        raise ValueError('Missing or unexpected native reconstruction intervals')
    def rate(value):
        if pd.isna(value): return r'---'
        return f'{value/1000:g} k' if value>=1000 else f'{value:g}'
    lines=[]
    for r in native.itertuples():
        duration=f'{1000*r.nominal_duration_s:g} ms' if r.nominal_duration_s<1 else f'{r.nominal_duration_s:g} s'
        lines.append(f'{duration} & {r.native_envelope_Q95_pct:.2f} & {rate(r.persistent_1pct_sps)} & {rate(r.persistent_0p5pct_sps)}'+r' \\')
    table_file(T/'jetson_reference.tex','lrrr',
               r'Interval & Error (\%) & $f_{\min,1\%}$ (S/s) & $f_{\min,0.5\%}$ (S/s)',lines)
    native.to_csv(G/'jetson_foundation_energy.csv',index=False)

    fig,ax=plt.subplots(figsize=(3.6,2.75))
    ax.plot(native.nominal_duration_s,native.native_envelope_Q95_pct,'o-',ms=4,lw=1.2,
            label='Fixed 2 kS/s')
    ax.axhline(1,ls='--',lw=.9,label='1% criterion')
    ax.axhline(.5,ls=':',lw=.9,label='0.5% criterion')
    ax.set_xscale('log');ax.set_yscale('log')
    ax.set_xlim(.015,13);ax.set_ylim(.32,16)
    ax.xaxis.set_major_locator(FixedLocator([.02,.1,1,10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{1000*x:g} ms' if x<1 else f'{x:g} s'))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_locator(FixedLocator([.5,1,2,5,10]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y,_:f'{y:g}'))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel('Integration interval',fontsize=9)
    ax.set_ylabel('Hierarchical Q95 energy error (%)',fontsize=9)
    ax.legend(loc='upper right',frameon=False,fontsize=8)
    clean_axes(ax);finish(fig,'jetson_rate_duration')

    fp=pd.read_csv(G/'fp16_energy.csv').sort_values('rate_sps')
    if fp.rate_sps.tolist()!=[50,85,2000] or not fp.n_offset_cases.eq(960).all():
        raise ValueError('Wrong all-15 energy cohort')
    fp[['rate_sps','native_pooled_Q95_pct','native_max_pct','n_offset_cases']].to_csv(G/'fp16_energy_plot.csv',index=False)
    fig,ax=plt.subplots(figsize=(3.55,2.85));x=np.arange(3)
    ax.plot(x-.075,fp.native_pooled_Q95_pct,'o',ms=5,label='Pooled Q95')
    ax.plot(x+.075,fp.native_max_pct,'s',ms=5,label='Largest observed error')
    ax.axhline(1,ls='--',lw=.9,label='1% criterion')
    ax.set_xticks(x,['50 S/s','85 S/s','2 kS/s']);ax.set_xlim(-.5,2.5)
    ax.set_ylim(.05,2);ax.set_yscale('log')
    ax.yaxis.set_major_locator(FixedLocator([.1,.5,1]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y,_:f'{y:g}'))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel('Evaluated reconstruction rate',fontsize=9)
    ax.set_ylabel('Absolute relative energy error (%)',fontsize=9)
    ax.legend(loc='lower left',fontsize=8,frameon=False)
    clean_axes(ax,'y');finish(fig,'fp16_energy_objective')

    coverage=pd.read_csv(G/'fp16_coverage.csv').sort_values('rate_sps')
    if coverage.rate_sps.tolist()!=[2000,125000,160000] or not coverage.n.eq(15).all():
        raise ValueError('Wrong FP16 spectral cohort')
    coverage.to_csv(G/'fp16_coverage_plot.csv',index=False)
    above=100-coverage.median_pct.to_numpy()
    low=100-coverage.q95_pct.to_numpy();high=100-coverage.q05_pct.to_numpy()
    fig,ax=plt.subplots(figsize=(3.55,2.85));x=np.arange(3)
    ax.errorbar(x,above,yerr=np.stack((above-low,high-above)),fmt='o',ms=5,capsize=3,
                label='Median and 5th–95th percentiles')
    ax.axhline(5,ls='--',lw=.9,label='95% coverage target')
    ax.axhline(1,ls=':',lw=.9,label='99% coverage target')
    ax.set_xticks(x,['2 kS/s','125 kS/s','160 kS/s']);ax.set_xlim(-.4,2.4)
    ax.set_yscale('log');ax.set_ylim(.3,250)
    ax.yaxis.set_major_locator(FixedLocator([.5,1,5,10,100]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y,_:f'{y:g}'))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel('Evaluated sampling rate',fontsize=9)
    ax.set_ylabel('Variance above Nyquist (%)',fontsize=9)
    for i in (1,2):
        ax.annotate(f'Q05 coverage\n{coverage.q05_pct.iloc[i]:.1f}%',(i,above[i]),
                    xytext=(-10,16),textcoords='offset points',ha='center',fontsize=8)
    ax.legend(loc='upper center',fontsize=7.5,frameon=False,bbox_to_anchor=(.5,1.24))
    clean_axes(ax,'y');finish(fig,'fp16_fluctuation_coverage')

    ids=['gemm_fp32','gemm_fp16','gemm_int8','yolo_fp32','yolo_fp16','yolo_int8','random_pattern_yolo']
    names=['GEMM-FP32','GEMM-FP16','GEMM-INT8','YOLO-FP32','YOLO-FP16','YOLO-INT8','Variable YOLO']
    devices=pd.read_csv(G/'paired_300s.csv')
    devices=devices[devices.platform.eq('Jetson')]
    if len(devices)!=21 or not devices.n.eq(15).all():
        raise ValueError('Wrong Jetson paired cohort')
    devices.to_csv(G/'jetson_paired_300s.csv',index=False)
    fig,ax=plt.subplots(figsize=(3.6,3.25))
    for sensor,label,marker,off in [('firmware','u.RECS','o',-.2),
                                  ('jetson','INA3221','s',0),
                                  ('shelly','Shelly (scaled AC)','^',.2)]:
        data=devices[devices.sensor.eq(sensor)].set_index('slug').loc[ids]
        ax.plot(data.P_median_pct,np.arange(7)+off,linestyle='none',marker=marker,ms=4.5,label=label)
    ax.axvline(0,ls=':',lw=.8);ax.axhline(5.5,ls=':',lw=.8)
    ax.set_xlim(-7.1,3.65);ax.set_ylim(6.6,-.75);ax.set_yticks(range(7),names)
    ax.set_xlabel('Median paired power difference (%)',fontsize=9)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.22),ncol=1,frameon=False,fontsize=8)
    clean_axes(ax);finish(fig,'jetson_deployed_meters')

    curves=pd.read_csv(G/'duration.csv');jet=curves[curves.platform.eq('Jetson')]
    if len(jet)!=70: raise ValueError('Wrong Jetson duration cohort')
    jet.to_csv(G/'jetson_duration.csv',index=False)
    fig,ax=plt.subplots(figsize=(3.6,2.75))
    for slug,name,marker in zip(ids,names,['o','s','^','v','D','P','X']):
        v=jet[jet.slug.eq(slug)].sort_values('requested_s')
        ax.plot(v.requested_s,v.relative_median_pct,linestyle='--' if slug=='random_pattern_yolo' else '-',
                marker=marker,ms=3,lw=1,label=name)
        # Default fill and line colour cycles advance once per workload.
        ax.fill_between(v.requested_s,v.relative_q05_pct,v.relative_q95_pct,alpha=.10)
    ax.set_xscale('log');ax.set_xlim(4,760)
    ax.xaxis.set_major_locator(FixedLocator([5,20,100,600]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:g}'))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel('Requested duration (s)',fontsize=9)
    ax.set_ylabel('Mean power relative to 600 s (%)',fontsize=9)
    ax.legend(loc='lower center',bbox_to_anchor=(.5,-.53),ncol=2,frameon=False,fontsize=7.6)
    clean_axes(ax);finish(fig,'jetson_duration')

    direct=pd.read_csv(G/'direct_rates.csv')
    lines=[]
    for platform in ['Jetson','Hailo']:
        v=direct[direct.platform.eq(platform)]
        lines.append(r'\multicolumn{4}{l}{\textit{'+platform+r'}} \\')
        if platform=='Jetson':
            slug_order=ids+['llm'];name_map=dict(zip(ids,names));name_map['llm']='Gemma3-12B'
        else:
            slug_order=['gemm','yolo','random_pattern_yolo','llm']
            name_map={'gemm':'GEMM','yolo':'YOLO','random_pattern_yolo':'Variable YOLO','llm':'LLM'}
        for slug in slug_order:
            row=v[v.slug.eq(slug)]
            if len(row)!=1: raise ValueError(f'Missing direct series: {platform}/{slug}')
            r=row.iloc[0]
            lines.append(f'{name_map[slug]} & {int(r.finite_runs)} & {r.max_cv_pct:.2f} & {r.max_group_displacement_pct:.2f}'+r' \\')
        if platform=='Jetson': lines.append(r'\midrule')
    table_file(T/'direct_repeatability.tex','lrrr',r'Workload & Runs & Max. CV (\%) & Max. shift (\%)',lines)
    print('Expanded nine-duration and direct-sweep tables; five foundation chart files generated.')

if __name__=='__main__': main()
