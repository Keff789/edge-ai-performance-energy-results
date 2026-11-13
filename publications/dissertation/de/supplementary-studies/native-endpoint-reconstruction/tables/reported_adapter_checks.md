| Fall | P2 / s | Abschlüsse / s | Prüfungen |
| --- | --- | --- | --- |
| YOLOv7 Hailo-8/TRT b066 | 96 | 96 | 32 |
| YOLO26s Hailo-8/TRT b038 | 153 | 153 | 32 |
| YOLO11l Full-ORT-Wiedergabe | NA | NA | 16 |
| Hailo-10H YOLO26s Producer | NA | 35 | 300 |
| DEEPX YOLO26s Producer | NA | 40 | 300 |

Berichtete Zusammenfassungen aus dem Manuskript. YOLOv7 und YOLO26s validieren 32/32 Pipeline-Bilder. YOLO11l validiert 16/16 Bilder durch ORT-Wiedergabe ohne Beschleuniger-Zeitmessung. Die letzten beiden Zeilen zählen 300 Arbeitseinheiten des Producers. Diese sind keine vollständigen Detektoraufgaben. Quellendpunkt und Validierungsstatus bleiben in der CSV erhalten.
