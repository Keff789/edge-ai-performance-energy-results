# RQ3: Selecting cuts with graph scores

Graph scores rank cuts before hardware measurements. We measure the highest Generic throughput found after testing the first one, three or five recommendations, relative to the best measured cut in each group.

The analysis includes 331 quality-admissible cuts in 21 model–accelerator groups. Of 420 planned configurations, 61 could not be executed and 28 measured cuts exceed the 5% relative quality-loss limit. Per-group coverage is recorded in `inputs/coverage.csv`.

Mean held-out Generic throughput loss (%); every model–accelerator group has equal weight:

| Ranking | 1 cut | 3 cuts | 5 cuts | Mean at 1, 3, 5 |
| --- | ---: | ---: | ---: | ---: |
| Boundary size | 22.224463 | 15.828006 | 6.610356 | 14.887608 |
| Standard (1, 3, 0.2) | 34.771105 | 32.265247 | 21.708820 | 29.581724 |
| Shared fitted weights | 22.481569 | 19.346566 | 10.519977 | 17.449371 |
| Fit by task | 25.463220 | 17.773157 | 10.956996 | 18.064458 |
| Fit by accelerator | 21.112468 | 15.292203 | 9.888455 | 15.431042 |
| Fit by task and accelerator | 17.741997 | 13.338409 | 9.800775 | 13.627060 |

Learned rankings hold out the complete model on every accelerator. One training fit minimizes mean loss at budgets 1, 3 and 5, and supplies the same ranking at all budgets. The primary simplex grid has step 0.0025 and includes the exact standard and pure boundary-size weights. Full-data weights are descriptive training fits, separate from held-out performance.

Reproduce the complete study and its English and German outputs from the repository root:

```bash
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

To rebuild only the graph-score analysis:

```bash
python -B scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs "results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs" \
  --output /tmp/generic420-reproduced --languages en de
```

Verify a completed study with `scripts/supplementary-studies/rq3-generic420/verify.py --study STUDY`. Dependencies and the detailed scoring, holdout and sensitivity protocol are in `scripts/supplementary-studies/rq3-generic420/README.md`. No private snapshot is needed for this rebuild.

[Recorded compiler examples](inputs/technical_exclusion_examples.README.md) explain two excluded boundaries. These are compiler-output examples, not additional measurements.
