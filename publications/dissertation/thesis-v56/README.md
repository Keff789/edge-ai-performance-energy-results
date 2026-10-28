# Feste Abbildungsexporte der Dissertation v56

Diese Sammlung dokumentiert die im bereinigten LaTeX-Projekt verwendeten
Abbildungen und Tabellen. Die Auswertungsskripte und Datengrundlagen gehören
zum Results-Repository. Das LaTeX-Projekt enthält lediglich die benötigten
festen Exporte und die direkt in die Sections eingebauten kleinen Tabellen.

## Ablage

| Ort | Inhalt |
| --- | --- |
| `figures/` | 15 bisher nicht byteidentisch im Repository vorhandene Messgrafiken der Dissertation |
| `illustrations/` | 13 feste Schema- und Architekturabbildungen |
| `tables/` | Sieben größere, auf die Dissertation formatierte Tabellen |
| `inline-table-exports/` | Die ursprünglichen Exporte der 19 kleinen Tabellen, die im LaTeX-Projekt direkt in den Sections stehen |
| `values/energy_numbers.tex` | Die unveränderten aktiven Kennzahlenmakros |

Die weiteren 15 Messgrafiken liegen bereits byteidentisch in den aktuellen
Publikations- beziehungsweise Studienverzeichnissen. Sie werden hier nicht
erneut kopiert. Der
[Quellnachweis](../../../results/supplementary-studies/dissertation-v56/SOURCE_MANIFEST.json)
verknüpft alle 30 verwendeten Messgrafiken, die Tabellen und die sonstigen
Abbildungen mit ihren jeweiligen Orten und SHA-256-Werten. Die drei Fotos
bleiben redaktionelle Bilddateien des LaTeX-Projekts.

## Herkunft und Verwendung

Die [historischen Quellen und Daten](../../../results/supplementary-studies/dissertation-v56/README.md)
bleiben getrennt von den aktuellen Auswertungen. Die sechs früher im
LaTeX-Paket enthaltenen Programme liegen ausschließlich unter
`scripts/dissertation/legacy-v56/`. Für die aktuelle Studie bleibt
`scripts/reproduce_current.py` der Einstiegspunkt.

Die hier eingefrorenen deutschen Darstellungen enthalten auch frühere,
für die Dissertation angepasste Layouts. Ein übereinstimmender Dateiname
mit einem aktuellen Export belegt keine identischen Bytes oder identischen
Untersuchungsumfang. Diese Sammlung bewahrt den geprüften Satzstand; sie
wurde weder als neue Messung noch als Ersatz für die aktuelle Analyse erzeugt.

Bei einer Aktualisierung werden geprüfte Exporte aus dem Results-Repository
in `9_resources/messdaten/` beziehungsweise `9_resources/grafiken/` der
Dissertation übernommen. Ein Importnachweis im LaTeX-Projekt nennt den
Repository-Commit, die Quellpfade und die Hashes. Der normale LaTeX-Build
benötigt weder Python noch einen Checkout dieses Repositorys.
