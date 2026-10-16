# YOLOv7: Split-Reparatur und Orin-Abgleich

Der langsame H10-/DeepX-Splitpfad führte noch dichten CPU-Decode und wiederholte Payload-/Quellprüfungen im seriellen Consumer-Tail aus. Der reguläre Worktree einschließlich Mirrors/Dispatcher ist repariert und mit dem vorhandenen Fast-Completion-Pfad verbunden. Alle neun Splitfälle wurden anschließend erfolgreich in je drei getrennten Prozessen gemessen. Die 18 gültigen Full-Repeats werden nach drei aktuellen unveränderten TRT-Full-Kontrollen weiterverwendet. Energie bleibt STOP/NA.

## Gemessene Ursache und Konfiguration

**Gesichert – Ursache des langsamen H10-Abschlusses.** Im identisch abgegrenzten b066-Diagnosefenster (100 Warmups, 100 Abschlüsse, ein Prozess) sinkt der CPU-Abschluss von 63.599 auf 6.614 ms/Bild: **9.62×**. Das ursprüngliche dichte Decoding beansprucht 48.802 ms, der Payloadhash weitere 7.829 ms. Der Kandidat verwendet den vorhandenen Fast-Pfad mit geprüftem Abschlussinhalt; seine Sparse-Decodierung einschließlich Finitprüfung dauert 2.964 ms. Payload- und Quelldateihashes entfallen im gemessenen Abschluss; ein kleiner kanonischer Metadatenhash bleibt (0.103 ms/Bild). Exklusive Funktionszeiten, ihre Elternintervalle und CUDA-Zeiten werden nicht doppelt addiert.

**Gesichert – verbleibende Pipelinegrenze.** H10 wechselt von 73.531 auf 19.073 ms/Bild im instrumentierten Gesamtfenster (3.86×). FIFO-Putblockierung sinkt von 67.488 auf 0.027 ms, Queuealter von 281.435 auf 0.192 ms. Danach begrenzt der beobachtete Producerzyklus von 18.919 ms die Pipeline; die tatsächlich geleistete serielle Consumerarbeit beträgt 15.973 ms. Die Hailo-Submissionlatenz von 145.137 ms bei inflight 8 ist keine isolierte NPU-Ausführungszeit. H8 b066 überlappt Prefix, P2 und Postprocessing: P2 gesamt 8.811 ms, Callback 3.499 ms, Messfenster 8.909 ms/Bild. Der topologische Unterschied bleibt; er erklärt den jetzigen H10-Prefixengpass allein nicht. Diese Diagnosen liefern keine Final-FPS.

**Gesichert – H8 b044 langsamer.** Der gültige Dreiermedian sinkt von 53.460813 auf 47.800201 completed-FPS (-10.59%). Im Python-VStreams-FIFO ist Completion seriell in P2; der Tail wächst im Mittel um 2.115 ms, der TRT-Abschnitt nur um 0.079 ms. Die neue kurze Diagnose misst zwei vollständige Finitprüfungen: 0.950 ms in der Kanonisierung und 0.892 ms im gemeinsamen Sparse-Decoder, zusammen 1.842 ms. Der instrumentierte CPU-Tail beträgt 6.068 ms gegenüber 5.339 ms uninstrumentiertem Finalmedian; Instrumentierung und Kurzfenster beeinflussen den Vergleich. Die zusätzliche Guardarbeit ist damit konkret gemessen. Ohne gleich instrumentierten alten b044-Lauf wird die historische Differenz nicht vollständig einzelnen Funktionen zugerechnet. Der b066-C++-Pfad überlappt seinen Postprocessor und reagiert anders auf Hostmehrarbeit. Die doppelte Guardprüfung bleibt im gemessenen Kandidaten bestehen. Die Regression bleibt in der Finalmatrix erhalten; keine Produktänderung wurde daraus abgeleitet. Details: [H8-B044-Vergleich](H8_B044_REGRESSION_ANALYSIS.md).

