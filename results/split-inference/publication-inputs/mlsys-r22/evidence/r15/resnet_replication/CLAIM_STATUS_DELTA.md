# Zusätzlicher Aussageumfang der vollständigen ResNet-Serie

Grundlage sind ausschließlich 40 neue Prozesse in fünf gemeinsamen randomisierten Acht-Zellen-Blöcken. Alle Angaben beziehen sich auf ResNet-50/H10, b002 und b095, die gebundenen aktuellen Laufzeitketten und die vorab festgeschriebene Auswertung.

| Aussage | Neuer Status und Beleg |
|---|---|
| Generic und Native bevorzugen produktiv verschiedene Cuts | Für dieses Paar gestützt: Generic r(b095/b002) = 0,6057 [0,6033; 0,6082], Native 2,0597 [2,0281; 2,0919]. Beide Intervalle liegen auf entgegengesetzten Seiten von 1. |
| Native ändert durch höchstens eine ausstehende Aufgabe seine Rangfolge | In der neuen Serie erneut gestützt: r wechselt von 2,0597 auf 0,8290 [0,8240; 0,8339], also von b095 zu b002. Die alte 20-Prozess-Serie bleibt separat. |
| Generic ändert durch die Intervention ebenfalls sein Cut-Verhältnis | Gestützt: r steigt von 0,6057 auf 0,8359 [0,8276; 0,8442]. b002 bleibt bevorzugt; keine Generic-Rangumkehr. |
| Vollständige Scheduling-by-Runtime-Interaktion bei ResNet | Neu mit frischen Generic- und Native-Prozessen gemeinsam geprüft: I = 3,4288 [3,3532; 3,5061]. Die alte Native-only-Serie konnte diesen Kontrast nicht identifizieren. |
| Richtung der RegNet-Interaktion überträgt sich | Für dieses zweite ausgewählte Cut-Paar gestützt: I und sein nominales Intervall liegen über 1. Gleiche Effektstärke wurde nicht getestet. |
| Beide Laufzeitketten haben unter der Intervention dieselbe Präferenz | Für ResNet gestützt: beide bevorzugen b002. Dies ist nicht dieselbe verbleibende Präferenz wie bei RegNet, wo beide b123 leicht bevorzugten. |

Alle Intervalle sind nominale 95-%-t-Intervalle über fünf Prozessblöcke, keine simultanen Garantien. I ist ein Verhältnis von Cut-Verhältnissen und kein einzelner Cut-Speedup. Vollständige Blockwerte und Rohbindungen: `results/replication_analysis_blocks.csv`, `results/replication_analysis_cells.csv`, `results/final_progress.json`.

Offen beziehungsweise außerhalb des Anspruchs bleiben:

- Allgemeine Verbreitung auf unbekannten Modellen, Cuts oder Hardware: das ResNet-Paar war wegen einer bekannten Rangumkehr ausgewählt.
- Gleich große Interaktion über Modelle oder formaler Unterschied zwischen den Studien: hier nicht getestet.
- Isolierte Kopier-, Layout- oder Konvertierungskosten: Generic und Native bleiben ganze unterschiedliche Laufzeitketten.
- Neue Energieeffizienz, vollständige Suchkosten oder Übertragbarkeit auf beliebige variable Eingabeströme: nicht gemessen.
- Historische Softwarebedingungen: der Versuch bindet den eingefrorenen aktuellen Quellstand.

Unverändert bleiben der abgeschlossene Audit, die Kalibrierung, die alte RegNet-Verlängerungsentscheidung und die separat archivierte Native-only-ResNet-Serie. Der neue Befund ersetzt keine alten Rohdaten und erweitert keine alten Blöcke.
