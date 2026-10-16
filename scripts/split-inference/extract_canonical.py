#!/usr/bin/env python3
"""Project the active Native A4 Current into the existing compact paper inputs.

Adapted from the existing Refresh16 extract_canonical.py. Measurement values
come only from the normal manifest-bound compact export, never raw reports.
The supplied finite selection identifies the replacement; existing selected
dataset-quality values and sources are retained exactly. Nothing runs without an
explicit fresh --output, and this command never changes Current or its archive.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

GENERATION = 'deepx_native_a4_20261015'
SETUP = {'orin_nx_deepx_m1_01': 'DeepX', 'orin_nx_hailo8_01': 'H8',
         'orin_nx_hailo10_01': 'H10'}
IDENTITY = ('uid', 'model_id', 'setup_id', 'backend', 'case_id', 'runner', 'kind', 'task')


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    p.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def key(r):
    return (r['model_id'], SETUP.get(r['setup_id'], r['setup_id']),
            r['backend'], r['case_id'])


def unique(rows):
    result = {r['uid']: r for r in rows}
    assert len(result) == len(rows), 'Duplicate compact UID'
    return result


def checked(root, manifest, name):
    path = root / name
    assert Path(name).name == name and path.resolve().is_relative_to(root.resolve()), name
    assert sha(path) == manifest[name], ('Compact input changed', name)
    return read(path)


def quality(row):
    return {k: v for k, v in row.items() if 'quality' in k}


def groups(rows, targets):
    result = collections.defaultdict(list)
    for row in rows:
        if row['uid'] not in targets:
            result[row['uid']].append(row)
    return dict(result)


def project_metadata(row):
    """Expose the selected normal compact source and policy, without raw parsing."""
    fresh = row['native_refresh']
    assert fresh['campaign'] == GENERATION and fresh['quality_remeasured'] is False
    assert fresh['normal_import_complete'] is True
    performance, energy = fresh['performance_summary'], fresh['energy_source']
    assert performance['sha256'] == row['performance_source_sha256']
    policy = json.loads(row['scheduling'])
    assert row['deepx_runtime_mode'] == policy['deepx_runtime_mode'] == 'A4'
    assert row['deepx_max_inflight'] == policy['deepx_max_inflight'] == 4
    if row['kind'] == 'split':
        assert policy['queue_depth'] == 3
    notes = ['DeepX Native A4; maximum four outstanding DeepX jobs',
             'normal imported performance and calibrated host-inclusive energy; dataset quality reused']
    if row['kind'] == 'split':
        notes.append('split FIFO queue_depth=3; serial TensorRT consumer including task completion')
    if row.get('completion_mode'):
        notes.append('normal measured completion mode=' + row['completion_mode'])
    if row.get('measurement_boundary'):
        notes.append('measurement_boundary=' + row['measurement_boundary'])
    return dict(performance_source=performance['canonical_path'],
               performance_generation=GENERATION,
               performance_original_field='fps_samples / fps_median (normal compact import)',
               energy_source=energy['canonical_path'], energy_source_sha256=energy['sha256'],
               energy_generation=GENERATION,
               energy_original_field='energy_repeats[].energy_j / completed_tasks',
               runtime=row['backend'], runtime_policy=policy,
               timing_input={k: row[k] for k in ['prepared_image_sha256', 'contract_preprocessing'] if row.get(k)},
               measured_completion_mode=row.get('completion_mode') or None,
               execution_notes=notes)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True, help='Canonical archive containing the active CURRENT.json')
    ap.add_argument('--inputs', type=Path, required=True, help='Existing compact publication inputs whose quality evidence is preserved')
    ap.add_argument('--selection', type=Path, required=True, help='Original FINITE_MATRIX.json selecting exactly 75 UIDs')
    ap.add_argument('--output', type=Path, required=True, help='Fresh compact output directory outside the archive and existing inputs')
    a = ap.parse_args()
    b, previous, out = a.base.resolve(), a.inputs.resolve(), a.output.resolve()
    assert not out.is_relative_to(b) and not out.is_relative_to(previous), 'Output must be outside source inputs'
    assert not out.exists() or (out.is_dir() and not any(out.iterdir())), 'Use a fresh output directory'
    current_bytes = (b / 'CURRENT.json').read_bytes()
    cur = json.loads(current_bytes)
    assert cur['generation'] == GENERATION, 'Active Current is not the selected Native A4 generation'
    src = b / cur['selected_inputs']
    assert src.resolve().is_relative_to(b), 'Current inputs escape canonical archive'
    assert sha(src / 'MANIFEST.json') == cur['selected_input_manifest_sha256']
    manifest = read(src / 'MANIFEST.json')
    old_manifest = read(previous / 'MANIFEST.json')
    old = {name: checked(previous, old_manifest, name) for name in old_manifest}
    canonical = {name: checked(src, manifest, name) for name in
                 ['cases.json', 'pipeline_repeats.json', 'energy_repeats.json',
                  'native_refresh_provenance.json', 'provenance_limits.json', 'split_full_contracts.json']}
    cases, baseline = unique(canonical['cases.json']), unique(old['cases.json'])
    assert len(cases) == len(baseline) == 450 and set(cases) == set(baseline)
    selection = read(a.selection)
    cells = selection['cells']
    targets = {c['uid'] for c in cells}
    assert selection['schema'] == 'onnx-splitpoint/native-refresh-selection/v1'
    assert len(cells) == len(targets) == 75
    assert sum(c['backend'] == 'deepx_to_trt' for c in cells) == 68
    assert sum(c['backend'] == 'native_full_deepx' for c in cells) == 7
    for cell in cells:
        row = cases[cell['uid']]
        assert row['runner'] == 'native' and row['setup_id'] == 'DeepX'
        assert key(row) == key(cell), ('Finite selection identity changed', cell['uid'])
    provenance = canonical['native_refresh_provenance.json']
    assert set(provenance['targeted_uids']) == targets
    assert {uid for uid, row in cases.items() if row.get('native_refresh')} == targets
    assert all(cases[u] == baseline[u] for u in cases.keys() - targets), 'Nonselected case changed'
    assert all(quality(cases[u]) == quality(baseline[u]) for u in cases), 'Dataset quality changed'
    assert all(canonical[name] == old[name] for name in ['provenance_limits.json', 'split_full_contracts.json'])
    for name in ['pipeline_repeats.json', 'energy_repeats.json']:
        assert groups(canonical[name], targets) == groups(old[name], targets), ('Nonselected repeats changed', name)
        selected = [r for r in canonical[name] if r['uid'] in targets]
        assert len(selected) == 225 and collections.Counter(r['uid'] for r in selected) == dict.fromkeys(targets, 3)
        assert all(r['campaign'] == GENERATION and r['deepx_runtime_mode'] == 'A4'
                   and r['deepx_max_inflight'] == 4 for r in selected)
        if name == 'energy_repeats.json':
            assert all(r.get('source_sha256', r['source']['sha256']) == r['source']['sha256']
                       for r in selected), 'Energy source hash aliases differ'
    validation_path = b / cur['validation']
    assert validation_path.resolve().is_relative_to(b)
    validation = read(validation_path)
    binding = validation['activation_bindings']
    assert validation['status'] == 'PASS' and validation['cases'] == 450 and validation['targeted_cases'] == 75
    assert binding['generation'] == GENERATION
    assert binding['candidate_current_json_sha256'] == hashlib.sha256(current_bytes).hexdigest()
    assert binding['candidate_selected_manifest_sha256'] == cur['selected_input_manifest_sha256']
    # Identity and quality suffice for target preservation checks. Old target
    # performance/energy remain in the external migration backup, not this package.
    baseline_rows = [{k: v for k, v in row.items() if k in IDENTITY or 'quality' in k}
                     if row['uid'] in targets else row for row in old['cases.json']]
    evidence = [dict(row, **project_metadata(cases[row['uid']])) if row['uid'] in targets else row
                for row in old['selected_evidence.json']]
    assert all(quality(before) == quality(after) for before, after in zip(old['selected_evidence.json'], evidence))
    changed = {
        'baseline_cases.json': baseline_rows,
        'cases.json': canonical['cases.json'],
        'selected_evidence.json': evidence,
        'pipeline_repeats.json': canonical['pipeline_repeats.json'],
        'energy_repeats.json': [dict(r, source_sha256=r['source']['sha256'])
                                if r['uid'] in targets and 'source_sha256' not in r else r
                                for r in canonical['energy_repeats.json']],
        'native_refresh_provenance.json': dict(provenance, generation=GENERATION,
            selection_sha256=sha(a.selection), target_validation=cur['validation'],
            target_validation_sha256=sha(validation_path),
            baseline_target_records='identity_and_quality_only; historical metric rows remain outside the publication'),
        'source_binding.json': dict(old['source_binding.json'], generation=GENERATION,
            selected_inputs=cur['selected_inputs'], selected_input_manifest_sha256=cur['selected_input_manifest_sha256'],
            current_sha256=hashlib.sha256(current_bytes).hexdigest(),
            baseline_cases_sha256=hashlib.sha256((json.dumps(baseline_rows, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()).hexdigest(),
            previous_compact_manifest_sha256=sha(previous / 'MANIFEST.json'),
            projection='Current-selected Native A4 observations; 375 other observations and all selected dataset-quality evidence preserved',
            targeted_cases=75, unchanged_cases=375, quality_evaluations_started=0, measurement_starts=0),
    }
    assert (b / 'CURRENT.json').read_bytes() == current_bytes, 'Current changed during projection'
    out.mkdir(parents=True, exist_ok=True)
    for name in old_manifest:
        if name not in changed:
            (out / name).write_bytes((previous / name).read_bytes())
    for name, value in changed.items():
        write(out / name, value)
    write(out / 'MANIFEST.json', {p.name: sha(p) for p in sorted(out.glob('*.json')) if p.name != 'MANIFEST.json'})
    print(json.dumps({'status': 'PROJECTED', 'generation': GENERATION, 'cases': 450,
                      'targeted_cases': 75, 'unchanged_cases': 375,
                      'quality_selections_preserved': 450, 'performance_repeats': 225,
                      'energy_repeats': 225, 'measurement_starts': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
