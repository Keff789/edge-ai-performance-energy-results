# Archived Hailo-10H format measurement scripts

These are the original measurement sources for the completed 3 September 2026
[host-format microbenchmarks](../../../results/split-inference/microbenchmarks/README.md).

| Source | Recorded scope |
|---|---|
| [hailo10_input_format_ab.py](input_format/hailo10_input_format_ab.py) | FLOAT32 versus HEF-native UINT8/UINT16 host inputs, identical quantized device values, native outputs and one outstanding job. External reference quantization is timed separately. |
| [hailo10_infermodel_format_ab.py](infermodel_output_format/hailo10_infermodel_format_ab.py) | FLOAT32 versus HEF-native UINT8/UINT16 host outputs with FLOAT32 inputs; serial latency and separately measured streaming throughput. The retained run used two outstanding jobs for throughput. |

Both files are byte-identical to `experiments/hailo10/…` in Results commit
[`fc57876b0a6ba69e90723e3a9209b72b36cbaa51`](https://github.com/Keff789/onnx-splitpoint-results/tree/fc57876b0a6ba69e90723e3a9209b72b36cbaa51/experiments/hailo10).
They also match the original download packages
`ONNX_Splitpoint_Hailo10H_UINT8_Input_AB_Test_2026-09-03.zip`
(`hailo10_input_ab/hailo10_input_format_ab.py`) and
`ONNX_Splitpoint_v2.79.14_Akutbefunde_und_Hailo10_AB_Test_2026-09-03.zip`
(`hailo10_ab/hailo10_infermodel_format_ab.py`). Original code and version `1.0`
are preserved without edits.

These programs perform hardware measurements and require NumPy, a Hailo-10H
device, compatible HailoRT and the recorded compiled HEF. Their required `--hef`
and `--output` arguments identify the external model and new measurement output.
They are kept outside the [offline analysis entry points](../../README.md) and
were neither imported nor executed during this source recovery. Only source
identity and Python syntax were checked. The supplied result JSON and comparison
CSV remain unchanged. These September format experiments are separate from the
7 October YOLOv7 completion/stage profiles and the independent stage-cost study.

See the existing [rights and notices](../../../RIGHTS_AND_NOTICES.md).
