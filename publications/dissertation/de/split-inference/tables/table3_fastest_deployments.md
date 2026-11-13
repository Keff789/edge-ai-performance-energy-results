# Tabelle 3: Global schnellste gemessene Konfigurationen

Global schnellstes gemessenes Full gegenüber global schnellstem gemessenen Split, eine Zeile je Modell. R_global = Split-FPS / globale Full-FPS. delta_E_global (%) = 100 (Split-Energie / globale Full-Energie - 1). Die Auswahl nutzt ungerundete gemessene FPS der Messreihe über alle Systeme und Native/Generic-Splits. Exakte Gleichstände werden durch aufsteigende UID aufgelöst. Die Energie ist der Mittelwert der kalibrierten, den Host einschließenden J/Bild jeder genau nach FPS gewählten UID und wird als mJ/Bild dargestellt. Energie und Qualität schließen keine Konfiguration von der FPS-Auswahl aus. NA bezeichnet fehlende Kandidaten oder Metriken, deren Gründe und vollständige Originalaufzeichnungen in CSV/JSON stehen. Diese rückblickenden Ausführungsvergleiche bedeuten weder gleiche Qualität oder zeitlich gleiche Endpunkte noch einen isolierten Split-Effekt oder statistisch signifikante Unterschiede.

| Modell | Schnellstes Full (Backend, Host) | Full-FPS | Full mJ/Bild | Schnellster Split (Runner, System/Cut) | Split-FPS | Split mJ/Bild | R_global | delta_E_global (%) |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| MobileNetV3-L | DeepX (DeepX host) | 1469 | 12.01 | Native DeepX/b135 | 1552 | 12.59 | 1.06 | 4.8 |
| RegNet-X 1.6GF | DeepX (DeepX host) | 538 | 31.54 | Native H10/b123 | 1367 | 15.83 | 2.54 | -49.8 |
| ResNet-50 | DeepX (DeepX host) | 656 | 27.65 | Native H10/b095 | 1100 | 29.46 | 1.68 | 6.6 |
| YOLO11l | DeepX (DeepX host) | 63 | 315.23 | Native H10/b120 | 53 | 555.75 | 0.84 | 76.3 |
| YOLO26m | TRT (H8 host) | 85 | 400.03 | Native H10/b043 | 110 | 319.65 | 1.30 | -20.1 |
| YOLO26s | TRT (DeepX host) | 152 | 187.80 | Native H8/b021 | 187 | 157.65 | 1.23 | -16.1 |
| YOLOv7 | DeepX (DeepX host) | 83 | 269.44 | Native H8/b066 | 113 | 330.14 | 1.35 | 22.5 |
