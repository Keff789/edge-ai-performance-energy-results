"""Apply curated, source-bound observations to the established input dataset.

The input archive stays intact. This module resolves metric values from retained
normal result files, then replaces only the declared metrics in memory.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

IDENTITY = ('model_id', 'setup_id', 'backend', 'case_id', 'runner', 'kind')
HOSTS = {'H8':'orin_nx_hailo8_01', 'H10':'orin_nx_hailo10_01', 'DeepX':'orin_nx_deepx_m1_01'}
SCHEMA = 'current-deployment-observations-v1'


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def pointer(value, path):
    if not path:
        return value
    if not path.startswith('/'):
        raise ValueError('Evidence pointers must use JSON Pointer syntax')
    for key in path[1:].split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


class Evidence:
    def __init__(self, document, root):
        self.sources, self.values = document['sources'], {}
        root = Path(root).resolve()
        for name, source in self.sources.items():
            path = (root / source['path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Current observation source escapes its input directory')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise ValueError('Current observation source hash differs: ' + name)
            self.values[name] = json.loads(raw)

    def value(self, reference):
        if not isinstance(reference, dict) or set(reference) != {'source', 'pointer'}:
            raise ValueError('A current metric value needs an exact actual-source reference')
        return pointer(self.values[reference['source']], reference['pointer'])

    def source(self, name):
        return self.sources[name]['sha256']

    def admission(self, descriptor):
        checks = descriptor.get('checks', [])
        if not descriptor.get('normal_api') or not checks:
            raise ValueError('Existing normal admission authority is required')
        accepted = self.value(descriptor['accepted'])
        if accepted is not True and accepted not in ('PASS', 'pass', 'accepted', 'completed_verified_actual_native_producer'):
            raise ValueError('Existing normal observation admission did not pass')
        for check in checks:
            if self.value(check['actual']) != check['expected']:
                raise ValueError('Normal observation admission check differs')


def completed(evidence, metric, allow_missing=False):
    value = evidence.value(metric['completed_at'])
    if value is None and allow_missing:
        return None
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Actual metric completion needs a timezone')
    return value


def referenced_sources(value):
    result = set()
    if isinstance(value, dict):
        if 'source' in value and 'pointer' in value:
            result.add(value['source'])
        if isinstance(value.get('actual_result'), str):
            result.add(value['actual_result'])
        for nested in value.values():
            result.update(referenced_sources(nested))
    elif isinstance(value, list):
        for nested in value:
            result.update(referenced_sources(nested))
    return result


def apply_replacements(cases, selected, energy, pipeline, document, root):
    """Return active inputs and exact archived rows; never select by outcome."""
    if document.get('schema') != SCHEMA:
        raise ValueError('Unsupported current observation input schema')
    evidence = Evidence(document, root)
    expected = document.get('expected_packages', [])
    labels = [metric['package_label'] for row in document['observations']
        for metric in row['metrics'].values() if metric.get('package_label')]
    if len(set(expected)) != len(expected) or len(set(labels)) != len(labels) or set(labels)-set(expected):
        raise ValueError('Current acquisition package identities are duplicated or unplanned')
    cases, selected, energy, pipeline = map(copy.deepcopy, (cases, selected, energy, pipeline))
    indexed = {row['uid']: row for row in cases}
    details = {row['uid']: row for row in selected}
    history, seen = [], set()
    for observation in document['observations']:
        uid = observation['uid']
        if uid in seen:
            raise ValueError('Duplicate active replacement identity')
        seen.add(uid)
        prior = indexed.get(uid)
        if prior is None:
            if observation.get('prior_case_sha256') is not None:
                raise ValueError('New observation unexpectedly has a prior row')
            row = {key:None for case in cases for key in case}
            row.update(copy.deepcopy(observation['new_case']))
            if row.get('uid') != uid or row.get('runner') != 'generic' or row.get('kind') != 'split':
                raise ValueError('Only an explicitly identified Generic deployment may be added')
            if any(row.get(field) is not None for field in ['fps', 'raw_j_per_task', 'quality_value', 'quality_relative_loss']):
                raise ValueError('A new deployment cannot supply unbound metric values')
            if not {'performance', 'quality'} <= set(observation['metrics']):
                raise ValueError('A new Generic deployment needs actual FPS and own quality sources')
            # A new Generic deployment does not manufacture a Native partner.
            cases.append(row); indexed[uid] = row
            ev = {key:None for record in selected for key in record}
            ev['uid'] = uid; selected.append(ev); details[uid] = ev
        else:
            if canonical_sha(prior) != observation['prior_case_sha256']:
                raise ValueError('Active replacement prior row differs: ' + uid)
            row, ev = prior, details[uid]
        identity = observation['identity']
        if row.get('kind') != 'split':
            raise ValueError('Current split observations cannot replace Full baselines')
        if any(row.get(key) != identity.get(key) for key in IDENTITY):
            raise ValueError('Current observation changes its deployment identity')
        for field, reference in observation['identity_evidence'].items():
            expected = HOSTS.get(row['setup_id'], row['setup_id']) if field == 'physical_host' else row.get(field)
            if field not in IDENTITY + ('uid', 'model_sha256', 'physical_host') or evidence.value(reference) != expected:
                raise ValueError('Actual source deployment identity differs: ' + field)
        required = ({'uid', 'model_sha256', 'physical_host'} if 'uid' in observation['identity_evidence']
                    else {'model_id', 'case_id', 'runner', 'model_sha256'})
        if not required <= set(observation['identity_evidence']):
            raise ValueError('Current observation lacks actual model/cut/runner identity')
        metrics = observation['metrics']
        if not metrics or set(metrics) - {'performance', 'quality', 'energy'}:
            raise ValueError('Unsupported current metric replacement')
        if row['runner'] == 'native' and 'native_binding' not in observation:
            raise ValueError('Every active Native replacement needs its exact RQ2 cut binding')
        archived = dict(uid=uid, case=copy.deepcopy(prior) if prior else None,
            selected_evidence=copy.deepcopy(ev),
            energy_repeats=[r for r in energy if r['uid'] == uid],
            pipeline_repeats=[r for r in pipeline if r['uid'] == uid])
        old_performance = row.get('performance_source_sha256')
        for name in ['performance', 'quality', 'energy']:
            if name not in metrics:
                continue
            metric = metrics[name]
            evidence.admission(metric['normal_admission'])
            source_sha = (evidence.value(metric['actual_result_sha256']) if metric.get('actual_result_sha256')
                          else evidence.source(metric['actual_result']))
            origin = metric.get('acquisition_origin')
            if origin not in {'new_capture', 'reused_existing'}:
                raise ValueError('Current metric needs its actual acquisition origin')
            when = completed(evidence, metric, allow_missing=name=='quality' and origin=='reused_existing')
            if name != 'performance':
                bound = evidence.value(metric['performance_source_sha256'])
                if bound != row.get('performance_source_sha256'):
                    raise ValueError(name + ' does not bind the selected actual FPS source')
            if name == 'performance':
                repetitions = []
                for rep in metric['repetitions']:
                    values = {key:evidence.value(ref) for key, ref in rep.items() if key != 'process_evidence'}
                    if 'process_evidence' in rep:
                        process = {key:evidence.value(ref) for key, ref in rep['process_evidence'].items()}
                        if not all(process.get(key) for key in ['namespace', 'process_id', 'start_ticks', 'runtime_instance_id']):
                            raise ValueError('Normal process evidence needs its actual namespace and runtime identity')
                        values['process_evidence'] = process
                    elif values.get('clock_domain'):
                        # Native's pinned request-latency producer writes this
                        # exact domain using os.getpid(); do not decode UUIDs.
                        prefix = 'perf_counter_ns:process:'
                        domain = values['clock_domain']
                        suffix = domain[len(prefix):] if isinstance(domain, str) and domain.startswith(prefix) else ''
                        if not suffix.isdigit() or not values.get('runtime_instance_id'):
                            raise ValueError('Native process clock domain/runtime identity is invalid')
                        values['pid'] = int(suffix)
                        values['process_evidence'] = dict(namespace='dut_'+row['runner']+'_python_process',
                            process_id=values['pid'], runtime_instance_id=values['runtime_instance_id'],
                            pid_source='request_latency.clock_domain', clock_domain=domain)
                    elif values.get('pid') is not None:
                        values['process_evidence'] = dict(namespace='measured_runner_pid', process_id=values['pid'])
                    else:
                        raise ValueError('FPS repetition lacks actual normal process evidence')
                    repetitions.append(values)
                process_keys = {(r['process_evidence']['namespace'], r['process_evidence']['process_id'],
                    r['process_evidence'].get('start_ticks')) for r in repetitions}
                runtimes = [r['process_evidence'].get('runtime_instance_id') for r in repetitions]
                if len(repetitions) != 3 or len(process_keys) != 3 or (any(runtimes) and len(set(runtimes)) != 3):
                    raise ValueError('FPS requires three independent actual processes')
                if any(r['warmups'] != 100 or r['completed_tasks'] != 1000 or not positive(r['fps']) for r in repetitions):
                    raise ValueError('FPS contract must be 100 warmups and 1000 completed tasks')
                rates = [r['fps'] for r in repetitions]
                row.update(fps=statistics.median(rates), fps_samples=rates,
                    performance_observations=3, performance_source_sha256=source_sha,
                    performance_completed_at=when, performance_acquisition_origin=origin,
                    normal_performance_claim=True)
                # These legacy fields describe the selected quality evaluation,
                # not the new runner's separately recorded timed contract.
                row.update(contract_decoder=None, contract_nms=None)
                pipeline[:] = [r for r in pipeline if r['uid'] != uid]
                pipeline.extend(dict(uid=uid, repeat=i, runner_pid=r.get('pid'), completed_tasks=1000,
                    process_evidence=r['process_evidence'],
                    runtime_instance_id=r['process_evidence'].get('runtime_instance_id'),
                    raw_sha256=source_sha) for i, r in enumerate(repetitions))
            elif name == 'quality':
                value, reference = (evidence.value(metric[key]) for key in ['value', 'reference'])
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not positive(reference):
                    raise ValueError('Actual numerical quality/reference is unavailable')
                if evidence.value(metric['n']) != 5000 or evidence.value(metric['bootstrap_repetitions']) != 1000:
                    raise ValueError('Current detector quality requires N5000/B1000')
                loss = (reference - value) / reference
                # Native's normal source-admission result is separate from its
                # legacy absolute-margin bootstrap decision. When it reports
                # no standalone eligibility boolean, apply the established
                # study's numeric CPU-relative five-percent rule directly.
                admitted = evidence.value(metric['quality_eligible']) if metric.get('quality_eligible') else loss <= .05
                if not isinstance(admitted, bool):
                    raise ValueError('Normal quality admission decision is unavailable')
                quality_class = evidence.value(metric['quality_class'])
                row.update(quality_relative_loss=loss, normal_quality=admitted,
                    quality_class=quality_class,
                    quality_exclusions=[] if admitted else ['normal_quality_admission_failed'],
                    quality_source_sha256=source_sha, quality_completed_at=when,
                    quality_acquisition_origin=origin, quality_timed_endpoint_bound=True,
                    quality_relative_loss_ci=None, quality_ci=None, quality_cached_loss_disagrees=None)
                ev.update(quality_value=value, quality_reference_value=reference,
                    quality_numeric_relative_loss=loss, quality_n=5000,
                    quality_metric='coco_ap_50_95', quality_evidence_sha256=source_sha,
                    quality_observation_status='normal_actual_completed_record_evaluation',
                    quality_primary_observation=None, quality_relative_loss_ci=None,
                    quality_cached_loss_disagrees=None, quality_bound_result_sha256=None,
                    quality_source_request_sha256=None, quality_result_class=quality_class,
                    quality_reference_delta_percentage_points=100*(value-reference),
                    quality_remeasured_in_refresh16=False,
                    quality_original_field=metric['value']['pointer']+'; '+metric['reference']['pointer'],
                    quality_binding_note='Actual current normal quality bound to the selected FPS source; prior statistics remain archived.')
                for field,key in [('quality_primary_observation','primary_observation'),
                        ('quality_relative_loss_ci','relative_loss_ci'),
                        ('quality_bound_result_sha256','bound_result_sha256'),
                        ('quality_source_request_sha256','request_sha256')]:
                    if metric.get(key):
                        ev[field] = evidence.value(metric[key])
                for field in ['quality_value', 'quality_reference_value', 'quality_numeric_relative_loss',
                        'quality_n', 'quality_metric', 'quality_evidence_sha256', 'quality_observation_status',
                        'quality_primary_observation', 'quality_relative_loss_ci', 'quality_cached_loss_disagrees',
                        'quality_bound_result_sha256', 'quality_source_request_sha256', 'quality_result_class',
                        'quality_reference_delta_percentage_points', 'quality_remeasured_in_refresh16',
                        'quality_original_field', 'quality_binding_note']:
                    row[field] = ev[field]
            else:
                repeats = []
                for i, rep in enumerate(metric['repetitions']):
                    values = {key: evidence.value(ref) for key, ref in rep['values'].items()}
                    if not all(positive(values.get(key)) for key in ['energy_j', 'completed_tasks', 'duration_s']):
                        raise ValueError('Energy requires actual E, completed images and duration')
                    if values.get('requested_duration_s') != 60:
                        raise ValueError('Energy requires an actual requested 60-second window')
                    repeats.append(dict(values, uid=uid, repeat=i,
                        source_sha256=(evidence.value(rep['source_sha256']) if rep.get('source_sha256')
                            else evidence.source(rep['actual_result']))))
                if len(repeats) != 3 or len({r['source_sha256'] for r in repeats}) != 3:
                    raise ValueError('Energy requires three distinct actual sensor repeats')
                if evidence.value(metric['system_scope']) not in {'full_system', 'FS'}:
                    raise ValueError('Current energy must retain the complete system scope')
                energy[:] = [r for r in energy if r['uid'] != uid]; energy.extend(repeats)
                row.update(raw_j_per_task=statistics.mean(r['energy_j']/r['completed_tasks'] for r in repeats),
                    energy_repeat_n=3, energy_scope='full_system', energy_source_sha256=source_sha,
                    energy_completed_at=when, energy_acquisition_origin=origin, normal_energy=True,
                    energy_claim=True, diagnostic_energy=False)
                row.update(comparison_j_per_task=row['raw_j_per_task'], comparison_basis='raw_measured',
                    mean_tasks_per_j=statistics.mean(r['completed_tasks']/r['energy_j'] for r in repeats),
                    energy_ci=None, energy_exclusions=[])
            row[name + '_generation'] = observation['generation']
            ev.update({name + '_generation': observation['generation'],
                       name + '_source': evidence.sources[metric['actual_result']]['path'],
                       name + '_source_sha256': source_sha})
        if row.get('performance_source_sha256') != old_performance and 'energy' not in metrics:
            # No old energy may silently become a joint observation of new FPS.
            row.update(raw_j_per_task=None, comparison_j_per_task=None, energy_repeat_n=0,
                energy_claim=False, normal_energy=False, energy_source_sha256=None,
                energy_generation=None, energy_original_field=None,
                energy_ci=None, mean_tasks_per_j=None, energy_scope=None, energy_window=None,
                energy_exclusions=['no_energy_bound_to_current_performance_observation'],
                comparison_basis='unavailable_for_current_performance_observation',
                energy_status='unavailable_for_current_performance_observation')
            ev.update(energy_source=None, energy_source_sha256=None, energy_generation=None, energy_original_field=None)
            energy[:] = [r for r in energy if r['uid'] != uid]
        if row.get('performance_source_sha256') != old_performance and 'quality' not in metrics:
            row.update(quality_relative_loss=None, normal_quality=False, quality_class='unavailable',
                quality_source_sha256=None, quality_timed_endpoint_bound=False,
                quality_ci=None,
                quality_exclusions=['no_quality_bound_to_current_performance_observation'])
            ev.update(quality_value=None, quality_reference_value=None, quality_evidence_sha256=None,
                quality_n=0, quality_numeric_relative_loss=None, quality_relative_loss_ci=None,
                quality_primary_observation=None, quality_cached_loss_disagrees=None,
                quality_bound_result_sha256=None, quality_source_request_sha256=None,
                quality_reference_delta_percentage_points=None, quality_generation=None,
                quality_source=None, quality_original_field=None, quality_result_class='unavailable',
                quality_remeasured_in_refresh16=False,
                quality_binding_note='No current quality observation is bound to the replacement FPS source.',
                quality_observation_status='unavailable_for_current_performance_observation')
            for field in ['quality_value', 'quality_reference_value', 'quality_evidence_sha256',
                    'quality_n', 'quality_numeric_relative_loss', 'quality_relative_loss_ci',
                    'quality_primary_observation', 'quality_cached_loss_disagrees', 'quality_bound_result_sha256',
                    'quality_source_request_sha256', 'quality_reference_delta_percentage_points',
                    'quality_generation', 'quality_source', 'quality_original_field', 'quality_result_class',
                    'quality_binding_note', 'quality_remeasured_in_refresh16']:
                row[field] = ev[field]
        for field, reference in observation.get('runtime_fields', {}).items():
            if field in IDENTITY or field in {'uid', 'fps', 'raw_j_per_task', 'quality_relative_loss'}:
                raise ValueError('Runtime metadata cannot replace identity or metrics')
            row[field] = evidence.value(reference)
        if 'native_binding' in observation:
            if row['runner'] != 'native':
                raise ValueError('A Generic observation cannot supply a Native pair')
            binding = copy.deepcopy(observation['native_binding'])
            evidence.admission(binding['normal_admission'])
            binding['identity'] = {key: evidence.value(ref) for key, ref in binding['identity'].items()}
            if not all(binding['identity'].get(key) for key in ['model_sha256', 'part1_sha256',
                    'part2_engine_sha256', 'boundary_id', 'preprocessing_sha256', 'completion_contract_sha256']):
                raise ValueError('Native replacement lacks its actual artifact/input/completion binding')
            if binding['identity']['model_sha256'] != row['model_sha256']:
                raise ValueError('Native replacement model hash differs')
            if 'performance' in metrics:
                comparison = {key:evidence.value(ref) for key, ref in binding['generic_comparison'].items()}
                for key in ['preprocessing_sha256', 'prepared_inputs_sha256', 'completed_endpoint_contract_sha256']:
                    if not binding['identity'].get(key) or binding['identity'][key] != comparison.get(key):
                        raise ValueError('Current Native/Generic actual input/completed endpoint differs: ' + key)
                if not comparison.get('performance_source_sha256'):
                    raise ValueError('Native replacement lacks its selected Generic source relation')
                binding['generic_comparison'] = comparison
            binding['normal_source_sha256'] = {name:evidence.source(name)
                for name in sorted(referenced_sources(observation))}
            binding['performance_source_sha256'] = row['performance_source_sha256']
            binding['evidence_sha256'] = canonical_sha(binding)
            row['current_native_binding'] = binding
        row['current_observation_generation'] = observation['generation']
        row['current_observation_metric_updates'] = sorted(metrics)
        row['current_observation_document_sha256'] = canonical_sha(document)
        history.append(archived)
    return cases, selected, energy, pipeline, history
