"""Reviewed German labels applied before Matplotlib computes text layout.

Only presentation strings change. Artist coordinates and numeric source payloads
are never translated. Unknown visible strings are reported by the export audit.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent


class GermanLabels:
    def __init__(self, decimal_comma=False):
        self.decimal_comma = decimal_comma
        self.catalog = json.loads((HERE / 'locales/figures_de.json').read_text(encoding='utf-8'))
        self.targets = set(self.catalog.values())
        self.rules = []
        self._neutral = lambda text: False
        try:
            from figure_terms import DYNAMIC_TRANSLATIONS, is_neutral
            self.rules = [(re.compile(pattern), replacement) for pattern, replacement in DYNAMIC_TRANSLATIONS]
            self._neutral = is_neutral
        except ImportError:
            pass
        self.figures = {}
        self._origins = {}

    def translate(self, text):
        if not isinstance(text, str) or not text.strip():
            return text
        if self.decimal_comma and re.fullmatch(r'[+−\-0-9.,%×/ =]+', text):
            return text.replace('.', ',')
        if text in self.catalog:
            return self.catalog[text]
        if text in self.targets:
            return text
        # Preserve deliberate multiline labels; normalizing them first collapses
        # compact bar labels and causes overlaps in the dissertation profile.
        if '\n' in text:
            return '\n'.join(self.translate(line) for line in text.split('\n'))
        normalized = re.sub(r'\s+', ' ', text).strip()
        if normalized in self.catalog:
            return self.catalog[normalized]
        for pattern, replacement in self.rules:
            if pattern.fullmatch(text):
                return pattern.sub(replacement, text)
        if '\n' in text:
            return '\n'.join(self.translate(line) for line in text.split('\n'))
        return text

    def known(self, source, target):
        if not source.strip() or source in self.catalog or source in self.targets or self._neutral(source):
            return True
        if re.sub(r'\s+', ' ', source).strip() in self.catalog:
            return True
        if any(pattern.fullmatch(source) for pattern, _ in self.rules):
            return True
        if '\n' in source:
            return all(self.known(line, self.translate(line)) for line in source.split('\n'))
        # Numeric tick marks and purely mathematical notation are language-neutral.
        if not re.search(r'[A-Za-z]', source):
            return True
        if re.fullmatch(r'\$[^$]*\$', source) and not re.search(r'\\(?:text|mathrm)\{[A-Za-z]{3,}', source):
            return True
        if re.fullmatch(r'(?:[a-zA-Z]?=?[+−-]?\d+(?:[.,]\d+)?(?:%|x|×)?\s*)+', source):
            return True
        return False

    @contextmanager
    def active(self):
        from matplotlib.text import Text
        from matplotlib.figure import Figure
        original_set_text, original_savefig = Text.set_text, Figure.savefig
        owner = self

        def set_text(artist, value):
            original = '' if value is None else str(value)
            translated = owner.translate(original)
            # A later redraw may set an already translated label again.
            old = getattr(artist, '_german_source_text', None)
            if old is None or original != owner.translate(old):
                artist._german_source_text = original
            return original_set_text(artist, translated)

        def savefig(figure, filename, *args, **kwargs):
            figure.canvas.draw()
            unknown = set()
            labels = []
            for artist in figure.findobj(match=Text):
                if not artist.get_visible() or not artist.get_text().strip():
                    continue
                source = getattr(artist, '_german_source_text', artist.get_text())
                target = artist.get_text()
                labels.append({'en': source, 'de': target})
                if not owner.known(source, target):
                    unknown.add(source)
            key = str(Path(filename).with_suffix(''))
            owner.figures[key] = {'labels': sorted({(x['en'], x['de']) for x in labels}),
                                  'untranslated': sorted(unknown)}
            return original_savefig(figure, filename, *args, **kwargs)

        Text.set_text, Figure.savefig = set_text, savefig
        try:
            yield self
        finally:
            Text.set_text, Figure.savefig = original_set_text, original_savefig

    def report(self):
        return {'figures_checked': len(self.figures),
                'untranslated': sorted({s for item in self.figures.values() for s in item['untranslated']}),
                'figures': self.figures}
