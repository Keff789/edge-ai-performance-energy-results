#!/usr/bin/env python3
"""Unified distribution heatmaps of individual physical measurement results.

Each cell contains up to 15 equal horizontal strips: one observed result per
strip, sorted by value within the group. Strip position is not execution order.
Columns are discrete tested settings, not a continuous/interpolated time axis.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, SymLogNorm
from matplotlib.collections import PolyCollection
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np
import pandas as pd

INK='#18354A'; MUTED='#587084'; GRID='#D7E1E8'; MISSING='#CBD0D4'
JET=[('gemm_fp32','GEMM-FP32'),('gemm_fp16','GEMM-FP16'),('gemm_int8','GEMM-INT8'),
     ('yolo_fp32','YOLO-FP32'),('yolo_fp16','YOLO-FP16'),('yolo_int8','YOLO-INT8'),
     ('random_pattern_yolo','YOLO variabel')]
HAILO=[('gemm','GEMM'),('yolo','YOLO'),('random_pattern_yolo','YOLO variabel')]
CMAP=LinearSegmentedColormap.from_list('energy_deviation',
    ['#164768','#377DB0','#93BBDD','#F4F5F5','#F3B482','#D36925','#943E17'],N=512)
STYLE={'font.family':'sans-serif','font.sans-serif':['Liberation Sans','DejaVu Sans'],
       'font.size':10,'text.color':INK,'axes.labelcolor':INK,
       'xtick.color':INK,'ytick.color':INK,'pdf.fonttype':42,'svg.fonttype':'none',
       'svg.hashsalt':'energy-combined-result-strips-v1','savefig.facecolor':'white',
       'figure.facecolor':'white'}


ROOT = Path(__file__).resolve().parents[2]
ENERGY = Path('results/energy-measurement')
INPUTS = {
    'duration_runs': ENERGY / 'tables/tim/paired_all_durations.csv',
    'duration_summary': ENERGY / 'tables/tim/duration.csv',
    'rate_runs': ENERGY / 'data/tim/final_direct/plotted_candidates.csv',
    'rate_groups': ENERGY / 'data/tim/final_direct/groups_all_candidates.csv',
    'rate_summary': ENERGY / 'tables/tim/direct_rates.csv',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(repository):
    """Select the published cohorts and verify their normalizations from CSVs."""
    repository = Path(repository).resolve()
    paths = {key: repository / path for key, path in INPUTS.items()}
    read = lambda key: pd.read_csv(paths[key], float_precision='round_trip')
    source = read('duration_runs')
    keys = ['platform', 'slug', 'series', 'window', 'requested_s', 'record_id']
    for name in ['pico_P_W', 'pico_E_J', 'pico_span_s']:
        assert source.groupby(keys)[name].nunique().eq(1).all(), name
    duration = source.drop_duplicates(keys).copy()
    assert duration.record_id.nunique() == len(duration)
    assert np.isfinite(duration[['pico_P_W', 'pico_E_J', 'pico_span_s']]).all().all()
    ref = duration[duration.requested_s.eq(600)].groupby(
        ['platform', 'slug']).pico_P_W.median().rename('reference_W')
    duration = duration.join(ref, on=['platform', 'slug'])
    assert duration.reference_W.gt(0).all()
    duration['value_pct'] = 100 * (duration.pico_P_W / duration.reference_W - 1)
    duration['setting'] = duration.requested_s.astype(int)
    published = read('duration_summary')
    observed = duration.groupby(['platform', 'slug', 'requested_s']).value_pct.agg(
        n='size', median='median').reset_index()
    checked = observed.merge(published, on=['platform', 'slug', 'requested_s'],
                             validate='one_to_one', suffixes=('', '_ref'))
    assert len(checked) == len(published) == len(observed)
    assert checked.n.eq(checked.n_ref).all()
    assert np.allclose(checked['median'], checked.relative_median_pct, atol=1e-10, rtol=0)

    raw = read('rate_runs')
    summary = read('rate_summary')
    published_groups = read('rate_groups')
    rate = raw.merge(summary[['platform', 'slug', 'series', 'window', 'reference_J']],
                     on=['series', 'window'], validate='many_to_one')
    included = rate.included.astype(str).str.lower().eq('true')
    rate = rate.loc[rate.sensor.eq('pico') & included &
                    np.isfinite(rate.energy_J) & np.isfinite(rate.span_s)].copy()
    assert rate.reference_J.gt(0).all()
    assert rate.axis_value.eq(rate.axis_value.astype(int)).all()
    rate['setting'] = rate.axis_value.astype(int)
    rate['value_pct'] = 100 * (rate.energy_J / rate.reference_J - 1)
    assert not rate.duplicated(['series', 'setting', 'run_id']).any()
    assert rate.record_id.nunique() == len(rate)
    groups = rate.groupby(['platform', 'slug', 'series', 'window', 'setting']).energy_J.agg(
        n='size', mean='mean').reset_index()
    for row in summary.itertuples():
        group = groups[groups.platform.eq(row.platform) & groups.slug.eq(row.slug)]
        assert len(group) == int(row.rates)
        assert group.n.sum() == int(row.finite_runs)
        assert np.isclose(group['mean'].mean(), row.reference_J, rtol=1e-12)
    reference_groups = published_groups[published_groups.sensor.eq('pico')].merge(
        summary[['series', 'window']], on=['series', 'window'], validate='many_to_one')
    reference_groups['setting'] = reference_groups.axis_value.astype(int)
    check = groups.merge(reference_groups[['series', 'window', 'setting', 'n', 'energy_mean']],
                         on=['series', 'window', 'setting'], validate='one_to_one',
                         suffixes=('_raw', '_published'))
    assert len(check) == len(groups) == len(reference_groups)
    assert check.n_raw.eq(check.n_published).all()
    assert np.allclose(check['mean'], check.energy_mean, rtol=1e-12)
    expected_duration = {('Jetson', slug) for slug, _ in JET} | {('Hailo', slug) for slug, _ in HAILO}
    assert set(zip(duration.platform, duration.slug)) == expected_duration
    assert set(zip(rate.platform, rate.slug)) == expected_duration | {('Jetson', 'llm'), ('Hailo', 'llm')}
    assert not set(duration.record_id) & set(rate.record_id)
    metadata = {
        'source_hashes': {str(INPUTS[key]): sha(path) for key, path in paths.items()},
        'duration_selection': 'One PicoScope result per physical execution after deduplicating comparator rows.',
        'rate_selection': 'Exact series/window in direct_rates.csv; sensor=pico; included=True; finite energy_J and span_s.',
        'validation': 'Unique executions, published group sizes, duration medians, rate-group mean energies and equal-group-weight references verified.',
    }
    try:
        metadata['source_commit'] = subprocess.check_output(
            ['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Extracted repository archives remain reproducible through the file hashes.
        metadata['source_commit'] = None
    return duration, rate, metadata


def number(x): return f'{x:g}'.replace('.',',')


def draw(frame,kind,output,metadata):
    is_rate=kind=='rate'
    rows=[('Jetson',s,l) for s,l in JET+([('llm','Sprachmodell')] if is_rate else [])]
    rows += [('Hailo',s,l) for s,l in HAILO+([('llm','Sprachmodell')] if is_rate else [])]
    columns=sorted(frame.setting.unique())
    norm=SymLogNorm(linthresh=.5,linscale=.65,vmin=-100,vmax=100,base=10) if is_rate else Normalize(-10,10)
    assert norm.vmin<=frame.value_pct.min() and frame.value_pct.max()<=norm.vmax
    target='rate_results' if is_rate else 'duration_results'
    original_height = 5.5 if is_rate else 4.8
    height = original_height - (.62 if is_rate else .55)
    # Crop the removed heading area without rescaling the plot, labels or strips.
    yscale = original_height / height
    yfig = lambda y: y * yscale
    plot_bottom=.32 if is_rate else .29
    plot_top=.86
    with plt.rc_context(STYLE):
        fig=plt.figure(figsize=(6.0,height))
        ax=fig.add_axes([.285,yfig(plot_bottom),.665,yfig(plot_top-plot_bottom)])
        ax.set_xlim(-.5,len(columns)-.5)
        yvalues=[i+(.5 if p=='Hailo' else 0) for i,(p,_,_) in enumerate(rows)]
        ax.set_ylim(yvalues[-1]+.6,-.6)
        ax.set_axis_off()
        polygons=[];values=[];records=[]
        for (platform,slug,label),yc in zip(rows,yvalues):
            ax.text(-.025,yc,label,ha='right',va='center',transform=ax.get_yaxis_transform(),fontsize=10.2)
            for xc,setting in enumerate(columns):
                d=frame[frame.platform.eq(platform)&frame.slug.eq(slug)&frame.setting.eq(setting)].sort_values(['value_pct','record_id'])
                assert len(d)<=15
                width=.91 if is_rate else .94
                left=xc-width/2;top=yc-.43
                ax.add_patch(Rectangle((left,top),width,.86,facecolor=MISSING,edgecolor='white',lw=.3,zorder=0))
                for j,row in enumerate(d.itertuples()):
                    y0=top+j*.86/15;y1=top+(j+1)*.86/15
                    polygons.append([(left,y0),(left+width,y0),(left+width,y1),(left,y1)])
                    values.append(float(row.value_pct))
                    records.append({'record_id':row.record_id,'platform':platform,'slug':slug,
                                    'setting':int(setting),'value_pct':float(row.value_pct),'sorted_position':j})
                if not len(d):
                    ax.plot([xc-.25,xc+.25],[yc-.25,yc+.25],color='#7C8891',lw=.6)
        collection=PolyCollection(polygons,array=np.array(values),cmap=CMAP,norm=norm,
                                  edgecolors='none',antialiased=False,zorder=1)
        ax.add_collection(collection)
        assert len(values)==len(frame) and len(set(x['record_id'] for x in records))==len(frame)
        for platform in ['Jetson','Hailo']:
            ys=[y for y,(p,_,_) in zip(yvalues,rows) if p==platform]
            trans=ax.get_yaxis_transform();x=-.31
            ax.plot([x,x],[ys[0]-.43,ys[-1]+.43],transform=trans,color=INK,lw=1,clip_on=False)
            ax.text(x-.035,np.mean([ys[0],ys[-1]]),platform,transform=trans,
                    ha='center',va='center',rotation=90,fontsize=11,weight='bold')
        bottom=yvalues[-1]+.72
        if is_rate:
            for x,setting in enumerate(columns):
                scaled=setting if setting<1000 else (setting/1000 if setting<1e6 else setting/1e6)
                ax.text(x,bottom,number(scaled),rotation=90,ha='center',va='top',fontsize=8.9)
            for low,high,unit in [(0,1000,'S/s'),(1000,1000000,'kS/s'),(1000000,float('inf'),'MS/s')]:
                positions=[i for i,value in enumerate(columns) if low <= value < high]
                if not positions:
                    continue
                lo,hi=positions[0],positions[-1]
                x0=.285+.665*(lo+.05)/len(columns)
                x1=.285+.665*(hi+.95)/len(columns)
                fig.add_artist(Line2D([x0,x1],[yfig(.244),yfig(.244)],transform=fig.transFigure,color=GRID,lw=.65))
                fig.text((x0+x1)/2,yfig(.239),unit,ha='center',va='top',fontsize=9.7)
            fig.text(.6175,yfig(.193),'Erfassungsrate',ha='center',fontsize=10.4)
        else:
            for x,setting in enumerate(columns):
                ax.text(x,bottom,str(setting),ha='center',va='top',fontsize=10.2)
            fig.text(.6175,yfig(.205),'Angeforderte Messdauer (s)',ha='center',fontsize=10.4)
        fig.add_artist(Rectangle((.285,yfig(.156)),.012,yfig(.012),transform=fig.transFigure,
                                 facecolor=MISSING,edgecolor='none'))
        fig.text(.305,yfig(.155),'Kein auswertbarer Messwert',fontsize=8,color=MUTED,va='bottom')
        if is_rate:
            fig.text(.95,yfig(.155),'Nichtlineare Farbskala',ha='right',fontsize=8,color=MUTED,va='bottom')
        cax=fig.add_axes([.285,yfig(.103),.665,yfig(.025)])
        ticks=[-100,-10,-1,0,1,10,100] if is_rate else [-10,-5,0,5,10]
        cb=fig.colorbar(collection,cax=cax,orientation='horizontal',ticks=ticks)
        cb.outline.set_linewidth(.4);cb.outline.set_edgecolor(GRID)
        cb.ax.tick_params(labelsize=9,length=2,pad=2,width=.5)
        cb.ax.set_xticklabels([('+' if v>0 else '')+str(v).replace('-','−') for v in ticks])
        cb.ax.minorticks_off()
        if is_rate:
            fig.text(.6175,yfig(.035),'Energieabweichung zum jeweiligen Bezugswert (%)',
                     ha='center',fontsize=9)
        else:
            fig.text(.6175,yfig(.027),'Leistungsabweichung zur jeweiligen 600-s-Referenz (%)',ha='center',fontsize=9)
        fig.canvas.draw();renderer=fig.canvas.get_renderer()
        for text in fig.findobj(match=Text):
            if text.get_visible() and text.get_text().strip():
                b=text.get_window_extent(renderer)
                if b.x0<-.5 or b.x1>fig.bbox.width+.5 or b.y0<-.5 or b.y1>fig.bbox.height+.5:
                    raise ValueError('Text outside canvas: '+text.get_text())
        for ext in ['pdf','svg','png']:
            meta={'CreationDate':None,'ModDate':None} if ext=='pdf' else ({'Date':None} if ext=='svg' else {})
            fig.savefig(output/f'{target}.{ext}',dpi=240,metadata=meta)
        plt.close(fig)
    payload={'figure':target,'design':'One unified distribution heatmap. One equal-size strip per observed execution.',
             'n_runs':len(frame),'n_groups':frame.groupby(['platform','slug','setting']).ngroups,
             'within_group_order':'Ascending measured deviation, not chronological order.',
             'missing':'Grey strips are missing/unavailable results, not zero deviations.',
             'x_axis':'Equally spaced categorical columns for tested settings; no interpolation.',
             'normalization':('Energy relative to the equally weighted mean of rate-group mean energies per variant.' if is_rate else 'Mean power relative to the variant-specific 600-s group median.'),
             'title_and_subtitle':False,
             'canvas_inches':[6.0,height],
             'color_scale':{'kind':'SymLogNorm' if is_rate else 'linear','vmin':norm.vmin,'vmax':norm.vmax,
                            'linear_center':[-.5,.5] if is_rate else None},
             'min_pct':float(frame.value_pct.min()),'max_pct':float(frame.value_pct.max()),
             'source':metadata,'records':records}
    (output/f'{target}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    source_keys = ('rate_runs', 'rate_groups', 'rate_summary') if is_rate else ('duration_runs', 'duration_summary')
    source_inputs = {str(INPUTS[key]): metadata['source_hashes'][str(INPUTS[key])] for key in source_keys}
    return {
        'file': f'figures/energy/{target}.pdf',
        'source_kind': 'normalized_individual_execution_results',
        'language': 'de',
        'sha256': sha(output / f'{target}.pdf'),
        'data_payload': f'{target}.json',
        'data_payload_sha256': sha(output / f'{target}.json'),
        'include_width': r'\linewidth',
        'generator': 'scripts/dissertation/render_energy_result_fields.py',
        'generator_sha256': sha(__file__),
        'source_inputs': source_inputs,
        'n_runs': len(frame),
        'n_groups': payload['n_groups'],
        'normalization': payload['normalization'],
        'color_scale': payload['color_scale'],
        'all_valid_results_shown_once': True,
        'statistics_recomputed': True,
        'statistical_operations': 'Published references and group statistics recomputed only for verification; individual relative deviations displayed.',
        'title_and_subtitle': False,
        'pdf_width_bp': 6.0 * 72,
        'pdf_height_bp': height * 72,
        'clipped_text': [],
    }


def render(repository: Path, output: Path):
    """Write both result fields and return records for the parent manifest."""
    repository, output = Path(repository).resolve(), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    duration, rate, metadata = load_inputs(repository)
    records = {
        'duration_results': draw(duration, 'duration', output, metadata),
        'rate_results': draw(rate, 'rate', output, metadata),
    }
    return {
        'schema': 'thesis-energy-result-fields-v1',
        'status': 'PASS',
        'figures': records,
        'input_hashes': metadata['source_hashes'],
        'source_commit': metadata['source_commit'],
        'generator': 'scripts/dissertation/render_energy_result_fields.py',
        'generator_sha256': sha(__file__),
        'measurement_acquisition_performed': False,
        'normalization_and_summary_verification_performed': True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = render(args.repository, args.output)
    (args.output / 'ENERGY_RESULT_FIELDS.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'figures': len(result['figures']),
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
