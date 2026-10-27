"""Source-bound current RQ1 changes must preserve the literal archival guards."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publication_mlsys_r30 as r30


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


class CurrentSourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo, self.broad, self.inputs = [self.root / name for name in ['repo', 'broad', 'inputs']]
        self.old = [dict(uid='full', kind='full', fps=60),
            dict(uid='native|yolov7_paper|H8|hailo8_to_trt|b066', kind='split', fps=112),
            dict(uid='unaffected-split', kind='split', fps=50),
            dict(uid='native|yolov7_paper|H8|hailo8_to_trt|b009', kind='split', fps=100)]
        self.rows = copy.deepcopy(self.old)
        self.rows[-1]['fps'] = 80  # A slower actual observation is still current.
        self.document = {'schema': 'current-deployment-observations-v1', 'sources': {
            'actual': {'path': 'actual.json', 'sha256': 'a' * 64}},
            'observations': [dict(uid=self.rows[-1]['uid'], generation='actual-current',
                                  metrics={'performance': {'acquisition_origin': 'new_capture'},
                                           'quality': {'acquisition_origin': 'new_capture'}})]}
        self.source = self.inputs / 'current_observations.json'
        write(self.source, self.document)
        self.history = [dict(uid=self.rows[-1]['uid'], case=self.old[-1])]
        self.expected = {'data/PAPER_DATASET.json': self.rows,
            'data/current_observation_history.json': self.history,
            'tables/energy_repeats.json': [], 'tables/pipeline_repeats.json': [],
            'tables/table3_top2_native.json': []}
        write(self.repo / 'results/split-inference/data/PAPER_DATASET.json', self.old)
        write(self.broad / 'data/analysis_config.json', {})
        self.publish_current()

    def publish_current(self):
        for name, value in self.expected.items():
            write(self.broad / name, value)
        write(self.broad / 'data/current_observation_inputs.json', self.document)
        write(self.broad / 'data/current_observation_binding.json', dict(
            schema='current-deployment-input-binding-v1', observations_sha256=r30.digest(self.source),
            sources=self.document['sources'], prior_rows_preserved=True,
            hardware_measurements_performed_by_generator=False))

    def validate(self):
        def rebuild(inputs, output, config, current_observations):
            if current_observations is False:
                self.assertEqual(Path(inputs), self.repo / 'results/split-inference/data/inputs')
                write(Path(output) / 'data/PAPER_DATASET.json', self.old)
                return
            self.assertEqual(Path(inputs), self.inputs)
            self.assertEqual(Path(current_observations), self.source)
            for name, value in self.expected.items():
                write(Path(output) / name, value)
        # The dataset importer's real admission/repetition checks have their own
        # tests; this fixture isolates the publication's replay and archive joins.
        with patch('build_paper_dataset.build', side_effect=rebuild):
            return r30.current_rq1_binding(self.repo, self.broad, self.source, self.inputs)

    def test_declared_slower_current_observation_is_accepted_with_exact_source_provenance(self):
        result = self.validate()
        self.assertEqual(result['affected_observations'], [dict(uid=self.rows[-1]['uid'],
            generation='actual-current', metrics=['performance', 'quality'])])
        self.assertEqual(result['observation_inputs_sha256'], r30.digest(self.source))
        self.assertTrue(result['full_baselines_unchanged'] and result['literal_b066_unchanged'])
        self.assertTrue(result['new_native_measurements'])
        self.assertFalse(result['hardware_measurements_performed_by_generator'])

    def test_changed_row_without_matching_source_replay_is_rejected(self):
        changed = copy.deepcopy(self.rows)
        changed[-1]['fps'] = 200
        write(self.broad / 'data/PAPER_DATASET.json', changed)
        with self.assertRaisesRegex(AssertionError, 'Source-bound current data differs'):
            self.validate()

    def test_source_replay_cannot_override_full_or_literal_b066(self):
        for index in [0, 1]:
            with self.subTest(index=index):
                self.expected['data/PAPER_DATASET.json'] = copy.deepcopy(self.rows)
                self.expected['data/PAPER_DATASET.json'][index]['fps'] += 1
                self.publish_current()
                with self.assertRaisesRegex(AssertionError, 'Archived Full or literal b066 changed'):
                    self.validate()

    def test_changed_original_observation_input_is_rejected(self):
        write(self.source, {**self.document, 'changed': True})
        with self.assertRaisesRegex(AssertionError, 'Current observation input changed'):
            self.validate()

    def test_rebuilt_input_cannot_silently_change_an_undeclared_uid(self):
        self.expected['data/PAPER_DATASET.json'][2]['fps'] = 70
        self.publish_current()
        with self.assertRaisesRegex(AssertionError, 'Unaffected archived deployment changed'):
            self.validate()

    def test_unchanged_no_sidecar_path_has_no_current_override(self):
        (self.broad / 'data/current_observation_binding.json').unlink()
        self.assertIsNone(r30.current_rq1_binding(self.repo, self.broad))


class CurrentNumericalReferenceTests(unittest.TestCase):
    def test_current_b009_can_change_winner_without_changing_literal_b066_or_fulls(self):
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as temporary:
            baseline, broad = Path(temporary) / 'archived', Path(temporary) / 'current'
            from build_paper_dataset import build
            build(repo / 'results/split-inference/data/inputs', baseline,
                  json.loads((repo / 'results/split-inference/data/analysis_config.json').read_text()),
                  current_observations=False)
            for name in ['data', 'tables']:
                shutil.copytree(baseline / name, broad / name)
            rows = json.loads((broad / 'data/PAPER_DATASET.json').read_text())
            uid = 'native|yolov7_paper|H8|hailo8_to_trt|b009'
            changed = next(row for row in rows if row['uid'] == uid)
            changed.update(fps=300., fps_samples=[299., 300., 301.])
            write(broad / 'data/PAPER_DATASET.json', rows)
            # This exercises numeric data export only: no renderer or weights.
            reference = r30.current_core_reference(repo, broad)
            winners = json.loads(reference['tables/best_cases_table.json'])
            self.assertEqual(next(row for row in winners if row['model'] == 'yolov7_paper')['split_uid'], uid)
            original = json.loads((repo / 'results/split-inference/publications/mlsys-r22/figures/FIGURE_DATA.json').read_text())
            current = json.loads(reference['figures/FIGURE_DATA.json'])
            self.assertEqual(current['yolov7_h8_case'], original['yolov7_h8_case'])
            archived = repo / 'results/split-inference/publications/mlsys-r22/tables/full_performance_table.json'
            self.assertEqual(json.loads(reference['tables/full_performance_table.json']), json.loads(archived.read_text()))
            for name, encoded in reference.items():
                target = broad / 'publications/mlsys-r30' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(encoded)
            checker = r30.module(repo / 'scripts/split-inference/validation/check_mlsys_profile.py', 'current_checker_test')
            with patch.object(r30, 'current_rq1_binding', return_value={'verified_fixture': True}):
                checked = checker.check_current_science(repo, broad)
            self.assertEqual(checked['configurations'], len(rows))


class CurrentProfileVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / 'repo'
        self.broad = Path(self.temporary.name) / 'broad'
        self.r22 = self.repo / 'results/split-inference/publications/mlsys-r22'
        self.r30 = self.repo / 'results/split-inference/publications/mlsys-r30'
        frozen = {'yolov7_h8_case': {'points': [{'case': 'b066', 'fps': 112}]}}
        write(self.r22 / 'figures/FIGURE_DATA.json', frozen)
        write(self.r30 / 'figures/yolov7_h8_case_single_column.json', frozen['yolov7_h8_case'])
        write(self.r30 / 'data/frozen_r22_figure_data.json', frozen)
        write(self.r30 / 'data/profile_summary.json', {'measurement_changes': False, 'profile': r30.PROFILE})
        write(self.r30 / 'tables/best_cases_table.json', [{'fps': 100}])
        shutil.copytree(self.r22, self.broad / 'publications/mlsys-r22')
        self.output = self.broad / 'publications/mlsys-r30'
        shutil.copytree(self.r30, self.output)
        self.binding = {'schema': 'bound-current-fixture', 'affected_observations': [{'uid': 'b009'}]}
        write(self.output / 'data/current_rq1_binding.json', self.binding)
        write(self.output / 'data/profile_summary.json', {'measurement_changes': True,
            'profile': r30.PROFILE, 'current_rq1_observations': self.binding})
        write(self.output / 'tables/best_cases_table.json', [{'fps': 80}])
        self.reference = {'tables/best_cases_table.json': (self.output / 'tables/best_cases_table.json').read_bytes()}

    def validate(self):
        with patch.object(r30, 'current_rq1_binding', return_value=self.binding), \
                patch.object(r30, 'current_core_reference', return_value=self.reference):
            return r30.verify_profile(self.repo, self.broad)

    def test_current_asset_uses_fresh_reference_while_r22_stays_exact(self):
        self.assertEqual(self.validate()['result'], 'PASS')

    def test_current_mode_does_not_waive_numerical_asset_verification(self):
        write(self.output / 'tables/best_cases_table.json', [{'fps': 200}])
        with self.assertRaisesRegex(AssertionError, 'Current source-derived RQ1 differs'):
            self.validate()

    def test_current_mode_rejects_a_missing_rebuilt_export(self):
        (self.output / 'tables/best_cases_table.json').unlink()
        with self.assertRaisesRegex(AssertionError, 'Missing current source-derived RQ1 export'):
            self.validate()

    def test_current_mode_does_not_waive_literal_yolo_or_archive_guards(self):
        write(self.output / 'figures/yolov7_h8_case_single_column.json', {'points': []})
        with self.assertRaises(AssertionError):
            self.validate()


class CurrentAcquisitionMetadataTests(unittest.TestCase):
    def test_external_native_acquisition_is_not_generator_hardware_or_refit(self):
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary)
            summary = dict(quality_pair_count=1, quality_group_count=1,
                classifier_quality_pairs=0, detector_quality_pairs=1, models=['yolov7_paper'],
                groups_without_quality_pairs=[], scope='fixture', weights={'fixed': 1}, weight_policy='frozen')
            write(study / 'summary.json', summary)
            write(study / 'INPUT_MANIFEST.json', {'source_snapshot_sha256': 'a' * 64})
            self.assertFalse(r30.current_weighted_validation(study)['new_native_measurements'])
            summary['current_native_external_captures'] = dict(performance=1, quality=0, energy=0)
            write(study / 'summary.json', summary)
            result = r30.current_weighted_validation(study)
            self.assertTrue(result['new_native_measurements'])
            self.assertFalse(result['hardware_measurements_performed_by_generator'])
            self.assertFalse(result['weights_refitted'])

if __name__ == '__main__':
    unittest.main()
