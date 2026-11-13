# Vorschlag: Übersicht der Energiemessungen

Die neue Übersicht ist ein eigenständiger Abbildungsvorschlag. Die bestehenden
neun Energieabbildungen und ihre englischen Referenzflächen werden unverändert
beibehalten. Die neue Grafik benötigt keine englische Gegenfassung.

## Reproduktion

Im Repository ausführen:

```sh
python scripts/dissertation/render_thesis_energy_de.py --coverage-only --output /tmp/measurement-scope
```

Alternativ kann der eigenständige Renderer mit `--repository` auf den Stamm
dieses Repositorys verwiesen werden:

```sh
python scripts/dissertation/render_measurement_scope.py --repository . --output /tmp/measurement-scope
```

Der Loader liest die vorhandenen CSV-Dateien unter
`results/energy-measurement/`. Für die Erfassungsraten wählt er ausschließlich
die in `direct_rates.csv` dokumentierten Serien und Auswertungsfenster aus.
Er prüft die Auswahl gegen `paper_window_policy.csv`. Die Zahlen der
Daueruntersuchung werden zusätzlich anhand eindeutiger Ausführungskennungen
geprüft. Parallele Sensorvergleiche werden dabei zusammengeführt.

Die JSON-Begleitdatei enthält die dargestellten Gruppen, Auswahlregeln und
SHA-256-Prüfsummen aller acht Quellen. Der Aufruf über den Haupt-Renderer
erzeugt zusätzlich `MEASUREMENT_SCOPE_REGENERATION.json` mit Quell- und
Ausgabeprüfsummen sowie einer Schriftgrößenprüfung bei 355,42 bp Einfügebreite.
Es werden keine Signalverarbeitung oder statistischen Messgrößen neu berechnet.

## Vorgeschlagene Bildunterschrift

```latex
\caption[Übersicht der ausgewerteten Energiemessungen.]{Übersicht der ausgewerteten Energiemessungen. (a) Kombinationen aus Berechnungsvariante und Erfassungsrate. (b) Kombinationen aus Berechnungsvariante und angeforderter Messdauer. Jede gefüllte Zelle steht für 15 auswertbare physische Ausführungen. Zahlen in offenen Zellen geben eine geringere Anzahl an. Durchgestrichene Zellen kennzeichnen fehlende Daten, $\Sigma$ die jeweilige Zeilensumme. (c) Separat durchgeführte Referenz- und Kontrollversuche. Parallel verwendete Messgeräte, numerische Rekonstruktionen und zusätzliche Auswertungsfenster werden nicht als weitere Ausführungen gezählt. Datengrundlage: \cite{energyEvidence2026,edgeAIResults2026}.}
```

Die Referenzmessungen umfassen 59 Ausführungen mit zwei gleichzeitig verwendeten
Oszilloskopen. Daraus entstehen 118 Messaufzeichnungen, aber keine 118
Ausführungen. Die Pausenuntersuchung zählt sechs ausgewertete Ausführungen und
schließt einen vorbereitenden Konditionierungslauf aus.

Die 15 FP16-Aufzeichnungen für lange Integrationsintervalle, die 30
Hailo-Spektralaufzeichnungen und die 225 Auswertungen mit festem innerem
Zeitfenster verwenden bereits gezählte Aufzeichnungen erneut. Sie werden
deshalb nicht addiert. Die Grafik erhebt keinen Anspruch auf einen Gesamtzähler
aller historischen Energiemessungen.
