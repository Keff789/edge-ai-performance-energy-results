# Edge AI: Performance and energy measurements

This repository contains measured results and offline analyses of neural-network inference on heterogeneous edge systems. The split-inference experiments cover **seven vision models** on Jetson Orin NX hosts with Hailo-8, Hailo-10H or DeepX DX-M1 accelerators.

The study distinguishes **Full** (unpartitioned execution), **Generic** (a common split runner) and **Native** (device-specific split implementations).

## Main results

| Question | Evidence | Result in the measured candidate sets |
|---|---|---|
| RQ1 — When is splitting useful? | [Deployment comparisons](results/split-inference/tables/table3_fastest_deployments.md) | The fastest quality-admissible split outperforms the fastest tested Full configuration in throughput for all seven models; three also use less energy per image. |
| RQ2 — Can Generic select good Native cuts? | [Paired runner analysis](results/supplementary-studies/rq2-native-scope-20261027/README.md) | 204 paired cuts, of which 187 satisfy the quality rule; choosing by Generic throughput leaves 1.35% mean Native throughput loss across 21 groups. |
| RQ3 — Can graph features shorten the search? | [Graph-selection analysis](results/supplementary-studies/rq3-generic420-detector-corrected-20261027/README.md) | 420 planned configurations, 359 measured and 331 quality-admissible; testing five cuts ranked by boundary size leaves 6.61% mean Generic throughput loss. |

These figures describe **retrospective comparisons of recorded candidates**, not a prediction for unseen models or hardware. The quality criterion is a maximum 5% relative loss against the CPU-ONNX reference. The [study overview](docs/current-study.md) defines the candidate sets, exclusions and evaluation procedure.

## Find the data

| Area | Entry point |
|---|---|
| Split inference, measurement methods and tables | [Split-inference results](results/split-inference/README.md) |
| Energy measurement and calibration | [Energy results](results/energy-measurement/README.md) |
| Runner selection, graph selection and additional analyses | [Supporting studies](results/supplementary-studies/README.md) |
| MLSys and dissertation tables and figures | [MLSys](publications/mlsys/README.md) · [Dissertation](publications/dissertation/README.md) |
| Software and measurement tools | [Software index](software/README.md) |
| Current outputs versus frozen historical records | [Results directory guide](results/README.md) · [Research archive](docs/archival_studies.md) |

For a German-language guide to the dissertation evidence, see [Wegweiser Dissertation](WEGWEISER_DISSERTATION.md).

## Reproduce the current analyses

From the repository root, after installing the dependencies described in [scripts/README.md](scripts/README.md):

```bash
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

This regenerates analyses and publication outputs **from the measurements already supplied**; it does not collect new hardware measurements. The [active-results manifest](results/ACTIVE_GENERIC420.json) identifies the input snapshots and output collections. Earlier study versions remain available, but must not be combined as independent experimental cohorts.

## Provenance and reuse

The dissertation's [preserved appendix](results/supplementary-studies/dissertation-appendix-20261111/README.md) documents the use of AI tools in software development, alongside methods and verification notes. See [research transparency](docs/research_transparency.md), [rights and notices](RIGHTS_AND_NOTICES.md) and the [cleanup notes](CLEANUP_NOTES.md). This repository does not have a blanket license for all data, code and figures.
