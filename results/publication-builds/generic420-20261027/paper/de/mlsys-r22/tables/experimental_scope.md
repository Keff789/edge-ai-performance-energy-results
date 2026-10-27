# Versuchsaufbau

Plattformen, Datensatz und Messprotokoll des Ausführungsvergleichs.

| Aspekt | Umfang |
| --- | --- |
| Plattformen | Drei Orin-NX-Hosts mit H8, H10 oder DX. |
| Modelle | MobileNetV3-L, RegNet-X 1.6GF, ResNet-50, YOLO11l, YOLO26m, YOLO26s, YOLOv7. |
| Abdeckung | 204 gepaarte Native/Generic-Cuts und 42 host-spezifische Full-Alternativen. |
| Eingaben | ImageNet-Validierung mit 224×224 und COCO-2017-Validierung mit 640×640. |
| Präzision | TensorRT-Full-Kompilierungen aktivieren FP16. Split-Übergänge nutzen float32-Layoutumwandlung oder uint8-Dequantisierung nach FP16. Die Beschleunigerpräzision folgt dem kompilierten Artefakt. |
| Durchsatz | Drei unabhängige Prozessläufe mit je 1,000 abgeschlossenen Aufgaben. Verfügbare Pfadaufzeichnungen nennen Batch 1 und 100 vollständig beendete Aufwärmaufgaben. |
| Energie | Eingangsshunt mit INA225-Erfassung. Drei 60-s-Wiederholungen am kalibrierten DC-Systemeingang, ohne Abzug der Leerlaufleistung. |
| Qualität | Gemeinsame Auswertesätze mit 5,000 Bildern, über Datensatz-Hashes zugeordnet. 1,000 gepaarte Bootstrap-Wiederholungen. |
