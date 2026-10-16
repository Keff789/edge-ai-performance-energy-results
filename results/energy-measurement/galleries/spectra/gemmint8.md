# GEMM INT8: native Jetson spectra

[Back to gallery](../spectra-jetson.md) · [Energy results](../../README.md) · [Methods and limits](../../METHODS.md) · [Table index](../../tables/README.md)

Native 5-MS/s setup comparison with the recorded active and independent idle cohorts. PSD integrals are variance. Each cumulative spectrum is normalized by its own full-band variance; those percentages do not measure absolute energy agreement.

### GEMM INT8: absolute current PSD

Current fluctuation density in absolute units, retaining the available native frequency band.

![GEMM INT8: absolute current PSD](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_absolute_psd.png)

[PNG](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_absolute_psd.png) · [PDF](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_absolute_psd.pdf)

### GEMM INT8: cumulative current variance

Fraction of full-band current variance below each frequency; each setup has its own denominator.

![GEMM INT8: cumulative current variance](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_cumulative.png)

[PNG](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_cumulative.png) · [PDF](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/current_cumulative.pdf)

### GEMM INT8: absolute power PSD

Power fluctuation density after the recorded current-to-power model; this is not an energy spectrum in joules.

![GEMM INT8: absolute power PSD](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_absolute_psd.png)

[PNG](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_absolute_psd.png) · [PDF](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_absolute_psd.pdf)

### GEMM INT8: cumulative power variance

Fraction of full-band power variance below each frequency, normalized separately for each setup.

![GEMM INT8: cumulative power variance](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_cumulative.png)

[PNG](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_cumulative.png) · [PDF](../../figures/spectra/pico_vs_tek_psd/per_workload/gemmint8/power_cumulative.pdf)

