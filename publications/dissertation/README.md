# Grafiken und Tabellen für die Dissertation

Die Dissertation verwendet denselben aktuellen Split-Datensatz wie das Paper. Die Ergebnisse gliedern sich in den Nutzen der Aufteilung, die Auswahl mit Generic und die Vorauswahl mit Graph-Scores. Die deutsche und englische Ausgabe verwenden gemeinsame Zahlen und dieselbe grafische Gestaltung.

| Bereich | Dateien |
|---|---|
| Deutsche Split-Grafiken und Tabellen | [Aktuelle Sammlung](../../results/publication-builds/generic420-20261027/dissertation-de/README.md) |
| Englische Split-Grafiken und Tabellen | [Aktuelle Sammlung](../../results/publication-builds/generic420-20261027/dissertation-en/README.md) |
| Deutscher Graph-Score-Vergleich | [Grafiken und Tabellen](../../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/artifacts/de/) |
| Englischer Graph-Score-Vergleich | [Grafiken und Tabellen](../../results/supplementary-studies/rq3-generic420-detector-corrected-20261027/artifacts/en/) |
| Auswahl mit Graph, Generic und Native | [Deutsch](../../results/supplementary-studies/staged-selection/artifacts/de/) · [Englisch](../../results/supplementary-studies/staged-selection/artifacts/en/) |
| Energiemessung | [Kalibrierung, Messvergleiche und Spektralanalyse](../../results/energy-measurement/README.md) |

PDF und SVG sind für Abbildungen vorgesehen, LaTeX für Tabellen. PNG und Markdown dienen der Vorschau. CSV und JSON enthalten die zugrunde liegenden Zahlen. Die YOLOv7-Fallstudie steht zusätzlich in einer breiten und einer einspaltigen Fassung bereit.

Die [Auswertung der Auswahlkette](../../results/supplementary-studies/staged-selection/README.md) untersucht zuerst eine Vorauswahl nach Grenztensorgröße, dann Generic-Tests und schließlich zwei Native-Tests. Mit höchstens fünf Generic-Tests werden im Mittel 96,20 Prozent des besten gemessenen Native-Durchsatzes erreicht. Mit zwölf sind es 99,65 Prozent. Die Zahl der exakt gefundenen Gewinner wird getrennt angegeben.

## Aktuelle Split-Auswertung erzeugen

Im Wurzelverzeichnis des Repositorys ausführen:

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Die [Installationshinweise](../../scripts/README.md) beschreiben die Python-Abhängigkeiten. Die Erzeugung benötigt keine administrativen Rechte und verwendet vorhandene Messdaten. Der Aufruf erzeugt die aktuelle englische und deutsche Ausgabe gemeinsam.

## Weitere Ergebnisse für die Dissertation

Die [ergänzenden Analysen](../../results/supplementary-studies/README.md) enthalten unter anderem Stufenkosten und zusätzliche Methodenprüfungen. Die [Hailo-10H-Formatmessungen](../../results/split-inference/microbenchmarks/README.md), [Messreihen zur Energieerfassung](../../results/energy-measurement/galleries/direct-sweeps.md) und [Spektralanalysen](../../results/energy-measurement/galleries/spectra-jetson.md) können unabhängig davon verwendet werden.

Frühere Fassungen und Entwicklungsversuche sind im [Forschungsarchiv](../../docs/archival_studies.md) verzeichnet. Die dortigen Ergebnisse behalten ihren jeweiligen Untersuchungsumfang. Die aktuelle Split-Auswertung ist über die oben verlinkten Sammlungen zugänglich.
