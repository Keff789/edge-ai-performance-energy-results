# Energy table index

Every CSV under `tables/` is linked here, together with every distinct CSV under `data/`. The index covers **48 table files and 152 data files**. The data tree has 186 CSV paths; 34 are symlink aliases of those real data files. Download links below point to the real files, with symlink targets resolved relative to the directory containing each link.

Start with the [energy overview](../README.md), [methods and limits](../METHODS.md), or the question-specific galleries below. Energy is in J, mean power in W, current in A, duration in s and sampling rate in S/s unless a column says otherwise. PSD integrals are variance in A² or W², not energy. Empirical fifth/95th percentiles are distribution summaries, not confidence intervals.

Browse by question: [Energy reconstruction](#energy-reconstruction-native-reference-and-all-15-fp16) · [Earlier common reference](#earlier-common-reference-exports-and-workload-inventory) · [Jetson spectra](#jetson-spectra-acquisition-response-idle-and-load) · [FP16 spectra](#fp16-spectral-coverage-and-estimator-sensitivity) · [Historical FP16 curves](#historical-fp16-spectra-and-dense-rate-curves) · [Hailo spectra](#hailo-spectra-matched-prefixes-and-full-records) · [Meter comparisons](#meter-comparisons-paired-energy-power-and-duration) · [Direct sweeps](#direct-rate-sweeps-duration-sweeps-and-supplementary-observations) · [Protocol controls](#protocol-controls-windows-sequence-and-pauses) · [Calibration and provenance](#current-verification-and-transformation-provenance).

The primary completed platforms are Jetson Orin NX and Hailo-10. Native 5-MS/s reconstruction is primary; the via-1-MS/s energy path is a sensitivity branch. The primary all-15 FP16 spectral branch is `matched_4s_4s`; its 1-MS/s spectral representation is a different analysis choice from the energy sensitivity branch. Adjusted and before-adjustment window views, earlier individual GPU observations, and diagnostic controls retain their separate scope. No final updated GPU campaign or complete PARMA v0.15.4 reproduction package is implied.

## Energy reconstruction: native reference and all-15 FP16

[Reconstruction gallery](../galleries/reconstruction.md). The six-workload scope cohort contains 59 physical executions and 118 traces. Its hierarchy is Q95 across cases within a recording, Q95 across recordings, then the maximum across workload/path groups. A persistent minimum must pass at every higher eligible tested rate. Native and via-1-MS/s columns remain side by side; missing/ineligible cells remain missing. FP16 includes IDs 0–14 and 960 window/offset cases per energy rate.

| CSV | Contents and scope |
|---|---|
| [Native energy summary](tim/native_reconstruction.csv) | Fixed 2-kS/s error by duration, plus persistent native 1% and 0.5% minima. |
| [Jetson foundation energy](tim/jetson_foundation_energy.csv) | Companion publication export of the native reconstruction summary. |
| [FP16 energy: all 15 recordings](tim/fp16_energy.csv) | Three tested energy rates; native/via-1-MS/s pooled Q95, maximum error and cohort provenance. |
| [FP16 energy plot values](tim/fp16_energy_plot.csv) | Native Q95, maximum and case counts used in the compact plot. |
| [Scope errors by recording](../data/reconstruction/scopes/scope_per_run.csv) | 19,824 eligible recording/rate/duration rows; includes case counts and both reconstruction paths. |
| [Scope errors by workload and setup](../data/reconstruction/scopes/scope_groups.csv) | 2,016 group summaries with expected/used IDs and cohort completeness. |
| [Full scope error envelope](../data/reconstruction/scopes/scope_envelope.csv) | 168 eligible duration/rate cells; native and via-1-MS/s worst-case Q95. |
| [Fixed 2-kS/s source excerpt](../data/tim/final_reconstruction/scope_fixed_2k_excerpt.csv) | Nine duration rows with source line references. |
| [Persistent minima and first passes](../data/tim/robustness_20261009/scope_persistent_minima.csv) | Native, via-1-MS/s and earlier phase-only minima; distinguishes first pointwise pass from persistent pass. |
| [Selected envelope checks](../data/tim/robustness_20261009/scope_selected_envelope.csv) | Six selected duration/rate cells comparing native and via-1-MS/s Q95. |
| [Native versus earlier envelope](../data/reconstruction/review/scope_envelope_original_comparison.csv) | Differences and decision changes against the earlier phase-only analysis. |
| [FP16 cohort sensitivity](../data/tim/robustness_20261009/fp16_energy_selection.csv) | All-15, earlier selected-cohort and other retained selection rows; use the all-15 table above for the primary result. |

## Earlier common-reference exports and workload inventory

These retained phase-only and anti-alias common-reference outputs support comparison with the finalized native reconstruction above. Their rate/duration thresholds describe their declared reference path and tested grid. Separate-run direct validation also includes execution variability. Read the mode, setup, completeness and interpretation columns before combining rows.

| CSV | Contents and scope |
|---|---|
| [Six-workload inventory](multi-workload/paper_artifacts/tables/table_multi_workload_inventory.csv) | Publication view of workload family, precision, available 5-MS/s pairs and analysis status. |
| [Common-reference 1% rates](multi-workload/paper_artifacts/tables/table_cross_workload_fmin.csv) | Publication rate minima by workload, setup and duration. |
| [Common-reference 2-kS/s durations](multi-workload/paper_artifacts/tables/table_cross_workload_two_k_sufficiency.csv) | Publication minimum tested duration by workload, setup and tolerance. |
| [Common-reference worst-case rates](multi-workload/paper_artifacts/tables/table_cross_workload_worst_case_envelope.csv) | Publication envelope and limiting workloads, with coverage counts. |
| [Direct runs versus reconstruction](multi-workload/paper_artifacts/tables/table_cross_workload_direct_validation.csv) | Publication comparison of separate-run deviations and same-trace Q95. |
| [Detailed workload inventory](../data/tim/validation/multi_workload/workload_inventory.csv) | Configuration status, pair counts, source paths, precision and readiness. |
| [Common-reference grid](../data/tim/validation/multi_workload/common_reference_summary.csv) | Full errors by workload, setup, reconstruction mode, target rate and duration. |
| [Common-reference minima grid](../data/tim/validation/multi_workload/f_min_by_workload_duration.csv) | Persistent tested-rate minima for each workload, setup, mode, duration and tolerance. |
| [Highlighted-rate duration thresholds](../data/tim/validation/multi_workload/highlighted_rate_thresholds.csv) | Shortest passing tested duration that also passes at all longer tested durations. |
| [Common-reference envelope data](../data/tim/validation/multi_workload/worst_case_envelope.csv) | Worst-case minima with contributing workloads and completeness flags. |
| [Reference-cache energy check](../data/tim/validation/multi_workload/cache_energy_qc.csv) | 118 trace-level input/output energy comparisons for the 5-to-1-MS/s cache reduction. |
| [Direct-validation source values](../data/multi-workload/direct_rate_validation/direct_rate_validation.csv) | Separate execution power deviations and matching common-reference errors. |
| [Archived rate-minimum table](../data/tim/validation/multi_workload/table_cross_workload_fmin.csv) | Retained TIM data copy of the publication rate-minimum table. |
| [Archived 2-kS/s duration table](../data/tim/validation/multi_workload/table_cross_workload_two_k_sufficiency.csv) | Retained TIM data copy of the publication duration table. |
| [Publication macro map](../data/multi-workload/paper_artifacts/latex/multi_workload_results_macros_name_map.csv) | Analysis keys, TeX command names and exported values. |

## Jetson spectra: acquisition response, idle and load

[Jetson spectra gallery](../galleries/spectra-jetson.md). Native comparisons use 5 MS/s and independent idle recordings. Keep metrics of the pointwise-median spectrum separate from medians of per-recording metrics. Full-band and independently normalized 0–77-kHz CDFs have different denominators. Observed PicoScope/Tektronix PSD ratios are descriptive setup comparisons, not transfer functions or independent bandwidth validation.

| CSV | Contents and scope |
|---|---|
| [Primary excess-power setup comparison](tim/native_spectral_comparison.csv) | Six-workload full-band and conditional CDF differences, variance ratios and frequency percentiles. |
| [Setup PSD metrics](spectra/pico_vs_tek_psd/tables/table_tek_vs_pico_psd_metrics.csv) | Current/power excess-spectrum metrics, including curve and per-recording statistics. |
| [Setup excess-variance bands](spectra/pico_vs_tek_psd/tables/table_tek_vs_pico_frequency_bands.csv) | Band shares for the excess spectra. |
| [Setup comparison across signals](spectra/pico_vs_tek_psd/tables/table_pico_usability_summary.csv) | Active/excess current and power CDF differences and variance ratios. |
| [Workload ranking stability](spectra/pico_vs_tek_psd/tables/table_workload_ranking_stability.csv) | Small-sample descriptive rank comparisons between setups. |
| [Workload spectral summary](multi-workload/paper_artifacts/tables/table_cross_workload_psd_metrics.csv) | Publication frequency percentiles, nominal-bandwidth share and entropy. |
| [Dominant load peaks](multi-workload/paper_artifacts/tables/table_cross_workload_dominant_peaks.csv) | Publication peak frequencies, relative levels and prominence. |
| [Above-2.5-MHz coverage](multi-workload/paper_artifacts/tables/table_cross_workload_high_rate_coverage.csv) | Publication highest-rate Tektronix checks, with active-only/excess basis retained. |
| [Idle and load summary](multi-workload/paper_artifacts/tables/table_cross_workload_idle_load_summary.csv) | Publication active/idle ratios, overlap and additional variance. |
| [Idle and load by band](multi-workload/paper_artifacts/tables/table_cross_workload_idle_load_bands.csv) | Publication band-level ratios and variance shares. |
| [Load peaks versus idle](multi-workload/paper_artifacts/tables/table_cross_workload_idle_load_peaks.csv) | Publication peak matches and descriptive classifications. |
| [All Jetson spectral metrics](../data/tim/validation/multi_workload/all_spectral_metrics.csv) | 72 active, idle and excess records across workloads, setups and signals. |
| [Full setup-comparison data](../data/tim/validation/multi_workload/setup_comparison.csv) | Source comparison rows for active/excess current and power. |
| [All spectral band metrics](../data/spectra/pico_vs_tek_psd/data/frequency_band_metrics.csv) | 432 band rows spanning active, idle and excess curves. |
| [Observed PSD ratios by log-frequency bin](../data/spectra/pico_vs_tek_psd/data/observed_psd_ratio_log_bins.csv) | Integrated band ratios with reporting/gating status. |
| [Ranking source data](../data/spectra/pico_vs_tek_psd/data/rankings.csv) | Rank correlations and explicit workload orders. |
| [High-rate coverage source data](../data/multi-workload/psd/high_rate_coverage.csv) | Highest Tektronix acquisition rates and variance above the PicoScope Nyquist frequency. |
| [Full idle/load summary](../data/multi-workload/psd/idle_load_summary.csv) | Setup and signal details for independent idle comparisons. |
| [Full idle/load band data](../data/multi-workload/psd/idle_load_frequency_bands.csv) | Active/idle integrals, overlap and additional variance by band. |
| [Idle/load ratios by log-frequency bin](../data/multi-workload/psd/idle_load_log_frequency_ratio.csv) | Integrated ratios; active and idle are independent records. |
| [Full idle/load peak classifications](../data/multi-workload/psd/idle_load_peak_classification.csv) | Peak proximity, local ratios and descriptive classifications. |
| [Independent idle recordings](../data/multi-workload/psd/external_idle/5000000Sps/idle_per_run.csv) | 11 ten-second paired idle recordings, sample counts and Welch settings. |
| [Archived idle/load publication table](../data/tim/validation/multi_workload/table_cross_workload_idle_load_summary.csv) | Retained TIM data copy of the compact six-workload idle/load summary. |

### Per-workload spectral detail

Each row links the four retained detail CSVs for that workload. These contain both setup and signal columns where applicable.

| Workload | Peaks | Spectral bands | Idle/load bands | Idle/load peak matches |
|---|---|---|---|---|
| GEMM FP32 | [Peaks](../data/multi-workload/psd/per_workload/gemmfp32/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/gemmfp32/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/gemmfp32/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/gemmfp32/idle_load_peak_classification.csv) |
| GEMM INT8 | [Peaks](../data/multi-workload/psd/per_workload/gemmint8/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/gemmint8/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/gemmint8/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/gemmint8/idle_load_peak_classification.csv) |
| YOLO FP32 | [Peaks](../data/multi-workload/psd/per_workload/yolofp32/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/yolofp32/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/yolofp32/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/yolofp32/idle_load_peak_classification.csv) |
| YOLO INT8 | [Peaks](../data/multi-workload/psd/per_workload/yoloint8/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/yoloint8/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/yoloint8/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/yoloint8/idle_load_peak_classification.csv) |
| Gemma3-4B | [Peaks](../data/multi-workload/psd/per_workload/gemma3-4b/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/gemma3-4b/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/gemma3-4b/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/gemma3-4b/idle_load_peak_classification.csv) |
| ResNet-50 FP32 | [Peaks](../data/multi-workload/psd/per_workload/resnet50/dominant_peaks.csv) | [Bands](../data/multi-workload/psd/per_workload/resnet50/frequency_bands.csv) | [Idle/load bands](../data/multi-workload/psd/per_workload/resnet50/idle_load_frequency_bands.csv) | [Peak matches](../data/multi-workload/psd/per_workload/resnet50/idle_load_peak_classification.csv) |

### Sampled Jetson PSD curves

These CSVs are plotting curves; exact reported spectral metrics were calculated from full-resolution arrays. All use the retained `existing_full_record` window. Idle files are shared across workload aliases and are linked once below.

| Workload | Setup | Signal | Active curve | Positive-excess curve |
|---|---|---|---|---|
| GEMM FP32 | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__tek__current__excess__existing_full_record.csv) |
| GEMM FP32 | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__tek__power__excess__existing_full_record.csv) |
| GEMM FP32 | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__pico__current__excess__existing_full_record.csv) |
| GEMM FP32 | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmfp32__pico__power__excess__existing_full_record.csv) |
| GEMM INT8 | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__tek__current__excess__existing_full_record.csv) |
| GEMM INT8 | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__tek__power__excess__existing_full_record.csv) |
| GEMM INT8 | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__pico__current__excess__existing_full_record.csv) |
| GEMM INT8 | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemmint8__pico__power__excess__existing_full_record.csv) |
| YOLO FP32 | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__tek__current__excess__existing_full_record.csv) |
| YOLO FP32 | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__tek__power__excess__existing_full_record.csv) |
| YOLO FP32 | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__pico__current__excess__existing_full_record.csv) |
| YOLO FP32 | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yolofp32__pico__power__excess__existing_full_record.csv) |
| YOLO INT8 | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__tek__current__excess__existing_full_record.csv) |
| YOLO INT8 | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__tek__power__excess__existing_full_record.csv) |
| YOLO INT8 | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__pico__current__excess__existing_full_record.csv) |
| YOLO INT8 | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__yoloint8__pico__power__excess__existing_full_record.csv) |
| Gemma3-4B | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__current__excess__existing_full_record.csv) |
| Gemma3-4B | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__power__excess__existing_full_record.csv) |
| Gemma3-4B | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__current__excess__existing_full_record.csv) |
| Gemma3-4B | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__power__excess__existing_full_record.csv) |
| ResNet-50 FP32 | Tektronix | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__tek__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__tek__current__excess__existing_full_record.csv) |
| ResNet-50 FP32 | Tektronix | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__tek__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__tek__power__excess__existing_full_record.csv) |
| ResNet-50 FP32 | PicoScope | Current | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__pico__current__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__pico__current__excess__existing_full_record.csv) |
| ResNet-50 FP32 | PicoScope | Power | [Active](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__pico__power__active__existing_full_record.csv) | [Excess](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__resnet50__pico__power__excess__existing_full_record.csv) |

