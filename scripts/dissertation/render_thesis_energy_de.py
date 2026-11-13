#!/usr/bin/env python3
"""German energy views from published summaries and per-execution exports.

The nine existing layouts do not fit, estimate spectra, re-integrate signals,
recompute statistics, or change a cohort. Existing English
PDFs are read only for the recorded canvas size and independent validation;
no PDF paths or text are reused as drawing input. JSON sidecars retain the exact
source rows and plotted values, including the original quantile bounds.

Two additional result fields normalize existing per-execution power/energy
exports to their published within-series references. They retain every selected
physical execution and do not reconstruct or re-integrate raw waveforms.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/split-inference'))
from publication_mlsys_figures import DISSERTATION_STYLE, DISSERTATION_PALETTE
TABLES = ROOT / 'results/energy-measurement/tables/tim'
FROZEN = ROOT / 'publications/dissertation/thesis-v56/en'
CURVES = ROOT / 'results/energy-measurement/data/spectra/pico_vs_tek_psd/data/curves'
NAMES = ('fp16_objectives', 'cross_workload_spectra', 'native_cdf',
         'hailo_spectral_tail', 'jetson_deployed_meters', 'hailo_meters',
         'hailo_variable_intervals', 'duration_comparison', 'pause_sequence')
JET_IDS = ['gemm_fp32','gemm_fp16','gemm_int8','yolo_fp32','yolo_fp16','yolo_int8','random_pattern_yolo']
JET_LABELS = ['GEMM-FP32','GEMM-FP16','GEMM-INT8','YOLO-FP32','YOLO-FP16','YOLO-INT8','YOLO variabel']
HAILO_IDS = ['gemm','yolo','random_pattern_yolo']
HAILO_LABELS = ['GEMM','YOLO','YOLO variabel']
SPECTRAL_IDS = ['gemmfp32','gemmint8','yolofp32','yoloint8','gemma3-4b','resnet50']
SPECTRAL_LABELS = ['GEMM-FP32','GEMM-INT8','YOLO-FP32','YOLO-INT8','Gemma3-4B','ResNet-50 FP32']
STYLE = {**DISSERTATION_STYLE,'font.size':11.5,'axes.labelsize':11.5,
    'axes.titlesize':11.5,'xtick.labelsize':11.5,'ytick.labelsize':11.5,
    'legend.fontsize':11.5,'axes.linewidth':.7,'axes.spines.top':False,
    'axes.spines.right':False,'axes.axisbelow':True,'pdf.fonttype':42,
    'svg.fonttype':'none','svg.hashsalt':'thesis-v56-energy-de-20261029',
    'figure.facecolor':'white','savefig.facecolor':'white',
    'axes.prop_cycle':matplotlib.cycler(color=[DISSERTATION_PALETTE[k] for k in ['blue','orange','green']] + ['#b74d53','#8c6bb0','#8d6554','#b55aa2'])}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def number(value, _=None): return f'{value:g}'.replace('.', ',')
def clean(ax, axis='y'):
    ax.grid(axis=axis, color='#e5e7eb', linewidth=.65)
    ax.tick_params(length=3, width=.6, pad=3)
    ax.xaxis.set_major_formatter(FuncFormatter(number))
    ax.yaxis.set_major_formatter(FuncFormatter(number))

def logarithmic_duration(ax):
    ax.set_xscale('log'); ax.set_xlim(4,730)
    ax.xaxis.set_major_locator(FixedLocator([5,20,100,600]))
    ax.xaxis.set_major_formatter(FuncFormatter(number))
    ax.xaxis.set_minor_formatter(NullFormatter())


class Builder:
    def __init__(self, output):
        self.output=Path(output); self.output.mkdir(parents=True,exist_ok=True)
        self.sources={}; self.records={}; self.payloads={}
        self.manifest={Path(x['file']).stem:x for x in json.loads((FROZEN/'ENERGY_SOURCE_MANIFEST.json').read_text())['figures']}
    def read(self, name):
        path=TABLES/(name+'.csv') if isinstance(name,str) else name
        self.sources[str(path.relative_to(ROOT))]=sha(path)
        return pd.read_csv(path,float_precision='round_trip')
    def figure(self,name):
        # These explicit canvases preserve the exact English publication size.
        sizes={'fp16_objectives':(6.15,2.8),'cross_workload_spectra':(6.8,3.5),
            'native_cdf':(4.8,3.05),'hailo_spectral_tail':(4.4,2.5),
            'jetson_deployed_meters':(4.8,3.2),'hailo_meters':(6,2.6),
            'hailo_variable_intervals':(4.4,2.65),'duration_comparison':(6,4.25),
            'pause_sequence':(6,2.6)}
        return plt.figure(figsize=sizes[name])
    def save(self,fig,name,payload):
        fig.canvas.draw()
        renderer=fig.canvas.get_renderer()
        text_bounds=[]
        from matplotlib.text import Text
        for text in fig.findobj(match=Text):
            if text.get_visible() and text.get_text().strip():
                box=text.get_window_extent(renderer)
                # Off-axis tick objects may exist but are not drawn.
                if box.x1 < 0 or box.x0 > fig.bbox.width or box.y1 < 0 or box.y0 > fig.bbox.height:
                    continue
                if box.x0 < -.5 or box.y0 < -.5 or box.x1 > fig.bbox.width+.5 or box.y1 > fig.bbox.height+.5:
                    text_bounds.append({'text':text.get_text(),'bbox':list(box.extents),'canvas':list(fig.bbox.extents)})
        if text_bounds: raise ValueError(f'Text outside canvas in {name}: {text_bounds}')
        for ext in ['pdf','svg','png']:
            kw={'metadata':{'CreationDate':None,'ModDate':None}} if ext=='pdf' else ({'metadata':{'Date':None}} if ext=='svg' else {})
            fig.savefig(self.output/f'{name}.{ext}',dpi=200,**kw)
        plt.close(fig)
        payload=dict(schema='thesis-energy-de-render-data-v1',language='de',figure=name,
            scientific_transformations='Only existing plotted unit conversions (Hz to kHz, complementary percentages, and PSD dB display); no new statistics.',**payload)
        (self.output/f'{name}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        self.payloads[name]=payload
        import fitz
        page=fitz.open(self.output/f'{name}.pdf')[0]
        reference=FROZEN/self.manifest[name]['file']
        original=fitz.open(reference)[0]
        if max(abs(x-y) for x,y in zip(page.rect,original.rect))>.001:
            raise ValueError('Canvas changed: '+name)
        include=self.manifest[name]['include_width']
        width=float(include[:-2]) if include.endswith('bp') else 355.42147945
        spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans']]
        sizes=collections.Counter(round(s['size'],3) for s in spans)
        reference_checks=validate_reference(name,payload,reference)
        self.records[name]={
            'file':f'figures/energy/{name}.pdf','source_kind':'published_summary_data_rerender',
            'language':'de','sha256':sha(self.output/f'{name}.pdf'),
            'english_reference':str(reference.relative_to(ROOT)),'english_reference_sha256':sha(reference),
            'source_inputs':{key:value for key,value in self.sources.items() if key in payload['source_inputs']},
            'data_payload':f'{name}.json','data_payload_sha256':sha(self.output/f'{name}.json'),
            'exact_source_rows_retained':True,'statistics_recomputed':False,
            'english_numeric_geometry_check':reference_checks,
            'same_canvas_as_english':True,'pdf_width_bp':page.rect.width,'include_width_bp':width,
            'font_sizes_bp':dict(sizes),'smallest_placed_font_bp':min(sizes)*width/page.rect.width,
            'placed_modal_font_bp':sizes.most_common(1)[0][0]*width/page.rect.width,
            'clipped_text':text_bounds}
        if self.records[name]['smallest_placed_font_bp']<8.4:
            raise ValueError('Unexpected small text: '+name)
    def data(self,frames,series):
        return {'source_inputs':[str((TABLES/(key+'.csv')).relative_to(ROOT)) for key in frames],
                'source_rows':{key:frame.to_dict(orient='records') for key,frame in frames.items()},
                'plotted_series':series}


def validate_reference(name, payload, reference):
    """Independently check the selected CSV values against frozen EN geometry.

    The PDF is used only as a validation reference, never as rendering data.
    Constants below calibrate the frozen EN axes from their labeled tick marks.
    Each checked point must agree within 0.002 PDF points (far below one pixel).
    """
    import fitz
    page=fitz.open(reference)[0]; drawings=page.get_drawings();checks=[]
    palette=[matplotlib.colors.to_rgb(c) for c in ['#2475a7','#d77a2d','#4c8d53','#b74d53','#8c6bb0','#8d6554','#b55aa2']]
    def same(color,wanted):return color is not None and max(abs(a-b) for a,b in zip(color,wanted))<.0001
    def markers(color,bounds,sort=1):
        pts=[]
        for d in drawings:
            r=d['rect'];x=(r.x0+r.x1)/2;y=(r.y0+r.y1)/2
            if same(d['fill'],palette[color]) and 1<r.width<9 and 1<r.height<9 and bounds[0]<x<bounds[2] and bounds[1]<y<bounds[3]:pts.append([x,y])
        return np.array(sorted(pts,key=lambda row:row[sort]))
    def check(label,actual,expected):
        actual,expected=np.asarray(actual),np.asarray(expected)
        if actual.shape!=expected.shape:raise ValueError(f'{name}/{label}: reference count {actual.shape} != source {expected.shape}')
        error=float(np.max(np.abs(actual-expected))) if actual.size else 0.
        if error>.002:raise ValueError(f'{name}/{label}: source/reference coordinate mismatch {error:.6g} bp')
        checks.append({'series':label,'checked_values':int(actual.size),'maximum_error_bp':error})
    series=payload['plotted_series']
    if name=='cross_workload_spectra':
        paths=[d for d in drawings if len(d['items'])>10]
        assert len(paths)==12
        for i,source in enumerate(series):
            frame=pd.DataFrame(source['source_rows']);frame=frame[frame.frequency_hz.gt(0)]
            for panel in range(2):
                data=frame[frame.normalised_density_per_hz.gt(0)] if panel==0 else frame
                x0=60.54 if panel==0 else 297.775
                xx=x0+184.675*(np.log10(data.frequency_hz.to_numpy())-np.log10(4))/(np.log10(2.5e6)-np.log10(4))
                scaled=(10*np.log10(data.normalised_density_per_hz.to_numpy())+140)/125 if panel==0 else data.cumulative_variance_pct.to_numpy()/101
                yy=161.85-140.06*scaled;source_points=np.column_stack((xx,yy))
                path=paths[i+6*panel];points=np.array([list(path['items'][0][1])]+[list(item[2]) for item in path['items']])
                expected=[]
                for point in points:
                    at=np.searchsorted(xx,point[0]);near=source_points[max(at-1,0):min(at+2,len(source_points))]
                    expected.append(near[np.argmin(np.linalg.norm(near-point,axis=1))])
                check(source['workload']+('/PSD' if panel==0 else '/CDF'),points,expected)
    elif name=='fp16_objectives':
        check('Q95',markers(0,(45,21,214,163),0)[:,1],162.4-126.0357142857*np.asarray(series[0]['y']))
        # The frozen English view plots the complementary percentage. Compare
        # its geometry with the complement of the directly displayed coverage.
        check('above Nyquist (complement of coverage)',markers(1,(268,21,437,163),0)[:,1],140.0370178223-56.1968765259*np.log10(100-np.asarray(series[1]['y'])))
    elif name=='native_cdf':
        for color,source in enumerate(series):
            bars=sorted([d['rect'] for d in drawings if same(d['fill'],palette[color]) and 30<d['rect'].y0<181 and 6<d['rect'].height<8],key=lambda r:r.y0)
            check(source['field'],[r.width for r in bars],np.asarray(source['values'])*7.7687878788)
    elif name=='hailo_spectral_tail':
        for color,source in enumerate(series):
            check(source['basis'],markers(color,(48,30,310,141))[:,0],48.53+2.27060869565*np.asarray(source['median_khz']))
    elif name=='jetson_deployed_meters':
        for color,source in enumerate(series):
            check(source['sensor'],markers(color,(90,27,340,192))[:,0],256.303333333+23.6276190476*np.asarray(source['P_median_pct']))
    elif name=='hailo_meters':
        for color,source in enumerate(series):
            values=np.asarray(source['P_median_pct'])
            expected=217.4358064516+48.6637741935*values if color<2 else 283.7963870968+6.15667882231*(values-20)
            bounds=(90,21,264,122) if color<2 else (283,21,426,122)
            check(source['sensor'],markers(color,bounds)[:,0],expected)
    elif name=='hailo_variable_intervals':
        for color,source in enumerate(series):
            check(source['field'],markers(color,(61,6,310,129),0)[:,1],33.7342222222-8.4794444444*np.asarray(source['values']))
    elif name=='duration_comparison':
        for i,source in enumerate(series):
            color=i if i<7 else i-7;top=source['platform']=='Jetson'
            bounds=(58,18,309,122) if top else (58,162,309,267)
            expected=(54.8595424837-7.71277777778*np.asarray(source['median']) if top else 182.22328125-10.3058558559*np.asarray(source['median']))
            check(source['platform']+'/'+source['slug'],markers(color,bounds,0)[:,1],expected)
    elif name=='pause_sequence':
        frame=pd.DataFrame(payload['source_rows']['pause_timing'])
        for panel,source in enumerate(series):
            for pause,color in [(20,1),(120,0)]:
                values=frame[frame.pause_s.eq(pause)][source['field']].to_numpy()
                expected=103.9326782227-9.72779846191*(values-100) if panel==0 else 131.2269287109-6.28322753906*(values-60)
                check(source['field']+'/'+str(pause),markers(color,((59,25,219,149) if panel==0 else (266,25,426,149)),0)[:,1],expected)
    return {'status':'PASS','tolerance_bp':.002,'reference_use':'validation only; no PDF data used in rendering','checks':checks,
            'checked_values':sum(item['checked_values'] for item in checks)}


def render(output:Path)->dict:
    b=Builder(output)
    with plt.rc_context(STYLE):
        # Q95 error and directly displayed spectral coverage from existing rows.
        fp=b.read('fp16_energy').sort_values('rate_sps');cov=b.read('fp16_coverage').sort_values('rate_sps')
        assert fp.rate_sps.tolist()==[50,85,2000] and fp.n_offset_cases.eq(960).all()
        assert cov.rate_sps.tolist()==[2000,125000,160000] and cov.n.eq(15).all()
        fig=b.figure('fp16_objectives'); axs=fig.subplots(1,2)
        fig.subplots_adjust(left=.115,right=.985,bottom=.24,top=.86,wspace=.52)
        axs[0].plot(range(3),fp.native_pooled_Q95_pct,'o',ms=4.6)
        axs[0].axhline(1,color='#89939a',ls='--',lw=.8);axs[0].text(1.65,.88,'1 %',color='#626d77',ha='center')
        axs[0].set(xlim=(-.45,2.45),ylim=(0,1.12),yticks=[0,.2,.4,.6,.8,1],ylabel='Q95-Energiefehler (%)',title='(a) Energie über 104 s')
        coverage=cov.median_pct.to_numpy();lo=cov.q05_pct.to_numpy();hi=cov.q95_pct.to_numpy()
        axs[1].errorbar(range(3),coverage,yerr=[coverage-lo,hi-coverage],fmt='o',ms=4.6,capsize=2,color='#D18432')
        for target,style in [(95,'--'),(99,':')]:
            axs[1].axhline(target,color='#89939a',ls=style,lw=.8,label=f'{target}-%-Ziel')
        axs[1].set(xlim=(-.45,2.45),ylim=(0,110),yticks=[0,25,50,75,100],ylabel='Anteil unterhalb der\nNyquist-Grenze (%)',title='(b) Spektrale Abdeckung')
        axs[1].legend(loc='center left',frameon=False,handlelength=1.5,handletextpad=.5)
        for ax,ticks in zip(axs,[['50 S/s','85 S/s','2 kS/s'],['2 kS/s','125 kS/s','160 kS/s']]):
            clean(ax);ax.set_xticks(range(3),ticks);ax.set_xlabel('Abtastrate')
        b.save(fig,'fp16_objectives',b.data({'fp16_energy':fp,'fp16_coverage':cov},[
            {'panel':0,'y':fp.native_pooled_Q95_pct.tolist(),'field':'native_pooled_Q95_pct'},
            {'panel':1,'y':coverage.tolist(),'lower':lo.tolist(),'upper':hi.tolist(),'field':'median_pct',
             'statistic':'median with empirical 5th–95th percentiles across 15 recordings',
             'target_criterion':'q05_pct >= target percentage','targets_pct':[95,99]}]))

        # Existing, already exported PSD/CDF curves: no PSD estimation or rebinning.
        with plt.rc_context({'font.size':12,'axes.labelsize':12,'axes.titlesize':12,
                            'xtick.labelsize':12,'ytick.labelsize':12,'legend.fontsize':12}):
            fig=b.figure('cross_workload_spectra');axs=fig.subplots(1,2)
            fig.subplots_adjust(left=.15,right=.985,bottom=.33,top=.86,wspace=.34)
            series=[];sources=[]
            for ident,label in zip(SPECTRAL_IDS,SPECTRAL_LABELS):
                path=CURVES/f'Jetson_Orin_NX__{ident}__tek__power__excess__existing_full_record.csv'
                frame=b.read(path); valid=frame.frequency_hz.gt(0)&frame.normalised_density_per_hz.gt(0)
                f=frame.loc[valid,'frequency_hz'].to_numpy();db=10*np.log10(frame.loc[valid,'normalised_density_per_hz'].to_numpy())
                axs[0].plot(f,db,lw=.75,alpha=.8,label=label)
                axs[1].plot(frame.loc[frame.frequency_hz.gt(0),'frequency_hz'],frame.loc[frame.frequency_hz.gt(0),'cumulative_variance_pct'],lw=1.05,alpha=.8,label=label)
                sources.append(str(path.relative_to(ROOT)))
                series.append({'workload':ident,'source':sources[-1],'source_rows':frame.to_dict(orient='records'),
                    'psd_mask':'frequency_hz > 0 and normalised_density_per_hz > 0',
                    'psd_display':'10*log10(normalised_density_per_hz)','cdf_field':'cumulative_variance_pct'})
            for ax in axs:
                clean(ax);ax.set_xscale('log');ax.set_xlim(4,2.5e6);ax.set_xlabel('Frequenz (Hz)')
                ax.xaxis.set_major_locator(FixedLocator([10,1000,100000,1000000]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:{10:'10',1000:'1k',100000:'100k',1000000:'1M'}[int(x)]));ax.xaxis.set_minor_formatter(NullFormatter())
            axs[0].set(ylim=(-140,-15),yticks=[-125,-100,-75,-50,-25],ylabel='Normierte PSD\n(dB bez. 1/Hz)',title='(a) Leistungsspektrum')
            axs[1].set(ylim=(0,101),yticks=[0,20,40,60,80,100],ylabel='Kumulierte Varianz (%)',title='(b) Spektrale Verteilung')
            fig.legend(*axs[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.53,.015),ncol=3,frameon=False,columnspacing=1.0,handlelength=1.5,handletextpad=.55)
            b.save(fig,'cross_workload_spectra',{'source_inputs':sources,'plotted_series':series})

        native=b.read('native_spectral_comparison').set_index('workload_id').loc[SPECTRAL_IDS].reset_index()
        assert native.signal.eq('power').all() and native.basis.eq('excess').all()
        fig=b.figure('native_cdf');ax=fig.subplots();fig.subplots_adjust(left=.34,right=.98,bottom=.29,top=.83)
        y=np.arange(6)
        ax.barh(y-.15,native.max_abs_cdf_difference_pp,height=.28,label='Gesamtband')
        ax.barh(y+.15,native.conditional_0_77khz_max_abs_cdf_difference_pp,height=.28,label='0–77 kHz')
        ax.set(xlim=(0,33),ylim=(5.6,-.6),xlabel='Maximale Differenz der kumulierten\nAnteile (Prozentpunkte)')
        clean(ax,'x');ax.set_yticks(y,SPECTRAL_LABELS);ax.set_xticks([0,5,10,15,20,25,30])
        fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.60,.99),ncol=2,frameon=False,handlelength=1.5,columnspacing=1.2)
        b.save(fig,'native_cdf',b.data({'native_spectral_comparison':native},[
            {'field':field,'values':native[field].tolist()} for field in ['max_abs_cdf_difference_pp','conditional_0_77khz_max_abs_cdf_difference_pp']]))

        hs=b.read('hailo_spectra');assert hs.signal.eq('power').all() and hs.window.eq('matched_prefix').all()
        fig=b.figure('hailo_spectral_tail');ax=fig.subplots();fig.subplots_adjust(left=.17,right=.98,bottom=.34,top=.69)
        payload=[]
        for basis,label,marker,offset,col in [('active','Aktiver Zustand','s',-.08,'#2E73B6'),('excess','Positives Differenzspektrum','o',.08,'#D18432')]:
            v=hs[hs.basis.eq(basis)].set_index('workload_id').loc[['gemm','yolo']]
            mid=v.f99_median_hz.to_numpy()/1000;low=v.f99_q05_hz.to_numpy()/1000;high=v.f99_q95_hz.to_numpy()/1000
            ax.errorbar(mid,np.arange(2)+offset,xerr=[mid-low,high-mid],fmt=marker,ms=5,capsize=2,label=label,color=col)
            payload.append({'basis':basis,'median_khz':mid.tolist(),'q05_khz':low.tolist(),'q95_khz':high.tolist()})
        ax.axvline(77,ls='--',lw=.9,color='#777777',label='Nominell 77 kHz');clean(ax,'x')
        ax.set(xlim=(0,115),ylim=(1.5,-.5),xlabel='Frequenz bei 99 %\nkumulierter Varianz (kHz)');ax.set_xticks([0,20,40,60,80,100]);ax.set_yticks([0,1],['GEMM','YOLO'])
        handles,labels=ax.get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.52,.99),ncol=2,frameon=False,handlelength=1.1,handletextpad=.4,columnspacing=.8)
        b.save(fig,'hailo_spectral_tail',b.data({'hailo_spectra':hs},payload))

        paired=b.read('paired_300s');assert paired.n.eq(15).all() and paired.requested_s.eq(300).all()
        jet=paired[paired.platform.eq('Jetson')]
        fig=b.figure('jetson_deployed_meters');ax=fig.subplots();fig.subplots_adjust(left=.285,right=.98,bottom=.27,top=.83)
        series=[]
        for sensor,label,marker,offset,col in [('firmware','u.RECS','o',0,'#2E73B6'),('jetson','Jetson-Telemetrie','s',0,'#D18432'),('shelly','Shelly (skaliert)','^',0,'#25896F')]:
            v=jet[jet.sensor.eq(sensor)].set_index('slug').loc[JET_IDS]
            ax.plot(v.P_median_pct,np.arange(7)+offset,ls='none',marker=marker,ms=5,label=label,color=col)
            series.append({'sensor':sensor,'slugs':JET_IDS,'P_median_pct':v.P_median_pct.tolist()})
        clean(ax,'x');ax.axvline(0,color='#89939a',ls=':',lw=.8);ax.axhline(5.5,color='#89939a',ls=':',lw=.8)
        ax.set(xlim=(-7,3.5),ylim=(6.6,-.6),xlabel='Leistungsabweichung gegenüber\nPicoScope (%)');ax.set_xticks([-6,-4,-2,0,2]);ax.set_yticks(range(7),JET_LABELS)
        fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.53,.99),ncol=3,frameon=False,handletextpad=.35,columnspacing=.9,handlelength=1.1)
        b.save(fig,'jetson_deployed_meters',b.data({'paired_300s':jet},series))

        hailo=paired[paired.platform.eq('Hailo')]
        fig=b.figure('hailo_meters');axs=fig.subplots(1,2,sharey=True,gridspec_kw={'width_ratios':[1.22,1]});fig.subplots_adjust(left=.225,right=.985,bottom=.35,top=.84,wspace=.15)
        series=[]
        for sensor,label,marker,offset,col,panel in [('firmware','u.RECS','o',0,'#2E73B6',0),('hailo_rt','HailoRT','s',0,'#D18432',0),('shelly','Shelly (skaliert)','^',0,'#25896F',1)]:
            v=hailo[hailo.sensor.eq(sensor)].set_index('slug').loc[HAILO_IDS]
            axs[panel].plot(v.P_median_pct,np.arange(3)+offset,ls='none',marker=marker,ms=5,label=label,color=col)
            series.append({'sensor':sensor,'slugs':HAILO_IDS,'P_median_pct':v.P_median_pct.tolist()})
        for ax in axs:clean(ax,'x');ax.set_ylim(2.6,-.6)
        axs[0].set(xlim=(-2.6,.95),title='(a) DC und Telemetrie');axs[0].axvline(0,color='#89939a',ls=':',lw=.8);axs[0].set_xticks([-2,-1,0]);axs[0].set_yticks(range(3),HAILO_LABELS)
        axs[1].set(xlim=(20,43),title='(b) Shelly (skaliert)');axs[1].set_xticks([20,30,40]);axs[1].tick_params(axis='y',left=False)
        fig.text(.60,.16,'Leistungsabweichung gegenüber PicoScope (%)',ha='center')
        hl=[ax.get_legend_handles_labels() for ax in axs];fig.legend(hl[0][0]+hl[1][0],hl[0][1]+hl[1][1],loc='lower center',bbox_to_anchor=(.55,.01),ncol=3,frameon=False,handletextpad=.35,columnspacing=1.4,handlelength=1.1)
        b.save(fig,'hailo_meters',b.data({'paired_300s':hailo},series))

        intervals=b.read('hailo_variable_interval_comparison').sort_values('requested_s')
        assert intervals.platform.eq('Hailo').all() and intervals.slug.eq('random_pattern_yolo').all() and intervals.sensor.eq('hailo_rt').all()
        fig=b.figure('hailo_variable_intervals');ax=fig.subplots();fig.subplots_adjust(left=.24,right=.98,bottom=.43,top=.965)
        series=[]
        for field,label,marker in [('P','Leistung','o'),('E','Energie','s'),('T','Ausgewertete Zeitspanne','^')]:
            vals=intervals[field+'_median_pct'];ax.plot(intervals.requested_s,vals,marker=marker,ms=4,lw=1.1,label=label)
            series.append({'field':field+'_median_pct','requested_s':intervals.requested_s.tolist(),'values':vals.tolist()})
        clean(ax);logarithmic_duration(ax);ax.set(ylim=(-11.2,3.2),ylabel='Abweichung zu\nPicoScope (%)',xlabel='Angeforderte Dauer (s)');ax.set_yticks([-10,-5,0])
        fig.legend(*ax.get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.55,.015),ncol=2,frameon=False,handletextpad=.35,columnspacing=.8,handlelength=1.1)
        b.save(fig,'hailo_variable_intervals',b.data({'hailo_variable_interval_comparison':intervals},series))

        duration=b.read('duration');fig=b.figure('duration_comparison');axs=fig.subplots(2,1,sharex=True)
        fig.subplots_adjust(left=.16,right=.71,bottom=.15,top=.93,hspace=.44)
        series=[]
        for ax,platform,ids,labels in zip(axs,['Jetson','Hailo'],[JET_IDS,HAILO_IDS],[JET_LABELS,HAILO_LABELS]):
            ax.set_title('(a) Jetson' if platform=='Jetson' else '(b) Hailo',loc='left',pad=4)
            for i,(slug,label) in enumerate(zip(ids,labels)):
                v=duration[duration.platform.eq(platform)&duration.slug.eq(slug)].sort_values('requested_s')
                mid=v.relative_median_pct.to_numpy();lo=v.relative_q05_pct.to_numpy();hi=v.relative_q95_pct.to_numpy()
                marker=['o','s','^','v','D','P','X'][i];ls='--' if slug=='random_pattern_yolo' else '-'
                ax.errorbar(v.requested_s,mid,yerr=[mid-lo,hi-mid],fmt=marker,ls=ls,ms=3.4,lw=1,capsize=2,elinewidth=.65,label=label)
                series.append({'platform':platform,'slug':slug,'requested_s':v.requested_s.tolist(),'median':mid.tolist(),'q05':lo.tolist(),'q95':hi.tolist()})
            clean(ax);logarithmic_duration(ax);ax.axhline(0,ls=':',lw=.8,color='#89939a');ax.set_yticks([-5,0])
            ax.legend(loc='center left',bbox_to_anchor=(1.005,.5),frameon=False,handlelength=1.2,handletextpad=.45,borderaxespad=0,labelspacing=.36)
        fig.supylabel('Leistungsabweichung zur 600-s-Referenz (%)',x=.045,y=.54,fontsize=STYLE['axes.labelsize'])
        axs[1].set_xlabel('Angeforderte Dauer (s)')
        b.save(fig,'duration_comparison',b.data({'duration':duration},series))

        pause=b.read('pause_timing').sort_values('index');assert pause['index'].tolist()==[1,2,3,4,5,6]
        fig=b.figure('pause_sequence');axs=fig.subplots(1,2);fig.subplots_adjust(left=.14,right=.985,bottom=.23,top=.80,wspace=.34)
        series=[]
        for ax,field,ylabel in zip(axs,['trt_s','gpu_before_5s_median_C'],['Laufzeit für\n100 Inferenzen (s)','GPU-Temperatur\nvor Start (°C)']):
            ax.plot(pause['index'],pause[field],color='#c5cbd0',lw=1,zorder=1)
            for length,label,marker,col in [(20,'20-s-Pause','o','#D18432'),(120,'120-s-Pause','s','#2E73B6')]:
                v=pause[pause.pause_s.eq(length)];ax.plot(v['index'],v[field],ls='none',marker=marker,ms=5,label=label,color=col,zorder=2)
            clean(ax);ax.set(xlim=(.75,6.25),xlabel='Reihenfolge',ylabel=ylabel);ax.set_xticks(range(1,7))
            series.append({'field':field,'index':pause['index'].tolist(),'values':pause[field].tolist()})
        axs[0].set_yticks([100,105]);axs[1].set_yticks([60,65,70,75])
        fig.legend(*axs[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.55,.99),ncol=2,frameon=False,handlelength=1.1,columnspacing=1.5)
        b.save(fig,'pause_sequence',b.data({'pause_timing':pause},series))
    from render_energy_result_fields import render as render_result_fields
    individual = render_result_fields(ROOT, b.output)
    b.records.update(individual['figures'])
    b.sources.update(individual['input_hashes'])
    result={'schema':'thesis-energy-de-regeneration-v1','status':'PASS','language':'de',
        'base_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        'generator':'scripts/dissertation/render_thesis_energy_de.py','generator_sha256':sha(__file__),
        'style_profile':'dissertation-author-20261103',
        'style_source':'scripts/split-inference/publication_mlsys_figures.py',
        'style_sha256':sha(ROOT/'scripts/split-inference/publication_mlsys_figures.py'),
        'figures':b.records,'input_hashes':b.sources,'measurement_or_statistical_analysis_performed':True,
        'measurement_acquisition_performed':False,'raw_signal_processing_performed':False,
        'statistical_operations':'Verify published reference and group statistics, and normalize individual execution exports for the two result fields.',
        'individual_execution_normalization_performed':True,
        'individual_result_generator':individual['generator'],
        'individual_result_generator_sha256':individual['generator_sha256']}
    (b.output/'ENERGY_DE_REGENERATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def render_coverage_proposal(output):
    """Render the new inventory view without an artificial English counterpart."""
    from load_measurement_scope_data import load_coverage
    from render_measurement_scope import render_coverage
    import fitz
    output=Path(output)
    rates,durations,metadata=load_coverage(ROOT)
    payload=render_coverage(rates,durations,output,metadata)
    name='measurement_scope'
    pdf=output/f'{name}.pdf'
    page=fitz.open(pdf)[0]
    spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans']]
    sizes=collections.Counter(round(s['size'],3) for s in spans)
    include_width=355.42147945
    placed_min=min(sizes)*include_width/page.rect.width
    # The one compact rate-cell exception (12 valid Hailo LLM runs) was reviewed
    # at 7.6 bp in the 396-bp canvas. All labels retain at least 7.8 bp after placement.
    small_spans=[s for s in spans if s['size']*include_width/page.rect.width<7.8]
    if any(s['text']!='12' or abs(s['size']-7.6)>.01 for s in small_spans) or len(small_spans)>1:
        raise ValueError(f'Unexpected small coverage text: {small_spans}')
    regular_sizes=[s['size'] for s in spans if s not in small_spans]
    generators=[Path(__file__),Path(__file__).with_name('render_measurement_scope.py'),
                Path(__file__).with_name('load_measurement_scope_data.py')]
    commit=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],
                          text=True,capture_output=True)
    record={
        'file':f'figures/energy/{name}.pdf','source_kind':'physical_execution_inventory',
        'language':'de','sha256':sha(pdf),'source_inputs':metadata['source_inputs'],
        'data_payload':f'{name}.json','data_payload_sha256':sha(output/f'{name}.json'),
        'counts':payload['counts'],'selection_rules':metadata['selection_rules'],
        'statistics_recomputed':False,'count_aggregation_performed':True,
        'english_reference_check':'not_applicable_new_figure',
        'pdf_width_bp':page.rect.width,'include_width_bp':include_width,
        'font_sizes_bp':dict(sizes),'smallest_placed_font_bp':placed_min,
        'smallest_placed_label_font_bp':min(regular_sizes)*include_width/page.rect.width,
        'reviewed_compact_cell_text':[{'text':s['text'],'font_size_bp':s['size'],
            'placed_font_size_bp':s['size']*include_width/page.rect.width} for s in small_spans],
        'clipped_text':[],
    }
    result={
        'schema':'thesis-energy-measurement-scope-regeneration-v1',
        'status':'PASS','publication_status':'proposal','language':'de',
        'base_commit':commit.stdout.strip() if commit.returncode==0 else None,
        'generators':{str(path.relative_to(ROOT)):sha(path) for path in generators},
        'figures':{name:record},'input_hashes':metadata['source_inputs'],
        'measurement_or_statistical_analysis_performed':False,
        'count_aggregation_performed':True,
    }
    (output/'MEASUREMENT_SCOPE_REGENERATION.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--coverage-only',action='store_true',
                        help='Render only the proposed measurement-coverage overview from repository inventories')
    args=parser.parse_args()
    result=render_coverage_proposal(args.output) if args.coverage_only else render(args.output)
    print(json.dumps({'status':result['status'],'figures':len(result['figures']),'output':str(args.output)}))

if __name__=='__main__':main()

