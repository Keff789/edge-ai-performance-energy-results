# Full-Referenzen des schnellsten Splits

Derselbe gewählte Split mit zwei Full-Referenzen. R_h verwendet dessen physischen Host, R_g das global schnellste Full. Der Split wird nicht nach relativem Gewinn neu ausgewählt. Der Vergleich beschreibt die Wahl der Referenz, keinen Optimierungsschritt.

| Modell | Gewählter Split | FPS | Lokales Full | FPS | Globales Full | FPS | R_h | R_g |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| MobileNetV3-L | Native DeepX/b135 | 1552 | DeepX | 1469 | DeepX | 1469 | 1.06 | 1.06 |
| RegNet-X | Native H10/b123 | 1367 | TRT (H10) | 316 | DeepX | 538 | 4.33 | 2.54 |
| ResNet-50 | Native H10/b095 | 1100 | TRT (H10) | 522 | DeepX | 656 | 2.11 | 1.68 |
| YOLO11l | Generic DeepX/b511 | 69 | DeepX | 63 | DeepX | 63 | 1.10 | 1.10 |
| YOLO26m | Native H10/b043 | 110 | TRT (H10) | 84 | TRT (H8) | 85 | 1.31 | 1.30 |
| YOLO26s | Native H8/b021 | 187 | TRT (H8) | 151 | TRT (DeepX) | 152 | 1.24 | 1.23 |
| YOLOv7 | Native H8/b066 | 113 | TRT (H8) | 53 | DeepX | 83 | 2.13 | 1.35 |
