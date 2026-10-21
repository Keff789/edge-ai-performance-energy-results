# Qualität der aktuellen Konfigurationen

Numerischer Qualitätsverlust gegenüber der CPU für dieselben globalen Durchsatzgewinner. Ein negativer Verlust bedeutet einen höheren Punktschätzer, keine statistisch signifikante Verbesserung.

| Modell | Split | q (%) | Verlust (%) | Full | q (%) | Verlust (%) |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| MobileNetV3-L | DeepX/b135 | 72.02 | 2.28 | DeepX | 71.72 | 2.69 |
| RegNet-X | H10/b123 | 79.16 | -0.28 | DeepX | 78.70 | 0.30 |
| ResNet-50 | H10/b095 | 80.16 | 0.35 | DeepX | 80.54 | -0.12 |
| YOLO11l | H10/b120 | 45.55 | 2.42 | DeepX | 45.67 | 2.17 |
| YOLO26m | H10/b043 | 43.66 | 2.75 | TRT (H8) | 44.82 | 0.18 |
| YOLO26s | H8/b021 | 39.18 | 2.26 | TRT (DeepX) | 40.11 | -0.05 |
| YOLOv7 | H8/b066 | 45.74 | 0.64 | DeepX | 45.86 | 0.38 |
