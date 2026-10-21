# Erfasste Systemeinstellungen

Erfasste System- und Lastmetadaten. Die YOLOv7-Plattformbeobachtungen beschreiben dessen Systemvergleich. Andere Konfigurationen behalten ihre eigenen erfassten Einstellungen.

| Merkmal | Erfasste Einstellung | Geltungsbereich |
| --- | --- | --- |
| Durchsatzmessung | Drei Wiederholungen mit je 1,000 abgeschlossenen Aufgaben | 204 Split- und 42 Full-Konfigurationen. YOLOv7 kombiniert 27 neue Split- mit 18 erhaltenen Full-Wiederholungen |
| Batch und Generic-Warteschlangen | Batch 1. Zwei Worker. Warteschlangentiefe 2. 100 Aufwärmaufgaben. Wiederholung derselben vorbereiteten Eingabe | Neun gezielt erfasste Ausführungspfade, nicht alle 204 Splits |
| Native-Warteschlangen | Warteschlangentiefe 3. 100 Aufwärmaufgaben. H10-Pfade erfassen zusätzlich 8 gleichzeitig laufende Präfixanfragen | Dieselben neun gezielt erfassten Ausführungspfade. Die Laufzeitorganisation bleibt fallspezifisch |
| Räumliche Eingabegrößen | ImageNet-Validierung 224×224 und COCO-2017-Validierung 640×640 | Datensatzidentitäten und verfügbare Vorverarbeitungsverträge, unten beschrieben |
| Orin-Konfiguration | NX 16 GB. L4T 36.4.7. Übereinstimmende aktive MAXN_SUPER-Definition | YOLOv7-Systemvergleich |
| Takt- und Link-Beobachtungen | CPU 1984 MHz. GPU 1173 MHz. Keine beobachteten OC-Zähleranstiege. PCIe-Momentaufnahmen des Beschleunigers: 8.0 GT/s ×4 | YOLOv7-Lastproben mit etwa 1 Hz und separate Link-Momentaufnahmen. EMC nicht erfasst |
| TensorRT-Full-Kompilierung | Gleiches Modell, FP16-Option, statische FLOAT-Ein-/Ausgabeformen und Workspace-Einstellung | YOLOv7-Full-Vergleich. Serialisierte Engines und interne Taktiken müssen nicht identisch sein |
| DC-Energiegrenze | Kalibrierte Eingangsenergie des Gesamtsystems. Kein Leerlaufabzug im Hauptvergleich | 231 Fälle / 693 Wiederholungen über sechs Modelle. Kalibrierungsdetails in der separaten historischen Energiestudie |
