Reported ResNet50/Imagenette development matrix. Ranges retain mixed original timing contracts; unavailable throughput is NA and is never inferred from latency. Quality is a fraction. This is neither ImageNet nor B500.

| Execution path | Top-1 | Top-5 | Latency (ms) | Throughput (FPS) | Status |
| --- | --- | --- | --- | --- | --- |
| TensorRT full | 0.82 | 0.96 | 7.5–7.8 | 129–134 | valid canonical full baseline. |
| DEEPX DX-M1 full | 0.84 | 0.94 | 3.2 | 310.9 | valid full-backend repeated-feed path. |
| DEEPX DX-M1→TensorRT | 0.76–0.78 | 0.94 | 20.3–23.5 | 62.5–72.9 | Generic Runner development row. |
| Hailo-8 full/composed | 0.82–0.84 | 0.96 | 12–13 | NA | valid with quantised-interface warning. |
| Hailo-8→TensorRT | 0.82 | 0.96 | 9–10 | NA | valid with interface warning. |
| TensorRT→Hailo-8 | 0.82 | 0.96 | 8–9 | NA | valid activation-proxy-calibrated Stage 2. |
| TensorRT→DEEPX DX-M1 | split-dependent | split-dependent | NA | NA | buildable and accepted only after a multi-sample contract probe. |
