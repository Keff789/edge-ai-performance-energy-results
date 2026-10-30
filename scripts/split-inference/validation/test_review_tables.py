"""Check compact winner exports against the archived full-precision selections."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import render_review_tables as review


class ReviewTableChecks(unittest.TestCase):
    source = REPO / 'results/split-inference/publications/mlsys-r30/tables/r14_winner_quality.json'

    def test_same_selected_deployments_and_unrounded_numeric_payload(self):
        original = self.source.read_bytes()
        source_rows = json.loads(original)[:7]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            manifest = review.build(self.source, output)
            self.assertEqual(manifest['rows'], 7)
            for language in ('en', 'de'):
                base = output / 'artifacts' / language / 'tables' / review.STEM
                self.assertEqual(json.loads(base.with_suffix('.json').read_text()), source_rows)
                text = base.with_suffix('.tex').read_text()
                for delta in ('+0.30', '+0.46', '-0.38', '+0.71', '-0.79', '-0.93', '-0.12'):
                    self.assertIn(delta, text)
            for extension in ('.json', '.csv'):
                en = output / 'artifacts/en/tables' / (review.STEM + extension)
                de = output / 'artifacts/de/tables' / (review.STEM + extension)
                self.assertEqual(en.read_bytes(), de.read_bytes())
            self.assertEqual(manifest['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.source.read_bytes(), original)

    def test_rejects_inconsistent_quality_delta(self):
        rows = json.loads(self.source.read_text())
        rows[0]['quality_difference_pp'] += 1
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'corrupt.json'
            source.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, 'Quality delta'):
                review.winner_rows(source)

    def test_rejects_quality_inadmissible_or_duplicate_winners(self):
        rows = json.loads(self.source.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'corrupt.json'
            invalid = copy.deepcopy(rows)
            invalid[0]['split_quality_loss'] = 5.1
            source.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, 'quality-loss threshold'):
                review.winner_rows(source)
            source.write_text(json.dumps(rows + [rows[0]]))
            with self.assertRaisesRegex(ValueError, 'one source-selected global winner'):
                review.winner_rows(source)


if __name__ == '__main__':
    unittest.main()
