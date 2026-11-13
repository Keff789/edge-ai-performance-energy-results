# Deutsche Grafiken und Tabellen für die Dissertation

Diese Ausgabe enthält die vollständige Split-Auswertung, die Publikationsprofile und die ergänzenden Split-Studien. Die Energiemessung besitzt ein separates Auswertetool.

Alle Darstellungen verwenden die vorhandenen Messdaten. Achsen, Legenden und Tabellenbeschriftungen sind deutsch. Modell-, Geräte- und Methodennamen sowie die wissenschaftliche Zahlenschreibweise bleiben erhalten. Die englischen CSV-/JSON-Dateien bleiben die gemeinsame Datenquelle.

Das aktuelle Paper verwendet `mlsys-r30`. `mlsys-r22` und die datierten Zusatzstudien bleiben als eigene Messreihen getrennt. Das Manifest verknüpft jede deutsche Datei mit ihrer Quelle und deren Prüfsumme.

## Reproduktion

```sh
python -I -B scripts/dissertation/reproduce.py --output /tmp/dissertation-de --verify
```

Ein leeres Ausgabeverzeichnis verwenden. Für die vollständige englische und deutsche Split-Ausgabe:

```sh
python -I -B scripts/split-inference/reproduce.py \
  --publication mlsys-r30 --languages en de --output /tmp/split-de --verify
```

## Auswahl

| Bereich | Grafiken | Tabellen-Dateien |
|---|---:|---:|
| [mlsys-r22](mlsys-r22/README.md) | 8 | 56 |
| [mlsys-r30](mlsys-r30/README.md) | 13 | 60 |
| [split-inference](split-inference/README.md) | 23 | 12 |
| [supplementary-studies/dissertation-development-2026](supplementary-studies/dissertation-development-2026/README.md) | 2 | 15 |
| [supplementary-studies/mlsys-selection-20261007](supplementary-studies/mlsys-selection-20261007/README.md) | 4 | 25 |
| [supplementary-studies/native-endpoint-reconstruction](supplementary-studies/native-endpoint-reconstruction/README.md) | 0 | 12 |
| [supplementary-studies/rq2-all-cuts-20261020](supplementary-studies/rq2-all-cuts-20261020/README.md) | 4 | 1 |
| [supplementary-studies/stage-cost-composition](supplementary-studies/stage-cost-composition/README.md) | 2 | 2 |
| [supplementary-studies/thesis-v49-confirmation-20261019](supplementary-studies/thesis-v49-confirmation-20261019/README.md) | 0 | 0 |
| [supplementary-studies/thesis20-ranking-20261005](supplementary-studies/thesis20-ranking-20261005/README.md) | 2 | 0 |
| [supplementary-studies/yolov7-completion-20261007](supplementary-studies/yolov7-completion-20261007/README.md) | 0 | 1 |
