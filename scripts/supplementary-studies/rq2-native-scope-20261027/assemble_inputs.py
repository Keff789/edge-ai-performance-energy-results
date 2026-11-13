#!/usr/bin/env python3
"""Assemble portable provisional RQ2 inputs and apply current bound quality overlays."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rq2_input_engine', HERE / 'reproduce.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def portable(value, followup):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            projected_key = portable(key, followup) if isinstance(key, str) else key
            if projected_key in result:
                raise ValueError('Portable source locator key collision')
            result[projected_key] = portable(item, followup)
        return result
    if isinstance(value, list):
        return [portable(item, followup) for item in value]
    if isinstance(value, str) and value.startswith(('/home/', '/homes/', '/mnt/')):
        path = Path(value)
        try:
            return 'followup_source::' + str(path.relative_to(followup))
        except ValueError:
            parts = path.parts
            anchors = ['Reports', 'diss_results', 'models', 'splitpoint_runs']
            positions = [parts.index(anchor) for anchor in anchors if anchor in parts]
            return 'retained_source::' + '/'.join(parts[min(positions):] if positions else parts[-3:])
    if isinstance(value, str):
        return re.sub(r"/(?:home|homes|mnt)/[^\s\"'<>`\)\]]+", lambda match: portable(match.group(), followup), value)
    return value


def copy_projection(source, target, followup, manifest):
    payload = engine.read(source)
    engine.write_json(target, portable(payload, followup))
    manifest.append(dict(input_file=target.name, source_locator=portable(str(source), followup),
        original_source_sha256=engine.sha(source), portable_projection_sha256=engine.sha(target)))
    return engine.read(target)


def retain_performance_candidate(pool, baseline, patch, acquisition_source_sha256):
    """Retain distinct actual observations; Native compatibility is selected later."""
    uid = baseline['generic_uid']
    for key in ['performance_source_sha256', 'completed_at', 'effective_generic_fps', 'effective_repeats', 'artifacts', 'observation_contract']:
        if key not in patch:
            raise ValueError('Performance overlay missing ' + key + ': ' + uid)
    if patch['generic_uid'] != uid:
        raise ValueError('Performance candidate identity differs: ' + uid)
    origin = patch.get('performance_acquisition_origin', 'unknown')
    if origin not in ['new_capture', 'reused_existing', 'unknown']:
        raise ValueError('Unknown performance acquisition origin: ' + origin)
    if engine.timestamp(patch['completed_at']) is None:
        raise ValueError('Performance observation completion time unavailable: ' + uid)
    source_sha = patch['performance_source_sha256']
    previous = pool.get(source_sha)
    if previous and previous.get('completed_at') != patch['completed_at']:
        raise ValueError('Same actual FPS source has conflicting completion times: ' + uid)
    candidate = copy.deepcopy(previous if previous is not None else baseline)
    if previous is None:
        for key in ['quality_completed_at', 'quality_acquisition_origin', 'quality_acquisition_source_sha256', 'source_capture_evidence']:
            if key not in patch:
                candidate.pop(key, None)
    candidate.update(copy.deepcopy(patch))
    if previous is None and 'quality_binding' not in patch:
        candidate['quality_binding'] = dict(verified=False, normal_admission=False,
            proof_type='corrected_normal_quality_pending', normal_exclusion_reasons=['fresh_performance_quality_binding_pending'])
        candidate['quality_correction'] = dict(status='pending', reason='New FPS candidate has no matching quality observation yet')
    pair_held = candidate.get('pair_compatibility', {}).get('verified') is False
    reasons = [reason for reason in engine.contract_reasons(candidate)
               if not (pair_held and reason.startswith('generic_native_pair_compatibility_unresolved:'))]
    if reasons:
        raise ValueError('Fresh performance contract not admitted: ' + uid + ': ' + ','.join(reasons))
    candidate['performance_acquisition_origin'] = origin
    candidate['performance_acquisition_source_sha256'] = acquisition_source_sha256
    candidate['observation_origin'] = 'remeasured' if origin == 'new_capture' else 'recovered'
    pool[source_sha] = candidate
    return candidate


def assemble(followup, output, quality_overlays=(), performance_overlays=(), typed_admissions=(), provenance_overlays=()):
    followup, output = Path(followup).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    projections = []
    current = copy_projection(followup / 'current_observations/candidate_generic_observations.json', output / 'current_generic_observations.json', followup, projections)
    extra = copy_projection(followup / 'extra_sources/public_projection/candidate_generic_observations.json', output / 'extra_generic_observations.json', followup, projections)
    copy_projection(followup / 'current_observations/proofs.json', output / 'current_observation_proofs.json', followup, projections)
    copy_projection(followup / 'current_observations/validation.json', output / 'current_observation_validation.json', followup, projections)
    reuse = followup / 'current_observations/fps_reuse_after_quality_fix.json'
    if reuse.is_file():
        copy_projection(reuse, output / 'current_fps_reuse_after_quality_fix.json', followup, projections)
    names = {'observation_proofs.json':'extra_observation_proofs.json', 'quality_proofs.json':'extra_quality_proofs.json',
             'PROJECTION_MANIFEST.json':'extra_projection_manifest.json'}
    for source in sorted((followup / 'extra_sources/public_projection').glob('*.json')):
        if source.name == 'candidate_generic_observations.json':
            continue
        copy_projection(source, output / names.get(source.name, 'extra_' + source.name), followup, projections)
    affected = copy_projection(followup / 'quality_audit/AFFECTED_SCOPE.json', output / 'quality_affected_scope.json', followup, projections)
    copy_projection(followup / 'quality_audit/AFFECTED_SCOPE_VALIDATION.json', output / 'quality_affected_scope_validation.json', followup, projections)
    policy = followup / 'OBSERVATION_POLICY_v1.json'
    shutil.copyfile(policy, output / 'OBSERVATION_POLICY_v1.json')
    projections.append(dict(input_file='OBSERVATION_POLICY_v1.json', original_source_sha256=engine.sha(policy), portable_projection_sha256=engine.sha(output / policy.name)))
    records = {row['generic_uid']: copy.deepcopy(row) for row in current['rows'] + extra['rows']}
    if len(records) != len(current['rows']) + len(extra['rows']):
        raise ValueError('Original current and recovered observations overlap; merge actual observation identity explicitly')
    if affected.get('summary', {}).get('AP_or_outcome_used_for_scope') is not False:
        raise ValueError('Affected implementation scope must be derived independently of AP or admission outcomes')
    original_affected_sha = engine.sha(followup / 'quality_audit/AFFECTED_SCOPE.json')
    affected_uids = {row['uid'] for row in affected['rows'] if row['classification'] == 'affected'}
    for uid in affected_uids:
        if uid not in records:
            continue
        row = records[uid]
        row['quality_history'] = [dict(quality_binding=copy.deepcopy(row.get('quality_binding')),
            quality_status=row.get('quality_status'), quality_value=row.get('quality_value'),
            quality_reference_value=row.get('quality_reference_value'), historical_only=True,
            invalidated_for_current_runtime=True, invalidation_evidence_sha256=original_affected_sha,
            reason='demonstrated_generic_quality_physical_layout_assignment_error')]
        row['quality_binding'] = dict(verified=False, normal_admission=False,
            proof_type='corrected_normal_quality_pending', evidence_sha256=original_affected_sha,
            normal_exclusion_reasons=['corrected_normal_N5000_quality_pending', 'demonstrated_generic_quality_physical_layout_assignment_error'])
        row.update(quality_eligible=False, quality_status='unavailable_corrected_quality_pending',
                   quality_value=None, quality_reference_value=None, quality_relative_loss=None)
        row['quality_correction'] = dict(status='pending', affected_scope_source_sha256=original_affected_sha,
            FPS_preserved=True, reason='Quality assignment implementation changed; selected timed FPS runtime and complete-task contract unchanged')
    closure_path = followup.parent / 'postprocess_rq3_20261027/closure_b009.json'
    if closure_path.is_file():
        closure = copy_projection(closure_path, output / 'historical_b009_preprocessing_closure.json', followup, projections)
        uid = closure['generic_uid']
        if uid in records and closure.get('unchanged_normal_preprocessing_guard_passes') is False:
            row = records[uid]
            row['pair_compatibility'] = dict(verified=False, evidence_sha256=engine.sha(closure_path),
                reason='historical_b009_actual_preprocessing_authority_unproved; accepted standalone FPS preserved, pairing pending fresh observation')
            row['quality_correction'] = dict(status='pending', affected_scope_source_sha256=engine.sha(closure_path),
                FPS_preserved=True, reason='Fresh bound Generic FPS and corrected normal quality pending; historical standalone FPS remains preserved')
            for name in ['final_hold', 'exact_guard_receipt', 'normal_relation_receipt']:
                proof = followup.parent / closure['evidence'][name]['report_relative_path']
                if proof.is_file():
                    if engine.sha(proof) != closure['evidence'][name]['sha256']:
                        raise ValueError('Historical b009 closure proof hash differs: ' + name)
                    copy_projection(proof, output / ('historical_b009_' + name + '.json'), followup, projections)
    baseline_records = copy.deepcopy(records)
    candidates = {uid: {row['performance_source_sha256']: row} for uid, row in records.items()}
    performance_log = []
    for ordinal, path in enumerate(performance_overlays):
        source = Path(path).resolve()
        overlay = copy_projection(source, output / f'performance_overlay_{ordinal:03d}.json', followup, projections)
        for patch in overlay.get('rows', []):
            uid = patch['generic_uid']
            if uid not in records:
                raise ValueError('Performance overlay has no original Native observation: ' + uid)
            candidate = retain_performance_candidate(candidates[uid], baseline_records[uid], patch, engine.sha(source))
            records[uid] = max(candidates[uid].values(), key=lambda row: (engine.timestamp(row['completed_at']), row['performance_source_sha256']))
            performance_log.append(dict(generic_uid=uid, action='actual_performance_candidate_retained_for_compatibility_selection',
                performance_acquisition_origin=candidate['performance_acquisition_origin'], performance_source_sha256=patch['performance_source_sha256'],
                acquisition_source_sha256=engine.sha(source), completed_at=patch['completed_at']))
    completion = dict(schema='rq2-quality-and-timed-completion-provenance-v1',
        native_gate='Established original Native numerical AP/reference relative-loss gate <=5%; Native values are unchanged historical quality observations.',
        generic_gate='Normal bound Generic quality evaluates actual selected timed completion records with the existing CPU-ONNX reference and evaluator policy.',
        limitation='Historical Native quality is not asserted to measure exact selected timed Native endpoint AP. Proven additional NMS differences are scoped to the cases below; other cases are unassessed here.', cases=[])
    diagnostic_sources = [('h8_diagnostic/REAL_H8_B043_NATIVE_COMPARISON_v1.json', 'generic|yolo26m|H8|hailo8_to_trt|b043'),
                          ('h10_diagnostic/postprocess_trace_v1/POSTPROCESS_TRACE_REPORT_v1.json', 'generic|yolo26m|H10|hailo10h_to_trt|b043')]
    for name, uid in diagnostic_sources:
        source = followup / name
        if source.is_file():
            target_name = 'native_quality_completion_' + ('H8' if '|H8|' in uid else 'H10') + '_b043.json'
            evidence = copy_projection(source, output / target_name, followup, projections)
            detail = dict(generic_uid=uid, evidence_file=target_name, original_evidence_sha256=engine.sha(source),
                scope='This exact model/device/cut and evidenced source identities only; no blanket detector or population claim.',
                native_historical_quality_postfilter='additional class-aware NMS',
                native_selected_timed_completion='source-completed records with no second host NMS',
                generic_selected_timed_completion='source-completed records with no second host NMS',
                historical_native_AP_is_exact_timed_endpoint_AP=False,
                established_native_quality_gate_preserved=True)
            if '|H10|' in uid:
                detail['historical_native_quality_identity'] = evidence['historical_Native_quality']
                detail['native_timed_identity'] = evidence['measured_Native_FPS']
                detail['generic_timed_identity'] = evidence['measured_Generic_FPS']
                detail['CPU_reference_identity'] = evidence['CPU_reference_actual_runner']
                detail['CPU_reference_source_closure_caveat'] = evidence['CPU_reference_retained_vendored_harness']['caveat']
            completion['cases'].append(detail)
            if uid in records:
                for candidate in candidates[uid].values():
                    candidate['completion_provenance'] = detail
    overlay_log = []
    for ordinal, path in enumerate(quality_overlays):
        source = Path(path).resolve()
        overlay = copy_projection(source, output / f'quality_overlay_{ordinal:03d}.json', followup, projections)
        for patch in overlay.get('rows', []):
            uid = patch['generic_uid']
            if uid not in records:
                raise ValueError('Quality overlay has no original Native observation: ' + uid)
            target = patch.get('performance_source_sha256')
            row = candidates[uid].get(target)
            if row is None:
                raise ValueError('Quality overlay is not bound to an actual FPS candidate: ' + uid)
            quality_origin = patch.get('quality_acquisition_origin', 'unknown')
            if quality_origin not in ['new_capture', 'reused_existing', 'unknown']:
                raise ValueError('Unknown quality acquisition origin: ' + quality_origin)
            quality_acquisition = dict(quality_acquisition_origin=quality_origin,
                quality_evidence_sha256=patch.get('quality_binding', {}).get('evidence_sha256'),
                acquisition_source_sha256=engine.sha(source), source_capture_evidence=patch.get('source_capture_evidence'))
            observed = engine.timestamp(patch.get('quality_completed_at'))
            if observed is None:
                raise ValueError('Quality overlay completion time unavailable: ' + uid)
            prior = engine.timestamp(row.get('quality_completed_at'))
            if prior is not None and observed < prior:
                overlay_log.append(dict(generic_uid=uid, action='retained_newer_quality', quality_completed_at=patch['quality_completed_at'], **quality_acquisition))
                continue
            if prior == observed and row.get('quality_binding') != patch.get('quality_binding'):
                raise ValueError('Conflicting quality overlays have identical completion time: ' + uid)
            row.setdefault('quality_history', []).append(dict(quality_binding=copy.deepcopy(row.get('quality_binding')), superseded=True))
            row['quality_binding'] = copy.deepcopy(patch['quality_binding'])
            row['quality_completed_at'] = patch['quality_completed_at']
            row['quality_acquisition_origin'] = quality_origin
            row['quality_acquisition_source_sha256'] = engine.sha(source)
            row['source_capture_evidence'] = patch.get('source_capture_evidence')
            row['quality_correction'] = dict(status='normal_quality_observed', overlay_source_sha256=engine.sha(source), FPS_preserved=True)
            result = engine.generic_quality(row)
            row.update(quality_status=result['status'], quality_eligible=result['admitted'],
                       quality_value=result['value'], quality_reference_value=result['reference'], quality_relative_loss=result['relative_loss'])
            overlay_log.append(dict(generic_uid=uid, action='newer_actual_quality_applied', quality_completed_at=patch['quality_completed_at'], quality_status=result['status'], **quality_acquisition))
    provenance_log = []
    epoch_keys = ['controller_source_commit', 'controller_sourcefreeze_sha256', 'central_consumer_source_commit',
                  'central_consumer_sourcefreeze_sha256', 'hardware_producer_source_commit',
                  'hardware_producer_sourcefreeze_sha256', 'normal_central_source_publication_sha256']
    for ordinal, path in enumerate(provenance_overlays):
        source = Path(path).resolve()
        overlay = copy_projection(source, output / f'provenance_overlay_{ordinal:03d}.json', followup, projections)
        for patch in overlay.get('rows', []):
            uid = patch['generic_uid']
            target = patch.get('performance_source_sha256', patch.get('original_FPS_result_sha256', patch.get('actual_FPS_result_sha256')))
            row = candidates.get(uid, {}).get(target)
            if row is None:
                raise ValueError('Source-epoch provenance has no matching actual FPS candidate: ' + uid)
            evidence = patch.get('actual_published_result_sha256', patch.get('actual_published_quality_result_sha256'))
            if evidence != row.get('quality_binding', {}).get('evidence_sha256'):
                raise ValueError('Source-epoch provenance has a different actual quality source: ' + uid)
            for projected, actual_key in [('generic_ap', 'value'), ('generic_cpu_reference_ap', 'reference')]:
                if projected in patch and patch[projected] != row['quality_binding'].get(actual_key):
                    raise ValueError('Source-epoch provenance numerical identity differs: ' + uid)
            epochs = {key: patch[key] for key in epoch_keys if patch.get(key)}
            row['quality_binding']['source_epochs'] = epochs
            provenance_log.append(dict(generic_uid=uid, quality_evidence_sha256=evidence,
                source_projection_sha256=engine.sha(source), source_epochs=epochs))
    typed_authorities = []
    for ordinal, path in enumerate(typed_admissions):
        source = Path(path).resolve()
        name = f'typed_quality_admission_{ordinal:03d}.json'
        receipt = copy_projection(source, output / name, followup, projections)
        authority = dict(input_file=name, original_source_sha256=engine.sha(source),
            typed_API=receipt.get('typed_API'), result_ledger=receipt.get('result'),
            only_UIDs=receipt.get('only_UIDs', []), state=receipt.get('state'),
            FPS_values_repeats_attempts_and_source_authorities_unchanged=receipt.get('FPS_values_repeats_attempts_and_source_authorities_unchanged'))
        typed_authorities.append(authority)
        for uid in authority['only_UIDs']:
            if uid not in records:
                continue
            captured = receipt.get('corrected_capture_bindings', {}).get(uid, {}).get('actual_capture_source_closure', {}).get('source', {}).get('sha256')
            matching = [record for record in candidates[uid].values() if not captured
                        or record.get('source_capture_evidence', {}).get('source', {}).get('sha256') == captured]
            if not matching:
                raise ValueError('Typed admission is bound to a different actual quality capture: ' + uid)
            for record in matching:
                record.setdefault('typed_quality_import_authorities', []).append(authority)
    fixed = engine.read(engine.REPO / engine.legacy.INPUT)
    observation_rows = sorted((row for pool in candidates.values() for row in pool.values()),
        key=lambda row: (row['generic_uid'], engine.timestamp(row['completed_at']), row['performance_source_sha256']))
    payload = dict(schema='rq2-native-scope-observations-v1', source_snapshot_sha256=current.get('source_snapshot_sha256'),
        source_selection_sha256=fixed.get('source_selection_sha256'), fixed420_uids=sorted(row['generic_uid'] for row in fixed['rows']),
        rows=observation_rows, assembly=dict(current_rows=len(current['rows']), extra_rows=len(extra['rows']),
            original_observations=len(records), distinct_performance_observation_candidates=len(observation_rows), affected_quality_scope_uses_outcomes=affected['summary']['AP_or_outcome_used_for_scope'], affected_quality_pending=sum(row.get('quality_correction', {}).get('status') == 'pending' for row in records.values()),
            overlays=overlay_log, performance_overlays=performance_log, typed_quality_import_authorities=typed_authorities, provenance_overlays=provenance_log), completion_provenance=completion)
    engine.write_json(output / 'observations.json', payload)
    engine.write_json(output / 'quality_contract_provenance.json', completion)
    engine.write_json(output / 'SOURCE_PROJECTION_MANIFEST.json', dict(schema='rq2-native-scope-portable-source-projections-v1', sources=projections,
        observations_sha256=engine.sha(output / 'observations.json'), policy_sha256=engine.sha(output / 'OBSERVATION_POLICY_v1.json')))
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--followup', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quality-overlay', type=Path, action='append', default=[])
    parser.add_argument('--performance-overlay', type=Path, action='append', default=[])
    parser.add_argument('--typed-admission', type=Path, action='append', default=[])
    parser.add_argument('--provenance-overlay', type=Path, action='append', default=[])
    args = parser.parse_args()
    result = assemble(args.followup, args.output, args.quality_overlay, args.performance_overlay, args.typed_admission, args.provenance_overlay)
    print(json.dumps(result['assembly'], indent=2))
