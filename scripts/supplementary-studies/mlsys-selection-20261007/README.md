# Historical MLSys selection supplements

From the repository root, using Python 3.10+ with NumPy, pandas, SciPy and Matplotlib:

```bash
python3 -I -B scripts/supplementary-studies/mlsys-selection-20261007/reproduce.py --output /tmp/mlsys-selection-reproduced
```

The output must be fresh or empty and outside this repository. The tested local environment is `../local-preparation/energy-venv/bin/python` (NumPy 1.26.4, pandas 2.3.3, SciPy 1.13.1, Matplotlib 3.8.4). Ghostscript is optional; its absence selects native vector PDF with embedded TrueType fonts. SVG and PNG are always generated. The command needs no TeX installation, network, model or hardware.

The entry reuses the existing THESIS20 score/evaluation functions, then executes the ported MLSys `build_best_cases`, `update_ranking_reported`, `build_review_additions`, `derive_vendor_quality`, inventory and plot functions. Outputs contain `historical-methods/`, `analysis/` and `figures/`; all temporary font files also stay under the explicit output. Importing these modules does not run an analysis. Standalone generator functions accept explicit input/output paths; the documented entry enforces repository and fresh-output boundaries.

Plot projections are produced after the numerical stages. All Generic group metrics and all nine-combination repeat ranges are recomputed. Stored point rates are checked against their three-repeat medians; historical H8 Native rates retain their original six-decimal reporting precision (at most 0.0000005 FPS rounding), while repeat ranges use full-precision arrays. Energy E/N and own-window N/T are recalculated from the preserved repeats and checked against archived aggregates. The selection overlay updates nine YOLOv7 Native cases while retaining historical Generic observations, admission gates and frozen selector choices. Its missing current energy and numeric quality remain missing. No new ranker is fitted.

See the [study, gallery and interpretation](../../../results/supplementary-studies/mlsys-selection-20261007/README.md). These scripts are adapted from the supplied MLSys R10 manuscript analysis; the original THESIS20 functions and their license notices remain in their existing package. [Rights and notices](../../../RIGHTS_AND_NOTICES.md) apply to the supplementary records and figures.
