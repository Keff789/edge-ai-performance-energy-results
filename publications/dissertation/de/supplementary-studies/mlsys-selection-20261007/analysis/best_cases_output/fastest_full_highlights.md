# Größte Gewinne gegenüber dem schnellsten Full

Der schnellste Full wird vor der Qualitätsfilterung anhand des Native-Durchsatzes ausgewählt. Dieselbe Full-Identität liefert die Energieangaben, soweit vorhanden. Durchsatz und Energie verwenden getrennte Messfenster.

| Modell | System | Cut | Fest gewählter schnellster Full | Full-FPS | Split-FPS | Beschleunigung | Split mJ/Aufgabe | Energiegewinn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet_v3_large | H10 | b074 | tensorrt_full | 778 | 1168 | 1.502 | 19.7 | 1.359 |
| mobilenet_v3_large | H10 | b068 | tensorrt_full | 778 | 1121 | 1.441 | 20.4 | 1.315 |
| regnet_x_1_6gf | H10 | b123 | tensorrt_full | 317 | 1521 | 4.803 | 15.6 | 4.621 |
| regnet_x_1_6gf | H10 | b132 | tensorrt_full | 317 | 1175 | 3.711 | 16.9 | 4.272 |
| resnet50 | H10 | b095 | tensorrt_full | 525 | 1060 | 2.017 | 29.3 | 1.831 |
| resnet50 | H10 | b088 | tensorrt_full | 525 | 1057 | 2.013 | 30.3 | 1.772 |
| yolo11l | H8 | b120 | tensorrt_full | 37 | 44 | 1.168 | 549.0 | 1.289 |
| yolo11l | H8 | b062 | tensorrt_full | 37 | 43 | 1.159 | 573.6 | 1.233 |
| yolo26m | H10 | b043 | tensorrt_full | 83 | 104 | 1.252 | 326.8 | 1.174 |
| yolo26m | H10 | b038 | tensorrt_full | 83 | 102 | 1.231 | 331.6 | 1.157 |
| yolo26s | H8 | b021 | tensorrt_full | 147 | 189 | 1.285 | 155.8 | 1.284 |
| yolo26s | H10 | b021 | tensorrt_full | 146 | 167 | 1.143 | 176.0 | 1.081 |
| yolov7_paper | H8 | b066 | tensorrt_full | 52 | 112 | 2.172 | NA | NA |
| yolov7_paper | H10 | b044 | tensorrt_full | 51 | 65 | 1.253 | NA | NA |
