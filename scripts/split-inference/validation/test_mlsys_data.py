"""R22 numerical oracles and adversarial checks, without plotting packages.

Full-precision oracles below were transcribed from the supplied R22 archive:
analysis/r19_output/yolov7_h8_case.csv, r20_output/quality_generic_selection.csv,
current_output/fastest_deployments.csv and reported_update/ranking_tables/
method_summary.csv. Archive SHA256 is recorded in the publication input spec.
These expectations are tests, never production selection inputs.
"""
import copy
import itertools
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]
REPO = SCRIPT.parents[1]
sys.path.insert(0, str(SCRIPT))
import publication_mlsys_data as data
from build_paper_dataset import build as build_dataset


# Model order is the published seven-model order, with H8/H10/DeepX per model.
# count, Generic choice, Native best, lost Native throughput (%), selected FPS, best FPS
R20_GROUPS = [
    (8,'b027','b027',0.,993.083599,993.083599),
    (9,'b027','b074',25.751565663652652,848.5888327723347,1142.9046825798443),
    (17,'b056','b135',48.12336109225727,804.9318017396938,1551.6267412219636),
    (20,'b066','b073',5.476326145995247,583.689262,617.505899),
    (20,'b052','b123',68.05463929240618,436.7290142209431,1367.1124837764846),
    (20,'b052','b109',45.81785439066508,395.0067738898496,729.0349421337696),
    (19,'b002','b038',4.711109546123138,553.944927,581.33212),
    (19,'b002','b095',54.46678185867402,500.6551031567817,1099.5381472990744),
    (19,'b002','b104',42.837409865626654,446.74949550676115,781.5417294013049),
    (3,'b120','b120',0.,43.776598201597565,43.776598201597565),
    (3,'b003','b120',16.31259175719374,44.591755271673506,53.2837092317369),
    (3,'b062','b062',0.,49.75397642714195,49.75397642714195),
    (3,'b043','b038',.21168169862483266,78.61904956868067,78.78582474076751),
    (3,'b038','b043',1.625883190391797,108.49918627804847,110.292412066109),
    (3,'b038','b043',3.230503938213447,95.04282611480488,98.21568777636374),
    (3,'b021','b021',0.,187.0049385138302,187.0049385138302),
    (3,'b021','b021',0.,181.93118513799513,181.93118513799513),
    (3,'b021','b021',0.,163.35948835722328,163.35948835722328),
    (3,'b066','b066',0.,112.86778421355565,112.86778421355565),
    (3,'b044','b044',0.,69.619008524253,69.619008524253),
    (3,'b044','b044',0.,64.04541779762341,64.04541779762341),
]
# split setup/cut, global Full backend/setup, split FPS/mJ, Full FPS/mJ, Rg/Rh, energy ratio
R22_WINNERS = [
    ('DeepX','b135','native_full_deepx','DeepX',1551.6267412219636,12.585884827419374,1469.2326117811697,12.009177335145056,1.0560797036358365,1.0560797036358365,1.0480222313469028),
    ('H10','b123','native_full_deepx','DeepX',1367.1124837764846,15.825866567203944,538.4109850699407,31.541578820300792,2.5391615730107993,4.328858760580097,.5017461762889973),
    ('H10','b095','native_full_deepx','DeepX',1099.5381472990744,29.458790892250505,656.1328389034252,27.64651178617798,1.6757858807016868,2.107885674071269,1.065551817896194),
    ('H10','b120','native_full_deepx','DeepX',53.2837092317369,555.753729911817,63.17858794512672,315.2272215384534,.8433824016139148,1.3622423922871911,1.763025817375428),
    ('H10','b043','native_full_tensorrt','H8',110.292412066109,319.6512627384614,84.76304109853896,400.025163961432,1.301185170290098,1.3095718423028733,.7990778869333337),
    ('H8','b021','native_full_tensorrt','DeepX',187.0049385138302,157.65165795795798,151.7882068523364,187.80006038659675,1.2320123044588938,1.2366267245505562,.8394654273988165),
    ('H8','b066','native_full_deepx','DeepX',112.86778421355564,330.140070508485,83.39511418585668,269.4394672773603,1.3534100326550946,2.12736013720405,1.2252847507623659),
]


