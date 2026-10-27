"""Declared dynamic German labels for the dissertation figure export.

Every rule is anchored and preserves numeric fields. Unknown prose is not
translated by word substitution. The caller should record unmatched labels.
"""
import re

DYNAMIC_TRANSLATIONS = [
    (r'^(DeepX|H8|H10): quality (\d+)/(\d+)$', r'\1: Qualität \2/\3'),
    (r'^(.+): selected existing dataset quality$', r'\1: gemessene Datensatzqualität'),
    (r'^(\d+)/(\d+) hits$', r'\1/\2 Treffer'),
    (r'^(\d+) models$', r'\1 Modelle'),
    (r'^n=(\d+) · front=(\d+)$', r'n=\1 · Pareto-Punkte=\2'),
    (r'^All measured Full configurations: throughput \(n=(\d+)/(\d+)\)$',
     r'Alle gemessenen Full-Konfigurationen: Durchsatz (n=\1/\2)'),
    (r'^All measured Full configurations: energy \(n=(\d+)/(\d+)\)$',
     r'Alle gemessenen Full-Konfigurationen: Energie (n=\1/\2)'),
    (r'^Existing dataset quality: (\d+)/(\d+) numerical candidate/reference observations$',
     r'Datensatzqualität: \1/\2 numerische Kandidat-Referenz-Vergleiche'),
    (r'^(\d+) selected model\(s\) lack a required ratio; see FIGURE_DATA\.json\.$',
     r'Bei \1 gewählten Modellen fehlt ein benötigtes Verhältnis, siehe FIGURE_DATA.json.'),
]

# Names and compact symbolic annotations carry no prose to localize. This list
# intentionally does not accept arbitrary English sentences after a model name.
NEUTRAL_PATTERNS = [
    r'^b\d+$',
    r'^(?:N|G|Native|Generic) (?:F|E|F=E) b\d+$',
    r'^(?:DeepX|H8|H10)/b\d+ · (?:Native|Generic)$',
    r'^(?:MobileNet V3|RegNetX-1.6GF|ResNet50|YOLO11l|YOLO26m|YOLO26s|YOLOv7) / (?:DeepX|H8|H10)\s+n=\d+/\d+(?:\s+=)?$',
    r'^(?:DeepX|H8|H10|DX|Hailo8|Hailo10H|Hailo-8|Hailo-10H|TensorRT|TRT)(?: Full)?$',
    r'^(?:DeepX|H8|H10), n=\d+$',
    r'^(?:DeepX|H8|H10)\s+\(\d+\)$',
    r'^Top1 \d+/\d+$',
    r'^n=\d+(?:/\d+)?$',
    r'^F=E$',
]


def translate_dynamic(text):
    """Return a German string for a declared dynamic label, otherwise None."""
    for pattern, replacement in DYNAMIC_TRANSLATIONS:
        if re.fullmatch(pattern, text):
            return re.sub(pattern, replacement, text)
    return None


def is_neutral(text):
    return any(re.fullmatch(pattern, text) for pattern in NEUTRAL_PATTERNS)
