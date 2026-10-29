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

## Aktueller RQ2-/RQ3-Publikationsstand

Die korrigierte Publikationsausgabe verwendet beide geprüften Studien. Die folgenden normalen Befehle erwarten neue oder leere Ausgabeverzeichnisse:

```sh
python -I -B scripts/split-inference/reproduce.py \
  --publication mlsys-r30 --languages en de \
  --rq2-study results/supplementary-studies/rq2-native-scope-20261027 \
  --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027 \
  --output results/publication-builds/generic420-20261027/paper --verify
python -I -B scripts/dissertation/reproduce.py \
  --source results/publication-builds/generic420-20261027/paper \
  --rq2-study results/supplementary-studies/rq2-native-scope-20261027 \
  --generic420-study results/supplementary-studies/rq3-generic420-detector-corrected-20261027 \
  --output results/publication-builds/generic420-20261027/dissertation-de --verify
python -I -B scripts/dissertation/finalize_generic420_publication.py
```

Der letzte Schritt erzeugt den englischen Dissertation-Quellenindex mit Prüfsummen und den Integrationsnachweis. Er verwendet die vorhandenen englischen Grafiken und Tabellen. Er prüft die unveränderten R22-Zahlen, beide b066-Layouts, die aktuellen RQ2-Exporte und die Übersetzungsabdeckung. Das historische R22-Nachweisprotokoll bleibt als relativer Verweis auf seine unveränderte Repository-Datei erhalten. Der Schritt führt keine Messung oder neue wissenschaftliche Berechnung aus und kann auf einer abgeschlossenen Ausgabe erneut ausgeführt werden.

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

## Final-thesis profiles (English and German)

The English thesis export uses the final 451-configuration deployment dataset,
187 quality-admissible Native/Generic pairs, and the 331-cut broader Generic
study. It does not replace the independent historical confirmation study.

```sh
python3 scripts/dissertation/export_thesis_selection.py \
  --output local-output/thesis-en --figure-profile dissertation
python3 scripts/dissertation/export_frozen_thesis_figures.py \
  --output local-output/thesis-en-fixed
```

The first output directory must be new or empty. The first command redraws
15 current figures using the existing deployment, RQ2, staged-selection and
trade-off renderers. Fonts are approximately 9 points at the intended printed
width, matching the dissertation captions rather than enlarging the graphics.
The seven compact galleries use three vertical accelerator panels in a 4.8 by
5.8 inch canvas, with one shared quality scale per model. Main selection plots
are 4.65 inches wide; the workflow and YOLOv7 case use 4.9 inches. Insert the
PDFs at their natural width to retain the intended font size.

The staged workflow illustrates YOLO11l's 615 graph boundaries, followed by
five Generic and two Native tests. It is not a measured 615-cut campaign.
The budget graph retains one- and two-Native-test curves. The redundant
classifier/detector graph-shortlist plot is omitted from this thesis export;
its numerical comparison remains in the tables. The quality table lists CPU,
Full and Split quality plus the Split-minus-Full difference; CPU-relative
quality losses are not duplicated as extra columns.

`tables/` contains 10 LaTeX files from full-precision published records or their
current official exports. `MANIFEST.json` records input, source and output
hashes. `VALIDATION.json` checks 116 unchanged CSV/JSON payloads, 60 staged
aggregate comparisons and 3,780 combination-policy-budget cases. All seven
gallery payloads retain their exact 450 measured points and 34 same-setup
Pareto points. No fitting, quality reclassification or hardware measurement
is performed. The canonical English exports are in
`publications/dissertation/thesis-v56/en/current-selection/`.

The second command copies 13 fixed English publication exports: eleven
energy plots, the DAG-cut schematic and the independent stage-cost plot.
These exact v48 layouts came from the author's English v56 source archive.
They are preserved as PDFs, not represented as newly data-driven renderings.
Their source archive, original paths, hashes and related numerical evidence
are documented in `ENERGY_SOURCE_MANIFEST.json` and
`METHODS_SOURCE_MANIFEST.json` under
`publications/dissertation/thesis-v56/en/`. The optional `--project` argument
installs these checked PDFs at their existing LaTeX paths. The drawing bundle
supplied by the author remains the source for the other conceptual diagrams.

Copy only the PDFs and required TeX files into the LaTeX project. The temporary
`render_work/` folder is not needed for compilation. The default paper geometry
remains unchanged; the modified publication renderer was checked against the
previous renderer with 41 byte-identical paper outputs.

### German final-thesis profile

```sh
python3 scripts/dissertation/export_thesis_selection.py \
  --language de --figures-only --figure-profile dissertation \
  --output local-output/thesis-de
python3 scripts/dissertation/export_frozen_thesis_figures.py \
  --language de --output local-output/thesis-de-fixed
```

The current German profile uses the same 15 renderers and published inputs as
the English profile. `--figures-only` keeps independently maintained thesis
tables out of this figure export. The static label catalog and declared dynamic
rules run before layout. Deliberate line breaks survive translation; annotation
placement measures the displayed German text. Decimal commas affect numeric
labels only, not model names or JSON/CSV data. Generic, Native, Full, Bytes and
Weighted remain method names. Unknown labels fail the export.

`TRANSLATION_AUDIT.json`, `VALIDATION.json` and `MANIFEST.json` record coverage,
exactly unchanged scientific payloads, source hashes and output hashes. The
German staged workflow wraps longer labels inside its original canvas. The
English profile retains its existing outputs; all 15 PDF checksums were verified
against the previously published English thesis selection after these changes.

The frozen export accepts `--language de` and verifies the existing German
counterparts against their source manifest. PyMuPDF is needed for its checks of
page dimensions, drawing commands and numerical labels. The German energy
figures with compressed translated labels are recreated from the same published
summary/curve CSVs by `render_thesis_energy_de.py`; their typography is checked
at the original LaTeX inclusion widths. This is presentation only: no raw
signal processing, new measurement, fitting or replacement cohort is used.

## Supplied DrawIO diagrams

The English DrawIO-7 bundle is exported separately with
`scripts/dissertation/drawio/update_drawio_thesis.py`. Its
[README](drawio/README.md) documents the input bundle, typography and two
factual corrections. Only PDF exports enter the LaTeX project.
