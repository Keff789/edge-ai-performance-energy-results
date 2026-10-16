#!/usr/bin/env python3
"""Independent standard-library checks of exported outcomes and numerical presentation inputs.

No pandas, NumPy, SciPy, waveform integration, Git, or network operations.
Run after generate_results.py. A failed comparison stops with a nonzero status.
"""
from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json
import math
import re
import statistics

from paths import ROOT, D, G, T, Q


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def quantile(values, p):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('Empty quantile input')
    pos = (len(ordered) - 1) * p
    left = math.floor(pos)
    right = math.ceil(pos)
    return ordered[left] + (pos - left) * (ordered[right] - ordered[left])


def close(a, b, label, atol=1e-9):
    if not (math.isfinite(a) and math.isfinite(b)) or abs(a-b) > atol:
        raise ValueError(f'{label}: {a} != {b}')
    return abs(a-b)


def main():
    policy = {r['series']: r['paper_window'] for r in rows(D/'final_direct/paper_window_policy.csv')}
    series = json.loads((D/'final_direct/series.json').read_text())
    selected = {s['id']:s for s in series if s['section']=='primary' and s['summary']
                and s['platform'] in ('Jetson','Hailo') and s['slug']!='random_pattern_yolo_adjusted'}
    durations, ratecells = {}, defaultdict(list)
    for r in rows(D/'final_direct/plotted_candidates.csv'):
        sid = r['series']
        if sid not in selected or r['window'] != policy[sid]:
            continue
        s = selected[sid]
        if s['axis']=='sample_rate' and r['sensor']=='pico':
            ratecells[(sid,float(r['axis_value']))].append(float(r['energy_J']))
        elif s['axis']=='nominal_duration':
            key=(sid,float(r['axis_value']),r['record_id'],r['sensor'])
            if key in durations:
                raise ValueError('Ambiguous input: ' + repr(key))
            durations[key]=(float(r['energy_J']),float(r['span_s']))
    pair_groups=defaultdict(lambda: defaultdict(list))
    expected_pairs={}
    identity_max=0.0
    for (sid,dur,rid,sensor),(energy,span) in durations.items():
        if sensor not in ('firmware','jetson','hailo_rt','shelly'):
            continue
        ref=durations.get((sid,dur,rid,'pico'))
        if ref is None:
            continue
        ep,tp=ref
        if min(ep,tp,span,energy)<=0:
            raise ValueError('Nonpositive input to paired comparison')
        ratios={'E':energy/ep,'T':span/tp,'P':(energy/span)/(ep/tp)}
        identity_max=max(identity_max,abs(ratios['E']-ratios['P']*ratios['T']))
        expected_pairs[(sid,dur,rid,sensor)]={q:100*(r-1) for q,r in ratios.items()}
        for q,r in ratios.items():
            pair_groups[(sid,dur,sensor)][q].append(100*(r-1))
    exported=rows(G/'paired_all_durations.csv')
    if len(exported)!=len(expected_pairs):
        raise ValueError('Pair-count mismatch')
    residual=0.0
    for r in exported:
        key=(r['series'],float(r['requested_s']),r['record_id'],r['sensor'])
        for q in ('E','P','T'):
            residual=max(residual,close(expected_pairs[key][q],float(r['delta_'+q+'_pct']),str(key)+q))
    summaries=rows(G/'paired_summary.csv')
    if len(summaries)!=len(pair_groups):
        raise ValueError('Summary-count mismatch')
    for r in summaries:
        key=(r['series'],float(r['requested_s']),r['sensor'])
        values=pair_groups[key]
        if int(r['n'])!=len(values['P']):
            raise ValueError('Wrong pair denominator')
        for q in ('E','P','T'):
            for label,p in (('median',.5),('q05',.05),('q95',.95)):
                residual=max(residual,close(quantile(values[q],p),float(r[q+'_'+label+'_pct']),str(key)+q+label))
    direct={r['series']:r for r in rows(G/'direct_rates.csv')}
    for sid,output in direct.items():
        cells=[v for (s,_),v in ratecells.items() if s==sid]
        means=[statistics.mean(v) for v in cells]
        ref=statistics.mean(means)
        max_cv=max(100*statistics.pstdev(v)/abs(statistics.mean(v)) for v in cells)
        shift=max(100*abs(v/ref-1) for v in means)
        residual=max(residual,close(shift,float(output['max_group_displacement_pct']),sid+' shift'))
        residual=max(residual,close(max_cv,float(output['max_cv_pct']),sid+' CV'))
        if len(cells)!=int(output['rates']) or sum(map(len,cells))!=int(output['finite_runs']):
            raise ValueError('Direct-sweep population mismatch')
    curves=rows(G/'duration.csv')
    for r in curves:
        sid=r['series'];dur=float(r['requested_s'])
        values=[e/t for (s,d,_,sen),(e,t) in durations.items() if s==sid and d==dur and sen=='pico']
        reference=statistics.median([e/t for (s,d,_,sen),(e,t) in durations.items() if s==sid and d==600 and sen=='pico'])
        if int(r['n'])!=len(values):
            raise ValueError('Wrong duration denominator')
        for label,p in (('median',.5),('q05',.05),('q95',.95)):
            qv=quantile(values,p)
            residual=max(residual,close(qv,float(r['power_'+label+'_W']),sid+label))
            residual=max(residual,close(100*(qv/reference-1),float(r['relative_'+label+'_pct']),sid+label+' relative'))
    prior=rows(ROOT/'tables/measurement-comparison/all_platform_device_pair_spread.csv')
    prior={(r['series'],r['sensor']):r for r in prior}
    for r in rows(G/'paired_300s.csv'):
        p=prior[(r['series'],r['sensor'])]
        for label in ('median','q05','q95'):
            residual=max(residual,close(float(r['P_'+label+'_pct']),float(p['paired_'+label+'_pct']),'PARMA package '+label))
    # Self-contained journal additions are new views of the same data, not new observations.
    for derived,base in [('jetson_foundation_energy.csv','native_reconstruction.csv'),
                         ('fp16_coverage_plot.csv','fp16_coverage.csv')]:
        aa,bb=rows(G/derived),rows(G/base)
        if len(aa)!=len(bb): raise ValueError('Foundation table length mismatch')
        for x,y in zip(aa,bb):
            for k,v in x.items():
                if v==y[k]: continue
                close(float(v),float(y[k]),derived+k)
    for filename,original,platform,count in [('jetson_paired_300s.csv','paired_300s.csv','Jetson',21),
                                          ('jetson_duration.csv','duration.csv','Jetson',70)]:
        aa=rows(G/filename); bb=[r for r in rows(G/original) if r['platform']==platform]
        if len(aa)!=len(bb) or len(aa)!=count:
            raise ValueError('Changed standalone Jetson count: '+filename)
        for x,y in zip(aa,bb):
            if set(x)!=set(y): raise ValueError('Standalone column mismatch')
            for k,v in x.items():
                if v==y[k]: continue
                close(float(v),float(y[k]),filename+k)
    foundation_text=(T/'jetson_reference.tex').read_text()
    for label in ['20 ms','50 ms','100 ms','200 ms','500 ms','1 s','2 s','5 s','10 s']:
        if label+' &' not in foundation_text: raise ValueError('Incomplete nine-duration table: '+label)
    direct_table=(T/'direct_repeatability.tex').read_text()
    if direct_table.count(' & ') != (12+1)*3:
        raise ValueError('Incomplete direct-sweep overview')
    # Numeric guards for the final, rather than superseded, reference definitions.
    native={float(r['nominal_duration_s']):r for r in rows(G/'native_reconstruction.csv')}
    close(float(native[2]['persistent_1pct_sps']),16000.,'native persistent rate')
    close(float(native[2]['native_envelope_Q95_pct']),.853155439737469,'fixed native rate')
    fp=rows(G/'fp16_energy.csv')
    if len(fp)!=3 or any(r['cohort']!='all_ids_0_to_14' or int(r['n_offset_cases'])!=960 for r in fp):
        raise ValueError('Wrong FP16 primary cohort')
    physical300={(sid,rid) for sid,dur,rid,_ in expected_pairs if dur==300}
    if len(physical300)!=150:
        raise ValueError('Sensor pairs confused with physical repeats')
    qa={'status':'PASS','method':'Independent Python standard-library recomputation (statistics and explicit type-7 quantiles)',
        'paired_rows_checked':len(exported),'paired_groups_checked':len(summaries),
        'duration_groups_checked':len(curves),'rate_series_checked':len(direct),
        'source_PARMA_300s_summary_rows_checked':len(prior),'physical_executions_at_300s':len(physical300),
        'max_numeric_residual':residual,'max_pair_identity_residual':identity_max,
        'native_all15_reference_guards':'PASS',
        'raw_signals_read':0,'scope':'Export arithmetic and displayed input definitions; not raw calibration/PSD or acquisition verification'}
    (Q/'INDEPENDENT_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    print(json.dumps(qa,indent=2))

if __name__=='__main__':
    main()
