Die Tabelle enthält kurze instrumentierte Diagnosen mit jeweils 100 vollständig verworfenen Warmups, 100 abgeschlossenen Detektionen und einem Prozess. Die ersten vier Diagnosen betreffen b066, die letzte H8 b044. Die Tabelle ist keine finale FPS-Nachmessung. Sources und tatsächlich importierte Modulpfade/Hashes stehen in den jeweiligen Profilbelegen.

| Pfad | Abschluss CPU ms | Decode inkl. interner Guards ms | Payload-SHA ms | TRT synchronisiert ms | Fenster / Bild ms | Diagnose completed/s |
|---|---:|---:|---:|---:|---:|---:|
| H10 original strict | 63.599 | 48.802 | 7.829 | 8.943 | 73.531 | 13.600 |
| DeepX original strict | 69.528 | 54.370 | 8.004 | 9.071 | 81.031 | 12.341 |
| H8 original fast | 3.386 | 1.665 | 0.000 | siehe C++-Stufe | 8.909 | 112.243 |
| H10 candidate fast | 6.614 | 2.964 | 0.000 | 8.860 | 19.073 | 52.429 |
| H8 b044 candidate fast | 6.068 | 2.659 | 0.000 | 15.262 | 22.074 | 45.302 |

Die exklusiven CPU-Zeilen partitionieren ausschließlich den Completion-Aufruf. Jede instrumentierte Kindfunktion wird vom Elternwert abgezogen; der Rest enthält übrige Arbeit und Instrumentierungsaufwand. CUDA H2D/Engine/D2H liegen innerhalb des synchronisierten TensorRT-Hostintervalls und werden diesem nicht noch einmal addiert. Producer und Consumer laufen gleichzeitig; ihre Mittelwerte ergeben addiert keine Laufzeit. Die CSV weist deshalb Zeitdomäne, Überlappung, Completion-Anteil und normierten Anteil am Messfenster separat aus. Bei Queue- und Submission-Latenzen ist dieser normierte Quotient keine Ressourcen-Auslastung und kann über 100% liegen.

H10 original strict: Quelle `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/profiling/hailo10/accepted_profile.json`. Exklusive CPU-Completionanteile:

| Stufe | ms/Bild | Anteil Completion |
|---|---:|---:|
| canonical_json_sha | 1.1309 | 1.78% |
| canonical_records | 0.2726 | 0.43% |
| dense_decode_filter | 48.8016 | 76.73% |
| frozen_processor | 0.1114 | 0.18% |
| harness_geometry_dispatch | 0.7485 | 1.18% |
| head_canonicalization | 1.1350 | 1.78% |
| implementation_checks | 0.8919 | 1.40% |
| nms | 1.0440 | 1.64% |
| payload_content_sha | 7.8290 | 12.31% |
| receipt_artifact | 0.0272 | 0.04% |
| result_conversion | 0.0085 | 0.01% |
| source_contract | 0.3656 | 0.57% |
| source_file_sha | 0.9561 | 1.50% |
| tensor_signature | 0.1355 | 0.21% |
| uninstrumentierter Rest | 0.1411 | 0.22% |

Der serielle Consumeranteil aus Inputkopie, synchronisiertem TensorRT und Completion beträgt 72.944 ms/Bild. Das Messfenster entspricht 73.531 ms/Bild; die Differenz 0.587 ms/Bild umfasst Füllen/Leeren, Scheduling und Arbeit außerhalb dieser Wrapper. Sie ist keine isoliert gemessene GPU-Leerlaufzeit.
H10 wartet pro Übergabe 67.488 ms beim FIFO-Put; der Consumer sieht 281.435 ms Warteschlangenalter. Die gemeldeten 476.766 ms Hailo-Latenz messen Submission bis Einsammeln und enthalten Backlog. Bei inflight8 und queue_depth3 sind sie kein Beleg für entsprechend langsame reine NPU-Ausführung. Producer-Durchschnittszyklus 70.672 ms, Consumer-Durchschnittszyklus 73.530 ms.
Pro Completion wurden 8,568,000 Payloadbytes gehasht; zusätzlich 603,102 Quelldateibytes in 6 Datei-Hashaufrufen und 10 kanonischen JSON-Hashaufrufen. JSON-Bytes werden zur Instrumentierung nicht erneut serialisiert.

