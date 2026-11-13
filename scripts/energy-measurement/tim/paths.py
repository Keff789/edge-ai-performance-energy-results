"""Shared portable paths; all generated output is outside the publication tree."""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[3] / 'results/energy-measurement'
if 'ENERGY_OUTPUT_ROOT' not in os.environ:
    raise SystemExit('Use ../reproduce.py --output <separate-directory>.')
OUT = Path(os.environ['ENERGY_OUTPUT_ROOT']).resolve()
D = ROOT / 'data/tim'
G = (ROOT if os.environ.get('ENERGY_VERIFY_SHIPPED') else OUT) / 'tables/tim'
T = G
F = OUT / 'figures/tim'
Q = OUT / 'validation'
for p in (G, F, Q): p.mkdir(parents=True, exist_ok=True)
