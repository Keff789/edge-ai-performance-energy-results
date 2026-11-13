# Evidence-linked text for later thesis integration

For Appendix C: the historical ConvTranspose rule is a dense output-based
proxy. Independent coordinate enumeration for a single-channel 2×2 input and
2×2 kernel, stride two, and no padding or bias gives
16 direct products, whereas the historical
rule gives 64 proxy units. Neither
quantity is a measurement of backend instructions. The historical d164aad6
definition and published db729b9 source contain the same inspected counting
bytes; the inspected campaign manifests do not bind these analyzer bytes to a
particular historical process. [Counterexample, formula and source distinction](convtranspose_audit.json).

The audit inspected 7 hash-bound full ONNX graphs
(2125 nodes in total): MobileNetV3-Large,
RegNetX-1.6GF, ResNet-50, YOLO11l, YOLO26m, YOLO26s and YOLOv7. None contains
ConvTranspose, so changing only that counting branch leaves their proxy totals
and associated prefix/suffix shares unchanged. Recomputed totals match the
recorded historical totals for 7/7 graphs.
Coverage statistics are node fractions, not runtime fractions.
The assertion is confined to the listed hashes:
437 of the 450 later deployment rows
bind to them, while 13 lack a model hash. Distinct source/build part
graphs were referenced but not inspected. [Exact hashes, operators, coverage and cohort bindings](convtranspose_audit.json),
[operator table](operator_inventory.csv).

For the score-unit discussion: decimal `cut_bytes/10^6` values enter historical
accelerator-fit thresholds labelled in MiB. The separate `binary_mib_input_v1`
comparison supplies `cut_bytes/2^20` to that input while retaining the original
candidate universe, filters, coefficients and tie rules. It reproduces
14777 historical score entries
before comparison. Accelerator-fit changes 1254
rank positions, with no complete-universe or eligible-subset Top-1 change.
The stored stream heuristic changes 663 rank
positions and 7 overlapping subset
selections (yolov7_paper: b044 → b066); all complete-universe Top-1 choices remain
unchanged. Boundary-bytes, weighted and bottleneck controls remain unchanged.
The ms/FPS-labelled heuristics do not gain physical calibration from this
conversion, and the current deployment winners and measured values are
preserved. [Unit definitions](score_units.csv), [rank deltas](score_rank_deltas.csv),
[selection scopes, eligibility and controls](score_audit.json).

For the reproducibility appendix: the selected UID
`native|mobilenet_v3_large|DeepX|deepx_to_trt|b135` is linked through its selected quality result to the central
replay request `4a5702ca2dff3ec3414917370ffd59e3d23d421c5296be3187886669957b30ff`
and fingerprint `2723b4e07f3a96a0b2035b2ee3a9406c3d47e6f834607d49d24cd9cf22199180`.
This is a later evaluation than the original runtime request. The candidate
and CPU-reference prediction files were hash/format checked without recomputing
quality. The historical execution-to-evaluator binding remains incomplete:
the bounded sources contain no contemporaneous receipt binding that replay to
the loaded evaluator, service/helper code and Python/NumPy environment.
Preserved later code or matching quality values cannot establish this missing
history. [Full UID chain, inspected sources, checks and exact open fields](mobilenet_evaluator_binding.json).

Three reproduction levels are distinguished. Level A was executed using safe
offline table commands: 227 main-study scientific files and all 38 confirmation
table files matched their published counterparts byte for byte. This includes
summaries of already saved bootstrap values, not new resampling. Level B was
limited to source/command review and selected prediction format/hash checks;
no individual-metric or raw-signal derivation was executed. Level C, physical
acquisition and model/quality execution, was inventoried only. A documented
command is therefore not reported as a passed reproduction. Further historical
source receipts, missing graph identities and any separately claimed part
graphs would be needed to extend these bounded conclusions.
[Executed commands, prerequisites and per-route status](reproduction_paths.json),
[source identities](source_manifest.json), [remaining claims and next evidence](task_closeout.json).
