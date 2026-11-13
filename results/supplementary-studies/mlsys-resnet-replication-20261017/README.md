# Full ResNet scheduling-by-runtime replication

Completed on 17 October 2026. Forty fresh independent processes measure ResNet-50/H10 cuts b002 and b095 with Generic/Native productive schedules and with a global limit of one outstanding task. Five jointly randomized blocks contain all eight cells. All forty were admitted, with no failure, exclusion or replacement. Both Native variants were measured again within these new blocks. The earlier twenty-process Native series and forty-process RegNet series remain separate.

For each variant, r = FPS(b095)/FPS(b002). Values below 1 prefer b002.

| Contrast | Geometric mean | Nominal 95% interval |
|---|---:|---:|
| Generic productive | 0.60571 | [0.60325, 0.60818] |
| Native productive | 2.05975 | [2.02807, 2.09192] |
| Generic, one outstanding task | 0.83587 | [0.82757, 0.84425] |
| Native, one outstanding task | 0.82898 | [0.82404, 0.83395] |
| Generic scheduling contrast | 0.72465 | [0.71831, 0.73105] |
| Native scheduling contrast | 2.48468 | [2.43823, 2.53203] |
| Primary interaction I | 3.42880 | [3.35320, 3.50611] |

Productive Generic prefers b002 while productive Native prefers b095. Under the one-task intervention both prefer b002. Native therefore reverses its cut preference. Generic changes the relative strength while retaining the same preference. This direction is consistent in all five blocks.

The interaction has the same direction as the [separate RegNet result](../mlsys-evidence-mechanism-20261017/README.md). Its different magnitude is descriptive; neither equal effect size nor an inter-study difference was formally tested. The residual one-task preference also differs: RegNet slightly prefers its later cut, whereas ResNet prefers b002.

## Protocol and analysis

The protocol and analyzer were bound before the first new measurement. Randomization seed: 20261017. No outcome-dependent extension was defined. The exact R14 HEFs, TensorRT engines, prepared inputs, precision, profiles, runtime sources and completed-classification endpoints match the prior study. Eight exactly bound functional records, each containing 32 mixed requests with two distinguishable inputs, were reused. Their outputs match their references byte for byte; they do not enter throughput estimates or constitute new dataset-quality measurements.

Each worker has 30 s warm-up followed by full drain, then 60 s admission followed by full drain. FPS equals completed classifications divided by the full measured makespan, including materialization and Top-1/Top-5 completion. Generic productive uses two workers/queue limit 2, Native productive eight async slots/queue limit 3. The intervention holds a global permit until task completion; Native also limits async slots to one. The global one-task property is supported by the bound semaphore/call structure, counters and functional evidence. No direct global high-water measurement is claimed.

Within each block, log(I) = [log(r_N_product) - log(r_N_single)] - [log(r_G_product) - log(r_G_single)]. Geometric means and nominal two-sided 95% t intervals use the five log contrasts and four degrees of freedom. Individual frames are not independent replicates. I is a ratio of ratios, not a per-cut throughput gain. [All seven contrasts](tables/replication_summaries.csv), [35 block values](tables/replication_blocks.csv) and [40 cell summaries](tables/replication_cells.csv) are available at full precision.

## Interpretation limits

The result supports scheduling-dependent runtime interaction for this second known cut pair. ResNet was selected because a reversal was already known, so joint randomization does not turn it into an independently selected architecture or establish prevalence on unknown models or devices. Runtime chains still bundle SDK/backend, copy and layout behavior. The intervention does not isolate any one of these factors, reconstruct historical software, measure new energy efficiency or establish total search-cost savings. No arbitrary-input production-serving guarantee follows from the fixed-input timing protocol and bounded functional tests. The five-block intervals are nominal and not simultaneous across all reported contrasts.

The earlier RegNet extension remains unstarted. The [scheduling evidence archive](evidence/resnet_scheduling_evidence.tar.xz) contains the protocol-bound runtime sources, all forty fresh process reports, their state snapshots, analysis and reused functional evidence. The [member manifest](evidence/resnet_scheduling_evidence.manifest.json) records each original path and hash. The [source manifest](PROVENANCE.json) binds the archive and exported tables; [extraction instructions](../mlsys-public-evidence-20261020/README.md) describe verification. The earlier Native-only series remains separate. External HEFs, engines, benchmark dependencies and the recorded hardware/software environment are still required for new hardware collection. The historical [archive status](ARCHIVE_STATUS.json) is unchanged.

Source task: `mlsys_r14_resnet_full_replication_20261017_sm2`. Source package: `MLSYS_R14_RESNET_FULL_REPLIKATION_20261017_RESULTS.zip`. Existing [rights and notices](../../../RIGHTS_AND_NOTICES.md) apply. No new license is asserted. No figure or plot generator is added or changed.
