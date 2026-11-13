# Historischer YOLOv7-Durchsatz vollständig abgeschlossener Aufgaben

Berichtete Mediane aus drei Prozesswiederholungen mit 100 Aufwärmdurchläufen und 1,000 abgeschlossenen Aufgaben je Wiederholung. Sechs Full-Alternativen wurden aus der früheren Durchsatzmessung wiederverwendet. Drei separate Full-Kontrollen sind nicht enthalten. FPS sind hier gerundet. Die CSV behält alle berichteten Nachkommastellen und Wiederholungen.

| System | Pfad | Median FPS | / Schnellstes Full | / Beschleuniger-Full | Berichtete Qualität | Energie |
|---|---|---:|---:|---:|---|---|
| H8 | Beschleuniger-Full | 31 | — | — | accuracy_loss | nicht gemessen |
| H8 | TensorRT Full | 52 | — | — | reference_close | nicht gemessen |
| H8 | Split b009 | 43 | 0.828 | 1.361 | reference_close | nicht gemessen |
| H8 | Split b044 | 48 | 0.923 | 1.519 | reference_close | nicht gemessen |
| H8 | Split b066 | 112 | 2.172 | 3.574 | reference_close | nicht gemessen |
| H10 | Beschleuniger-Full | 12 | — | — | accuracy_loss | nicht gemessen |
| H10 | TensorRT Full | 51 | — | — | reference_close | nicht gemessen |
| H10 | Split b009 | 51 | 0.998 | 4.171 | reference_close | nicht gemessen |
| H10 | Split b044 | 65 | 1.253 | 5.238 | reference_close | nicht gemessen |
| H10 | Split b066 | 53 | 1.036 | 4.332 | reference_close | nicht gemessen |
| DeepX | Beschleuniger-Full | 23 | — | — | reference_close | nicht gemessen |
| DeepX | TensorRT Full | 47 | — | — | reference_close | nicht gemessen |
| DeepX | Split b009 | 34 | 0.716 | 1.476 | reference_close | nicht gemessen |
| DeepX | Split b044 | 49 | 1.031 | 2.126 | reference_close | nicht gemessen |
| DeepX | Split b066 | 31 | 0.647 | 1.333 | reference_close | nicht gemessen |

Der schnellste technisch vergleichbare Full-Pfad wurde vor der Qualitätsfilterung ausgewählt. Kleine Verhältnisse über eins belegen keine statistische Überlegenheit. Qualitätskennzeichnungen sind aus dem Bericht übernommen und nicht unabhängig ausgewertet. Für diese Messreihe liegen keine zugehörigen Energiemessungen vor. Energie bleibt NA und wird nicht aus späteren Ergebnissen ergänzt.

Diese abschließenden Wiederholungen sind von der kurzen instrumentierten H10-Stufendiagnose getrennt. Deren ursprüngliche detaillierte CSV und Hardware-Profilierskripte sind nicht enthalten. Stufenzeiten werden hier nicht rekonstruiert.
