# Zusammenfassung der unabhängigen Stufenkosten

[CSV mit voller Genauigkeit](https://github.com/Keff789/edge-ai-performance-energy-results/blob/main/results/supplementary-studies/stage-cost-composition/tables/STAGE_COST_SUMMARY.csv) · [LaTeX-Tabelle](stage_cost_table.tex)

Alle Raten sind Mediane zugehöriger Blöcke. Fehler werden innerhalb jedes Blöcke vor der Aggregation berechnet. Sie entsprechen daher im Allgemeinen nicht dem Verhältnis der angezeigten FPS-Mediane. P zählt nutzbare Grenztensoren, C/PC zählen abgeschlossene Klassifikationen. Alle primären Raten verwenden das feste mittlere Messfenster.

| Fall | P / s | C / s | Oracle / s | PC / s | Median des absoluten Fehlers | Maximaler absoluter Fehler | Blöcke |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepX / ResNet50 / b045 | 230 | 669 | 230 | 225 | 2.24% | 4.38% | 3 |
| DeepX / ResNet50 / b002 | 473 | 520 | 473 | 444 | 5.50% | 8.80% | 3 |
| Hailo-10H / RegNetX-1.6GF / b059 | 1565 | 500 | 500 | 477 | 4.77% | 4.88% | 3 |
| Hailo-10H / RegNetX-1.6GF / b123 | 1577 | 1999 | 1577 | 1518 | 3.85% | 5.90% | 3 |

Alle zwölf Fehler sind positiv (optimistische Oracle-Schätzung) und liegen unter der vorab festgelegten 10%-Grenze. Diese ist kein Konfidenzintervall. Beide modellinternen Cut-Rangfolgen stimmen in allen drei Blöcken überein. Die detaillierte Vergleichs-CSV enthält zwölf Blockvergleiche und sechs Zeilen mit Paarverhältnissen. Dies sind keine achtzehn unabhängigen Beobachtungen.

Experiment `stage_cost_composition_20261014`, Quelldatenstand `20261014T102852Z`. Die CSV behält die volle Genauigkeit und enthält außerdem gesamte Pipeline-FPS, kleinsten Fehler, Zyklusresiduum und Engpass.
