# Aufgabenausgaben und Abschlussarbeiten

Erforderliche Aufgabenausgaben und Abschlussarbeiten. Generic, Native und Full verwenden denselben modellspezifischen Vergleichsvertrag. Der kompilierte Graph bestimmt, ob Dekodierung und Unterdrückung im Modell oder im Host-Code stattfinden. Erforderliche Ausgabeverarbeitung und Materialisierung liegen vor dem Aufgabenabschluss.

| Modell oder Ausgabepfad | Fertiges Ergebnis | Erforderliche Verarbeitung |
| --- | --- | --- |
| MobileNet, RegNet, ResNet | Synchronisierte Klassifikatorausgaben und geordnete Top1/Top5 | Ausgabematerialisierung und Top1/Top5-Verarbeitung. |
| YOLO11l und YOLOv7 | Boxen in Originalbildkoordinaten, Wahrscheinlichkeiten und Klassenindizes | Modellspezifische Dekodierung und klassenabhängige NMS, soweit nicht bereits im Modell ausgeführt, anschließend Materialisierung. |
| YOLO26m/s, Rohkopf-Pfade | Dasselbe Detektionsdatenformat | Rohköpfe dekodieren und erforderliche NMS ausführen. Dies umfasst Hailo-Full-Pfade. |
| YOLO26m/s, integrierte Ausgaben | Dasselbe Detektionsdatenformat | Integrierte Detektionen filtern und normalisieren, Letterboxing rückgängig machen und Ausgaben materialisieren. Gültige integrierte Ausgaben erhalten keinen zusätzlichen NMS-Durchlauf. |
