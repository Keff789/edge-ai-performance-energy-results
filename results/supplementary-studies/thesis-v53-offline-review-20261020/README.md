# Thesis v53: bounded offline software and provenance audit

Status: **completed_with_limits**. The independent counterexample confirms
16 direct products versus
64 historical dense-proxy units.
The 7 inspected full ONNX hashes contain
0 ConvTranspose nodes. The separate unit
sensitivity changes historical score rankings, while the selected measured
deployments and their measurements remain unchanged. The selected MobileNet
evaluation's execution-to-source binding remains open.
[Operator evidence](convtranspose_audit.json), [score evidence](score_audit.json),
[MobileNet evidence](mobilenet_evaluator_binding.json).

## Exact graph scope

| Model | Inspected full graph SHA-256 | Nodes | Unimplemented zero-fallback nodes | ConvTranspose |
|---|---|---:|---:|---:|
| mobilenet_v3_large | `2f5e79b1e4280251e7b6eefe1d6161c4831e2fc27858e1e9fe2fac697f44489e` | 140 | 39 | 0 |
| regnet_x_1_6gf | `fba2c5b46ff63bd4b4bc65f1cf60fd86fa84e16e7432fcaa60d5efbd2c99b8f3` | 135 | 2 | 0 |
| resnet50 | `cebd9d5879ddd304a18f51e559ab74fba5cbd1f610b9359321bc5228acbe4f50` | 122 | 3 | 0 |
| yolo11l | `f0fcdf56a4ac24d87ec30c627170492ccad9db80486ec5694df6de65c1b3d147` | 617 | 72 | 0 |
| yolo26m | `d1c6a922dd92f896c69e2f6767ea3ca23fac0e53e5ac69681965eb8a74cda897` | 418 | 77 | 0 |
| yolo26s | `4b8ff9dce56ca7058c53e1a08feca69a59f8504a8f2ef68c85c065ae837ce04a` | 384 | 75 | 0 |
| yolov7_paper | `7a13e66f91047cce0e251c05f64159646847e842af31d60441c63dcdfad7825d` | 309 | 31 | 0 |

Coverage fractions use each graph's node count as denominator; they are not
runtime or energy shares. No missing or symbolic input/output shapes remain in the captured static shape projection. Recomputed totals match the historical
saved totals for 7/7 graphs;
2111 candidate feature records are checked against
their bound originals. A change confined to the unused ConvTranspose branch
cannot affect these graphs' totals, prefix/suffix shares or ranks.
[Operator inventory](operator_inventory.csv), [calculation and source scope](convtranspose_audit.json).

The later 450-row deployment export binds
437 rows to these exact full hashes;
13 rows lack `model_sha256`. Fourteen confirmation UID-to-full-graph
bindings and its separate source/build graph references are recorded explicitly.
Distinct part-graph references remain uninspected. Their operator content is
unknown and is not inferred from a full-model name or boundary.
[Graph/UID identities and uninspected references](convtranspose_audit.json).

The d164aad6 historical definition and the published db729b9 analyzer use the
same inspected counting bytes. The preserved campaign critical-module lists do
not individually bind `metrics.py` to historical execution. Original code,
current published code and observed foreign dirty checkout state are therefore
separate facts. [Source context](source_manifest.json),
[counting provenance](inputs/operators/source_bindings.json).

## Score units and separate comparison

`binary_mib_input_v1` changes only the affected temporary objective input from
decimal MB to binary MiB; coefficients, candidates, normalization universes,
eligibility filters and exact tie rules remain fixed. It reproduces all
14777 saved method-score entries
before comparing variants. The pure boundary-bytes ranker is unaffected.
[Field definitions](score_units.csv), [candidate deltas](score_rank_deltas.csv).

Accelerator-fit: 912 changed scores,
1254 changed rank positions and
0 complete-universe or
0 eligible-subset Top-1 changes.
Stream heuristic: 663 changed rank positions,
0 complete-universe Top-1 changes and
7 changed eligible-subset selections
(yolov7_paper: b044 → b066). Those subset changes are overlapping static projections,
not independent experiments. The existing minimum-three-candidates gate is
retained. A unit conversion with fixed empirical coefficients does not establish
physical ms/FPS calibration. [Full comparison and unchanged controls](score_audit.json).