**Gesichert – Full-Restdifferenz und sichtbare Konfiguration.** Die aktuellen uninstrumentierten Full-Kontrollen liefern H8 51.755756, H10 51.347944 und DeepX 47.439887 completed-FPS; jeweils 100 Warmups / 1000 Abschlüsse. DeepX liegt damit 7.61% unter H10 bzw. benötigt 1.604 ms mehr pro Bild. Modell-ONNX, Full-Buildargv, FP16-Option, Workspace 4096 sowie statische FLOAT-Ein-/Ausgabeformen sind gleich; Full verwendet keine unterschiedliche Split-Bridge. Die Orin NX 16GB-Module, L4T 36.4.7, Kernel und aktive MAXN_SUPER-Definition stimmen überein. In den Full-Lastsamples stehen CPU 1984 MHz / GPU 1173 MHz konstant und die neuen OC-Zählerdeltas auf 0. Konfigurierte Lüfter-Defaultprofile unterscheiden sich (H8 cool / H10 max / DeepX quiet), ohne damit eine FPS-Ursache zu belegen.

**Gesichert – separate Loaderprobe.** Alle drei Probeprozesse wählen `_CudaCompat`: H10 lädt `libcudart.so.12.9.79` (Runtime-API 12.9), H8 und DeepX `libcudart.so.12.6.68` (Runtime-API 12.6); Driver-API jeweils 12.6. Das ist eine aktuelle Probe desselben Python-Ladepfads, keine rückwirkende Beobachtung eines Messprozesses und kein Nachweis für den H8-C++-Split-SO. H8 und DeepX teilen die CUDART-Version bei unterschiedlicher Full-FPS; die Versionsabweichung allein erklärt daher nicht die Trennung. Die Beschleuniger-PCIe-Endpunkte melden im Snapshot alle 8.0 GT/s × 4; ein abweichender Linkmodus ist dort nicht belegt. Exakte Bibliothekspfade, Module und Umgebung: `configuration/*-runtime-probe.json` und `*-pci-driver.json`.

**Plausibel, nicht kausal bewiesen.** Der historische trtexec-Export meldet bereits H8≈15.065, H10≈15.116 und DeepX≈16.744 ms Latenz ohne denselben completed-detection-Endpunkt. Das ist mit einem Anteil im TRT-Ausführungspfad vereinbar. Identische damalige Inputwerte und Lastzustände sind jedoch nicht belegt. Beim ursprünglichen DeepX-Split beanspruchen Prefix 33.407 ms und Mapping 4.123 ms; diese getrennten Messwerte begründen die Prüfung des verbleibenden Prefix-/Transferanteils, keine daraus errechnete finale FPS.

**Unbekannt.** EMC wurde nicht exponiert; debugfs war wegen fehlender lokaler Rechte unlesbar, die Hardware erreichbar. Interne Tactics, Layerpräzision/-platzierung, Timingcache-Bytes und Buildzeitpunkt-Takte fehlen. Unterschiedliche Enginehashes belegen nur unterschiedliche serialisierte Bytes. Die tatsächlich geladenen Bibliotheken früherer Messprozesse und des H8-C++-Split-SO bleiben unbekannt; die separate Probe des Python-NativeTRT-Loaderpfads ist oben gesondert ausgewiesen. Die 1-Hz-Lastabtastung löst kurze Zwischenereignisse nicht auf. Damit ist keine abschließende Einzelursache für den Full-Abstand 47 gegen 51 FPS bewiesen.

