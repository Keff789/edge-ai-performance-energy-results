# Deutsche Abbildungen der finalen Dissertation v56

Diese Sammlung enthält die 28 aus dem Results-Repository übernommenen
Abbildungen der deutschen Dissertation. Die englischen Veröffentlichungen
und alle Messdaten bleiben unverändert.

| Teil | Umfang | Nachweis |
| --- | --- | --- |
| `current-selection/figures/` | 15 aktuelle Darstellungen | `current-selection/VALIDATION.json`, `TRANSLATION_AUDIT.json`, `MANIFEST.json` |
| `figures/energy/` | 9 neu gezeichnete Energieabbildungen und 2 unveränderte deutsche Exporte | `figures/energy/ENERGY_DE_REGENERATION.json`, `FROZEN_EXPORT.json` |
| `figures/methods/` | 2 unveränderte deutsche Exporte | `FROZEN_EXPORT.json` |

`THESIS_IMPORT.json` ordnet jede Datei ihrem LaTeX-Pfad, Quellbefehl, SHA-256-Wert
und der tatsächlichen Schriftgröße bei der vorgesehenen Einbindung zu.
Die JSON-Dateien neben den neun neu gezeichneten Energieabbildungen enthalten
die unveränderten veröffentlichten Quellzeilen und die dargestellten Werte.

Die aktuellen Darstellungen bewahren 450 Messpunkte und 34 Pareto-Punkte der
sieben Modellgalerien. 116 CSV-/JSON-Payloads bleiben unverändert. Die erneute
englische Ausgabe aller 15 aktuellen PDFs war byteidentisch zum veröffentlichten
Stand; siehe `current-selection/EN_REGRESSION_CHECK.json`.

Die neun Energieabbildungen werden aus den vorhandenen Tabellen und
Spektralkurven gezeichnet. Eine unabhängige Prüfung vergleicht 20.758
Koordinatenwerte mit den bisherigen englischen Abbildungen; die maximale
Abweichung beträgt 0,00003113 PDF-Punkte bei einer Toleranz von 0,002 Punkten.
Die englischen PDFs dienen ausschließlich der Prüfung, niemals als Datenquelle
zum Zeichnen. Insbesondere stammen die zwölf Kurven des Spektrenvergleichs
unverändert aus den veröffentlichten Tek-Power-Excess-Dateien. Es werden keine
Messung, Spektralschätzung, Anpassung oder statistische Neuauswertung ausgeführt.

Die Schrift der neun überarbeiteten Energieabbildungen beträgt bei den
bestehenden Einbindungsbreiten mindestens 8,711 bis 8,991 Punkte. Die anderen
vier festen Abbildungen werden byteidentisch aus den geprüften deutschen
Veröffentlichungen kopiert. Mathematische Indizes sind im Schriftbericht
separat erkennbar.

## Reproduktion

Im Repository-Wurzelverzeichnis, jeweils mit einem leeren Zielverzeichnis:

```sh
python scripts/dissertation/export_thesis_selection.py \
  --language de --figures-only --figure-profile dissertation \
  --output local-output/thesis-de-current
python scripts/dissertation/export_frozen_thesis_figures.py \
  --language de --output local-output/thesis-de-fixed
```

Die Exporte erzeugen zusätzlich SVG-/PNG-Vorschauen. Hier werden nur die für
die Dissertation benötigten PDFs und ihre maschinenlesbaren Nachweise abgelegt.
