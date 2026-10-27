"""Uniform observation policy, original-population coverage and honest quality gates."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rq2_native_scope_test', HERE / 'reproduce.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
assembly_spec = importlib.util.spec_from_file_location('rq2_assembler_test', HERE / 'assemble_inputs.py')
assembler = importlib.util.module_from_spec(assembly_spec); assembly_spec.loader.exec_module(assembler)


class NativeScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bindings, cls.graph, cls.data, cls.frozen = engine.load_public(engine.REPO)
        cls.previous = engine.read(engine.REPO / engine.legacy.INPUT)

    def candidate(self, uid=None):
        row = copy.deepcopy(next(r for r in self.previous['rows'] if r['generic_uid'] == uid) if uid else self.previous['rows'][0])
        row.update(completed_at='2026-10-27T01:00:00+00:00', performance_source_sha256='a' * 64,
                   observation_id='observation-a', observation_origin='recovered')
        row['observation_contract'] = dict(valid=True, contract_evidence_sha256='b' * 64,
            proof_type='normal_current_ledger', ledger_row_sha256='c' * 64,
            identity_verified=True, complete_task_verified=True, product_identity=engine.product_identity(row))
        row['quality_binding'] = dict(verified=True, evidence_sha256='d' * 64,
            proof_type='normal_current_ledger', ledger_row_sha256='c' * 64,
            product_identity_verified=True, runtime_artifacts_and_inputs_bound=True,
            dataset_reference_evaluator_bound=True, reference_runtime='cpu_onnx',
            normal_admission=True, value=.99, reference=1., product_identity=engine.product_identity(row))
        old = self.bindings[row['generic_uid']]
        native = self.data[old['config_id']]
        return row, old, native

    def out420_candidate(self):
        fixed = {r['generic_uid'] for r in self.previous['rows']}
        uid = next(uid for uid in self.bindings if uid not in fixed)
        old = self.bindings[uid]
        native = self.data[old['config_id']]
        row, _, _ = self.candidate()
        row.update(generic_uid=uid, model=old['model'], setup=old['setup'], setup_id=native['physical_host'],
            case_id=old['case'], model_sha256=old['native_resolved_model_sha256'], boundary_id=old['resolved_boundary_id'],
            execution_precision=native['precision'], part2_input_count=1, boundary_count=1,
            full_product_identity=dict(direction=native['backend']),
            artifacts=dict(part1_sha256=old['native_part1_artifact_sha256'], part2_engine_sha256=old['native_part2_engine_sha256']),
            effective_generic_fps=float(old['generic_fps']))
        row['observation_contract']['product_identity'] = engine.product_identity(row)
        row['quality_binding']['product_identity'] = engine.product_identity(row)
        return row, old, native

    def test_latest_completed_fail_selected_over_older_pass(self):
        old, binding, native = self.candidate()
        newer = copy.deepcopy(old)
        newer.update(completed_at='2026-10-27T02:00:00+00:00', performance_source_sha256='f' * 64,
                     observation_id='observation-b', effective_generic_fps=.1)
        newer['quality_binding'].update(value=.1, normal_admission=False)
        chosen, _, _, reasons = engine.select_observation([old, newer], binding, native)
        self.assertFalse(reasons)
        self.assertEqual(chosen['observation_id'], 'observation-b')
        self.assertEqual(engine.generic_quality(chosen)['status'], 'accuracy_loss')
        old['effective_generic_fps'] = 999999
        chosen2, _, _, _ = engine.select_observation([newer, old], binding, native)
        self.assertEqual(chosen2['observation_id'], 'observation-b')

    def test_unknown_completion_order_held(self):
        row, binding, native = self.candidate(); row.pop('completed_at')
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertIsNone(chosen)
        self.assertIn('actual_generic_completion_order_unresolved', reasons)

    def test_contradicting_measurement_count_not_overridden_by_admission_label(self):
        row, binding, native = self.candidate()
        row['observation_contract']['completed_tasks_per_process'] = 999
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertIsNone(chosen)
        self.assertIn('generic_measurement_contract_completed_tasks_per_process_mismatched', reasons)

    def test_normal_product_pair_authority_checks_actual_quality_artifacts(self):
        row, binding, native = self.candidate()
        row['observation_contract']['proof_type'] = 'normal_product_pair_admission_plus_actual_three_repetitions'
        row['quality_binding']['proof_type'] = 'normal_product_pair_admission_with_actual_artifact_quality_evidence'
        row['quality_binding']['artifacts'] = copy.deepcopy(row['artifacts'])
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertFalse(reasons)
        self.assertTrue(engine.generic_quality(chosen)['admitted'])
        chosen['quality_binding']['artifacts']['part2_engine_sha256'] = 'e' * 64
        self.assertEqual(engine.generic_quality(chosen)['status'], 'unavailable')

    def test_invalidated_quality_pending_is_unavailable_and_keeps_fps(self):
        row, binding, native = self.candidate()
        row['quality_history'] = [dict(quality_status='accuracy_loss', value=0.0, historical_only=True)]
        row['quality_binding'] = dict(proof_type='corrected_normal_quality_pending', verified=False,
            normal_admission=False, normal_exclusion_reasons=['demonstrated_generic_quality_physical_layout_assignment_error'])
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertFalse(reasons)
        self.assertIsNotNone(chosen)
        quality = engine.generic_quality(chosen)
        self.assertEqual(quality['status'], 'unavailable')
        self.assertIsNone(quality['value'])
        self.assertIsNone(quality['relative_loss'])

    def test_standalone_fps_can_be_preserved_while_pair_compatibility_held(self):
        row, binding, native = self.candidate()
        row['pair_compatibility'] = dict(verified=False, evidence_sha256='a' * 64,
            reason='original_actual_preprocessing_authority_missing')
        historical_fps = row['effective_generic_fps']
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertIsNone(chosen)
        self.assertEqual(row['effective_generic_fps'], historical_fps)
        self.assertTrue(any('pair_compatibility_unresolved' in reason for reason in reasons))

    def test_reviewed_pair_uses_existing_evidence_without_filling_missing_recipe(self):
        uid = 'generic|yolov7_paper|H8|hailo8_to_trt|b009'
        actual = engine.read(engine.REPO / engine.INPUT)
        row = copy.deepcopy(next(r for r in actual['rows'] if r['generic_uid'] == uid
                                 and r.get('pairing_review')))
        native = self.data[self.bindings[uid]['config_id']]
        chosen, proof, _, reasons = engine.select_observation([row], self.bindings[uid], native)
        self.assertFalse(reasons)
        self.assertIsNotNone(chosen)
        self.assertFalse(chosen['pair_compatibility']['verified'])
        self.assertFalse(proof['full_historical_recipe_binding_verified'])
        self.assertTrue(engine.generic_quality(chosen)['admitted'])
        # A review cannot be transferred to another execution or used to admit
        # mismatched artifacts or a failing measured quality result.
        changed = copy.deepcopy(row)
        changed['performance_source_sha256'] = '0' * 64
        self.assertIsNone(engine.select_observation([changed], self.bindings[uid], native)[0])
        changed = copy.deepcopy(row)
        changed['artifacts']['part1_sha256'] = '0' * 64
        self.assertIsNone(engine.select_observation([changed], self.bindings[uid], native)[0])
        changed = copy.deepcopy(row)
        changed['quality_binding'].update(value=.1, normal_admission=False)
        self.assertFalse(engine.generic_quality(changed)['admitted'])

    def test_captures_and_standalone_quality_are_reported_even_when_pair_held(self):
        row, _, _ = self.candidate()
        row['pair_compatibility'] = dict(verified=False, evidence_sha256='e' * 64, reason='Native_preprocessing_authority_missing')
        row['performance_acquisition_origin'] = 'new_capture'
        row['quality_acquisition_origin'] = 'new_capture'
        row['quality_acquisition_source_sha256'] = 'f' * 64
        row['quality_completed_at'] = '2026-10-27T02:00:00+00:00'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'input.json'
            engine.write_json(path, dict(rows=[row], fixed420_uids=[]))
            summary = engine.run(root / 'output', numeric_only=True, input_path=path)
            self.assertEqual((summary['source_found'], summary['compatible_selected']), (1, 0))
            self.assertEqual((summary['new_fps_captured'], summary['new_quality_captured']), (1, 1))
            standalone = engine.read(root / 'output/tables/native_generic_quality_observations.json')[0]
            self.assertEqual(standalone['generic_quality_value'], .99)
            self.assertEqual(standalone['generic_quality_reference_value'], 1.)
            self.assertTrue(standalone['generic_quality_own_admitted'])
            self.assertFalse(standalone['pair_eligible'])
            self.assertTrue(any('Native_preprocessing_authority_missing' in reason for reason in standalone['pair_hold_reasons']))
            group = next(r for r in engine.read(root / 'output/data/pair_group_coverage.json') if r['source_found'])
            self.assertEqual((group['source_found'], group['compatible_selected'], group['remeasured'], group['new_quality_captured']), (1, 0, 1, 1))

    def test_quality_only_capture_does_not_become_fps_remeasurement(self):
        row, _, _ = self.candidate()
        row['quality_acquisition_origin'] = 'new_capture'
        row['quality_acquisition_source_sha256'] = 'f' * 64
        row['quality_completed_at'] = '2026-10-27T02:00:00+00:00'
        acquisitions = engine.acquisition_index(dict(rows=[row]))
        self.assertEqual(len(acquisitions[row['generic_uid']]['quality']), 1)
        self.assertEqual(len(acquisitions[row['generic_uid']]['fps']), 0)

    def test_assembly_retains_older_compatible_candidate_when_newer_artifacts_differ(self):
        old, binding, native = self.candidate()
        newer = copy.deepcopy(old)
        newer.update(completed_at='2026-10-27T03:00:00+00:00', performance_source_sha256='f' * 64,
                     observation_id='newer-incompatible', performance_acquisition_origin='new_capture')
        newer['artifacts']['part2_engine_sha256'] = 'e' * 64
        newer['observation_contract']['product_identity'] = engine.product_identity(newer)
        newer['quality_binding']['product_identity'] = engine.product_identity(newer)
        pool = {old['performance_source_sha256']: old}
        assembler.retain_performance_candidate(pool, old, newer, 'd' * 64)
        self.assertEqual(len(pool), 2)
        chosen, _, _, reasons = engine.select_observation(list(pool.values()), binding, native)
        self.assertFalse(reasons)
        self.assertEqual(chosen['performance_source_sha256'], old['performance_source_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'input.json'
            engine.write_json(path, dict(rows=list(pool.values()), fixed420_uids=[]))
            summary = engine.run(root / 'output', numeric_only=True, input_path=path)
            self.assertEqual(summary['pair_count'], 1)
            standalone = engine.read(root / 'output/data/standalone_generic_observations.json')
            new_row = next(r for r in standalone if r['generic_performance_source_sha256'] == newer['performance_source_sha256'])
            self.assertFalse(new_row['pair_compatible_selected'])
            self.assertFalse(new_row['pair_eligible'])
            self.assertIn('part2_engine_sha256_missing_or_mismatched', new_row['pair_hold_reasons'])
            self.assertEqual(summary['new_fps_captured'], 1)

    def test_assembly_retention_does_not_clear_existing_native_authority_hold(self):
        old, binding, native = self.candidate()
        old['pair_compatibility'] = dict(verified=False, evidence_sha256='e' * 64, reason='Native_preprocessing_authority_missing')
        newer = copy.deepcopy(old)
        newer.update(completed_at='2026-10-27T03:00:00+00:00', performance_source_sha256='f' * 64,
                     observation_id='newer-standalone', performance_acquisition_origin='new_capture')
        newer.pop('pair_compatibility')
        pool = {old['performance_source_sha256']: old}
        retained = assembler.retain_performance_candidate(pool, old, newer, 'd' * 64)
        self.assertFalse(retained['pair_compatibility']['verified'])
        chosen, _, _, reasons = engine.select_observation(list(pool.values()), binding, native)
        self.assertIsNone(chosen)
        self.assertTrue(any('Native_preprocessing_authority_missing' in reason for reason in reasons))

    def test_new_fps_candidate_does_not_inherit_a_quality_capture(self):
        old, _, _ = self.candidate()
        old.update(quality_acquisition_origin='new_capture', quality_acquisition_source_sha256='c' * 64,
                   quality_completed_at='2026-10-27T02:00:00+00:00')
        newer = copy.deepcopy(old)
        newer.update(completed_at='2026-10-27T03:00:00+00:00', performance_source_sha256='f' * 64,
                     observation_id='newer-fps-only', performance_acquisition_origin='new_capture')
        for key in ['quality_binding', 'quality_acquisition_origin', 'quality_acquisition_source_sha256', 'quality_completed_at']:
            newer.pop(key)
        pool = {old['performance_source_sha256']: old}
        retained = assembler.retain_performance_candidate(pool, old, newer, 'e' * 64)
        self.assertNotIn('quality_acquisition_origin', retained)
        acquired = engine.acquisition_index(dict(rows=list(pool.values())))
        self.assertEqual(len(acquired[old['generic_uid']]['quality']), 1)
        self.assertEqual(len(acquired[old['generic_uid']]['fps']), 1)
        self.assertEqual(retained['quality_correction']['status'], 'pending')

    def test_wrong_artifact_rejected(self):
        row, binding, native = self.candidate(); row['artifacts']['part2_engine_sha256'] = 'f' * 64
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertIsNone(chosen)
        self.assertTrue(reasons)

    def test_unbound_new_cut_rejected(self):
        row, _, native = self.candidate(); row['generic_uid'] = 'generic|new|H8|hailo8_to_trt|b999'
        chosen, _, _, reasons = engine.select_observation([row], None, native)
        self.assertIsNone(chosen)
        self.assertTrue(reasons)

    def test_quality_label_without_current_bound_evidence_unavailable(self):
        row, _, _ = self.candidate(); row.pop('quality_binding'); row['quality_eligible'] = True
        quality = engine.generic_quality(row)
        self.assertFalse(quality['admitted'])
        self.assertEqual(quality['status'], 'unavailable')
        self.assertIsNone(quality['relative_loss'])

    def test_quality_of_wrong_executable_unavailable(self):
        row, _, _ = self.candidate()
        row['quality_binding']['product_identity']['part2_engine_sha256'] = 'f' * 64
        self.assertEqual(engine.generic_quality(row)['status'], 'unavailable')

    def test_contract_name_alone_does_not_reject_real_full_postprocessing(self):
        row, binding, native = self.candidate()
        row['observation_contract']['completion_mode'] = 'fast_oracle_outside_timing'
        chosen, _, _, reasons = engine.select_observation([row], binding, native)
        self.assertIsNotNone(chosen)
        self.assertFalse(reasons)

    def test_outside_fixed420_original_native_pair_included_and_singleton_marked(self):
        row, binding, native = self.out420_candidate()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / 'input.json'
            engine.write_json(input_path, dict(rows=[row], fixed420_uids=[r['generic_uid'] for r in self.previous['rows']]))
            summary = engine.run(root / 'output', numeric_only=True, input_path=input_path)
            self.assertEqual(summary['original_native_population'], len(self.bindings))
            self.assertEqual(summary['outside_rq3_fixed420_pairs'], 1)
            self.assertEqual(summary['pair_count'], 1)
            pair = engine.read(root / 'output/data/current_pairs.json')[0]
            self.assertEqual(pair['native_fps'], native['fps'])
            self.assertFalse(pair['rq3_fixed420_member'])
            self.assertIsNone(pair['generic_mj_per_image'])
            groups = engine.read(root / 'output/data/quality_selection_groups.json')
            self.assertEqual(len(groups), 1)
            self.assertTrue(groups[0]['singleton'])
            self.assertFalse(groups[0]['ranking_evaluable'])
            self.assertEqual(summary['mean_final_generic_loss_pct'], 0.)
            self.assertIsNone(summary['mean_final_generic_loss_n_ge_2_pct'])
            coverage = engine.read(root / 'output/data/pair_group_coverage.json')
            self.assertEqual(sum(r['original'] for r in coverage), len(self.bindings))
            self.assertEqual(sum(r['quality_admitted'] + r['excluded'] + r['unresolved'] for r in coverage), len(self.bindings))

    def test_no_admitted_pairs_produces_unavailable_statistics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_path = root / 'input.json'
            engine.write_json(input_path, dict(rows=[], fixed420_uids=[]))
            summary = engine.run(root / 'output', numeric_only=True, input_path=input_path)
            self.assertEqual(summary['pair_count'], 0)
            self.assertEqual(summary['unresolved_candidates'], len(self.bindings))
            self.assertIsNone(summary['mean_final_generic_loss_pct'])


if __name__ == '__main__':
    unittest.main()