class R22DataChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='r22-data-test-')
        cls.broad = Path(cls.tmp.name)/'archived-broad'
        build_dataset(REPO/'results/split-inference/data/inputs', cls.broad,
                      json.loads((SCRIPT/'config.json').read_text()), current_observations=False)
        cls.output = Path(cls.tmp.name)/'profile'
        cls.context = data.build(REPO, cls.broad, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def close(self, actual, expected):
        self.assertTrue(math.isclose(actual, expected, rel_tol=2e-12, abs_tol=1e-11), (actual,expected))

    def test_quality_counts_and_equal_group_means(self):
        s = self.context['summary']
        for field,value in [('configurations',450),('quality_eligible',407),('eligible_native_splits',187),
                            ('eligible_generic_splits',187),('eligible_fulls',33),('paired_candidates',204),
                            ('quality_paired_candidates',187),('quality_groups',21),('quality_exact_hits',9)]:
            self.assertEqual(s[field],value,field)
        self.close(s['quality_mean_loss_pct'],15.077128973324962)
        self.close(s['family_selection']['classification']['mean_loss_pct'],32.80433865060003)
        self.close(s['family_selection']['detection']['mean_loss_pct'],1.7817217153686513)
        self.assertEqual(s['family_selection']['classification']['pairs'],151)
        self.assertEqual(s['family_selection']['detection']['pairs'],36)
        self.assertTrue(s['global_winners_unchanged_at_5pct'])

    def test_all_twenty_one_quality_groups_match_full_precision_r20(self):
        groups = self.context['quality_selection_groups']
        self.assertEqual(len(groups),len(R20_GROUPS))
        for row,expected in zip(groups,R20_GROUPS):
            count,chosen,best,loss,selected_fps,best_fps = expected
            self.assertEqual((row['candidate_count'],row['generic_choice'],row['native_best']),(count,chosen,best))
            for field,value in [('loss_pct',loss),('selected_native_fps',selected_fps),('best_native_fps',best_fps)]:
                self.close(row[field],value)
            self.assertEqual(len(row['candidate_uids']),2*count)
        self.assertEqual(sum(r['candidate_count'] for r in self.context['selection_groups']),204)

    def test_seven_winner_coordinates_and_energy_match_full_precision_r22(self):
        for row,expected in zip(self.context['winners'],R22_WINNERS):
            self.assertEqual(tuple(row[k] for k in ['split_setup','split_case','global_full_backend','global_full_setup']),expected[:4])
            for key,value in zip(['split_fps','split_mj_per_image','global_full_fps','global_full_mj_per_image','R_global','R_host','energy_ratio_global'],expected[4:]):
                self.close(row[key],value)
            self.close(row['R_global'],row['split_record']['fps']/row['global_full_record']['fps'])
            self.close(row['energy_ratio_global'],row['split_record']['energy_j_per_image']/row['global_full_record']['energy_j_per_image'])
        self.assertEqual(self.context['summary']['globally_faster_models'],6)
        self.assertEqual(self.context['summary']['globally_faster_and_less_energy_models'],3)

    def test_yolov7_three_exact_deployments_quality_and_different_denominators(self):
        rows = self.context['yolov7_case']
        expected = [(32.0712613037562,549.8435630511002,40.77616377244088),
                    (53.055325348859675,598.4064624597721,46.02158790020155),
                    (112.86778421355565,330.140070508485,45.74084155464624)]
        for row,values in zip(rows,expected):
            for key,value in zip(['throughput_fps','system_energy_mj_per_image','coco_ap_50_95_percent'],values):
                self.close(row[key],value)
            self.close(row['reference_coco_ap_50_95_percent'],46.0346586685622)
        self.assertEqual([r['passes_5pct'] for r in rows],[False,True,True])
        split,accel=rows[2],rows[0]
        self.close(split['coco_ap_50_95_percent']-accel['coco_ap_50_95_percent'],4.96467778220536)
        self.assertLess(split['system_energy_mj_per_image'],accel['system_energy_mj_per_image'])
        self.assertGreater(self.context['winners'][-1]['energy_ratio_global'],1)

    def test_current_vendor_binding_all_hosts_and_48_original_energy_repetitions(self):
        vendor=json.loads((self.output/'tables/vendor_quality_recovery_table.json').read_text())
        for row,values in zip(vendor,[(60.62,71.58,10.96),(59.42,72.22,12.80),(71.72,72.18,.46)]):
            for key,value in zip(['full_quality','split_quality','quality_difference_pp'],values):self.close(row[key],value)
        ranges=json.loads((self.output/'tables/r21_winner_repeat_ranges.json').read_text())
        self.assertEqual(len(ranges),16)
        self.assertEqual(sum(len(r['fps_repeats']) for r in ranges),48)
        self.assertEqual(sum(len(r['energy_repeats_mj_per_image']) for r in ranges),48)
        row=next(r for r in ranges if r['uid']=='native|yolo26s|H8|hailo8_to_trt|b021')
        for actual,expected in zip(row['energy_repeats_mj_per_image'],[157.6803974499624,157.71555910375878,157.55901732015276]):self.close(actual,expected)
        self.assertEqual(row['energy_range'],'157.56--157.72')
        self.assertEqual({r['campaign'] for r in row['energy_repeat_source_bindings']},{'refresh16_20261013'})
        self.assertTrue(all(r['source_sha256'] for r in row['energy_repeat_source_bindings']))

    def test_historical_selector_results_remain_a_separate_cohort(self):
        rows=json.loads((self.output/'tables/ranking_tables.json').read_text())
        expected=[(6,.0377011716274378,.2528449058431817,.5508611854373832),
                  (6,.1378792205175893,.17283459484091723,.24566293306336093),
                  (6,.1281401645765981,.1964894571630482,.32022007244518425),
                  (6,.1378792205175893,.17283459484091723,.24566293306336093),
                  (7,.0925058428168986,.1742285164958115,.24566293306336093),
                  (11,0.,.12741933938579636,.28067101254949944)]
        for row,(hits,median,mean,energy) in zip(rows,expected):
            self.assertEqual(row['all_hits'],hits)
            self.assertEqual(row['energy_groups'],18)
            for key,value in [('median_loss_pct',median),('mean_loss_pct',mean),('mean_energy_excess_pct',energy)]:self.close(row[key],100*value)
        groups=self.context['historical_groups']
        self.assertEqual(len(groups),126)
        self.assertTrue(all(r['energy_excess_fraction'] is None for r in groups if r['model_id']=='yolov7_paper'))
        self.assertTrue(all(r['performance_basis']=='supplied_report_overlay_20261006' for r in groups if r['model_id']=='yolov7_paper'))

    def test_quality_advantages_and_exact_budget_reference_precision(self):
        rows=json.loads((self.output/'tables/r14_quality_advantages.json').read_text())
        fields=['native_candidates','admissible_fulls','faster_than_fastest_full','lower_energy_than_fastest_full',
                'both_vs_fastest_full','lower_energy_than_minimum_full']
        expected=[(204,42,105,77,65,72),(114,28,58,40,32,37),(147,30,88,61,52,56),(187,33,102,74,62,69)]
        self.assertEqual([tuple(r[k] for k in fields) for r in rows],expected)
        budgets=[r for r in self.context['budget_summary'] if r['scope']=='native_quality_5pct' and r['family']=='classification']
        expected=[(1,32.8043386506,32.2903249270113,1,.602829377364981),
                  (3,23.7682060169818,15.4064603675747,2,1.80848813209494),
                  (5,20.4477330488889,9.10421809459636,3,3.01414688682491)]
        for row,(k,generic,random,hits,random_hits) in zip(budgets,expected):
            self.assertEqual((row['requested_k'],row['generic_exact_hits']),(k,hits))
            for key,value in [('generic_mean_loss_pct',generic),('random_mean_expected_loss_pct',random),('random_expected_exact_hits',random_hits)]:self.close(row[key],value)
        capped=[r for r in self.context['budget_groups'] if r['family']=='detection' and r['requested_k']==5]
        self.assertTrue(all(r['actual_k']==3 and r['generic_loss_pct']==0 and r['random_expected_loss_pct']==0 for r in capped))

    def test_actual_full_uid_energy_and_host_means_are_distinct_and_old_top2_retained(self):
        rows={r['uid']:r for r in self.context['rows']}
        summaries=json.loads((self.output/'tables/full_performance_table.json').read_text())
        for summary in summaries:
            trt=[rows[uid] for uid in summary['trt_uids']]
            self.assertEqual(len(trt),3)
            self.close(summary['trt_fps'],statistics.mean(r['fps'] for r in trt))
            self.close(summary['trt_mj'],statistics.mean(r['energy_mj_per_image'] for r in trt))
        fulls=json.loads((self.output/'tables/current_full_details.json').read_text())
        for row in fulls:
            for prefix in ['accel','trt']:
                source=rows[row[prefix+'_uid']]
                self.close(row[prefix+'_fps'],source['fps'])
                self.close(row[prefix+'_mj'],1000*source['energy_j_per_image'])
                self.close(row[prefix+'_quality'],100*source['quality_value'])
        old=json.loads((self.broad/'tables/table3_top2_native.json').read_text())
        current=json.loads((self.output/'tables/current_top2_relative.json').read_text())
        for expected,actual in zip(old,current):
            self.assertEqual(expected,{key:actual[key] for key in expected})
        tex=(self.output/'tables/r14_budget_details.tex').read_text()
        self.assertIn(r'$\leq$5\% loss',tex)

    def test_independent_stage_recomputed_and_asset_scope_complete(self):
        stage=self.context['stage_summary']
        self.assertEqual(stage['comparison_rows'],12)
        self.assertEqual(len(stage['cases']),4)
        self.assertEqual(len(stage['pair_ratios']),6)
        self.assertTrue(all(r['direction_agrees'] for r in stage['pair_ratios']))
        self.assertEqual(stage['errors'],[])
        self.assertEqual(len(self.context['assets']),16)
        for label,asset in self.context['assets'].items():
            self.assertTrue(asset['input_uids'],label)
            self.assertTrue(all((self.output/p).is_file() for p in asset['outputs']),label)
            self.assertEqual(sum((self.output/p).read_text().count('\\label{'+label+'}') for p in asset['outputs'] if p.endswith('.tex')),1)

    def test_profile_generation_is_deterministic_and_imports_no_numeric_or_plot_package(self):
        second=Path(self.tmp.name)/'second'
        data.build(REPO,self.broad,second)
        for path in self.output.rglob('*'):
            if path.is_file():self.assertEqual(path.read_bytes(),(second/path.relative_to(self.output)).read_bytes(),str(path))
        self.assertFalse(any(name in sys.modules for name in ['matplotlib','numpy','pandas','scipy']))


class PublicationEdgeCases(unittest.TestCase):
    def test_quality_numeric_boundary_negative_loss_and_stale_flags(self):
        row=dict(quality_value=.95,quality_reference_value=1.,quality_numeric_relative_loss=.9,quality_class='accuracy_loss')
        # .95 is not an exact binary boundary; use an exactly representable case.
        self.assertTrue(data.eligible(dict(row,quality_value=.875),.125))
        self.assertFalse(data.eligible(dict(row,quality_value=.874999999999),.125))
        self.assertTrue(data.eligible(dict(row,quality_value=1.1)))
        self.assertIsNone(data.quality_loss(dict(row,quality_reference_value=0)))
        self.assertFalse(data.eligible(dict(row,quality_value=float('nan'))))
        self.assertFalse(data.eligible(dict(row,quality_value=None)))

    def test_exact_random_expectation_matches_enumeration_including_ties_and_cap(self):
        values=[1.,3.,3.,8.,8.]
        for requested in [1,3,5,9]:
            expected,hit,count=data.expected_random(values,requested)
            maxima=[max(r) for r in itertools.combinations(values,min(requested,len(values)))]
            self.assertEqual(count,len(maxima))
            self.assertAlmostEqual(expected,statistics.mean(maxima))
            self.assertAlmostEqual(hit,sum(x==8 for x in maxima)/len(maxima))

    def test_group_selection_unrounded_fps_uid_ties_and_equal_weight(self):
        rows=[dict(model='mobilenet_v3_large',setup='H8',case='low',native_uid='nlow',generic_uid='glow',native_fps=1.,generic_fps=2.000001),
              dict(model='mobilenet_v3_large',setup='H8',case='best',native_uid='nbest',generic_uid='gbest',native_fps=2.,generic_fps=2.),
              dict(model='mobilenet_v3_large',setup='H10',case='only',native_uid='nonly',generic_uid='gonly',native_fps=2.,generic_fps=2.)]
        original=copy.deepcopy(rows)
        groups=data.selection_groups(rows)
        self.assertEqual(groups[0]['generic_choice'],'low')
        self.assertEqual(groups[0]['loss_pct'],50.)
        self.assertEqual(groups,data.selection_groups(list(reversed(rows))))
        _,summaries=data.budget_calculations(rows,rows)
        summary=next(r for r in summaries if r['scope']=='native_quality_5pct' and r['family']=='all' and r['requested_k']==1)
        self.assertEqual(summary['generic_mean_loss_pct'],25.)
        self.assertEqual(rows,original)


if __name__=='__main__':
    unittest.main(verbosity=2)
