# Wissenschaftliche Klärung der MLSys-Fassung R14

Der Auftrag ist ausgeführt. Der Nachweisaudit umfasst alle 450 R14-Konfigurationen. Die feste Kalibrierung und alle 60 vorgesehenen bestätigenden Hardwareprozesse sind abgeschlossen. Hinzu kommen 18 getrennte H10-Pilotprozesse und ein regulärer DeepX-Zuordnungsworker, insgesamt 79 neue abgeschlossene Workerprozesse. Die bedingte RegNet-Erweiterung war nach der festgelegten Regel nicht erforderlich. Wissenschaftliche Grenzen bleiben ausdrücklich ausgewiesen.

## Welche vorhandenen Aussagen tragen?

Die numerischen R14-Ergebnisse lassen sich reproduzieren. Der Audit umfasst alle 450 Konfigurationen, nicht nur die 14 globalen Gewinner. Die Quellen verbinden die ausgewertete Qualität mit den tatsächlich verwendeten kompilierten Artefakten, den fachlichen Timing-Endpunkten und den Energiebelegen. Die geforderte relative Qualitätsgrenze von 5 % lässt 407 Konfigurationen zu: 187 Native-Splits, die zugehörigen 187 Generic-Splits und 33 Full-Ausführungen. 43 Konfigurationen scheiden allein wegen der numerischen Qualität aus. Fehlende Werte werden nicht als Null oder Erfolg behandelt.

Alle sieben globalen Split-/Full-Gewinnerpaare bleiben erhalten. Sechs Splits sind schneller als die jeweils stärkste verfügbare Full-Ausführung, drei davon zugleich energieärmer. Beim globalen RegNet-Vergleich beträgt das Durchsatzverhältnis 2,539 und die Energieabnahme 49,825 %. Dieser globale Vergleich erlaubt unterschiedliche Hosts. Der lokale Vergleich innerhalb eines Modell-/Setup-Paars beantwortet eine andere Frage: Nach Qualitätsfilter sind 102 von 187 Native-Splits schneller als der jeweils schnellste zulässige Full, 74 energieärmer und 62 beides. Gegen die unabhängig energieärmste Full-Ausführung sind 69 von 187 energieärmer.

Im exakt gepaarten Runnervergleich ist Native nach dem gemeinsamen Qualitätsfilter in 169 von 187 Fällen schneller und in 179 von 187 Fällen energieärmer als Generic. Der Median des Durchsatzquotienten beträgt 1,602. Ohne Qualitätsfilter sind es 186 von 204 beziehungsweise 196 von 204 bei einem Median von 1,595. Beide Kohorten verwenden nachgewiesene Artefakt- und Eingabepaare, bleiben aber getrennt ausgewiesen. Die maschinelle Nachrechnung steht in `results/confirmed_pair_comparison.json`.

Die sieben stärksten Full-Referenzen bleiben in der Bewertung. Insbesondere wird kein ungeklärter starker Full entfernt, um einen größeren Splitgewinn zu erzeugen. Die 5-%-Zulassung beweist keine identische Genauigkeit. Alle ausgewählten Qualitätsquellen nennen 5.000 Beispiele. Bei 53 Konfigurationen weicht ein gespeicherter Policyverlust vom neu berechneten numerischen Verlust ab. Die Auswertung verwendet die Evaluationswerte und erhält die ursprünglichen Labels unverändert.

## Warum die historischen Einschränkungen jetzt anders bewertet werden

Die 75 DeepX-Beobachtungen gehören bereits zur in R14 verwendeten A4-Generation. Ihre neuen Reviewentscheidungen sind keine neue Leistungsrangliste. Die zugrunde liegenden 225 Performanceprozesse und 225 Energiewiederholungen waren abgeschlossen. Die Energiebelege besitzen drei 60-Sekunden-Wiederholungen je Konfiguration, die korrekte Kalibrierung und den tatsächlichen finalen Messvertrag. Die alten Screeningvermerke stammen aus einer früheren Zulassungs-/Qualitätsklassifikation. Die konkreten Artefakt-, Eingabe-, Kommando-, Completion- und Sensorbelege schließen diese Einschränkung für die ausgewerteten Konfigurationen.

