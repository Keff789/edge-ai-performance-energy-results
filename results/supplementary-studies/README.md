# Supporting analyses

The current split-inference study combines deployment comparisons, runner-based selection and graph-based selection. Start with the [paper results](../../publications/mlsys/README.md) for the main findings.

| Analysis | Contents |
|---|---|
| [Runner-based cut selection](rq2-native-scope-20261027/README.md) | Generic and Native observations, paired rankings, shortlist budgets and inclusion sensitivity |
| [Graph-based cut selection](rq3-generic420-detector-corrected-20261027/README.md) | Candidate features, model-held-out fitting, task/device variants and budget comparisons |
| [Independent stage-cost composition](stage-cost-composition/README.md) | Measured stage capacities and their relation to pipeline throughput |

The current English and German tables and figures are regenerated together with:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Run from the repository root; see [setup instructions](../../scripts/README.md). Configuration-level measurement records and source references remain alongside each analysis. Older publication profiles, scheduling experiments and development diagnostics are listed in the [research archive](../../docs/archival_studies.md).
