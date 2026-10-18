# ResNet: vollständige Scheduling-by-Runtime-Replikation

Abgeschlossen am 17.10.2026 auf SM2, Serie `resnet_full_replication_v1`. **40 frische Prozesse in fünf gemeinsamen randomisierten Blöcken** wurden zugelassen. Es gab keine Fehlversuche, Ausschlüsse, technischen Wiederholungen oder zusätzlichen Messprozesse. Der Controller endete regulär mit Exitcode 0 und gab die Gerätesperre frei.

**Der RegNet-Befund wird für das bereits ausgewählte ResNet-Cut-Paar in seiner Richtung gestützt.** Der primäre Interaktionskontrast beträgt **3,4288**, mit nominalem 95-%-Intervall **[3,3532; 3,5061]**. Unter produktivem Scheduling bevorzugt Generic b002 und Native b095. Die Ein-Aufgabe-Intervention lässt beide Laufzeitketten b002 bevorzugen. Bei Native kehrt sich damit die Rangfolge um; bei Generic ändert sich die relative Stärke bei unveränderter Präferenz. Die Übertragung betrifft dieses bekannte Cut-Paar und die gebundenen aktuellen Laufzeitketten.

## Messvertrag und Herkunft

ResNet-50/H10, b002 und b095, wurden mit vier Varianten gemessen: Generic/Native jeweils produktiv und mit global höchstens einer ausstehenden Aufgabe. Jeder Block enthält alle acht Zellen in gemeinsam randomisierter Reihenfolge; Seed 20261017. Alle Native-Zellen wurden ebenfalls neu gemessen. Die 40 neuen Worker haben verschiedene Prozess-IDs und wurden nacheinander ausgeführt.

`PROTOCOL.json` wurde am 17.10.2026 um 19:03:57 UTC vor der ersten neuen Messung festgeschrieben. SHA256: `c57205b0cbcdd2c7862bf0c21d88eec585a374c7b566bb6896a8571f37be2601`. Der vorab gebundene Analyzer blieb unverändert. Die Ausführung lief von etwa 19:07 bis 20:17 UTC auf `orin_nx_hailo10_01` mit denselben R14-Artefakten, Eingaben, Präzisionseinstellungen, Profilen und Laufzeitquellen wie die abgeschlossene Mechanismusstudie. Die Laufzeitquellen wurden ausschließlich in einen separaten Auftragsordner kopiert. Es handelt sich um einen Versuch mit dem eingefrorenen aktuellen Code, keine Rekonstruktion historischer Softwarebedingungen.

Pro Worker: 30 s Warm-up, vollständiger Drain, 60 s Aufnahme neuer Aufgaben, anschließend vollständiger Drain. Durchsatz = vollständig abgeschlossene Aufgaben / gesamte gemessene Laufzeit einschließlich Anlauf und Drain. Warm-up-Aufgaben zählen nicht. Die beobachteten Makespans liegen bei 60,00138–60,02365 s. Der Task-Endpunkt umfasst Materialisierung und Top-1/Top-5-Verarbeitung.

Generic produktiv verwendet die vorhandenen zwei Worker mit Queue-Limit 2; Native produktiv acht asynchrone Slots mit Queue-Limit 3. Bei der Intervention hält das unveränderte globale Completion-Gate die einzige Erlaubnis bis zur vollständigen Task-Fertigstellung; Native begrenzt zusätzlich Inflight auf 1. Es gibt keinen direkten globalen Highwater-Zähler. Der Nachweis beruht auf gebundener Semaphore-/Aufrufreihenfolge, vorhandenen Queue-/Inflight- und Completion-Zählern sowie passenden Funktionsbelegen, nicht auf einem erfundenen Messwert für die globale Spitze.

Acht bereits vorhandene Funktionsbelege decken exakt beide Cuts und alle vier Ausführungspfade ab: je 32 gemischte Aufträge mit zwei unterscheidbaren Eingaben, insgesamt 256 Aufträge. Gespeicherte Referenzen und Ausgaben stimmen bytegenau überein. Die Wiederverwendung ist einschließlich Artefakten, Konfigurationen und Quellbindungen in `receipts/reuse/` geprüft. Neue Piloten und eine erneute vollständige Datensatzbewertung waren nicht erforderlich; diese Funktionsbelege gehen nicht in die Durchsatzschätzung ein.

