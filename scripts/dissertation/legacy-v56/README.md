# Historische Generatorquellen aus Dissertation v56

Diese sechs Programme bewahren frühere Generatorquellen aus
`doctor_thesis_v56_de_minimal_aktualisiert.zip`. Sie sind ein historischer
Quellbestand und gehören nicht zum aktuellen Reproduktionsablauf. Die aktuelle
Auswertung verwendet weiterhin [scripts/reproduce_current.py](../../reproduce_current.py),
die Energiemessung ihr [bestehendes Auswertetool](../../energy-measurement/README.md).

Die beiden Rankingdarstellungen werden bereits von
[plot_rankings.py](../../supplementary-studies/dissertation-development-2026/plot_rankings.py)
aus den dort hinterlegten aggregierten Eingaben erzeugt. Für diese Darstellungen
ist der bestehende Renderer vorgesehen; die beiden alten Programme hier bleiben
ausschließlich als historische Quellen erhalten.

## Herkunft und Anpassungen

Die ursprünglichen Pfade beziehen sich auf das LaTeX-Quellpaket:

| Datei hier | Ursprünglicher Pfad |
| --- | --- |
| `energie/generate_energy_results_v41.py` | `9_resources/energy_reference_v41/generate_energy_results_v41.py` |
| `energie/generate_measurement_setups_v41.py` | `9_resources/energy_reference_v41/generate_measurement_setups_v41.py` |
| `energie/generate_thesis_energy_figures_v41.py` | `9_resources/energy_reference_v41/generate_thesis_energy_figures_v41.py` |
| `evaluation/generate_phase2_ranking_audit_figure.py` | `9_resources/generated/phase2_ranking_audit/generate_phase2_ranking_audit_figure.py` |
| `evaluation/generate_static_proxy_figure.py` | `9_resources/generated/phase2_ranking_audit/generate_static_proxy_figure.py` |
| `grafiken/generate_redesigned_figures.py` | `9_resources/redesigned/scripts/generate_redesigned_figures.py` |

Angepasst wurden Projektwurzel, Eingabe- und Ausgabepfade, Aufrufoptionen und
Fehlermeldungen. Rechen- und Zeichenlogik der historischen Quellen bleibt
erhalten. Alle sechs Programme unterstützen `--help`. Sie erzeugen die damaligen
englischen Darstellungen und ersetzen keine aktuell freigegebenen deutschen
Grafiken. Die v41-Makros sind zudem ein anderer Stand als die v43-Makros des
LaTeX-Projekts.

## Isolierte historische Energieausgabe

Vom Repository-Stamm aus:

```bash
python3 scripts/dissertation/legacy-v56/energie/generate_energy_results_v41.py
python3 scripts/dissertation/legacy-v56/energie/generate_measurement_setups_v41.py
python3 scripts/dissertation/legacy-v56/energie/generate_thesis_energy_figures_v41.py
```

Die datenbasierten Programme lesen den eingefrorenen Snapshot
`results/supplementary-studies/dissertation-v56/inputs/energie/`. Standardausgaben
liegen unter `local-output/dissertation-v56-legacy/energie_v41/`: Makros in `tex/`,
PDFs und PNGs in `figures/`. `--output-dir` setzt das jeweilige Ausgabeverzeichnis;
`--data-dir` erlaubt den datenbasierten Programmen ein anderes Eingabeverzeichnis.

## Grenzen der alten Rankingprogramme

Der Phase-2-Generator verlangt die vollständige ursprüngliche
`ranking_method_comparison.csv`, einschließlich `evaluation_role`. Der kompakte
Ergebnisexport enthält dieses Feld nicht und wird ausdrücklich abgewiesen.
Der Static-Proxy-Generator benötigt außerdem die ursprünglichen Performance-
und Vorhersageexporte mit modellweisen `analysis/predictions_frozen.csv` und
`analysis/final_candidate_plan.json`. Diese vollständigen Eingaben sind durch
die mitgelieferten Aggregatwerte nicht ersetzt. Eine neue Berechnung der
Korrelationen wird daher nicht als reproduzierbarer Standardweg angeboten.

Bei einer gesonderten historischen Untersuchung sind die Eingaben über die
jeweiligen CLI-Optionen anzugeben. Die Standardziele sind
`local-output/dissertation-v56-legacy/ranking/figures/` und `ranking/daten/`.
Ein ausdrücklich gesetztes `--output-dir` empfängt aus Kompatibilität alle
Ausgaben; `--data-output-dir` trennt bei Bedarf die CSV-Ausgabe.

## Grafikentwürfe mit externen Originalen

Der Redesigned-Generator benötigt ausdrücklich `--source-dir`. Dieses externe
Verzeichnis muss `urecs_real_front.png`, `recs_pcb_front.png`,
`recs_pcb_back.png` und `vedliot_yolov4_power_vs_perf.pdf` enthalten. Diese vier
Originale sind nicht Bestandteil des übernommenen LaTeX-Pakets. Zusätzlich
wird der Snapshot
`results/supplementary-studies/dissertation-v56/inputs/yolov7/prediction_vs_benchmark_yolov7_cases.csv`
gelesen.

```bash
python3 scripts/dissertation/legacy-v56/grafiken/generate_redesigned_figures.py \
  --source-dir /pfad/zum/originalen/grafikarchiv
```

Die Programme prüfen die erforderlichen Originaldateien vor der ersten
Ausgabe. Standardziele sind
`local-output/dissertation-v56-legacy/redesigned/figures/` und `redesigned/photos/`;
`--output-dir` setzt deren gemeinsames Elternverzeichnis.

## Abhängigkeiten und Übernahme von Ausgaben

Python 3.10 oder neuer ist erforderlich. Der Energie-Makroexport verwendet nur
die Standardbibliothek. Die übrigen Abhängigkeiten stehen ohne neue
Versionsfestlegung in [requirements.txt](requirements.txt). Eine bereits
eingerichtete passende Auswerteumgebung kann verwendet werden.

Die Standardaufrufe schreiben ausschließlich in `local-output/`. Sie ändern
weder eingefrorene Ergebnisdateien noch die Dissertation. Eine Übernahme neuer
Ausgaben erfolgt erst nach fachlicher und visueller Prüfung sowie Prüfung von
Eingabestand und Herkunft. Danach werden nur die ausgewählten Ergebnisdateien
in den passenden Ergebnisexport übernommen; das LaTeX-Projekt erhält die
benötigten Abbildungen und großen Tabellen als konsumierte Artefakte.
