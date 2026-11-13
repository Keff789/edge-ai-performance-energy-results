#!/usr/bin/env python3
"""Cross-module R22 registration and independent identity checks."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from publication_mlsys import build_profile, OUTPUT_ROOT
from check_mlsys_profile import check_inventory, check_science


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo=Path(__file__).resolve().parents[3]
        cls.temp=tempfile.TemporaryDirectory()
        cls.output=Path(cls.temp.name)
        # Fresh broad exports are equivalent; this fixture reuses the canonical
        # current broad source, never any previously generated profile output.
        import shutil
        for name in ['data','tables']:
            shutil.copytree(cls.repo/'results/split-inference'/name,cls.output/name)
        build_profile(cls.repo,cls.output,numeric_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_independent_denominators_quality_and_cohorts(self):
        self.assertEqual(check_science(self.output)['quality_admissible'],407)

    def test_complete_inventory_and_figure_data_registration(self):
        manifest=check_inventory(self.repo,self.output)
        self.assertEqual(sum(a['kind']=='table' for a in manifest['assets']),28)

    def test_missing_plot_csv_registration_is_rejected(self):
        path=self.output/OUTPUT_ROOT/'ASSET_MANIFEST.json'
        original=path.read_bytes()
        try:
            manifest=json.loads(original)
            asset=next(a for a in manifest['assets'] if a['asset_id']=='fig:selectors')
            asset['outputs']=[p for p in asset['outputs'] if not p.endswith('.csv')]
            asset['repo_targets']=['results/split-inference/'+str(OUTPUT_ROOT/p) for p in asset['outputs']]
            path.write_text(json.dumps(manifest))
            with self.assertRaises(AssertionError):
                check_inventory(self.repo,self.output)
        finally:
            path.write_bytes(original)


if __name__=='__main__':
    unittest.main()
