# Split inference: performance, energy and quality

451 observed deployments cover 7 models, with 204 Native splits, 205 Generic splits and 42 host-specific Full configurations. Measured coverage is 451/451 FPS, 450/451 energy and 451/451 numerical quality observations. Missing metrics remain unavailable.

This deployment comparison is RQ1 of the [split-selection study](../../docs/current-study.md). The same study evaluates Generic recommendations against Native and graph rankings against Generic.

[Figures](figures/README.md) · [Tables](tables/README.md) · [Complete dataset](data/PAPER_DATASET.csv) · [Findings](FINDINGS.md) · [Methods](METHODS.md)

The fastest-deployment tables select one split across Native and Generic runners and all measured setups, with the runner and exact source UID retained. Global and same-host Full references use the same selected split. Energy and quality belong to the same recorded runtime configuration as its throughput. Quality uses Top-1 accuracy for classifiers and COCO AP@[.50:.05:.95] for detectors. The paper applies a 5% relative quality-loss limit against the CPU-ONNX reference.

The [paired selection analysis](../supplementary-studies/rq2-native-scope-20261027/README.md) uses its bound Generic observations for ranking. Energy is not transferred from a different observation when runtime measurements differ. The [metric sources](data/METRIC_SOURCES.csv) and [configuration history](data/current_observation_history.json) retain these mappings.

Reproduce with the [offline instructions](../../scripts/split-inference/README.md). The generator performs no hardware measurement, compilation or dataset evaluation.
