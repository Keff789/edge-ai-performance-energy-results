# Dissertation

Current generated EN/DE evidence: [detector-corrected release, 27 October 2026](../../results/supplementary-studies/generic420-closeout-20261027/README.md), with [English source manifest](../../results/publication-builds/generic420-20261027/dissertation-en/README.md) and [German outputs](../../results/publication-builds/generic420-20261027/dissertation-de/README.md). Both consume the current original-Native-scope RQ2 and fixed420 RQ3 studies. Native/Full/energy studies and frozen RQ1/YOLOv7-b066 evidence retain their original values. Dissertation prose is unchanged; the earlier collections below retain their historical scope.

## Deutsche Split-Grafiken und Tabellen

Die [deutsche Sammlung](de/README.md) enthält 58 Grafikfamilien und die verfügbaren
Tabellen aus der vollständigen Split-Auswertung, den Publikationsprofilen und den
ergänzenden Split-Studien. PDF/SVG und LaTeX sind für die Dissertation vorgesehen,
PNG und Markdown für die Vorschau. Die Auswahl ist nicht auf die im Paper
verwendeten Darstellungen beschränkt.

Die Sammlung verwendet die vorhandenen Messwerte. Englische Daten und Ergebnisse
bleiben erhalten. Aktuelle und frühere Messreihen sind in eigenen Ordnern abgelegt.
Die [Exportanleitung](../../scripts/dissertation/README.md) beschreibt die lokale
Erzeugung auf twix ohne administrative Rechte. Der zusätzliche Export umfasst
Split-Inferenz. Für Energiemessungen gilt weiterhin die separate Auswertung unten.


Use both [split-inference results](../../results/split-inference/README.md) and [energy-measurement results](../../results/energy-measurement/README.md). Complete model views, supplementary comparisons, protocol controls, negative results and scientific limitations are retained beyond individual paper selections.

Additional entry points: [Hailo-10 format microbenchmarks](../../results/split-inference/microbenchmarks/README.md), [complete measurement sweeps](../../results/energy-measurement/galleries/direct-sweeps.md), [spectral analysis](../../results/energy-measurement/galleries/spectra-jetson.md) and [calibration](../../results/energy-measurement/galleries/calibration.md).

[Analysis instructions](../../scripts/README.md) and the [ONNX tool source](../../software/README.md) support reuse. Data are shared once across publication entry points; the result galleries and table indices provide the detailed navigation.

All seven current performance–energy/Pareto and quality views are available for [MobileNetV3 Large](../../results/split-inference/figures/models/mobilenet_v3_large.md), [RegNet X 1.6GF](../../results/split-inference/figures/models/regnet_x_1_6gf.md), [ResNet-50](../../results/split-inference/figures/models/resnet50.md), [YOLO11l](../../results/split-inference/figures/models/yolo11l.md), [YOLO26m](../../results/split-inference/figures/models/yolo26m.md), [YOLO26s](../../results/split-inference/figures/models/yolo26s.md) and [YOLOv7](../../results/split-inference/figures/models/yolov7_paper.md). Shared assets include [captions](../../results/split-inference/CAPTIONS.md), [methods](../../results/split-inference/METHODS.md), [LaTeX methods](../../results/split-inference/METHODS_PARAGRAPH.tex), [tables](../../results/split-inference/tables/README.md), [plot data](../../results/split-inference/figures/FIGURE_DATA.json) and all Pareto rows in [CSV](../../results/split-inference/tables/PARETO_POINTS.csv) or [JSON](../../results/split-inference/tables/PARETO_POINTS.json).

The new [global fastest Full-versus-split table](../../results/split-inference/tables/table3_fastest_deployments.md) ([LaTeX](../../results/split-inference/tables/table3_fastest_deployments.tex), [CSV](../../results/split-inference/tables/table3_fastest_deployments.csv), [JSON](../../results/split-inference/tables/table3_fastest_deployments.json)) and [same selected split with two Full baselines](../../results/split-inference/tables/fastest_split_baselines.md) ([LaTeX](../../results/split-inference/tables/fastest_split_baselines.tex), [CSV](../../results/split-inference/tables/fastest_split_baselines.csv), [JSON](../../results/split-inference/tables/fastest_split_baselines.json)) share one absolute-FPS selection across both runners. The separate [relative same-host Top-2 Native table](../../results/split-inference/tables/table3_top2_native.md) preserves the historical selection method and results. Global fastest describes open setup choice; same-host describes the selected split against its own host's Full alternatives.

The associated [baseline-effect figure](../../results/split-inference/figures/fastest_split_baseline_comparison.pdf) ([SVG](../../results/split-inference/figures/fastest_split_baseline_comparison.svg), [PNG](../../results/split-inference/figures/fastest_split_baseline_comparison.png)) and [fastest-deployment throughput–energy figure](../../results/split-inference/figures/fastest_deployment_tradeoff.pdf) ([SVG](../../results/split-inference/figures/fastest_deployment_tradeoff.svg), [PNG](../../results/split-inference/figures/fastest_deployment_tradeoff.png)) use the same exact table UIDs and unrounded values. They preserve observations below a throughput ratio of one. The latter shows throughput-selected configurations against one global Full denominator; it complements the full observed-space Pareto views and does not establish equal quality, equal timed work or causal efficiency. The normal reproduction command regenerates these shared assets without editing a complete dissertation.

The [supplementary studies](../../results/supplementary-studies/README.md) retain the completed THESIS20 selector/energy analysis, YOLOv7 completion/stage-cost report and Hailo-8 HAR diagnosis with their original dates, cohorts and interpretation limits. Their data remain separate from the current DeepX Native A4 main dataset.

The [v49 hardware confirmation and energy supplements, 18–19 October 2026](../../results/supplementary-studies/thesis-v49-confirmation-20261019/README.md) add a separate R3 confirmation with seventy primary throughput runs and thirty-five primary throughput pairs. Conditional energy coverage consists of sixty-eight primary acquisitions and two separately identified supplements with their own completion counts and intervals. The original energy-null fields and throughput rows remain unchanged. Generated tables retain the actual Full host/backend, cross-session energy pair identities, direct offline quality intervals and open ADC-unit, measurement-chain and historical-provenance limits. This campaign does not replace or pool the historical 450-configuration results or R1/R2 attempts.

The [independent stage-cost composition study](../../results/supplementary-studies/stage-cost-composition/README.md) adds a separate four-case Oracle test. Its [English section, bibliography and newly built standalone preview](stage-cost-composition/README.md) are prepared for later integration and share the study’s regenerated vector figures and table. No complete dissertation has been changed.

The [native endpoint reconstruction](../../results/supplementary-studies/native-endpoint-reconstruction/README.md) separates serial completion, one-image concurrent smoke, 32-image decode parity and pipeline throughput using archived JSON reports. Its tables are regenerated offline; their populations and timing scopes remain distinct.

The [historical FP16 spectral and rate curves](../../results/energy-measurement/galleries/historical-fp16.md) provide six regenerated figure families from the earlier 13-run cohort. Active/idle windows and dependent phase ranges are documented alongside the unchanged current energy results.

The [dissertation development study](../../results/supplementary-studies/dissertation-development-2026/README.md) makes the six-stratum ranking/proxy figures and the reported decoder, B500, compiler-sensitivity and seven-row Imagenette tables reproducible. Aggregate correlations remain aggregate inputs; manuscript transcriptions remain reported values. The separate [MLSys R10 study](../../results/supplementary-studies/mlsys-selection-20261007/README.md) adds its dated selection, split/Full, quality-tolerance, long-window, vendor and graph-inventory views without replacing THESIS20 or the current main dataset.