Bei sechs YOLO26-Splitzusammenfassungen blieb trotz jeweils drei gültiger Rohwiederholungen ein Teilstatus stehen. Die Prüfung führt den Widerspruch auf Pfadänderungen in der Attestierungsidentität zurück. Die relevanten Artefakthashes stimmen überein. Die Originalzusammenfassungen bleiben erhalten. Die korrigierte Einschlussentscheidung steht ausschließlich in den abgeleiteten Audittabellen.

Für Hailo-Fulls stützt sich die Bindung auf konkrete Produktionsbelege. Fünf Fulls haben zu allen drei Wiederholungen zeitnahe Artefakthashes vor und nach dem Lauf. Die übrigen neun besitzen eine erfolgreich erzeugte zusammengesetzte Quittung, die den exakten Performance-Rohreport mit HEF, Graph und Vorbereitung verbindet. Ein Modellname oder Cutlabel ersetzt diese Verbindung nicht.

Die fachlichen Endpunkte schließen bei Klassifikation synchronisierte Ausgaben und Top1/Top5 ein. Bei Detektion gehören erforderliches Decoding, NMS beziehungsweise die entsprechende integrierte Ausgabe und Materialisierung dazu. YOLO26 verwendet einen zulässigen NMS-freien Graphendpunkt. Eine zusätzliche unabhängige Oracle-Prüfung außerhalb des Timers ist kein ausgelassener fachlicher Arbeitsschritt. Unterschiedliche Sprachen oder Schedules sind für diesen Deploymentvergleich zulässig.

Historische Durchsatzmessungen mit wiederholter vorbereiteter Eingabe beweisen keine beliebige Request-/Output-Zuordnung. Für die sieben DeepX-Fulls liegen exakt gebundene Tests mit 32 unterschiedlichen Bildern vor. Für den global ausgewählten MobileNet-/DeepX-Split b135 wurde ein neuer regulärer, profilgesteuerter Test ausgeführt. Alle 32 seriellen Referenzen und 32 A4-Ausgaben stimmen an Grenze und Logits exakt überein. Der Test enthält zusätzlich 64 ungemessene Smoke-Abschlüsse und dokumentiert vollständigen Drain sowie Freigabe der eigenen Ressourcen. Er liefert keine neue Genauigkeits-, Performance- oder Energiekohorte. Ein erster Profil-Ladefehler vor dem Hardwarestart bleibt als Versuch erhalten.

## Wie zuverlässig ist die Auswahl mit kleinem Budget?

Die einfache Generic-Einzelauswahl trifft unverändert 9 von 21 Native-Gewinnern. Ihr gleichgewichteter Durchsatzverlust beträgt 15,164 % ohne Qualitätsfilter und 15,077 % mit dem numerischen 5-%-Filter. Diese 21 Gruppen mischen neun Klassifikator- und zwölf Detektorgruppen. Die getrennte Klassifikatorauswertung ist für anspruchsvolle kleine Messbudgets aussagekräftiger.

Die Kalibrierung war vor der Foldauswertung festgelegt. Sie modelliert den logarithmierten Native-/Generic-Quotienten mit Prefix-Rechenanteil und logarithmierten Grenztensorbytes. Je Gerät werden ganze Architekturen zurückgehalten. Training und Standardisierung verwenden ausschließlich die beiden anderen Architekturen. Die Ridge-Strafe ist lambda=1 bei mittlerem quadratischem Fehler und unbestraftem Intercept. Es gibt keine Merkmals- oder Hyperparametersuche.

| Methode | Verlust k=1 | Verlust k=3 | Verlust k=5 | Exakte Gewinner k=1 / 3 / 5 |
|---|---:|---:|---:|---:|
| Generic | 32,804 % | 23,768 % | 20,448 % | 1 / 2 / 3 von 9 |
| Kalibrierter Generic | 28,319 % | 23,146 % | 15,431 % | 1 / 3 / 4 von 9 |
| Uniform Random, exakte Erwartung | 32,290 % | 15,406 % | 9,104 % | 0,603 / 1,808 / 3,014 erwartete Treffer |
| Neu berechnete Grenztensorbytes-Regel | 32,966 % | 21,747 % | 8,862 % | 1 / 3 / 5 von 9 |

