# Qualität der Hauptkonfigurationen

Die archivierte historische Qualität verwendet gepaarte 95%-Bootstrap-Intervalle (5,000 Beispiele, 1,000 Bootstrap-Wiederholungen). Die Zulassung verwendet eine Verlustgrenze von 5% für den Punktschätzer. Die beiden späteren YOLOv7-Hauptimplementierungen liefern nur berichtete Kennzeichnungen. Ihre numerische Qualität bleibt NA. Historische AP-Werte werden ihnen nicht zugeordnet.

| Modell / System / Cut | Metrik | CPU-Qualitätswert (%) | Split-Qualitätswert (%) | Differenz (pp) | 95%-Intervall der Differenz (pp) | Relativer Verlust (%) | Intervall überschreitet 5% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MobileNet-V3-L/H10/b074 | Top1 | 73.70 | 70.36 | -3.34 | [-4.08, -2.56] | 4.53 | Ja |
| MobileNet-V3-L/H10/b068 | Top1 | 73.70 | 70.68 | -3.02 | [-3.72, -2.26] | 4.10 | Ja |
| RegNet-X/H10/b123 | Top1 | 78.94 | 79.16 | 0.22 | [-0.28, 0.72] | -0.28 | Nein |
| RegNet-X/H10/b132 | Top1 | 78.94 | 78.74 | -0.20 | [-0.74, 0.32] | 0.25 | Nein |
| ResNet-50/H10/b095 | Top1 | 80.44 | 80.16 | -0.28 | [-0.76, 0.22] | 0.35 | Nein |
| ResNet-50/H10/b088 | Top1 | 80.44 | 80.28 | -0.16 | [-0.62, 0.32] | 0.20 | Nein |
| YOLO11l/H8/b120 | COCO_AP_50_95 | 46.68 | 45.89 | -0.80 | [-1.02, -0.59] | 1.71 | Nein |
| YOLO11l/H8/b062 | COCO_AP_50_95 | 46.68 | 45.90 | -0.79 | [-1.02, -0.59] | 1.68 | Nein |
| YOLO26m/H10/b043 | COCO_AP_50_95 | 44.90 | 43.66 | -1.24 | [-1.53, -0.97] | 2.75 | Nein |
| YOLO26m/H10/b038 | COCO_AP_50_95 | 44.90 | 43.67 | -1.23 | [-1.50, -0.92] | 2.75 | Nein |
| YOLO26s/H8/b021 | COCO_AP_50_95 | 40.09 | 39.18 | -0.91 | [-1.18, -0.63] | 2.26 | Nein |
| YOLO26s/H10/b021 | COCO_AP_50_95 | 40.09 | 39.21 | -0.88 | [-1.16, -0.59] | 2.19 | Nein |
| YOLOv7/H8/b066 | COCO_AP_50_95 | NA | NA | NA | NA | NA | NA |
| YOLOv7/H10/b044 | COCO_AP_50_95 | NA | NA | NA | NA | NA | NA |
