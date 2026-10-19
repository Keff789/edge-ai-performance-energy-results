# v49 hardware confirmation and energy supplements

This separate R3 campaign, completed on 18–19 October 2026, repeats fourteen selected Native split/Full configurations from the historical deployment study. It asks whether their observed throughput and conditional energy directions persist in fresh processes. It preserves the existing 450-configuration dataset and the earlier R1/R2 attempts as separate populations.

The completed result has three distinct scopes:

- **Throughput:** 70 accepted primary runs, five per UID, and 35 primary split/Full block pairs.
- **Conditional energy:** 68 primary integrations and two separately identified supplements provide energy coverage for all seventy logical slots. The two original primary energy-null fields remain null.
- **Physical qualification:** C remains zero. Complete measurement-chain qualification and a combined physical energy uncertainty are still unavailable.

Use the [generated tables](tables/), [compact measurement inputs](inputs/measurements.json), [configuration design](inputs/design.json) and [offline reproduction instructions](../../../scripts/supplementary-studies/thesis-v49-confirmation-20261019/README.md). Numerical result tables are generated from these inputs rather than transcribed into this README.

## Generated records

| Record | CSV | JSON |
|---|---|---|
| Primary throughput, actual counts/intervals, host/backend and primary energy/null | [CSV](tables/primary_measurements.csv) | [JSON](tables/primary_measurements.json) |
| Primary per-UID count, mean, median and observed range | [CSV](tables/primary_uid_statistics.csv) | [JSON](tables/primary_uid_statistics.json) |
| Primary throughput block pairs | [CSV](tables/primary_throughput_pairs.csv) | [JSON](tables/primary_throughput_pairs.json) |
| Primary conditional energy acquisitions | [CSV](tables/primary_energy.csv) | [JSON](tables/primary_energy.json) |
| Primary energy pairs | [CSV](tables/primary_energy_pairs.csv) | [JSON](tables/primary_energy_pairs.json) |
| Separate supplements with their own N/t/E and source identity | [CSV](tables/supplement_measurements.csv) | [JSON](tables/supplement_measurements.json) |
| Energy coverage with explicit primary/supplement roles | [CSV](tables/energy_coverage.csv) | [JSON](tables/energy_coverage.json) |
| Energy pairs with session identities | [CSV](tables/energy_pairs.csv) | [JSON](tables/energy_pairs.json) |
| Seven model comparisons and named aggregators | [CSV](tables/model_comparisons.csv) | [JSON](tables/model_comparisons.json) |
| Direct paired quality, all metrics | [CSV](tables/direct_quality_intervals.csv) | [JSON](tables/direct_quality_intervals.json) |
| Direct paired quality, primary metric per model | [CSV](tables/direct_quality_primary.csv) | [JSON](tables/direct_quality_primary.json) |
| Historical energy repeats | [CSV](tables/historical_energy_repeats.csv) | [JSON](tables/historical_energy_repeats.json) |
| Historical throughput repeats | [CSV](tables/historical_performance_repeats.csv) | [JSON](tables/historical_performance_repeats.json) |
| Historical per-UID statistics | [CSV](tables/historical_uid_statistics.csv) | [JSON](tables/historical_uid_statistics.json) |
| Retained attempts and resume history | [CSV](tables/attempt_history.csv) | [JSON](tables/attempt_history.json) |
| Start accounting and population boundaries | [CSV](tables/attempt_accounting.csv) | [JSON](tables/attempt_accounting.json) |

The [coverage summary](tables/coverage.json) records the population checks. The [reproduction manifest](tables/reproduction_manifest.json) binds the compact inputs, reused calculation sources and generated files.

In `primary_measurements`, the inherited `joules_per_completion=null` and `energy_same_interval_verified=false` fields describe the still-open fully physically qualified energy scope C. The conditional same-interval calculation is represented separately by `B_valid`, `conditional_energy_j` and `conditional_energy_j_per_completion`, retaining 68 integrations and the two primary nulls.

## Timing, selection and replication

