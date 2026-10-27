# Split selection: current results

Seven vision models are evaluated on Jetson Orin NX systems paired with Hailo-8, Hailo-10H or DeepX DX-M1. The study examines deployment benefits, selection with Generic, and graph-based shortlists.

| Question | Data and results |
|---|---|
| RQ1: When does splitting improve deployment? | [Split and Full comparisons](../../split-inference/tables/fastest_split_baselines.md), including throughput, quality and energy. |
| RQ2: Can Generic select a fast Native cut? | [Paired comparison](../rq2-native-scope-20261027/README.md) on 204 cuts, with 187 passing the quality rule. |
| RQ3: How well do graph scores narrow the search? | [Graph-score comparison](../rq3-generic420-detector-corrected-20261027/README.md) on 331 quality-admissible cuts. |

## Generic recommendations

Each model–device group contributes equally. Loss is measured against its fastest Native cut.

| Models | Admitted pairs | Groups | Mean Native loss (%) |
|---|---:|---:|---:|
| All models | 187 | 21 | 1.3468 |
| Classifiers | 151 | 9 | 3.1189 |
| Detectors | 36 | 12 | 0.0176 |

The [staged selection analysis](../staged-selection/README.md) combines graph-based preselection, Generic measurements, and one or two final Native tests. Its budget curves and tables use the same paired candidates.


## Coverage and interpretation

The paired set contains 204 cuts. The quality rule excludes 17. The broader graph-score set selects 20 cuts per model and accelerator, including multi-tensor boundaries. Of 420 planned configurations, 359 have throughput measurements, 61 cannot be executed, and 28 measured cuts exceed the quality limit. The [coverage table](closure_matrix.csv) gives the counts for each group.

Both selection analyses apply the 5% relative quality-loss rule. RQ2 evaluates Native throughput and RQ3 Generic throughput. The [measurement notes](../rq2-native-scope-20261027/DATA_NOTES.md) record source details that affect interpretation. The paired b009 observation uses the new normally admitted Native observation and its current input binding; the historical metadata review remains archived. Energy comparisons use measurements of the same runtime configuration.

## Figures, tables and reproduction

[Paper figures and tables](../../publication-builds/generic420-20261027/paper/README.md) · [German dissertation collection](../../publication-builds/generic420-20261027/dissertation-de/README.md) · [English dissertation collection](../../publication-builds/generic420-20261027/dissertation-en/README.md)

From the repository root:

```bash
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

The command regenerates the analyses and English/German outputs from the published inputs. It performs no hardware measurements. Requirements are listed in [the analysis instructions](../../../scripts/README.md).

The machine-readable input and output manifests retain source identities. Earlier profiles and diagnostic experiments are indexed in [the archive](../../../docs/archival_studies.md).
