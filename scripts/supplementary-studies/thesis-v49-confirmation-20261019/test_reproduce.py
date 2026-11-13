"""Small, hardware-free tests of the published table reproduction contract."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reproduce as r


MODELS = ['mobilenet_v3_large', 'regnet_x_1_6gf', 'resnet50', 'yolo11l', 'yolo26m', 'yolo26s', 'yolov7_paper']
SHA = 'a'*64


def fixture():
    catalog = []
    for model in MODELS:
        for kind in ('split', 'full'):
            backend = 'native_full_tensorrt' if kind == 'full' and model in {'yolo26m', 'yolo26s'} else 'native_full_deepx' if kind == 'full' else 'selected_split'
            host = 'H8' if model == 'yolo26m' else 'DeepX' if model != 'yolo11l' else 'H10'
            catalog.append(dict(uid=f'native|{model}|{host}|{backend}|'+('full' if kind == 'full' else 'b1'),
                model=model, kind=kind, setup_id='setup_'+host, host=host, runtime_backend=backend))
    facts = []
    for block in range(1, 6):
        order = list(catalog)
        target = next(row for row in catalog if (row['model'], row['kind']) ==
                      (('mobilenet_v3_large', 'full') if block == 4 else ('yolo11l', 'split')))
        order.remove(target); order.insert(8, target)
        for position, item in enumerate(order, 1):
            run = f'b{block:02}_p{position:02}'
            n = 6000+block*100+position
            null = run in {'b04_p09', 'b05_p09'}
            facts.append(dict(run_id=run, execution_run_id=run+'__a01', attempt_id='primary:'+run+':a01',
                session_id='primary', uid=item['uid'], setup_id=item['setup_id'], block=block, position=position,
                N_completed=n, interval_start_ns=10**12, interval_stop_ns=10**12+60_000_000_001,
                conditional_energy_j=None if null else 100+position, conditional_alignment_envelope_j=0.1,
                candidate_dropped_samples=64 if null else 0, candidate_raw_counter_discontinuities=1 if null else 0,
                A_valid=True, B_valid=not null, C_valid=False, target_sample_support_complete=not null,
                source_completion_verified=True,
                provenance={name: {'archive_member': f'runs/primary/{run}/{name}.json', 'sha256': SHA}
                            for name in ('attempt', 'analysis', 'timing', 'run_identity')}))
    # Seven old pairs already span acquisition sessions; two more use supplements.
    changed = 0
    for row in facts:
        if row['uid'].endswith('|full') and row['conditional_energy_j'] is not None and changed < 7:
            row['session_id'] = 'resume'
            row['attempt_id'] = 'resume:'+row['run_id']+':a01'
            changed += 1
    supplements = []
    for index, old in enumerate(row for row in facts if row['conditional_energy_j'] is None):
        row = copy.deepcopy(old)
        row.update(N_completed=500+index, conditional_energy_j=100.0, candidate_dropped_samples=0,
            candidate_raw_counter_discontinuities=0, A_valid=True, B_valid=True, C_valid=False,
            target_sample_support_complete=True, native_makespan_including_drain_s=60.0000000011,
            session_id='supplement', attempt_id='supplement:energy_'+old['run_id']+'__e01',
            execution_run_id='energy_'+old['run_id']+'__e01', attempt_number=1,
            collector_process_identity=[100+index, 10000+index], runtime_process_identity=[200+index, 20000+index],
            physical_source_GO_identity_sha256=str(index+1)*64)
        row['provenance'] = {key: {'archive_member': 'supplement/'+old['run_id']+'/'+key+'.json', 'sha256': SHA}
                             for key in row['provenance']}
        supplements.append(row)
    history = dict(schema='v49-confirmation-historical-repeats-v1', selection=[dict(uid=row['uid'], fps=50) for row in catalog],
        energy=[dict(uid=row['uid'], repeat=i, N_completed=100, duration_s=2, energy_j=10+i)
                for row in catalog for i in range(3)],
        performance=[dict(uid=row['uid'], repeat=i, N_completed=100, duration_s=2, reported_rate_per_s=49+i)
                     for row in catalog for i in range(3)])
    return dict(schema='v49-confirmation-measurement-inputs-v1', primary=facts, supplements=supplements), history, dict(uid_catalog=catalog)


def write_json(root, relative, value):
    path = root/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n')
    return dict(path=relative, sha256=r.digest(path.read_bytes()))


def quality_fixture(root, design):
    entries = []
    for mi, model in enumerate(MODELS):
        metrics = ['top1_accuracy'] if mi < 3 else ['coco_ap_50_95', 'ap50', 'ap75']
        full_uid = next(row['uid'] for row in design['uid_catalog'] if row['model'] == model and row['kind'] == 'full')
        split_uid = next(row['uid'] for row in design['uid_catalog'] if row['model'] == model and row['kind'] == 'split')
        values = np.empty((1000, 2, len(metrics)), dtype=np.float64)
        values[:, 0, :] = .7
        values[:, 1, :] = .7+np.arange(1000)[:, None]/100000
        stream = io.BytesIO(); np.savez_compressed(stream, values=values, delta=values[:, 1]-values[:, 0])
        relative = f'quality/{model}/values.npz'; path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(stream.getvalue())
        bootstrap = dict(path=relative, sha256=r.digest(path.read_bytes()))
        plan = dict(seed=42, image_ids=list(range(5000)), frozen_before_first_metric_result=True,
                    seed_schema=dict(B=1000, n=5000, model=model, full_uid=full_uid, split_uid=split_uid))
        plan_binding = write_json(root, f'quality/{model}/plan.json', plan)
        # The existing campaign's original plan and the public projection have distinct byte hashes.
        plan_binding['origin_sha256'] = 'b'*64
        result = dict(model=model, split_uid=split_uid, full_uid=full_uid, B=1000, n_images=5000, seed=42,
            exact_image_ids_paired=True, ground_truth_equal=True, cpu_relative_intervals_subtracted=False,
            plan_sha256='b'*64, bootstrap_values_sha256=bootstrap['sha256'],
            components={metric: dict(full=.7, split=.703, percentile_95_low=-999, percentile_95_high=999) for metric in metrics})
        result_binding = write_json(root, f'quality/{model}/result.json', result)
        entries.append(dict(model=model, result=result_binding, plan=plan_binding, bootstrap=bootstrap))
    write_json(root, 'quality/index.json', dict(schema='v49-confirmation-quality-inputs-v1', models=entries))


def input_fixture(root):
    measurements, history, design = fixture()
    bindings = [write_json(root, 'measurements.json', measurements), write_json(root, 'history_repeats.json', history)]
    write_json(root, 'design.json', design)
    def receipt(index):
        return dict(collector_process_started=True, collector_process_identity=[10+index, 1000+index],
            physical_source_GO_observed=True, physical_source_GO_identity_sha256=f'{index:064x}',
            runtime_process_started=True, runtime_process_identity=[100+index, 2000+index])
    attempts = dict(cohorts_pooled=False, primary_chain=[receipt(i) for i in range(72)],
        supplements=[receipt(i) for i in range(100, 102)], technical_diagnostics=[receipt(i) for i in range(200, 204)],
        other_cohorts={'r1':[receipt(300), receipt(301)], 'r2':[receipt(400), receipt(401)]})
    bindings.append(write_json(root, 'attempt_history.json', attempts))
    write_json(root, 'origin_provenance.json', dict(outputs=bindings))
    quality_fixture(root, design)
    return measurements, history, design


class ReproductionTests(unittest.TestCase):
    def test_own_N_and_primary_nulls_survive(self):
        measurements, history, design = fixture()
        data = r.build(measurements, history, design, [])
        own = data['supplements'][0]
        self.assertEqual(own['conditional_energy_j_per_completion'], 100/500)
        self.assertNotEqual(own['conditional_energy_j_per_completion'], 100/own['original_primary_N'])
        self.assertEqual(own['duration_s'], 60.0000000011)
        self.assertEqual(len(data['energies']), 68)
        self.assertEqual(data['aggregate']['target_records'][0]['primary_B'], None)
        self.assertFalse(own['primary_A_replaced'])

    def test_33_old_plus2_new_pairs_and9_cross_session(self):
        args = fixture(); data = r.build(*args, [])
        pairs = data['aggregate']['coverage_energy_pairs']
        self.assertEqual(len(data['pairs']), 35)
        self.assertEqual(len(data['energy_pairs']), 33)
        self.assertEqual(sum(row['cross_session'] for row in pairs), 9)
        self.assertEqual(sum(row['contains_supplement'] for row in pairs), 2)

    def test_means_medians_and_ranges_are_different_estimands(self):
        data = r.build(*fixture(), [])
        row = data['uid_statistics'][0]
        self.assertEqual(row['rate']['n'], 5)
        self.assertLess(row['rate']['observed_min'], row['rate']['observed_max'])
        model = data['aggregate']['seven_model_impacts'][0]
        self.assertIn('mean', model['primary_A_rate_statistics']['full'])
        self.assertEqual(model['coverage_energy_median_split_minus_full'],
            model['coverage_energy_statistics']['split']['median']-model['coverage_energy_statistics']['full']['median'])

    def test_GPU_full_reference_is_not_host_accelerator(self):
        data = r.build(*fixture(), [])
        model = next(row for row in data['aggregate']['seven_model_impacts'] if row['model'] == 'yolo26m')
        self.assertEqual(model['full_reference']['host'], 'H8')
        self.assertEqual(model['full_reference']['runtime_backend'], 'native_full_tensorrt')
        args = fixture(); args[2]['uid_catalog'][9]['runtime_backend'] = 'H8'
        with self.assertRaisesRegex(ValueError, 'TensorRT'):
            r.build(*args, [])

    def test_missing_B_cannot_be_replaced_by_zero_or_gap_interpolation(self):
        args = fixture(); missing = next(row for row in args[0]['primary'] if row['conditional_energy_j'] is None)
        missing['conditional_energy_j'] = 0
        with self.assertRaisesRegex(ValueError, 'positive_conditional'):
            r.build(*args, [])
        args = fixture(); args[0]['primary'][0]['candidate_dropped_samples'] = 1
        with self.assertRaisesRegex(ValueError, 'sample_gap'):
            r.build(*args, [])

    def test_duplicates_and_changed_supplement_target_fail(self):
        args = fixture(); args[0]['primary'][1]['run_id'] = args[0]['primary'][0]['run_id']
        with self.assertRaisesRegex(ValueError, 'unique_primary'):
            r.build(*args, [])
        args = fixture(); args[0]['supplements'][0]['uid'] = args[0]['primary'][0]['uid']
        with self.assertRaises(ValueError):
            r.build(*args, [])

    def test_direct_quality_recomputes_paired_percentiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _, _, design = fixture(); quality_fixture(root, design)
            rows, primary, _ = r.quality_tables(r.Inputs(root), r.validate_catalog(design))
            self.assertEqual(len(rows), 15); self.assertEqual(len(primary), 7)
            delta = (.7+np.arange(1000)/100000)-.7
            self.assertEqual(rows[0]['percentile_95_low'], float(np.percentile(delta, 2.5, method='linear')))
            self.assertNotEqual(rows[0]['percentile_95_low'], -999)

    def test_quality_rejects_unpaired_deltas(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _, _, design = fixture(); quality_fixture(root, design)
            index = json.loads((root/'quality/index.json').read_text()); item = index['models'][0]
            path = root/item['bootstrap']['path']
            with np.load(path) as old:
                values = old['values']
            np.savez_compressed(path, values=values, delta=np.zeros((1000, 1)))
            item['bootstrap']['sha256'] = r.digest(path.read_bytes())
            result = json.loads((root/item['result']['path']).read_text()); result['bootstrap_values_sha256'] = item['bootstrap']['sha256']
            item['result'] = write_json(root, item['result']['path'], result)
            write_json(root, 'quality/index.json', index)
            with self.assertRaisesRegex(ValueError, 'paired_delta'):
                r.quality_tables(r.Inputs(root), r.validate_catalog(design))

    def test_external_cli_is_deterministic_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = root/'inputs'; inputs.mkdir(); input_fixture(inputs)
            results = []
            for name in ('one', 'two'):
                process = subprocess.run([sys.executable, '-B', str(HERE/'reproduce.py'), '--inputs', str(inputs), '--output', str(root/name)],
                    cwd='/', text=True, capture_output=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                results.append({path.name: path.read_bytes() for path in (root/name).iterdir()})
            self.assertEqual(results[0], results[1])
            self.assertEqual(json.loads(results[0]['coverage.json'])['logical_energy_pairs'], 35)
            accounting = json.loads(results[0]['attempt_accounting.json'])
            self.assertEqual(next(row for row in accounting if row['history_scope'] == 'primary_R3_chain')['collector_process_starts'], 72)
            with self.assertRaisesRegex(ValueError, 'fresh_external'):
                r.generate(inputs, root/'one')

    def test_origin_hash_tamper_fails_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = root/'inputs'; inputs.mkdir(); input_fixture(inputs)
            (inputs/'measurements.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'input_hash_mismatch'):
                r.generate(inputs, root/'out')
            self.assertFalse((root/'out').exists())

    def test_path_escape_symlink_and_private_machine_fields_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = root/'inputs'; inputs.mkdir(); (root/'outside').write_text('{}')
            package = r.Inputs(inputs)
            for path in ('../outside', str(root/'outside')):
                with self.assertRaises(ValueError): package.json(path)
            (inputs/'link').symlink_to(root/'outside')
            with self.assertRaisesRegex(ValueError, 'escapes_package'): package.json('link')
            write_json(inputs, 'private.json', {'origin':'/home/user/data'})
            with self.assertRaisesRegex(ValueError, 'private_machine'): package.json('private.json')

    def test_copied_calculations_have_exact_segment_hashes(self):
        source = (HERE/'calculation_core.py').read_text()
        funcs = {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
        provenance = json.loads((HERE/'calculation_origins.json').read_text())
        self.assertEqual(r.digest(source.encode()), provenance['generated_module_sha256'])
        for origin in provenance['sources']:
            for function in origin['functions']:
                self.assertEqual(r.digest(funcs[function['name']].encode()), function['source_segment_sha256'])


if __name__ == '__main__':
    unittest.main()
