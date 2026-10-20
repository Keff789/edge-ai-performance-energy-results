# Complete RQ2 rankings and search budgets

The offline entry point extends the existing Top-1/3/5 analysis to every measured
cut and every integer Native-test budget. It reproduces complete ranks,
Spearman correlations, retained-throughput loss, exact and near-optimal hit
curves, and minimum budgets for specified success coverage. The
[results](../../../results/supplementary-studies/rq2-all-cuts-20261020/README.md)
explain the two separate measurement campaigns and list the output files.

From the repository root:

```bash
python3 -m venv ../rq2-analysis-venv
../rq2-analysis-venv/bin/python -m pip install -r scripts/supplementary-studies/rq2-all-cuts-20261020/requirements.txt
../rq2-analysis-venv/bin/python -I -B scripts/supplementary-studies/rq2-all-cuts-20261020/reproduce.py \
  --output ../rq2-all-cuts-reproduced --verify
```

Use an empty output directory. The pinned dependency versions and Python
3.12.14 were used for the published export. `--numeric-only` skips Matplotlib
and figure rendering but still requires NumPy, pandas and SciPy. The existing
R22 environment has a different dependency set and is not modified by this
recipe.

`reproduce.py` binds the four numerical engines to existing canonical repository
inputs, records their hashes, and stages temporary working copies. The
engines retain the audited calculations and tie rules. No model, archive,
sensor, accelerator, network connection or new fit is used. Only derived files
are copied into the requested output. Source evidence and the frozen R22
publication profile remain unchanged.

The graph-rule success engine consumes the just-regenerated complete graph
scores rather than an unexplained copied score table. Current success and loss
engines independently read the same source audit and frozen predictions.
Exact-optimum success is checked against every corresponding loss-curve
winner count. `--verify` then compares scientific CSV and JSON exports with the
published reference files. Figure bytes are not a verification target.

`analyze_current.py`, `analyze_graph_rules.py`, `success_current.py`, and
`success_graph_rules.py` are internal engines invoked by `reproduce.py`.
`documentation.py` generates the results index from the derived budget tables.
`paper_assets.py` renders the English publication figures and generates the
budget table. `ASSET_MANIFEST.json` binds each asset to its numerical sources.
Full-mode verification also compares the exact plotted coordinates in
`figures/RQ2_FIGURE_DATA.json`; numerical mode includes the CSV/JSON/TeX budget
table without loading Matplotlib.
