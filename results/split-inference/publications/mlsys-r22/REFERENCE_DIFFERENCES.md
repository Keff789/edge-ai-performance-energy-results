# R22 reference differences

The reference manuscript remains unchanged. Numeric results are calculated from the repository inputs; paper PDF bytes are not used as regenerated-data targets.

| Output | Reference issue | Resolution and source |
|---|---|---|
| `vendor_quality_recovery_table` | The older THESIS20 generator uses DeepX MobileNet b027 quality 0.7222, producing 72.22% and +0.50 pp. The active R22 table already uses the current 0.7218. | Bind the new export to the current Native b027 and Full UIDs in `PAPER_DATASET`, yielding 72.18% and +0.46 pp. Check H8 and H10 likewise; retain the historical table in its original study. This corrects generator binding, not the active paper value. |
| `r21_winner_repeat_ranges` | R22 prints a dash for YOLO26s/H8 b021 split energy because its compact extract lacks three repeats. | The exact UID `native|yolo26s|H8|hailo8_to_trt|b021` has three source-bound `refresh16_20261013` energy repeats in the canonical energy-repeat export. The generated complete range is 157.56–157.72 mJ/image; its mean remains unchanged. These are original samples, not inferred confidence limits or new measurements. |

Paper-sized layouts, stable rendering metadata, standalone table labels and publication navigation are export adaptations. Numerical CSV/JSON values retain full precision, while paper display rounds FPS to integers and energy to mJ/image. Observed three-repeat ranges are minima/maxima, not confidence intervals. CPU-relative quality intervals are not paired split-minus-Full intervals.

The current source audit projections are verified offline from their compact published contents; optional reconstruction from the original large archives is a separate provenance check. Existing historical mean(N/T) energy-window rates are recomputed separately from current performance medians in `data/historical_yolo11l_windows.json`. No unresolved numerical reference differences were identified by the registered checks.
