#!/usr/bin/env python3
"""Project a normally accepted fresh Generic FPS and own quality without Native inference."""
from __future__ import annotations

import argparse
import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rq2_fresh_projection_helpers', HERE / 'import_case_quality.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
engine, assembly = helpers.engine, helpers.assembly


def project(followup, portable_path, receipt_path, accepted_path, performance_output, quality_output, observations_path=None):
    followup = Path(followup).resolve()
    portable_path, receipt_path, accepted_path = map(Path, (portable_path, receipt_path, accepted_path))
    portable, receipt, accepted = map(engine.read, (portable_path, receipt_path, accepted_path))
    receipt_sha = engine.sha(receipt_path)
    if portable['normal_import_receipt_sha256'] != receipt_sha or receipt['accepted_rows']['sha256'] != engine.sha(accepted_path):
        raise ValueError('Fresh normal FPS/quality accepted source hashes differ')
    if portable['generic_only_relabelled'] is not False or receipt['generic_only_relabelled'] is not False:
        raise ValueError('A legacy completed-task observation cannot be relabelled Generic-only')
    if receipt['Native_performance_or_quality_admission_inferred'] is not False:
        raise ValueError('Fresh Generic authority cannot infer original Native authority')
    if portable['Native_or_Full_or_energy_observations_changed'] is not False or portable['historical_configuration_equality_claimed'] is not False:
        raise ValueError('Fresh Generic observation changed preserved records or asserted historical configuration equality')
    sources = receipt['normal_sources']
    raw = helpers.checked(sources['actual_result'])
    terminal, cleanup = helpers.checked(sources['terminal']), helpers.checked(sources['cleanup'])
    quality_case = helpers.checked(sources['quality_case'])
    quality_result = helpers.checked(sources['quality_reference']['result'])
    if terminal['status'] != 'complete' or terminal['exitcode'] != 0 or cleanup['active_owned_remote_operations'] != 0:
        raise ValueError('Fresh normal FPS terminal or cleanup is incomplete')
    repetitions = raw['repetitions']
    if len(repetitions) != 3 or len({row['pid'] for row in repetitions}) != 3:
        raise ValueError('Fresh FPS needs three independent actual processes')
    if any(row['warmup_completed_count'] != 100 or row['completed_task_count'] != 1000 or row['postprocess_timed'] is not True for row in repetitions):
        raise ValueError('Fresh FPS complete-task measurement contract differs')
    observations = engine.read(observations_path or engine.REPO / engine.INPUT)['rows']
    patches, quality_patches = [], []
    for projected in portable['rows']:
        uid = projected['generic_uid']
        row = next(row for row in accepted['rows'] if row['generic_uid'] == uid)
        original = min((row for row in observations if row['generic_uid'] == uid), key=lambda row: engine.timestamp(row['completed_at']))
        if (float(row['effective_generic_fps']), [float(value) for value in row['effective_repeats']]) != (
                projected['generic_fps'], projected['generic_fps_repetitions']):
            raise ValueError('Fresh FPS projection differs from accepted normal row')
        if raw['completed_task_fps_median'] != projected['generic_fps'] or [rep['completed_task_fps'] for rep in repetitions] != projected['generic_fps_repetitions']:
            raise ValueError('Fresh actual FPS result/repetitions differ from normal projection')
        if sources['actual_result']['sha256'] != projected['actual_FPS_result_sha256']:
            raise ValueError('Fresh FPS source identity differs')
        for key in ['model_sha256', 'boundary_id', 'case_id', 'setup_id']:
            if row[key] != original[key] or projected[key] != original[key]:
                raise ValueError('Fresh Generic model/device/cut identity differs: ' + key)
        authority = row['actual_artifact_authority']
        artifacts = copy.deepcopy(original['artifacts'])
        artifacts.update(part1_sha256=authority['part1']['sha256'],
            part2_engine_sha256=authority['part2_engine_observation']['artifact']['sha256'])
        for key in ['part1_sha256', 'part2_engine_sha256']:
            if artifacts[key] != original['artifacts'][key]:
                raise ValueError('Fresh Generic executable differs from existing bound product: ' + key)
        metrics = row['accuracy_gate_metrics']
        if (metrics['candidate'], metrics['reference'], metrics['n'], metrics['bootstrap_repetitions']) != (
                projected['generic_ap'], projected['generic_cpu_reference_ap'], 5000, 1000):
            raise ValueError('Fresh actual normal quality numerical projection differs')
        if (quality_result['primary']['candidate'], quality_result['primary']['reference']) != (metrics['candidate'], metrics['reference']):
            raise ValueError('Fresh actual quality result differs from accepted normal quality')
        if quality_case['quality_completed_at'] != projected['quality_completed_at'] or engine.timestamp(raw['completed_at']) is None:
            raise ValueError('Fresh actual FPS/quality completion ordering is unknown')
        epoch_keys = ['controller_source_commit', 'hardware_producer_source_commit', 'central_consumer_source_commit']
        epochs = {key: projected[key] for key in epoch_keys if projected.get(key)}
        epochs.update(controller_sourcefreeze_sha256=sources['source_freeze']['sha256'],
                      hardware_producer_sourcefreeze_sha256=sources['fixed_runtime_sourcefreeze']['sha256'])
        contract = dict(valid=True, contract_evidence_sha256=receipt_sha, proof_type='normal_current_ledger',
            ledger_row_sha256=assembly.canonical_hash(row), identity_verified=True, complete_task_verified=True,
            independent_processes=3, warmups_per_process=100, completed_tasks_per_process=1000, full_postprocessing=True,
            complete_task_contract_sha256=raw['completion_contract']['contract_sha256'],
            preprocessing_sha256=raw['input_binding']['preprocessing_contract_sha256'], product_identity=engine.product_identity(original),
            normal_FPS_API=receipt['normal_FPS_API'], measurement_mode=projected['measurement_mode'], scope_mode=projected['scope_mode'])
        patch = dict(generic_uid=uid, completed_at=raw['completed_at'], performance_source_sha256=sources['actual_result']['sha256'],
            effective_generic_fps=row['effective_generic_fps'], effective_repeats=row['effective_repeats'], artifacts=artifacts,
            full_product_identity=row['full_product_identity'], execution_precision=row['execution_precision'],
            observation_mode='normal_legacy_completed_task_new_measurement', admission_mode='normal_legacy_completed_task_new_measurement',
            measurement_status=row['measurement_status'], performance_acquisition_origin=projected['performance_acquisition_origin'],
            observation_contract=contract, source_epochs=epochs,
            pair_compatibility=copy.deepcopy(original['pair_compatibility']))
        own_quality = dict(verified=True, evidence_sha256=projected['actual_published_quality_result_sha256'],
            proof_type='normal_current_ledger', ledger_row_sha256=assembly.canonical_hash(row), normal_admission_sha256=projected['normal_quality_admission_sha256'],
            normal_Quality_API=receipt['normal_Quality_API'], normal_legacy_import_receipt_sha256=receipt_sha,
            product_identity_verified=True, runtime_artifacts_and_inputs_bound=True, dataset_reference_evaluator_bound=True,
            reference_runtime='cpu_onnx', normal_admission=row['quality_eligible'], value=metrics['candidate'], reference=metrics['reference'],
            product_identity=engine.product_identity(patch | dict(model_sha256=row['model_sha256'], setup_id=row['setup_id'])), artifacts=artifacts,
            source_epochs=epochs, legacy_1pct_decision=projected['original_1pct_test_decision'],
            legacy_1pct_margin_absolute_ap=metrics['margin'], legacy_1pct_ci_low=metrics['ci_low'], legacy_1pct_ci_high=metrics['ci_high'],
            normal_exclusion_reasons=[] if row['quality_eligible'] else ['actual_normal_quality_gate_failed'])
        quality_patches.append(dict(generic_uid=uid, performance_source_sha256=patch['performance_source_sha256'],
            quality_completed_at=projected['quality_completed_at'], quality_acquisition_origin=projected['quality_acquisition_origin'],
            source_capture_evidence=quality_case['actual_capture_source_closure'], quality_binding=own_quality))
        patches.append(patch)
    proof = dict(normal_receipt=receipt, accepted_rows=accepted, actual_FPS_result=raw, actual_terminal=terminal, actual_cleanup=cleanup,
        actual_quality_case_index=quality_case, actual_quality_result=quality_result, portable_projection=portable,
        receipt_sha256=receipt_sha, accepted_rows_sha256=engine.sha(accepted_path), portable_projection_sha256=engine.sha(portable_path))
    engine.write_json(performance_output, assembly.portable(dict(schema='rq2-normal-fresh-legacy-performance-overlay-v1', rows=patches, proofs=helpers.compact(proof)), followup))
    engine.write_json(quality_output, assembly.portable(dict(schema='rq2-normal-fresh-legacy-own-quality-overlay-v1', rows=quality_patches,
        performance_overlay_sha256=engine.sha(performance_output), normal_receipt_sha256=receipt_sha), followup))
    return patches, quality_patches


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--followup', type=Path, required=True)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--accepted-rows', type=Path, required=True)
    parser.add_argument('--performance-output', type=Path, required=True)
    parser.add_argument('--quality-output', type=Path, required=True)
    args = parser.parse_args()
    project(args.followup, args.portable, args.receipt, args.accepted_rows, args.performance_output, args.quality_output)
