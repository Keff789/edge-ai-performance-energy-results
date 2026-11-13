# Split-Optima je Modell und System

Schnellste und energieärmste gemessene Splits je Modell/System/Runner. Kandidatenzahlen beschreiben den gemessenen Suchraum. Q ist die vorhandene Datensatzmetrik in Prozent: Top-1 für Klassifikatoren und COCO mAP@[.50:.95] für Detektoren. Diese Metriken werden nicht zusammengefasst. Gemeinsame Optima sind ein Punkt. Alle Auswahlen sind rückblickend. Die Energie ist in mJ/Bild einschließlich Host angegeben.

| Runner | Modell | System | Kandidaten | Schnellster Cut | FPS | mJ/Bild | Q (%) | Energieärmster Cut | FPS | mJ/Bild | Q (%) | Gleicher Punkt |
|---|---|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|
| Native | MobileNetV3-L (Top-1) | DeepX | 17 | b135 | 1552 | 12.59 | 72.02 | b135 | 1552 | 12.59 | 72.02 | ja |
| Native | MobileNetV3-L (Top-1) | H10 | 17 | b078 | 1172 | 20.09 | 67.10 | b085 | 1140 | 18.36 | 67.58 | nein |
| Native | MobileNetV3-L (Top-1) | H8 | 17 | b027 | 993 | 23.01 | 71.58 | b027 | 993 | 23.01 | 71.58 | ja |
| Native | RegNet-X 1.6GF (Top-1) | DeepX | 20 | b109 | 729 | 30.69 | 78.76 | b115 | 728 | 30.05 | 78.82 | nein |
| Native | RegNet-X 1.6GF (Top-1) | H10 | 20 | b123 | 1367 | 15.83 | 79.16 | b123 | 1367 | 15.83 | 79.16 | ja |
| Native | RegNet-X 1.6GF (Top-1) | H8 | 20 | b073 | 618 | 41.73 | 77.76 | b073 | 618 | 41.73 | 77.76 | ja |
| Native | ResNet-50 (Top-1) | DeepX | 19 | b104 | 782 | 30.97 | 80.54 | b119 | 678 | 28.42 | 80.52 | nein |
| Native | ResNet-50 (Top-1) | H10 | 19 | b095 | 1100 | 29.46 | 80.16 | b095 | 1100 | 29.46 | 80.16 | ja |
| Native | ResNet-50 (Top-1) | H8 | 19 | b038 | 581 | 49.92 | 80.24 | b060 | 570 | 45.17 | 80.18 | nein |
| Native | YOLO11l (mAP) | DeepX | 3 | b062 | 50 | 544.29 | 46.46 | b062 | 50 | 544.29 | 46.46 | ja |
| Native | YOLO11l (mAP) | H10 | 3 | b120 | 53 | 555.75 | 45.55 | b120 | 53 | 555.75 | 45.55 | ja |
| Native | YOLO11l (mAP) | H8 | 3 | b120 | 44 | 555.17 | 45.89 | b120 | 44 | 555.17 | 45.89 | ja |
| Native | YOLO26m (mAP) | DeepX | 3 | b043 | 98 | 332.03 | 44.81 | b043 | 98 | 332.03 | 44.81 | ja |
| Native | YOLO26m (mAP) | H10 | 3 | b043 | 110 | 319.65 | 44.03 | b043 | 110 | 319.65 | 44.03 | ja |
| Native | YOLO26m (mAP) | H8 | 3 | b038 | 79 | 360.60 | 43.66 | b043 | 79 | 355.99 | 43.97 | nein |
| Native | YOLO26s (mAP) | DeepX | 3 | b021 | 163 | 176.61 | 40.02 | b021 | 163 | 176.61 | 40.02 | ja |
| Native | YOLO26s (mAP) | H10 | 3 | b021 | 182 | 168.51 | 39.21 | b021 | 182 | 168.51 | 39.21 | ja |
| Native | YOLO26s (mAP) | H8 | 3 | b021 | 187 | 157.65 | 39.18 | b021 | 187 | 157.65 | 39.18 | ja |
| Native | YOLOv7 (mAP) | DeepX | 3 | b044 | 64 | 469.30 | 45.97 | b044 | 64 | 469.30 | 45.97 | ja |
| Native | YOLOv7 (mAP) | H10 | 3 | b044 | 70 | 455.36 | 45.78 | b044 | 70 | 455.36 | 45.78 | ja |
| Native | YOLOv7 (mAP) | H8 | 3 | b066 | 113 | 330.14 | 45.74 | b066 | 113 | 330.14 | 45.74 | ja |
| Generic | MobileNetV3-L (Top-1) | DeepX | 17 | b056 | 810 | 25.22 | 72.28 | b056 | 810 | 25.22 | 72.28 | ja |
| Generic | MobileNetV3-L (Top-1) | H10 | 17 | b027 | 419 | 46.26 | 72.22 | b027 | 419 | 46.26 | 72.22 | ja |
| Generic | MobileNetV3-L (Top-1) | H8 | 17 | b027 | 524 | 46.33 | 71.58 | b019 | 494 | 45.53 | 71.60 | nein |
| Generic | RegNet-X 1.6GF (Top-1) | DeepX | 20 | b052 | 412 | 59.08 | 78.78 | b052 | 412 | 59.08 | 78.78 | ja |
| Generic | RegNet-X 1.6GF (Top-1) | H10 | 20 | b052 | 348 | 69.33 | 77.82 | b080 | 309 | 67.59 | 78.00 | nein |
| Generic | RegNet-X 1.6GF (Top-1) | H8 | 20 | b066 | 375 | 65.89 | 78.04 | b066 | 375 | 65.89 | 78.04 | ja |
| Generic | ResNet-50 (Top-1) | DeepX | 19 | b002 | 463 | 61.94 | 80.50 | b119 | 340 | 50.88 | 80.52 | nein |
| Generic | ResNet-50 (Top-1) | H10 | 19 | b002 | 303 | 82.33 | 80.20 | b002 | 303 | 82.33 | 80.20 | ja |
| Generic | ResNet-50 (Top-1) | H8 | 19 | b002 | 436 | 74.53 | 80.14 | b060 | 346 | 71.36 | 80.18 | nein |
| Generic | YOLO11l (mAP) | DeepX | 4 | b511 | 69 | 326.19 | 46.37 | b511 | 69 | 326.19 | 46.37 | ja |
| Generic | YOLO11l (mAP) | H10 | 3 | b003 | 30 | 829.21 | 45.64 | b120 | 27 | 811.74 | 45.55 | nein |
| Generic | YOLO11l (mAP) | H8 | 3 | b120 | 43 | 573.88 | 45.89 | b120 | 43 | 573.88 | 45.89 | ja |
| Generic | YOLO26m (mAP) | DeepX | 3 | b038 | 64 | 423.95 | 44.78 | b043 | 64 | 417.70 | 44.81 | nein |
| Generic | YOLO26m (mAP) | H10 | 3 | b038 | 52 | 485.93 | 43.67 | b043 | 52 | 483.01 | 43.66 | nein |
| Generic | YOLO26m (mAP) | H8 | 3 | b043 | 79 | 362.35 | 43.64 | b043 | 79 | 362.35 | 43.64 | ja |
| Generic | YOLO26s (mAP) | DeepX | 3 | b021 | 119 | 213.84 | 40.02 | b021 | 119 | 213.84 | 40.02 | ja |
| Generic | YOLO26s (mAP) | H10 | 3 | b021 | 74 | 296.28 | 39.21 | b021 | 74 | 296.28 | 39.21 | ja |
| Generic | YOLO26s (mAP) | H8 | 3 | b021 | 137 | 190.39 | 39.18 | b038 | 134 | 190.30 | 39.16 | nein |
| Generic | YOLOv7 (mAP) | DeepX | 3 | b044 | 50 | 549.51 | 45.97 | b044 | 50 | 549.51 | 45.97 | ja |
| Generic | YOLOv7 (mAP) | H10 | 3 | b044 | 47 | 582.19 | 45.78 | b044 | 47 | 582.19 | 45.78 | ja |
| Generic | YOLOv7 (mAP) | H8 | 3 | b066 | 47 | 548.07 | 45.74 | b066 | 47 | 548.07 | 45.74 | ja |
