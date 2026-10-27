# Generic420 graph-score analysis (RQ3)

This additive study evaluates graph rankings against **measured Generic throughput**.
It does not replace the paired Generic/Native dataset or recompute Native results.
The active corrected 27 October snapshot has 420 frozen configurations,
359 accepted FPS medians, and 331 measured and quality-eligible cuts in
21 nonempty model–accelerator groups. All 21 groups have resolved FPS and
quality decisions. The remaining 28 measured cuts have quality failures.
Fifteen corrected historical quality observations retain their original FPS;
YOLOv7 on Hailo-8, cut b009, uses its genuinely new three-repeat FPS observation
and current quality admission. Its earlier observation remains in ledger history.
A further 61 configurations have technical exclusions (37 compile failures and
24 unsupported configurations); no supported FPS measurements remain pending.
This is the resolved conditional pool; technical exclusions are not measured
quality outcomes. These categories remain separate in `inputs/coverage.csv`.
`inputs/feature_metadata.json` records the complete current quality coverage.
The earlier 315-cut preliminary study remains preserved separately under
`results/supplementary-studies/rq3-generic420-20261027`.

## Reproduce

From the repository root, in Python 3.12 with this directory's pinned requirements:

```bash
python -m pip install -r scripts/supplementary-studies/rq3-generic420/requirements.txt
python scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs \
  --output /tmp/generic420-reproduced
```

By default this builds the main analysis, four sensitivity analyses, and all
figures and tables in English and German. It uses recorded metadata and CSVs only.
There is no compilation, benchmark execution, remote access, or change to a
running measurement job. `--skip-sensitivity` builds the main analysis alone.
`--numeric-only` skips figure rendering while retaining tables and plot data.
Always use a fresh output directory.

For a later frozen SM2 export, extract it to a new directory first. Use the
export's top-level directory containing `EXPORT_MANIFEST.json`:

```bash
python scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --source /path/to/extracted-sm2-export \
  --output /path/to/new-generic420-study
```

The importer verifies every export-manifest hash, the ledger selected by
`status420/CURRENT.json`, all frozen model and boundary identities, and the median
of all three accepted FPS repeats. It uses the published graph feature CSV and
normalization universe from `rq2-weighted-20261020/features`. Optional
`--published-features` and `--published-normalization` arguments select those
files explicitly. The imported candidate pool must still be the same frozen
420-cell design; the numbers measured and eligible are derived dynamically.
A different model set or selection design requires a reviewed protocol change.
The importer rejects incomplete exports instead of filling in missing features.
The audited published feature bytes are pinned (allowing the delivery package’s
extra terminal newline), and `inputs/published_feature_provenance.json` retains
the audit and exact hashes of the consumed sources. Public tables and inputs use
relative source names and hashes; the private snapshot is not needed for a
complete rebuild using `--inputs`.

For rendering an already computed study without refitting:

```bash
python scripts/supplementary-studies/rq3-generic420/render_artifacts.py \
  --study results/supplementary-studies/rq3-generic420-detector-corrected-20261027 \
  --out /tmp/generic420-artifacts --languages en de
```

The existing publication entrypoints accept an optional `--generic420-study`:

```bash
python scripts/split-inference/reproduce.py --output /tmp/paper-build \
  --publication mlsys-r30 --languages en de \
  --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027
python scripts/dissertation/reproduce.py --output /tmp/diss-build \
  --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027
```

These calls keep their original behavior and additionally create `rq3-generic420/`
inside the chosen output. They do not silently promote a preliminary study to the
paper's main dataset. The result directory and its manifest identify the snapshot.

## What “1, 3, and 5 tests” means

For each model–accelerator group, a ranking selects up to **1, 3, or 5 cuts**.
We use the fastest measured Generic result among those cuts. The loss is its
throughput reduction relative to the best measured, quality-eligible Generic cut
in the same group. If fewer cuts are available, all are selected. Unknown
measurements are excluded rather than scored as failures or assigned zero FPS.
Every eligible group has equal weight.

For a learned ranking, one whole model is held out **on every accelerator**.
The remaining models train the weights. The held-out model supplies the test
results. The number of held-out models does not change with the measurement
budget. One trained ranking is used at all budgets; it is not refitted separately
for each point in the main figure.

## Score and fitting contract

