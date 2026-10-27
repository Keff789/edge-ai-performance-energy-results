#!/usr/bin/env python3
"""Checks for presentation-only translation and reversible renderer hooks."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from german_labels import GermanLabels
from german_tables import translate_tex, translate_markdown


class TranslationContract(unittest.TestCase):
    def test_active_english_source_authority(self):
        from reproduce import source_reference
        repo = Path('/repository')
        source = repo / 'results/publication-builds/generic420-20261027/paper'
        asset = Path('publications/mlsys-r30/figures/current_generic_selection_loss.json')
        self.assertEqual(source_reference(source / asset, repo, source),
                         str(source.relative_to(repo) / asset))
        historical = repo / 'results/split-inference'
        self.assertEqual(source_reference(historical / asset, repo, historical),
                         str(historical.relative_to(repo) / asset))
        external = Path('/temporary/reproduction')
        self.assertEqual(source_reference(external / asset, repo, external),
                         str(historical.relative_to(repo) / asset))
        relative = Path('results/publication-builds/generic420-20261027/paper')
        self.assertEqual(source_reference(relative / asset, Path.cwd(), relative),
                         str(relative / asset))

    def test_known_axis_and_unknown_prose(self):
        labels = GermanLabels()
        text = 'Maximum Native trials per group'
        self.assertEqual(labels.translate(text), 'Maximale Native-Tests je Gruppe')
        self.assertFalse(labels.known('A new unreviewed scientific claim', 'A new unreviewed scientific claim'))
        self.assertEqual(labels.translate('157.56'), '157.56')

    def test_numeric_rows_and_structural_identifiers(self):
        source = r'''\begin{table}
\label{tab:current-selection-groups}
\begin{tabular}{lrr}
Model & FPS & mJ/image \\
YOLO26s & 187.80 & 157.65 \\
\end{tabular}
\end{table}
'''
        translated = translate_tex(source)
        self.assertIn(r'\label{tab:current-selection-groups}', translated)
        self.assertIn('YOLO26s & 187.80 & 157.65', translated)
        self.assertIn('mJ/Bild', translated)
        self.assertIn('Modell', translated)

    def test_markdown_numeric_identity(self):
        source = '| Model | FPS |\n|---|---:|\n| YOLOv7 | 113 |\n'
        self.assertEqual(translate_markdown(source), source.replace('Model', 'Modell'))

    def test_text_hook_is_removed_even_on_error(self):
        from matplotlib.text import Text
        original = Text.set_text
        labels = GermanLabels()
        with self.assertRaises(RuntimeError):
            with labels.active():
                self.assertEqual(Text(text='Maximum Native trials per group').get_text(),
                                 'Maximale Native-Tests je Gruppe')
                raise RuntimeError('intentional test exit')
        self.assertIs(Text.set_text, original)
        self.assertEqual(Text(text='Maximum Native trials per group').get_text(),
                         'Maximum Native trials per group')


if __name__ == '__main__':
    unittest.main()
