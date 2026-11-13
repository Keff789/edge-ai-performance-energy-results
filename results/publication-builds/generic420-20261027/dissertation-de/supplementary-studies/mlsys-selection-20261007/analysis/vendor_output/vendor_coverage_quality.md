# Historische Hersteller-Machbarkeit und Qualität

Die historische Abdeckung umfasst 588 Datensätze, einschließlich Full- und Kontrollzeilen. Die 420 geplanten heterogenen Basis-Splits sind von zusätzlich aufgenommenen Native-Fällen getrennt. Native schließt Suffixe mit part2_input_count != 1 aus. Qualitätsdatensätze und abgeschlossene Runner-Ausführungen bilden unterschiedliche Grundgesamtheiten. Sieben doppelte zugehörige TensorRT-Full-Konfigurationen sind aus den 42 eindeutigen Full-Qualitätsdatensätzen ausgeschlossen.

| System | Geplante Basis-Splits | Generic abgeschlossen | Kompilierung fehlgeschlagen | Durch Regeln ausgeschlossen | Native-Ausschlüsse wegen mehrerer Eingaben | Native-Basis abgeschlossen | Zusätzliche Native abgeschlossen | Split-Qualität referenznah / gesamt | Full-Qualität referenznah / eindeutig gesamt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H8 | 140 | 108 | 20 | 12 | 76 | 64 | 4 | 95 / 112 | 2 / 7 |
| H10 | 140 | 111 | 17 | 12 | 76 | 64 | 4 | 103 / 115 | 3 / 7 |
| DeepX | 140 | 140 | 0 | 0 | 76 | 64 | 4 | 143 / 144 | 7 / 7 |
| TensorRT-Kontrolle | 140 | 140 | 0 | 0 | 0 | 0 | 0 | 140 / 140 | 21 / 21 |
