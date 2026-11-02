#!/usr/bin/env python3
"""Focused regressions for scientific identity joins and inclusion semantics."""
import copy
import csv
import json
import unittest

from boundary_performance import DEFAULTS, build_payload, graph_catalogue, load_payload


class BoundaryPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = []
        for key in ('graph_universe', 'graph_features', 'candidates'):
            with DEFAULTS[key].open(newline='') as handle:
                cls.inputs.append(list(csv.DictReader(handle)))
        cls.inputs.append(json.loads(DEFAULTS['dataset'].read_text()))

    def inputs_copy(self):
        return copy.deepcopy(self.inputs)

    @staticmethod
    def target(rows, runner=None, case='b009'):
        return next(row for row in rows if row.get('model', row.get('model_id')) == 'yolov7_paper'
                    and row.get('accelerator', row.get('setup_id')) == 'H8'
                    and row.get('case_id') == case
                    and (runner is None or row.get('runner') == runner))

    def test_complete_profile_and_unique_measurements(self):
        payload = load_payload(DEFAULTS, 'yolov7_paper', 'H8', 'b066')
        self.assertEqual(payload['counts'], {'graph_boundaries': 308, 'workflow_boundaries': 307,
                                          'fixed_candidates': 20, 'generic_measured': 22,
                                          'generic_admissible': 21, 'native_measured': 3,
                                          'native_admissible': 3})
        self.assertEqual([r['boundary'] for r in payload['graph_boundaries']], list(range(308)))
        self.assertEqual(payload['merged_duplicate_uids'], ['generic|yolov7_paper|H8|hailo8_to_trt|b009'])
        failed = [r for r in payload['measurements'] if not r['quality_eligible']]
        self.assertEqual([(r['runner'], r['case_id']) for r in failed], [('generic', 'b306')])
        self.assertAlmostEqual(payload['full_reference']['fps'], 53.055325348859675)
        self.assertIn('tensorrt', payload['full_reference']['backend'])
        # A recorded quality evaluation is not the numerical admission criterion.
        hailo_full = next(r for r in payload['full_alternatives'] if 'hailo8' in r['backend'])
        self.assertFalse(hailo_full['quality_eligible'])
        self.assertGreater(hailo_full['relative_quality_loss'], .05)

    def test_conflicting_duplicate_is_not_silently_preferred(self):
        inputs = self.inputs_copy()
        self.target(inputs[3], 'generic')['fps'] += .5
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate.*FPS'):
            build_payload(*inputs)

    def test_wrong_candidate_boundary_id_rejected(self):
        inputs = self.inputs_copy()
        self.target(inputs[2])['boundary_id'] = self.target(inputs[2], case='b017')['boundary_id']
        with self.assertRaisesRegex(ValueError, 'boundary_id mismatch'):
            build_payload(*inputs)

    def test_missing_candidate_boundary_id_rejected(self):
        inputs = self.inputs_copy()
        self.target(inputs[2])['boundary_id'] = ''
        with self.assertRaisesRegex(ValueError, 'boundary_id mismatch'):
            build_payload(*inputs)

    def test_deployment_model_hash_mismatch_rejected(self):
        inputs = self.inputs_copy()
        self.target(inputs[3], 'native')['model_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'model hash mismatch'):
            build_payload(*inputs)

    def test_profile_difference_rejected(self):
        inputs = self.inputs_copy()
        row = next(r for r in inputs[0] if r['model'] == 'yolov7_paper' and r['case_id'] == 'b066')
        row['cut_bytes'] = str(float(row['cut_bytes']) + 1)
        with self.assertRaisesRegex(ValueError, 'Workflow/full graph mismatch'):
            build_payload(*inputs)

    def test_duplicate_graph_identity_rejected(self):
        inputs = self.inputs_copy()
        inputs[0].append(copy.deepcopy(next(r for r in inputs[0] if r['model'] == 'yolov7_paper')))
        with self.assertRaisesRegex(ValueError, 'Duplicate graph boundary'):
            build_payload(*inputs)

    def test_different_physical_host_rejected(self):
        inputs = self.inputs_copy()
        self.target(inputs[3], 'native')['physical_host'] = 'different_jetson'
        with self.assertRaisesRegex(ValueError, 'Physical host mismatch'):
            build_payload(*inputs)

    def test_technical_exclusion_never_creates_zero_fps_point(self):
        inputs = self.inputs_copy()
        row = self.target(inputs[2], case='b017')
        row.update(fps_measured='False', fps='', technical_exclusion='True', technical_reason='Compiler rejection')
        payload = build_payload(*inputs)
        self.assertFalse(any(r['case_id'] == 'b017' for r in payload['measurements']))
        self.assertEqual(payload['omitted'][0]['reason'], 'Compiler rejection')
        self.assertTrue(all(r['fps'] > 0 for r in payload['measurements']))

    def test_case_label_does_not_determine_graph_position(self):
        # Even a nonnumeric label binds to the explicitly recorded position.
        rows = [copy.deepcopy(next(r for r in self.inputs[0] if r['model'] == 'yolov7_paper'))]
        expected = int(rows[0]['boundary'])
        rows[0]['case_id'] = 'named_boundary'
        self.assertEqual(graph_catalogue(rows, 'yolov7_paper')['named_boundary']['boundary'], expected)


if __name__ == '__main__':
    unittest.main()