**Abgeschlossene Lastbeobachtung.** Der letzte Telemetrieexport umfasst 38 eindeutige Fenster: 35 mit Rückgabecode 0 (27 Finalrepeats, drei Full-Kontrollen, fünf Diagnosen) und drei erhaltene Fehlversuche. Alle 27 akzeptierten Finalrepeats haben beobachtete CPU 1984 MHz / GPU 1173 MHz und OC-Zählerdeltas 0. Temperatur-/Lüfterverläufe stehen im Konfigurationsvergleich; EMC bleibt ungemessen. Dies ist eine 1-Hz-Beobachtung der Subprozessfenster, keine Garantie für jeden Zeitpunkt zwischen den Samples.

Belege: [Stage-Profil](SPLIT_STAGE_PROFILE.md), [TensorRT-Buildvergleich](configuration/TRT_BUILD_COMPARISON.md), [Konfiguration und Last](ORIN_CONFIG_COMPARISON.md); zugrunde liegende Originalreports und importierte Quellhashes sind dort referenziert. Die Finalmatrix enthält die 27 separat geprüften Splitrepeats; Diagnosewerte bleiben davon getrennt.


H10 und DeepX zählen weiterhin erst nach echter vollständiger CPU-Completion. H10 inflight=8 betrifft den Prefix; es erzeugt keinen Overlap innerhalb des seriellen TRT-/CPU-Consumer-Tails. DeepX verwendet im gebundenen Originalrunner einen synchronen `engine.run()`/`Run`-Aufruf und eine eigene zusammenhängende Boundary-Kopie. Ein Python-Output-Pollingloop ist dort nicht vorhanden; internes SDK-Scheduling bleibt unbekannt. H8 b009/b044 sind schnelle Python-VStreams-Pfade, b066 überlappt drei Stufen über die bestehende Concurrent-Pipeline. Die Erklärung folgt ausgeführter Arbeit und Overlap, nicht einer pauschalen Sprachbewertung.

Historische Quellen wurden anhand vollständiger SHA256 geprüft. Die vorher fehlende tatsächliche DeepX-Splitquelle und Abhängigkeiten beider ursprünglicher Roots sind unter `bound_sources/deepx_root0` und `deepx_root1` samt `REMOTE_SOURCE_CAPTURE.json` enthalten. Eine Korrektur gegenüber der Auftragsannahme: Der erfolgreiche historische H8-b066-Commandcontract bindet `artifacts.native_three_stage` ausdrücklich an SHA256 `453e6bff8ba5d7635614cc3eb3e56fcf53230b68857af4891384bbfbbb3ea7fa`. Diese konkrete Bindung gilt nicht pauschal für b009/b044.

## Finale Performance

Je Split: 100 fertige Warmups, 1.000 fertige Tasks, drei unabhängige Prozesse. Keine Stage-Instrumentierung; begleitende etwa 1-Hz-Telemetrie. Neue Modell-/Engine-Builds: null. Alle Zeiten/FPS beruhen auf dem vollständigen Taskfenster, einschließlich Drain bis zum letzten Abschluss.

| Setup | Cut | FPS 1 | FPS 2 | FPS 3 | Median FPS | / TRT Full | / Accelerator Full |
|---|---|---:|---:|---:|---:|---:|---:|
| H8 | b009 | 42.868121 | 42.777702 | 42.851710 | 42.851710 | 0.827548 | 1.361354 |
| H8 | b044 | 47.765246 | 47.800201 | 47.836383 | 47.800201 | 0.923113 | 1.518563 |
| H8 | b066 | 112.939567 | 112.492794 | 112.454680 | 112.492794 | 2.172450 | 3.573779 |
| H10 | b009 | 51.393191 | 51.357901 | 51.352162 | 51.357901 | 0.997617 | 4.170591 |
| H10 | b044 | 64.500526 | 64.128738 | 64.726423 | 64.500526 | 1.252909 | 5.237856 |
| H10 | b066 | 53.350448 | 53.374984 | 52.993817 | 53.350448 | 1.036321 | 4.332398 |
| DeepX | b009 | 33.512406 | 35.043370 | 33.866133 | 33.866133 | 0.715689 | 1.475921 |
| DeepX | b044 | 49.091787 | 48.790077 | 48.758800 | 48.790077 | 1.031075 | 2.126321 |
| DeepX | b066 | 30.083126 | 30.594221 | 30.640496 | 30.594221 | 0.646544 | 1.333327 |

