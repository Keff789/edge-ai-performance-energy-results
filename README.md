# Edge AI performance and energy results

This repository contains measurements and reproducible analyses of neural-network inference on heterogeneous edge systems. The split-inference study covers seven vision models on Jetson Orin NX systems paired with Hailo-8, Hailo-10H, or DeepX DX-M1.

## Current split-inference study

The study connects three questions: when splitting improves a deployment, how well a universal runner selects cuts for specialized implementations, and how graph scores can narrow the search before hardware testing. **Generic** is the universal runner, **Native** the specialized implementation, and **Full** the unpartitioned model.

| Question | Evaluation | Current results |
|---|---|---|
| RQ1: When is splitting useful? | Throughput, energy per image and quality against Full execution | [Deployment comparisons](results/split-inference/tables/table3_fastest_deployments.md) |
| RQ2: Can Generic identify fast Native cuts? | 204 paired cuts; 187 satisfy the quality rule across 21 model–device groups | [Runner-based selection](results/supplementary-studies/rq2-native-scope-20261027/README.md) |
| RQ3: Can graph scores reduce the candidate set? | 420 planned Generic configurations; 359 measured and 331 quality-admissible across 21 groups | [Graph-based selection](results/supplementary-studies/rq3-generic420-detector-corrected-20261027/README.md) |

The fastest quality-admissible split exceeds the globally fastest Full for six of seven models. Selecting the Generic winner leaves **1.35% mean Native throughput loss**. In the broader graph-score evaluation, testing five cuts selected by boundary size leaves **6.61% mean Generic throughput loss**. The loss is relative to the best measured cut in each model–device group, with equal weight per group.

Start with the [paper results](publications/mlsys/README.md) or the [dissertation figures and tables](publications/dissertation/README.md). Both use the same current inputs. The [data index](results/ACTIVE_GENERIC420.json) identifies the analysis and artifact directories.

From the repository root, regenerate the current English and German outputs with:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

See [setup and reproduction](scripts/README.md) for dependencies. This is an offline analysis of the supplied measurements. It does not start hardware runs. Quality is assessed against the CPU-ONNX reference using the 5% relative-loss rule. Energy comparisons use throughput and energy from the same recorded deployment.

## Other research areas

| Area | Contents |
|---|---|
| [Energy measurement](results/energy-measurement/README.md) | Calibration, signal reconstruction, sampling and measurement comparisons |
| [Supplementary analyses](results/supplementary-studies/README.md) | Additional methods, sensitivity analyses and stage-cost measurements |
| [Software and measurement tools](software/README.md) | Evaluators, measurement tools and ONNX sources |
| [PARMA-DITAM](publications/parma-ditam/README.md) · [IEEE TIM](publications/tim/README.md) | Publication-specific results |

Earlier analyses and development experiments are indexed in the [research archive](docs/archival_studies.md). Their source records remain available without mixing them into the current result summaries. Large model files, datasets and raw archives are stored separately. See [rights and notices](RIGHTS_AND_NOTICES.md).