## MobileNet source gap

The full UID is `native|mobilenet_v3_large|DeepX|deepx_to_trt|b135`. Its selected quality source leads to the
central replay at `2026-10-10T18:36:03.402707+00:00`, with request
`4a5702ca2dff3ec3414917370ffd59e3d23d421c5296be3187886669957b30ff` and fingerprint
`2723b4e07f3a96a0b2035b2ee3a9406c3d47e6f834607d49d24cd9cf22199180`.
This replay differs from the original runtime request. Candidate and CPU
reference prediction bytes and record ordering were checked without calculating
quality. The archived inventory records historical evaluator-source bindings
for 13 of its
14 selected UIDs; this audit checks that inventory rather than
re-auditing every historical execution. The bounded search for the remaining
UID did not find a contemporaneous binding to loaded
evaluator/service/helper bytes or the Python/NumPy environment. The referenced
`DX56_QUALITY_COMMANDS.json` remains unresolved in its original resolver;
the later preserved evaluator alone does not close the gap.
[Complete chain, search bounds and missing evidence](mobilenet_evaluator_binding.json).

## Offline reproduction

Run from this repository's root with an existing Python >=3.10 environment.
The audit itself uses the standard library; it needs neither the original
graphs nor the external archive, a tool installation, network or hardware.

```bash
python3 -I -B scripts/supplementary-studies/thesis-v53-offline-review-20261020/reproduce.py \
  --output ../v53-audit-check --verify
```

Use an absent or empty external output directory. The command rechecks compact
source bindings, runs only the audit's focused tests, regenerates all reports
and compares them byte for byte with the committed audit. It does not rerun the
original-source capture or the historical A commands. To refresh the owned
audit outputs after an intentional source/code change, omit `--verify` and use
`--output results/supplementary-studies/thesis-v53-offline-review-20261020`. Never refresh historical measurements.

Path A was actually executed in new directories: the main numeric reproduction
verified 227 scientific files and the confirmation reproduction matched all 38
published table files. Exact commands, input/code/output hashes, environments
and controls are in [reproduction paths](reproduction_paths.json) and
[execution evidence](inputs/reproduction/).
The main numeric command excludes figure rendering. The confirmation command
uses saved bootstrap replicates for table summaries; it draws no new samples.

Path B was limited to source/command review and selected prediction hash/format
checks. No individual quality metric, bootstrap or raw-signal integration was
recomputed. Path C was inventoried only. Its commands are historical entry
points, not tested fresh-run recipes. Some B scripts write into their input
tree; any later authorized use needs an isolated archive copy and the stated
dependencies. [Per-route status and prerequisites](reproduction_paths.json).

## Provenance and remaining evidence

The audit is based on results commit
`b10d15992d0ce45d0f81329a5e961cb6207a1d09`. The task's historical main and
confirmation pins are kept separately in [source_manifest.json](source_manifest.json).
The explicit input trees were byte-unchanged between those pins and this base.
The locally found thesis copy identifies an older version; v53 was not found
in the bounded locations. The task specifies the review questions completely,
and the manuscript was not edited.

The compact evidence contains metadata projections, not model weights,
predictions or waveforms. Reproducing projections does not newly authenticate
absent originals. To strengthen the open claims, obtain an execution-bound
MobileNet replay receipt with source/environment identities, the missing
deployment model hashes and any part graphs whose operator coverage is to be
claimed. Historical analyzer execution additionally needs its original
process-to-module binding. These are evidence requests, not a measurement
campaign. [Task-by-task closeout and recorded Git state](task_closeout.json).

[English insertion text](thesis_insert.md) is derived from these same facts.
The recorded Git receipt names an already existing implementation commit when
available; it deliberately cannot name the future commit containing itself.
Push is left to the user.
