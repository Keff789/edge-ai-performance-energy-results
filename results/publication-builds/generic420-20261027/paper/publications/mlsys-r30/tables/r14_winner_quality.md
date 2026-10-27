# Winner Quality

Top1 for classifiers and AP50:95 for detectors. The first rows use global throughput winners admitted by the 5% CPU-relative quality rule. The final MobileNet rows compare b027 to Hailo Fulls on the same host; those Fulls fail the rule. Direct quality differences are split minus the stated Full.

| Model / setup | Full q (%) | Split q (%) | Delta q (pp) |
| --- | ---: | ---: | ---: |
| MobileNetV3-L | 71.72 | 72.02 | +0.30 |
| RegNet-X | 78.70 | 79.16 | +0.46 |
| ResNet-50 | 80.54 | 80.16 | -0.38 |
| YOLO11l | 45.67 | 46.37 | +0.71 |
| YOLO26m | 44.82 | 44.03 | -0.79 |
| YOLO26s | 40.11 | 39.18 | -0.93 |
| YOLOv7 | 45.86 | 45.74 | -0.12 |
| MobileNet / H8 | 60.62 | 71.58 | +10.96 |
| MobileNet / H10 | 59.42 | 72.22 | +12.80 |
