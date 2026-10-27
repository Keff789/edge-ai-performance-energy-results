# Split selection: study overview

The study asks how to find a useful accelerator–GPU split without implementing every candidate with a specialized runner. Seven vision models run on three Jetson Orin NX systems paired with Hailo-8, Hailo-10H or DeepX DX-M1. **Generic** is the common runner, **Native** is the specialized runner for each accelerator–GPU combination, and **Full** executes the unpartitioned model through one backend.

## Candidate sets and coverage

The graph-score evaluation starts with twenty candidate cuts per model and accelerator: **420 configurations** across 21 model–device groups. Candidates cover different graph windows and include boundaries with several tensors. The paired runner comparison uses **204 cuts** supported by both Generic and Native. There are also **42 Full configurations**, one accelerator Full and one TensorRT Full on each host for every model.

| Evaluation | Planned or paired cuts | Measured with FPS and quality | Pass the quality rule | Quality exclusions | Technical exclusions | Pending |
|---|---:|---:|---:|---:|---:|---:|
| Graph selection using Generic | 420 | 359 | 331 | 28 | 61 | 0 |
| Generic selection using Native | 204 | 204 | 187 | 17 | 0 | 0 |

These sets overlap and must not be added as independent measurements. Of the 204 paired cuts, 192 belong to the 420-candidate set and twelve are additional paired cuts. Native currently accepts one input to the GPU suffix, so its paired detector groups contain three cuts each. Generic also supports multi-tensor boundaries. Its quality-admissible groups contain 7–20 cuts, which provides the wider candidate set for graph-score evaluation.

The [Generic coverage table](../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs/coverage.csv) and [paired summary](../results/supplementary-studies/rq2-native-scope-20261027/summary.json) provide the counts by model and accelerator. All planned cases are resolved. An exclusion is a recorded outcome, not a pending measurement.

## Why some cuts are excluded

Exporting an ONNX prefix does not ensure that an accelerator compiler can build it. Cutting a graph can expose intermediate tensors as new outputs, remove downstream shape information, or leave operators that the backend cannot represent. In this candidate set, 37 configurations fail compilation and 24 are classified as unsupported.

Two recorded Hailo examples illustrate the distinction. For YOLO11l/H10 b031, the parser reports an ambiguous output shape at `/model.2/Split` because a successor name is missing. For YOLO26m/H10 b416, compilation reports unsupported detector-selection operations, including `TopK` and `GatherElements`. These are failures for the particular exported subgraphs and compiler version. Multiple boundary tensors alone do not make a cut invalid. The [compiler evidence excerpts](../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs/technical_exclusion_examples.json) retain the exact messages and source references.

The quality rule excludes deployments whose task score falls more than 5% relative to the CPU-ONNX reference. Classification uses Top1 accuracy and detection uses COCO AP50:95. Accelerator compilation can quantize weights and activations to lower precision. Rounding, clipping and the calibration ranges can change the outputs. Compiling a prefix separately can also change its quantization parameters, while the GPU suffix uses a different numerical path. The resulting task quality may therefore be lower or higher than Full execution. The study measures the complete compiled deployment; it does not attribute each quality difference to one compiler transformation or training step.

## Three questions within one evaluation

**RQ1: Is splitting useful?** Compare the fastest split with the fastest Full using the same configuration's quality, throughput and energy. If hardware is fixed, compare with Full on that host. If hardware can still be chosen, Full on another tested system is also an option. A split is faster for all seven models, and three selected splits also use less energy per image. Six winners use Native. YOLO11l uses Generic on DeepX at b511, with 9.85% more throughput and 3.48% more energy per image than the fastest Full. See the [deployment table](../results/split-inference/tables/table3_fastest_deployments.md).

**RQ2: Can Generic identify fast Native cuts?** Rank the paired cuts by Generic throughput and evaluate the recommendation using Native. Choosing the first recommendation leaves 1.35% mean Native throughput loss. Testing the first two finds a Native winner in 20 of 21 groups; four suffice in all groups. See the [runner comparison](../results/supplementary-studies/rq2-native-scope-20261027/README.md).

**RQ3: Can graph scores narrow the search?** Rank the 331 admitted Generic cuts before hardware testing. Five cuts selected by boundary size retain 93.39% of the best measured Generic throughput on average. Learned weights are tested with the entire test model excluded from training on every device. The [graph-score analysis](../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/README.md) compares shared and task/device-specific fits.

The [staged analysis](../results/supplementary-studies/staged-selection/README.md) then replays the complete selection sequence on the paired data: graph preselection, Generic testing, and Native testing of the two fastest Generic candidates. At most five Generic tests retain 96.20% of the best measured Native throughput on average, with 17 exact winners out of 21 groups. Twelve Generic tests retain 99.65%, with 19 exact winners. Mean retained throughput and exact winner frequency are different quantities. Budgets count throughput tests on admitted candidates and do not measure total search time, compilation effort or quality-evaluation cost.

## Outputs and reproduction

The [paper collection](../publications/mlsys/README.md) and [dissertation collection](../publications/dissertation/README.md) use the same numerical inputs. Figures and tables are generated in English and German with a common style. From the repository root:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

The command performs offline analysis, without starting hardware measurements. [Setup instructions](../scripts/README.md) list the dependencies. The [data index](../results/ACTIVE_GENERIC420.json) identifies the current inputs and outputs. Configuration-level metric sources remain available for reproduction. Energy coverage differs from FPS/quality coverage, and energy is never borrowed from another runtime configuration. Earlier analyses and the documented historical raw-data archive gap remain in the [research archive](archival_studies.md).
