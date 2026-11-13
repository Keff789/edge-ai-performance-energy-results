H8 b044 fällt im gültigen Dreiermedian von 53.460813 auf 47.800201 completed-FPS (-10.59%). Die drei ursprünglichen und drei aktuellen Repeats haben jeweils 100 Warmups und 1000 Abschlüsse. Der historische Sammelreport enthält zusätzlich einen veralteten Top-Level-FPS-Wert; dieser Vergleich verwendet ausschließlich seine vollständigen `repetition_evidence`-Einträge.

| Messgröße | vorher: drei Werte | nachher: drei Werte | Mittel vorher | Mittel nachher | Änderung |
|---|---|---|---|---|---|
| fps_makespan | 53.296442 / 53.490480 / 53.460813 | 47.765246 / 47.800201 / 47.836383 | 53.415912 | 47.800610 | -5.615302 |
| p1_ms | 5.856794 / 5.843396 / 5.839530 | 5.929450 / 5.919907 / 5.926433 | 5.846573 | 5.925263 | +0.078690 |
| handoff_ms | 0.238554 / 0.238391 / 0.246517 | 0.254552 / 0.274719 / 0.258316 | 0.241154 | 0.262529 | +0.021375 |
| p2_run_ms | 15.468683 / 15.455969 / 15.452426 | 15.530983 / 15.542516 / 15.541387 | 15.459026 | 15.538296 | +0.079270 |
| completion_tail_ms | 3.260179 / 3.206967 / 3.220929 | 5.368316 / 5.338600 / 5.326747 | 3.229358 | 5.344554 | +2.115196 |
| p1_thread_ms | 6.095348 / 6.081787 / 6.086047 | 6.184002 / 6.194626 / 6.184748 | 6.087727 | 6.187792 | +0.100065 |
| p2_thread_ms | 18.728862 / 18.662935 / 18.673355 | 20.899299 / 20.881117 / 20.868134 | 18.688384 | 20.882850 | +2.194466 |
| makespan_ms | 18762.978430 / 18694.915580 / 18705.289674 | 20935.724029 / 20920.414016 / 20904.590751 | 18721.061228 | 20920.242932 | +2199.181704 |

Die vorhandenen Stagecounter lokalisieren die Mehrarbeit: Der serielle P2-Zyklus wächst um 2.194466 ms/Bild, davon 2.115196 ms im Completion-Tail (96.39% der Zyklusänderung) und 0.079270 ms im TRT-Abschnitt. Der beobachtete Tail ist damit die konkrete Hauptstelle der Regression. P1 und P2 überlappen; ihre Mittel werden nicht zur Gesamtlaufzeit addiert.

b044 verwendet den Python-VStreams-FIFO mit Completion seriell im P2-Thread. b066 verwendet dagegen den C++-Pfad mit separatem Postprocess-Worker. Deshalb kann derselbe zusätzliche Hostaufwand bei b044 unmittelbar den seriellen Zyklus verlängern, während die b066-Pipeline ihn teilweise überlappt. Das ist eine Topologieerklärung; ein konkreter b066-Zeitanteil wird daraus nicht errechnet.

Statisch belegt: Der ursprüngliche H8-Fastdecoder prüft Form/Grid/Dtype, aber scannt nicht jedes Rohhead-Element auf Finitheit. Der aktuelle Adapter ruft zuerst `_canonicalize_yolov7_heads` mit vollständigem Finit-Scan und anschließend den gemeinsamen `ExactSparseYoloV7Decoder` mit einem zweiten vollständigen Finit-Scan auf. Dazu kommen die Kanonisierungs-/Ankertabellenprüfungen und der Mapping-Metadatenhash. Grid und Anker bleiben vorgebunden; Quelldateihashes liegen außerhalb des gemessenen Tails. Quelle: `parity/h8_b044_static_additional_work.json`. Die Codeänderung belegt zusätzliche Arbeit, noch keinen isolierten Millisekundenanteil.

Die zusätzliche kurze Diagnose ist separat instrumentiert (100 Warmups / 100 erfolgreiche Abschlüsse). Sie ersetzt keinen Finalrepeat.

| Exklusiver CPU-Abschnitt | ms/Bild | Aufrufe/Bild |
|---|---|---|
| canonical_finite_scan | 0.801799 | 3.0 |
| canonical_finite_reduction | 0.148336 | 3.0 |
| head_canonicalization | 0.256792 | 1.0 |
| finite_value_scan | 0.754948 | 3.0 |
| finite_value_reduction | 0.136800 | 3.0 |
| sparse_decode_filter | 1.767690 | 1.0 |
| sparse_adapter | 0.032905 | 1.0 |
| nms | 1.302324 | 10.0 |
| geometry_materialization | 0.479548 | 1.0 |
| canonical_records | 0.146822 | 1.0 |
| tensor_signature | 0.073758 | 1.0 |
| canonical_json_sha | 0.100010 | 1.0 |

Der instrumentierte CPU-Tail liegt 0.729432 ms über dem uninstrumentierten Final-Tailmedian von 5.338600 ms. Instrumentierung und das kürzere Diagnosefenster beeinflussen die Laufzeit; der höhere Diagnosewert wird weder zur Final-FPS umgerechnet noch als weitere Regression der Finalserie gewertet.

Gemessener CPU-Abschluss: 6.068032 ms/Bild. Die beiden unveränderten vollständigen Finitprüfungen einschließlich ihrer booleschen Reduktionen kosten zusammen 1.841883 ms/Bild (30.35% des instrumentierten Abschlusses); der übrige exklusive CPU-Anteil beträgt 4.226149 ms. Diese Anteile liegen innerhalb von Kanonisierung bzw. Sparse-Decodierung und werden nicht nochmals zu deren inklusiven Zeiten addiert. Die Diagnose belegt ihren heutigen Kostenanteil; ohne instrumentierten alten b044-Gegenlauf wird nicht behauptet, die gesamte historische Differenz ausschließlich diesen Prüfungen zuordnen zu können.

Original: `/home/kmika/Reports/yolov7-full-fix-20261005/performance_first_20261006/matrix_inventory/raw_original_reports/2aca9ca338e2a8072eca4adf4d296bfa1eab793a032494e87ab77d30ecff6b0e.json` (SHA256 `2aca9ca338e2a8072eca4adf4d296bfa1eab793a032494e87ab77d30ecff6b0e`). Aktuell: `/home/kmika/Reports/yolov7-full-fix-20261005/splits_orin_20261006_222316/split_final/H8__hailo8_to_trt__b044__command_guard_v2/summary.json`. Instrumentierung und gezielte lokale Regression: `profiling/profile_h8_python_b044.py`, `profiling/test_h8_b044_profile_local.py`.