DeepX original strict: Quelle `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/profiling/deepx/accepted_profile.json`. Exklusive CPU-Completionanteile:

| Stufe | ms/Bild | Anteil Completion |
|---|---:|---:|
| canonical_json_sha | 1.1864 | 1.71% |
| canonical_records | 0.2706 | 0.39% |
| dense_decode_filter | 54.3699 | 78.20% |
| frozen_processor | 0.1125 | 0.16% |
| harness_geometry_dispatch | 0.7491 | 1.08% |
| head_canonicalization | 1.1621 | 1.67% |
| implementation_checks | 0.8900 | 1.28% |
| nms | 1.0434 | 1.50% |
| payload_content_sha | 8.0043 | 11.51% |
| receipt_artifact | 0.0261 | 0.04% |
| result_conversion | 0.0086 | 0.01% |
| source_contract | 0.3850 | 0.55% |
| source_file_sha | 1.0028 | 1.44% |
| tensor_signature | 0.1611 | 0.23% |
| uninstrumentierter Rest | 0.1566 | 0.23% |

Der serielle Consumeranteil aus Inputkopie, synchronisiertem TensorRT und Completion beträgt 80.098 ms/Bild. Das Messfenster entspricht 81.031 ms/Bild; die Differenz 0.933 ms/Bild umfasst Füllen/Leeren, Scheduling und Arbeit außerhalb dieser Wrapper. Sie ist keine isoliert gemessene GPU-Leerlaufzeit.
DeepX-Prefixaufruf 33.407 ms, Boundary-Mapping 4.123 ms und blockiertes FIFO-Put 40.315 ms zeigen Rückstau durch den langsameren Consumer. Dieser Runner exportiert kein separates Warteschlangenalter; dieser Wert bleibt unavailable.
Pro Completion wurden 8,568,000 Payloadbytes gehasht; zusätzlich 603,102 Quelldateibytes in 6 Datei-Hashaufrufen und 10 kanonischen JSON-Hashaufrufen. JSON-Bytes werden zur Instrumentierung nicht erneut serialisiert.

H8 original fast: Quelle `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/profiling/hailo8/accepted_profile.json`. Exklusive CPU-Completionanteile:

| Stufe | ms/Bild | Anteil Completion |
|---|---:|---:|
| canonical_json_sha | 0.0000 | 0.00% |
| canonical_records | 0.1366 | 4.04% |
| geometry_materialization | 0.4201 | 12.41% |
| implementation_checks | 0.0000 | 0.00% |
| nms | 1.0072 | 29.74% |
| payload_content_sha | 0.0000 | 0.00% |
| receipt_artifact | 0.0000 | 0.00% |
| source_contract | 0.0000 | 0.00% |
| source_file_sha | 0.0000 | 0.00% |
| sparse_decode_filter | 1.6651 | 49.17% |
| tensor_signature | 0.0875 | 2.58% |
| uninstrumentierter Rest | 0.0698 | 2.06% |

H8 verwendet den bereits vorhandenen Sparse-Pfad: Prefix 5.917 ms, P2-Handoff 0.403 ms, TensorRT einschließlich Rohoutput-D2H 8.408 ms, gesamte P2-Stufe 8.811 ms. Der native Postprocessing-Callback dauert 3.499 ms einschließlich Python-Callbackübergang und Wrapper. Diese drei Stufen überlappen; das tatsächliche Fenster beträgt 8.909 ms/Bild. P1 wartet 2.754 ms auf einen freien Boundaryslot; P2 wartet nur 0.000205 ms auf einen Postprocessingslot. Der gebundene vorhandene SO liefert keine getrennten CUDA-Ereignisphasen. Payload-/JSON-/Dateihashes und strikte Oracle-Prüfungen liegen außerhalb des Timings; entsprechende instrumentierte Hotloop-Aufrufe sind null.

