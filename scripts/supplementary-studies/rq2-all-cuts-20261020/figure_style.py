"""Shared RQ2 figure style from the central MLSys publication renderer.

Font sizes, device palette and device markers reuse the published profile's
settings without modifying that profile or its frozen output files.
"""
import importlib.util
from pathlib import Path

_path=Path(__file__).resolve().parents[3]/'scripts/split-inference/publication_mlsys_figures.py'
_spec=importlib.util.spec_from_file_location('rq2_mlsys_publication_style',_path)
_profile=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_profile)
MODEL_LABELS=dict(_profile.MODEL_LABELS)
SETUPS=list(_profile.SETUPS)
COLORS=dict(_profile.COLORS)
PALETTE=dict(_profile.PAPER_PALETTE)
MARKERS=dict(_profile.MARKERS)
STYLE=dict(_profile.PAPER_STYLE,**{'svg.hashsalt':'rq2-all-cuts-20261020'})


def apply(plt):
    plt.rcParams.update(STYLE)


def grid(ax, axis='y'):
    ax.grid(axis=axis,color='#dddddd',linewidth=.45,zorder=0)
