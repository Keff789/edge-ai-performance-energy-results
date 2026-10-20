# MLSys R30 paper assets

Generated with `python -I -B scripts/split-inference/reproduce.py --publication mlsys-r30 --output <empty-directory> --verify`.
Add `--numeric-only` to omit image rendering. The default registered R22 profile remains unchanged.

The core measurement figures use the common paper style and their frozen R22 numerical data.
The author boundary illustration is regenerated from its maintained vector source.
Both wide and single-column YOLOv7 case figures are included, with identical numbers.
The weighted figure and tables use all 187 quality-eligible measured pairs in 21 groups.
Optimized weights are fitted on all seven models; held-out results exclude one entire model at a time.
The new main weighted figure has no Random curve. Existing historical supplementary evidence keeps its original scope.

Inputs, operation rules, fold memberships, exact results and sensitivity checks are in
`results/supplementary-studies/rq2-weighted-20261020`.
`ASSET_MANIFEST.json` maps assets to generators. `PROVENANCE.json` records hashes.
