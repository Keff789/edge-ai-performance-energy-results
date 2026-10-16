# Native endpoint reconstruction and decoder canaries

These historical YOLOv7-paper `b066` / Hailo-8 → TensorRT observations show why the physical suffix output and completed detections must be reported separately. They come from the reference reports and the `v2793` regression fixture in the bundled [ONNX Splitpoint Tool source snapshot](../../../software/README.md), the archived 32-image pipeline report supplied with the MLSys analysis, and explicitly labelled dissertation summary tables. Their August 2026 scope is separate from the current Refresh16 results and the [October completion study](../yolov7-completion-20261007/README.md).

## Results and tables

| View | Readable table | Machine-readable data |
|---|---|---|
| Serial completion and concurrent one-image smoke | [Markdown](tables/endpoint_comparison.md) · [TeX](tables/endpoint_comparison.tex) | [CSV](tables/endpoint_comparison.csv) |
| Decoder comparison on 32 images | [Summary](tables/decoder_summary.md) · [TeX](tables/decoder_summary.tex) | [CSV](tables/decoder_summary.csv) |
| Per-image decoder timings and parity | [Markdown](tables/decoder_images.md) · [TeX](tables/decoder_images.tex) | [CSV](tables/decoder_images.csv) |
| Three-stage pipeline on 32 images | [Repetitions](tables/pipeline_canary_repetitions.md) · [TeX](tables/pipeline_canary_repetitions.tex) | [CSV](tables/pipeline_canary_repetitions.csv) |
| Reported execution paths | [Table](tables/reported_execution_paths.md) · [TeX](tables/reported_execution_paths.tex) | [CSV](tables/reported_execution_paths.csv) |
| Reported adapter/producer checks | [Table](tables/reported_adapter_checks.md) · [TeX](tables/reported_adapter_checks.tex) | [CSV](tables/reported_adapter_checks.csv) |
| Recomputed aggregates | [JSON](tables/summary.json) | [Input report extracts](inputs/reference_extracts.json) |

The serial report has a median completed throughput of 15.872 FPS. The separate concurrent **one-image smoke** has 97.059 completed FPS and 97.077 raw-output FPS, over three fresh runtime repetitions of 1,000 frames after 100 drained warm-ups. Input preparation and execution differ between the reports; their juxtaposition does not estimate a controlled scheduling-only speedup. Repeat minima/maxima are observed ranges, not confidence intervals.

The separate **32-image pipeline canary** has 95.889 completed FPS and 95.902 raw-output FPS, with a median completed/raw ratio of 0.999868761. Three repetitions each cycle the fixed corpus for 1,000 measured completions after 100 drained warm-ups. All 32 images pass recorded parity in each repetition and in the separate postflight. P1/P2/Post means and observed rates are retained per repetition; theoretical stage capacity is not substituted for observed throughput. This corpus differs from the one-image smoke.

The **32-image decoder parity canary** is a different experiment: all 32 retained images have exact sparse/oracle detections. Median decoder times across image medians are 36.235 ms for the frozen oracle and 1.297 ms for the sparse implementation. The median paired speedup is 25.904×, not the ratio of those aggregate medians. Each image has five warm-ups and 30 decoder iterations. The corpus uses annotation-count/geometry strata and a forced reference image; it is not a COCO accuracy evaluation. Its one-frame raw-head collection is explicitly not a performance measurement.

## Endpoint and verification methods

The original published engine included multiscale decoding and EfficientNMS in P2, with final C++ object materialisation and coordinate presentation outside its measured section. The reconstructed current-artifact suffix instead produces three raw heads. The [reported execution-path table](tables/reported_execution_paths.md) distinguishes published pipeline, original replay, current-artifact replay and completed three-stage execution; their roughly 95–97 FPS values are diagnostic throughputs with different endpoint scopes. A host CPU adapter performs sparse multiscale decoding, class-aware NMS, inverse letterbox and canonical records to reach `completed_detection`. Engine-integrated decoding would place this work elsewhere and requires its own endpoint contract; the raw suffix output cannot stand in for completed detections. In the concurrent path, P1 handles image read/preprocessing and Hailo inference, P2 handles handoff/TensorRT/raw-head D2H, and Post handles task completion. Bounded queues expose backpressure. Theoretical capacity from stage means is therefore distinct from observed throughput.

The fast timed callback excludes hashing, JSON evidence construction, contract discovery and the slow oracle. A separate postflight checks raw-head identity and exact oracle parity outside timing. The retained smoke verifies one image; the decoder and pipeline reports each verify their 32-image corpus. The current-artifact replay used the quality-corrected dequantisation engine and matched the prepared inputs, boundary payload and raw heads; within that replay, explicit dequantisation did not explain the slowdown. Neither is a new quality measurement.

The preserved boundary contract binds `uint8_dequant_fp16`, NHWC-to-NCHW layout, scale 0.06533566862344742 and zero point 5. The original `scripts/native_part2_boundary_replay_compare.py` describes replaying an existing boundary through the bridge ONNX to separate dequant/layout errors from TensorRT/output-path differences. That diagnostic needs external arrays/models and is not rerun by this table command. No new fit or dequantization sweep is performed.

## Offline reproduction

From the repository root, with Python 3.10 or newer and its standard library:

```bash
python3 -I -B scripts/supplementary-studies/native-endpoint-reconstruction/reproduce.py --output ../native-endpoint-reproduced
```

Use a fresh or empty external output directory. The command recomputes repetition/image aggregates, checks them against the retained original summaries, and writes six CSV/Markdown/TeX table families plus `summary.json`. Reported execution-path and adapter tables retain the manuscript precision; no underlying repetitions are invented for those rows. All inputs are local to this repository. The small `percentile` and `summarize` functions are taken unchanged from the source canary; no hardware module is imported.

The inputs are exact selected fields from four existing JSON reports, with source archive member names retained. Absolute device paths, raw detections and duplicated contracts are omitted. This reproduces reported numerical summaries, not hardware timing, raw tensor verification or independent COCO quality. The full source archive retains the original reports and MIT notice.

The [32-image pipeline input](inputs/pipeline_canary_extract.json) is a compact field-preserving projection of `analysis/runner_sources/three_stage__three_stage_canary_report.json` in the MLSys R10 source. The two reported-results CSVs transcribe `2_body/08_evaluation/14_endpoint_execution.tex` and `4_appendix/02_split_reproduction.tex` in the dissertation v46 source. For the two pipeline adapter rows, the appendix prose supplies three-decimal rates; producer rates retain the two-decimal table precision. The 16-image YOLO11l replay is adapter verification without accelerator timing, and the 300-unit H10/DeepX observations qualify producers rather than complete detectors.

The older Generic–Native screening summary reports 24 paired identities, six groups with at least three pairs, 17/18 concordant within-group orderings and the same best candidate in all six groups (zero reported regret). This is a reported aggregate, not a recovered pair-level dataset. It does not resolve the separately documented identity-join issue in the 264-case/208-materialised-measurement reprojection, establish multi-tensor Native support or replace the later [THESIS20](../thesis20-ranking-20261005/README.md) and [MLSys](../mlsys-selection-20261007/README.md) cohorts.