Alle Methoden verwenden dieselben 151 bestätigten Klassifikatorkandidaten in neun gleichgewichteten Gruppen. Die Verbesserung durch Kalibrierung kommt aus DeepX. Auf H10 wird die Auswahl bei allen drei Budgets schlechter. Auf H8 steigt der Verlust bei k=5 von 0 auf 1,825 %. Bei k=3 und k=5 bleibt die exakte Zufallserwartung besser als die Kalibrierung. Die Grenztensorbytes-Regel ist eine neue Anwendung einer festen Formel auf die nachgewiesenen aktuellen Graphen. Historische Graphscores mit anderer Runtime-Referenz werden nicht anhand gleicher Cutnamen in diese Tabelle übernommen.

Die 36 Detektorkandidaten bilden zwölf Gruppen mit je drei Cuts. Generic verliert bei k=1 im Mittel 1,782 %, Uniform Random erwartet 14,091 %. k=3 untersucht die gesamte jeweilige Gruppe. k=5 ist nicht verfügbar, und die Klassifikatorkalibrierung wird nicht auf Detektoren übertragen.

Dies ist eine retrospektive gruppenweise Validierung auf drei bereits bekannten Klassifikatorarchitekturen je Gerät. Sie belegt keine allgemeine Generalisierung. Die Zufallswerte sind Erwartungen über endliche Teilmengen, keine Messfehlerintervalle. k zählt nur Native-Versuche in der Testgruppe. Zusätzlich werden Generic-Messungen und Native-Trainingswerte benötigt. Über alle Folds werden 151 unterschiedliche Native- und 151 unterschiedliche Generic-Konfigurationen verwendet. Deren Akquisition, Kompilierung und Qualitätsprüfung sind nicht kostenlos. Gesamtzeit oder Gesamtkosteneinsparung wurden nicht gemessen.

## Rangumkehr: historische Beobachtung und neue Intervention

Die exakten Oktober-8-Rohbelege reproduzieren RegNet b052 mit 348,301 Generic- und 436,729 Native-FPS sowie b123 mit 228,273 und 1367,112 FPS. Das Verhältnis b123/b052 beträgt damit ungefähr 0,655 bei Generic und 3,130 bei Native. Pro Cut sind dieselben vorbereiteten Eingaben, HEFs und TensorRT-Engines nachgewiesen. Die zwölf Native- und zwölf Generic-Prozesse der vier angefragten Cuts sind separat archiviert.

Die ältere Vier-Cut-Stufenstudie untersucht bei RegNet b059/b123. Sie liefert ein Diagnoseprinzip, aber keinen kontrollierten Gegenversuch an b052. Überlappende Hailo-Antwortzeiten dürfen nicht zur Suffixzeit addiert werden. Queuewartezeiten und Handoffzeiten sind keine isolierten PCIe-Transfermessungen.

Die neue bestätigende Serie verwendet die exakten R14-HEFs, TensorRT-Engines und vorbereiteten Eingabebytes auf H10, aber einen eingefrorenen Ausschnitt der aktuellen Produktquellen. Sie rekonstruiert nicht automatisch den historischen Software- und Gerätezustand. Vor dem ersten bestätigenden Prozess wurden Protokoll, Quellhashes, Profile, Reihenfolge, Endpunkt, Ausschlussregeln und mathematische Auswertungsregeln festgelegt. Zwei getrennte Pilotserien prüfen 16 Eingabezuordnungsläufe und zwei Dauerläufe. Pilotdurchsätze gehen nicht in die folgenden Schätzungen ein.

Die bestätigende RegNet-Matrix enthält zwei Cuts und vier Varianten in fünf vollständigen, innerhalb jedes Blocks randomisierten Prozessblöcken. Jeder der 40 Läufe startet einen eigenen Workerprozess. 30 Sekunden Warmup mit vollständigem Drain gehen einem 60-Sekunden-Annahmefenster voraus. Alle angenommenen Aufgaben werden abgeschlossen. Durchsatz ist die abgeschlossene Aufgabenanzahl geteilt durch die gesamte Messdauer einschließlich Füllung und Drain. CPU-/GPU-Takte, Powerprofil, Affinität, Temperatur und Konkurrenzlast werden vor und nach jedem Lauf geprüft. Alle 40 Prozesse sind zugelassen, keiner wurde ausgeschlossen oder wiederholt.

