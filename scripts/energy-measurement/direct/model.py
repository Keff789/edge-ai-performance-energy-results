"""Statistics over immutable result windows. Never drops a finite candidate for its size."""
from __future__ import annotations
import csv, gzip, hashlib, io, json, math, os
from collections import defaultdict
from pathlib import Path
import numpy as np

VIEWS = ('reported_legacy', 'envelope_0.5')
SENSORS = ('pico','firmware','jetson','shelly','hailo_rt')
LABELS = {'pico':'Picoscope','firmware':'u.RECS','jetson':'Jetson','shelly':'Shelly','hailo_rt':'Hailo'}
VIEW_LABELS = {'reported_legacy':'Recorded interval','envelope_0.5':'Detected load intervals (all finite outcomes)','paper_selected':'Selected intervals: detected load; Hailo variable YOLO uses its recorded interval'}
METRICS = {'energy':'energy_J','power':'mean_power_W','duration':'span_s'}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def finite(x):
    try: return math.isfinite(float(x))
    except (TypeError,ValueError): return False

def write_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    path=Path(path);tmp=path.with_name(path.name+'.part')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    os.replace(tmp,path)

def write_csv(path,rows,fields=None):
    rows=list(rows); fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('w',encoding='utf8',newline='') as f:
        if fields:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def flags(row):
    return sorted(set(filter(None,(row.get('notes','')+';'+row.get('exclusion_reasons','')).split(';')))-{'reported_YAML_no_new_integration','stationary_series_no_automatic_load_envelope'})

def numeric_candidate(row):
    return all(finite(row.get(k)) for k in ('energy_J','span_s','mean_power_W')) and float(row['span_s'])>0

def statistics(values):
    a=np.asarray(list(values),dtype=float)
    if not len(a): return {k:None for k in ('median','mean','sd','cv_pct','q25','q75','q05','q95','min','max')}
    if not np.isfinite(a).all(): raise ValueError('Nonfinite statistics input')
    avg=float(np.mean(a));sd=float(np.std(a,ddof=0)) if len(a)>1 else None
    return dict(median=float(np.median(a)),mean=avg,sd=sd,cv_pct=100*sd/abs(avg) if sd is not None and avg!=0 else None,
                q25=float(np.percentile(a,25)),q75=float(np.percentile(a,75)),q05=float(np.percentile(a,5)),q95=float(np.percentile(a,95)),min=float(a.min()),max=float(a.max()))

