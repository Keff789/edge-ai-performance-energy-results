#!/usr/bin/env python3
"""Recompute TIM v0.3 summaries from frozen exported values, not raw waveforms.

No internet access, measurement acquisition, waveform integration or new PSD
estimation is performed. Plot creation is a separate step (make_figures.py).
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from paths import ROOT, D, G, T, Q
G.mkdir(exist_ok=True); T.mkdir(exist_ok=True)


def save(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(G/name, index=False)


def tex_tabular(name: str, columns: str, header: str, rows: list[str]) -> None:
    (T/name).write_text('\\begin{tabular}{@{}'+columns+'@{}}\n\\toprule\n'+header+
        ' \\\\\n\\midrule\n'+'\n'.join(rows)+'\n\\bottomrule\n\\end{tabular}\n', encoding='utf-8')


def main() -> None:
    c = pd.read_csv(D/'final_direct/plotted_candidates.csv')
    grouped = pd.read_csv(D/'final_direct/groups_all_candidates.csv')
    series = json.loads((D/'final_direct/series.json').read_text())
    policy = pd.read_csv(D/'final_direct/paper_window_policy.csv').set_index('series').paper_window.to_dict()
    selected = [s for s in series if s['section']=='primary' and s['summary'] and s['platform'] in ('Jetson','Hailo') and s['slug']!='random_pattern_yolo_adjusted']
    pair_rows, duration_rows, rate_rows = [], [], []
    direct_cv_error = 0.0
    for s in selected:
        b = c[(c.series==s['id']) & (c.window==policy[s['id']])].copy()
        p = b[b.sensor=='pico']
        assert np.isfinite(p.energy_J).all() and p.span_s.gt(0).all()
        if s['axis']=='sample_rate':
            cells=[]
            for rate,v in p.groupby('axis_value', sort=True):
                e=v.energy_J.to_numpy(float)
                cells.append({'rate_sps':float(rate),'n':len(e),'mean_J':e.mean(),
                              'median_J':np.median(e),'cv_pct':100*e.std(ddof=0)/abs(e.mean())})
            cells=pd.DataFrame(cells)
            prior=grouped[(grouped.series==s['id']) & (grouped.window==policy[s['id']]) & grouped.sensor.eq('pico')].set_index('axis_value')
            assert len(cells)==len(prior)
            for cell in cells.itertuples():
                assert cell.n==prior.loc[cell.rate_sps,'n']
                direct_cv_error=max(direct_cv_error,abs(cell.cv_pct-prior.loc[cell.rate_sps,'energy_cv_pct']))
            ref=cells.mean_J.mean()
            rate_rows.append({'platform':s['platform'],'slug':s['slug'],'series':s['id'],
                             'window':policy[s['id']],'rates':len(cells),'finite_runs':int(cells.n.sum()),
                             'max_cv_pct':cells.cv_pct.max(),
                             'max_group_displacement_pct':(100*(cells.mean_J/ref-1)).abs().max(),
                             'reference_J':ref,'reference_statistic':'unweighted_mean_of_rate_group_means'})
            continue
        if s['axis']!='nominal_duration':
            continue
        for req,v in p.groupby('axis_value', sort=True):
            power=v.energy_J.to_numpy(float)/v.span_s.to_numpy(float)
            duration_rows.append({'platform':s['platform'],'slug':s['slug'],'series':s['id'],'window':policy[s['id']],
                'requested_s':float(req),'n':len(v),'power_median_W':np.median(power),
                'power_q05_W':np.quantile(power,.05),'power_q95_W':np.quantile(power,.95),
                'span_median_s':np.median(v.span_s)})
            a=v.set_index('record_id'); assert a.index.is_unique
            for sensor in ('firmware','jetson','hailo_rt','shelly'):
                z=b[(b.sensor==sensor)&(b.axis_value==req)].set_index('record_id')
                assert z.index.is_unique
                ids=sorted(set(a.index)&set(z.index))
                if not ids: continue
                ap=a.loc[ids]; zp=z.loc[ids]
                assert (ap.energy_J>0).all() and (ap.span_s>0).all()
                assert np.isfinite(zp.energy_J).all() and (zp.span_s>0).all()
                for rid in ids:
                    ep=float(ap.loc[rid,'energy_J']); tp=float(ap.loc[rid,'span_s'])
                    es=float(zp.loc[rid,'energy_J']); ts=float(zp.loc[rid,'span_s'])
                    pair_rows.append({'platform':s['platform'],'slug':s['slug'],'series':s['id'],
                        'window':policy[s['id']],'requested_s':float(req),'sensor':sensor,'record_id':rid,
                        'pico_E_J':ep,'sensor_E_J':es,'pico_span_s':tp,'sensor_span_s':ts,
                        'pico_P_W':ep/tp,'sensor_P_W':es/ts,
                        'delta_E_pct':100*(es/ep-1),'delta_T_pct':100*(ts/tp-1),
                        'delta_P_pct':100*((es/ts)/(ep/tp)-1)})
    pairs=pd.DataFrame(pair_rows)
    assert not pairs.duplicated(['series','requested_s','sensor','record_id']).any()
    reconstruction=(1+pairs.delta_P_pct/100)*(1+pairs.delta_T_pct/100)
    identity_error=float(np.max(np.abs(reconstruction-(1+pairs.delta_E_pct/100))))
    assert identity_error<1e-12 and direct_cv_error<1e-8
    summaries=[]
    keys=['platform','slug','series','window','requested_s','sensor']
    for key,v in pairs.groupby(keys,sort=True):
        r=dict(zip(keys,key));r['n']=len(v)
        for quantity in ('E','P','T'):
            a=v['delta_'+quantity+'_pct'].to_numpy()
            for name,q in [('median',.5),('q05',.05),('q95',.95)]:r[f'{quantity}_{name}_pct']=float(np.quantile(a,q))
        summaries.append(r)
    summaries=pd.DataFrame(summaries)
    at300=summaries[summaries.requested_s.eq(300)].copy()
    assert len(at300)==30 and at300.n.eq(15).all()
    p300=pairs[pairs.requested_s.eq(300)]
    assert len(p300)==450 and p300[['series','record_id']].drop_duplicates().shape[0]==150
    save(pairs,'paired_all_durations.csv'); save(summaries,'paired_summary.csv');save(at300,'paired_300s.csv')
    var=summaries[summaries.platform.eq('Hailo')&summaries.slug.eq('random_pattern_yolo')&summaries.sensor.eq('hailo_rt')].copy()
    assert len(var)==10 and var.n.eq(15).all()
    save(var,'hailo_variable_interval_comparison.csv')
    duration=pd.DataFrame(duration_rows)
    for sid,v in duration.groupby('series'):
        base=v[v.requested_s.eq(600)];assert len(base)==1
        ref=float(base.power_median_W.iloc[0]); mask=duration.series.eq(sid)
        for stat in ('median','q05','q95'):
            duration.loc[mask,'relative_'+stat+'_pct']=100*(duration.loc[mask,'power_'+stat+'_W']/ref-1)
    save(duration,'duration.csv')
    rates=pd.DataFrame(rate_rows); save(rates,'direct_rates.csv')
    assert rates.groupby('platform').rates.sum().to_dict()=={'Hailo':108,'Jetson':215}
    # The missing three LLM intervals remain missing; they are never zeros or replacements.
    assert rates[rates.platform.eq('Hailo')&rates.slug.eq('llm')].finite_runs.iloc[0]==402
    labels={'gemm':'GEMM','yolo':'YOLO','random_pattern_yolo':'Variable YOLO','llm':'LLM'}
    hr=rates[rates.platform.eq('Hailo')].set_index('slug')
    tex_tabular('hailo_repeatability.tex','lrrr',r'Workload & Runs & Max. CV (\%) & Max. shift (\%)',[
        f'{labels[k]} & {int(hr.loc[k,"finite_runs"])} & {hr.loc[k,"max_cv_pct"]:.1f} & {hr.loc[k,"max_group_displacement_pct"]:.1f}'+r' \\'
        for k in ('gemm','yolo','random_pattern_yolo','llm')])
    # Native reconstruction and all-15 FP16 summaries: selection, not raw reanalysis.
    scope=pd.read_csv(D/'final_reconstruction/scope_fixed_2k_excerpt.csv')
    minima=pd.read_csv(D/'robustness_20261009/scope_persistent_minima.csv')
    m=minima.pivot(index='duration_s',columns='tolerance_pct',values='native_min_rate_sps')
    scope['persistent_1pct_sps']=scope.nominal_duration_s.map(m[1.])
    scope['persistent_0p5pct_sps']=scope.nominal_duration_s.map(m[.5])
    save(scope,'native_reconstruction.csv')
    assert float(scope.loc[scope.nominal_duration_s.eq(2),'persistent_1pct_sps'].iloc[0])==16000
    row=scope.set_index('nominal_duration_s')
    def rate(x: float) -> str: return f'{x/1000:g} kS/s' if x>=1000 else f'{x:g} S/s'
    tex_tabular('jetson_reference.tex','lrr',r'Interval & Q95 at 2 kS/s (\%) & Persistent $f_{\min}$ (1\%)',[
        f'{"100 ms" if d==.1 else f"{d:g} s"} & {row.loc[d,"native_envelope_Q95_pct"]:.2f} & {rate(row.loc[d,"persistent_1pct_sps"])}'+r' \\'
        for d in (.1,2.,5.,10.)])
    fp=pd.read_csv(D/'robustness_20261009/fp16_energy_selection.csv')
    fp=fp[fp.cohort.eq('all_ids_0_to_14')].copy(); assert len(fp)==3 and fp.n_offset_cases.eq(960).all()
    save(fp,'fp16_energy.csv')
    fp_psd=json.loads((D/'robustness_20261009/fp16_psd_selection.json').read_text())['cohorts']['all_ids_0_to_14']['branches']['matched_4s_4s']
    save(pd.DataFrame([{'rate_sps':float(f),'median_pct':100*v['median'],'q05_pct':100*v['q05'],'q95_pct':100*v['q95'],'n':v['n_defined']} for f,v in fp_psd['coverage_by_rate'].items()]),'fp16_coverage.csv')
    native=pd.read_csv(D/'validation/multi_workload/setup_comparison.csv')
    native=native[native.signal.eq('power')&native.basis.eq('excess')];assert len(native)==6
    save(native,'native_spectral_comparison.csv')
    spectral=pd.read_csv(D/'git/platform_spectral_metrics.csv')
    h=spectral[spectral.window.eq('matched_prefix')&spectral.basis.isin(['active','excess'])].copy()
    assert len(h)==4 and h.physical_runs.eq(15).all() and h.active_duration_s.eq(10).all()
    save(h,'hailo_spectra.csv')
    # Refit the prespecified additive control from the twelve stored run outcomes.
    ctrl=pd.read_csv(D/'validation/controlled/complementary/data/combined_runs.csv').sort_values(['session','position'])
    assert len(ctrl)==12 and ctrl.TRT_queries.eq(250).all()
    X=np.column_stack([np.ones(12),ctrl.rate5m.to_numpy(float),(ctrl.session==sorted(ctrl.session.unique())[1]).to_numpy(float)] + [(ctrl.position==i).to_numpy(float) for i in range(2,7)])
    rank=np.linalg.matrix_rank(X);assert rank==8
    ref_ctrl=pd.read_csv(D/'validation/controlled/complementary/data/balanced_effects.csv').set_index('metric')
    ctrlrows=[]
    for key,label in [('pico_load_20_80_mean_power_W','External DC power'),('vdd_load_W','Input telemetry'),('TRT_time_s','250-query runtime')]:
        y=ctrl[key].to_numpy(float);coef=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@coef
        se=np.sqrt((res@res/4)*np.linalg.inv(X.T@X)[1,1]); base=y[ctrl.rate5m.eq(0)].mean()
        eff=100*coef[1]/base;delta=100*student_t.ppf(.975,4)*se/base
        assert abs(eff-ref_ctrl.loc[key,'balanced_effect_percent_of_2kSps_mean'])<1e-9
        assert abs((eff-delta)-ref_ctrl.loc[key,'ci95_low_percent_of_2kSps_mean'])<1e-9
        ctrlrows.append({'metric':key,'label':label,'mean_2k':base,'mean_5M':y[ctrl.rate5m.eq(1)].mean(),'effect_pct':eff,'ci95_low_pct':eff-delta,'ci95_high_pct':eff+delta,'df':4})
    effect=pd.DataFrame(ctrlrows);save(effect,'controlled_effects.csv')
    tex_tabular('controlled.tex','lrrr',r'Quantity & Change (\%) & \multicolumn{2}{c}{95\% interval (\%)}',[
        f'{r.label} & {r.effect_pct:+.2f} & {r.ci95_low_pct:+.2f} & {r.ci95_high_pct:+.2f}'+r' \\' for r in effect.itertuples()])
    pause=pd.read_csv(D/'pause/pause_runs.csv');pause=pause[~pause.conditioning].copy()
    assert pause['index'].tolist()==list(range(1,7)) and pause.pause_s.tolist()==[20,120,120,20,20,120]
    psummary=pause.groupby('pause_s').agg(n=('index','size'),runtime_median_s=('trt_s','median'),start_gpu_median_C=('gpu_before_5s_median_C','median')).reset_index()
    save(pause[['index','pause_s','actual_pause_s','trt_s','gpu_before_5s_median_C']],'pause_timing.csv');save(psummary,'pause_summary.csv')
    drop=100*(psummary.loc[psummary.pause_s.eq(120),'runtime_median_s'].iloc[0]/psummary.loc[psummary.pause_s.eq(20),'runtime_median_s'].iloc[0]-1)
    # Source-bound numerical macros prevent uncoordinated prose/table updates.
    vars_5=var[var.requested_s.eq(5)].iloc[0]
    macros={'PauseReduction':f'{abs(drop):.1f}', 'HailoLLMCV':f'{hr.loc["llm","max_cv_pct"]:.1f}',
            'HailoLLMShift':f'{hr.loc["llm","max_group_displacement_pct"]:.1f}',
            'VariableEnergyFive':f'{vars_5.E_median_pct:.1f}', 'VariablePowerFive':f'{vars_5.P_median_pct:.1f}',
            'VariableSpanFive':f'{vars_5.T_median_pct:.1f}',
            'FPFifty':f'{fp[fp.rate_sps.eq(50)].native_pooled_Q95_pct.iloc[0]:.2f}'}
    (G/'numbers.tex').write_text('% Generated from frozen exported observations.\n'+''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()),encoding='utf-8')
    qa={'status':'PASS','source_candidate_rows':len(c),'direct_series':len(rates),
        'direct_groups':int(rates.rates.sum()),'direct_finite_runs':int(rates.finite_runs.sum()),
        'max_source_CV_residual_pp':direct_cv_error,'duration_groups':len(duration),
        'all_duration_pair_rows':len(pairs),'all_duration_pair_groups':len(summaries),
        '300s_groups':len(at300),'300s_pairs':len(p300),'300s_physical_executions':150,
        'per_run_energy_power_duration_identity_max_absolute_residual':identity_error,
        'scope_native_rows':len(scope),'scope_physical_executions':59,'scope_observations':118,
        'fp16_primary_recordings':15,'fp16_cases_per_energy_rate':960,'fp16_psd_branch':'matched_4s_4s',
        'Hailo_spectral_recordings':30,'pause_scored_runs':len(pause),'control_runs':len(ctrl),'control_residual_df':4,
        'new_measurements':False,'raw_waveform_reads':0,'PSD_reestimation':False,
        'additional_summary':'Same stored Hailo paired values now also compared as E/P/span over all ten duration requests.'}
    (Q/'NUMERICAL_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    print(json.dumps(qa,indent=2))

if __name__=='__main__':
    main()
