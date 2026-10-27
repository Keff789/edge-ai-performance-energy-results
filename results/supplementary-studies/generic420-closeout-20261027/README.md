# Generic420 closeout and publication artifacts — 27 October 2026

**FPS-complete; one historical quality association remains unresolved.** The frozen selection contains seven models, twenty cuts per model, and three accelerators. All 359 supported FPS configurations are accepted; 61 configurations have documented technical exclusions. The quality partition is 315 admitted, 43 excluded, and one unresolved. This dated release does not claim to replace a fully quality-resolved dataset.

The unresolved case is H8 / YOLOv7 / b009: its original FPS execution lacks an authenticated preprocessing binding. Its FPS remains valid; historical quality is not substituted for that missing binding. See [the exact gap](closure_b009.json). No new Native, Full, energy, or hardware campaign was run for this closeout.

## Closure matrix

FPS is an overlapping availability count. The disjoint partition is **planned = quality admitted + quality excluded + technical excluded + open**.

| Model | Accelerator | Planned | FPS | Quality admitted | Quality excluded | Technical excluded | Open |
|---|---|---:|---:|---:|---:|---:|---:|
| mobilenet_v3_large | H8 | 20 | 20 | 10 | 10 | 0 | 0 |
| mobilenet_v3_large | H10 | 20 | 20 | 11 | 9 | 0 | 0 |
| mobilenet_v3_large | DeepX | 20 | 20 | 19 | 1 | 0 | 0 |
| regnet_x_1_6gf | H8 | 20 | 20 | 20 | 0 | 0 | 0 |
| regnet_x_1_6gf | H10 | 20 | 20 | 20 | 0 | 0 | 0 |
| regnet_x_1_6gf | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| resnet50 | H8 | 20 | 20 | 20 | 0 | 0 | 0 |
| resnet50 | H10 | 20 | 20 | 20 | 0 | 0 | 0 |
| resnet50 | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolo11l | H8 | 20 | 8 | 6 | 2 | 12 | 0 |
| yolo11l | H10 | 20 | 11 | 9 | 2 | 9 | 0 |
| yolo11l | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolo26m | H8 | 20 | 9 | 4 | 5 | 11 | 0 |
| yolo26m | H10 | 20 | 9 | 6 | 3 | 11 | 0 |
| yolo26m | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolo26s | H8 | 20 | 11 | 5 | 6 | 9 | 0 |
| yolo26s | H10 | 20 | 11 | 9 | 2 | 9 | 0 |
| yolo26s | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolov7_paper | H8 | 20 | 20 | 18 | 1 | 0 | 1 |
| yolov7_paper | H10 | 20 | 20 | 18 | 2 | 0 | 0 |
| yolov7_paper | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| **Total** | | **420** | **359** | **315** | **43** | **61** | **1** |

The technical exclusions comprise 37 compiler failures and 24 unsupported configurations. The [machine-readable matrix](closure_matrix.json), [420 case identities](closure_cases.csv), and [closure validation](closure_validation.json) preserve the accounting, observed completion time, original runner revisions, and selection hashes.

Ledger SHA-256: `36d0a02e1b941edb08a179ed05a0e9e38056eef6544ea6a5d135e4850b3b2e3e`.

## Analyses and scope

- [RQ2: current Generic / existing Native](../rq2-generic-final-20261027/README.md): 192 artifact-verified pairs; 159 pairs in 13 groups pass both quality gates. Eight groups have no eligible paired candidate. The mean loss in **Native throughput** from selecting by Generic is 2.159239%, compared with 22.959196% using the earlier Generic values on exactly the same pairs. The earlier published 15.077129% used 187 eligible pairs in 21 groups and is a different cohort. Original Native, Full and energy records are preserved. Refreshed Generic pairs carry no derived or reused energy. Historical graph weights remain frozen in this paired comparison.
- [RQ3: measured Generic throughput](../rq3-generic420-20261027/README.md): quality-admitted Generic candidates, independent of Native availability. Each fold excludes one entire model across devices. A budget k tests min(k,n) cuts and retains the fastest; model/device groups are equally weighted. The primary training loss averages budgets 1, 3 and 5. All four fit scopes and the specified sensitivity analyses remain available.
- [Paper EN/DE outputs](../../publication-builds/generic420-20261027/paper/) and [German dissertation outputs](../../publication-builds/generic420-20261027/dissertation-de/) share these studies. The English dissertation source is the complete English paper/split output plus the retained English supplementary studies. RQ1 and both widths of the YOLOv7 case study retain their frozen numerical evidence. The preset name `mlsys-r30` is a tool interface; no R36/R37 manuscript text was replaced.