| CSV | Contents and scope |
|---|---|
| [Shared Tektronix idle current](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__current__idle__existing_full_record.csv) | Independent idle plotting curve reused by the six workloads; the canonical filename contains Gemma3-4B. |
| [Shared Tektronix idle power](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__tek__power__idle__existing_full_record.csv) | Independent idle plotting curve reused by the six workloads; the canonical filename contains Gemma3-4B. |
| [Shared PicoScope idle current](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__current__idle__existing_full_record.csv) | Independent idle plotting curve reused by the six workloads; the canonical filename contains Gemma3-4B. |
| [Shared PicoScope idle power](../data/spectra/pico_vs_tek_psd/data/curves/Jetson_Orin_NX__gemma3-4b__pico__power__idle__existing_full_record.csv) | Independent idle plotting curve reused by the six workloads; the canonical filename contains Gemma3-4B. |

## FP16 spectral coverage and estimator sensitivity

The primary branch is `matched_4s_4s`: matched four-second active/idle segments and per-recording positive-excess integration before across-recording quantiles. The other branches remain estimator/window sensitivity checks. Spectral coverage and integrated-energy preservation answer different questions.

| CSV | Contents and scope |
|---|---|
| [FP16 primary spectral coverage](tim/fp16_coverage.csv) | All-15 median and fifth/95th percentiles at 2, 125 and 160 kS/s. |
| [FP16 spectral plot values](tim/fp16_coverage_plot.csv) | Retained plot export of the primary coverage summary. |
| [FP16 spectra by recording and branch](../data/reconstruction/fp16/fp16_psd_per_run.csv) | 90 rows covering the primary branch and retained alternatives; signed/positive/negative excess and frequency thresholds. |

