# Current seven-model Weighted-score analysis

The intended analysis includes all seven models with 187 quality-eligible
Native/Generic pairs in 21 model/device groups: 151 classifier pairs and 36
detector pairs. Measurements and quality decisions remain unchanged.

The script requires complete verified current graph features for every model.
It never silently fills missing operation counts or imbalance values. The internal analysis API offers an explicit incomplete-model diagnostic option;
the registered reproduction entry points require all seven models.

## Reproduction

From the repository root, with the pinned dependencies in
`scripts/split-inference/requirements-r30.txt`:

```sh
python -I -B scripts/supplementary-studies/rq2-weighted-20261020/reproduce.py \
  --output ../weighted-reproduced --verify
```

The command verifies and unpacks `inputs/current_graph_feature_inputs.zip` in
temporary storage, recomputes the versioned operation extension, fits all seven
model holdouts, exports full-precision results and checks the two operation-cost
sensitivity variants. It does not use the network or benchmark hardware.
The original graph capture, license and source manifests are retained verbatim
in that compact archive. Its `MANIFEST.json` defines the required subset.

The registered publication command also renders the existing paper assets,
the five-curve weighted figure and both YOLO case-study layouts:

```sh
python -I -B scripts/split-inference/reproduce.py --publication mlsys-r30 \
  --output ../mlsys-r30-reproduced --verify
```

Add `--numeric-only` to skip image rendering. R30 verification compares numeric
CSV/JSON/TeX artifacts, including the unchanged frozen R22 measurement payloads.
R22 remains the default profile and retains its original verification policy.
New figures and tables are under `publications/mlsys-r30` in the output.
Inputs originate from repository commit `d323645da002b5e24949d6106429c078e509a00b`;
source and input hashes are recorded in `PROVENANCE.json` and `analysis/summary.json`.

## Formula and candidate population

The score is the printed ARCS formula:

`w_comm * minmax(log10(1 + Comm)) + w_imb * Imb_raw + w_tensors * minmax(T_raw)`.

`Comm` is the logical volume of tensors crossing the boundary. `Imb_raw` is
`abs(F_left - F_right) / (F_left + F_right)`. `T_raw` is
`max(crossing_tensor_count - 1, 0)`.

Communication and tensor-count normalization use the complete regular workflow
candidate universe of each current graph, before measured-cut or quality
filtering. Membership and normalization ranges are checked against the export.
Imbalance is used directly, without the additional normalization performed by
the archived tool implementation. Every measured cut has a single crossing
tensor, so its tensor penalty is zero and the tensor weight stays fixed at 0.2.

The final seven-model run uses the explicitly versioned operation proxy
`analytic-operation-proxy-r29-extended-v1`. This adds defined analytic operation
counts for 15 previously unsupported nodes in YOLO11l, YOLO26m and YOLO26s.
The already complete three classifiers and YOLOv7 are unchanged. This is a new
documented graph-cost proxy extension, not recovery of unspecified historical
counter rules. The original graph identities, boundary bytes, tensor counts,
pair bindings and throughput measurements remain unchanged.

## Methods and fitting

- **Bytes:** increasing logical boundary volume.
- **Generic:** decreasing measured Generic throughput.
- **Weighted, default:** weights `(1, 3, 0.2)`.
- **Weighted, shared R28:** fixed `(1, 0.15799266978091375, 0.2)`, learned on all
  three classifiers in R28 and applied unchanged to every model. Its classifier
  results are in-sample. Its detector results measure transfer from classifiers.
- **Weighted, pooled fit:** one common weight ratio optimized retrospectively
  using every included model/device group. These are in-sample results.
- **Weighted, model held-out:** one whole model is excluded on all three
  devices, the weights are fitted on the remaining models, and the excluded
  model provides the test result. Every displayed group has its own model
  absent from the corresponding training fold.

Frozen calibrated Generic has confirmed predictions for only 151 classifier
pairs. No confirmed detector predictions exist. It is unavailable for the
combined population and is not represented by a reduced-group average or by
extrapolated values.

The fit minimizes mean percentage Native-throughput loss at budgets 1, 3,
and 5. Every model/device group and every budget receives equal weight. The
communication and imbalance weights are nonnegative and share one ratio across
devices. The exhaustive one-dimensional search evaluates all ranking-change
intervals and their boundaries. The representative solution is the midpoint
of the widest optimal interval, with smaller alpha breaking equal-width ties.
An independent 1,001-point grid checks each fit.

## Budget and aggregation

Every budget keeps the same complete set of groups. A group with `n` candidates
tests `min(k, n)` of them. Each detector group contains three measured cuts, so
its loss is zero from `k = 3` onward. It remains part of the mean thereafter.
This prevents the population from changing as the budget grows.

Selection uses unrounded Native FPS. Configuration identity breaks score ties.
Throughput loss is measured relative to the best observed Native cut in the
same model/device group.

## Outputs

Numerical outputs are in `analysis/`; the derived full-graph features, operation
audit and normalization populations are in `features/`. The original pair binding
file is kept once in the input archive.

- `summary.json`: complete protocol, scope, weights, fitting intervals, input
  hashes and coverage/identity checks.
- `key_budget_results.csv`: combined results at 1, 3 and 5 trials.
- `aggregate_curves.csv`, `group_curves.csv`, `task_curves.csv`: every budget
  from 1 to 20, with fixed group counts.
- `fold_weights.csv`, `fold_memberships.csv`: fitted weights and exact
  train/test configuration identities.
- `complete_rankings.csv`: every method's selected order for every group.
- `candidate_features.csv`: verified current features used by the score.

Generators require a fresh output directory and do not modify their source inputs.

## Seven-model results

The final population contains all 187 eligible pairs and all 21 groups.
Optimizing one common ratio on all seven models yields the same representative
weights as the earlier classifier fit: `(1, 0.15799266978091375, 0.2 fixed)`.
Shared and pooled curves therefore coincide. This numerical agreement does not
turn their in-sample classifier results into held-out results.

| Method | 1 trial | 3 trials | 5 trials |
|---|---:|---:|---:|
| Bytes | 17.23% | 9.32% | 3.80% |
| Generic | 15.08% | 10.19% | 8.76% |
| Weighted, default | 15.73% | 10.01% | 7.37% |
| Weighted, shared / pooled | 16.67% | 5.08% | 2.96% |
| Weighted, model held-out | 18.77% | 11.34% | 4.90% |

The leave-one-model-out imbalance weights are 0.569343 for MobileNet, 0.157993
for RegNet, 0.025085 for ResNet, and 0.157993 for each of the four YOLO test
models. Communication weight is 1 and tensor weight is fixed at 0.2.

## Operation-cost sensitivity

The 15 newly modeled nodes use the declared `analytic-operation-proxy-r29-extended-v1`
rules for stable Softmax, ReduceMax, integer Mod and a deterministic TopK reference
algorithm. These scalar operation counts are a graph-analysis convention, not a
prediction of compiler instructions or device latency. All previous counts remain
unchanged. Multiplying only the added counts by 0.1 and by 10 changes none of the
84 complete ranking comparisons per variant at the main default, shared, pooled
and held-out weights. This checks those fixed rankings, not every possible fit.
See `analysis/sensitivity_fixed_weights.json` and `features/added_operation_nodes.json`.

Candidate features preserve the original audit flags and additionally expose
`current_graph_feature_identity_verified` and `current_operation_features_complete`
for the new verified bindings. Original detector audit availability flags therefore
remain distinguishable from the complete features used by this analysis.
