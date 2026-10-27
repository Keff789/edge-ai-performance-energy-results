# Generic420 closeout and publication artifacts — 27 October 2026

**Generic420 complete.** The frozen selection contains seven models, twenty cuts per model, and three accelerators. All 359 supported FPS configurations are accepted; 61 configurations have documented technical exclusions. The quality partition is 331 admitted, 28 excluded, and 0 open.

H8 / YOLOv7 / b009 has a new accepted Generic FPS observation and a new verified quality observation. Its three unrounded FPS repetitions are 41.13953018707622, 41.263681919555594, and 41.19388564433142; the median is **41.19388564433142 FPS**. Its primary COCO AP@[.50:.05:.95] (`coco_ap_50_95`) is 0.45791324238237674 versus CPU 0.460346586685622, classified `reference_close` after N=5000/B=1000 evaluation. The separate original Native preprocessing-authority hold remains unresolved; this new Generic observation does not supply the missing original Native execution recipe. See [the exact current observation and retained hold](closure_b009.json). No new Native, Full, or energy measurements were made for this follow-up.

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
| yolo11l | H8 | 20 | 8 | 8 | 0 | 12 | 0 |
| yolo11l | H10 | 20 | 11 | 11 | 0 | 9 | 0 |
| yolo11l | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolo26m | H8 | 20 | 9 | 7 | 2 | 11 | 0 |
| yolo26m | H10 | 20 | 9 | 9 | 0 | 11 | 0 |
| yolo26m | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolo26s | H8 | 20 | 11 | 7 | 4 | 9 | 0 |
| yolo26s | H10 | 20 | 11 | 11 | 0 | 9 | 0 |
| yolo26s | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| yolov7_paper | H8 | 20 | 20 | 19 | 1 | 0 | 0 |
| yolov7_paper | H10 | 20 | 20 | 19 | 1 | 0 | 0 |
| yolov7_paper | DeepX | 20 | 20 | 20 | 0 | 0 | 0 |
| **Total** | | **420** | **359** | **331** | **28** | **61** | **0** |

The technical exclusions comprise 37 compiler failures and 24 unsupported configurations. The [machine-readable matrix](closure_matrix.json), [420 case identities](closure_cases.csv), and [closure validation](closure_validation.json) preserve the accounting, original source epochs, and selection hashes.

[Final owner and queue receipts](closure_process_status.json) retain current H8/H10 completion evidence and the final central worker shutdown. Source capture and central quality receipts are separate from outer workflow status: the final H10 outer action returned 1, while its normal N=5000 source capture and central quality evaluation completed successfully.

Ledger SHA-256: `d658eb195bcb20322c587c47180fc6c4d78003c9368e206943e0ab9ae1c55216`.

## Analyses and scope

[RQ2](../rq2-native-scope-20261027/README.md) considers the original 204 Native cuts, including all twelve recovered pairs outside fixed420. Of the 204 original cuts, 203 have compatible pairs: 186 pass the retained quality rule and 17 fail it. The remaining original Native case is held because its preprocessing authority remains unproved. All 21 eligible model/device groups contain at least two cuts; the overall and n≥2-group means are identical. The fresh H8/YOLOv7/b009 Generic FPS and quality are complete; another Generic capture cannot establish its missing historical Native authority.

The target below is **Native throughput loss after selecting by Generic**, with equal group weighting. Historical/current comparisons use exactly the same current admitted pairs.

| Scope | Candidates | Groups | Current Generic loss | Historical Generic, same pairs |
|---|---:|---:|---:|---:|
| all | 186 | 21 | 1.346752% | 15.077129% |
| classification | 151 | 9 | 3.118901% | 32.804339% |
| detection | 35 | 12 | 0.017640% | 1.781722% |

The prior importer omitted twelve measured pairs because it used only the RQ3 intersection. Separately, the affected Hailo Generic quality path ignored its verified interface binding when no Native binding was present, omitting the physical-memory layout transform required by the reused Part2 engine. The targeted fix restores that existing transform. The [source comparison](../rq2-native-scope-20261027/inputs/current_fps_reuse_after_quality_fix.json) confirms that the fifteen affected existing FPS observations already applied it, so their FPS was reused. Seventeen new quality captures and central evaluations, including fresh b009 and the extra H10 b038, complete the corrected evidence. A separate local mini-AP coordinate-frame defect was not used as a central quality result.

The preliminary published intersection had 159 admitted pairs in 13 groups and a 2.159239% current-Generic mean loss. It is a different cohort, so its difference from the present 186-pair result is not an isolated algorithm improvement. Original Native, Full and energy values remain unchanged; new Generic throughput has no derived or reused energy. Native quality retains its established historical numerical gate. Source-scoped additional-NMS differences for the existing H8/H10 YOLO26m/b043 Native quality evidence remain documented in RQ2's quality-contract provenance; exact timed Native endpoint AP is not inferred from an artifact match alone.

[RQ3](../rq3-generic420-detector-corrected-20261027/README.md) retains all 420 selected identities and evaluates **measured Generic throughput** over 331 admitted candidates in 21 groups. The original 2,111-row graph-feature universe, normalization, operations proxy and standard weights (1,3,0.2) are unchanged. One complete model, across all accelerators, is held out per fold. A budget k tests min(k,n) cuts and retains the fastest; groups are equally weighted and the primary training objective averages k=1,3,5. Each fold has one ranking for all budgets. Boundary size (1,0,0) remains in the search space.

