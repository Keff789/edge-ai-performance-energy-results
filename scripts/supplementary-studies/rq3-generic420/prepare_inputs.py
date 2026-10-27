#!/usr/bin/env python3
"""Build a traceable, quality-filtered Generic ranking dataset from the pinned export.
All frozen cells remain in candidates.csv; analysis_eligible chooses admitted measurements.
Graph normalization uses the complete per-model prediction candidate universe.
"""
import argparse,csv,json,hashlib,math,statistics
from pathlib import Path
from collections import Counter,defaultdict


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def validate_published_source(path, expected):
    # The delivery audit adds one extra terminal newline to repository originals.
    canonical = path.read_bytes().rstrip(b'\r\n') + b'\n'
    if expected not in {hashlib.sha256(canonical).hexdigest(), hashlib.sha256(canonical+b'\n').hexdigest()}:
        raise ValueError('Published graph feature source differs from the audited scoring protocol: '+path.name)
def writecsv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    repo=Path(__file__).resolve().parents[3]
    ap.add_argument('--source',type=Path,required=True,help='Read-only SM2 export root containing EXPORT_MANIFEST.json')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--published-features',type=Path,default=repo/'results/supplementary-studies/rq2-weighted-20261020/features/graph_boundary_features.csv')
    ap.add_argument('--published-normalization',type=Path,default=repo/'results/supplementary-studies/rq2-weighted-20261020/features/normalization_universes.json')
    a=ap.parse_args()
    if a.out.exists() and any(a.out.iterdir()): raise ValueError('Use an empty output directory; source exports are never modified')
    a.out.mkdir(parents=True,exist_ok=True)
    b=a.source; manifest=json.loads((b/'EXPORT_MANIFEST.json').read_text());bad=[]
    for e in manifest['files']:
        source_file=(b/e['member']).resolve()
        if not source_file.is_relative_to(b.resolve()): raise ValueError('Export manifest member escapes source root')
        if digest(source_file)!=e['sha256']:bad.append(e['member'])
    assert not bad,bad
    pointer=json.loads((b/'data/job/status420/CURRENT.json').read_text());job=manifest['job'];ledger_path=b/'data/job'/Path(pointer['snapshot']['path']).relative_to(job)
    assert digest(ledger_path)==pointer['snapshot']['sha256']
    assert ledger_path.resolve().is_relative_to(b.resolve())
    ledger=json.loads(ledger_path.read_text());frozen_path=b/'data/job/selection420/frozen_candidates420.json';frozen=json.loads(frozen_path.read_text());fidx={r['generic_uid']:r for r in frozen['rows']};lidx={r['generic_uid']:r for r in ledger['rows']};assert len(fidx)==len(lidx)==420;assert set(fidx)==set(lidx)
    audit=json.loads((Path(__file__).parent/'published_feature_provenance.json').read_text())
    published_path=a.published_features
    validate_published_source(published_path,audit['hashes']['published_graph_boundary_features.csv'])
    validate_published_source(a.published_normalization,audit['hashes']['published_normalization_universes.json'])
    with published_path.open() as f: published_rows=list(csv.DictReader(f))
    published={(r['model'],r['case']):r for r in published_rows}
    frozen_model_hashes={r['model_id']:r['model_sha256'] for r in frozen['rows']}
    assert len(published)==len(published_rows)
    universes={};features={};universe_rows=[];provenance={}
    for path in sorted(b.rglob('prediction.json')):
        j=json.loads(path.read_text());model=j['model_id'];cs=j['candidates'];assert model not in universes;universes[model]=cs
        assert len(cs)==j['analysis_candidate_count'];assert len(set(x['case_id'] for x in cs))==len(cs)
        cvals=[math.log10(1+float(r['cut_bytes'])) for r in cs];tvals=[max(int(r['n_cut_tensors'])-1,0) for r in cs];clo,chi=min(cvals),max(cvals);tlo,thi=min(tvals),max(tvals)
        provenance[model]={'source_name':model+'/prediction.json','sha256':digest(path),'candidate_count':len(cs),'source_artifact_id':j['artifact_id'],'C_log10_min':clo,'C_log10_max':chi,'T_raw_min':tlo,'T_raw_max':thi,'strict_ok_count':sum(x['strict_ok'] for x in cs)}
        for r,c,t in zip(cs,cvals,tvals):
            left,right=float(r['flops_left_abs']),float(r['flops_right_abs']);imb=abs(left-right)/(left+right) if left+right else 0.0
            assert math.isclose(imb,float(r['imbalance_val']),rel_tol=1e-12,abs_tol=1e-12),(model,r['case_id'],imb,r['imbalance_val'])
            feat={'model':model,'case_id':r['case_id'],'boundary':int(r['boundary']),'cut_bytes':float(r['cut_bytes']),'n_cut_tensors':int(r['n_cut_tensors']),'part2_input_count_graph':r.get('part2_input_count'),'flops_left_abs':left,'flops_right_abs':right,'C_log10':c,'T_raw':t,'C':(c-clo)/(chi-clo) if chi>clo else 0.0,'I':imb,'T':(t-tlo)/(thi-tlo) if thi>tlo else 0.0,'source_rank':r.get('source_rank',r.get('rank')),'strict_ok':r['strict_ok']}
            pub=published[model,r['case_id']]
            assert pub['model_sha256']==frozen_model_hashes[model]
            assert int(pub['boundary'])==feat['boundary'] and float(pub['Comm'])==feat['cut_bytes'] and int(pub['crossing_tensor_count'])==feat['n_cut_tensors']
            assert pub['feature_complete']=='True' and pub['tool_workflow_candidate']=='True'
            feat['I_workflow']=feat['I'];feat['flops_left_workflow']=feat['flops_left_abs'];feat['flops_right_workflow']=feat['flops_right_abs']
            feat['I']=float(pub['Imb_raw']);feat['flops_left_abs']=float(pub['F_left']);feat['flops_right_abs']=float(pub['F_right'])
            assert math.isclose(feat['I'],abs(feat['flops_left_abs']-feat['flops_right_abs'])/(feat['flops_left_abs']+feat['flops_right_abs']),rel_tol=1e-12,abs_tol=1e-12)
            feat['model_sha256']=pub['model_sha256'];feat['boundary_id']=pub['boundary_id']
            features[model,r['case_id']]=feat;universe_rows.append(feat)
    assert len(universes)==7
    published_norm_path=a.published_normalization
    published_norm=json.loads(published_norm_path.read_text())
    for graph in published_norm['graphs']:
        ranges=graph['universes']['regular_workflow_candidates']['ranges'];ours=provenance[graph['model']]
        for ownkey,feature,endpoint in [('C_log10_min','log10_1p_Comm','minimum'),('C_log10_max','log10_1p_Comm','maximum'),('T_raw_min','T_raw','minimum'),('T_raw_max','T_raw','maximum')]:
            assert math.isclose(ours[ownkey],ranges[feature][endpoint],rel_tol=1e-12,abs_tol=1e-12)
        ours['normalization_matches_published']=True
    rows=[];groupidx={(r['model'],r['setup']):r for r in ledger['groups']};repeat_errors=[]
    for uid,f in fidx.items():
        l=lidx[uid];model=f['model_id'];cut=f['case_id'];feat=features[model,cut]
        assert l['model_id']==model and l['case_id']==cut and l['setup']==f['setup']
        assert l['boundary_id']==f['boundary_id']==feat['boundary_id']
        assert float(f['cut_bytes'])==feat['cut_bytes'],(model,cut,'bytes mismatch')
        assert int(f['n_cut_tensors'])==feat['n_cut_tensors'],(model,cut,'tensor count mismatch')
        assert int(f['part2_input_count'])==int(published[model,cut]['part2_input_count'])
        rawfps=l.get('effective_generic_fps');fps=float(rawfps) if rawfps not in (None,'') else None
        reps=[float(x) for x in l.get('effective_repeats',[])];measured=fps is not None and math.isfinite(fps) and fps>0
        if measured:
            assert len(reps)==3 and all(math.isfinite(x) and x>0 for x in reps),(uid,reps)
            assert math.isclose(fps,statistics.median(reps),rel_tol=1e-12,abs_tol=1e-10),(uid,fps,reps)
        eligible=bool(measured and l.get('quality_eligible'));terminal=l.get('terminal_exclusion') or {};g=groupidx[model,f['setup']]
        row={'generic_uid':uid,'model':model,'task':f['task'],'accelerator':f['setup'],'setup_id':f['setup_id'],'case_id':cut,'boundary_id':f['boundary_id'],'direction':f['direction'],'execution_precision':l.get('execution_precision'),'admission_mode':l.get('admission_mode'),'observation_mode':l.get('observation_mode'),'fps':fps,'fps_measured':measured,'repeat1':reps[0] if len(reps)>0 else None,'repeat2':reps[1] if len(reps)>1 else None,'repeat3':reps[2] if len(reps)>2 else None,'fps_min':min(reps) if reps else None,'fps_max':max(reps) if reps else None,'fps_status':l.get('fps_status'),'quality_status':l.get('quality_status'),'quality_eligible':bool(l.get('quality_eligible')),'quality_role':l.get('quality_role'),'historical_quality_status':l.get('historical_quality_status'),'historical_quality_is_current_endpoint_admission':bool(l.get('historical_quality_is_current_endpoint_admission')),'analysis_eligible':eligible,'technical_exclusion':terminal.get('status',''),'technical_reason':terminal.get('reason',''),'selection_rank':f['selection_rank'],'window_index':f['window_index'],'part2_input_count':f['part2_input_count'],'group_full20_measured':g['full20_measured'],'group_resolved_conditional_pool':g['resolved_conditional_pool']}
        row.update({k:v for k,v in feat.items() if k not in ['model','case_id']});rows.append(row)
    cov=[]
    for (model,acc),g in groupidx.items():
        rs=[r for r in rows if r['model']==model and r['accelerator']==acc];meas=[r for r in rs if r['fps_measured']];qfail=sum(r['quality_status']=='accuracy_loss' for r in meas);eligible=sum(r['analysis_eligible'] for r in rs);qpending=len(meas)-qfail-eligible;technical=sum(bool(r['technical_exclusion']) for r in rs);fpspending=20-len(meas)-technical
        assert len(rs)==20 and fpspending>=0 and qpending>=0
        assert not any(r['fps_measured'] and r['technical_exclusion'] for r in rs)
        cc={'model':model,'task':rs[0]['task'],'accelerator':acc,'selected':20,'fps_measured':len(meas),'analysis_eligible':eligible,'quality_fail_measured':qfail,'quality_pending_measured':qpending,'technical_excluded':technical,'fps_pending':fpspending,'all20_measured':len(meas)==20,'all20_attempts_resolved':fpspending==0,'quality_resolved_measured':qpending==0,'analysis_group_complete':fpspending==0 and qpending==0,'ledger_resolved_conditional_pool':g['resolved_conditional_pool']};cov.append(cc)
        for r in rs:r['analysis_group_complete']=cc['analysis_group_complete'];r['group_eligible_n']=eligible;r['group_fps_pending']=fpspending;r['group_quality_pending']=qpending
    counts={'selected':len(rows),'fps_measured':sum(r['fps_measured'] for r in rows),
            'eligible':sum(r['analysis_eligible'] for r in rows),
            'quality_fail_measured':sum(g['quality_fail_measured'] for g in cov),
            'quality_pending_measured':sum(g['quality_pending_measured'] for g in cov),
            'technical_excluded':sum(g['technical_excluded'] for g in cov),
            'fps_pending':sum(g['fps_pending'] for g in cov),
            'nonempty_eligible_groups':sum(g['analysis_eligible']>0 for g in cov),
            'analysis_complete_groups':sum(g['analysis_group_complete'] for g in cov)}
    pending_quality=[{k:r[k] for k in ['generic_uid','model','accelerator','case_id','quality_status','quality_role','historical_quality_status','historical_quality_is_current_endpoint_admission']} for r in rows if r['fps_measured'] and not r['analysis_eligible'] and r['quality_status']!='accuracy_loss']
    assert counts['fps_measured']+counts['technical_excluded']+counts['fps_pending']==len(rows)
    assert counts['eligible']+counts['quality_fail_measured']+counts['quality_pending_measured']==counts['fps_measured']
    writecsv(a.out/'candidates.csv',rows);writecsv(a.out/'graph_universe.csv',universe_rows);writecsv(a.out/'coverage.csv',cov)
    meta={'schema':'generic420-graph-fit-input-v1','ledger_sha256':digest(ledger_path),'ledger_source':str(ledger_path.relative_to(b)),'frozen_selection_sha256':digest(frozen_path),'all_export_hashes_verified':len(manifest['files']),'export_manifest_sha256':digest(b/'EXPORT_MANIFEST.json'),'ledger_summary':ledger['summary'],'feature_definitions':{'C':'Per model min-max normalization of log10(1+cut_bytes) across all candidates in prediction.json','I':'Published analytic-operation-proxy-r29-extended-v1 Imb_raw, verified equal to abs(F_left-F_right)/(F_left+F_right). Workflow imbalance retained separately as I_workflow.','T':'Per model min-max normalization of max(n_cut_tensors-1,0) across all candidates in prediction.json','score':'w_C*C+w_I*I+w_T*T, lower scores preferred','normalization_origin':'Published weighted-score method: normalized log communication and tensor penalty, raw analytic-operation-proxy-r29-extended-v1 imbalance. Identical complete workflow candidate universe recovered from prediction.json.','normalization_uses_measured_outcomes':False,'tensor_feature_note':'Graph n_cut_tensors is not interchangeable with exact exported part2_input_count. Both columns retained.'},'quality_completion':{'complete':not pending_quality,'pending_measured':pending_quality,'historical_quality_is_current_admission':False,'claim':'Available quality-eligible conditional pool; not a final full-quality universe' if pending_quality else 'Resolved quality within the measured conditional candidate pool'},'published_graph_features':{'path':'results/supplementary-studies/rq2-weighted-20261020/features/graph_boundary_features.csv','sha256':digest(published_path),'all420_boundary_ids_match':True,'all_model_sha256_match':True,'all_workflow_candidate_features_complete':True},'published_normalization':{'path':'results/supplementary-studies/rq2-weighted-20261020/features/normalization_universes.json','sha256':digest(published_norm_path)},'prediction_sources':provenance,'counts':counts,'status':'preliminary' if counts['fps_pending'] or counts['quality_pending_measured'] else 'resolved_conditional_candidate_pool','group_coverage':cov}
    (a.out/'feature_metadata.json').write_text(json.dumps(meta,indent=2)+'\n');
    source_provenance={'schema':'generic420-public-feature-provenance-v1','repository':'Keff789/edge-ai-performance-energy-results','repository_commit':'1f3734bf0a190e4541dc843c957730280e0f6eb4','feature_source':'Published RQ2 feature CSV and complete regular workflow normalization universe; rechecked against every frozen boundary identity','operation_proxy':'analytic-operation-proxy-r29-extended-v1','published_graph_features':meta['published_graph_features'],'published_normalization':meta['published_normalization'],'frozen_selection_sha256':meta['frozen_selection_sha256'],'ledger_sha256':meta['ledger_sha256'],'export_manifest_sha256':meta['export_manifest_sha256'],'package_audit':json.loads((Path(__file__).parent/'published_feature_provenance.json').read_text()),'file_byte_note':'The package audit copies add a final newline to the repository feature CSV and normalization JSON. Parsed values are identical; consumed source hashes above refer to the original repository files.'}
    (a.out/'published_feature_provenance.json').write_text(json.dumps(source_provenance,indent=2)+'\n');
    print(json.dumps(meta['counts'],indent=2));print('out',a.out)
if __name__=='__main__':main()