F1 verändert die Parallelität samt erforderlicher Schedulingpolicy. Generic produktiv verwendet zwei Worker und Queuegröße 2. Native produktiv verwendet acht Hailo-Async-Slots und Queuegröße 3. Die Einzelvariante erlaubt global nur eine ausstehende Aufgabe bis zum fachlichen Abschluss. Bei Native wird zusätzlich die Zahl der Async-Slots auf eins gesetzt. Nur die Slotzahl zu ändern würde diesen Vertrag nicht herstellen. F2 vergleicht die tatsächlichen Generic-/Native-Ketten einschließlich Backend, SDK, Übergabe, Materialisierung und Konvertierung. Die Faktoren sind insofern gekoppelt. Dies ist kein unabhängig geschalteter Einzelkopiertest.

| Variante | b123/b052 | Nominales 95-%-Intervall | SD der Logverhältnisse |
|---|---:|---:|---:|
| Generic produktiv | 0.660350 | [0.655929, 0.664800] | 0.005410 |
| Native produktiv | 3.371337 | [3.355540, 3.387208] | 0.003783 |
| Generic einzeln | 1.028864 | [1.022782, 1.034982] | 0.004775 |
| Native einzeln | 1.028321 | [1.016294, 1.040490] | 0.009475 |

Die Tabelle zeigt geometrische Mittel der innerhalb desselben Blocks gebildeten Verhältnisse b123/b052. Die Streuung ist die Stichprobenstandardabweichung der fünf Logverhältnisse. Die nominalen 95-%-Intervalle verwenden Student-t mit vier Freiheitsgraden. Bei produktiver Parallelität ist b123 unter Generic langsamer und unter Native deutlich schneller. Globale Einzelausführung hebt diese gegensätzliche Rangfolge auf. Beide Runner bevorzugen dann b123 knapp mit einem Verhältnis nahe 1,03. Dies ist keine formale Äquivalenzprüfung der Runner.

Der Native-Schedulingkontrast ist 3,278 [3,229, 3,328], der Generic-Kontrast 0,642 [0,635, 0,649]. Beide vergleichen das Cutverhältnis bei produktiver Parallelität mit dem Cutverhältnis bei Einzelausführung. Ihre Wechselwirkung beträgt 5,108 [4,990, 5,229]. Das ist ein Verhältnis von Verhältnissen, kein Durchsatzgewinn eines einzelnen Cuts. Die unterschiedlichen produktiven Schedules verstärken die Cutpräferenz in entgegengesetzte Richtungen. Die Intervention belegt damit, dass die aktuelle qualitative Rangumkehr vom Zusammenwirken der definierten Schedules und Runtimeketten abhängt.

Die vorab definierte Verlängerung wurde nicht ausgelöst: Die Logintervalle von Generic produktiv, Native produktiv und ihrer Schedulingwechselwirkung schließen jeweils 0 aus. Es gibt keine zusätzlichen ausgewählten Zellen und keine nachträgliche Verlängerung. Die nominalen Intervalle beschreiben diese fünf Blöcke. Das bedingte Studiendesign garantiert keine simultane oder sequenzielle 95-%-Abdeckung für sämtliche Aussagen.

Die vorhandenen Native-Produktzähler aus Läufen ohne zusätzliche Diagnoseinstrumentierung stützen die Diagnose. Über fünf Produktläufe liegt der Median der gesamten Zykluszeit bei b052 bei 2,243 ms, die gemessene serielle Consumerzeit bei 2,218 ms und ihr Anteil an der Messdauer bei 98,98 %. Bei b123 sind es 0,666 ms, 0,613 ms und 92,29 %. Die synchronisierte TensorRT-Zeit einschließlich H2D-Kopie, Ausführung, D2H-Kopie und Stream-Synchronisierung sinkt von 2,020 auf 0,451 ms. b052 zeigt ausgeprägten Rückstau: mediane FIFO-Put-Blockierung 1,675 ms und Queuewartezeit 8,366 ms, gegenüber 0,021 und 0,322 ms bei b123. b123 ist dennoch nicht als ausschließlich prefixlimitiert belegt.

In den Native-Einzelläufen liegen die Zykluszeiten bei 4,977 und 4,846 ms. Die Zeitanteile der gemessenen seriellen Consumerabschnitte sinken auf 43,70 % und 11,26 %. Diese Zähler messen unterschiedliche, teilweise überlappende Pipelineabschnitte. Insbesondere enthält die Prefixantwortzeit der Einzelvariante das Warten auf die globale Freigabe, und Queuewartezeiten schließen Put-Blockierung ein. Die Zeiten werden deshalb nicht addiert oder als isolierte Gerätekosten behandelt. Für Generic liegen in den bestätigenden Reports keine entsprechend getrennten Stufenzähler vor. Diese Werte fehlen ausdrücklich und sind keine Nullen.