`score = w_C C + w_I I + w_T T`, with nonnegative weights summing to one;
smaller scores are preferred.

* `C`: min–max normalized `log10(1 + cut_bytes)` across the full original
  model-specific workflow candidate universe, not only its measured cuts.
* `I`: `abs(F_left - F_right) / (F_left + F_right)` from the published
  `analytic-operation-proxy-r29-extended-v1` features. Workflow FLOPs
  are retained separately for audit and are not substituted for this feature.
* `T`: min–max normalized `max(n_cut_tensors - 1, 0)` across that same universe.
  Graph tensor count is distinct from exported `part2_input_count`.

Standard weights are `(1, 3, 0.2)`, normalized to sum to one. The primary grid
uses increments of 0.0025 (80,602 combinations including the exact standard).
Pure boundary size `(1,0,0)` is explicitly included. Training minimizes the mean
loss across budgets 1, 3 and 5 and eligible training groups. Score ties use scores
rounded to 12 decimals, then the stable configuration identifier. Equal training
optima are resolved using training-only score-line margins, distance to the
standard weights, then lexicographic weights. `fit_config.json` records this.
The search establishes an optimum on the declared grid, not a proof over all
continuous weights.

Four scopes are evaluated: shared (`global`), separate by classification/detection
(`task`), by accelerator (`device`), and by both (`task_device`). Holding out a
classifier leaves only two other classifier models for a task-specific fit.
`fold_weights.csv` contains the actual weights used for held-out evaluation.
`full_data_weights.csv` contains descriptive fits using all available data; these
weights and their training loss are never presented as held-out performance.

A fitted score may lose to boundary size at five cuts while improving the
training objective averaged over 1, 3, and 5. The training guarantee also does not
apply to the unseen test model. `verify.py` checks that every primary fitted
training objective is at least as good as the included pure-bytes candidate.
The separate `budget5_fit` sensitivity changes the training objective to five
cuts alone; it is not substituted for the prespecified main comparison.

## Files and figures

`inputs/` contains the 420-cell canonical data, full graph universe, coverage,
and portable hash provenance. Device-specific raw bundles remain in the archived
SM2 export; they are not duplicated in this public study. Host paths do not appear
in the public tables. Historical Native data are unchanged.

`fit_results/primary/` contains per-fold weights, per-group results for all budgets,
summary tables, and fitting metadata. Main plots use budgets 1, 3, and 5.
Optional sensitivity directories contain coarse-grid, five-only objective,
joint YOLO26-family holdout, and boundary-size tie-break checks. In this snapshot,
the grid check is stable at the primary budgets; off-budget ranks can differ.

`artifacts/en/` and `artifacts/de/` contain matching tables (`.tex` and `.csv`) and
figures (`.pdf`, `.svg`, `.png`). Both languages use the central
`publication_mlsys_figures.py` font and color palette. Figure titles are omitted;
panel identifiers and axes remain, with explanations in generated LaTeX captions.
The main figure has three methods and separate classifier/detector panels. A
single-column variant is also generated. The scope comparison is supplemental.
All numbers come from the same canonical CSVs. `FIGURE_DATA.json` records sources
and coordinates. `figure_includes.tex` gives adaptable LaTeX examples, not an
instruction to include all variants in the same paper.

Tables are bare `tabular` fragments requiring `booktabs`. Use the small summary
in the paper; detailed coverage and fold tables may need landscape or multiple
pages in a supplement. File names ending in `descriptive` are training summaries.
Sensitivity filenames identify the changed training/test protocol.

## Validation

```bash
python scripts/supplementary-studies/rq3-generic420/verify.py \
  --study /path/to/generated-study
```

Checks cover the coverage partition, three-repeat FPS medians, full-universe
normalization, published operation-proxy consistency, all four fitting scopes
and every sensitivity analysis. They bind reported rankings to their recorded
fold weights, enforce whole-model holdout and pure-bytes training-objective
dominance, recalculate every loss and summary, and verify matching EN/DE numeric
tables and file hashes. Descriptive full-data weights remain separate from
held-out results. This validates the analysis and preserves any unresolved
decisions as exclusions when importing a different snapshot. Regression checks reject corrupted fold weights, altered
sensitivity metrics, and a test model leaked into training on another device:

```bash
python -B scripts/supplementary-studies/rq3-generic420/test_verify.py
```