Alle neuen Splitfälle erhalten `reference_close`. Referenz für den Speedup ist auf jedem Setup der schnellste technisch vergleichbare Full **vor** Qualitätsfilterung, hier TRT Full. Gegenüber Accelerator Full wird zusätzlich ausgewiesen. Kleine Quotienten über 1 sind keine statistisch gesicherte Überlegenheitsbehauptung.

Wiederverwendete Fulls, ohne Einmischen der aktuellen Kontrollwerte:

| Setup | Full-Pfad | FPS 1 | FPS 2 | FPS 3 | Median | Qualität |
|---|---|---:|---:|---:|---:|---|
| H8 | native_full_hailo8 | 31.477269 | 31.446099 | 31.498550 | 31.477269 | accuracy_loss |
| H8 | native_full_tensorrt | 51.781526 | 51.793755 | 51.723216 | 51.781526 | reference_close |
| H10 | native_full_hailo10h | 12.314299 | 12.250686 | 12.365826 | 12.314299 | accuracy_loss |
| H10 | native_full_tensorrt | 51.059922 | 51.480597 | 51.601523 | 51.480597 | reference_close |
| DeepX | native_full_deepx | 23.001767 | 22.882797 | 22.945769 | 22.945769 | reference_close |
| DeepX | native_full_tensorrt | 47.361123 | 47.319602 | 47.300755 | 47.319602 | reference_close |

Aktuelle separate Full-Kontrollen: H8: 51.755756 FPS (-0.050% zum bisherigen Median); H10: 51.347944 FPS (-0.258% zum bisherigen Median); DeepX: 47.439887 FPS (+0.254% zum bisherigen Median). Gleiche isolierte optimierte Runtime, Engine, vorbereitete Inputbytes, Endpunkt und exakte gespeicherte Endartefakte; sichtbare Betriebsbedingungen und Lastbelege passen. Der geringe beobachtete Drift erfordert keine erneute komplette Full-Serie. Die sechs Full-Konfigurationen stammen aus dem vorherigen Performanceauftrag am selben Tag; nur die neun Splitkonfigurationen sind in diesem Auftrag neu gemessen.

Historischer Vergleich zur Ursachenorientierung:

| Setup | Cut | Historischer Median | Neuer Median | Quotient neu / historisch |
|---|---|---:|---:|---:|
| H8 | b009 | 47.299004 | 42.851710 | 0.905975 |
| H8 | b044 | 53.460813 | 47.800201 | 0.894117 |
| H8 | b066 | 113.653846 | 112.492794 | 0.989784 |
| H10 | b009 | 12.587491 | 51.357901 | 4.080075 |
| H10 | b044 | 13.756416 | 64.500526 | 4.688759 |
| H10 | b066 | 12.860551 | 53.350448 | 4.148380 |
| DeepX | b009 | 14.086139 | 33.866133 | 2.404217 |
| DeepX | b044 | 14.188628 | 48.790077 | 3.438675 |
| DeepX | b066 | 14.946793 | 30.594221 | 2.046875 |

Diese Quotienten vergleichen unterschiedliche Kohorten (historisch drei Runtimeinstanzen in einem Prozess, jetzt drei Prozesse). Der kontrollierte kausale Softwarevergleich ist das kurze H10-b066-Profil auf demselben Gerät, nicht die Behauptung, alle historischen Faktoren seien gleich gewesen. Historische Werte bleiben unverändert erhalten.

## Reparatur und regulärer Start

