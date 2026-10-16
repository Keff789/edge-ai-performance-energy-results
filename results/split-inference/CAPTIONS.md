# Figure captions

All figures are generated from PAPER_DATASET and its derived comparison tables. SVG/PDF are vector outputs; PNG files are previews. Broad observed selection; no quality/claim/hash gate.

## 01_full_throughput

Full throughput for all 42 selected model/backend/host identities; 42 have this metric. Host-specific TRT values are separate. No quality, claim, sample-count or hash admission filter is applied. Whiskers show the observed performance-repeat minimum and maximum, not a confidence interval; historical n=1 has no whisker.

## 02_full_energy

Full energy for all 42 selected model/backend/host identities; 42 have this metric. Host-specific TRT values are separate. No quality, claim, sample-count or hash admission filter is applied. Bars use mean of per-repeat calibrated raw E/N, including the host; n is the actual sensor-repeat count. This is mJ per completed image, not energy divided by FPS.

## 03a_native_generic_pooled

Point-pooled empirical distributions of Native/Generic throughput and host-inclusive raw J/image ratios. Each split pair has one vote; models with more measured splits have more points here. The two axes use their own observed metric pairs. A ratio of one indicates equality.

## 03b_native_generic_equal_model

One dot is the median ratio within a model/setup. Horizontal bars are arithmetic means of these model medians within each setup, so each observed model has equal weight. In All, each dot first averages the setup medians for one model, then the bar averages across models. Metric-specific pair counts and all model medians are in figures/FIGURE_DATA.json. This differs intentionally from the point-pooled distribution.

## 03c_native_generic_model_setup

All observed Native/Generic ratios by model/setup. Every dot is one paired split, spread vertically only for readability; the black tick marks the within-group median. No point is removed because of quality or old admission flags.

## 04_tradeoff_mobilenet_v3_large

All 108 observed deployments of MobileNet V3 Large, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes.

## 04_tradeoff_regnet_x_1_6gf

All 126 observed deployments of RegNet X 1.6GF, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes.

## 04_tradeoff_resnet50

All 120 observed deployments of ResNet-50, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes.

## 04_tradeoff_yolo11l

All 24 observed deployments of YOLO11l, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes. Native detector oracles are outside timing; Generic records decoded NMS; Fulls retain their recorded host-tail or normalization work.

## 04_tradeoff_yolo26m

All 24 observed deployments of YOLO26m, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes. Native detector oracles are outside timing; Generic records decoded NMS; Fulls retain their recorded host-tail or normalization work.

## 04_tradeoff_yolo26s

All 24 observed deployments of YOLO26s, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes. Native detector oracles are outside timing; Generic records decoded NMS; Fulls retain their recorded host-tail or normalization work.

## 04_tradeoff_yolov7_paper

All 24 observed deployments of YOLOv7, by host setup; axes are scaled separately. Color shows selected dataset quality on one model-wide scale (gray: missing). Energy is calibrated host-inclusive mean(E/N), in mJ/image. Outer outlines mark the empirical two-dimensional Pareto front: maximize FPS, minimize energy, including both Fulls. Quality is displayed, never a filter or third front objective. F/E label runner optima; F=E means one UID. Straight segments only guide between distinct observed front coordinates; intermediate configurations are unproven. Singleton fronts have no line. Timed work and quality differ; see METHODS.md and the exported endpoint notes. Native detector oracles are outside timing; Generic records decoded NMS; Fulls retain their recorded host-tail or normalization work.

## 05_fastest_vs_min_energy

Fastest and minimum-energy splits selected independently within each model/setup/runner with stable UID tie-breaking. Blue circles compare throughput; orange squares compare host-inclusive J/image, always fastest divided by minimum-energy split. Labels show performance/energy candidate counts and an equals sign when one observed point realizes both optima. Groups with one candidate are visible and do not constitute independent evidence for a conflict. Quality values and selected identities are retained in FIGURE_DATA.json.

## 06_quality_reference_comparison

Selected existing dataset quality minus the corresponding model reference, in percentage points. Top-1 and COCO mAP@[.50:.95] are kept on separate axes. All numerical Native/Generic split and Full evaluations are retained, including Hailo Full losses and split improvements. Values are reused evidence, not new quality measurements. Missing quality is not filled from output-PASS or a historical favorable assessment. References can have different evaluation scopes; sample counts and exact source fields remain in the dataset.

## 06_quality_mobilenet_v3_large

Absolute selected dataset quality for MobileNet V3 Large. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_regnet_x_1_6gf

Absolute selected dataset quality for RegNet X 1.6GF. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_resnet50

Absolute selected dataset quality for ResNet-50. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_yolo11l

Absolute selected dataset quality for YOLO11l. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_yolo26m

Absolute selected dataset quality for YOLO26m. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_yolo26s

Absolute selected dataset quality for YOLO26s. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

## 06_quality_yolov7_paper

Absolute selected dataset quality for YOLOv7. Every available split evaluation is shown; gray ticks are its recorded model reference. Horizontal lines show the matching host Vendor Full and TRT Full when numerical quality exists. No missing Full quality is inferred. Percent values denote Top-1 accuracy or COCO mAP as labeled, not relative loss. Exact quality sample counts are in FIGURE_DATA.json.