Der festgelegte ResNet-Versuch umfasst zwei Cuts, Native produktiv und Native einzeln sowie fünf vollständige randomisierte Blöcke. Alle 20 unabhängigen Prozesse sind zugelassen, ohne Wiederholung oder Ausschluss. Die Intervention wurde unverändert und ohne Nachoptimierung übernommen.

| ResNet-Variante | b095/b002 | Nominales 95-%-Intervall | SD der Logverhältnisse |
|---|---:|---:|---:|
| Native produktiv | 2.054190 | [2.046727, 2.061681] | 0.002932 |
| Native einzeln | 0.830991 | [0.828403, 0.833588] | 0.002512 |
| Schedulingkontrast produktiv/einzeln | 2.471976 | [2.461054, 2.482945] | 0.003566 |

Die produktive Native-Ausführung bevorzugt b095, die globale Einzelausführung b002. Beide Cutverhältnisse und der Schedulingkontrast liegen mit ihren nominalen Intervallen eindeutig auf der jeweiligen Seite von 1. Die im Primärfall festgelegte Native-Intervention verändert somit auch im zweiten bekannten Fall die Cutrangfolge. Das bestätigt die Übertragung dieses begrenzten Schedulingbefunds. Der Versuch enthält keine neuen Generic-Dauerläufe und prüft weder die vollständige zweite Generic-/Native-Rangumkehr noch eine zweite Faktorenwechselwirkung.

Auch die ResNet-Stufenzähler passen zur Intervention. Im produktiven Schedule beanspruchen die gemessenen seriellen Consumerabschnitte bei b002 im Median 98,71 % der Messdauer, bei b095 89,98 %. Die FIFO-Put-Zeit beträgt 1,445 gegenüber 0,0126 ms. Unter Einzelausführung liegen die Gesamtzyklen bei 5,123 und 6,155 ms und die Queuewartezeiten bei ungefähr 0,04 ms. Diese deskriptiven Prozessmittel unterstützen die Schedulingdiagnose, sind aber weiterhin keine isolierten Prefix- oder Transferkapazitäten. Alle Einzelwerte stehen in `results/mechanism_stage_diagnostics_runs.csv` und `_summary.csv`.

Die zwei Paare wurden wegen bereits bekannter Rangwechsel ausgewählt. Die Befunde erlauben keine Häufigkeitsaussage über alle Architekturen. Sie identifizieren weder einen einzelnen Kopier-, Layout- oder Konvertierungsbeitrag noch eine historische Softwareursache. Die Schlussfolgerung trägt für die nachgewiesenen Artefakte, den kontrollierten aktuellen Gerätezustand und den offen dokumentierten Eingriff in die produktiven Runnerketten.

Die 16 vorab getrennten H10-Zuordnungsprozesse prüfen je 32 gemischte Requests über zwei unterschiedliche vorbereitete Testinputs. Alle acht Vergleiche zwischen Runnerketten und alle acht Vergleiche zwischen Schedules sind für beide Inputs bytegleich. Die ursprünglichen funktionalen Referenzen der vier Cuts werden ebenfalls exakt erreicht. Das ist kein neuer 5.000-Bilder-Qualitätslauf und erweitert die historische all-450-Zuordnungsdeckung nicht pauschal. Die acht exakt gebundenen R14-Konfigurationen mit unterschiedlichen Datensatzeingaben bleiben von diesen neuen Tests an der aktuellen kontrollierten Runtime getrennt.


## Konsequenz für das Paper

Die drei vorhandenen Forschungsfragen reichen aus. Der Audit ergänzt die Methodenabsicherung. Die Kalibrierung ergänzt die vorhandene Budgetdarstellung, einschließlich ihrer schlechteren Geräteergebnisse und Kostenbegrenzung. Die kontrollierte Rangumkehrstudie soll eine bestehende Mechanismuserklärung ersetzen. Compilerdiagnosen, Versionsketten, vollständige Prozesslisten und die ResNet-Fallstudie gehören überwiegend ins Supplement. Das Manuskript wird in diesem Auftrag nicht verändert.

## Quellen, Reproduktion und unabhängige Prüfung