`native_detection_postprocess.py` wählt bei `auto` nur für einen attestierten YOLOv7-Rawhead-Vertrag die vorhandene `FastDetectionCompletionRuntime`. `native_three_stage.py` verwendet dafür den bereits validierten exakten Sparse-Decoder aus dem Harness. Die vollständige Finitprüfung bleibt erhalten; ein konkret gefundenes NaN-/Inf-Loch in früh verworfenen Zeilen ist behoben. Dense/Strict bleiben explizit verfügbar. Vertrag, Modus und tatsächliche Quellen werden vor und nach geprüft; bei DeepX zusätzlich der wirklich importierte H10-NativeTRT-Helper.

H10-/DeepX-Runner und normaler Dispatcher reichen den Modus korrekt weiter. Rawdump und striktes Postflight-Oracle beziehen sich auf einen eigenen Snapshot des letzten gemessenen Outputs. Scheduling, Pufferownership, NMS, Klassen, Geometrie und Messgrenzen wurden nicht geändert. Es wird ehrlich `postflight_oracle_sentinel` verwendet, kein erfundener per-Frame-Hashnachweis. Ein kleiner Metadaten-JSON-Hash bleibt pro Frame bestehen.

H8 b066 unterstützt regulär die angeforderten drei getrennten 100/1000-Prozesse mit je einer Wiederholung und Wiederverwendung des hashgeprüften vorhandenen nativen SO unter `--no-build`. H8 b009/b044 verwenden den bestehenden Python-Completed-Task-Pfad. Ein isolierter Benchmarkset-Root verhindert, dass der normale H8-Reportschreiber historische Ergebnisse überschreibt. Die C++-Clockdomain bleibt wahrheitsgetreu `steady_clock_ns:runtime_report_local`; unabhängige Prozesse werden durch echte PIDs, monotone Prozessstarts und Runtime-IDs belegt, nicht durch erfundene Clocklabels.

Die Shared-Completion, Concurrent-Helper, vier Runner jeweils mit Mirror und der reguläre H8-Commandvalidator sowie einschlägige Tests sind in `parity/validated_split_fix.patch`, den versionierten Paritäts-/Runtime-Manifesten und dem finalen Worktree-Diff dokumentiert. Nach einem echten H8-Qualitätsjoinfehler wurde für H8 zusätzlich der aktuelle normale Commandvalidator eingebunden und sein eng begrenzter b066-Guard auf eine oder drei Wiederholungen bei unverändert 100 Warmups/1000 Tasks erweitert. Die zuvor erfolgreichen H10-/DeepX-Runtimes und ihr ursprüngliches Manifest bleiben unverändert. Der bestehende korrigierte YOLO-Harness ist unverändert mit enthalten. Vorherige Full-/Energie-/Recovery-Änderungen sind erhalten; kein Commit/Push. Die regulären Startpfade des geänderten Worktrees wählen den Fix bereits. Die Hardwareabnahme erfolgte in isolierten Candidate-Runtimes; installierte Stammruntime und bestehende gemeinsame Gerätestände wurden nicht global ersetzt. Zur Nutzung außerhalb des Worktrees ist die geprüfte Version über den vorhandenen normalen Runtime-Sync/Deploymentpfad zu übernehmen. Eine allgemeine GUI-Kampagnenabnahme wurde nicht durchgeführt.

H8 projiziert seine interne Fast-Quellbindung nicht als neues Top-/Repeat-Feld `completion_runtime_source_binding`. Sein interner Before-/Afterguard und die vollständige externe Runtimeprüfung liegen vor; fehlende Felder werden nicht nachträglich erfunden. H10/DeepX liefern die neue Projektion. Statische Auswirkungen anderer Modellfamilien: `parity/other_model_family_static_scope.json`. Andere Modelle bleiben strict, Klassifikation separat; kein allgemeiner H10-/DeepX-Modellbefund wird daraus abgeleitet.

## Abnahme, Fehlbelege und Grenzen

