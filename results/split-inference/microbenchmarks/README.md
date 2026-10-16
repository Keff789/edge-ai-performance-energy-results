# Hailo-10H host-format experiments

These completed 3 September 2026 microbenchmarks isolate host input or output representation for YOLO26s Part 1 at cut `b024`, using HailoRT 5.3.0 on Jetson Orin NX. They measure a device stage with synthetic device-equivalent inputs. TensorRT Part 2, FIFO overlap, model dataset quality and energy are outside the measured scope. They are separate from the 450-deployment selection.

| Experiment | FLOAT32 mean latency | Native UINT8 mean latency | Observed stream rate |
|---|---:|---:|---|
| Host input, one outstanding job | 49.618 ms | 12.769 ms | 20.151 to 78.280 images/s |
| Host output, two outstanding jobs | 63.027 ms | 49.741 ms | 28.348 to 28.294 images/s |

Native output reduces host bytes fourfold and measured latency, while the stream-rate change is −0.19%: this observation does not establish a throughput benefit. Native input reduces host bytes fourfold with exactly equal quantized outputs. Its external reference quantization averages 1.259 ms and is excluded from both inference timings; native latency plus that cost is 14.027 ms.

[CSV with counts and dispersion](tables/format-comparison.csv) · [Complete input-format record](data/input-format.json) · [Complete output-format record](data/output-format.json)

The JSON retains HEF identity, shapes, quantization, runtime versions, warm-up, frame counts, order, correctness checks and recorded clock-query limitations. Environment installation paths and the host name have been removed or made relative in these export copies; numerical values are unchanged. The experiments have one recorded run each; frame-level dispersion is not independent run-to-run uncertainty.

The original [input-format script](../../../scripts/hardware/hailo10/input_format/hailo10_input_format_ab.py) and [output-format script](../../../scripts/hardware/hailo10/infermodel_output_format/hailo10_infermodel_format_ab.py) are now included byte-identically to Results commit `fc57876b0a6ba69e90723e3a9209b72b36cbaa51`. Their [source and requirements](../../../scripts/hardware/hailo10/README.md) identify the matching original A/B-test packages. They require a Hailo-10H device, HailoRT and the recorded compiled HEF. They are not part of the hardware-free reproduction and were not executed for this export.

[Back to split inference](../README.md)
