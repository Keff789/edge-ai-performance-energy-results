# Ergänzende Methoden und Prüfprotokolle

Dieses Ergänzungspaket bewahrt die ausführlichen Anhänge des am 11. November
2026 bereitgestellten LaTeX-Projekts
`Dissertation_Lean_Kapitel5(1)(1).zip`. Die überarbeitete Dissertation enthält
eine gekürzte Auswahl. Die hier gesicherten Texte, Tabellen und Abbildungen
bleiben als Nachweis und zum Nachschlagen verfügbar.

Das Paket ergänzt den Ergebnisstand
`fc0899711c544596e67efd96b294692ea9ee05e6` vom 10. November 2026. Es verändert
keine Messdaten, berechnet keine Ergebnisse neu und fügt keine Messungen zu
einer Versuchsreihe hinzu. Es wird mit dem aktualisierten Ergebnis-ZIP
bereitgestellt. Diese lokale Ergänzung wurde nicht in das entfernte
GitHub-Repository übertragen.

## Einstieg

| Datei oder Verzeichnis | Inhalt |
|---|---|
| [Ergänzende Methoden und Prüfprotokolle (PDF)](Ergaenzende_Methoden_und_Pruefprotokolle.pdf) | Lesbare Sicherung des ursprünglichen Anhangs mit dem zugehörigen Literaturverzeichnis |
| [Originale Anhangquellen](source/4_appendix/) | Unveränderte LaTeX-Dateien A bis D vor der Kürzung |
| [Tabellen und Abbildungen der Originalfassung](source/9_resources/) | Sämtliche von diesen Anhangdateien eingebundenen Ressourcen und die numerischen LaTeX-Makros |
| [Literaturdatenbank der Originalfassung](source/3_back_matter/library.bib) | Ursprüngliche Zuordnung der Literaturangaben |
| [Alle sieben Modellansichten](figures/) | Einzelne PDF-Abbildungen zum direkten Öffnen |
| [Dateinachweis](MANIFEST.json) | Herkunft und Prüfsummen der gesicherten Dateien |
| [Änderungen am LaTeX-Projekt](changes.patch) | Redaktionelle Unterschiede zwischen dem bereitgestellten und dem gekürzten Projekt |

**Die Abschnitts-, Seiten-, Tabellen- und Literaturnummern im gesicherten PDF
beziehen sich bewusst auf die Originalfassung.** Sie stimmen nach der Kürzung
nicht durchgehend mit der aktuellen Dissertation überein. Angaben wie
„Tabelle B.2“ in diesem Verzeichnis bezeichnen daher die hier gesicherte
Fassung. Ihre Anhangseiten sind mit 217 bis 249 nummeriert. Die LaTeX-Dateien
unter `source/` sind eine unveränderte Quellensicherung und kein eigenständig
baubares vollständiges Dissertationsprojekt. Der vollständige ursprüngliche
Anhang wird zur Nachvollziehbarkeit aufbewahrt, auch soweit einzelne Inhalte
weiterhin in der gekürzten Dissertation stehen.

## Ausgelagerte Inhalte gezielt finden

