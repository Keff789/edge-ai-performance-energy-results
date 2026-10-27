# Selecting Native splits with Generic

The comparison covers 204 measured cuts on seven models and three accelerator setups. The 5% relative quality-loss rule admits 187 paired cuts in 21 model–device groups. 17 cuts exceed this quality limit.

For each group, Generic recommends its fastest measured cut. We evaluate that recommendation by its Native throughput, relative to the fastest measured Native cut in the same group. Each group contributes equally.

| Models | Paired cuts | Groups | Mean Native loss (%) |
|---|---:|---:|---:|
| All models | 187 | 21 | 1.3468 |
| Classifiers | 151 | 9 | 3.1189 |
| Detectors | 36 | 12 | 0.0176 |

[Shortlist results](analysis/key_budget_results.csv) show how the loss changes when more than one recommendation can be tested. [Group results](data/quality_selection_groups.csv) identify the selected cuts. The [paired observations](data/current_pairs.csv) contain the measurement values and quality decisions. [Runner comparison](data/runner_graph_comparison.csv) evaluates the same graph shortlists with Generic and Native.

RQ3 uses a broader candidate set to evaluate graph rankings against Generic throughput. It is available from the [current study entry](../generic420-closeout-20261027/README.md). The two analyses answer different selection questions within the same study.

## Reproduce

```bash
python3 scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py --output local-output/rq2 --verify
```

Run from the repository root. Add `--numeric-only` to omit rendering. [Measurement notes](DATA_NOTES.md) explain the few retained source differences. The input manifest and detailed source records support reproduction without making the measurement chronology part of the result.

<!-- assemble_inputs.py reconstructs historical acquisition sources. It does not apply the published pairing review. Normal reproduction reads the current observations.json and validates that review separately. -->