142 gezielte lokale Tests bestanden (141 im fokussierten Lauf, ein weiterer Helper-Drifttest). Nach der zusätzlichen H8-Guardkorrektur bestanden 17 fokussierte Commandtests und acht normale Qualityconsumer-Regressionen; der alte fehlende Producerzweig wird reproduziert und falsche Counts bleiben abgelehnt. Diese separaten Testläufe werden nicht als disjunkte Gesamtmenge ausgegeben. Acht ursprüngliche Profilregressionen und drei zusätzliche Prüfungen der b044-Finit-Instrumentierung bestanden; disjunkte Stageanteile ergeben vollständig 100%. Acht lokale Roh-Latenzprüfungen sichern die korrigierte H8-Reportauswertung. Vier echte CLI-Help-Aufrufe sowie die H8-Argumentparser/Admission-/Quellabschlussprüfung bestanden. Der erste lokale Testlauf mit 53 PASS/3 FAIL bleibt erhalten: Drei bestehende Tests verlangen das private NumPy-2-Attribut `np._core`, das die tatsächliche lokale NumPy-1.26-Umgebung nicht bietet. Diese drei wurden im fokussierten Lauf ausdrücklich ausgelassen; es wird kein vollständig grüner Gesamttestlauf behauptet.

Fünf repräsentative Rawsets (zwei bestehende Canarys, neue Originalprofile H10/DeepX/H8) sind Strict/Bound-dense/Fast-exakt. Der H10-Nachherprofil-Sentinel und alle 27 neuen finalen Split-Sentinels bestehen zusätzlich die normalen Command-/Completion-/Fast-/Dumpprüfungen, den jeweiligen Downstream und einen unabhängigen Strict-Replay. Die erhaltenen 18 Full-Sentinels waren bereits exakt zu ihren Originalen; alle drei aktuellen Full-Kontrollen bewahren diese Artefakte. Dies ist endliche Paritätsevidenz, kein neuer COCO-Test und keine per-Frame-Bytegleichheitsbehauptung.

Alle Messversuche, vollständigen argv/env, Starts und Fehler sind unter `jobs`, `split_final`, `full_controls` und `profiling` erhalten. Vor dem ersten H10-b066-Start wurde ein lokaler Controller-Path-Typfehler korrigiert. Zwei H10-b009-Vorprüfungen und eine DeepX-b009-Vorprüfung stoppten wegen fehlender historischer Remote-Dateien, bevor ein Repeat startete. H10 b009 erreichte danach den Runner, dessen Completion-Vertragsprüfung wegen der ebenfalls fehlenden `output_contracts.json` scheiterte. Dieser Fehler wurde offline mit der versiegelten Runtime exakt reproduziert; mit der archivierten Originaldatei löst derselbe Resolver den ursprünglichen gültigen Endpunkt auf. Für alle drei b009-Fälle wurden die nötigen Benchmark-/Output-/Split-/Schema-/Qualitymetadaten bytegleich aus dem Originalarchiv in neue isolierte Pfade gestellt; bestehende Modelle, Bildinputs und Engines bleiben gebunden. Historische reine Outputbelege werden lokal geprüft. Neue Ergebniszweige erhalten die Fehlstarts; keine Hash- oder Qualitätsprüfung wurde abgeschwächt.

