# Best Cases

Fastest observed Full and split across all setups among configurations with at most 5% numeric CPU-relative quality loss. Changes use unrounded values. Energy belongs to these same throughput-selected configurations; negative energy change means less energy per image.

| Model | Fastest Full | FPS | Fastest split | FPS | FPS gain (%) | Energy change (%) |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| MobileNetV3-L | DeepX | 1469 | Native DeepX/b135 | 1552 | +5.6 | +4.8 |
| RegNet-X | DeepX | 538 | Native H10/b123 | 1367 | +153.9 | -49.8 |
| ResNet-50 | DeepX | 656 | Native H10/b095 | 1100 | +67.6 | +6.6 |
| YOLO11l | DeepX | 63 | Generic DeepX/b511 | 69 | +9.9 | +3.5 |
| YOLO26m | TRT (H8) | 85 | Native H10/b043 | 110 | +30.1 | -20.1 |
| YOLO26s | TRT (DeepX) | 152 | Native H8/b021 | 187 | +23.2 | -16.1 |
| YOLOv7 | DeepX | 83 | Native H8/b066 | 113 | +35.3 | +22.5 |
