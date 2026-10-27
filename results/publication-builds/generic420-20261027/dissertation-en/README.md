# English dissertation figures and tables

The complete English split and paper build is in [paper](../paper). The same current RQ2 and corrected RQ3 studies feed the English and German outputs. Original RQ1, Native, Full and energy observations retain their recorded values.

The source index below links the existing English artifacts for every registered dissertation bundle. Historical supplementary studies keep their own populations and captions. `ASSET_MANIFEST.json` records each selected file and its SHA256.

| Bundle | Files | Source |
|---|---:|---|
| mlsys-r22 | 80 | [English artifacts](../paper/publications/mlsys-r22) |
| mlsys-r30 | 99 | [English artifacts](../paper/publications/mlsys-r30) |
| rq3-generic420 | 67 | [English artifacts](../paper/rq3-generic420/en) |
| split-inference | 81 | [English artifacts](../paper) |
| supplementary-studies/dissertation-development-2026 | 21 | [English artifacts](../../../supplementary-studies/dissertation-development-2026) |
| supplementary-studies/mlsys-selection-20261007 | 37 | [English artifacts](../../../supplementary-studies/mlsys-selection-20261007) |
| supplementary-studies/native-endpoint-reconstruction | 12 | [English artifacts](../../../supplementary-studies/native-endpoint-reconstruction/tables) |
| supplementary-studies/rq2-all-cuts-20261020 | 13 | [English artifacts](../../../supplementary-studies/rq2-all-cuts-20261020) |
| supplementary-studies/stage-cost-composition | 8 | [English artifacts](../../../supplementary-studies/stage-cost-composition) |
| supplementary-studies/thesis20-ranking-20261005 | 6 | [English artifacts](../../../supplementary-studies/thesis20-ranking-20261005) |
| supplementary-studies/yolov7-completion-20261007 | 1 | [English artifacts](../../../supplementary-studies/yolov7-completion-20261007) |

The [German dissertation export](../dissertation-de/README.md) records translation coverage and numerical checks. Both wide and single-column YOLOv7 b066 figures use the frozen original values.

Recreate this source index and the integration verification after the normal paper and German dissertation builds:

```sh
python -I -B scripts/dissertation/finalize_generic420_publication.py
```

The complete preceding commands, including both `--rq2-study` and `--generic420-study`, are recorded in [INTEGRATION_VALIDATION.json](../INTEGRATION_VALIDATION.json).
