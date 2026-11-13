#!/usr/bin/env python3
"""Focused acceptance checks for the actual R22 evidence calculation/export API."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publication_mlsys_evidence as evidence


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[3]
        cls.broad = cls.repo/'results/split-inference'
        cls.audit, cls.sources = evidence.recompute(cls.repo, cls.broad)

    def test_ridge_mse_unit_penalty_and_unpenalized_intercept(self):
        train = [{'prefix_compute_fraction': x, 'boundary_bytes': 0,
                  'generic_fps': 10, 'native_fps': 10*math.exp(2+x)} for x in (-1, 0, 1)]
        beta, means, scales = evidence.r15.fit_ridge(train)
        self.assertAlmostEqual(beta[0], 2)
        self.assertAlmostEqual(beta[1], math.sqrt(2/3)/2)
        self.assertEqual(beta[2], 0)
        self.assertEqual(means, [0, 0])
        self.assertAlmostEqual(scales[0], math.sqrt(2/3))
        self.assertEqual(scales[1], 1)

    def test_architecture_memberships_and_cost_population(self):
        calibration = self.audit['calibration']
        self.assertEqual(len(calibration['folds']), 9)
        self.assertEqual(len(calibration['predictions']), 151)
        self.assertEqual(len({r['uid'] for r in calibration['memberships'] if r['role'] == 'train'}), 151)
        for fold in calibration['folds']:
            members = [r for r in calibration['memberships'] if r['fold_id'] == fold['fold_id']]
            train = [r for r in members if r['role'] == 'train']
            test = [r for r in members if r['role'] == 'test']
            self.assertEqual({r['model'] for r in test}, {fold['held_out_architecture']})
            self.assertNotIn(fold['held_out_architecture'], {r['model'] for r in train})
            self.assertFalse({r['uid'] for r in train} & {r['uid'] for r in test})

    def test_budget_full_precision_oracles_and_unavailable_detector_budget(self):
        results = self.audit['calibration']['budget_results']
        self.assertAlmostEqual(results['classification|generic|1']['regret_pct'], 32.8043386506, places=8)
        self.assertAlmostEqual(results['detection|generic|1']['regret_pct'], 1.7817217154, places=8)
        for row in self.audit['calibration']['groups']:
            if row['task'] == 'detection' and row['k'] == 5:
                self.assertEqual(row['status'], 'unavailable')
                self.assertIsNone(row['regret_pct'])
            if row['method'] == 'uniform_random' and row['status'] == 'evaluated':
                self.assertEqual(row['random_subset_count'], math.comb(row['n'], row['k']))

    def test_three_scheduling_studies_remain_separate(self):
        studies = self.audit['scheduling']
        self.assertEqual([studies[k]['raw_reports_recomputed'] for k in studies], [40, 40, 20])
        identities = [set(s['process_uids']) for s in studies.values()]
        self.assertFalse(identities[0] & identities[1] or identities[0] & identities[2] or identities[1] & identities[2])
        self.assertEqual(sum(s['block_contrasts'] for s in studies.values()), 85)
        self.assertEqual(sum(s['summary_contrasts'] for s in studies.values()), 17)
        self.assertAlmostEqual(studies['regnet']['estimates']['interaction']['geometric_mean'], 5.10808, places=5)
        self.assertAlmostEqual(studies['resnet']['estimates']['interaction']['geometric_mean'], 3.4288, places=4)

    def test_r20_exact_compact_projection_checks(self):
        self.assertTrue(self.audit['r20']['generator_verified'])
        self.assertEqual(self.audit['r20']['value_checks'], {
            'detectors': 96, 'workloads': 450, 'energy_configurations': 75,
            'energy_windows': 225, 'case_quality_rows': 3})

    def test_rendered_table_series_and_budget_mapping_against_bound_reference(self):
        tables = {r['stem']: r for r in evidence.tables(self.audit)}
        source = self.sources.path('r15')
        saved_budget = {(r['task'], r['method'], int(r['k'])): r
                        for r in evidence.r15.rows(source/'audit_regnet/results/calibration_summary.csv')
                        if r['cohort'] == 'confirmed'}
        for row in tables['r15_budget']['records']:
            for k in (1, 3, 5):
                saved = saved_budget[(row['task'], row['method'], k)]
                expected = saved['mean_native_regret_pct_or_expectation']
                if expected:
                    self.assertAlmostEqual(row['regret_k'+str(k)], float(expected), places=10)
                else:
                    self.assertIsNone(row['regret_k'+str(k)])
        saved_series = {
            'regnet': {r['contrast']: r for r in evidence.r15.rows(source/'audit_regnet/results/mechanism_confirmation_summary.csv')
                       if r['cohort'] == 'primary'},
            'resnet': {r['contrast']: r for r in evidence.r15.rows(source/'resnet_replication/results/replication_analysis_summaries.csv')},
        }
        count = 0
        for row in tables['r15_mechanism']['records']:
            for series, saved in saved_series.items():
                for field in ['geometric_mean', 'ci95_low', 'ci95_high']:
                    self.assertAlmostEqual(row[series+'_'+field], float(saved[row['contrast']][field]), places=10)
                count += 1
        self.assertEqual(count, 8)
        for row in tables['r15_scheduling_summary']['records']:
            for series, saved in saved_series.items():
                for field in ['geometric_mean', 'ci95_low', 'ci95_high', 'sd_log']:
                    self.assertAlmostEqual(row[series+'_'+field], float(saved[row['contrast']][field]), places=10)

    def test_rendering_and_tampered_artifact_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            metadata = evidence.build(self.repo, self.broad, out)
            self.assertEqual(len(metadata['assets']), 7)
            self.assertEqual(evidence.validate(self.repo, self.broad, out)['status'], 'PASS')
            target = out/'tables/r15_mechanism.json'
            target.write_text(target.read_text().replace('0.660', '0.760', 1))
            with self.assertRaisesRegex(ValueError, 'output differs'):
                evidence.validate(self.repo, self.broad, out)

    def test_mapping_cannot_escape_repository(self):
        with self.assertRaisesRegex(ValueError, 'unsafe logical'):
            self.sources.path('../unbound.json')


if __name__ == '__main__':
    unittest.main()
