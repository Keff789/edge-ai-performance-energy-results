# Split selection on heterogeneous edge systems

This study evaluates seven vision models on three accelerator–GPU systems. It compares complete deployments, tests whether the universal Generic runner identifies fast cuts for specialized Native implementations, and evaluates graph scores on a broader set of Generic cuts. The [study overview](../../docs/current-study.md) explains the common design, candidate coverage and exclusions.

## Results

| Question | Evidence | Main finding |
|---|---|---|
| RQ1: When does splitting help? | [Full and split comparisons](../../results/split-inference/tables/table3_fastest_deployments.md), [quality](../../results/publication-builds/generic420-20261027/paper/publications/mlsys-r30/tables/r14_winner_quality.csv), [YOLOv7 case](../../results/publication-builds/generic420-20261027/paper/publications/mlsys-r30/figures/yolov7_h8_case_single_column.pdf) | The selected splits have higher measured median throughput than the globally fastest Full for all seven models. Three also use less energy per image. Six winners use Native and the YOLO11l winner uses Generic. |
| RQ2: Can Generic identify good Native splits? | [Runner-based selection](../../results/supplementary-studies/rq2-native-scope-20261027/README.md) | Selecting the Generic winner leaves 1.35% mean Native throughput loss: 3.12% for classifiers and 0.02% for detectors. |
| RQ3: How well do graph scores narrow the search? | [Graph-based selection](../../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/README.md) | Boundary size has the lowest mean loss at five tests. Weights fitted separately by task and accelerator perform best at one and three tests among the evaluated methods. |

RQ2 evaluates 187 quality-admissible pairs in 21 model–device groups. RQ3 evaluates 331 quality-admissible Generic configurations in the same 21 groups. A test budget is the number of cuts measured within a group. The fastest tested cut determines the shortlist result, and each group contributes equally to the mean. These results support using graph scores for an initial shortlist, Generic measurements to refine it, and Native measurements to confirm the deployment choice.

## Figures and tables

- [English paper figures and tables](../../results/publication-builds/generic420-20261027/paper/publications/mlsys-r30/)
- [German paper figures and tables](../../results/publication-builds/generic420-20261027/paper/de/mlsys-r30/)
- [English graph-score figures and tables](../../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/artifacts/en/)
- [German graph-score figures and tables](../../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/artifacts/de/)
- [Runner illustration and editable source](figure1/README.md)

The YOLOv7 case is available in [single-column](../../results/publication-builds/generic420-20261027/paper/publications/mlsys-r30/figures/yolov7_h8_case_single_column.pdf) and [wide](../../results/publication-builds/generic420-20261027/paper/publications/mlsys-r30/figures/yolov7_h8_case.pdf) layouts. Both use the same measured values. English and German assets share their numerical inputs.

The [staged selection figure and tables](../../results/supplementary-studies/staged-selection/artifacts/en/) show the practical graph–Generic–Native procedure. Each group first tests up to five or twelve cuts with Generic, then its two fastest candidates with Native. The resulting mean Native throughput is 96.20% or 99.65% of the best measured result. Exact winners are found in 17 or 19 of the 21 groups. The lowest retained throughput rises from 45.53% to 94.52%. Classifier means are 91.14% and 99.18%, while both budgets cover all three cuts in each paired detector group. Direct Native tests of the five-cut shortlists give the same result using 81 Native tests. The staged procedure instead uses 81 Generic and 42 Native tests, without an established total-time saving. The percentages describe achieved throughput, not the probability of success on a new model. The [analysis](../../results/supplementary-studies/staged-selection/README.md) defines the candidate counts, evaluation and subgroup results.

Additional [selection-failure tables](../../results/supplementary-studies/staged-selection/artifacts/en/tables/selection_failures_k5.tex) identify graph-preselection and Generic-ranking misses. A separate [workflow figure](../../results/supplementary-studies/staged-selection/artifacts/en/figures/staged_selection_flow_review.pdf) distinguishes a conceptual prospective search from the retrospective replay evaluated in this study.

## Additional review tables

The [compact deployment table](../../results/supplementary-studies/mlsys-review-tables-20261030/artifacts/en/tables/best_cases_quality_table.md) combines the global throughput winners with energy change and the direct quality difference in percentage points. [German presentation exports](../../results/supplementary-studies/mlsys-review-tables-20261030/artifacts/de/tables/) retain identical CSV/JSON values. Existing tables and the underlying selection remain unchanged. Full refers to single-backend full-model execution.

The additional export is included in `scripts/reproduce_current.py`. It can also be regenerated independently from the current full-precision winner export:

```sh
python3 scripts/split-inference/render_review_tables.py \
  --output local-output/review-tables --languages en de
```

The [retrospective Native energy-selection analysis](../../results/supplementary-studies/native-energy-selection-20261030/README.md) selects minimum-energy cuts subject to 95% or 99% of the best measured Native throughput in each combination. It uses all 187 admissible Native cuts in 21 combinations, preserves the Full comparisons, and makes no limited-budget energy-search claim.

## Reproduction and methods

Run from the repository root:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

[Setup instructions](../../scripts/README.md) describe the Python dependencies. The command rebuilds the current runner-selection analysis, graph-score analysis and publication outputs from the supplied inputs. The directory name `mlsys-r30` is an internal rendering profile used by the current build.

The [measurement methods](../../results/split-inference/METHODS.md) describe throughput, quality and energy. The selection-analysis pages above specify their candidate sets and fitting procedure. Configuration-level source records remain with the analysis inputs. Earlier publication profiles and experiments are indexed in the [research archive](../../docs/archival_studies.md).