class Data:
    def __init__(self,rows,registry):
        self.registry={s['id']:s for s in registry}
        self.index=defaultdict(list); self.missing=[]; self.ids=set();self.snapshot_rows_seen=0
        for raw in rows:
            self.snapshot_rows_seen+=1
            if raw['window'] not in VIEWS: continue
            r=dict(raw)
            if r['series'] not in self.registry: raise ValueError('Unknown source series: '+r['series'])
            key=(r['id'],r['window'])
            if key in self.ids:raise ValueError('Duplicate result/window '+str(key))
            self.ids.add(key)
            r['axis_value']=float(r['axis_value']) if r.get('axis_value') not in ('',None) else None
            if not numeric_candidate(r):
                self.missing.append(dict(id=r['id'],series=r['series'],window=r['window'],reason='nonfinite_or_nonpositive_span'));continue
            for k in ('energy_J','span_s','mean_power_W'):r[k]=float(r[k])
            if not math.isclose(r['energy_J']/r['span_s'],r['mean_power_W'],rel_tol=1e-9,abs_tol=1e-9):raise ValueError('E/T inconsistency '+r['id'])
            self.index[(r['series'],r['window'],r['sensor'],r['axis_value'])].append(r)
        for key,rr in self.index.items():
            if len(rr)!=len({r['record_id'] for r in rr}):raise ValueError('Duplicate participant '+str(key))
            rr.sort(key=lambda r:(int(r['run_id']),r['record_id']))
        self._stats={}
    @classmethod
    def load(cls,base):
        base=Path(base);registry=json.loads((base/'data/series.json').read_text())
        with gzip.open(base/'data/windows.csv.gz','rt',encoding='utf8',newline='') as f:
            return cls(csv.DictReader(f),registry)
    def get(self,s,v,sen,x):return self.index.get((s,v,sen,x),[])
    def grid(self,s):return self.registry[s]['grid'] or [None]
    def sensors(self,s):return [sen for sen in SENSORS if any(k[0]==s and k[2]==sen for k in self.index)]
    def group(self,s,v,sen,x):
        key=(s,v,sen,x)
        if key in self._stats:return self._stats[key]
        rr=self.get(*key);original=self.get(s,'reported_legacy',sen,x)
        fs=[flags(r) for r in rr]
        allflags=sorted({f for ff in fs for f in ff})
        g=dict(series=s,window=v,sensor=sen,axis_value=x,n=len(rr),n_reported=len(original),run_ids=','.join(r['run_id'] for r in rr),
               n_flagged=sum(bool(f) for f in fs),n_sensitive=sum('envelope_energy_sensitive_gt1pct' in f for f in fs),
               n_boundary_flagged=sum(any('edge' in k or 'boundary' in k or 'margin' in k for k in f) for f in fs),
               n_legacy_mismatch=sum(any('legacy_integral_mismatch' in k for k in f) for f in fs),
               n_timestamp_gap=sum('timestamp_gap_requires_review' in f for f in fs),flags=';'.join(allflags))
        for m,k in METRICS.items():
            for stat,z in statistics(r[k] for r in rr).items():g[m+'_'+stat]=z
        self._stats[key]=g;return g
    def groups(self):
        return [self.group(s,v,sen,x) for s in sorted(self.registry) for v in VIEWS for sen in self.sensors(s) for x in self.grid(s)]
    def pairs(self,s,v,sen,x):
        p={r['record_id']:r for r in self.get(s,v,'pico',x)}
        q={r['record_id']:r for r in self.get(s,v,sen,x)}
        return [(p[i],q[i]) for i in sorted(p.keys() & q.keys())]
    def pair_group(self,s,v,sen,x):
        pp=self.pairs(s,v,sen,x)
        g=dict(series=s,window=v,sensor=sen,reference='pico',axis_value=x,n_pairs=len(pp),
               n_pico=len(self.get(s,v,'pico',x)),n_sensor=len(self.get(s,v,sen,x)),
               record_ids=','.join(a['record_id'] for a,b in pp),
               n_flagged=sum(bool(flags(a) or flags(b)) for a,b in pp),
               flags=';'.join(sorted({f for a,b in pp for r in (a,b) for f in flags(r)})),
               interpretation='paired_own_window_setup_difference_not_synchronized_instrument_error')
        for m,k in METRICS.items():
            a=[r[k] for r,q in pp];b=[q[k] for r,q in pp]
            g[m+'_ratio_of_medians_pct']=100*(float(np.median(b))/float(np.median(a))-1) if a and np.median(a)>0 else None
            ratio=[100*(q[k]/r[k]-1) for r,q in pp if r[k]>0]
            g[m+'_valid_denominators']=len(ratio)
            st=statistics(ratio)
            for n in ('median','q25','q75','min','max'):g[m+'_paired_'+n+'_pct']=st[n]
        return g

def comparison_grid(data,registry,view,sensor='pico'):
    """Fixed internal baseline, never the best-looking group. No cross-series pooling."""
    out=[]
    for spec in registry:
        s=spec['id'];axis=spec['axis']
        if axis not in ('sample_rate','nominal_duration'):continue
        ref=2000. if axis=='sample_rate' else 600.
        metric='energy' if axis=='sample_rate' else 'power'
        rg=data.group(s,view,sensor,ref)
        median_ref=rg[metric+'_median']
        for x in data.grid(s):
            g=data.group(s,view,sensor,x);rr=data.get(s,view,sensor,x)
            base_ok=median_ref is not None and median_ref>0
            deviations=[100*(r[METRICS[metric]]/median_ref-1) for r in rr] if base_ok else []
            ab=np.abs(deviations)
            out.append(dict(series=s,label=spec['label'],platform=spec['platform'],section=spec['section'],summary=spec['summary'],
                            axis=axis,axis_value=x,window=view,sensor=sensor,metric=metric,reference_axis_value=ref,
                            reference_median=median_ref,reference_n=rg['n'],reference_n_reported=rg['n_reported'],reference_flags=rg['flags'],
                            n=g['n'],n_reported=g['n_reported'],n_flagged=g['n_flagged'],n_sensitive=g['n_sensitive'],
                            flags=g['flags'],median_relative_pct=100*(g[metric+'_median']/median_ref-1) if g['n'] and base_ok else None,
                            q95_absolute_relative_pct=float(np.percentile(ab,95)) if len(ab) else None,
                            max_absolute_relative_pct=float(np.max(ab)) if len(ab) else None,
                            repeatability_cv_pct=g[metric+'_cv_pct'],metric_median=g[metric+'_median']))
    return out