The fourteen UIDs and their split/Full assignments were fixed before this confirmation. The accepted primary cohort contains five logical blocks with fourteen UID-specific runtime runs per block. Each process uses 30 s of warm-up admission and full drain, followed by 60 s of measurement admission and full drain; the protocol specifies a 60 s cooling pause between scheduled runs. Throughput is its own `N_completed` divided by the actual native measurement makespan, including drain. Model and compiler artifacts are reused; this campaign does not introduce a rebuild or a new configuration search.

Per-UID throughput and primary conditional-energy summaries report sample count, arithmetic mean, median and observed minimum/maximum. Block comparisons retain the individual split/Full ratios. Energy-coverage summaries separately include the supplements, and their direction comparison uses arithmetic means of per-acquisition `E/N`, with each acquisition's own denominator. Historical three-repeat means and medians remain separately named; a change of aggregator is not presented as a measurement change. Observed ranges are not confidence intervals. These are observations for the selected deployments, with no population-wide or isolated hardware-effect claim.

Logical block/run IDs are distinct from physical attempt IDs. Failed starts, source-completion failures, controller interruptions, recovery epochs and later accepted attempts remain in the [attempt history](inputs/attempt_history.json). For the R3 lineage and its energy supplements, the final accounting distinguishes 74 scientific physical starts, including two failed primary attempts and the two energy supplements, from four technical source-validation cycles. Earlier R1/R2 measurements are not pooled into the accepted R3 statistics. Untimed qualification operations also remain separate from scientific throughput and energy acquisitions.

## What the two energy supplements add

The missing primary energy entries belong to `b04_p09`, MobileNetV3-Large Full on the DeepX setup, and `b05_p09`, YOLO11l split b120 on H10. Their new energy acquisitions retain separate execution IDs, sessions, actual completion counts and native intervals. Each conditional `E/N` uses the `N_completed` of that same new acquisition. Neither supplement replaces a primary throughput row or borrows the original primary completion count.

Selection accepts the first acquisition satisfying the fixed A+B gates, within the recorded budget of three physical starts per target. Source END and socket close, complete target-interval sample support, counter checks and the actual runtime admission/drain events remain required. This establishes the retained conditional calculation; it does not resolve ADC calibration or sample-clock uncertainty.

The energy comparisons contain 33 primary pairs and two additional pairs that are explicitly cross-session. Seven primary energy pairs were already cross-session, so nine of the resulting 35 pairs cross sessions. The new MobileNet pair combines the original `b04_p04` split with the new Full acquisition. The new YOLO11l pair combines the new H10 split with the original `b05_p13` DeepX Full acquisition. Original throughput pairs remain unchanged. This is not a wholly new simultaneous five-block energy replication.

## Actual Full references and observed directions

Host setup labels and execution backends are separate fields in the [configuration design](inputs/design.json). The selected YOLO26m Full runs on the H8 host using TensorRT on the GPU; the selected YOLO26s Full runs on the DeepX host using TensorRT on the GPU. Their `native_full_tensorrt` backends are GPU executions. The other five selected Full references use `native_full_deepx` on the DeepX setup. An H8 or DeepX host label alone does not identify which processor executes Full.

All seven observed energy directions are retained relative to the historical means and to the primary conditional-energy means. Under the retained model, split uses less energy per completed inference for RegNet X 1.6GF, YOLO26m and YOLO26s. It uses more for MobileNetV3-Large, ResNet-50, YOLO11l and YOLOv7 relative to the selected Full references here. In particular, this YOLOv7 comparison does not show an energy gain. Comparisons with another Full baseline require their own explicit denominator.

The [generated model comparisons](tables/model_comparisons.json) retain medians, arithmetic means and observed ranges, with [individual measurements](tables/primary_measurements.csv) and [energy pair identities](tables/energy_pairs.json) available separately. They distinguish throughput effects from conditional energy effects and retain results unfavorable to split execution.

## Direct paired quality analysis

The seven direct split-minus-selected-Full model pairs provide fifteen quality metric intervals: Top-1 accuracy for three classifiers, and COCO AP50:95, AP50 and AP75 for each of four detectors. They are an offline analysis of existing predictions, not additional hardware measurements. The retained analysis uses the same 5,000 image IDs within each pair and 1,000 fixed paired image resamples. The compact entry recomputes percentage-point differences and nominal 95% percentiles from the [saved absolute split/Full bootstrap values and frozen plans](inputs/quality/index.json).

