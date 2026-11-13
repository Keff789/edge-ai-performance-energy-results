#!/usr/bin/env python3
"""Focused checks of publication plot projections and numeric-only imports."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from publication_mlsys_figures import build_figure_data, METHODS


def fixture():
    winner = dict(model='resnet50', split_uid='native|split', split_runner='native',
                  split_setup='H8', split_case='cut-fast', global_full_uid='native|global',
                  host_full_uid='native|host', split_fps=20.00001, global_full_fps=10,
                  host_full_fps=8, R_global=2.000001, R_host=2.50000125,
                  split_energy_j_per_image=.03, global_full_energy_j_per_image=.02,
                  host_full_energy_j_per_image=.04, energy_ratio_global=1.5)
    groups = [dict(model='resnet50', setup=setup, candidate_count=2,
                   generic_choice='cut-slow', generic_choice_uid='generic|' + setup + '|slow',
                   selected_native_uid='native|' + setup + '|slow', native_best='cut-fast',
                   native_best_uid='native|' + setup + '|fast', selected_native_fps=10,
                   best_native_fps=20, loss_pct=50., exact_hit=False,
                   candidate_uids=[runner + '|' + setup + '|' + case
                                   for runner in ['native', 'generic'] for case in ['fast', 'slow']])
              for setup in ['H8', 'H10', 'DeepX']]
    resnet = [dict(uid='native|fast', model_id='resnet50', setup_id='H8', case_id='fast',
                   kind='split', runner='native', backend='hailo8_to_trt', fps=20,
                   energy_mj_per_image=30),
              dict(uid='native|low', model_id='resnet50', setup_id='H8', case_id='low',
                   kind='split', runner='native', backend='hailo8_to_trt', fps=19,
                   energy_mj_per_image=15)]
    yolo = [dict(configuration='Split cut', uid='native|yolov7', model='yolov7_paper', setup='H8',
                 runner='native', case='cut', throughput_fps=30, system_energy_mj_per_image=70,
                 coco_ap_50_95_percent=40, reference_coco_ap_50_95_percent=42, passes_5pct=True)]
    historical = [dict(model_id='resnet50', setup_id='H8', method=method, n=2, L_R=.125,
                       selected_case='old-slow', native_best_case='old-fast', top1_hit_tie_aware=False,
                       candidate_uids=['historical|old-slow', 'historical|old-fast']) for method in METHODS]
    return dict(winners=[winner], unfiltered_winners=[winner], selection_groups=groups,
                quality_selection_groups=groups, yolov7_case=yolo, resnet_h8=resnet,
                historical_groups=historical, source_generation='synthetic-current')


class PublicationFigureData(unittest.TestCase):
    def test_coordinates_reuse_exact_selected_uids_and_unrounded_ratios(self):
        context = fixture()
        original = copy.deepcopy(context)
        data = build_figure_data(context)
        row = context['winners'][0]
        baseline = data['fastest_split_baseline_comparison']['points'][0]
        tradeoff = data['fastest_deployment_tradeoff']['points'][0]
        self.assertEqual(baseline['split_uid'], tradeoff['split_uid'])
        self.assertEqual(baseline['global_full_uid'], tradeoff['global_full_uid'])
        self.assertEqual(baseline['R_global'], row['R_global'])
        self.assertEqual(baseline['R_host'], row['R_host'])
        self.assertEqual(tradeoff['x'], row['R_global'])
        self.assertEqual(tradeoff['y'], row['energy_ratio_global'])
        self.assertEqual(context, original)

    def test_missing_energy_only_omits_tradeoff_coordinate(self):
        context = fixture()
        context['winners'][0].update(energy_ratio_global=None, split_energy_j_per_image=None,
                                     split_energy_missing_reason='missing_energy_j_per_image')
        data = build_figure_data(context)
        baseline = data['fastest_split_baseline_comparison']['points'][0]
        self.assertTrue(baseline['global_plotted'])
        self.assertTrue(baseline['host_plotted'])
        self.assertEqual(data['fastest_deployment_tradeoff']['points'], [])
        missing = data['fastest_deployment_tradeoff']['omitted_points'][0]
        self.assertEqual(missing['split_uid'], 'native|split')
        self.assertEqual(missing['missing_values'], [dict(coordinate='energy_ratio_global',
                                                        reason='missing_energy_j_per_image')])

    def test_current_optima_and_historical_loss_keep_their_own_sources(self):
        context = fixture()
        data = build_figure_data(context)
        resnet = data['resnet_h8_energy_current']
        self.assertEqual(resnet['fastest_split_uid'], 'native|fast')
        self.assertEqual(resnet['lowest_energy_split_uid'], 'native|low')
        history = data['selector_loss_heatmap']
        self.assertEqual(history['cohort'], 'historical_graph_score_comparison')
        self.assertEqual({p['loss_pct'] for p in history['points']}, {12.5})
        self.assertEqual(history['input_uids'], ['historical|old-fast', 'historical|old-slow'])
        yolo = data['yolov7_h8_case']
        self.assertEqual(yolo['quality_threshold_percent'], .95 * 42)
        self.assertIn('CPU-relative', yolo['error_bars'])
        selected = data['quality_generic_selection_loss']
        self.assertEqual(selected['mean_weighting'], 'equal_model_setup_groups')
        self.assertEqual(selected['paired_candidates'], 6)
        self.assertEqual(len(selected['input_uids']), 12)

    def test_numeric_exports_do_not_import_plotting_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            code = '''import builtins, importlib.util, json, pathlib
original = builtins.__import__
def restricted(name, *args, **kwargs):
    if name.split('.')[0] in {'matplotlib', 'numpy'}:
        raise AssertionError('plotting dependency imported by numeric mode: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = restricted
spec = importlib.util.spec_from_file_location('figures', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
index, payload = module.write_figure_data(OUTPUT, CONTEXT)
assert len(index) == len(payload) == 8
assert len(list(pathlib.Path(OUTPUT).glob('figures/*.csv'))) == 7
assert not list(pathlib.Path(OUTPUT).glob('figures/*.png'))
assert not (pathlib.Path(OUTPUT) / 'figures/system_overview.csv').exists()
'''.replace('MODULE', repr(str(ROOT / 'publication_mlsys_figures.py'))).replace('OUTPUT', repr(directory)).replace('CONTEXT', repr(fixture()))
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
