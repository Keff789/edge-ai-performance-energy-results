"""Publication metadata must bind the documented relative CLI output."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publication_mlsys_r30 import bind_output_targets, profile_output_reference


class OutputAuthority(unittest.TestCase):
    def test_relative_cli_output_matches_absolute_output(self):
        repo = Path.cwd().resolve()
        output = Path('results/publication-builds/generic420-20261027/paper/publications/mlsys-r30')
        self.assertEqual(profile_output_reference(repo, output), output)
        self.assertEqual(profile_output_reference(repo, repo / output), output)
        assets = [{'outputs': ['figures/current_generic_selection_loss.json']}]
        bind_output_targets(assets, repo, output)
        self.assertEqual(assets[0]['repo_targets'], [str(output / assets[0]['outputs'][0])])

    def test_external_reproduction_retains_historical_reference(self):
        repo = Path.cwd().resolve()
        output = repo.parent / 'external-publication-reproduction'
        self.assertEqual(profile_output_reference(repo, output), Path('results/split-inference/publications/mlsys-r30'))


if __name__ == '__main__':
    unittest.main()