| Method | k=1 | k=3 | k=5 |
|---|---:|---:|---:|
| boundary_size | 22.224463% | 15.828006% | 6.610356% |
| weighted_default | 34.771105% | 32.265247% | 21.708820% |
| global | 22.481569% | 19.346566% | 10.519977% |
| task | 25.463220% | 17.773157% | 10.956996% |
| device | 21.112468% | 15.292203% | 9.888455% |
| task_device | 17.741997% | 13.338409% | 9.800775% |

The prespecified shared/global fit remains primary, although boundary size has lower mean held-out loss on this corrected cohort. The full-data descriptive shared weights are (0.215, 0.035, 0.750); these are not holdout scores or a substitute for the seven distinct held-out fold weights. The previous release had 315 eligible candidates; sixteen corrected/missing quality admissions change the candidate pool, and b009 has its new measured FPS. Comparisons across the 253-, 315- and 331-candidate releases are cohort comparisons, not constant-cohort estimates of a better fitting algorithm. All four fit scopes and the original sensitivities are retained.

Graph-score → Generic → Native remains a practical recommendation, not a jointly validated end-to-end search pipeline.

## Paper and dissertation artifacts

The existing active [paper EN/DE build](../../publication-builds/generic420-20261027/paper/) and [German dissertation collection](../../publication-builds/generic420-20261027/dissertation-de/) have been replaced from both current studies. The [English dissertation source index](../../publication-builds/generic420-20261027/dissertation-en/) binds the complete English core/current outputs and registered supplementary sources. Shared colors, typography, wide and single-column b066 variants are retained. RQ1 and all b066 numerical evidence are unchanged. No manuscript text or R37 source was overwritten. The historical `mlsys-r30` preset name is only a tool interface.

## Reproduction from published inputs

Install the existing `scripts/split-inference/requirements-r30.txt` and `scripts/supplementary-studies/rq3-generic420/requirements.txt` in a Python 3.12 environment. From the repository root, use fresh output directories:

```bash
RQ2_INPUTS=results/supplementary-studies/rq2-native-scope-20261027/inputs/observations.json
RQ3_INPUTS=results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs
python3 -B scripts/supplementary-studies/rq2-native-scope-20261027/reproduce.py \
  --input "$RQ2_INPUTS" --output local-output/rq2 --verify
python3 -B scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs "$RQ3_INPUTS" --output local-output/rq3 --languages en de
python3 -B scripts/supplementary-studies/rq3-generic420/verify.py --study local-output/rq3
python3 -B scripts/split-inference/reproduce.py \
  --publication mlsys-r30 --languages en de --output local-output/paper \
  --rq2-study local-output/rq2 --generic420-study local-output/rq3 --verify
python3 -B scripts/dissertation/reproduce.py \
  --source local-output/paper --output local-output/dissertation-de \
  --rq2-study local-output/rq2 --generic420-study local-output/rq3 --verify
```

The canonical active-tree indexing step is `python3 -B scripts/dissertation/finalize_generic420_publication.py`; it regenerates the English dissertation source manifest and validates the existing canonical release paths. It does not render or alter scientific results. The exact canonical generation commands and their input hashes are recorded in [integration validation](../../publication-builds/generic420-20261027/INTEGRATION_VALIDATION.json). Both study arguments are required: the RQ3 hook alone does not update RQ2.

## Verification, preservation and release binding

[Result changes](RESULT_CHANGES.json), [cohort/fit losses](graph_score_loss_comparison.csv), and [shared fold-weight changes](shared_fold_weight_comparison.csv) retain unrounded values. [RQ2 verification](RQ2_VALIDATION.json), [RQ3 verification](RQ3_VALIDATION.json), and [publication verification](PUBLICATION_VALIDATION.json) record the normal builds and bounded independent checks. The complete published-input RQ3 rebuild matches all 169 scientific/public files including eighteen figures; only the generated README path and its manifest entry differ.

The immutable core snapshot is `rq2_detector_followup_20261027/generic420_d658eb195bcb2032`, with export-manifest SHA256 `0922ac0b02f8053ffdc92fb466a87401444352c8731b9607c31c99678cde0e8f`. Its 1,162 files (443,288,537 bytes) bind the corrected ledger. [The portable backup receipt](PORTABLE_BACKUP_RECEIPT.json) separately records retained current FPS repetitions, all seventeen new quality captures, verified raw supplements, required physical artifacts and known historical limitations. The old b009 observation remains superseded history, never an additional current case. Analysis-core completeness is not a claim that previously authorized-deleted per-image data can be recovered; full historical raw preservation remains false.

[The release manifest](MANIFEST.json) and [active pointer](../../ACTIVE_GENERIC420.json) bind current curated inputs, analysis code, tables and EN/DE assets. The verified remote Git commit is recorded with this snapshot after regular push, without a circular commit hash inside the committed manifest. The separate unresolved Native-authority hold remains visible; this release does not claim complete Native provenance for that pair.
