#!/usr/bin/env python3
"""Compare generated scientific exports directly, without an output hash registry."""
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--expected', type=Path, required=True)
p.add_argument('--actual', type=Path, required=True)
a = p.parse_args()

def exports(root, include_figures):
    files = list((root/'data').glob('*.json')) + list((root/'data').glob('*.csv'))
    files += [f for f in (root/'tables').iterdir() if f.is_file()]
    if include_figures:
        files += [f for f in (root/'figures').iterdir() if f.is_file() and f.suffix in {'.png', '.pdf', '.svg', '.json'}]
        files += list((root/'figures').rglob('*.md'))
        files += [root/n for n in ['CAPTIONS.md', 'METHODS.md', 'METHODS_PARAGRAPH.tex', 'FINDINGS.md']]
    profile=root/'publications/mlsys-r22'
    assert profile.is_dir(), ('Missing registered publication profile',str(profile))
    files += [f for f in profile.rglob('*') if f.is_file()
              and (include_figures or f.suffix not in {'.pdf','.svg','.png'})]
    return {str(f.relative_to(root)): f.read_bytes() for f in files}

full = (a.actual/'figures').is_dir()
expected, actual = exports(a.expected, full), exports(a.actual, full)
assert expected == actual, {
    'missing': sorted(expected.keys()-actual.keys()),
    'unexpected': sorted(actual.keys()-expected.keys()),
    'different': sorted(n for n in expected.keys() & actual.keys() if expected[n] != actual[n]),
}
print(json.dumps({'status': 'PASS', 'matching_scientific_files': len(expected),
                  'figures_included': full}, sort_keys=True))
