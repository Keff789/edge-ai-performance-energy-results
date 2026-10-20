# Quality audit, fixed calibration and scheduling intervention

Completed on 17 October 2026. This study audits the R14 deployment snapshot and reports a separate scheduling intervention. It does not replace the underlying deployment observations or the earlier supplementary cohorts.

## Quality and provenance audit

The audit covers 450 configurations. Numeric relative task-quality loss of at most 5% retains 407: 187 Native splits, 187 matching Generic splits and 33 Full alternatives. The remaining 43 fail that numerical rule. All fourteen configurations in the seven global fastest-Full/fastest-split comparisons remain eligible. The observed global results therefore remain six of seven models faster with a split and three improving both throughput and energy relative to the selected global fastest Full.

Among the 187 quality-eligible Native splits, 102 are faster than their same-host fastest Full, 74 use less energy than that same reference and 62 improve both. These are descriptive deployment comparisons, not an isolated hardware or graph-partitioning effect.

The inherited screening restrictions on 75 DeepX A4 configurations were resolved using their existing row-specific protocol, artifact, completion, quality and energy evidence. This is an audit of existing observations, not 75 new performance measurements. Original flags and numerical quality remain separate. The supplied source report retains seventeen administrative quality-receipt gaps and six path-based attestation mismatches, with exact-artifact evidence explaining their disposition. It does not reconstruct every historical software environment. Cached loss labels disagreed with recomputed numerical loss in 53 rows; the numerical rule controls eligibility.

## Fixed calibration on held-out architectures

Nine classifier model/setup groups contain 151 eligible Native/Generic pairs. One fixed ridge correction predicts log(Native/Generic FPS) from prefix compute fraction and log(1 + boundary bytes), separately per device. An entire architecture is left out in each fold. Standardization uses training rows only; lambda is 1, the intercept is unpenalized and no hyperparameter search is performed. This is retrospective grouped validation over three known architectures, not a blind test of a newly selected model.

Mean throughput loss against each group's best observed Native cut, with equal group weights:

| Selection method | k = 1 | k = 3 | k = 5 |
|---|---:|---:|---:|
| Generic ranking | 32.804% | 23.768% | 20.448% |
| Fixed calibrated Generic | 28.319% | 23.146% | 15.431% |
| Uniform random, exact expectation | 32.290% | 15.406% | 9.104% |
| Increasing boundary bytes | 32.966% | 21.747% | 8.862% |

Calibration improves the aggregate but its benefit is device-dependent. The boundary-bytes rule slightly improves the k = 5 aggregate relative to random expectation, by 0.242 percentage points, while remaining unreliable in particular groups. These results do not show that all simple static rules fail. Detector groups are separate: all twelve contain three eligible cuts, Generic's k = 1 mean loss is 1.782%, and k = 5 is unavailable.

The budget k counts Native test measurements after the ranking and quality evidence are available. Generic acquisition, Native training data, compilation and quality evaluation are additional costs. No total search-cost saving was measured. [Full-precision summaries](tables/calibration_summary.csv), [device summaries](tables/calibration_device_summary.csv), [cost accounting](tables/calibration_costs.csv) and the [frozen calibration specification](methods/calibration_protocol.json) retain these boundaries.

## Scheduling intervention

Forty fresh RegNet X 1.6GF/H10 processes form five jointly randomized blocks, each containing both cuts b052/b123 and all four runtime/schedule variants. Twenty additional ResNet-50/H10 processes form a separate Native-only series. The latter is superseded for the complete factorial comparison by the [separate full ResNet replication](../mlsys-resnet-replication-20261017/README.md), without pooling old and new Native measurements.

For RegNet, r = FPS(b123)/FPS(b052):

| Runtime and schedule | Geometric mean r | Nominal 95% interval |
|---|---:|---:|
| Generic productive | 0.66035 | [0.65593, 0.66480] |
| Native productive | 3.37134 | [3.35554, 3.38721] |
| Generic, one outstanding task | 1.02886 | [1.02278, 1.03498] |
| Native, one outstanding task | 1.02832 | [1.01629, 1.04049] |

The primary interaction, I = (r_N_product/r_N_single)/(r_G_product/r_G_single), is 5.10808 [4.98961, 5.22936]. I is a ratio of cut ratios, not a speedup of an individual cut. Productive schedules prefer different cuts; with one outstanding task, both runtime chains slightly prefer b123.

Each worker has 30 s warm-up and full drain, followed by 60 s admission and full drain. Throughput counts completed classifications divided by the entire measured makespan, including materialization and Top-1/Top-5 completion. Generic productive uses two workers/queue limit 2. Native productive uses eight async slots/queue limit 3. The intervention retains a global permit until task completion; Native also uses one async slot. It changes the schedule within each bound runtime chain. It does not isolate copies, layouts or conversions from the different SDK/backend implementations.

All 60 confirmatory processes completed and were admitted. Eighteen H10 pilot processes and one DeepX input-association worker are separate functional/development evidence. The predefined RegNet extension was not triggered and its forty planned cells were not run. [Cell summaries](tables/mechanism_cells.csv), [block contrasts](tables/mechanism_blocks.csv) and [all supplied contrast summaries](tables/mechanism_summary.csv) distinguish the series and the unrun extension.

Five process blocks, not individual frames, are the replication units. Intervals are nominal two-sided t intervals on log contrasts with four degrees of freedom. They have no simultaneous or guaranteed sequential-coverage interpretation. Known rank reversals motivated case selection. No population prevalence, historical root cause, new energy effect, arbitrary-input serving guarantee or isolated copy-cost mechanism is established. Runtime code is the frozen current chain with exact R14 artifacts, not reconstructed historical code.

## Records and provenance

The original [450-configuration audit](EVIDENCE_AUDIT.csv) and [flag resolutions](FLAG_RESOLUTION.csv) are available unchanged. The [scheduling evidence archive](evidence/regnet_scheduling_evidence.tar.xz) contains the protocol-bound runtime sources, all forty RegNet and twenty earlier Native-only ResNet process reports, their state snapshots and frozen functional evidence. The two process series remain separate in the [member manifest](evidence/regnet_scheduling_evidence.manifest.json). The [source manifest](PROVENANCE.json) binds these files to the original archive. See the [extraction and verification instructions](../mlsys-public-evidence-20261020/README.md). Model binaries, complete benchmark dependencies and original sensor traces remain external; the historical [archive status](ARCHIVE_STATUS.json) is unchanged.

Source task: `mlsys_r14_evidence_mechanism_20261017_sm2`. Source package: `MLSYS_R14_SM2_ABKLAERUNG_20261017_RESULTS.zip`. Existing [rights and notices](../../../RIGHTS_AND_NOTICES.md) apply. No new license is asserted. No existing figure or plot generator is changed by this export.
