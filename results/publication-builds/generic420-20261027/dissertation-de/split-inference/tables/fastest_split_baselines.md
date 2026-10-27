# Gewählter schnellster Split: lokale und globale Full-Referenzen

Derselbe in Tabelle 3 gewählte Split, verglichen mit dem schnellsten Full auf seinem physischen Host und dem global schnellsten Full. Diese Tabelle wählt nicht erneut den größten relativen Gewinn. R_host und R_global nutzen die ausdrücklich genannten Full-Nenner. Die Auswahl nutzt ungerundete gemessene FPS der Messreihe über alle Systeme und Native/Generic-Splits. Exakte Gleichstände werden durch aufsteigende UID aufgelöst. Die Energie ist der Mittelwert der kalibrierten, den Host einschließenden J/Bild jeder genau nach FPS gewählten UID und wird als mJ/Bild dargestellt. Energie und Qualität schließen keine Konfiguration von der FPS-Auswahl aus. NA bezeichnet fehlende Kandidaten oder Metriken, deren Gründe und vollständige Originalaufzeichnungen in CSV/JSON stehen. Diese rückblickenden Ausführungsvergleiche bedeuten weder gleiche Qualität oder zeitlich gleiche Endpunkte noch einen isolierten Split-Effekt oder statistisch signifikante Unterschiede.

| Modell | Gewählter Split | Split-FPS | Lokal schnellstes Full | Lokale Full-FPS | Global schnellstes Full | Globale Full-FPS | R_host | R_global |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| MobileNetV3-L | Native DeepX/b135 | 1552 | DeepX (DeepX host) | 1469 | DeepX (DeepX host) | 1469 | 1.06 | 1.06 |
| RegNet-X 1.6GF | Native H10/b123 | 1367 | TRT (H10 host) | 316 | DeepX (DeepX host) | 538 | 4.33 | 2.54 |
| ResNet-50 | Native H10/b095 | 1100 | TRT (H10 host) | 522 | DeepX (DeepX host) | 656 | 2.11 | 1.68 |
| YOLO11l | Generic DeepX/b511 | 69 | DeepX (DeepX host) | 63 | DeepX (DeepX host) | 63 | 1.10 | 1.10 |
| YOLO26m | Native H10/b043 | 110 | TRT (H10 host) | 84 | TRT (H8 host) | 85 | 1.31 | 1.30 |
| YOLO26s | Native H8/b021 | 187 | TRT (H8 host) | 151 | TRT (DeepX host) | 152 | 1.24 | 1.23 |
| YOLOv7 | Native H8/b066 | 113 | TRT (H8 host) | 53 | DeepX (DeepX host) | 83 | 2.13 | 1.35 |
