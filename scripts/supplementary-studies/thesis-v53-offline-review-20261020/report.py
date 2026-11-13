"""Short, evidence-linked documentation from the same generated audit facts."""
from __future__ import annotations

import json
from pathlib import Path

STUDY = "results/supplementary-studies/thesis-v53-offline-review-20261020"
SCRIPT = "scripts/supplementary-studies/thesis-v53-offline-review-20261020/reproduce.py"


def read(output, name):
    return json.loads((output / name).read_text())


def build(repo: Path, output: Path) -> None:
    op = read(output, "convtranspose_audit.json")
    score = read(output, "score_audit.json")
    mobile = read(output, "mobilenet_evaluator_binding.json")
    bindings = mobile["archived_selected_binding_inventory"]
    a_counts = read(output, "reproduction_paths.json")["summary"]["A_output_files"]
    a_main, a_confirmation = a_counts["A_deployment_tables"], a_counts["A_confirmation_tables"]
    fit = score["changes"]["onnx_real_boundary_hardware_aware"]
    stream = score["changes"]["stored_predicted_stream_fps"]
    changed = [r for r in score["published_subset_selections"] if r["selected_case_changed"]]
    transitions = sorted({(r["model_id"], r["historical_selected_case"],
                           r["variant_selected_case"]) for r in changed})
    transition_text = "; ".join(f"{m}: {a} → {b}" for m, a, b in transitions) or "none"
    shape_gaps = sum(g["missing_or_symbolic_input_nodes_after_inference"]
                     + g["missing_or_symbolic_output_nodes_after_inference"] for g in op["graphs"])
    totals_matching = sum(g["recomputed_total_matches_all_stored_totals"] for g in op["graphs"])
    # This prose describes the observed zero-occurrence case. A changed graph
    # capture requires a new impact analysis before emitting the same conclusion.
    if op["inspected_convtranspose_count"] != 0:
        raise ValueError("ConvTranspose now occurs: update impact analysis and report before publication")
    shape_text = (
        "No missing or symbolic input/output shapes remain in the captured static shape projection."
        if shape_gaps == 0 else
        f"The captured static shape projection retains {shape_gaps} input/output node-shape gaps."
    )
    graph_rows = "\n".join(
        f"| {g['model_id']} | `{g['graph_sha256']}` | {g['node_count']} | "
        f"{g['zero_unimplemented_fallback_nodes']} | {g['convtranspose_count']} |"
        for g in op["graphs"]
    )
    missing = op["later_deployment_full_graph_unbound_rows"]
    readme = f"""# Thesis v53: bounded offline software and provenance audit

Status: **completed_with_limits**. The independent counterexample confirms
{op['counterexample']['direct_products']} direct products versus
{op['counterexample']['historical_dense_proxy']} historical dense-proxy units.
The {op['graph_count']} inspected full ONNX hashes contain
{op['inspected_convtranspose_count']} ConvTranspose nodes. The separate unit
sensitivity changes historical score rankings, while the selected measured
deployments and their measurements remain unchanged. The selected MobileNet
evaluation's execution-to-source binding remains open.
[Operator evidence](convtranspose_audit.json), [score evidence](score_audit.json),
[MobileNet evidence](mobilenet_evaluator_binding.json).

## Exact graph scope

| Model | Inspected full graph SHA-256 | Nodes | Unimplemented zero-fallback nodes | ConvTranspose |
|---|---|---:|---:|---:|
{graph_rows}

Coverage fractions use each graph's node count as denominator; they are not
runtime or energy shares. {shape_text} Recomputed totals match the historical
saved totals for {totals_matching}/{op['graph_count']} graphs;
{op['historical_candidates_bound']} candidate feature records are checked against
their bound originals. A change confined to the unused ConvTranspose branch
cannot affect these graphs' totals, prefix/suffix shares or ranks.
[Operator inventory](operator_inventory.csv), [calculation and source scope](convtranspose_audit.json).

The later 450-row deployment export binds
{op['later_deployment_full_graph_bound_rows']} rows to these exact full hashes;
{missing} rows lack `model_sha256`. Fourteen confirmation UID-to-full-graph
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

`{score['variant']}` changes only the affected temporary objective input from
decimal MB to binary MiB; coefficients, candidates, normalization universes,
eligibility filters and exact tie rules remain fixed. It reproduces all
{score['counts']['frozen_method_scores_verified']} saved method-score entries
before comparing variants. The pure boundary-bytes ranker is unaffected.
[Field definitions](score_units.csv), [candidate deltas](score_rank_deltas.csv).

Accelerator-fit: {fit['score_changed_candidates']} changed scores,
{fit['rank_changed_candidates']} changed rank positions and
{fit['full_universe_top1_changes']} complete-universe or
{fit['published_subset_top1_changes']} eligible-subset Top-1 changes.
Stream heuristic: {stream['rank_changed_candidates']} changed rank positions,
{stream['full_universe_top1_changes']} complete-universe Top-1 changes and
{stream['published_subset_top1_changes']} changed eligible-subset selections
({transition_text}). Those subset changes are overlapping static projections,
not independent experiments. The existing minimum-three-candidates gate is
retained. A unit conversion with fixed empirical coefficients does not establish
physical ms/FPS calibration. [Full comparison and unchanged controls](score_audit.json).

## MobileNet source gap

The full UID is `{mobile['uid']}`. Its selected quality source leads to the
central replay at `{mobile['historical_evaluation']['at']}`, with request
`{mobile['historical_evaluation']['central_replay_request_sha256']}` and fingerprint
`{mobile['historical_evaluation']['evaluation_fingerprint']}`.
This replay differs from the original runtime request. Candidate and CPU
reference prediction bytes and record ordering were checked without calculating
quality. The archived inventory records historical evaluator-source bindings
for {bindings['recorded_evaluator_source_bound_count']} of its
{bindings['selected_configuration_count']} selected UIDs; this audit checks that inventory rather than
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
python3 -I -B {SCRIPT} \\
  --output ../v53-audit-check --verify
```

Use an absent or empty external output directory. The command rechecks compact
source bindings, runs only the audit's focused tests, regenerates all reports
and compares them byte for byte with the committed audit. It does not rerun the
original-source capture or the historical A commands. To refresh the owned
audit outputs after an intentional source/code change, omit `--verify` and use
`--output {STUDY}`. Never refresh historical measurements.

Path A was actually executed in new directories: the main numeric reproduction
verified {a_main} scientific files and the confirmation reproduction matched all {a_confirmation}
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
"""
    (output / "README.md").write_text(readme)
    insert = f"""# Evidence-linked text for later thesis integration

For Appendix C: the historical ConvTranspose rule is a dense output-based
proxy. Independent coordinate enumeration for a single-channel 2×2 input and
2×2 kernel, stride two, and no padding or bias gives
{op['counterexample']['direct_products']} direct products, whereas the historical
rule gives {op['counterexample']['historical_dense_proxy']} proxy units. Neither
quantity is a measurement of backend instructions. The historical d164aad6
definition and published db729b9 source contain the same inspected counting
bytes; the inspected campaign manifests do not bind these analyzer bytes to a
particular historical process. [Counterexample, formula and source distinction](convtranspose_audit.json).

The audit inspected {op['graph_count']} hash-bound full ONNX graphs
({op['inspected_full_graph_nodes']} nodes in total): MobileNetV3-Large,
RegNetX-1.6GF, ResNet-50, YOLO11l, YOLO26m, YOLO26s and YOLOv7. None contains
ConvTranspose, so changing only that counting branch leaves their proxy totals
and associated prefix/suffix shares unchanged. Recomputed totals match the
recorded historical totals for {totals_matching}/{op['graph_count']} graphs.
Coverage statistics are node fractions, not runtime fractions.
The assertion is confined to the listed hashes:
{op['later_deployment_full_graph_bound_rows']} of the 450 later deployment rows
bind to them, while {missing} lack a model hash. Distinct source/build part
graphs were referenced but not inspected. [Exact hashes, operators, coverage and cohort bindings](convtranspose_audit.json),
[operator table](operator_inventory.csv).

For the score-unit discussion: decimal `cut_bytes/10^6` values enter historical
accelerator-fit thresholds labelled in MiB. The separate `{score['variant']}`
comparison supplies `cut_bytes/2^20` to that input while retaining the original
candidate universe, filters, coefficients and tie rules. It reproduces
{score['counts']['frozen_method_scores_verified']} historical score entries
before comparison. Accelerator-fit changes {fit['rank_changed_candidates']}
rank positions, with no complete-universe or eligible-subset Top-1 change.
The stored stream heuristic changes {stream['rank_changed_candidates']} rank
positions and {stream['published_subset_top1_changes']} overlapping subset
selections ({transition_text}); all complete-universe Top-1 choices remain
unchanged. Boundary-bytes, weighted and bottleneck controls remain unchanged.
The ms/FPS-labelled heuristics do not gain physical calibration from this
conversion, and the current deployment winners and measured values are
preserved. [Unit definitions](score_units.csv), [rank deltas](score_rank_deltas.csv),
[selection scopes, eligibility and controls](score_audit.json).

For the reproducibility appendix: the selected UID
`{mobile['uid']}` is linked through its selected quality result to the central
replay request `{mobile['historical_evaluation']['central_replay_request_sha256']}`
and fingerprint `{mobile['historical_evaluation']['evaluation_fingerprint']}`.
This is a later evaluation than the original runtime request. The candidate
and CPU-reference prediction files were hash/format checked without recomputing
quality. The historical execution-to-evaluator binding remains incomplete:
the bounded sources contain no contemporaneous receipt binding that replay to
the loaded evaluator, service/helper code and Python/NumPy environment.
Preserved later code or matching quality values cannot establish this missing
history. [Full UID chain, inspected sources, checks and exact open fields](mobilenet_evaluator_binding.json).

Three reproduction levels are distinguished. Level A was executed using safe
offline table commands: {a_main} main-study scientific files and all {a_confirmation} confirmation
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
"""
    (output / "thesis_insert.md").write_text(insert)