def paper_view(spec):
    """Frozen paper policy. No per-run choice and no result-dependent switch."""
    if spec.get('platform') == 'Hailo' and spec.get('slug') == 'random_pattern_yolo':
        return 'reported_legacy'
    return 'envelope_0.5'

def _paper_relevant_flag_string(value,source_view):
    names=[x for x in (value or '').split(';') if x]
    if source_view=='reported_legacy':
        keep={'timestamp_gap_requires_review','legacy_integral_mismatch','raw_result_unavailable','terminal_duplicate_power_row_excluded_in_derived_view'}
        names=[x for x in names if x in keep]
    return ';'.join(names)

def selected_comparison_grid(data,registry,sensor='pico'):
    out=[]
    for spec in registry:
        view=paper_view(spec)
        for q in comparison_grid(data,[spec],view,sensor):
            q=dict(q)
            q['source_window']=view
            q['window']='paper_selected'
            q['flags']=_paper_relevant_flag_string(q.get('flags'),view)
            q['reference_flags']=_paper_relevant_flag_string(q.get('reference_flags'),view)
            out.append(q)
    return out

def threshold_records(comparisons,tolerances=(1.,2.,5.)):
    """Persistent numerical agreement on observed grid, NOT calibrated f_min.

    At least two tested levels from threshold to the upper endpoint; at least two
    repetitions in every group and reference. Gaps in available WINDOW candidates
    prevent a suffix result. No interpolation between tested settings.
    """
    gg=defaultdict(list)
    for c in comparisons:gg[(c['series'],c['window'],c['sensor'])].append(c)
    result=[]
    for (s,v,sen),cc in sorted(gg.items()):
        cc.sort(key=lambda c:c['axis_value']);ref=cc[0]
        for eps in tolerances:
            found=None;status='not_met_on_observed_grid'
            if ref['reference_n']<2: status='reference_unavailable_or_n_lt_2'
            else:
                for i,c in enumerate(cc):
                    tail=cc[i:]
                    meets=all(q['n']>=2 and q['q95_absolute_relative_pct'] is not None and q['q95_absolute_relative_pct']<=eps for q in tail)
                    if meets and len(tail)>=2:found=i;status='observed_grid_agreement';break
                    if meets and len(tail)==1:status='endpoint_only_not_a_threshold'
            suffix=cc[found:] if found is not None else []
            issues=sorted({f for q in suffix for f in (q['flags']+';'+q['reference_flags']).split(';') if f})
            incomplete=any(q['n']<q['n_reported'] or q['reference_n']<q['reference_n_reported'] for q in suffix)
            result.append(dict(series=s,label=ref['label'],axis=ref['axis'],sensor=sen,window=v,tolerance_pct=eps,
                               first_observed_setting=cc[found]['axis_value'] if found is not None else None,
                               status=status,supporting_tested_levels=len(suffix),minimum_n=min((q['n'] for q in suffix),default=None),
                               candidates_incomplete=incomplete,flags=';'.join(issues),reference_axis_value=ref['reference_axis_value'],
                               criterion='empirical_q95_abs_run_difference_to_fixed_reference_median',
                               meaning='observed_grid_agreement_not_measurement_accuracy_or_universal_minimum'))
    return result
