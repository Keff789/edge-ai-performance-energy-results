import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('staged_selection', Path(__file__).with_name('reproduce.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(values, model='model', setup='device', task='classification'):
    pairs, rankings = [], []
    for rank, (generic, native) in enumerate(values, 1):
        uid = f'{model}|{setup}|b{rank:03d}'
        pairs.append(dict(native_uid=uid, model=model, setup=setup, task=task,
                          case=f'b{rank:03d}', generic_fps=generic, native_fps=native,
                          quality_eligible='True'))
        for method in module.METHODS:
            rankings.append(dict(model=model, setup=setup, method=method, rank=rank, native_uid=uid))
    return pairs, rankings


def pick(rows, k, policy='cascade_native2', method='bytes', task=None):
    return next(row for row in rows if row['k'] == k and row['policy'] == policy
                and row['method'] == method and (task is None or row['task'] == task))


class SelectionTests(unittest.TestCase):
    def test_second_native_test_resolves_generic_reversal(self):
        pairs, ranking = fixture([(110, 70), (100, 120), (90, 50)])
        rows = module.evaluate(pairs, ranking, 5)
        self.assertAlmostEqual(pick(rows, 3, 'cascade_native1')['loss_pct'], 100 * (1 - 70 / 120))
        self.assertEqual(pick(rows, 3)['loss_pct'], 0)
        self.assertEqual(pick(rows, 5)['generic_tests'], 3)
        self.assertEqual(pick(rows, 5)['native_tests'], 2)

    def test_more_generic_tests_can_displace_native_winner(self):
        pairs, ranking = fixture([(10, 100), (20, 30), (30, 40)])
        rows = module.evaluate(pairs, ranking, 3)
        self.assertEqual(pick(rows, 2)['loss_pct'], 0)
        self.assertEqual(pick(rows, 3)['loss_pct'], 60)
        self.assertEqual(pick(rows, 3)['preserves_shortlist_best'], 0)

    def test_generic_ties_do_not_consult_native_throughput(self):
        pairs, ranking = fixture([(10, 20), (10, 100), (10, 200)])
        row = pick(module.evaluate(pairs, ranking, 3), 3)
        self.assertEqual(row['native_tested'], 'b001;b002')
        self.assertEqual(row['selected_cut'], 'b002')
        self.assertEqual(row['retained_native_pct'], 50)

    def test_group_weights_do_not_follow_candidate_counts(self):
        small, small_rank = fixture([(50, 50), (100, 100)], model='small')
        large, large_rank = fixture([(100, 100)] * 5, model='large')
        rows = module.aggregate(module.evaluate(small + large, small_rank + large_rank, 1))
        result = pick(rows, 1, task='all')
        self.assertEqual(result['mean_retained_native_pct'], 75)
        self.assertEqual(result['groups'], 2)
        self.assertEqual(result['candidates'], 7)
        self.assertEqual(result['exact_winner_pct'], 50)

    def test_incomplete_or_duplicate_rankings_fail(self):
        pairs, ranking = fixture([(10, 10), (20, 20)])
        with self.assertRaisesRegex(ValueError, 'exactly'):
            module.evaluate(pairs, ranking[:-1], 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            module.evaluate(pairs + [pairs[0]], ranking, 2)

    def test_quality_and_invalid_rates_fail(self):
        pairs, ranking = fixture([(10, 10), (20, 20)])
        pairs[0]['quality_eligible'] = 'False'
        with self.assertRaisesRegex(ValueError, 'quality-ineligible'):
            module.evaluate(pairs, ranking, 2)
        pairs[0]['quality_eligible'] = 'True'
        pairs[0]['generic_fps'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Invalid throughput'):
            module.evaluate(pairs, ranking, 2)

    def test_published_direct_graph_curves(self):
        source = module.DEFAULT_STUDY
        details = module.evaluate(module.read_csv(source / 'data/quality_pairs.csv'),
                                  module.read_csv(source / 'analysis/complete_rankings.csv'))
        summary = module.aggregate(details)
        result = module.verify(details, summary, module.read_csv(source / 'analysis/aggregate_curves.csv'))
        self.assertEqual(result['direct_graph_aggregate_checks'], len(module.METHODS) * 20)
        self.assertEqual(result['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