Die historische Referenz ist Ergebnissnapshot `1b01b220b2a80af7e2e3fa186f777a0676582854`. Das unveränderte R14-Paket liegt unter `input/R14/`. Das installierte Tool ist Version 2.95.5 auf Git-Stand `db729b9fcde00e4bcadf9200d43282977d7bf1cc` mit bereits vorhandenen Benutzeränderungen. Diese Änderungen bleiben erhalten. Die neue Geräteuntersuchung verwendet separat kopierte und gehashte Produktquellen im Auftragsverzeichnis. Branch, lokale Commits und Diffs dokumentieren den Diagnosecode.

`EVIDENCE_AUDIT.csv` bindet alle 450 Konfigurationen. `FLAG_RESOLUTION.csv` erhält die ursprünglichen Einschränkungen und nennt die tragenden Nachweise. Die kompakte, verlustfrei komprimierte Quellenprojektion unter `analysis/audit_inputs/` ermöglicht den Audit ohne Gerätezugang. Große Originalartefakte werden über Pfad und SHA256 referenziert. `results/audit_independent_review.json` und `results/audit_final_validation.json` prüfen Identität, Herkunft und numerische Einschlussentscheidung unabhängig.

`results/calibration_protocol.json` enthält die vor der Foldauswertung fixierte Formel. `results/calibration_folds.csv`, die Vorhersage- und Metriktabellen sowie `results/calibration_independent_review.json` legen Parameter, Trainings-IDs, Vorhersagen und getrennte Tests offen. Die eigenständige Nachrechnung prüft die 18 Fits und 302 Vorhersagen der separat ausgewiesenen R14- und bestätigten Kohorten. Beide nutzen dieselben 151 Klassifikatorpaare und sind keine unabhängigen neuen Messungen.

Das Hauptprotokoll hat SHA256 `bff5aff0a26d8148256a688bccd2dd7e254092d42fcafb36b59f486edb96d9fd`. Die implementierte Statistiksoftware ist zusätzlich unter `receipts/ANALYSIS_CODE_PIN.json` gebunden. Diese zusätzliche Implementierungsquittung entstand nach Start des ersten bestätigenden Prozesses und vor dem ersten vollständigen Block. Die mathematischen Regeln standen bereits im zuvor eingefrorenen Protokoll. Die Auswertung verwendet unveränderliche, gehashte Journalabbilder. Zwei eigenständige Prüfer kontrollieren zum einen Rohdurchsätze, Blockverhältnisse und t-Intervalle und zum anderen Ausführungsreihenfolge, geladene Quellen, Gerätezustand und Abschlussvertrag. Der Rechenprüfer importiert die Hauptauswertung nicht.

Die endgültige Bestätigungsauswertung steht in `results/mechanism_confirmation.json`, `_summary.csv` und `_blocks.csv`. Der finale Journal-SHA256 ist `8dafb76fcb92c94314a52e43fb06282d87200dc2900416af823b61786e079fa8`. `results/mechanism_results_independent_review.json` bestätigt alle 60 Prozesse und 210 numerische Vergleichswerte unabhängig. `results/mechanism_execution_independent_review.json` bestätigt 60 unterschiedliche Worker-PIDs und 120 Zustandsbeobachtungen vor und nach den Läufen ohne Prüfabweichung. Die Starttemperaturen lagen zwischen 47,718 und 63,218 °C. Endtemperaturen von 49,000 bis 65,687 °C sind gemäß Protokoll deskriptiv, kein nachträgliches Ausschlusskriterium. Die finale Grafik unter `figures/mechanism.pdf` und `.svg` verwendet ausschließlich die fünf RegNet-Blöcke sowie getrennte historische Referenzpunkte. Ihre Daten und Quellen sind neben der Grafik gebunden.

`CLAIM_STATUS.csv` enthält die Entscheidungen pro Aussage samt Dateihashes. `README.md` nennt die tatsächlichen Offline-Befehle, `RESUME.md` den idempotenten Wiederaufnahmeweg und `RERUN_PLAN.csv` ausgeführte, wiederverwendete beziehungsweise nicht erforderliche Messungen. `SHA256SUMS` prüft das Reviewpaket. `PACKAGE_CHECK.json` neben dem ZIP dokumentiert die Archivprüfung und die identische Kopie im Downloadverzeichnis. Das Manuskript wurde nicht geändert. Es erfolgten kein Push, Merge oder Release.