H10 candidate fast: Quelle `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/profiling/hailo10_candidate/accepted_profile.json`. Exklusive CPU-Completionanteile:

| Stufe | ms/Bild | Anteil Completion |
|---|---:|---:|
| canonical_json_sha | 0.1029 | 1.56% |
| canonical_records | 0.1493 | 2.26% |
| finite_value_scan | 0.7861 | 11.88% |
| geometry_materialization | 0.5644 | 8.53% |
| head_canonicalization | 1.1730 | 17.73% |
| implementation_checks | 0.0000 | 0.00% |
| nms | 1.4768 | 22.33% |
| payload_content_sha | 0.0000 | 0.00% |
| receipt_artifact | 0.0000 | 0.00% |
| source_contract | 0.0000 | 0.00% |
| source_file_sha | 0.0000 | 0.00% |
| sparse_adapter | 0.0367 | 0.56% |
| sparse_decode_filter | 2.1783 | 32.93% |
| tensor_signature | 0.0766 | 1.16% |
| uninstrumentierter Rest | 0.0703 | 1.06% |

Der serielle Consumeranteil aus Inputkopie, synchronisiertem TensorRT und Completion beträgt 15.829 ms/Bild. Das Messfenster entspricht 19.073 ms/Bild; die Differenz 3.245 ms/Bild umfasst Füllen/Leeren, Scheduling und Arbeit außerhalb dieser Wrapper. Sie ist keine isoliert gemessene GPU-Leerlaufzeit.
H10 wartet pro Übergabe 0.027 ms beim FIFO-Put; der Consumer sieht 0.192 ms Warteschlangenalter. Die gemeldeten 145.137 ms Hailo-Latenz messen Submission bis Einsammeln und enthalten Backlog. Bei inflight8 und queue_depth3 sind sie kein Beleg für entsprechend langsame reine NPU-Ausführung. Producer-Durchschnittszyklus 18.919 ms, Consumer-Durchschnittszyklus 19.072 ms.
Der Kandidat weist die bestehende Finitprüfung als finite_value_scan separat aus. Sie bleibt im inklusiven Decodewert der Übersicht enthalten und wird nur für die exklusive CPU-Partition abgezogen. Im ursprünglichen Dense-Profil ist diese Scanphase nicht separat aufgelöst; daraus folgt dort kein Nullaufwand.

H8 b044 candidate fast: Quelle `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/profiling/hailo8_b044_candidate/accepted_profile.json`. Exklusive CPU-Completionanteile:

| Stufe | ms/Bild | Anteil Completion |
|---|---:|---:|
| canonical_finite_reduction | 0.1483 | 2.44% |
| canonical_finite_scan | 0.8018 | 13.21% |
| canonical_json_sha | 0.1000 | 1.65% |
| canonical_records | 0.1468 | 2.42% |
| finite_value_reduction | 0.1368 | 2.25% |
| finite_value_scan | 0.7549 | 12.44% |
| geometry_materialization | 0.4795 | 7.90% |
| head_canonicalization | 0.2568 | 4.23% |
| implementation_checks | 0.0000 | 0.00% |
| nms | 1.3023 | 21.46% |
| payload_content_sha | 0.0000 | 0.00% |
| receipt_artifact | 0.0000 | 0.00% |
| source_contract | 0.0000 | 0.00% |
| source_file_sha | 0.0000 | 0.00% |
| sparse_adapter | 0.0329 | 0.54% |
| sparse_decode_filter | 1.7677 | 29.13% |
| tensor_signature | 0.0738 | 1.22% |
| uninstrumentierter Rest | 0.0663 | 1.09% |