## Hailo spectra: matched prefixes and full records

[Hailo spectra gallery](../galleries/spectra-hailo.md). The primary matched-prefix selection uses 15 GEMM and 15 YOLO recordings with ten-second active prefixes and same-record idle. Full-record curves are supplemental window comparisons. Historical precision and boundary metadata remain as recorded in these CSVs; these are not model-matched cross-platform benchmarks.

| CSV | Contents and scope |
|---|---|
| [Hailo primary matched-prefix metrics](tim/hailo_spectra.csv) | Active and excess power metrics, four selected workload/basis rows. |
| [Hailo full spectral table](spectra/cross_platform_psd/tables/table_hailo_power_psd_metrics.csv) | Matched-prefix and full-record active, idle and excess metrics. |
| [Hailo spectral window inventory](spectra/cross_platform_psd/tables/table_cross_platform_inventory.csv) | Cohort counts, durations and retained metadata/status limitations. |
| [Hailo selected percentile values](../data/tim/git/hailo_psd_selected_rows.csv) | Per-recording f95/f99 summaries and empirical quantiles for the primary selection. |
| [Hailo spectral source metrics](../data/tim/git/platform_spectral_metrics.csv) | Full retained 12-row source export for both window choices. |

### Sampled Hailo power PSD curves

These are plotting curves. The matched-prefix idle aliases resolve to the full-record idle file for the corresponding workload.

