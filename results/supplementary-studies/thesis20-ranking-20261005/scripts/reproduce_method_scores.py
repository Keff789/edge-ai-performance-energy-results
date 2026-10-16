#!/usr/bin/env python3
"""Offline score projection from saved full graph universe; no fitted parameters.

--input-root contains this package's compact inputs; --source-root is the frozen
THESIS20 public analysis root; --output-root receives the derived input projection
and global-selection tables. The seven static method IDs include explicit missing
Native-handover and GUI-SystemSpec methods. Measured proxies are evaluated by the
companion evaluator; availability records their exact original population.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path
from method_core.ranking_methods import compute_ranking_predictions,ranking_method_policy
from method_core.objective_scoring import accelerator_fit_metrics,candidate_objective_metrics
from method_core.system_model import SystemSpec,ComputeSpec,LinkModelSpec

METHODS=('cut_bytes_only','weighted_score','onnx_real_boundary_hardware_aware','cycle_time_no_handover','cycle_time_with_handover','stored_predicted_stream_fps','gui_total_latency')
MEASURED=('measured_generic_raw','measured_generic_completion')
UNITS={'cut_bytes_only':'graph_estimated_bytes','weighted_score':'dimensionless_normalized_score','onnx_real_boundary_hardware_aware':'dimensionless_historical_fit_score','cycle_time_no_handover':'heuristic_ms','cycle_time_with_handover':'heuristic_ms','stored_predicted_stream_fps':'heuristic_tasks_per_s','gui_total_latency':'model_ms','measured_generic_raw':'raw_outputs_per_s','measured_generic_completion':'completed_tasks_per_s'}


def read_csv(path):
    with path.open(newline='') as f:rows=list(csv.DictReader(f))
    for row in rows:
        for k,v in row.items():
            if v=='':row[k]=None
            elif v=='True':row[k]=True
            elif v=='False':row[k]=False
            elif v.startswith(('{','[')):
                try:row[k]=json.loads(v)
                except ValueError:pass
            else:
                try:row[k]=float(v)
                except ValueError:pass
    return rows


def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,separators=(',',':'),sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def system_proxy(candidate,spec):
    """Only a supplied, fully parameterized SystemSpec can yield a GUI proxy."""
    if not isinstance(spec,dict):return None
    left=spec.get('left') or {};right=spec.get('right') or {};link=spec.get('link') or {}
    if not left.get('gops') or not right.get('gops') or not link.get('bandwidth_value') or not link.get('bandwidth_unit'):return None
    model=SystemSpec(left=ComputeSpec(gops=left['gops']),right=ComputeSpec(gops=right['gops']),link=LinkModelSpec(**{k:link[k] for k in ['type','bandwidth_value','bandwidth_unit','overhead_ms','mtu_payload_bytes','per_packet_overhead_ms','per_packet_overhead_bytes'] if k in link}),overhead_ms=spec.get('overhead_ms',0))
    return model.estimate_boundary(comm_bytes=candidate['cut_bytes'],flops_left=candidate['flops_left_abs'],flops_total=candidate['total_flops'])['latency_total_ms']


def derive_scores(features,parameters):
    groups=defaultdict(list)
    for row in features:groups[row['model_id']].append(row)
    result=[];verification=[]
    for model,rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['source_list_order'])
        if len({r['case_id'] for r in rows})!=len(rows):raise ValueError('duplicate graph candidate identity')
        if any(r['strict_ok'] is not True for r in rows):raise ValueError('saved universe unexpectedly contains strict-ineligible candidate')
        frozen_profiles={json.dumps(r['accelerator_fit_profile'],sort_keys=True) for r in rows}
        if len(frozen_profiles)!=1:raise ValueError('multiple historical hardware-fit profiles need explicit separate analysis')
        profile=json.loads(next(iter(frozen_profiles)))
        context=dict(direction=profile['stage1']+'_to_'+profile['stage2'],stage1=profile['stage1'],stage2=profile['stage2'],runner_regime='native_fifo')
        # Crucial: normalization is performed once over the COMPLETE saved model
        # universe, before selection of measured candidates or quality subsets.
        predictions=compute_ranking_predictions(rows,[context],parameters['ranking_validation'])
        indexed={(r['case_id'],r['method_id']):r for r in predictions}
        for candidate in rows:
            fit=accelerator_fit_metrics(candidate,stage1=profile['stage1'],stage2=profile['stage2'])
            assert all(profile[k]==v for k,v in fit['accelerator_fit_profile'].items())
            assert math.isclose(fit['accelerator_fit_score'],candidate['accelerator_fit_score'],abs_tol=1e-12)
            # Verify the actual stored heuristic origin, never relabel as GUI.
            fallback=5+candidate['total_flops']/1e10+candidate['cut_bytes']/1e9
            assert math.isclose(fallback,candidate['predicted_total_latency_ms'],abs_tol=1e-12)
            enriched=dict(candidate,pred_latency_total_ms=candidate['predicted_total_latency_ms'])
            objective=candidate_objective_metrics(enriched,stage1=profile['stage1'],stage2=profile['stage2'],use_calibration=candidate['throughput_calibration_enabled'])
            for field in ['predicted_bottleneck_ms','predicted_stream_fps']:
                assert math.isclose(objective[field],candidate[field],rel_tol=1e-12,abs_tol=1e-12),(model,candidate['case_id'],field)
            for method in METHODS:
                if method in {'cut_bytes_only','weighted_score','cycle_time_no_handover','cycle_time_with_handover'}:
                    pred=indexed[(candidate['case_id'],method)];score=pred['predicted_value'];reason=pred['prediction_source'];derivation='posthoc_existing_method_full_universe'
                elif method=='onnx_real_boundary_hardware_aware':score=candidate['accelerator_fit_score'];reason='stored_hailo10_profile_score_exactly_reproduced';derivation='stored_historical_score'
                elif method=='stored_predicted_stream_fps':score=candidate['predicted_stream_fps'];reason='stored_yolov7_streaming_v1_hailo10_direction';derivation='stored_historical_prediction'
                else:score=system_proxy(candidate,parameters['system_spec_by_model'][model]);reason='original_system_spec_missing' if score is None else 'original_system_spec_estimate_boundary';derivation='unavailable' if score is None else 'posthoc_original_system_spec'
                result.append(dict(model_id=model,case_id=candidate['case_id'],setup_id='all',method=method,score=score,score_direction='descending' if method=='stored_predicted_stream_fps' else 'ascending',original_order=int(candidate['original_order']),source_list_order=int(candidate['source_list_order']),status='available' if score is not None else 'unavailable',reason=reason,derivation_status=derivation,source_role='BASE_saved_graph_and_profile'))
        verification.append(dict(model_id=model,graph_candidates=len(rows),historical_fit_rows_verified=len(rows),stored_fallback_latency_rows_verified=len(rows),stored_bottleneck_and_stream_rows_verified=len(rows),historical_fit_profile=profile,system_spec_available=parameters['system_spec_by_model'][model] is not None))
    return result,verification


def provenance(method,parameters,profile):
    if method=='weighted_score':return dict(weights=parameters['ranking_validation']['weighted_score'],normalization='per_model_full_strict_saved_graph_universe',communication='log10(1+graph_bytes) minmax',imbalance='stored imbalance minmax',tensor_term='max(n_tensors-1,0) minmax')
    if method=='onnx_real_boundary_hardware_aware':return dict(profile=profile,preserved_input_unit='cut_mb_val decimal MB is consumed by existing code whose threshold labels say mib; preserved without correction',binding='historical Hailo10-to-TensorRT fit shared across all requested setups; no target-device adaptation')
    if method=='cycle_time_no_handover':return dict(stage_time_models=parameters['ranking_validation']['cycle_time_no_handover'],stage_source='candidate_bottleneck',total_latency_source='workflow fallback 5 + FLOPs/1e10 + graph_bytes/1e9',bottleneck_source='stored total heuristic times max(left,right) FLOPs fraction',scope='heuristic_not_measured_stage_or_GUI_SystemSpec')
    if method=='cycle_time_with_handover':return dict(runner_regime='native_fifo',policy=parameters['ranking_validation']['cycle_time_with_handover'],scope='native_handover_model_unconfigured; Generic calibration is not substituted')
    if method=='stored_predicted_stream_fps':return dict(calibration_profile='yolov7_streaming_v1',historical_direction='hailo10_to_tensorrt',definition='1000/(stored_bottleneck_ms+stored_calibrated_handover_ms)',scope='saved heuristic common to all setups; not independently fitted for each device/model')
    if method=='gui_total_latency':return dict(path='SystemSpec.estimate_boundary',source='BASE/models/<model>/benchmark_set/legacy_benchmark_set.json:system_spec',status='null in all seven models; stored fallback latency does not supply SystemSpec parameters')
    if method=='cut_bytes_only':return dict(unit='bytes',decimal_MB='bytes/1000000',binary_MiB='bytes/1048576',precision='original graph tensor-byte estimate; per-tensor dtype not serialized here; no runtime precision conversion')
    return dict(scope='192 exact original raw/completion identities' if method=='measured_generic_raw' else '204 measured completed-task pairs',aggregation='existing median, unchanged original gates and observation origin')


def analyze(input_root,source_root,output_root):
    features=read_csv(input_root/'inputs/method_graph_features.csv');parameters=json.loads((input_root/'inputs/method_parameters.json').read_text());scores,verification=derive_scores(features,parameters)
    pairs=read_csv(source_root/'inputs/completion_pairs.csv');coverage=read_csv(source_root/'inputs/coverage.csv');raw=read_csv(source_root/'inputs/generic_raw.csv')
    feature_index={(r['model_id'],r['case_id']):r for r in features};score_groups=defaultdict(list)
    for row in scores:score_groups[(row['model_id'],row['method'])].append(row)
    pair_index={(r['model_id'],r['case_id'],r['setup_id']):r for r in pairs}
    raw_index={}
    for row in raw:
        if row['variant']=='split':
            key=(row['model_id'],row['case_id'],row['setup_id'],'deepx' if row['comparison_backend']=='deepx_m1' else row['comparison_backend'])
            if key in raw_index:raise ValueError('raw identity ambiguous')
            raw_index[key]=row
    coverage_index=defaultdict(list)
    for row in coverage:coverage_index[(row['model_id'],row['case_id'],row['setup_id'])].append(row)
    availability=[];global_rows=[];special=[]
    for model,setup in sorted({(r['model_id'],r['setup_id']) for r in pairs}):
        pp=[r for r in pairs if r['model_id']==model and r['setup_id']==setup];profile=next(r['accelerator_fit_profile'] for r in features if r['model_id']==model)
        for method in METHODS+MEASURED:
            graph_rows=score_groups.get((model,method),[]);available=[r for r in graph_rows if r['score'] is not None]
            matched=[r for r in pp if (r['model_id'],r['case_id']) in feature_index and next(x for x in graph_rows if x['case_id']==r['case_id'])['score'] is not None] if graph_rows else []
            if method=='measured_generic_completion':matched=pp
            if method=='measured_generic_raw':
                matched=[r for r in pp if r['observation_origin']=='base' and (model,r['case_id'],setup,r['comparison_backend']) in raw_index]
                for r in matched:assert math.isclose(raw_index[(model,r['case_id'],setup,r['comparison_backend'])]['throughput_fps'],r['historical_generic_raw_fps'],rel_tol=1e-12)
            reason=graph_rows[0]['reason'] if graph_rows else 'measured_proxy_original_identity_subset'
            availability.append(dict(model_id=model,setup_id=setup,method=method,status='available' if matched else 'unavailable',graph_universe_count=len([r for r in features if r['model_id']==model]),graph_score_count=len(available),completed_candidate_count=len(pp),measured_score_count=len(matched),unit=UNITS[method],score_direction='descending' if method in MEASURED+('stored_predicted_stream_fps',) else 'ascending',reason=reason,parameters=provenance(method,parameters,profile),source_role='BASE_saved_graph_and_profile' if method in METHODS else 'existing_public_completed_and_raw',tie_policy='boundary_then_case_id; source_list_order retained separately' if method in METHODS else 'unchanged original completion pair row order',target_setup_binding='same historical graph score projected to this setup' if method in METHODS else 'measured exact setup'))
            if method not in METHODS:continue
            ranked=sorted(available,key=lambda r:((-r['score'] if r['score_direction']=='descending' else r['score']),r['original_order']))
            if not ranked:
                global_rows.append(dict(model_id=model,setup_id=setup,method=method,status='unavailable',selected_case_id=None,reason=reason));continue
            top=ranked[0];best=top['score'];ties=[r['case_id'] for r in ranked if r['score']==best];key=(model,top['case_id'],setup);f=feature_index[(model,top['case_id'])];pair=pair_index.get(key);cov=coverage_index[key]
            global_rows.append(dict(model_id=model,setup_id=setup,method=method,status='available',selected_case_id=top['case_id'],score=best,graph_score_count=len(ranked),top_tie_count=len(ties),top_tied_case_ids=ties,original_order=top['original_order'],source_list_order=top['source_list_order'],part2_input_count=f['part2_input_count'],native_single_input_contract_satisfied=f['part2_input_count']==1,completed_measurement_available=pair is not None,historical_generic_statuses=sorted({r['status'] for r in cov}),native_support_status='measured' if pair else 'unsupported_by_single_input_contract' if f['part2_input_count']!=1 else 'unmeasured_capability_not_proven',quality_status=pair['native_task_quality_status'] if pair else None,native_fps=pair['native_completed_task_fps'] if pair else None,no_fallback_to_measured_candidate=True))
            if model=='yolov7_paper':
                for case in ['b009','b044','b066','b298']:
                    candidate=next((r for r in ranked if r['case_id']==case),None)
                    special.append(dict(model_id=model,setup_id=setup,method=method,case_id=case,graph_rank=ranked.index(candidate)+1 if candidate else None,score=candidate['score'] if candidate else None,completed_measurement_available=(model,case,setup) in pair_index,part2_input_count=feature_index[(model,case)]['part2_input_count']))
    write_csv(output_root/'inputs/method_candidate_scores.csv',scores);write_csv(output_root/'inputs/method_availability.csv',availability);write_csv(output_root/'tables/method_global_selection.csv',global_rows);write_csv(output_root/'tables/method_yolov7_global_context.csv',special)
    (output_root/'tables/method_score_verification.json').write_text(json.dumps(dict(graph_candidates=len(features),score_rows=len(scores),availability_rows=len(availability),model_verification=verification,normalization_scope='full original model graph candidate universe before any measured/quality filtering',new_fitted_parameters=False,system_specs_reconstructed=0),indent=2)+'\n')
    print(json.dumps(dict(graph_candidates=len(features),score_rows=len(scores),availability_rows=len(availability),global_rows=len(global_rows))))


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();analyze(a.input_root,a.source_root,a.output_root)
if __name__=='__main__':main()
