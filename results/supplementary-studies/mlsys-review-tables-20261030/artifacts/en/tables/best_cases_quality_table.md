# Best Cases Quality

Fastest measured single-backend Full and split across all setups among configurations with at most 5% numeric CPU-relative quality loss. Changes use unrounded values. Energy belongs to these same throughput-selected configurations; negative energy change means less energy per image. Delta q is split minus Full in percentage points: Top1 for classifiers and COCO AP50:95 for detectors. Passing the quality threshold does not establish statistical equivalence. YOLO11l uses Generic; the other selected splits use Native.

| Model | Fastest Full | FPS | Fastest split | FPS | FPS gain (%) | Energy change (%) | Delta q (pp) |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| MobileNetV3-L | DeepX | 1469 | DeepX/b135 | 1552 | +5.6 | +4.8 | +0.30 |
| RegNet-X | DeepX | 538 | H10/b123 | 1367 | +153.9 | -49.8 | +0.46 |
| ResNet-50 | DeepX | 656 | H10/b095 | 1100 | +67.6 | +6.6 | -0.38 |
| YOLO11l | DeepX | 63 | DeepX/b511 | 69 | +9.9 | +3.5 | +0.71 |
| YOLO26m | TRT (H8) | 85 | H10/b043 | 110 | +30.1 | -20.1 | -0.79 |
| YOLO26s | TRT (DeepX) | 152 | H8/b021 | 187 | +23.2 | -16.1 | -0.93 |
| YOLOv7 | DeepX | 83 | H8/b066 | 113 | +35.3 | +22.5 | -0.12 |