| Workload | Window | Active curve | Positive-excess curve | Idle curve |
|---|---|---|---|---|
| GEMM | Matched ten-second prefix | [Active](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__active__matched_prefix.csv) | [Excess](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__excess__matched_prefix.csv) | [Idle](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__idle__full_record.csv) |
| GEMM | Full record (supplemental) | [Active](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__active__full_record.csv) | [Excess](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__excess__full_record.csv) | [Idle](../data/spectra/cross_platform_psd/data/curves/Hailo-10__gemm__pico__power__idle__full_record.csv) |
| YOLO | Matched ten-second prefix | [Active](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__active__matched_prefix.csv) | [Excess](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__excess__matched_prefix.csv) | [Idle](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__idle__full_record.csv) |
| YOLO | Full record (supplemental) | [Active](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__active__full_record.csv) | [Excess](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__excess__full_record.csv) | [Idle](../data/spectra/cross_platform_psd/data/curves/Hailo-10__yolo__pico__power__idle__full_record.csv) |

## Meter comparisons: paired energy, power and duration

[Measurement comparison gallery](../galleries/measurement-comparison.md). These describe deployed measurement paths and electrical boundaries. Signed differences are 100 × (sensor/PicoScope − 1), calculated per matched execution. The 300-s request has 105 Jetson and 45 Hailo executions, observed as 450 comparator pairs; three comparators do not create three independent executions. Before-adjustment and adjusted variable-YOLO views must remain separate; the finalized main selection follows the retained window policy.

