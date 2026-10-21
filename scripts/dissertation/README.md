# Deutsche Grafiken und Tabellen für die Dissertation

Der Export erzeugt die Darstellungen der Split-Auswertung zusätzlich auf Deutsch. Er umfasst **58 Grafikfamilien** aus der vollständigen Split-Auswertung, den Publikationsprofilen R22 und R30 sowie den ergänzenden Split-Studien. Dazu kommen die verfügbaren Tabellen als LaTeX und Markdown. Die [veröffentlichte deutsche Sammlung](../../publications/dissertation/de/README.md) bietet einen Index nach Auswertung und Studie.

Die Grafiken werden mit den vorhandenen Renderern neu als PDF, SVG und PNG erzeugt. Achsen, Legenden, Anmerkungen und Tabellenbeschriftungen verwenden feste deutsche Übersetzungskataloge. Modell-, Geräte- und Methodennamen bleiben erhalten. Das gilt insbesondere für Generic, Native, Full, Bytes und Weighted. Die englischen CSV-/JSON-Dateien bleiben die gemeinsame Datenquelle. Messwerte, mathematische Ausdrücke, Konfigurationskennungen und die wissenschaftliche Zahlenschreibweise werden nicht übersetzt.

## Einrichtung auf twix

Alle Befehle werden im Wurzelverzeichnis des Ergebnis-Repositories ausgeführt. Python 3.12 und die Abhängigkeiten des aktuellen Publikationsprofils genügen. Eine eigene Umgebung kann im Benutzerverzeichnis oder neben dem Repository angelegt werden:

```sh
python3.12 -m venv ../dissertation-venv
../dissertation-venv/bin/python -m pip install \
  -r scripts/split-inference/requirements-r30.txt
```

Die Anforderungen sind in [requirements-r30.txt](../split-inference/requirements-r30.txt) festgehalten. Root-Rechte oder `sudo` sind nicht erforderlich. Nach der Installation benötigt die Erzeugung weder Netzwerkzugriff noch Beschleunigerhardware, Modelle oder Bilddatensätze.

## Deutsche Ausgabe aus den vorhandenen Ergebnissen

```sh
../dissertation-venv/bin/python -I -B scripts/dissertation/reproduce.py \
  --output ../dissertation-de --verify
```

Das Ausgabeverzeichnis muss leer sein oder noch nicht existieren. Standardmäßig verwendet der Export `results/split-inference` und die im Repository abgelegten Zusatzstudien. `--source` kann auf die Ausgabe eines bereits abgeschlossenen englischen Split-Auswertelaufs zeigen.

Für Tabellen ohne Grafikrendering:

```sh
../dissertation-venv/bin/python -I -B scripts/dissertation/reproduce.py \
  --output ../dissertation-de-tabellen --numeric-only --verify
```

`--no-supplementary` beschränkt den Export auf die breite Split-Auswertung und die vorhandenen Publikationsprofile. Die datierten Zusatzstudien werden dann ausgelassen.

## Englische und deutsche Ausgabe gemeinsam erzeugen

Die zentrale Auswertung unterstützt zusätzlich `--languages en de`:

```sh
../dissertation-venv/bin/python -I -B scripts/split-inference/reproduce.py \
  --publication mlsys-r30 --languages en de \
  --output ../split-auswertung-zweisprachig --verify
```

Die englische Ausgabe behält ihre bisherige Struktur. Der zusätzliche Ordner `de/` enthält die deutsche Sammlung. Ohne `--languages` bleibt die bisherige englische Ausgabe unverändert. `--numeric-only` kann auch bei diesem Aufruf verwendet werden.

## Ordnung der Dateien

| Ordner in der deutschen Ausgabe | Inhalt |
|---|---|
| `split-inference/` | Breite Auswertung aller verfügbaren Split- und Full-Konfigurationen |
| `mlsys-r30/` | Aktuelle Paper-Darstellungen einschließlich Weighted und beider YOLOv7-Layouts |
| `mlsys-r22/` | Eingefrorene frühere Publikationsdarstellung |
| `supplementary-studies/<Studie>/` | Ergänzende Auswertungen mit ihren jeweiligen Daten und Messreihen |

Jeder Bereich besitzt einen eigenen Index mit Links zu Grafiken und Tabellen. Die Ordnerstruktur trennt aktuelle Ergebnisse, ältere Publikationsstände und eigenständige Zusatzstudien. Ähnliche Modell- oder Cut-Namen führen nicht dazu, dass unterschiedliche Messreihen zusammengefasst werden.

PDF und SVG eignen sich für die Dissertation. PNG dient als Vorschau. Die TeX-Tabellen lassen sich mit `\input{...}` einbinden. Je nach Tabelle werden `booktabs`, `siunitx`, `longtable` und die in der Quelldatei genannten Pakete benötigt. Breite Tabellen sind für eine ganze Seite oder das Querformat vorgesehen. Eine vollständige Dissertation wird durch diesen Export nicht geändert.

## Übersetzung und Prüfung

Die statischen Kataloge [figures_de.json](locales/figures_de.json) und [tables_de.json](locales/tables_de.json) enthalten die verwendeten Formulierungen. Die Übersetzung der Grafiktexte erfolgt vor der Layoutberechnung. Die aktuelle Generic-/Native-Illustration verwendet ihren vorhandenen Vektorentwurf mit deutschen Beschriftungen.

`ASSET_MANIFEST.json` verbindet jede deutsche Datei mit Quelle, Generator und Prüfsummen. `TRANSLATION_AUDIT.json` dokumentiert die erkannten Beschriftungen. Der normale Export prüft die Übersetzungsabdeckung und die unveränderten numerischen Daten. Fehlende Beschriftungen werden als Fehler gemeldet. Der zentrale zweisprachige Aufruf prüft zuerst die englische Auswertung und erzeugt danach die deutsche Darstellung.

Für neue Beschriftungen werden die Kataloge ergänzt und die Ausgabe erneut erzeugt. Die englischen Quelldaten und die bestehenden englischen Ergebnisse bleiben dabei unverändert.

Der Umfang dieses Exports ist **Split-Inferenz einschließlich der ergänzenden Split-Studien**. Die Energiemessung besitzt ein [separates Auswertetool](../energy-measurement/README.md) und ist nicht Bestandteil dieses Exports.