Der serielle Consumeranteil aus Inputkopie, synchronisiertem TensorRT und Completion beträgt 21.563 ms/Bild. Das Messfenster entspricht 22.074 ms/Bild; die Differenz 0.511 ms/Bild umfasst Füllen/Leeren, Scheduling und Arbeit außerhalb dieser Wrapper. Sie ist keine isoliert gemessene GPU-Leerlaufzeit.
H8 b044 nutzt den regulären Python-VStreams-FIFO. Zwei vollständige Finitprüfungen sind getrennt beobachtet: Kanonisierung 0.950135 ms, gemeinsamer Sparse-Decoder 0.891748 ms, zusammen 1.841883 ms (30.35% der instrumentierten Completion). Beide Scans und beide booleschen Reduktionen erfolgen jeweils dreimal pro Bild; jede Prüfung umfasst 8.568.000 Rohheadbytes. Diese Kindintervalle sind bereits aus den exklusiven Kanonisierungs-/Decodezeilen abgezogen.
Die originale FIFO-Telemetrie liefert P1-Arbeit 6.284547 ms und serielle P2-Arbeit 21.966350 ms bei 22.074229 ms pro Diagnosebild. Separate FIFO-Putblock-/Queuealterwerte exportiert dieser H8-Pythonrunner nicht; sie bleiben unavailable. Gegenüber dem Final-Tailmedian 5.338600 ms ist der instrumentierte CPU-Tail höher. Instrumentierung und Kurzfenster sind keine neue Finalmessung. Ausführlicher 3+3-Countervergleich: [H8_B044_REGRESSION_ANALYSIS.md](H8_B044_REGRESSION_ANALYSIS.md).

H10 vor/nach: Der CPU-Abschluss sinkt von 63.599 auf 6.614 ms/Bild (9.62x). Das instrumentierte Pipelinefenster sinkt von 73.531 auf 19.073 ms/Bild (3.86x). Diese Verhältnisse beschreiben die Diagnose; sie ersetzen keine finalen uninstrumentierten FPS-Repeats.
Nach dem Fix beträgt der beobachtete Prefix-/Producerzyklus 18.919 ms/Bild, die tatsächlich geleistete serielle Consumerarbeit hingegen 15.973 ms/Bild. Das Gesamtfenster von 19.073 ms/Bild folgt nun der Prefixrate. Die zuvor starke Rückstauwirkung ist bei 0.027 ms FIFO-Putblockierung und 0.192 ms Queuealter verschwunden. Der Consumerzyklus über das ganze Fenster (19.072 ms) enthält Warten auf neue Eingaben; er darf nicht mit reiner Consumerarbeit verwechselt werden. Ohne separate Device-/SDK-Callbackereignisse ist innerhalb dieser Prefixrate keine belastbare Trennung von NPU-Ausführung, SDK und Scheduling möglich.
Der Kandidat hasht im gemessenen Abschluss keine Payloads und keine Quelldateien mehr. Die Headkanonisierung enthält noch 1 kanonischen JSON-Hash pro Bild (0.103 ms); vollständige Kryptofreiheit des Hotloops wird daher nicht behauptet.
Der verbleibende H10/H8-Unterschied beträgt diagnostisch 10.164 ms/Bild. Im gebundenen H10-FIFO bleiben Inputkopie, TensorRT-Synchronisierung und Completion auf demselben Consumer seriell; H8 führt den Postprocessing-Callback in einer separaten dritten Stufe parallel zu P2 aus. Diese Topologie bleibt ein Unterschied, ist nach dem Fix aber nicht der unmittelbar beobachtete H10-Flaschenhals: Der Prefix bestimmt die Rate. Aus diesen Diagnosen wird kein zusätzlicher Scheduler-Fix abgeleitet.

EMC_FREQ und GPU-Takt fehlen im H10-tegrastats-Auszug dieser Diagnose und bleiben unavailable. Fehlende Telemetriefelder werden nicht aus Sysfs-Sollwerten oder MAXN abgeleitet. Die Original- und Kandidaten-Final-FPS stammen ausschließlich aus den gesonderten uninstrumentierten Messungen.
