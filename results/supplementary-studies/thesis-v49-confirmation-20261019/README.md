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
| CH0 evidence: corrected, partly clarified and remaining points | [CSV](tables/metrology_claims.csv) | [JSON](tables/metrology_claims.json) |
| Applied unit and calibration paths with functions and parameters | [CSV](tables/metrology_conversion_paths.csv) | [JSON](tables/metrology_conversion_paths.json) |

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

## CH0 evidence alignment, 19 October 2026

The [CH0 addendum](inputs/metrology/ch0_joris_alignment.json) corrects the preceding review's overly broad statements about missing unit, channel, calibration and filter evidence. Kevin confirmed CH0 as the operating channel on 19 October 2026; all 70 primary, two supplemental and 42 historical selected acquisition commands agree. This establishes the recorded operating channel. The physical conductor and consumer boundary assigned to CH0 still require the setup-specific evidence described below.

Joris Wachsmuth, *Entwicklung und Validierung eines Messsystems zur energetischen Bewertung eingebetteter KI-Beschleuniger*, Master's thesis, Universität Bielefeld, July 2026, documents the design and original validation. Printed pages 27 and 29–30 specify 12 bits, a 2.048-V input range, a 20-mΩ shunt and amplifier gain 25 V/V. Thus `2.048 / (4096 × 25 × 0.020) = 0.001 A/count`: an unchanged ADC code is nominally numerically equal to current in mA. Code 4095 corresponds to 4.095 A; the full-scale boundary is 4.096 A. Raw-code transmission is compatible with the existing mA convention and is not evidence of a unit error. This design derivation is distinct from identifying the installed firmware and active ADC range on each board.

The applied path already performs the unit conversion and corrections: `q/1000 → I = g × (q/1000 + o) → U = a + b × I → P = c × s × I × U → energy integral → E/N`. The current analyzer uses amperes for `I` and `o`; the historical helper's mA expressions are algebraically equivalent. Collectors retain the uncalibrated payload values for these runs. The historical factor `c` is applied after power calculation, as the thesis describes on printed pages 65–66. The separate September setup factor `s`, although named `current_scale` in some metadata, multiplies power/energy after the current and voltage calculations. The addendum identifies the exact functions, parameter files, coefficients and application order. No extra factor of 0.001, two, or a repeated calibration was added; the published throughput and energy numbers and all seven comparison directions are unchanged.

Printed pages 53–55 document 36 load points from 0 to 3.5 A, ten seconds each, using an EA-EL 9080-60 DT load and Fluke 179 current reference, with uRECS at 2 kS/s and PicoScope at 5 MS/s. The endpoint-based gain/offset fit is followed by a separate verification run. A two-point fit therefore does not mean that only two load points were recorded. This original validation is acknowledged separately from the three later CH0 setup profiles and their retained warnings. It is not a contemporaneous before/after drift check of the October campaign.

The supplied PDF has SHA256 `897428afa66e9674f8e3ef9b2356bba2cf565fda471803bb9a2ed28de8001191`; printed page numbers map to PDF pages by adding six. The [addendum archive reference](METROLOGY_ADDENDUM_REFERENCE.json) records its internal preservation and the follow-up evidence. The complete third-party thesis is not published in this repository. Earlier metrology capsules remain preserved source snapshots; the [current metrology index](inputs/metrology/index.json) identifies the superseding CH0 alignment.

## Measurement-chain limits and the smallest remaining clarification

The documented hardware design and nominal unit conversion are now identified. The exact populated board revision, channel wiring, installed firmware/build and active ADC range are not yet fully bound to each campaign setup. The thesis names ADS7953 on printed page 29 and ADS7952 on page 48; no retained schematic/BOM resolves that specific type inconsistency. A matching firmware source is not proof of installation. Nominal [primary current ranges](inputs/metrology/primary_nominal_current_ranges.json) and [supplement current ranges](inputs/metrology/supplement_nominal_current_ranges.json) remain model observations; physical clipping is neither established nor excluded.

The thesis measured the Jetson-slot current path. Its voltage-model figure on printed page 56 shows a supply around 19 V, so that path must not be described generically as a 5-V rail. Its transfer to the later full-system profiles depends on the actual supply, wiring and included consumers; CH0 and a similar nominal voltage alone do not prove an identical measurement boundary. The separate historical 5-V-rail comparison remains a different source context. Existing calibration coefficients and setup-specific corrections are recorded, while the physical transfer of their reference conditions and the H10 calibration warnings remain explicit.

Printed page 30 identifies approximately 77 kHz as the cutoff of a differential RC filter before the INA225. Its provenance is a documented design value, not the INA225's general component bandwidth or a newly measured whole-chain transfer function. Actual R/C population, complete-path response and sample-clock characterization remain unbound for the campaign boards. The thesis itself notes that the 2-kS/s acquisition does not establish alias-free sampling of this bandwidth.

The documented calibration verification, residuals and component-based error estimates do not supply a complete physical uncertainty budget for this campaign's energy per inference. Reference-instrument bindings, setup transfer, drift, timebase/dynamic contributions and their covariance remain incomplete. Neither the reported small calibration deviations nor illustrative ±5% values are adopted as combined uncertainty. Unknown uncertainty is not zero, and relative ratios across setups are not generally calibration-independent.

[Historical runtime/compiler/firmware versions and precision bindings](inputs/metrology/version_and_precision_bindings.json) and [historical B500 limits](inputs/metrology/historical_b500_provenance.json) are unchanged: original B500 repeats and exact generator/seed bindings remain missing, so stored bounds are not relabeled as observed ranges. The [remaining-evidence list](inputs/metrology/index.json) isolates these unresolved assignments and physical uncertainty contributions. Any later demonstrated conversion correction must produce a new versioned analysis of the preserved raw data. This documentation alignment performs no new hardware acquisition, calibration, firmware update or compilation; C remains zero.

## Provenance, archive and access

The [origin manifest](inputs/origin_provenance.json) binds the compact inputs and their campaign sources. The complete campaign includes raw captures, error/resume evidence, acquisition and analysis code, the separate energy supplements, source manifests and external-dependency references. Compact Git inputs reproduce the published tables; deeper waveform, firmware and historical-environment checks require the external archive and its referenced artifacts.

The source archive is `thesis_v49_hardware_confirmation_energy_supplement_20261019.tar.gz`, 2,857,836,513 bytes, with SHA256:

```text
edbd618ad91ef658a866c73c61defd00389e3ca9218c33ea22d87a6ec3721915
```

Its source campaign commit is `64c1f487645d20a844d66ccdf8f65dcc80b96065`. The [archive and verified backup reference](ARCHIVE_REFERENCE.json) binds the archive, Git bundle, checksum files and closeout receipts. The internal Sprite destination is `diss_results/_supplements/thesis_v49_confirmation_energy_supplement_20261019` under the configured remote home. Complete target readback through the existing SSHFS mount matched the source hashes before the backup directory was published; this was not remote SSH execution.

The multi-gigabyte archive and Git bundle are external backup assets, not ordinary Git files. Sprite is an internal storage destination, not a public raw-data download. The reference records the full internal paths and backup-manifest hash. Referenced model and dataset stores are identified without duplicating them blindly into this repository. Existing [rights and notices](../../../RIGHTS_AND_NOTICES.md) apply.
