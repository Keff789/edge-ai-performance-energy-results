# PARMA-DITAM

All five empirical v0.15.4 figure subjects and the associated table families are present in the shared energy collection. The retained source exports include the v0.15.1 author package; that source-version label does not mean the later empirical subjects are absent.

| Empirical figure subject | Figure | Tables |
|---|---|---|
| Native scope energy reconstruction | [PDF](../../results/energy-measurement/figures/parma/scope_native_energy.pdf) | [Native reference by duration](../../results/energy-measurement/tables/tim/native_reconstruction.csv) |
| All-15 FP16 energy reconstruction | [PDF](../../results/energy-measurement/figures/tim/fp16_energy_objective.pdf) | [Energy errors and case counts](../../results/energy-measurement/tables/tim/fp16_energy.csv) |
| FP16 variance above Nyquist | [PDF](../../results/energy-measurement/figures/parma/fp16_variance_coverage.pdf) | [Matched-window spectral coverage](../../results/energy-measurement/tables/tim/fp16_coverage.csv) |
| Paired deployed measurement paths | [PDF](../../results/energy-measurement/figures/parma/device_pair_medians.pdf) | [Pair medians](../../results/energy-measurement/tables/measurement-comparison/parma_device_pair_values.csv), [spreads](../../results/energy-measurement/tables/measurement-comparison/parma_device_pair_spread.csv) |
| Duration dependence | [PDF](../../results/energy-measurement/figures/parma/duration_dependence.pdf) | [Duration summaries](../../results/energy-measurement/tables/tim/duration.csv) |

Explore [reconstruction and sampling effects](../../results/energy-measurement/galleries/reconstruction.md), [Jetson spectra](../../results/energy-measurement/galleries/spectra-jetson.md), [measurement comparisons](../../results/energy-measurement/galleries/measurement-comparison.md), [direct-rate and duration sweeps](../../results/energy-measurement/galleries/direct-sweeps.md) and [protocol controls](../../results/energy-measurement/galleries/protocol-controls.md). The [table index](../../results/energy-measurement/tables/README.md) also exposes the coverage/estimator-sensitivity, direct-rate, protocol, calibration and transformation families.

The [historical FP16 gallery](../../results/energy-measurement/galleries/historical-fp16.md) supplies the earlier 13-run spectral and dense rate curves with a tested offline generation command. It remains separate from the current all-15 results. The [window and pause findings](../../results/energy-measurement/data/protocol-controls/window-pause/FINDINGS.md) preserve detailed protocol evidence.

This is coverage of the empirical result groups, not a complete manuscript build or reproduction of external block diagrams. [Available analysis commands](../../scripts/energy-measurement/README.md) state the supported reproduction level. No acceptance status, DOI or published proceedings version is asserted.