Graph-score → Generic → Native is a practical recommendation, not a jointly validated end-to-end search experiment.

## Reproduction from published inputs

Install `scripts/split-inference/requirements-r30.txt` and `scripts/supplementary-studies/rq3-generic420/requirements.txt` in a separate Python 3.12 environment. Run from the repository root with fresh output directories:

```bash
RQ2_STUDY=results/supplementary-studies/rq2-generic-final-20261027
RQ3_STUDY=results/supplementary-studies/rq3-generic420-20261027
python3 -B scripts/supplementary-studies/rq2-generic-final-20261027/reproduce.py \
  --output local-output/rq2-reproduced --verify
python3 -B scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs "$RQ3_STUDY/inputs" --output local-output/rq3-reproduced --languages en de
python3 -B scripts/supplementary-studies/rq3-generic420/verify.py \
  --study local-output/rq3-reproduced
python3 -B scripts/split-inference/reproduce.py \
  --publication mlsys-r30 --languages en de --output local-output/paper \
  --rq2-study local-output/rq2-reproduced --generic420-study local-output/rq3-reproduced --verify
python3 -B scripts/dissertation/reproduce.py \
  --source local-output/paper --output local-output/dissertation-de \
  --rq2-study local-output/rq2-reproduced --generic420-study local-output/rq3-reproduced --verify
```

The immutable internal Sprite snapshot retains source metadata and separate raw-preservation evidence. The source export being complete does not imply all historical per-image predictions still exist: some completed captures were explicitly deleted under the preceding retention policy. Public inputs contain the repeat measurements, quality admissions, graph features and identities required for the published analyses; private archive locations are not included.

## Actual result changes

The primary RQ3 shared fit has mean held-out Generic throughput losses of **25.112249%, 17.098464%, 6.076342%** at 1, 3 and 5 tested cuts. Boundary size gives **24.875137%, 15.669239%, 5.681425%**; the common learned fit does not outperform it on this expanded held-out cohort. The prespecified main fit is retained. The prior package used 253 candidates in 19 groups, versus 315 in 21 now; its shared-fit losses were 20.920284%, 10.007736%, 4.330838%. These are different candidate pools, not a paired constant-cohort improvement comparison.

[Full result changes](RESULT_CHANGES.json), [all four fits and baseline comparison](graph_score_loss_comparison.csv), and [shared fold weights](shared_fold_weight_comparison.csv) retain the unrounded values. [RQ3 verification](RQ3_VALIDATION.json) records the byte-identical rebuild from public inputs and the independent checks; [RQ2 verification](RQ2_VALIDATION.json) records the paired-data and frozen-evidence checks.

## Preservation and release binding

[The portable backup receipt](PORTABLE_BACKUP_RECEIPT.json) confirms the pinned 1,110-file analysis core and all 359 original accepted FPS containers, including 1,077 individual repetition records, input bindings and completion contracts. It separately records 744 preserved quality-metadata references. Full raw preservation is explicitly false: previously authorized deletions of completed per-image captures are not undone, and some historical metadata versions and remote binary payloads are outside this guarantee. The exact archive locators and supplemental checksums remain in the internal Sprite snapshot.

[The release manifest](MANIFEST.json) binds curated inputs, source code, analysis results and publication artifacts to this ledger and export. The resulting Git commit is recorded alongside the snapshot after the regular push has been verified. The unchanged legacy R22 evidence audit is reused by a relative in-repository link instead of republishing a duplicate report containing old workstation paths. Earlier studies and manuscript sources remain untouched.
