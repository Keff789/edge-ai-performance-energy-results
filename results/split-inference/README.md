# Split inference: performance, energy and quality

451 observed deployments cover 7 models, with 204 Native splits, 205 Generic splits and 42 host-specific Full configurations. The current inputs admit 6/6 declared measurement packages. Measured coverage is 451/451 FPS, 450/451 energy and 451/451 numerical quality observations. Missing metrics remain unavailable.

[Figures](figures/README.md) · [Tables](tables/README.md) · [Complete dataset](data/PAPER_DATASET.csv) · [Findings](FINDINGS.md) · [Methods](METHODS.md)

The fastest-deployment tables select one split across Native and Generic runners and all measured setups, with the runner and exact source UID retained. Global and same-host Full references use the same selected split. Energy belongs to its exact performance observation; replacing FPS clears incompatible prior energy. The [source table](data/METRIC_SOURCES.csv), [measurement generations](data/MEASUREMENT_GENERATIONS.csv) and [replacement history](data/current_observation_history.json) retain the old and current observations. Full measurements and the literal b066 records are unchanged.

Unchanged Generic FPS/energy generations in this broad dataset remain separate from the current Generic FPS used by [RQ2](../supplementary-studies/rq2-native-scope-20261027/README.md). Quality uses Top-1 accuracy for classifiers and COCO AP@[.50:.05:.95] for detectors; current Native quality replacements evaluate their actual timed completion records. Source-specific runtime, quality and comparison authority remain visible in the data.

Reproduce with the [offline instructions](../../scripts/split-inference/README.md). The generator performs no hardware measurement, compilation or dataset evaluation.