def task_statuses(output: Path) -> list[dict]:
    op = read(output, "convtranspose_audit.json")
    mobile = read(output, "mobilenet_evaluator_binding.json")
    return [
        {
            "task": 1, "status": "completed_with_limits",
            "checks": ["Repository identities and base/pinned commits frozen",
                       "Actual compact inputs and audit code hashed",
                       "Historical definitions separated from execution binding",
                       "Original tool dirty tree excluded from implementation"],
            "evidence": ["source_manifest.json", "inputs/source_context.json",
                         "inputs/operators/source_bindings.json"],
            "open_points": ["Local v53 thesis source not found",
                            "Original process-to-analyzer-module hash binding not recorded in inspected critical-module lists"],
            "affected_claims": ["Exact historical analyzer execution", "Direct manuscript reconciliation"],
            "next_action": "Obtain the exact v53 source only for manuscript reconciliation; obtain historical execution receipts for any stronger process attribution.",
        },
        {
            "task": 2, "status": "completed_with_limits",
            "checks": ["16 direct products independently enumerated; 64 historical proxy checked against original code",
                       "Groups, cropped contributions and dilation tested",
                       f"{op['graph_count']} original full graphs / {op['inspected_full_graph_nodes']} nodes inspected and hash bound",
                       "Historical totals and candidate feature correspondence checked",
                       "Current deployment and confirmation identities kept separate from part-graph references"],
            "evidence": ["operator_inventory.csv", "convtranspose_audit.json", "inputs/operators/graphs.json"],
            "open_points": op["limitations"] + ["Distinct part graphs referenced but not inspected"],
            "affected_claims": ["ConvTranspose absence outside inspected full-graph hashes",
                                "Runtime-weighted operator coverage"],
            "next_action": "Obtain missing model identities and exact part graph bytes only if those separate graphs are to be included in an operator claim. No hardware execution is needed.",
        },
        {
            "task": 3, "status": "completed",
            "checks": ["Historical scores exactly reconstructed before comparison",
                       "Decimal MB versus binary MiB discrepancy reproduced",
                       "Versioned score/rank comparison with unchanged universe, gates and ties",
                       "Unaffected byte, weighted and bottleneck controls verified"],
            "evidence": ["score_units.csv", "score_rank_deltas.csv", "score_audit.json"],
            "open_points": ["Physical ms/FPS calibration is not established by this comparison",
                            "Historical GUI SystemSpecs and Native handover models remain unavailable"],
            "affected_claims": ["Physical timing prediction", "Unavailable historical score families"],
            "next_action": "No additional action required for the unit audit. Any calibration or missing-model study would be a separately scoped task.",
        },
        {
            "task": 4, "status": "completed_with_limits",
            "checks": ["Full UID, original runtime request, later replay, receipt and selected result cross-linked",
                       "Original referenced source files checked against projected hashes/pointers",
                       "Selected candidate/reference hashes, sampled record schema and all image-ID pairing checked",
                       "No quality evaluator or bootstrap executed"],
            "evidence": ["mobilenet_evaluator_binding.json", "inputs/binding/source_bindings.json"],
            "open_points": mobile["open_fields"],
            "affected_claims": ["Historical execution-to-evaluator/environment binding for the selected MobileNet split"],
            "next_action": mobile["next_required_evidence"],
        },
        {
            "task": 5, "status": "completed_with_limits",
            "checks": ["A: actual safe numeric reproduction in fresh external outputs",
                       "B: bounded source/CLI review and selected input hash/format controls",
                       "C: source and prerequisite inventory only"],
            "evidence": ["reproduction_paths.json", "inputs/reproduction/"],
            "open_points": ["B derivations and C physical runs were not executed or certified by this audit",
                            "Full individual-data environments and historical execution-source bindings are not restored"],
            "affected_claims": ["End-to-end individual metric/raw-signal or physical repeatability"],
            "next_action": "Use per-route prerequisites to scope any later explicitly authorized reproduction. No new run is needed to close this inventory task.",
        },
    ]
