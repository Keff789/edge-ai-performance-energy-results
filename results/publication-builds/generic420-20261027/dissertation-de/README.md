# Deutsche Grafiken und Tabellen für die Dissertation

Die aktuelle Studie untersucht den Nutzen der Split-Inferenz, die Auswahl mit Generic und die Vorauswahl anhand des Modellgraphen. Die deutschen Darstellungen verwenden dieselben Messwerte wie die englischen Ausgaben.

- [Split-Vergleiche und Generic–Native-Auswahl](mlsys-r30/README.md)
- [Graph-basierte Vorauswahl](rq3-generic420/de/)

## Reproduktion

```sh
python3 scripts/reproduce_current.py --output local-output/current --languages en de
```

Ein leeres Ausgabeverzeichnis verwenden. Die Prüfung der Zahlen und Übersetzungen ist Bestandteil des Aufrufs. PDF/SVG und LaTeX sind für die Dissertation vorgesehen, PNG und Markdown für die Vorschau.

Der [vollständige Dateikatalog](ASSET_CATALOG.md) enthält zusätzliche Darstellungen. `ASSET_MANIFEST.json` verknüpft jede Ausgabe mit ihren Quelldaten.


[Auswahl mit Graph, Generic und Native](../staged-selection/artifacts/de/): deutsche Budgetgrafiken und Tabellen aus denselben Messpaaren.
