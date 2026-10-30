# Beste Konfigurationen mit Qualität

Schnellstes gemessenes Full mit einem Backend und schnellster Split über alle Systeme mit höchstens 5% numerischem Qualitätsverlust relativ zur CPU-Referenz. Änderungen verwenden ungerundete Werte. Die Energie gehört zu denselben nach Durchsatz gewählten Konfigurationen. Eine negative Energieänderung bedeutet weniger Energie pro Bild. Die Differenz q ist Split minus Full in Prozentpunkten: Top1 für Klassifikatoren und COCO AP50:95 für Detektoren. Das Einhalten der Qualitätsgrenze belegt keine statistische Äquivalenz. YOLO11l verwendet Generic. Die übrigen ausgewählten Splits verwenden Native.

| Modell | Schnellstes Full | FPS | Schnellster Split | FPS | FPS-Zuwachs (%) | Energieänderung (%) | Differenz q (pp) |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| MobileNetV3-L | DeepX | 1469 | DeepX/b135 | 1552 | +5.6 | +4.8 | +0.30 |
| RegNet-X | DeepX | 538 | H10/b123 | 1367 | +153.9 | -49.8 | +0.46 |
| ResNet-50 | DeepX | 656 | H10/b095 | 1100 | +67.6 | +6.6 | -0.38 |
| YOLO11l | DeepX | 63 | DeepX/b511 | 69 | +9.9 | +3.5 | +0.71 |
| YOLO26m | TRT (H8) | 85 | H10/b043 | 110 | +30.1 | -20.1 | -0.79 |
| YOLO26s | TRT (DeepX) | 152 | H8/b021 | 187 | +23.2 | -16.1 | -0.93 |
| YOLOv7 | DeepX | 83 | H8/b066 | 113 | +35.3 | +22.5 | -0.12 |
