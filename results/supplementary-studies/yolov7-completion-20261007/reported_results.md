# Historical YOLOv7 completed-task performance

Reported three-process repeat medians; 100 warmups and 1,000 completed tasks per repeat. Six Full alternatives were reused from the earlier performance task. Three separate Full controls are not included. FPS are rounded here; the CSV retains every reported decimal and repeat.

| Setup | Path | Median FPS | / Fastest Full | / Accelerator Full | Reported quality | Energy |
|---|---|---:|---:|---:|---|---|
| H8 | Accelerator Full | 31 | — | — | accuracy_loss | not measured |
| H8 | TensorRT Full | 52 | — | — | reference_close | not measured |
| H8 | Split b009 | 43 | 0.828 | 1.361 | reference_close | not measured |
| H8 | Split b044 | 48 | 0.923 | 1.519 | reference_close | not measured |
| H8 | Split b066 | 112 | 2.172 | 3.574 | reference_close | not measured |
| H10 | Accelerator Full | 12 | — | — | accuracy_loss | not measured |
| H10 | TensorRT Full | 51 | — | — | reference_close | not measured |
| H10 | Split b009 | 51 | 0.998 | 4.171 | reference_close | not measured |
| H10 | Split b044 | 65 | 1.253 | 5.238 | reference_close | not measured |
| H10 | Split b066 | 53 | 1.036 | 4.332 | reference_close | not measured |
| DeepX | Accelerator Full | 23 | — | — | reference_close | not measured |
| DeepX | TensorRT Full | 47 | — | — | reference_close | not measured |
| DeepX | Split b009 | 34 | 0.716 | 1.476 | reference_close | not measured |
| DeepX | Split b044 | 49 | 1.031 | 2.126 | reference_close | not measured |
| DeepX | Split b066 | 31 | 0.647 | 1.333 | reference_close | not measured |

The fastest technically comparable Full path was selected before quality filtering. Small ratios above one do not establish statistical superiority. Quality labels are transcribed from the report, not independently evaluated. No matching energy measurements are available for this cohort; energy remains NA and is not joined from later results.

These final repeats are separate from the short instrumented H10 stage diagnosis. Its original detailed CSV and hardware profiling scripts are not included; no stage timings are reconstructed here.
