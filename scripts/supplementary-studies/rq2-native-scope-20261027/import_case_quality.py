#!/usr/bin/env python3
"""Project actual normal per-case quality receipts into portable RQ2 overlays.

The per-case normal guard and genuine capture are authoritative independently of
an outer quality-only workflow's FPS-normalizer exit code. Existing FPS remains
unchanged and requires the scoped reuse relation; no outcome selects evidence.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rq2_case_assembly', HERE / 'assemble_inputs.py')
assembly = importlib.util.module_from_spec(spec); spec.loader.exec_module(assembly)
engine = assembly.engine


def checked(descriptor):
    path = Path(descriptor['path'])
    if engine.sha(path) != descriptor['sha256']:
        raise ValueError('Referenced case evidence hash differs: ' + str(path))
    return engine.read(path)


def pointer(payload, value):
    for key in value.strip('/').split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        payload = payload[int(key)] if isinstance(payload, list) else payload[key]
    return payload


def compact(value):
    if isinstance(value, dict):
        return {key: dict(omitted_binary_payload=True, base64_character_count=len(item),
                         base64_text_sha256=hashlib.sha256(item.encode()).hexdigest())
                if key.endswith('_base64') and isinstance(item, str) else compact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def project(followup, case_indices, derivation_path, output, observations_path=None):
    followup, output = Path(followup).resolve(), Path(output).resolve()
    observations_path = Path(observations_path) if observations_path else engine.REPO / engine.INPUT
    selected = {row['generic_uid']: row for row in engine.read(observations_path)['rows']}
    reuse_path = followup / 'current_observations/fps_reuse_after_quality_fix.json'
    reuse = engine.read(reuse_path)
    if reuse['status'] != 'PASS' or not reuse['product_review']['preprocessing_and_completion_runtime_functions_unchanged']:
        raise ValueError('Existing selected FPS reuse relation is unresolved')
    relations = {row['generic_uid']: row for row in reuse['rows']}
    derivation_path = Path(derivation_path).resolve()
    derivation = engine.read(derivation_path)
    if derivation['normal_source_admission'] is not True or derivation['normal_selected_dependency_proof'] is not True:
        raise ValueError('Corrected quality source admission is incomplete')
    by_case = {row['case']: row for row in derivation['config_derivations']}
    rows, proofs = [], []
    for index_path in map(Path, case_indices):
        index_path = index_path.resolve(); index = engine.read(index_path)
        uid = index['generic_uid']; original = selected[uid]; relation = relations.get(uid)
        if relation is None:
            raise ValueError('No affected-case FPS reuse authority for ' + uid + '; supply its independent normal FPS/quality relation instead')
        if index['normal_final_guard_completed'] is not True or index['quality_outcome_filter_applied'] is not False:
            raise ValueError('Normal final guard or outcome-independent selection is unresolved: ' + uid)
        if relation['exceptions'] or relation['fps_recapture_required'] is not False:
            raise ValueError('Existing scoped FPS reuse relation has exceptions: ' + uid)
        if (relation['performance_source_sha256'], relation['fps_completed_at']) != (
                original['performance_source_sha256'], original['completed_at']):
            raise ValueError('Reuse proof is not the selected actual FPS observation: ' + uid)
        actual_artifacts = {item['role']: item['sha256'] for item in index['actual_runtime_artifacts']}
        for key, role in [('part1_sha256', 'stage1_runtime'), ('part2_engine_sha256', 'stage2_runtime')]:
            if actual_artifacts.get(role) != original['artifacts'][key] or relation['runtime_artifacts'][key] != original['artifacts'][key]:
                raise ValueError('Actual quality/FPS artifact mismatch: ' + uid)
        actual = checked(index['actual_published_result'])
        normal_row = checked(index['quality_row'])
        admission = checked(index['own_normal_row_revalidation'])
        receipt = checked(index['completion_receipt'])
        source = checked(index['actual_capture_source_closure']['source'])
        capture = pointer(source, index['actual_capture_source_closure']['json_pointer'])
        corrected = by_case[original['case_id']]
        if (corrected['scientific_fields_and_original_artifacts_unchanged'] is not True
                or corrected['only_changed_field'] != 'runtime_source_files'
                or corrected['corrected_config']['sha256'] != index['quality_config']['sha256']):
            raise ValueError('Corrected configuration changed scientific task fields: ' + uid)
        if corrected['normal_sourcefreeze']['sha256'] != index['fixed6ac_sourcefreeze']['sha256']:
            raise ValueError('Corrected capture uses a different source freeze: ' + uid)
        checked(index['quality_config']); checked(index['fixed6ac_sourcefreeze'])
        identity = normal_row['identity']
        for key, expected in [('case_id', original['case_id']), ('model_id', original['model']), ('setup_id', original['setup_id']),
                              ('precision', original['execution_precision'])]:
            if identity.get(key) != expected or capture['identity'].get(key) != expected:
                raise ValueError('Actual normal quality identity differs: ' + uid + ': ' + key)
        if (admission['result_sha256'] != index['actual_published_result']['sha256']
                or admission['request_sha256'] != index['quality_request']['sha256']
                or capture['request']['sha256'] != index['quality_request']['sha256']
                or capture['candidate']['sha256'] != index['quality_candidate']['sha256']):
            raise ValueError('Actual source request/result relationship differs: ' + uid)
        binding = admission['completed_quality_binding']
        if (binding['all_actual_completed_records_verified'] is not True or binding['image_count'] != 5000
                or capture['image_count'] != 5000 or capture['performance_claims_emitted'] is not False
                or binding['evidence_sha256'] != capture['completion_evidence_sha256']):
            raise ValueError('Actual complete-task capture is not verified: ' + uid)
        if actual['implementation_runner_sha256'] != index['actual_generated_runner_sha256']:
            raise ValueError('Actual quality runner differs from admitted capture: ' + uid)
        if (actual['producer_identity_sha256'] != admission['producer_identity_sha256']
                or capture['producer_identity_sha256'] != admission['producer_identity_sha256']):
            raise ValueError('Actual producer identity differs: ' + uid)
        if (receipt['generic_uid'] != uid or receipt['normal_final_source_guard_completed'] is not True
                or receipt['normal_published_case_result']['sha256'] != index['actual_published_result']['sha256']
                or receipt['timing']['service_completion_observed_at'] != index['quality_completed_at']):
            raise ValueError('Actual per-case publication receipt differs: ' + uid)
        if actual.get('model_sha256') != original['model_sha256'] or actual.get('source_model_sha256') != original['model_sha256']:
            raise ValueError('Actual quality/reference model content differs: ' + uid)
        primary = actual['primary']
        if primary['n'] != 5000 or primary['bootstrap_repetitions'] != 1000 or primary['status'] != 'completed':
            raise ValueError('Normal quality observation is incomplete: ' + uid)
        proof = dict(generic_uid=uid, original_case_index_sha256=engine.sha(index_path),
            case_index=index, own_normal_quality_row=normal_row, own_normal_admission=compact(admission),
            actual_published_result=actual, completion_receipt=receipt, actual_capture_evidence=capture,
            actual_capture_source_sha256=index['actual_capture_source_closure']['source']['sha256'],
            existing_selected_FPS_relation=relation, existing_selected_FPS_relation_file_sha256=engine.sha(reuse_path),
            corrected_config_derivation=corrected, corrected_config_derivation_file_sha256=engine.sha(derivation_path),
            scientific_scope='Actual normal quality capture and its selected existing FPS relation only; no new FPS, energy or whole-workflow PASS claim.')
        quality = dict(verified=True, evidence_sha256=index['actual_published_result']['sha256'],
            proof_type='normal_current_ledger', ledger_row_sha256=assembly.canonical_hash(normal_row),
            normal_admission_sha256=index['own_normal_row_revalidation']['sha256'],
            product_identity_verified=True, runtime_artifacts_and_inputs_bound=True, dataset_reference_evaluator_bound=True,
            reference_runtime='cpu_onnx', normal_admission=admission['quality_eligible'],
            value=primary['candidate'], reference=primary['reference'], product_identity=engine.product_identity(original),
            artifacts=copy.deepcopy(original['artifacts']), model_sha256=original['model_sha256'],
            quality_policy_sha256=actual['policy_sha256'], candidate_predictions_sha256=actual['candidate_predictions_sha256'],
            reference_predictions_sha256=actual['reference_predictions_sha256'], dataset_manifest_sha256=admission['dataset_manifest_sha256'],
            image_ids_sha256=actual['validation_image_ids_sha256'], annotations_sha256=actual['annotations_sha256'],
            actual_generated_runner_sha256=index['actual_generated_runner_sha256'],
            selected_FPS_runtime_equivalence_proof_sha256=engine.sha(reuse_path),
            normal_exclusion_reasons=[] if admission['quality_eligible'] else ['actual_normal_quality_gate_failed'])
        rows.append(dict(generic_uid=uid, performance_source_sha256=original['performance_source_sha256'],
            quality_completed_at=index['quality_completed_at'], quality_acquisition_origin=index['quality_acquisition_origin'],
            source_capture_evidence=copy.deepcopy(index['actual_capture_source_closure']), quality_binding=quality))
        proofs.append(assembly.portable(proof, followup))
    payload = dict(schema='rq2-actual-normal-quality-overlay-v1', rows=rows, proofs=proofs,
        selection_policy='Actual completed normal per-case observations; preserve FAIL; no outcome filtering.',
        outer_quality_workflow_status='Not promoted to PASS; this projection validates actual case capture, normal quality admission and FPS reuse independently.')
    engine.write_json(output, assembly.portable(payload, followup))
    return payload


def project_typed(followup, portable_path, receipt_path, accepted_path, output, observations_path=None):
    """Reuse an already completed normal typed admission without invoking it again."""
    followup = Path(followup).resolve()
    portable_path, receipt_path, accepted_path = map(lambda path: Path(path).resolve(), (portable_path, receipt_path, accepted_path))
    typed, receipt, accepted = map(engine.read, (portable_path, receipt_path, accepted_path))
    if typed['typed_import_receipt_sha256'] != engine.sha(receipt_path) or typed['accepted_rows_sha256'] != engine.sha(accepted_path):
        raise ValueError('Typed portable projection source hashes differ')
    if accepted.get('typed_import_receipt'):
        if accepted['typed_import_receipt']['sha256'] != engine.sha(receipt_path):
            raise ValueError('Accepted rows use a different normal typed receipt')
    elif receipt.get('accepted_quality_rows', {}).get('sha256') != engine.sha(accepted_path):
        raise ValueError('Normal typed receipt does not bind the accepted rows')
    if receipt['FPS_values_repeats_attempts_and_source_authorities_unchanged'] is not True:
        raise ValueError('Quality-only typed admission changed selected FPS')
    if typed.get('new_Generic_FPS_observations') != 0 or typed.get('Native_or_Full_or_energy_observations_changed') is not False:
        raise ValueError('Historical quality import changed other observations')
    existing = engine.read(observations_path or engine.REPO / engine.INPUT)['rows']
    by_source = {(row['generic_uid'], row['performance_source_sha256']): row for row in existing}
    accepted_rows = {row['generic_uid']: row for row in accepted['rows']}
    rows = []
    for projection in typed['rows']:
        uid = projection['generic_uid']; normal = accepted_rows[uid]
        source_sha = projection['original_FPS_result_sha256']
        original = by_source[(uid, source_sha)]
        relation = normal['historical_completed_operator_quality_relation']
        if relation['fps_result']['sha256'] != source_sha:
            raise ValueError('Typed admission FPS source relation differs: ' + uid)
        for key in ['model_sha256', 'boundary_id', 'case_id', 'setup_id']:
            if normal[key] != original[key] or projection[key] != original[key]:
                raise ValueError('Typed quality product identity differs: ' + uid + ': ' + key)
        for key in ['effective_generic_fps', 'effective_repeats']:
            if normal[key] != original[key] or projection[key] != original[key]:
                raise ValueError('Typed quality changed original FPS/repetitions: ' + uid)
        metrics = normal['accuracy_gate_metrics']
        if (metrics['candidate'], metrics['reference'], metrics['n'], metrics['bootstrap_repetitions']) != (
                projection['generic_ap'], projection['generic_cpu_reference_ap'], 5000, 1000):
            raise ValueError('Typed quality numerical projection differs: ' + uid)
        if (normal['quality_eligible'], normal['quality_status']) != (projection['quality_eligible'], projection['quality_status']):
            raise ValueError('Typed quality normal admission projection differs: ' + uid)
        if relation['quality_result_sha256'] != projection['actual_published_result_sha256']:
            raise ValueError('Typed quality result identity differs: ' + uid)
        if relation['original_quality_admission']['sha256'] != projection['normal_quality_admission_sha256']:
            raise ValueError('Typed normal quality guard identity differs: ' + uid)
        capture = receipt['corrected_capture_bindings'][uid]['actual_capture_source_closure']
        if capture['source']['sha256'] != projection['normal_source_capture_status_sha256']:
            raise ValueError('Typed quality actual capture source differs: ' + uid)
        if engine.timestamp(projection['quality_completed_at']) is None:
            raise ValueError('Typed quality completion ordering is unknown: ' + uid)
        quality = dict(verified=True, evidence_sha256=projection['actual_published_result_sha256'],
            proof_type='normal_current_ledger', ledger_row_sha256=assembly.canonical_hash(normal),
            normal_admission_sha256=projection['normal_quality_admission_sha256'],
            typed_import_receipt_sha256=engine.sha(receipt_path), accepted_normal_rows_sha256=engine.sha(accepted_path),
            product_identity_verified=True, runtime_artifacts_and_inputs_bound=True, dataset_reference_evaluator_bound=True,
            reference_runtime='cpu_onnx', normal_admission=normal['quality_eligible'],
            value=metrics['candidate'], reference=metrics['reference'], product_identity=engine.product_identity(original),
            artifacts=copy.deepcopy(original['artifacts']), model_sha256=original['model_sha256'],
            quality_policy_sha256=projection['quality_policy_sha256'],
            legacy_1pct_decision=projection.get('original_1pct_test_decision', normal.get('accuracy_gate_decision')),
            legacy_1pct_margin_absolute_ap=metrics.get('margin'), legacy_1pct_ci_low=metrics.get('ci_low'),
            legacy_1pct_ci_high=metrics.get('ci_high'), legacy_1pct_decision_basis=metrics.get('decision_basis'),
            runtime_reporting_provenance=relation.get('runtime_reporting_provenance'),
            source_epochs={key: projection[key] for key in ['controller_source_commit', 'controller_sourcefreeze_sha256',
                'central_consumer_source_commit', 'central_consumer_sourcefreeze_sha256', 'hardware_producer_source_commit',
                'hardware_producer_sourcefreeze_sha256', 'normal_central_source_publication_sha256'] if projection.get(key)},
            normal_exclusion_reasons=[] if normal['quality_eligible'] else ['actual_normal_quality_gate_failed'])
        rows.append(dict(generic_uid=uid, performance_source_sha256=source_sha,
            quality_completed_at=projection['quality_completed_at'], quality_acquisition_origin=projection['quality_acquisition_origin'],
            source_capture_evidence=capture, quality_binding=quality))
    payload = dict(schema='rq2-actual-normal-quality-overlay-v1', rows=rows,
        typed_authority=dict(portable_projection_sha256=engine.sha(portable_path), receipt_sha256=engine.sha(receipt_path),
            accepted_rows_sha256=engine.sha(accepted_path), receipt=receipt, accepted_rows=accepted, portable_projection=typed),
        selection_policy='Already completed normal typed quality admissions; exact numerical/source crosschecks, no new import or outcome filtering.',
        full_workflow_PASS_claimed=False, new_FPS_claimed=False)
    engine.write_json(output, assembly.portable(payload, followup))
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--followup', type=Path, required=True)
    parser.add_argument('--case-index', type=Path, action='append', default=[])
    parser.add_argument('--derivation', type=Path)
    parser.add_argument('--typed-portable-overlay', type=Path)
    parser.add_argument('--typed-receipt', type=Path)
    parser.add_argument('--accepted-rows', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observations', type=Path)
    args = parser.parse_args()
    if args.typed_portable_overlay:
        if not args.typed_receipt or not args.accepted_rows:
            parser.error('Typed projection requires --typed-receipt and --accepted-rows')
        result = project_typed(args.followup, args.typed_portable_overlay, args.typed_receipt, args.accepted_rows, args.output, args.observations)
    else:
        if not args.case_index or not args.derivation:
            parser.error('Case projection requires --case-index and --derivation')
        result = project(args.followup, args.case_index, args.derivation, args.output, args.observations)
    print(json.dumps(dict(rows=len(result['rows']), generic_uids=[row['generic_uid'] for row in result['rows']]), indent=2))
