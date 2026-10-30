import importlib.util
import json
from pathlib import Path
import unittest
SCRIPT=Path(__file__).with_name('energy_aware_selection.py')
if not SCRIPT.exists():SCRIPT=Path(__file__).resolve().parents[1]/'energy_aware_selection.py'
s=importlib.util.spec_from_file_location('energy',SCRIPT);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def row(uid,fps,energy,quality=.98):
    return dict(uid=uid,model_id='model',setup_id='setup',case_id=uid,kind='split',runner='native',included_joint=True,included_energy=True,included_performance=True,fps=fps,energy_mj_per_image=energy,quality_value=quality,quality_reference_value=1.)

class EnergySelectionTests(unittest.TestCase):
    def test_constraints_and_quality(self):
        rows=[row('fast',100,10),row('best',96,8),row('too_slow',94,1),row('bad_quality',99,1,.94)]
        result=m.select(rows,.95)[0]
        self.assertEqual(result['selected_case'],'best');self.assertAlmostEqual(result['energy_reduction_pct'],20)
        self.assertEqual(result['candidate_count'],3)
    def test_groups_and_ties(self):
        rs=[row('z',100,10),row('a',100,10),row('lower',98,10)]
        other=row('other',1000,1);other['setup_id']='another';rs.append(other)
        result=m.select(rs,.95)
        self.assertEqual(len(result),2);self.assertEqual(result[1]['selected_case'],'a')
    def test_reject_unjoint_and_invalid(self):
        rs=[row('fast',100,10),row('bad',99,float('nan')),row('unjoint',99,1)]
        rs[-1]['included_joint']=False
        self.assertEqual(m.select(rs,.95)[0]['candidate_count'],1)
    def test_archived_evidence(self):
        path=Path(__file__).with_name('PAPER_DATASET.json')
        if not path.exists():path=SCRIPT.resolve().parents[2]/m.SOURCE_PATH
        if not path.exists():self.skipTest('full repository dataset not in standalone test directory')
        rows=json.loads(path.read_text());rs=m.select(rows,.95)
        self.assertEqual(len(rs),21);self.assertEqual(sum(r['candidate_count'] for r in rs),187)
        self.assertEqual(sum(r['changed'] for r in rs),3)
        h8=next(r for r in rs if r['model']=='resnet50' and r['setup']=='H8')
        self.assertEqual((h8['fastest_case'],h8['selected_case']),('b038','b060'))
        self.assertAlmostEqual(h8['energy_reduction_pct'],9.502307952099553)
        for r in rs:
            self.assertGreaterEqual(r['throughput_retained_pct']+1e-12,95)
            self.assertGreaterEqual(r['energy_reduction_pct']+1e-12,0)

if __name__=='__main__':unittest.main()
