# Supplement: Top-2 Native splits by largest relative same-host speedup

Two Native splits per model ranked from unrounded FPS ratios against the fastest measured Full on the same host; ties use ascending UID. Energy does not alter this ranking. G_n = energy of that same Full / split energy. Selection is retrospective; quality and endpoint differences remain in the dataset.

| Model | Rank | Setup/cut | Full | Full FPS | Split FPS | Speedup | Split mJ/image | G_n |
|---|---:|---|---|---:|---:|---:|---:|---:|
| MobileNetV3-L | 1 | H10/b078 | TRT | 710 | 1172 | 1.65 | 20.09 | 1.38 |
| MobileNetV3-L | 2 | H10/b074 | TRT | 710 | 1143 | 1.61 | 19.94 | 1.39 |
| RegNet-X 1.6GF | 1 | H10/b123 | TRT | 316 | 1367 | 4.33 | 15.83 | 4.69 |
| RegNet-X 1.6GF | 2 | H10/b132 | TRT | 316 | 1175 | 3.72 | 16.95 | 4.38 |
| ResNet-50 | 1 | H10/b095 | TRT | 522 | 1100 | 2.11 | 29.46 | 1.87 |
| ResNet-50 | 2 | H10/b088 | TRT | 522 | 1060 | 2.03 | 30.57 | 1.80 |
| YOLO11l | 1 | H10/b120 | TRT | 39 | 53 | 1.36 | 555.75 | 1.18 |
| YOLO11l | 2 | H10/b062 | TRT | 39 | 51 | 1.31 | 558.64 | 1.17 |
| YOLO26m | 1 | H10/b043 | TRT | 84 | 110 | 1.31 | 319.65 | 1.22 |
| YOLO26m | 2 | H10/b038 | TRT | 84 | 108 | 1.29 | 323.19 | 1.21 |
| YOLO26s | 1 | H8/b021 | TRT | 151 | 187 | 1.24 | 157.65 | 1.26 |
| YOLO26s | 2 | H10/b021 | TRT | 150 | 182 | 1.21 | 168.51 | 1.14 |
| YOLOv7 | 1 | H8/b066 | TRT | 53 | 113 | 2.13 | 330.14 | 1.81 |
| YOLOv7 | 2 | H10/b044 | TRT | 53 | 70 | 1.32 | 455.36 | 1.28 |
