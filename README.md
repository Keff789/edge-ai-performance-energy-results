# Edge AI performance and energy results

Measured split-inference performance, energy and quality, together with energy-measurement methods and controls. The current main dataset includes 75 DeepX Native A4 replacements; the other 375 direct observations and all 450 original dataset-quality selections are retained. The collection includes complete model views, supplementary analyses and negative results.

| Explore | Contents |
|---|---|
| [Split inference](results/split-inference/README.md) | 450 deployments, including 42 Full baselines; throughput, host-inclusive energy, dataset quality, repeats and sensitivity comparisons |
| [Energy measurement](results/energy-measurement/README.md) | Reconstruction, spectra, historical FP16 rate curves, measurement comparisons, calibration and protocol controls |
| [Supplementary studies](results/supplementary-studies/README.md) | Independent stage costs, historical THESIS20/MLSys selection, dissertation ranking and reported tables, YOLOv7 completion, native endpoints and Hailo-8 diagnosis, each with its own cohort |
| [Analysis scripts](scripts/README.md) | Offline reanalysis and plotting from the supplied inputs |
| [Software and measurement tools](software/README.md) | Offline evaluators, measurement tools and the selected ONNX source |

Publication entry points: [PARMA-DITAM](publications/parma-ditam/README.md) · [IEEE TIM](publications/tim/README.md) · [MLSys](publications/mlsys/README.md) · [Dissertation](publications/dissertation/README.md).

The split analysis now compares the [global fastest observed Full and split per model](results/split-inference/tables/table3_fastest_deployments.md), with throughput and energy from those exact configurations. A [companion table](results/split-inference/tables/fastest_split_baselines.md) compares the same selected split with both its same-host and global Full references. [Baseline-effect](results/split-inference/figures/fastest_split_baseline_comparison.pdf) and [throughput–energy](results/split-inference/figures/fastest_deployment_tradeoff.pdf) figures share those selections. The earlier [Top-2 Native splits by relative same-host gain](results/split-inference/tables/table3_top2_native.md) remains a separate supplementary selection method.

The split results retain differences in dataset quality and timed work. Their ratios describe measured deployments; they do not isolate the causal effect of graph splitting at equal work. Energy reconstructions retain their sampling and reference limitations. See each result area's methods before comparing values.

Offline reproduction processes existing measurements or exported numerical summaries. It does not repeat hardware acquisition, model compilation or dataset evaluation. Large models, engines, datasets and raw archives remain outside this repository.

The source collection is [onnx-splitpoint-results](https://github.com/Keff789/onnx-splitpoint-results/tree/380dfa09aa6740acdc71908cb6e5dd5c8fc115ad). Existing identifiers and measurement metadata are retained. See [rights and notices](RIGHTS_AND_NOTICES.md).
