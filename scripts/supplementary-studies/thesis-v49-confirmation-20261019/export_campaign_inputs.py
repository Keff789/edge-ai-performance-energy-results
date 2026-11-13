#!/usr/bin/env python3
"""Export primitive, hash-bound campaign metadata; no hardware or raw integration.

This one-time private import reads the canonical S04 attempts, their inner energy
analyses, the two separate supplement assessments, and the original historical
repeat CSVs. Public table reproduction uses their primitive JSON exports plus
the separately projected design/registry and quality/metrology capsules. This
importer writes exactly four documents; it does not create those other capsules.
No generated pair table or model aggregate is an import source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re


PRIMARY = 'runs/confirmation_r3_20261018/resume_sessions/resume_20261019_s04_h8_retry/resolution.json'
SUPPLEMENT = 'evidence/energy_supplement_20261019/sessions/energy_supplement_20261019_s01/resolution.json'
MANIFEST = 'provenance/delivery_payload_manifest_energy_supplement_20261019.json'
MANIFEST_SHA = '7bfa8e24cfe37f79530198f0d756fab5d0cb921c5c97cf737cf184262a0712f6'
ARCHIVE_SHA = 'edbd618ad91ef658a866c73c61defd00389e3ca9218c33ea22d87a6ec3721915'
SOURCE_COMMIT = '64c1f487645d20a844d66ccdf8f65dcc80b96065'
NAMES = ('measurements.json', 'history_repeats.json', 'attempt_history.json', 'origin_provenance.json')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def public_reason(value):
    """Retain diagnostic codes without private machine paths or addresses."""
    if isinstance(value, list):
        return [public_reason(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'/home/[^\s\"\'\)\],;]+', '[archival-path]', value)
        return re.sub(r'192\.168\.\d+\.\d+(?::\d+)?', '[private-endpoint]', value)
    return value


class Sources:
    def __init__(self, campaign):
        self.root = Path(campaign).resolve()
        raw = (self.root / MANIFEST).read_bytes()
        require(sha(raw) == MANIFEST_SHA, 'frozen energy-supplement manifest changed')
        manifest = json.loads(raw)
        self.members = {row['path']: row for row in manifest['files']}
        require(len(self.members) == manifest['file_count'] == 30815, 'member inventory changed')
        self.records = {MANIFEST: {'archive_member': MANIFEST, 'sha256': sha(raw), 'bytes': len(raw)}}
        self.cache = {}
        self.private_locations = []

    def member(self, path):
        path = str(path)
        marker = '/thesis_v49_hardware_confirmation_20261018/'
        if marker in path:
            path = path.split(marker, 1)[1]
        p = Path(path)
        if p.is_absolute():
            p = p.relative_to(self.root)
        require('..' not in p.parts, 'unsafe archive member')
        return p.as_posix()

    def binding(self, path, expected=None):
        member = self.member(path)
        row = self.members[member]
        require(expected is None or row['sha256'] == expected, 'archive binding mismatch: ' + member)
        result = {key: row[key] for key in ('sha256', 'bytes')}
        result['archive_member'] = member
        self.records[member] = result
        return result

    def reference(self, binding):
        return self.binding(binding['path'], binding.get('sha256'))

    def json(self, binding):
        if isinstance(binding, str):
            binding = {'path': binding}
        reference = self.reference(binding)
        member = reference['archive_member']
        if member not in self.cache:
            require(member.endswith('.json'), 'metadata JSON required')
            raw = (self.root / member).read_bytes()
            require(len(raw) == reference['bytes'] and sha(raw) == reference['sha256'], 'source metadata changed: ' + member)
            self.cache[member] = json.loads(raw)
        return self.cache[member]

    def external_csv(self, binding):
        """The historical thesis CSVs are original inputs, not campaign tables."""
        p = Path(binding['path'])
        require('/mnt/' not in str(p), 'import does not access mounted external files')
        raw = p.read_bytes()
        require(sha(raw) == binding['sha256'], 'historical CSV changed: ' + p.name)
        reference = {'external_sha256_ref': binding['sha256'], 'filename': p.name, 'bytes': len(raw)}
        self.records['external:' + binding['sha256']] = reference
        self.private_locations.append({'path': str(p), **reference})
        csv.field_size_limit(10_000_000)
        return csv.DictReader(io.StringIO(raw.decode())), reference


def own_binding(sources, binding, attempt_dir):
    reference = sources.reference(binding)
    require(Path(reference['archive_member']).is_relative_to(attempt_dir), 'receipt belongs to a different attempt')
    return reference


def primary_rows(sources, resolution):
    rows = []
    require(len(resolution['canonical_entries']) == 70, '70 canonical primary entries required')
    for entry in resolution['canonical_entries']:
        parent = sources.json(entry['attempt'])
        require(parent['status'] == 'pipeline_complete', 'unaccepted primary attempt')
        require(parent['run_id'] == entry['execution_run_id'] and parent['uid'] == entry['uid'], 'primary execution identity mismatch')
        require(parent['block'] == entry['block'] and parent['setup_id'] == entry['setup_id'], 'primary setup/block mismatch')
        summary = parent['summary_attempt']
        require(summary['status'] == 'completed' and summary['uid'] == entry['uid'], 'primary summary identity/status mismatch')
        require(all(summary.get(k) is True for k in ('qualification_pass', 'fresh_process', 'warmup_drained', 'measurement_drained', 'artifact_identity_verified', 'request_identity_verified')), 'primary admission/drain gate failed')
        require(all(summary[k] == 0 for k in ('lost_outputs', 'duplicate_outputs', 'stale_outputs')), 'primary completion errors')
        N, start, stop = (summary['completed'], summary['pipeline_start_monotonic_ns'], summary['pipeline_end_monotonic_ns'])
        require(type(N) is int and N > 0 and type(start) is type(stop) is int and stop > start, 'primary N/time invalid')
        require(summary['admitted'] == N and parent.get('source_completion_verified') is True, 'primary source/drain incomplete')
        analysis_binding = {'path': parent['inner_interval_analysis_path'], 'sha256': parent['inner_interval_analysis_sha256']}
        analysis = sources.json(analysis_binding)
        require(analysis['uid'] == entry['uid'] and analysis['N_completed'] == N, 'energy N/UID is from another attempt')
        require(analysis['remote_interval_start_ns'] == start and analysis['remote_interval_stop_ns'] == stop, 'energy interval is from another attempt')
        conditional = analysis['conditional_estimate']
        E = conditional['energy_j']
        require(E == parent['conditional_energy']['energy_j'], 'parent/inner energy mismatch')
        if E is not None:
            require(positive(E) and conditional['target_sample_support_complete'] is True and conditional['conditional_trace_covers_all_boundary_envelopes'] is True, 'admitted primary energy lacks support')
            require(conditional['candidate_dropped_samples'] == conditional['candidate_raw_counter_discontinuities'] == 0, 'admitted primary energy has target losses')
            require(math.isclose(E / N, conditional['energy_per_completed_j'], rel_tol=1e-12), 'primary E/N mismatch')
        require(analysis['valid_for_final_energy'] is False and conditional['complete_uncertainty_available'] is False, 'physical energy scope changed')
        provenance = {'attempt': sources.reference(entry['attempt']), 'analysis': sources.reference(analysis_binding)}
        for key, binding in summary['runtime_evidence'].items():
            provenance[key] = sources.reference(binding)
        rows.append({'run_id': entry['logical_run_id'], 'execution_run_id': entry['execution_run_id'],
            'attempt_id': entry['attempt_id'], 'session_id': entry['origin_session_id'],
            'uid': entry['uid'], 'setup_id': entry['setup_id'], 'block': entry['block'], 'position': entry['position'],
            'N_completed': N, 'interval_start_ns': start, 'interval_stop_ns': stop,
            'conditional_energy_j': E, 'conditional_alignment_envelope_j': conditional.get('energy_alignment_error_envelope_j'),
            'candidate_dropped_samples': conditional['candidate_dropped_samples'],
            'candidate_raw_counter_discontinuities': conditional['candidate_raw_counter_discontinuities'],
            'target_sample_support_complete': conditional['target_sample_support_complete'],
            'source_completion_verified': True, 'A_valid': True, 'B_valid': E is not None, 'C_valid': False,
            'provenance': provenance})
    require(len({r['run_id'] for r in rows}) == 70, 'duplicate canonical primary slot')
    require(sum(r['B_valid'] for r in rows) == 68, 'primary energy admission changed')
    return sorted(rows, key=lambda r: (r['block'], r['position']))


def supplement_rows(sources, resolution):
    require(resolution['execution_finished'] is True, 'supplement controller still active')
    require(len(resolution['selected_supplements']) == 2, 'two selected supplements required')
    rows = []
    for selected in resolution['selected_supplements']:
        item = next(x for x in resolution['all_attempts'] if x['attempt'] == selected['attempt'])
        parent = sources.json(item['attempt'])
        assessment = item['assessment']
        require(all(assessment.get(k) is True for k in ('A_valid', 'B_valid', 'selection_eligible')), 'supplement not strict A+B')
        require(assessment.get('C_valid') is False and parent['status'] == 'pipeline_complete', 'supplement physical/status scope changed')
        require(item['uid'] == parent['uid'] == assessment['uid'], 'supplement UID mismatch')
        require(item['execution_run_id'] == parent['run_id'] == assessment['execution_run_id'], 'supplement execution mismatch')
        own = assessment['own_measurement'];N = own['N_completed'];E = own['conditional_energy_j']
        require(type(N) is int and N > 0 and positive(E), 'supplement N/E invalid')
        require(math.isclose(E / N, own['conditional_energy_per_completed_j'], rel_tol=1e-12), 'supplement uses a different N')
        a = sources.json(assessment['analysis']);c = a['conditional_estimate']
        require(a['N_completed'] == N and a['uid'] == item['uid'] and c['energy_j'] == E, 'supplement assessment/inner mismatch')
        require(a['remote_interval_start_ns'] == own['native_interval_start_ns'] and a['remote_interval_stop_ns'] == own['native_interval_stop_ns'], 'supplement assessment/interval mismatch')
        require(all(item.get(k) is True for k in ('collector_process_started', 'physical_source_GO_observed', 'runtime_process_started')), 'supplement actual starts missing')
        completion = assessment['source_completion']
        require(all(completion.get(k) is True for k in ('source_completion_verified', 'natural_protocol_END_verified', 'source_socket_closed', 'owned_tree_quiescent')), 'supplement natural END incomplete')
        start, stop = own['native_interval_start_ns'], own['native_interval_stop_ns']
        require(type(start) is type(stop) is int and stop > start, 'supplement native interval invalid')
        require(positive(own['native_makespan_including_drain_s']), 'supplement native duration missing')
        provenance = {'attempt': sources.reference(item['attempt']), 'analysis': sources.reference(assessment['analysis'])}
        attempt_dir = Path(provenance['attempt']['archive_member']).parent
        for key, binding in item['start_receipts'].items():
            if binding:
                provenance[key] = own_binding(sources, binding, attempt_dir)
        if item.get('timing'):
            provenance['timing'] = own_binding(sources, item['timing'], attempt_dir)
        model = assessment['model_domain_observation']
        rows.append({'run_id': item['logical_run_id'], 'execution_run_id': item['execution_run_id'],
            'attempt_id': item['attempt_id'], 'attempt_number': item['attempt_number'],
            'session_id': item['origin_session_id'], 'uid': item['uid'], 'setup_id': item['setup_id'],
            'block': item['block'], 'position': item['position'], 'N_completed': N,
            'interval_start_ns': start, 'interval_stop_ns': stop,
            'native_makespan_including_drain_s': own['native_makespan_including_drain_s'],
            'conditional_energy_j': E, 'conditional_alignment_envelope_j': own['conditional_alignment_envelope_j'],
            'candidate_dropped_samples': assessment['observed_gates']['candidate_dropped_samples'],
            'candidate_raw_counter_discontinuities': assessment['observed_gates']['candidate_raw_counter_discontinuities'],
            'collector_process_started': True, 'physical_source_GO_observed': True, 'runtime_process_started': True,
            'collector_process_identity': item['collector_process_identity'],
            'physical_source_GO_identity_sha256': sha(canonical(item['physical_source_GO_identity']).encode()),
            'runtime_process_identity': item['runtime_process_identity'],
            'source_completion_verified': True,
            'source_completion': {k: completion[k] for k in ('source_completion_verified', 'natural_protocol_END_verified', 'source_socket_closed', 'owned_tree_quiescent')},
            'observed_gates': assessment['observed_gates'], 'model_domain_observation': model,
            'A_valid': True, 'B_valid': True, 'C_valid': False, 'provenance': provenance})
    require({r['run_id'] for r in rows} == {'b04_p09', 'b05_p09'}, 'supplement targets changed')
    return sorted(rows, key=lambda r: r['run_id'])


def historical_rows(sources, selected_uids):
    review = sources.json('evidence/history_reproduction.json')
    bindings = {Path(b['path']).name: b for b in review['sources'][:5]}
    energy_rows, energy_csv = sources.external_csv(bindings['energy_repeats.csv'])
    energy = []
    for i, row in enumerate(energy_rows, 2):
        if row['uid'] not in selected_uids:
            continue
        N = int(row['completed_images'] or row['completed_tasks']);E = float(row['energy_j']);duration = float(row['duration_s'])
        require(N > 0 and positive(E) and positive(duration), 'historical energy primitive invalid')
        energy.append({'uid': row['uid'], 'repeat': int(row['repeat']), 'N_completed': N,
            'duration_s': duration, 'energy_j': E,
            'source': {'external_sha256_ref': row['source_sha256'], 'kind': 'original_energy_summary', 'csv': energy_csv, 'csv_row': i}})
    performance_rows, performance_csv = sources.external_csv(bindings['pipeline_repeats.csv'])
    performance = []
    for i, row in enumerate(performance_rows, 2):
        if row['uid'] not in selected_uids:
            continue
        N = int(row.get('completed_images') or row['completed_tasks'] or row['completed_frames'])
        duration = float(row['stored_makespan_s']) if row['stored_makespan_s'] else float(row['makespan_ms']) / 1000
        require(N > 0 and positive(duration), 'historical performance primitive invalid')
        performance.append({'uid': row['uid'], 'repeat': int(row['repeat']), 'N_completed': N,
            'duration_s': duration, 'reported_rate_per_s': float(row['fps']) if row['fps'] else None,
            'source': {'external_sha256_ref': row['raw_sha256'], 'kind': 'original_performance_summary', 'csv': performance_csv, 'csv_row': i}})
    for rows in (energy, performance):
        require(len(rows) == 42 and all(sum(r['uid'] == uid for r in rows) == 3 for uid in selected_uids), 'three original historical repeats per UID required')
        require(len({(r['uid'], r['repeat']) for r in rows}) == 42, 'duplicate historical repeat')
    selection = sources.json('evidence/portable_inputs/energy_window_rates.json')
    require({r['uid'] for r in selection} == selected_uids, 'historical selection identity changed')
    points = [{k: row[k] for k in ('uid', 'model', 'kind', 'fps', 'source_hashes')} for row in selection]
    return {'schema': 'v49-confirmation-historical-repeats-v1',
        'energy': sorted(energy, key=lambda r: (r['uid'], r['repeat'])),
        'performance': sorted(performance, key=lambda r: (r['uid'], r['repeat'])),
        'selection': points, 'scope': 'Original thesis repeat CSV primitives, bound to their previously verified original summary SHA identities; no new historical measurements.'}


def attempt_row(sources, item, selected, cohort):
    binding = item['attempt'];parent = sources.json(binding)
    provenance = {'attempt': sources.reference(binding)}
    attempt_dir = Path(provenance['attempt']['archive_member']).parent
    require(parent['uid'] == item['uid'] and parent['block'] == item['block'], 'attempt history identity mismatch')
    for key, value in item.get('start_receipts', {}).items():
        if value:
            provenance[key] = own_binding(sources, value, attempt_dir)
    lifecycle = None
    if item.get('start_receipts', {}).get('source_lifecycle'):
        lifecycle = sources.json(item['start_receipts']['source_lifecycle'])
    return {'cohort_id': cohort, 'session_id': item.get('origin_session_id', cohort),
        'run_id': item.get('logical_run_id', parent['run_id']), 'execution_run_id': parent['run_id'],
        'attempt_id': item.get('attempt_id', cohort + ':' + parent['run_id']),
        'attempt_number': item.get('attempt_number', parent.get('attempt', 0)),
        'uid': parent['uid'], 'setup_id': parent['setup_id'], 'block': parent['block'], 'position': parent['position'],
        'status': parent['status'], 'selected_primary': provenance['attempt']['sha256'] in selected,
        'collector_process_started': item.get('collector_process_started', False),
        'physical_source_GO_observed': item.get('physical_source_GO_observed', False),
        'runtime_process_started': item.get('runtime_process_started', False),
        'collector_process_identity': item.get('collector_process_identity'),
        'runtime_process_identity': item.get('runtime_process_identity'),
        'physical_source_GO_identity_sha256': sha(canonical(item['physical_source_GO_identity']).encode()) if item.get('physical_source_GO_identity') else None,
        'source_completion_verified': parent.get('source_completion_verified') is True,
        'natural_protocol_END_verified': lifecycle.get('protocol_end_verified') if lifecycle else None,
        'source_failure_reason': lifecycle.get('reason') if lifecycle else None,
        'failure_reasons': public_reason(parent.get('pipeline_failure_reasons', parent.get('reason', []))),
        'abort_remaining_campaign': public_reason(parent.get('abort_remaining_campaign')),
        'provenance': provenance}


def previous_cohort_rows(sources, cohort):
    rows = []
    prefix = 'runs/' + cohort + '/slots/'
    for member in sorted(sources.members):
        if not (member.startswith(prefix) and member.endswith('/attempt.json')):
            continue
        parent = sources.json(member);directory = Path(member).parent
        item = {'uid': parent['uid'], 'block': parent['block'], 'attempt': {'path': member}, 'start_receipts': {}}
        manifest = directory / 'energy/run_000/acquisition_manifest.json'
        if manifest.as_posix() in sources.members:
            data = sources.json(manifest.as_posix());pid,stamp = data.get('collector_pid'),data.get('started_at_unix_ns')
            started = data.get('started') is True and type(pid) is int and pid > 0 and type(stamp) is int and stamp > 0
            item['collector_process_started'] = started
            item['collector_process_identity'] = [pid,stamp] if started else None
            item['start_receipts']['acquisition_manifest'] = {'path': manifest.as_posix()}
        lifecycle = directory/'energy/run_000/collector_storage/fast_firmware_source_lifecycle.json'
        if lifecycle.as_posix() in sources.members:
            data = sources.json(lifecycle.as_posix());go = data.get('request_send_before')
            item['physical_source_GO_observed'] = isinstance(go, dict) and type(go.get('realtime_ns')) is int
            item['physical_source_GO_identity'] = [data.get('local_endpoint'),go] if go else None
            item['start_receipts']['source_lifecycle'] = {'path': lifecycle.as_posix()}
        identity = directory/'runtime_output/run_identity.json'
        if identity.as_posix() in sources.members:
            data = sources.json(identity.as_posix())
            pid, stamp = data.get('pid'), data.get('created_unix_ns')
            require(data.get('uid') == parent['uid'], 'old cohort native UID mismatch')
            item['runtime_process_started'] = type(pid) is int and pid > 0 and type(stamp) is int and stamp > 0
            item['runtime_process_identity'] = [pid, stamp] if item['runtime_process_started'] else None
            item['start_receipts']['run_identity'] = {'path': identity.as_posix()}
        rows.append(attempt_row(sources, item, set(), cohort))
    summary = sources.json('runs/' + cohort + '/campaign_result.json')
    require(len(rows) == summary['attempt_records'], 'old cohort actual attempt inventory changed')
    return rows


def technical_history(sources, resolution):
    seen, cycles, chain = set(), [], []
    while resolution is not None:
        chain.append(resolution['session_id'])
        for binding in resolution.get('diagnostics', []):
            key = (sources.member(binding['path']), binding['sha256'])
            if key in seen:
                continue
            seen.add(key);doc = sources.json(binding)
            require(doc['schema'] == 'thesis-v49/source-technical-cycle-v3', 'unknown diagnostic cycle schema')
            physical = sources.json(doc['physical_start']);owned = sources.json(doc['owned_result']);life = sources.json(doc['lifecycle'])
            pid,stamp = physical['collector_pid'],physical['started_at_unix_ns']
            require(owned['collector_pid'] == pid and owned['process_started_at_unix_ns'] == stamp, 'technical receipt identity mismatch')
            started = doc['process_started'] is True and owned['process_started'] is True and type(pid) is int and pid > 0 and type(stamp) is int and stamp > 0
            go = life.get('request_send_before')
            cycles.append({'acquisition_id':doc['acquisition_id'],'setup_id':doc['setup_id'],
                'collector_process_started':started,'collector_process_identity':[pid,stamp],
                'physical_source_GO_observed':isinstance(go,dict) and type(go.get('realtime_ns')) is int,
                'physical_source_GO_identity_sha256':sha(canonical([life.get('local_endpoint'),go]).encode()),
                'natural_protocol_END_verified':life.get('protocol_end_verified') is True,
                'source_socket_closed':isinstance(life.get('source_socket_closed'),dict),
                'owned_tree_quiescent':owned.get('owned_tree_quiescent') is True,
                'provenance':{'cycle':sources.reference(binding),'physical_start':sources.reference(doc['physical_start']),
                    'owned_result':sources.reference(doc['owned_result']),'lifecycle':sources.reference(doc['lifecycle'])}})
        index = sources.json(resolution['index'])
        previous = index.get('previous_resolution')
        if previous:
            require(sources.member(previous['path']) not in seen, 'cyclic previous resolution')
            seen.add(sources.member(previous['path']))
        resolution = sources.json(previous) if previous else None
    require(len({tuple(r['collector_process_identity']) for r in cycles if r['collector_process_started']}) == 4, 'four distinct technical starts required')
    return cycles, chain


def export(campaign, output, private_provenance=None):
    output = Path(output)
    require(all(not (output/name).exists() for name in NAMES), 'refusing to overwrite exported inputs')
    s = Sources(campaign)
    resolution = s.json(PRIMARY);supplement = s.json(SUPPLEMENT)
    primary = primary_rows(s, resolution);supplements = supplement_rows(s, supplement)
    selected = {entry['attempt']['sha256'] for entry in resolution['canonical_entries']}
    attempts = [attempt_row(s, row, selected, 'confirmation_r3_20261018') for row in resolution['all_attempts']]
    supplement_attempts = [attempt_row(s, row, set(), 'energy_supplement_20261019') for row in supplement['all_attempts']]
    cycles, chain = technical_history(s, resolution)
    plan = s.json('provenance/preregistered_plan.json')
    measurements = {'schema':'v49-confirmation-measurement-inputs-v1','primary':primary,'supplements':supplements,
        'primary_resolution':s.binding(PRIMARY),'supplement_resolution':s.binding(SUPPLEMENT),
        'scope':'70 unchanged primary A rows,68 primary conditional E,2 separate own-N/t/E supplements; C remains0.'}
    history = historical_rows(s, {row['uid'] for row in primary})
    attempt_history = {'schema':'v49-confirmation-attempt-history-v1','primary_chain':attempts,'supplements':supplement_attempts,
        'other_cohorts':{name:previous_cohort_rows(s,name) for name in ('confirmation_20261018','confirmation_r2_20261018')},
        'other_cohort_summaries':{name:{key:value for key,value in s.json('runs/'+name+'/campaign_result.json').items()
            if key in ('status','planned_slots','attempt_records','pipeline_complete','failed','unavailable')}
            for name in ('confirmation_20261018','confirmation_r2_20261018')},
        'technical_diagnostics':cycles,'resume_chain':chain,'cohorts_pooled':False}
    contents = {'measurements.json':measurements,'history_repeats.json':history,'attempt_history.json':attempt_history}
    rendered = {name:(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode() for name,value in contents.items()}
    auxiliary = []
    for name in ('design.json', 'external_sources.json'):
        path = output/name
        if path.exists():
            raw = path.read_bytes()
            require(b'/home/' not in raw and b'192.168.' not in raw, 'private auxiliary capsule')
            data = json.loads(raw)
            references = list(data.get('sources', []))
            if 'profile_provenance' in data:
                references.append(data['profile_provenance'])
            references.extend(row['quality_data_identity']['source'] for row in data.get('entries', []))
            for reference in references:
                s.binding(reference['archive_member'], reference['sha256'])
            auxiliary.append({'path':name,'sha256':sha(raw),'bytes':len(raw)})
    origin = {'schema':'v49-confirmation-origin-provenance-v1','source_campaign_commit':SOURCE_COMMIT,
        'source_archive':{'filename':'thesis_v49_hardware_confirmation_energy_supplement_20261019.tar.gz','sha256':ARCHIVE_SHA,'bytes':2857836513},
        'source_payload_manifest':s.records[MANIFEST],
        'exporter':{'filename':Path(__file__).name,'sha256':sha(Path(__file__).read_bytes())},
        'sources':sorted(s.records.values(),key=lambda row:row.get('archive_member',row.get('external_sha256_ref',''))),
        'outputs':sorted([{'path':name,'sha256':sha(raw),'bytes':len(raw)} for name,raw in rendered.items()]+auxiliary,key=lambda row:row['path']),
        'plan':{'random_seed':plan['random_seed'],'blocks':plan['blocks'],'planned_processes':plan['planned_processes']},
        'original_files_modified':False,'raw_waveform_reintegration_performed':False,'hardware_or_network_operations':0,
        'generated_pair_or_model_aggregate_used_as_input':False,
        'scope':'Private one-time extraction from original canonical attempt metadata and original thesis repeat CSVs. Four importer documents are written; separately projected design/registry are bound if already present. Public table regeneration also consumes the independent quality/metrology capsules.'}
    rendered['origin_provenance.json'] = (json.dumps(origin,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    for name,raw in rendered.items():
        require(b'/home/' not in raw and b'192.168.' not in raw, 'private path/address leaked into '+name)
    output.mkdir(parents=True,exist_ok=True)
    for name,raw in rendered.items():
        with (output/name).open('xb') as f:
            f.write(raw)
    if private_provenance:
        path = Path(private_provenance);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as f:
            json.dump({'schema':'v49-confirmation-private-import-locations-v1','external_original_csv_locations':s.private_locations},f,indent=2);f.write('\n')
    return {'primary':len(primary),'primary_conditional_energy':sum(r['B_valid'] for r in primary),
        'supplements':len(supplements),'primary_chain_attempt_records':len(attempts),'technical_cycles':len(cycles),
        'historical_energy':len(history['energy']),'historical_performance':len(history['performance'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--private-provenance',type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.campaign,args.output,args.private_provenance),sort_keys=True))


if __name__ == '__main__':
    main()
