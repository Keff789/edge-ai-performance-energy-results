# Hailo-8 MobileNet HAR comparison

This completed diagnosis from 12 September 2026 compares six processing stages on the same **16 previously examined development images**. It retains status `diagnostic_evaluated`, `claim_eligible=false` and an unevaluated final quality gate. The cohort is separate from THESIS20 and Refresh16.

| Stage | Correct Top1 / 16 | Correct Top5 / 16 |
|---|---:|---:|
| Source ONNX, float | 13 | 14 |
| Compiler ONNX, float | 13 | 14 |
| Parsed HAR, SDK_NATIVE | 13 | 14 |
| Quantized HAR, SDK_QUANTIZED | 9 | 13 |
| GPU-built HEF | 10 | 15 |
| CPU-built HEF | 8 | 14 |

Source and compiler float outputs were identical. Parsed HAR differed from compiler float by at most 9.78×10⁻⁶, with no Top1 changes. Parsed-to-quantized RMS difference was 0.70196528 with five Top1 changes; quantized-to-GPU-HEF RMS difference was 0.39264502 with four changes. These observations locate numerical deviations in this example; they do not establish quantization as the sole cause of hardware quality loss.

[Per-image predictions](per_image.csv) and the [complete numerical export](comparison.json) retain all six stages, Top5 predictions, pairwise differences and original HAR sizes/hashes. Only two original machine-specific HAR path strings have been replaced by descriptive `external_gpu_build/build/…` identifiers; those identifiers do not denote bundled files. Numerical values are unchanged.

The HARs belong to the GPU build according to its original report. Their hashes were recorded later, not attested at build time. Quantized HAR versus CPU HEF compares different builds; the corresponding CPU HAR was unavailable. Inputs were the already recorded FLOAT32/NHWC feeds. This opened cohort supplies neither a new hold-out evaluation nor final additional GPU evidence. Further optimized-float and integer-I/O investigations were not completed.

The original [comparison helper](../../../scripts/supplementary-studies/hailo8-har-20260912/array_compare.py) and its [support module](../../../scripts/supplementary-studies/hailo8-har-20260912/common.py) are retained. Full logit comparisons need the external bound arrays, comparison request and stage process/result metadata:

```bash
python scripts/supplementary-studies/hailo8-har-20260912/array_compare.py compare --request /path/to/comparison_request.json --out /path/to/prepared-comparison-directory
```

Run from the repository root with NumPy installed. The `compare` mode consumes recorded arrays; the separate `prepare` mode performs ONNX reference inference and is not part of compact reproduction. The request retains exact file/hash/size bindings and must point to the corresponding external originals. No HARs, models, SDKs, images or raw arrays are bundled. This update checked exported prediction/count consistency; it did not rerun inference or reconstruct missing logits.

Source: [completed HAR evidence](https://github.com/Keff789/onnx-splitpoint-results/tree/380dfa09aa6740acdc71908cb6e5dd5c8fc115ad/results/hailo8/20260912_mobilenet_gpu/har_emulation/hailo8_har_git_20260912T171411Z_x0j2t2o1) and [original helpers](https://github.com/Keff789/onnx-splitpoint-results/tree/380dfa09aa6740acdc71908cb6e5dd5c8fc115ad/experiments/hailo8/har_comparison_r1). See [rights](../../../RIGHTS_AND_NOTICES.md).
