# Independent stage-cost summary

[Full-precision CSV](STAGE_COST_SUMMARY.csv) · [LaTeX table](stage_cost_table.tex)

All rates are medians of matching blocks. Errors are calculated within each block before aggregation; they are not generally the ratio of the displayed FPS medians. P counts usable boundary tensors; C/PC count completed classifications. All primary rates use the fixed core window.

| Case | P / s | C / s | Oracle / s | PC / s | Median absolute error | Maximum absolute error | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepX / ResNet50 / b045 | 230 | 669 | 230 | 225 | 2.24% | 4.38% | 3 |
| DeepX / ResNet50 / b002 | 473 | 520 | 473 | 444 | 5.50% | 8.80% | 3 |
| Hailo-10H / RegNetX-1.6GF / b059 | 1565 | 500 | 500 | 477 | 4.77% | 4.88% | 3 |
| Hailo-10H / RegNetX-1.6GF / b123 | 1577 | 1999 | 1577 | 1518 | 3.85% | 5.90% | 3 |

All twelve errors are positive (optimistic Oracle) and below the predeclared 10% band, which is not a confidence interval. Both within-model cut orderings match in all three blocks. The detailed comparison CSV contains twelve block comparisons plus six pair-ratio rows; those are not eighteen independent observations.

Experiment `stage_cost_composition_20261014`, source revision `20261014T102852Z`. The CSV retains full precision and also reports total pipeline FPS, minimum error, cycle residual and bottleneck.
