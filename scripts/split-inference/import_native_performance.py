#!/usr/bin/env python3
"""Project a completed normal Native FPS receipt without inferring Q or energy."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from current_observations import HOSTS, canonical_sha


def read(path):
    return json.loads(Path(path).read_text())


def checked(descriptor):
    path = Path(descriptor['path'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
        raise ValueError('Normal Native source hash differs: ' + str(path))
    if descriptor.get('size_bytes') is not None and len(raw) != descriptor['size_bytes']:
        raise ValueError('Normal Native source size differs: ' + str(path))
    return json.loads(raw)


def portable(value, followup):
    if isinstance(value, dict):
        return {key:(item if key=='pointer' or key.endswith(('_pointer','_pointers')) else portable(item, followup))
                for key,item in value.items()}
    if isinstance(value, list):
        return [portable(item, followup) for item in value]
    if isinstance(value, str) and value.startswith(('/home/','/homes/','/mnt/','/tmp/','/usr/','/opt/','/var/')):
        path = Path(value)
        if path.is_relative_to(followup):
            return 'followup_source::' + str(path.relative_to(followup))
        return 'retained_source::' + path.name
    return value


def project(receipt_path, output_path, followup):
    receipt_path, output_path, followup = Path(receipt_path), Path(output_path), Path(followup)
    receipt = read(receipt_path)
    if receipt.get('schema') != 'six-pack-normal-native-three-process-FPS-import-receipt-v1':
        raise ValueError('Unsupported normal Native FPS receipt')
    if receipt['normal_product_entrypoint'] != 'scripts/native_producer_final_report.py':
        raise ValueError('Native source was not admitted by the normal Product reader')
    summary = checked(receipt['normal_summary'])
    row = summary['rows'][0]
    if receipt['normal_summary']['json_pointer'] != '/rows/0' or canonical_sha(row) != receipt['normal_summary']['normal_row_sha256']:
        raise ValueError('Normal Native row binding differs')
    checks = dict(status='ok', ok=True, repetition_count_valid=3,
        repetition_claim_identity_status='exact', native_split_final_portable_binding_valid=True,
        repetition_independence_verified=True)
    if any(row.get(key) != value for key,value in checks.items()):
        raise ValueError('Normal Native observation is diagnostic, incomplete or unbound')
    # Keep actual capture/normal-import chronology separate. A completed FPS
    # source does not establish the still-pending fresh quality or energy.
    for name in ['normal_import_action', 'actual_capture_action', 'cleanup', 'current_preprocessing', 'sourcefreeze']:
        checked(receipt[name])
    repetitions, raw_sources, pids, runtime_ids = [], [], [], []
    raw_keys = ['fps_makespan', 'warmup', 'completed_frames', 'completed_work_units',
        'warmup_contract', 'runtime_instance_id', 'postprocess_included',
        'postprocess_completed_frames', 'postprocess_completion_verified',
        'completion_execution_contract_sha256', 'completed_task_endpoint_contract_hash',
        'completed_task_comparison_endpoint_contract_hash', 'timing_input_binding', 'precision',
        'completed_task_completion_mode', 'measurement_boundary']
    command_keys = ['backend', 'model', 'setup_id', 'case', 'precision', 'runner_sha256',
        'hef_sha256', 'engine_sha256', 'native_executable_sha256', 'input_image_sha256',
        'prepared_input_contract']
    for source in receipt['repeats']:
        raw = checked(source['raw_report'])
        if (raw.get('ok') is not True or raw['completed_frames'] != 1000 or raw['warmup'] != 100
                or raw['postprocess_completed_frames'] != 1000 or raw['postprocess_included'] is not True
                or raw['postprocess_completion_verified'] is not True):
            raise ValueError('Actual Native 100/1000 complete-task measurement differs')
        if raw['native_command_contract']['runner_sha256'] != receipt['native_runner_sha256']:
            raise ValueError('Actual Native source runner differs from the normal receipt')
        domain = raw['request_latency']['clock_domain']
        prefix = 'perf_counter_ns:process:'
        if not domain.startswith(prefix) or not domain[len(prefix):].isdigit():
            raise ValueError('Actual Native DUT process clock is unavailable')
        if raw['request_latency']['count'] != 1000 or len(raw['request_latency']['pairs']) != 1000:
            raise ValueError('Actual Native process clock lacks its complete task timestamps')
        pids.append(int(domain[len(prefix):])); runtime_ids.append(raw['runtime_instance_id'])
        projected = {key:raw[key] for key in raw_keys}
        projected['request_latency'] = {key:raw['request_latency'][key]
            for key in ['clock_domain', 'count', 'expected_count', 'status', 'task_complete']}
        projected['native_command_contract'] = {key:raw['native_command_contract'][key] for key in command_keys}
        projected['model_sha256'] = raw['completed_task_endpoint_contract']['model_sha256']
        projected['actual_source_sha256'] = source['raw_report']['sha256']
        repetitions.append(projected); raw_sources.append(source['raw_report'])
    if len(repetitions) != 3 or len(set(pids)) != 3 or len(set(runtime_ids)) != 3:
        raise ValueError('Actual Native processes/runtimes are not three independent observations')
    rates = [rep['fps_makespan'] for rep in repetitions]
    if statistics.median(rates) != row['fps_median'] or row['fps_median'] != receipt['fps_median']:
        raise ValueError('Normal Native median differs from its exact actual repetitions')
    command = repetitions[0]['native_command_contract']
    for rep in repetitions:
        actual = rep['native_command_contract']
        if any(actual[key] != command[key] for key in ['backend','model','setup_id','case','precision','hef_sha256','engine_sha256']):
            raise ValueError('Actual Native repeated executable identity drifted')
    setups = {value:key for key,value in HOSTS.items()}
    setup = setups[command['setup_id']]
    uid = '|'.join(['native', command['model'], setup, command['backend'], command['case']])
    projection = dict(schema='normal-native-three-process-performance-projection-v1',
        identity=dict(uid=uid, model_id=command['model'], setup_id=setup, physical_host=command['setup_id'],
            backend=command['backend'], case_id=command['case'], runner='native', kind='split',
            model_sha256=repetitions[0]['model_sha256']),
        normal_receipt=receipt, normal_row={key:row[key] for key in checks},
        source_epochs=dict(reported_source_commit=receipt['source_commit'],
            native_runner_sha256=receipt['native_runner_sha256'],
            sourcefreeze_sha256=receipt['sourcefreeze']['sha256']),
        repetitions=repetitions,
        upstream=dict(receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            normal_summary=receipt['normal_summary'], raw_reports=raw_sources),
        current_quality_or_energy_admission_inferred=False,
        prior_diagnostic_attempts_retained=receipt['previous_attempts_preserved'])
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(portable(projection, followup), indent=2, sort_keys=True, allow_nan=False)+'\n')
    return projection


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--followup', type=Path, required=True)
    args = parser.parse_args()
    project(args.receipt,args.output,args.followup)