| CSV | Contents and scope |
|---|---|
| [All paired outcomes](tim/paired_all_durations.csv) | 4,416 comparator pairs across ten duration requests; energy, power and actual retained spans. |
| [All-duration paired summaries](tim/paired_summary.csv) | 300 cells with paired medians and fifth/95th percentiles. |
| [300-s paired summaries](tim/paired_300s.csv) | 30 workload/comparator cells for both completed platforms. |
| [Jetson 300-s paired summaries](tim/jetson_paired_300s.csv) | 21-cell Jetson subset. |
| [Hailo variable-YOLO interval comparison](tim/hailo_variable_interval_comparison.csv) | Ten duration requests using the explicit legacy interval; separates energy, power and span differences. |
| [PARMA paired power medians](measurement-comparison/device_pair_medians.csv) | Compact Jetson comparison values with plot order. |
| [PARMA individual paired power values](measurement-comparison/parma_device_pair_values.csv) | 315 comparator pairs with execution IDs. |
| [PARMA paired power spread](measurement-comparison/parma_device_pair_spread.csv) | 21-cell Jetson summaries; paired percentiles and ratio-of-medians retained separately. |
| [Both-platform paired power spread](measurement-comparison/all_platform_device_pair_spread.csv) | 30-cell companion comparison; paired and ratio-of-medians columns remain distinct. |

