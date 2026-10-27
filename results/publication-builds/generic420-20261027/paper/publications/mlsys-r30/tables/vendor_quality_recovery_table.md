# Vendor Quality

MobileNetV3 Top1 on the same 5,000 images, CPU ONNX reference 73.70%. Current A4-bound b027 with TensorRT suffix. This current view preserves the separate historical vendor table and its older source generation.

| Host | Accel. Full (%) | Split b027 (%) | Recovered (pp) |
| --- | ---: | ---: | ---: |
| H8 | 60.62 | 71.58 | +10.96 |
| H10 | 59.42 | 72.22 | +12.80 |
| DeepX | 71.72 | 72.18 | +0.46 |
