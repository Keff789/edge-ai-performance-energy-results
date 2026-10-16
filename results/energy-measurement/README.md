# Energy measurement results

These results examine which sampling rates preserve integrated energy, which preserve electrical fluctuations, and how measurement boundaries and execution protocols affect comparisons. Jetson Orin NX and Hailo-10 are the completed primary platforms.

| Question | Gallery | Main numeric results |
|---|---|---|
| Energy reconstruction and rate/duration limits | [Reconstruction](galleries/reconstruction.md) | [Native rates](tables/tim/native_reconstruction.csv), [all-15 FP16](tables/tim/fp16_energy.csv) |
| Acquisition response and fluctuation coverage | [Jetson spectra](galleries/spectra-jetson.md), [Hailo spectra](galleries/spectra-hailo.md) | [Setup comparison](tables/tim/native_spectral_comparison.csv), [Hailo](tables/tim/hailo_spectra.csv) |
| Deployed measurement paths and boundaries | [Measurement comparison](galleries/measurement-comparison.md) | [All paired outcomes](tables/tim/paired_all_durations.csv), [quantiles](tables/tim/paired_summary.csv) |
| Duration, direct rates and repeatability | [Direct sweeps](galleries/direct-sweeps.md) | [Rate summaries](tables/tim/direct_rates.csv), [duration summaries](tables/tim/duration.csv) |
| Window, sequence and pause effects | [Protocol controls](galleries/protocol-controls.md) | [Balanced effects](tables/tim/controlled_effects.csv), [pause timing](tables/tim/pause_timing.csv) |
| Historical 13-run FP16 spectra and dense rate curves | [Historical FP16](galleries/historical-fp16.md) | [Error groups](tables/historical-fp16-20260809/common_trace/common_trace_summary.csv), [coverage](tables/historical-fp16-20260809/psd/variance_capture_summary.csv) |
| Current verification and setup calibration | [Calibration](galleries/calibration.md) | [Verification points](data/tim/validation/calibration/jetson_calibration_verification_rows.csv) |

[Complete table index](tables/README.md) · [Methods and limits](METHODS.md) · [Analysis commands](../../scripts/energy-measurement/README.md) · [Rights](RIGHTS_AND_NOTICES.md)

Native scope reconstruction covers six workloads, 59 physical executions and 118 traces. The long-window FP16 cohort contains all 15 recordings and 960 window/offset cases per tested energy rate. At the 300-s request the meter comparison contains 105 Jetson and 45 Hailo executions, observed as 450 comparator pairs. Hailo spectra contain 15 GEMM and 15 YOLO recordings. The final direct-rate summary contains 12 series, 323 rate groups and 4,842 finite outcomes.

Energy is in joules, power in watts, current in amperes, duration in seconds and sampling rate in samples/s. PSD density is A²/Hz or W²/Hz; its integral is variance, not energy. Empirical quantiles and sample counts remain in the CSVs.

The files include the final TIM v0.3 and PARMA v0.15.1 numerical exports, broader completed PSD and reconstruction evidence, and completed direct-sweep/control views. The direct-view gallery explains the small offline refresh to the final TIM estimators. Earlier GPU observations and adjusted-window diagnostics remain clearly separate from the completed primary results. All five empirical PARMA v0.15.4 figure subjects and their table families are accessible through the [PARMA entry](../../publications/parma-ditam/README.md). No final updated GPU campaign or complete PARMA manuscript reproduction is claimed.

Inputs are shared across publication entry points. Relative symbolic links inside `data/` reuse byte-identical compact inputs; keep symbolic links intact when copying the repository. Gallery and table download links resolve to their actual files. No raw NPY/Parquet acquisition archive is bundled. Redrawing these figures does not repeat acquisition, calibration or raw-waveform analysis.