## Ergebnisse über fünf Blöcke

Für jede Variante ist r = Durchsatz(b095) / Durchsatz(b002). Werte unter 1 bevorzugen b002, Werte über 1 b095. Die beiden Scheduling-Effekte sind jeweils r(produktiv) / r(eine Aufgabe). Alle Angaben sind geometrische Mittel und nominale zweiseitige 95-%-t-Intervalle über fünf Prozessblöcke.

| Kontrast | Geometrisches Mittel | Nominales 95-%-Intervall |
|---|---:|---:|
| Generic, produktiv | 0.6057 | [0.6033; 0.6082] |
| Native, produktiv | 2.0597 | [2.0281; 2.0919] |
| Generic, eine Aufgabe | 0.8359 | [0.8276; 0.8442] |
| Native, eine Aufgabe | 0.8290 | [0.8240; 0.8339] |
| Generic: r(produktiv) / r(eine Aufgabe) | 0.7247 | [0.7183; 0.7310] |
| Native: r(produktiv) / r(eine Aufgabe) | 2.4847 | [2.4382; 2.5320] |
| Primäre Interaktion I | 3.4288 | [3.3532; 3.5061] |

Die vier Cut-Verhältnisse und die primäre Interaktion je gemeinsamem Block:

| Block | Generic produktiv | Native produktiv | Generic eine Aufgabe | Native eine Aufgabe | I |
|---|---:|---:|---:|---:|---:|
| 1 | 0.605842 | 2.016153 | 0.839013 | 0.831017 | 3.359875 |
| 2 | 0.606863 | 2.061840 | 0.831229 | 0.827672 | 3.412135 |
| 3 | 0.602796 | 2.078277 | 0.834925 | 0.827488 | 3.478714 |
| 4 | 0.608045 | 2.077963 | 0.845668 | 0.824116 | 3.506817 |
| 5 | 0.605024 | 2.065149 | 0.828609 | 0.834636 | 3.388687 |

Alle sieben Kontraste je Block stehen mit ungerundeten Logwerten in `results/replication_analysis_blocks.csv`. Die 40 Zellwerte einschließlich vollständiger Aufgabenanzahl, Makespan, Durchsatz, Worker-PID, tatsächlicher Reihenfolge und Rohberichtbindung stehen in `results/replication_analysis_cells.csv`; sämtliche Versuche in `results/replication_analysis_attempts.csv`.

Der primäre Kontrast wird innerhalb jedes Blocks als

`log(I) = [log(r_N_product) − log(r_N_single)] − [log(r_G_product) − log(r_G_single)]`

gebildet. Über die fünf Blockwerte werden Mittelwert und Stichprobenstandardabweichung der Logwerte berechnet; das Intervall ist `exp(mean_log ± 2.7764451051977987 × sd_log / sqrt(5))`, mit vier Freiheitsgraden. **I ist ein Verhältnis von Cut-Verhältnissen, kein Durchsatzgewinn eines einzelnen Cuts.** Die fünf Blöcke bilden die Replikationseinheiten; Frames innerhalb eines Prozesses sind keine zusätzlichen unabhängigen Wiederholungen. Die Intervalle sind nominal, bei kleiner Blockzahl und ohne simultane Absicherung aller sieben Kontraste.

## Drei getrennte Antworten

**a) Produktive Cut-Präferenz:** Ja. Generic r = 0,6057 und Native r = 2,0597 liegen mit ihren jeweiligen Intervallen auf entgegengesetzten Seiten von 1. Auch in jedem der fünf Einzelblöcke ist diese Richtung gleich.

**b) Wirkung der Ein-Aufgabe-Intervention:** Generic r steigt von 0,6057 auf 0,8359; b002 bleibt bevorzugt. Native r fällt von 2,0597 auf 0,8290 und wechselt von b095 zu b002. Die Änderung des Cut-Verhältnisses bei Generic ist keine Rangumkehr. Aus den Verhältnisänderungen allein folgt keine Aussage über einen absoluten Durchsatzzuwachs.