These intervals are conditional on the already selected pairs. They have no simultaneous or selection-adjusted coverage interpretation. Their inputs and resample identities remain separate from the fresh throughput processes and from historical software-version claims. Reproducing a compact bootstrap table does not rerun inference or reconstruct every historical evaluator environment.

## Measurement-chain limits and the smallest remaining clarification

The payload unit and ADC scaling have not been bound to the firmware actually installed on the three measurement boards. A [recovered firmware candidate](inputs/metrology/candidate_firmware.json) forwards masked 12-bit SPI values without conversion; its installation is unproven. This neither establishes a unit error nor confirms the nominal mA convention. Reported energies remain conditional on that convention and the retained 19-V supply model. The historical 5-V module measurement and the 19-V system input represent different measurement boundaries.

Physical board/channel identity, shunt, gain, Vref/full-scale, included consumers and the actual supply point remain incompletely bound. Independent voltage/current references before and after load, covering idle and the used operating range, are missing; the [configuration/reference gaps](inputs/metrology/configuration_and_reference_gaps.json) retain their status. Nominal [primary current ranges](inputs/metrology/primary_nominal_current_ranges.json) and [supplement current ranges](inputs/metrology/supplement_nominal_current_ranges.json) are model observations, not physical ADC-range measurements. Clipping is neither established nor excluded. Combined physical uncertainty is unavailable, rather than zero. Relative ratios can retain offset, nonlinear, drift and channel-specific errors; they are not generally calibration-independent.

The 77-kHz statement remains a declared analysis band limit; the complete-path filter or transfer-function evidence and sample-clock characterization needed for a physical bandwidth claim are missing. A component bandwidth specification is not a measurement of the complete chain. [Historical runtime/compiler/firmware versions and precision bindings](inputs/metrology/version_and_precision_bindings.json), including internal NPU precision and some evaluator/helper branches, also remain incomplete. The [historical B500 limits](inputs/metrology/historical_b500_provenance.json) remain stored bounds: the original repeats and exact generator/seed binding are missing, so those limits are not relabeled as observed minimum/maximum values.

The [smallest remaining clarification](inputs/metrology/index.json) is to bind the actual uRECS build and ADC registers to each board revision, schematic and channel; document the upstream supply wiring and consumers; obtain independent idle/load voltage and current references before and after use; and supply the filter and timebase evidence. This release does not start that work or a new benchmark campaign. Any later scaling correction must be a new versioned analysis of the preserved raw data.

## Provenance, archive and access

The [origin manifest](inputs/origin_provenance.json) binds the compact inputs and their campaign sources. The complete campaign includes raw captures, error/resume evidence, acquisition and analysis code, the separate energy supplements, source manifests and external-dependency references. Compact Git inputs reproduce the published tables; deeper waveform, firmware and historical-environment checks require the external archive and its referenced artifacts.

The source archive is `thesis_v49_hardware_confirmation_energy_supplement_20261019.tar.gz`, 2,857,836,513 bytes, with SHA256:

```text
edbd618ad91ef658a866c73c61defd00389e3ca9218c33ea22d87a6ec3721915
```

Its source campaign commit is `64c1f487645d20a844d66ccdf8f65dcc80b96065`. The [archive and verified backup reference](ARCHIVE_REFERENCE.json) binds the archive, Git bundle, checksum files and closeout receipts. The internal Sprite destination is `diss_results/_supplements/thesis_v49_confirmation_energy_supplement_20261019` under the configured remote home. Complete target readback through the existing SSHFS mount matched the source hashes before the backup directory was published; this was not remote SSH execution.

The multi-gigabyte archive and Git bundle are external backup assets, not ordinary Git files. Sprite is an internal storage destination, not a public raw-data download. The reference records the full internal paths and backup-manifest hash. Referenced model and dataset stores are identified without duplicating them blindly into this repository. Existing [rights and notices](../../../RIGHTS_AND_NOTICES.md) apply.
