# Qualität der schnellsten Konfigurationen

Top1 für Klassifikatoren und AP50:95 für Detektoren. Die ersten Zeilen verwenden globale Durchsatzgewinner, die die CPU-relative 5%-Qualitätsregel erfüllen. Die letzten MobileNet-Zeilen vergleichen b027 mit Hailo-Full auf demselben Host. Diese Full-Konfigurationen erfüllen die Regel nicht. Direkte Qualitätsdifferenzen sind Split minus angegebenes Full.

| Modell / System | Full q (%) | Split q (%) | Differenz q (pp) |
| --- | ---: | ---: | ---: |
| MobileNetV3-L | 71.72 | 72.02 | +0.30 |
| RegNet-X | 78.70 | 79.16 | +0.46 |
| ResNet-50 | 80.54 | 80.16 | -0.38 |
| YOLO11l | 45.67 | 45.55 | -0.12 |
| YOLO26m | 44.82 | 43.66 | -1.15 |
| YOLO26s | 40.11 | 39.18 | -0.93 |
| YOLOv7 | 45.86 | 45.74 | -0.12 |
| MobileNet / H8 | 60.62 | 71.58 | +10.96 |
| MobileNet / H10 | 59.42 | 72.22 | +12.80 |