| Inhalt der Originalfassung | Fundstelle in diesem Paket | Zugehörige Auswertung im Ergebnisarchiv |
|---|---|---|
| A: KI-gestützte Werkzeugentwicklung | [A_ai_tool_development.tex](source/4_appendix/A_ai_tool_development.tex), ursprüngliche S. 217–219 | Dokumentation der Unterstützung und Verifikation. Keine zusätzlichen Messdaten. |
| B.1/B.2: Quellen, Reproduktionsbefehle und frühere Exportprüfungen | [B_evidence_archive.tex](source/4_appendix/B_evidence_archive.tex), ursprüngliche S. 220–222 | [Aktuelle Reproduktionsanleitung](../../../scripts/README.md), [Dissertationsausgaben](../../../publications/dissertation/README.md), [historischer Satzstand v56](../dissertation-v56/README.md) |
| B.4, Tabelle B.2: Wiederholbarkeit und Unterschiede zwischen Erfassungsraten | [Originaltabelle](source/9_resources/04_energiemessung/direct_rates.tex), ursprüngliche S. 225 | [Numerische Ratenzusammenfassung](../../energy-measurement/tables/tim/direct_rates.csv). Enthält unter anderem die Anzahl der Durchläufe, den größten Variationskoeffizienten und die größte Gruppenverschiebung. |
| B.4: Intervallregeln, Spannungsverarbeitung, Spektralsegmentierung und Ratenkontrolle | [B_evidence_archive.tex](source/4_appendix/B_evidence_archive.tex), ursprüngliche S. 224–227 | [Methoden der Energieauswertung](../../energy-measurement/METHODS.md), [thematisch geordnetes Tabellenverzeichnis](../../energy-measurement/tables/README.md), [kontrollierte Rateneffekte](../../energy-measurement/tables/tim/controlled_effects.csv) |
| B.5: Kalibrierprofile und aufgezeichneter Messbereich | [B_evidence_archive.tex](source/4_appendix/B_evidence_archive.tex), ursprüngliche S. 227–230 | [Profile der drei Versuchsaufbauten](../../energy-measurement/data/calibration/split-setups/), [Kalibrierungsnachweise](../thesis-v49-confirmation-20261019/inputs/metrology/calibration_records.json) |
| B.6: Dauerbetrieb und Eingabe-Ausgabe-Zuordnung | [B_evidence_archive.tex](source/4_appendix/B_evidence_archive.tex), ursprüngliche S. 230–231 | [Versuchsübersicht](../thesis-v49-confirmation-20261019/README.md), [primäre Messungen](../thesis-v49-confirmation-20261019/tables/primary_measurements.json), [Zuordnung der Energiemesspaare](../thesis-v49-confirmation-20261019/tables/primary_energy_pairs.json) |
| C.1/C.2: Plattform-, Ausführungs- und Bewertungseinstellungen | [C_split_reproduction.tex](source/4_appendix/C_split_reproduction.tex), ursprüngliche S. 232–235 | [Versionen und Präzisionszuordnungen](../thesis-v49-confirmation-20261019/inputs/metrology/version_and_precision_bindings.json) |
| C.3: Kandidatenmengen, Auswahlbudgets und einzelne Gewichtsvektoren | [C_split_reproduction.tex](source/4_appendix/C_split_reproduction.tex), ursprüngliche S. 235–238 | [Gepaarte Auswahl](../rq2-native-scope-20261027/README.md), [breitere Graphenauswertung](../rq3-generic420-detector-corrected-20261027/README.md), [Gewichtsvektoren](../rq3-generic420-detector-corrected-20261027/artifacts/de/tables/paper_shared_fold_weights.csv), [Auswahlkette](../staged-selection/README.md) |
| C.3, Tabelle C.3: Sensitivität der Gewichtsanpassung | [C_split_reproduction.tex](source/4_appendix/C_split_reproduction.tex), ursprüngliche S. 238 | [Gemeinsamer Ausschluss verwandter Modelle](../rq3-generic420-detector-corrected-20261027/artifacts/de/tables/sensitivity_family_holdout.csv), [Anpassung an das Fünf-Test-Budget](../rq3-generic420-detector-corrected-20261027/artifacts/de/tables/sensitivity_budget5_fit.csv) |
| C.4: Historische Zählregeln und nachträgliche Prüfungen | [C_split_reproduction.tex](source/4_appendix/C_split_reproduction.tex), [Operatorenkatalog](source/9_resources/10_anhang/operator_catalogue.tex), ursprüngliche S. 239–240 | Die hier gesicherten Regeln behalten ihren historischen Geltungsbereich. Die aktuelle Dissertation unterscheidet diese von den Erweiterungen der aktuellen Graphbewertung. |
| C.5: Früherer Hailo-Compiler-Vergleich mit interner B500-Metrik | [C_split_reproduction.tex](source/4_appendix/C_split_reproduction.tex), ursprüngliche S. 240–241 | [Erläuterung des Entwicklungsversuchs](../dissertation-development-2026/README.md#yolov7-decoder-b500-and-compiler-sensitivity), [Ergebnistabelle](../dissertation-development-2026/tables/hailo_optimisation_table.md), [ungerundete Werte](../dissertation-development-2026/tables/hailo_optimisation_full_precision.csv) |
| D: Vollständige Modellansichten | [D_model_tradeoffs.tex](source/4_appendix/D_model_tradeoffs.tex), ursprüngliche S. 242–249, sowie [Einzelabbildungen](figures/) | [Aktuelle deutsche Dissertationsausgaben](../../publication-builds/generic420-20261027/dissertation-de/README.md) |

Die ursprünglichen Versuchsgrenzen gelten unverändert. Insbesondere sind der
frühere B500-Compiler-Vergleich und die COCO-Bewertung der Hauptkampagne
verschiedene Untersuchungen. Auch die sieben Modellansichten enthalten
Konfigurationen vor der Qualitätsfilterung. Ihre markierten Pareto-Punkte
belegen daher keine Dominanz bei gleicher Ergebnisqualität.

## Alle Modellansichten

| Ursprüngliche Abbildung | Modell | PDF |
|---|---|---|
| D.1 | MobileNetV3 Large | [Öffnen](figures/04_tradeoff_mobilenet_v3_large.pdf) |
| D.2 | RegNet-X 1.6GF | [Öffnen](figures/04_tradeoff_regnet_x_1_6gf.pdf) |
| D.3 | ResNet-50 | [Öffnen](figures/04_tradeoff_resnet50.pdf) |
| D.4 | YOLO11l | [Öffnen](figures/04_tradeoff_yolo11l.pdf) |
| D.5 | YOLO26m | [Öffnen](figures/04_tradeoff_yolo26m.pdf) |
| D.6 | YOLO26s | [Öffnen](figures/04_tradeoff_yolo26s.pdf) |
| D.7 | YOLOv7 | [Öffnen](figures/04_tradeoff_yolov7_paper.pdf) |

Die Abbildungen wurden unverändert aus dem bereitgestellten LaTeX-Projekt
übernommen. Farben, Achsen, Messwerte und Beschriftungen wurden bei dieser
Auslagerung nicht neu erzeugt oder geändert.

## Tool-Dokumentation zu Adaptern und Dateiformaten

Der [Softwareindex](../../../software/README.md) verweist auf das eingefrorene
Quellarchiv
`software/ONNX-Splitpoint-Tool_v2.94.0_db729b9fcde00e4bcadf9200d43282977d7bf1cc_source.tar.gz`.
Innerhalb seines gleichnamigen Wurzelverzeichnisses befinden sich:

- `docs/NATIVE_THREE_STAGE.md`, Abschnitt **Adapter registry**: Bezeichnungen
  der Adapter für Klassifikation, YOLOv7, integrierte YOLO26-Ausgaben und
  YOLO11-DFL-Ausgaben.
- `onnx_splitpoint_tool/native_three_stage.py`: Zuordnung der Ausgabefamilien
  zu Adapterkennungen, einschließlich `ultralytics_decoded_pre_nms`.
- `docs/ARTIFACTS_AND_POSTPROCESSING_CONTRACT.md`: Ergebnisdateien und
  Schnittstelle zwischen Ausführung, Nachverarbeitung und Berichterstellung.
- `onnx_splitpoint_tool/resources/schemas/SCHEMA.md`: Felder von
  `split_manifest.json`, `benchmark_plan.json` und `benchmark_set.json`.

Diese Angaben dokumentieren den eingefrorenen Softwarestand. Die späteren
DEEPX-A4-Quellen sind im Softwareindex gesondert verzeichnet.
