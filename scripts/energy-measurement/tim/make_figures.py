#!/usr/bin/env python3
"""Manuscript figures from generated summaries; no raw-signal processing.
One axes per chart. Matplotlib default colour cycle; shapes separate methods.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
from paths import ROOT, G, F
F.mkdir(exist_ok=True)


def finish(fig, name):
    fig.tight_layout(pad=.5)
    fig.savefig(F/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None},bbox_inches='tight',pad_inches=.025)
    fig.savefig(F/(name+'.png'),dpi=210,bbox_inches='tight',pad_inches=.025)
    plt.close(fig)


def labels(ax):
    ax.tick_params(labelsize=9)
    ax.grid(True,alpha=.18,axis='x')
    ax.spines[['top','right']].set_visible(False)


def main():
    med=pd.read_csv(G/'paired_300s.csv');h=med[med.platform.eq('Hailo')]
    order=['gemm','yolo','random_pattern_yolo']; wl=['GEMM','YOLO','Variable YOLO']
    fig,ax=plt.subplots(figsize=(3.55,2.35))
    for sensor,label,m,off in [('firmware','u.RECS','o',-.14),('hailo_rt','HailoRT','s',.14)]:
        v=h[h.sensor.eq(sensor)].set_index('slug').loc[order]
        y=np.arange(3)+off;ax.plot(v.P_median_pct,y,linestyle='none',marker=m,ms=5,label=label)
        for x,yy in zip(v.P_median_pct,y):ax.annotate(f'{x:+.2f}',(x,yy),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
    ax.axvline(0,lw=.8,ls=':');ax.set_xlim(-2.6,1.25);ax.set_ylim(2.5,-.7)
    ax.set_yticks(range(3),wl);ax.set_xlabel('Paired power difference (%)',fontsize=9)
    ax.legend(loc='upper center',bbox_to_anchor=(.52,1.15),ncol=2,frameon=False,fontsize=9)
    labels(ax);finish(fig,'hailo_dc_telemetry')
    fig,ax=plt.subplots(figsize=(3.55,2.35))
    v=h[h.sensor.eq('shelly')].set_index('slug').loc[order]
    ax.plot(v.P_median_pct,range(3),linestyle='none',marker='^',ms=6,label='Shelly (scaled AC)')
    for x,y in zip(v.P_median_pct,range(3)):ax.annotate(f'{x:+.1f}',(x,y),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
    ax.set_xlim(20,45);ax.set_ylim(2.5,-.7);ax.set_yticks(range(3),wl)
    ax.set_xlabel('Paired power difference (%)',fontsize=9)
    ax.legend(loc='upper center',bbox_to_anchor=(.52,1.15),frameon=False,fontsize=9)
    labels(ax);finish(fig,'hailo_ac_context')
    allpairs=pd.read_csv(G/'paired_summary.csv')
    fig,ax=plt.subplots(figsize=(3.55,2.55))
    for k,l,m in zip(order,wl,['o','s','^']):
        v=allpairs[allpairs.platform.eq('Hailo')&allpairs.slug.eq(k)&allpairs.sensor.eq('hailo_rt')].sort_values('requested_s')
        ax.plot(v.requested_s,v.P_median_pct,marker=m,ms=4,lw=1.1,label=l)
    ax.set_xscale('log');ax.set_xlim(4,760);ax.set_ylim(-4.3,.2)
    ax.xaxis.set_major_locator(FixedLocator([5,20,100,600]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    ax.xaxis.set_minor_formatter(NullFormatter());ax.set_xlabel('Requested duration (s)',fontsize=9);ax.set_ylabel('Median power difference (%)',fontsize=9)
    ax.legend(loc='lower right',frameon=False,fontsize=8);labels(ax);finish(fig,'hailort_duration')
    fig,ax=plt.subplots(figsize=(3.55,2.55));v=pd.read_csv(G/'hailo_variable_interval_comparison.csv').sort_values('requested_s')
    for col,l,m in [('P','Mean power','o'),('E','Energy','s'),('T','Interval span','^')]:
        ax.plot(v.requested_s,v[col+'_median_pct'],marker=m,lw=1.1,ms=4,label=l)
    ax.set_xscale('log');ax.set_xlim(4,760);ax.set_ylim(-12,4)
    ax.xaxis.set_major_locator(FixedLocator([5,20,100,600]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    ax.xaxis.set_minor_formatter(NullFormatter());ax.set_xlabel('Requested duration (s)',fontsize=9);ax.set_ylabel('Median paired difference (%)',fontsize=9)
    ax.legend(loc='lower right',frameon=False,fontsize=8);labels(ax);finish(fig,'hailo_variable_intervals')
    hs=pd.read_csv(G/'hailo_spectra.csv')
    fig,ax=plt.subplots(figsize=(3.6,2.35))
    for basis,l,m,off in [('active','Active variance','o',-.13),('excess','Positive excess','s',.13)]:
        v=hs[hs.basis.eq(basis)].set_index('workload_id').loc[['gemm','yolo']]
        mid=v.f99_median_hz.to_numpy()/1000;lo=v.f99_q05_hz.to_numpy()/1000;hi=v.f99_q95_hz.to_numpy()/1000
        ax.errorbar(mid,np.arange(2)+off,xerr=np.array([mid-lo,hi-mid]),fmt=m,ms=5,capsize=3,label=l)
    ax.axvline(77,ls=':',lw=1,label='Nominal 77-kHz band')
    ax.set_xscale('log');ax.set_xlim(20,135);ax.set_ylim(1.5,-.6)
    ax.set_yticks(range(2),['GEMM','YOLO']);ax.xaxis.set_major_locator(FixedLocator([25,50,77,100]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    ax.xaxis.set_minor_formatter(NullFormatter());ax.set_xlabel('Frequency enclosing 99% of variance (kHz)',fontsize=9)
    ax.legend(loc='upper center',bbox_to_anchor=(.50,1.35),ncol=1,frameon=False,fontsize=8)
    labels(ax);finish(fig,'hailo_spectral_tail')
    native=pd.read_csv(G/'native_spectral_comparison.csv')
    ids=['gemmfp32','gemmint8','yolofp32','yoloint8','gemma3-4b','resnet50'];native=native.set_index('workload_id').loc[ids]
    fig,ax=plt.subplots(figsize=(3.6,2.8));x=np.arange(6)
    ax.bar(x-.18,native.max_abs_cdf_difference_pp,width=.34,label='Full recorded band')
    ax.bar(x+.18,native.conditional_0_77khz_max_abs_cdf_difference_pp,width=.34,label='Normalised within 0–77 kHz')
    ax.set_xticks(x,['GEMM\nFP32','GEMM\nINT8','YOLO\nFP32','YOLO\nINT8','Gemma\n3-4B','ResNet\n50']);ax.set_ylabel('Maximum CDF difference (pp)',fontsize=9)
    ax.set_ylim(0,39);ax.legend(loc='upper left',frameon=False,fontsize=8);labels(ax);ax.grid(False,axis='x');finish(fig,'native_cdf')
    duration=pd.read_csv(G/'duration.csv');fig,ax=plt.subplots(figsize=(3.6,2.75))
    for k,l,m in zip(order,wl,['o','s','^']):
        v=duration[duration.platform.eq('Hailo')&duration.slug.eq(k)].sort_values('requested_s')
        md=v.relative_median_pct.to_numpy();err=np.array([md-v.relative_q05_pct.to_numpy(),v.relative_q95_pct.to_numpy()-md])
        ax.errorbar(v.requested_s,md,yerr=err,fmt=m+'-',lw=1,ms=3.4,capsize=2,elinewidth=.65,label=l)
    ax.set_xscale('log');ax.set_xlim(4,760);ax.xaxis.set_major_locator(FixedLocator([5,20,100,600]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    ax.xaxis.set_minor_formatter(NullFormatter());ax.set_xlabel('Requested duration (s)',fontsize=9);ax.set_ylabel('Mean power relative to 600 s (%)',fontsize=9)
    ax.legend(loc='lower right',frameon=False,fontsize=8);labels(ax);finish(fig,'hailo_duration')
    pause=pd.read_csv(G/'pause_timing.csv');fig,ax=plt.subplots(figsize=(3.6,2.7))
    for p,l,m in [(20,'20-s pause','s'),(120,'120-s pause','o')]:
        v=pause[pause.pause_s.eq(p)];ax.plot(v['index'],v.trt_s,linestyle='none',marker=m,ms=6,label=l)
    ax.set_xticks(range(1,7));ax.set_xlim(.5,6.5);ax.set_ylim(92,112)
    ax.set_xlabel('Execution order (conditioning run excluded)',fontsize=9);ax.set_ylabel('Time for 100 queries (s)',fontsize=9)
    ax.legend(loc='upper left',frameon=False,fontsize=8);labels(ax);finish(fig,'pause_runtime')
    print('Created eight numeric charts (one axes each); boundary diagram retained from supplied TIM source.')

if __name__=='__main__':main()
