#!/usr/bin/env python3
"""Regression checks for corruption that the original verifier did not reject."""
from contextlib import redirect_stdout
import io
import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from fit_weights import run_one
from prepare_inputs import validate_published_source
from verify import verify_fit


def fixture():
    rows = []
    for model, task in [('a', 'classification'), ('b', 'classification'),
                        ('c', 'detection'), ('d', 'detection')]:
        for device in ['A', 'B']:
            for cut in range(6):
                rows.append(dict(generic_uid=f'{model}|{device}|{cut}', model=model,
                                 accelerator=device, task=task, case_id=f'b{cut:03}',
                                 analysis_eligible=True, analysis_group_complete=True,
                                 cut_bytes=100*(cut+1), C=cut/5, I=(5-cut)/5,
                                 T=(cut % 3)/2, fps=20+((cut+ord(model)+ord(device)) % 6)))
    return pd.DataFrame(rows)


class VerificationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = fixture()

    def build(self, name='primary', denominator=4):
        output = self.root/name
        with redirect_stdout(io.StringIO()):
            run_one(self.data, denominator, (1, 3, 5), output)
        return output

    def test_valid_fit_and_fold_weights_are_bound_to_reported_rankings(self):
        output = self.build()
        self.assertEqual(verify_fit(self.data, output)['metrics'], 1280)
        metrics = pd.read_csv(output/'heldout_metrics.csv')
        index = metrics.index[(metrics.method == 'global') & (metrics.k == 1)][0]
        old = metrics.loc[index, ['w_comm', 'w_imb', 'w_ten']].to_numpy(float)
        replacement = [0., 1., 0.] if old[0] == 1 else [1., 0., 0.]
        metrics.loc[index, ['w_comm', 'w_imb', 'w_ten']] = replacement
        metrics.to_csv(output/'heldout_metrics.csv', index=False)
        with self.assertRaises(AssertionError):
            verify_fit(self.data, output)

    def test_sensitivity_metrics_receive_the_same_arithmetic_checks(self):
        output = self.build('coarse_grid', 2)
        verify_fit(self.data, output)
        metrics = pd.read_csv(output/'heldout_metrics.csv')
        metrics.loc[0, 'loss_pct'] += 1
        metrics.to_csv(output/'heldout_metrics.csv', index=False)
        with self.assertRaises(AssertionError):
            verify_fit(self.data, output)

    def test_holdout_rejects_training_on_another_device_of_test_model(self):
        output = self.build()
        folds = pd.read_csv(output/'fold_weights.csv')
        folds.loc[0, 'train_models'] += ';'+folds.loc[0, 'test_model']
        folds.to_csv(output/'fold_weights.csv', index=False)
        with self.assertRaises(AssertionError):
            verify_fit(self.data, output)

    def test_feature_source_allows_only_terminal_newline_variation(self):
        path = self.root/'features.csv'
        data = b'model,Imb_raw\na,0.3'
        for reference in [data+b'\n', data+b'\n\n']:
            expected = hashlib.sha256(reference).hexdigest()
            for contents in [data, data+b'\n', data+b'\n\n']:
                path.write_bytes(contents)
                validate_published_source(path, expected)
        path.write_bytes(data.replace(b'0.3', b'0.4'))
        with self.assertRaises(ValueError):
            validate_published_source(path, expected)


if __name__ == '__main__':
    unittest.main()
