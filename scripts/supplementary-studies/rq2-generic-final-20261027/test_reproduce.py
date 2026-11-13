"""Identity gates and measured-cohort regression checks, with no hardware."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('rq2_final_test_engine',HERE/'reproduce.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


class FinalPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bindings,cls.graph,cls.data,cls.frozen=engine.load_public(engine.REPO)
        cls.rows=engine.read(engine.REPO/engine.INPUT)['rows']

    def candidate(self):
        row=copy.deepcopy(self.rows[0]);old=self.bindings[row['generic_uid']]
        native=self.data[row['generic_uid'].replace('generic|','native|',1)]
        return row,old,native

    def test_cut_name_cannot_override_changed_graph(self):
        row,old,native=self.candidate();row['boundary_id']='different_graph_same_cut'
        self.assertIn('model_or_graph_frontier_mismatch',engine.bind(row,old,native)[0])

    def test_artifact_change_rejects_join(self):
        row,old,native=self.candidate();row['artifacts']['part2_engine_sha256']='0'*64
        self.assertIn('part2_engine_sha256_missing_or_mismatched',engine.bind(row,old,native)[0])

    def test_physical_host_change_rejects_join(self):
        row,old,native=self.candidate();row['setup_id']='different_device'
        self.assertIn('physical_device_mismatch',engine.bind(row,old,native)[0])

    def test_source_measurement_change_rejects_join(self):
        row,old,native=self.candidate();native=copy.deepcopy(native);native['performance_source_sha256']='0'*64
        self.assertIn('native_measurement_source_mismatch',engine.bind(row,old,native)[0])

    def test_unknown_precision_is_preserved_with_exact_executable_relation(self):
        row=next(r for r in self.rows if r['generic_uid']=='generic|yolo26s|H8|hailo8_to_trt|b003')
        native=self.data[row['generic_uid'].replace('generic|','native|',1)]
        reasons,proof=engine.bind(row,self.bindings[row['generic_uid']],native)
        self.assertFalse(reasons);self.assertIsNone(proof['native_recorded_precision'])
        self.assertIsNone(proof['comparison_precision']);self.assertIn('same_bound_executable',proof['precision_basis'])

    def test_full_numeric_reproduction_and_energy_separation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'result'
            summary=engine.run(output,numeric_only=True,verify_reference=engine.REPO/engine.STUDY)
            self.assertEqual((summary['pair_count'],summary['quality_pair_count'],summary['quality_group_count']),(192,159,13))
            self.assertAlmostEqual(summary['mean_final_generic_loss_pct'],2.1592394401146824)
            self.assertAlmostEqual(summary['mean_old_generic_loss_same_pairs_pct'],22.959196291816436)
            pairs=engine.read(output/'data/current_pairs.json')
            self.assertTrue(all(r['generic_mj_per_image'] is None and r['native_mj_per_image'] is None for r in pairs))
            self.assertFalse(next(r for r in pairs if r['generic_uid']=='generic|yolov7_paper|H8|hailo8_to_trt|b009')['quality_eligible'])
            sources=engine.read(output/'INPUT_MANIFEST.json')['sources']
            self.assertIn(str(engine.OLD/'analysis/candidate_features.csv'),[r['path'] for r in sources])


if __name__=='__main__':unittest.main()