**c) Übertragung des RegNet-Befunds:** I = 3,4288 liegt mit dem gesamten nominalen Intervall über 1. Das stützt die gleichgerichtete Scheduling-by-Runtime-Interaktion für dieses zweite ausgewählte Paar. Die alte RegNet-Serie berichtete I = 5,1081 [4,9896; 5,2294]. Die unterschiedliche Größe ist hier deskriptiv; es wurde weder gleiche Effektstärke noch ein formaler Unterschied zwischen den Studien getestet. Zudem bevorzugten bei RegNet beide Ein-Aufgabe-Varianten leicht b123, während sie bei ResNet b002 bevorzugen. Die genaue verbleibende Cut-Präferenz wird also nicht über Modelle hinweg verallgemeinert.

## Seriengrenzen und Aussagegrenzen

| Serie | Umfang | Rolle in diesem Ergebnis |
|---|---:|---|
| Alte RegNet-Mechanismusstudie | 40 Prozesse | Separater Richtungsvergleich; keine Neuberechnung oder Zusammenfassung mit ResNet |
| Alte ResNet-Native-Serie | 20 Prozesse | Separater Vorbefund; kein vollständiger Generic-Vergleich |
| Neue vollständige ResNet-Serie | 40 Prozesse | Ausschließliche Grundlage der obigen Schätzungen und fünf gemeinsamen Blöcke |

Alte und neue Native-Messungen werden nicht gepoolt. Die früher nicht ausgelösten 40 RegNet-Erweiterungsprozesse bleiben ungestartet. Die neue Studie ist eine optionale Ergänzung eines bereits abgeschlossenen Auftrags.

ResNet und die Cuts wurden wegen einer bekannten Rangumkehr ausgewählt. Die neue gemeinsame Randomisierung ersetzt keine unabhängige Modellauswahl und belegt keine allgemeine Verbreitung über unbekannte Modelle oder Hardware. Generic und Native bleiben unterschiedliche Laufzeitketten; der Versuch isoliert weder Kopier-, Layout- noch Konvertierungskosten. Keine neuen Aussagen zu Energieeffizienz, Gesamtsuchkosten oder beliebigen variablen Eingabeströmen. Audit, Kalibrierung, weitere Modelle und Parametersweeps wurden nicht wiederholt.

## Unabhängige Prüfung und Paper-Einbindung

Die Ausführungsprüfung `results/execution_review.json` bestätigt 40/40 neue zugelassene Prozesse, fünf vollständige Blöcke, alle 80 Vorher-/Nachher-Zustände mit je 335 Quell-/Artefaktbindungen und die vollständigen Endpunkte. Die Starttemperaturen erfüllen das vorab definierte Zulassungsfenster; Endtemperaturen bis 66 °C sind nach dem eingefrorenen Vertrag deskriptiv und kein nachträglicher Ausschlussgrund.

`results/independent_results.json` berechnet ohne Import oder Aufruf des Analyzers aus den Rohberichten erneut Durchsätze, 35 Blockkontraste und sieben Zusammenfassungen. 294 numerische JSON-/CSV-Vergleiche stimmen überein; kein neuer Prozess wird aus der alten Serie übernommen. Die zusätzliche wissenschaftliche Schlussprüfung ist in `results/scientific_results_review.json` dokumentiert. Reproduktionsbefehle stehen in `README.md`; die Prüfung in einem umbenannten, isolierten Paketverzeichnis wird in `results/package_review.json` protokolliert. Der externe `PACKAGE_CHECK.json` belegt die tatsächlich erzeugte ZIP-Datei und ihre identische Downloads-Kopie.

**Paper-Entscheidung:** Die vollständige ResNet-Replikation mit ein bis zwei Sätzen in den vorhandenen Mechanismusabsatz aufnehmen und dort die bisher vorgeschlagene Native-only-ResNet-Passage ersetzen. Vollständige Tabellen und Protokolldetails ins Supplement. Keine zweite neue Hauptabbildung, keine neue Hauptsektion; Ziel bleiben zehn Haupttextseiten. `PAPER_DELTA.md` enthält den konkreten Ersatztext. Das Manuskript selbst bleibt unverändert.