H8 b066 hatte zunächst einen SDK-Importfehler, weil im vorbereiteten Plan die historisch gebundenen `SPLITPOINT_EXTRA_SITES` fehlten. Der tatsächliche normale Runnerimport mit diesem prozesslokalen Parameter wurde anschließend erfolgreich geprüft (System-Python, NumPy1.26.4, TRT10.3, HailoRT4.20); keine Paketinstallation. Der nächste Prozess schloss 1000 Tasks ab, scheiterte jedoch am normalen Qualitätsjoin des veralteten Commandvalidators. Seine 34 Zwischenartefakte wurden unverändert gesichert und werden nicht als akzeptierter Finalrepeat ausgegeben. Die beschriebene enge reguläre Validatorreparatur wurde vor neuen H8-Messungen geprüft. Der erste erfolgreich abgeschlossene Prozess mit dem neuen Guard wurde zunächst lokal wegen einer Formaterwartung abgewiesen: H8 liefert reguläre rohe Latenzpaare statt vorab aggregierter count/status-Felder. Der normale Produktvalidator bestätigt 1000 vollständige Paare ohne Fehler. Der lokale Reader wurde auf diesen normalen Validator umgestellt; der bereits vorhandene gültige Repeat blieb bytegleich erhalten und wurde ohne Hardwarewiederholung übernommen. Diese Fehler sind keine Hardware-Nichterreichbarkeit. Controller-Vorversionen ab der expliziten Versionierung sind unter `orchestration_versions` erhalten; für frühere lokale Korrekturen werden keine zeitgleichen Snapshots erfunden.

EMC/debugfs, `jetson_clocks --show` und die aktive Lüfterdaemon-Abfrage waren wegen fehlender Rootrechte nicht vollständig zugänglich. Das sind Berechtigungsgrenzen auf erreichbaren Geräten. Es wurden keine Leistungs-/Lüfter-/Treiber-/Paketänderungen vorgenommen. Low-rate-Telemetrie belegt nur ihre erfassten Samples. CUDA-Versionen und unterschiedliche Enginebytes werden nicht als alleinige bewiesene Ursachen ausgegeben. Vollständige konkrete Rohbelege und Auslassungsgründe stehen in `ORIN_CONFIG_COMPARISON.md` und `configuration/TRT_BUILD_COMPARISON.md`.

## Paper, Energie und Übergabe

Performanceentscheidung und kurzer englischer Papertext: [PAPER_READINESS.md](PAPER_READINESS.md). Export mit allen Einzelwerten, Kohorten, Qualitätsstatus und Quellenbindungen: [PAPER_PERFORMANCE.csv](PAPER_PERFORMANCE.csv), detailliert [PAPER_PERFORMANCE_MATRIX.json](PAPER_PERFORMANCE_MATRIX.json). Die LaTeX-Haupttabelle wurde nicht verändert.

Energie aller 15 optimierten Full-/aktuellen Splitvarianten bleibt `not_measured`/NA; genaue Restliste: [ENERGY_REMAINING.csv](ENERGY_REMAINING.csv). Alte Joulewerte bleiben separat. Keine neuen u.RECS-Starts, keine Hochrechnung aus FPS, keine Budget-/STOP-Änderungen. Der fehlende dritte historische H8-Vorher-Repeat bleibt ein eigenständiger offener Energiepunkt; zwei gültige Repeats, alle fünf physischen Starts und drei Transportfehler bleiben belegt.

Nachmessungen und Reparatur sind abgeschlossen. Offen sind die gesondert zu autorisierende Energiearbeit, ein regulärer Rollout für die Nutzung außerhalb des Worktrees, die nur mit zusätzlichem EMC-/Tactic-/Versionsvergleich abschließend klärbare Full-Restdifferenz sowie eine mögliche Zusammenführung der doppelt ausgeführten Finitprüfung. Letztere ist als gemessener Aufwand dokumentiert; sie wurde in dieser gültigen Runtimeversion nicht nachträglich entfernt und wäre ein neuer, erneut zu validierender Betriebspunkt. Finale Ressourcen-/Quellen-/Budgetprüfung: `FINAL_VERIFICATION.json`; aktueller Gitstatus und Diffstat: `final_git_status.txt`, `final_git_diff_stat.txt`. Das Review-ZIP enthält Reports, tatsächliche Quellen, Rohdaten, Patches, Manifest mit SHA256 und einen unabhängig ausführbaren Archivprüfer; große unveränderte Modell-/Engine-Dateien sind durch Pfade, Hashes und Buildreceipts repräsentiert.