## Direct rate sweeps, duration sweeps and supplementary observations

[Direct sweeps gallery](../galleries/direct-sweeps.md). The finalized main rate summary has 12 Jetson/Hailo series, 323 rate groups and 4,842 finite outcomes. Direct sweeps are separate executions and combine acquisition, order, duration and run variability. Final rate CV uses population standard deviation; displacement is relative to the unweighted mean of rate-group means. Duration deviations use the workload’s fixed 600-s median power.

The broader candidate, pair and reference files also contain earlier individual GPU observations, diagnostics, legacy/before-adjustment windows and the adjusted Jetson variable-YOLO series. Preserve `series`, `window`, inclusion and quality flags when selecting those supplements. A series path containing `historical` can still supply a finalized Jetson/Hailo result; the final selection is identified by the summary and policy, not by that path word alone. Supplemental fixed-2-kS/s agreement limits describe the observed grid, not measurement accuracy or a universal minimum rate.

| CSV | Contents and scope |
|---|---|
| [Final direct-rate summaries](tim/direct_rates.csv) | 12 primary series with rate counts, finite outcomes, maximum CV and group displacement. |
| [Final duration summaries](tim/duration.csv) | 100 workload/duration rows for Jetson and Hailo. |
| [Jetson duration summaries](tim/jetson_duration.csv) | 70-row Jetson subset. |
| [Supplemental fixed-reference comparisons](direct-sweeps/reference_comparisons.csv) | 2,457 rows with declared reference settings, repeatability and run-level agreement summaries. |
| [Observed-grid agreement limits](direct-sweeps/observed_agreement_limits.csv) | 378 criteria/settings rows, including missing/not-met status and explanatory flags. |
| [All retained device pairs](direct-sweeps/device_pairs.csv) | 14,855 broad candidate pairs; includes supplementary series and window choices. |
| [Unavailable-window register](direct-sweeps/unavailable_windows.csv) | 15 missing-window records and reasons; unavailable outcomes are not zeros. |
| [Final window policy](../data/tim/final_direct/paper_window_policy.csv) | Detected envelope selection and explicit exceptions; adjusted series identified separately. |
| [Individual candidate outcomes](../data/tim/final_direct/plotted_candidates.csv) | 35,791 retained outcomes with IDs, windows, inclusion flags and source hashes. |
| [Candidate distribution summaries](../data/tim/final_direct/groups_all_candidates.csv) | 2,698 groups with means, medians, quantiles, ranges and quality counts. |
| [Candidate pair summaries](../data/tim/final_direct/device_groups_all_pairs.csv) | 1,048 groups retaining paired summaries, ratio-of-medians and flags. |

