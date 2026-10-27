# Split-inference tables

[Result overview](../README.md) · [Figure gallery](../figures/README.md)

CSV is the convenient interchange format; JSON preserves structured fields and exact identities. Energy is J/image unless a column explicitly uses mJ/image, throughput is images/s, duration is s and power is W. Quality values are fractions; percentage-point columns are explicitly named. Existing counts, exclusions and source identifiers are retained.

Table 3 and the baseline supplement share the same absolute fastest observed split per model. The supplement changes only the Full denominator. The separately retained historical Top-2 method ranks relative same-host speedup and can select different splits.

| Table | CSV | JSON | Readable / LaTeX |
|---|---|---|---|
| Recommended Table 3: globally fastest Full versus globally fastest split | [CSV](table3_fastest_deployments.csv) | [JSON](table3_fastest_deployments.json) | [md](table3_fastest_deployments.md) · [tex](table3_fastest_deployments.tex) |
| Same selected fastest split: same-host and global Full baselines | [CSV](fastest_split_baselines.csv) | [JSON](fastest_split_baselines.json) | [md](fastest_split_baselines.md) · [tex](fastest_split_baselines.tex) |
| Fastest Full and separately minimum-energy Full | [CSV](baseline_selection.csv) | [JSON](baseline_selection.json) | — |
| Actual timed-work boundaries and limits | [CSV](boundary_cases.csv) | [JSON](boundary_cases.json) | — |
| Model/setup/runner coverage | [CSV](coverage.csv) | [JSON](coverage.json) | — |
| Every recorded energy repeat | [CSV](energy_repeats.csv) | [JSON](energy_repeats.json) | — |
| Equal model weighting | [CSV](equal_model_summary.csv) | [JSON](equal_model_summary.json) | — |
| All host-specific Full deployments | [CSV](full_configurations.csv) | [JSON](full_configurations.json) | — |
| Fastest and minimum-energy configurations by group | [CSV](model_setup_optima.csv) | [JSON](model_setup_optima.json) | [md](model_setup_optima.md) · [tex](model_setup_optima.tex) |
| Native generic groups | [CSV](native_generic_groups.csv) | [JSON](native_generic_groups.json) | [md](native_generic_groups.md) · [tex](native_generic_groups.tex) |
| Native generic models | [CSV](native_generic_models.csv) | [JSON](native_generic_models.json) | — |
| All Native/Generic pairs | [CSV](native_generic_pairs.csv) | [JSON](native_generic_pairs.json) | — |
| All Native split/Full comparisons | [CSV](native_split_full_pairs.csv) | [JSON](native_split_full_pairs.json) | — |
| Negative quality observations | [CSV](negative_quality.csv) | [JSON](negative_quality.json) | — |
| All points: joint model/setup and separate runner fronts | [CSV](PARETO_POINTS.csv) | [JSON](PARETO_POINTS.json) | — |
| Descriptive two-objective front within recorded work cohorts | [CSV](pareto.csv) | [JSON](pareto.json) | — |
| Recorded pipeline repeat metadata | [CSV](pipeline_repeats.csv) | [JSON](pipeline_repeats.json) | — |
| Quality comparison | [CSV](quality_comparison.csv) | [JSON](quality_comparison.json) | — |
| Repeat counts, ranges, dispersion and energy intervals | [CSV](repeat_uncertainty.csv) | [JSON](repeat_uncertainty.json) | — |
| Quality, original flags and energy-basis sensitivities | [CSV](sensitivity.csv) | [JSON](sensitivity.json) | — |
| Split full groups | [CSV](split_full_groups.csv) | [JSON](split_full_groups.json) | — |
| All split/Full comparisons | [CSV](split_full_pairs.csv) | [JSON](split_full_pairs.json) | — |
| Full model/backend summary (all host values retained) | [CSV](table2_full.csv) | [JSON](table2_full.json) | [md](table2_full.md) · [tex](table2_full.tex) |
| Supplement: Top-2 Native splits by relative same-host speedup (historical selection method) | [CSV](table3_top2_native.csv) | [JSON](table3_top2_native.json) | [md](table3_top2_native.md) · [tex](table3_top2_native.tex) |

The complete [deployment dataset](../data/PAPER_DATASET.csv), [metric sources](../data/METRIC_SOURCES.csv), [measurement generations](../data/MEASUREMENT_GENERATIONS.csv) and [summary](../data/summary.json) use the same broad selection.
