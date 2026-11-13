"""Current observations preserve provenance, pairing and metric independence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import current_observations as current


class CurrentObservationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.case = dict(uid='generic|detector|H8|split|b001', model_id='detector', setup_id='H8',
            backend='split', case_id='b001', runner='generic', kind='split', model_sha256='model',
            fps=100., fps_samples=[100.]*3, performance_observations=3,
            performance_source_sha256='old-performance', raw_j_per_task=.2)
        self.raw = dict(identity={key:self.case[key] for key in current.IDENTITY+('model_sha256',)},
            completed_at='2026-10-27T15:00:00Z', observation_accepted=True,
            repetitions=[dict(fps=rate, pid=i+1, warmups=100, completed_tasks=1000)
                         for i, rate in enumerate([81., 80., 79.])],
            quality=dict(value=0., reference=.5, n=5000, bootstrap_repetitions=1000,
                quality_eligible=False, quality_class='accuracy_loss'),
            performance_source_sha256='wrong-performance')
        self.source = self.root/'actual_normal_result.json'
        self.source.write_text(json.dumps(self.raw))
        self.ref = lambda path:dict(source='actual', pointer=path)
        self.admission = dict(normal_api='normal_fixture_admission',
            accepted=self.ref('/observation_accepted'),
            checks=[dict(actual=self.ref('/identity/model_sha256'), expected='model')])
        self.metric = dict(actual_result='actual', completed_at=self.ref('/completed_at'),
            acquisition_origin='new_capture', normal_admission=self.admission,
            repetitions=[{key:self.ref(f'/repetitions/{i}/{key}') for key in row}
                         for i, row in enumerate(self.raw['repetitions'])])
        self.observation = dict(uid=self.case['uid'], prior_case_sha256=current.canonical_sha(self.case),
            identity={key:self.case[key] for key in current.IDENTITY},
            identity_evidence={key:self.ref('/identity/'+key) for key in current.IDENTITY+('model_sha256',)},
            generation='current_fixture', metrics=dict(performance=self.metric))
        self.document = dict(schema=current.SCHEMA, observations=[self.observation],
            sources=dict(actual=dict(path=self.source.name,
                sha256=hashlib.sha256(self.source.read_bytes()).hexdigest())))

    def apply(self):
        return current.apply_replacements([self.case], [dict(uid=self.case['uid'])],
            [dict(uid=self.case['uid'], energy_j=2., completed_tasks=10, duration_s=60,
                  repeat=0, source_sha256='old-energy')], [], self.document, self.root)

    def test_new_slower_fps_replaces_by_authority_and_clears_old_energy(self):
        cases, evidence, repeats, pipeline, history = self.apply()
        self.assertEqual(cases[0]['fps'], 80.)
        self.assertIsNone(cases[0]['raw_j_per_task'])
        self.assertFalse(cases[0]['normal_energy'])
        self.assertEqual(repeats, [])
        self.assertEqual(history[0]['case']['fps'], 100.)
        self.assertEqual(history[0]['case']['raw_j_per_task'], .2)
        self.assertEqual(self.case['fps'], 100.)
        self.assertEqual(len(pipeline), 3)

    def test_bad_source_hash_rejected(self):
        self.source.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'source hash differs'):
            self.apply()

    def test_recorded_pid_from_actual_process_clock_domain_is_not_controller_pid(self):
        for i, rep in enumerate(self.raw['repetitions']):
            rep.pop('pid')
            rep.update(clock_domain=f'perf_counter_ns:process:{900+i}', runtime_instance_id=f'runtime-{i}')
        self.source.write_text(json.dumps(self.raw))
        self.document['sources']['actual']['sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.metric['repetitions'] = [{key:self.ref(f'/repetitions/{i}/{key}') for key in rep}
            for i,rep in enumerate(self.raw['repetitions'])]
        _, _, _, pipeline, _ = self.apply()
        self.assertEqual([row['runner_pid'] for row in pipeline], [900, 901, 902])
        self.assertTrue(all(row['process_evidence']['namespace']=='dut_generic_python_process' for row in pipeline))
        self.assertTrue(all(row['process_evidence']['pid_source']=='request_latency.clock_domain' for row in pipeline))

    def test_stale_prior_row_rejected(self):
        self.case['fps'] = 101.
        with self.assertRaisesRegex(ValueError, 'prior row differs'):
            self.apply()

    def test_normal_diagnostic_observation_cannot_become_current_accepted_fps(self):
        self.raw['observation_accepted'] = False
        self.source.write_text(json.dumps(self.raw))
        self.document['sources']['actual']['sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'admission did not pass'):
            self.apply()

    def test_quality_join_to_other_fps_rejected(self):
        quality = dict(actual_result='actual', completed_at=self.ref('/completed_at'),
            acquisition_origin='new_capture', normal_admission=self.admission,
            performance_source_sha256=self.ref('/performance_source_sha256'))
        self.observation['metrics'] = dict(quality=quality)
        with self.assertRaisesRegex(ValueError, 'selected actual FPS source'):
            self.apply()

    def test_actual_zero_ap_and_quality_failure_retained(self):
        self.case.update(quality_primary_observation={'candidate':.9, 'ci_low':-.1},
            quality_relative_loss_ci=[.01,.02], quality_cached_loss_disagrees=True,
            quality_reference_delta_percentage_points=.3)
        self.observation['prior_case_sha256'] = current.canonical_sha(self.case)
        self.raw['performance_source_sha256'] = 'old-performance'
        self.source.write_text(json.dumps(self.raw))
        self.document['sources']['actual']['sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        quality = dict(actual_result='actual', completed_at=self.ref('/completed_at'),
            acquisition_origin='new_capture', normal_admission=self.admission,
            performance_source_sha256=self.ref('/performance_source_sha256'),
            **{key:self.ref('/quality/'+key) for key in self.raw['quality']})
        quality['primary_observation'] = self.ref('/quality')
        self.observation['metrics'] = dict(quality=quality)
        cases, evidence, repeats, _, _ = self.apply()
        self.assertEqual(evidence[0]['quality_value'], 0.)
        self.assertFalse(cases[0]['normal_quality'])
        self.assertEqual(cases[0]['quality_relative_loss'], 1.)
        self.assertEqual(cases[0]['quality_primary_observation']['value'], 0.)
        self.assertIsNone(cases[0]['quality_relative_loss_ci'])
        self.assertIsNone(cases[0]['quality_cached_loss_disagrees'])
        self.assertEqual(cases[0]['quality_reference_delta_percentage_points'], -50.)
        self.assertEqual(len(repeats), 1)

    def test_quality_label_does_not_supply_normal_admission(self):
        self.metric['normal_admission'] = dict(normal_api='label_only')
        with self.assertRaisesRegex(ValueError, 'normal admission authority'):
            self.apply()

    def test_full_baseline_cannot_be_replaced(self):
        self.case['kind'] = self.observation['identity']['kind'] = 'full'
        self.observation['prior_case_sha256'] = current.canonical_sha(self.case)
        with self.assertRaisesRegex(ValueError, 'Full baselines'):
            self.apply()

    def test_new_native_case_cannot_be_added(self):
        self.document['observations'][0].update(uid='new-native', prior_case_sha256=None,
            new_case=dict(uid='new-native', runner='native', kind='split'))
        with self.assertRaisesRegex(ValueError, 'Generic deployment'):
            self.apply()


if __name__ == '__main__':
    unittest.main()