## Protocol controls: windows, sequence and pauses

The retained [window and pause findings](../data/protocol-controls/window-pause/FINDINGS.md) explain the window comparisons, schedule changes and limits of the pause diagnostic.

[Protocol controls gallery](../galleries/protocol-controls.md). The complementary FP16 control has two six-run sessions (ABBAAB/BAABBA), 250 queries per run and 120-s process gaps. Its fixed additive design has four residual degrees of freedom; its t interval is not an equivalence test. The fixed-window study retains all 225 executions. The FP32 pause diagnostic excludes one conditioner and scores six 100-query runs, three per pause condition. Waiting energy is excluded; this is a diagnostic rather than a randomized causal trial, and unchanged logged GPU/CPU frequency is counterevidence against claiming observed clock throttling.

| CSV | Contents and scope |
|---|---|
| [Selected balanced effects](tim/controlled_effects.csv) | External DC power, telemetry and runtime rate effects with t intervals. |
| [Scored pause timing](tim/pause_timing.csv) | Six scored runs with actual waits, runtime and pre-run GPU temperature. |
| [Pause condition summary](tim/pause_summary.csv) | Three runs per pause condition; median runtime and starting GPU temperature. |
| [Complementary-control executions](../data/tim/validation/controlled/complementary/data/combined_runs.csv) | All 12 runs with session, sequence, external measurements and telemetry. |
| [All balanced effects](../data/tim/validation/controlled/complementary/data/balanced_effects.csv) | 14 metrics with estimates, standard errors, intervals and residual degrees of freedom. |
| [Sequence-position balance](../data/tim/validation/controlled/complementary/data/position_balance.csv) | The complementary sampling-rate allocation at each of six positions. |
| [Position-matched contrasts](../data/tim/validation/controlled/complementary/data/position_contrasts.csv) | Metric differences between the two sessions at each sequence position. |
| [Within-session sequence slopes](../data/tim/validation/controlled/complementary/data/sequence_slopes.csv) | Descriptive changes across sequence positions. |
| [Session/rate summaries](../data/tim/validation/controlled/complementary/data/session_rate_summaries.csv) | Retained per-session differences before the combined balanced model. |
| [Fixed-window workload summary](../data/tim/validation/controlled/fixed-window/data/main_summary.csv) | Five workloads, three rates and 15 repeats per workload/rate. |
| [Fixed subwindow comparison](../data/tim/validation/controlled/fixed-window/data/subwindows.csv) | 20–80-s and shorter subwindow sensitivity. |
| [Pre-load baseline decomposition](../data/tim/validation/controlled/fixed-window/data/preload_decomposition.csv) | Exploratory arithmetic decomposition; not causal attribution or calibration. |
| [First-recording observations](../data/tim/validation/controlled/fixed-window/data/run0_observation.csv) | Run-0 comparisons; file order does not establish exact inter-benchmark pauses. |
| [Legacy versus envelope duration examples](../data/protocol-controls/window-comparison/duration_examples.csv) | Five duration examples with energy, retained span and per-run power summaries. |
| [Legacy versus envelope sweep endpoints](../data/protocol-controls/window-comparison/sweep_endpoints.csv) | Nine series comparing 2-kS/s and 5-MS/s endpoints under both windows. |
| [Fixed-query diagnostic executions](../data/protocol-controls/window-pause/iteration_runs.csv) | 45 executions with order, runtime, windows, process gaps and warnings. |
| [Fixed-query window sensitivity](../data/protocol-controls/window-pause/window_runs.csv) | 45 executions comparing legacy and unforced windows. |
| [Timeout-protocol rate summaries](../data/protocol-controls/window-pause/timeout_rates.csv) | 27 tested rate groups and relative energy against 2 kS/s. |
| [All pause-diagnostic executions](../data/tim/pause/pause_runs.csv) | Seven rows including the excluded conditioner; energy, timing and temperature fields. |
| [Pause latency by groups of ten queries](../data/protocol-controls/window-pause/pause_latency_groups.csv) | Within-run latency groups, with conditioner identified. |
| [Pause-window threshold sensitivity](../data/protocol-controls/window-pause/pause_window_sensitivity.csv) | Three envelope thresholds comparing the two pause conditions. |

