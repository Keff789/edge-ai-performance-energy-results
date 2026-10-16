# Figure captions and numerical checks

All figures use fixed physical sizes; embed at their recorded width. Fonts are 7.5 pt or larger. PDF and SVG are native vector plots. When available, Ghostscript embeds standard Type-1 fonts; otherwise Matplotlib embeds TrueType outlines. SVG retains editable text. Raster previews use the matching sans-serif fallback. Mathematical loss notation is defined in the captions rather than rendered with a non-Type-1 math font in the axes. Figure CSVs are regenerated projections of the preserved compact inputs. No new hardware runs, confidence intervals, or causal measurements are implied.

## split_full_tradeoffs (6.75 × 3.1 in)

Split/Full energy and task-rate ratios for the 195 split cases with current energy measurements, against each of two baseline families (390 dependent pairs; 36 unique Full baselines). YOLOv7 energy is unavailable and is excluded. Each ratio uses means of three per-repeat E/N and N/T values in the corresponding active energy windows. Filled markers have reference-close quality at both endpoints and local semantic evidence; open markers are quality-limited; crosses denote 15 semantic-limited Vendor Full pairs. The green region improves both metrics. Of the strict pairs, 78/138 improve both metrics against Vendor Full and 81/178 against TensorRT Full. Logarithmic axes; no uncertainty intervals are shown. Primary energy is calibrated full-system energy without idle subtraction. Shared baselines create dependence, and TensorRT Full retains the declared historical attestor-source gap. These are descriptive configuration comparisons, not isolated split effects.

Source: `split_full_source.csv`.

## selector_loss (6.75 × 4.4 in)

Native throughput loss L_R = 1 - R_selected/R_best (percent) for six selectors in 21 fixed candidate groups (204 technical candidates). Parentheses give the measured candidate count. YOLOv7 uses final native rates from the supplied campaign report and historical Generic rates; the other six models retain archived measurements. This is descriptive selector transfer across recorded campaigns, not a same-state controlled comparison. Column headings count Top1 selections matching the native winner. Static selections and tie order are frozen; the stored hardware fit retains its H10 profile on all setups. The oracle is the best candidate in the measured row, not a global graph optimum. Throughput uses three-repeat medians; repetition and tie sensitivity are separate from these point estimates.

Source: `selector_loss_source.csv`.

## resnet_energy (3.25 × 2.75 in)

Within-group energy/rate tradeoff for all 19 ResNet-50/H8 split candidates, with the two Full references shown once as contextual markers (diamond: Vendor Full; X: TensorRT Full). Points are means of three own-window N/T and E/N values; bars are observed min/max ranges, not confidence intervals. All plotted endpoints are reference-close. Energy minimum b060 uses 42.286 mJ/task at 615.65 tasks/s; energy-window rate maximum b031 uses 47.715 mJ/task at 626.89 tasks/s. Selecting b060 instead reduces energy by 11.38% and rate by 1.79%, with different denominators for the two changes. Generic completion selects b002; cut-payload selection chooses b119. Primary energy is calibrated full-system energy without idle subtraction. Fulls do not enter the split oracle; TensorRT Full retains the historical attestor-source gap. The paired artifact snapshot supplies local semantic evidence for both Full comparisons.

Source: `resnet_energy_source.csv`.

## generic_stability (6.75 × 2.4 in)

Generic-completion selection loss across 21 groups (204 technical candidates). Symbols use three-repeat median rates. YOLOv7 pairs historical Generic repetitions with final native repetitions from the supplied report; all other groups retain archived repetitions. Vertical ranges span nine dependent Generic/Native repetition combinations, not confidence intervals or nine independent experiments. H8, H10, and DX denote Hailo-8, Hailo-10H, and DeepX. Accuracy-loss cases and the 12 post-planned additions remain in the technical cohort. Near-tied Generic candidates can give a correct median recommendation yet a large observed loss range, as for YOLOv7/DeepX.

Source: `generic_stability_source.csv`.

## Numerical checks

- Split/Full: 390 rows, 195 split identities, 36 Full identities.
- Semantic-limited: 15 pairs, all Vendor Full.
- ResNet/H8: b060 vs b031 energy decrease = 11.376839897%; energy-window rate decrease = 1.792821922%.
- Ratio figures aggregate mean E/N and mean N/T separately; the power/rate identity need not hold exactly for a ratio of arithmetic means.
- Filled Split/Full symbols indicate the stated quality and semantic filters only, not claim eligibility or a passed historical provenance attestation.
- Heatmap L_R is recomputed from the final reported YOLOv7 native rates and archived rates for the other models; it uses a measured-set oracle. Reported values were not independently verified against a raw ZIP.
- Generic stability displays dependent repetition combinations; ranges do not imply inferential coverage.