## Historical FP16 spectra and dense rate curves

[Historical gallery and tested command](../galleries/historical-fp16.md). This earlier snapshot retains 13 reference recordings (IDs 2–14), ten-second active/four-second idle spectral windows and a 1-MS/s representation. The current all-15 matched-four-second main results remain separate. Error/coverage summaries are re-aggregated; the frequency-resolved PSD input is explicitly already aggregated. Units and the exact original-bin selection are documented in the [input definitions](../data/historical-fp16-20260809/README.md).

| CSV | Contents and scope |
|---|---|
| [Historical common-trace summary](historical-fp16-20260809/common_trace/common_trace_summary.csv) | 49 mode/rate groups, signed and absolute energy errors; [readable table](historical-fp16-20260809/common_trace/common_trace_summary.md). |
| [Historical independent acquisitions](historical-fp16-20260809/real_measurements/real_measurements_summary.csv) | 27 rate groups, fixed 5-MS/s median reference; [readable table](historical-fp16-20260809/real_measurements/real_measurements_summary.md). |
| [Historical variance coverage](historical-fp16-20260809/psd/variance_capture_summary.csv) | 27 tested rates and empirical across-run quantiles; [readable table](historical-fp16-20260809/psd/variance_capture_summary.md). |
| [Historical PSD plotting curves](historical-fp16-20260809/psd/psd_plot_samples.csv) | 38,088 exact selected frequency bins with power PSD and cumulative fractions. |
| [Historical common-trace cases](../data/historical-fp16-20260809/common_trace_raw.csv) | 16,159 retained run/phase energy outcomes feeding the current re-aggregation. |
| [Historical independent acquisition outcomes](../data/historical-fp16-20260809/real_measurements_raw.csv) | 351 completed energy outcomes, 13 at each of 27 rates. |
| [Historical per-run variance capture](../data/historical-fp16-20260809/variance_capture_per_run.csv) | 351 full-grid spectral integrals; source of the re-aggregated rate curve. |

## Current verification and transformation provenance

[Calibration gallery](../galleries/calibration.md). Current verification uses an electronic load, a Fluke reference, endpoint calibration and ten-second means; relative-error summaries exclude the zero-target setting. The provenance files retain reported transformations and evidence gaps, including the workload-only YOLO-FP32 Tektronix current offset. Corrected absolute agreement is not independent validation. The separate three-system calibration records described in the gallery do not retroactively recalibrate these campaigns.

| CSV | Contents and scope |
|---|---|
| [Jetson current-verification points](../data/tim/validation/calibration/jetson_calibration_verification_rows.csv) | 72 rows across two measurement sheets, with actual/adjusted currents, formulas and zero-target flags. |
| [Transformation register](../data/tim/provenance/transformations/transformationtable.csv) | Reported scaling/offset operations, parameters, source evidence and allowed claims. |
| [Archived workbook formulas](../data/tim/provenance/transformations/archived_ODS_formula_cells.csv) | 75 formula cells with cached values and sheet/row locations. |
| [Collected source inventory](../data/tim/provenance/transformations/collector_selected_sources.csv) | Source identities, hash scope, read scope and stability metadata. |
| [Transformation evidence candidates](../data/tim/provenance/transformations/collector_selected_transformation_candidates.csv) | Retained text/location evidence requiring interpretation. |
| [Binding and version candidates](../data/tim/provenance/transformations/collector_selected_binding_and_versions.csv) | Recorded configuration/version references and their evidence classifications. |
| [Recorded hash references](../data/tim/provenance/transformations/collector_selected_recorded_hash_references.csv) | References retained as recorded; these do not establish a historical model binding. |
| [Collection coverage limitations](../data/tim/provenance/transformations/collector_coverage_limitations.csv) | Missing paths and bounded evidence coverage. |

