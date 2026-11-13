# Methods and interpretation limits

## Cohort and timing

Four known recipes cover ResNet50/DeepX (b045, b002) and RegNetX-1.6GF/Hailo-10H (b059, b123). Three blocks per recipe each contain an isolated producer P, isolated consumer C and joint pipeline PC: 36 performance processes and twelve paired prediction/observation comparisons. The original experiment also recorded four independent serial references and twelve smokes. Those acquisitions are historical evidence; this compact export does not repeat or fully revalidate them.

Each performance process used batch 1, 100 fully drained warmups and 10,000 measured completions. The primary rate is exactly `8000 / (t9000 − t1000)` in seconds, using **1-based observed completion order**, not sorted request IDs. Total FPS retain fill/drain. The fixed halves t1000–t5000 and t5000–t9000 remain available; a relative rate change above 5% flags drift. No faster interval is selected retrospectively. Physical processes are the repeats; completion intervals are not independent replicates for significance tests.

P counts usable boundary tensors; C and PC count completed classifications. An effective stage interval `c = 1000/F` in ms is not a request latency. Within each case/block, the evaluator writes the prediction `min(F_P, F_C)` (equivalently `max(c_P, c_C)`) before reading its PC report. Neither Full-proportional scaling nor PC-derived stage costs enter the prediction. Signed error is `100 × (F_Oracle/F_PC − 1)`; cycle residual is `1000/F_PC − max(c_P,c_C)`. Errors are calculated per block and then summarized. A ratio of median FPS columns generally does not equal the reported median error.

## Included stage work and operating conditions

| Mode | Work included in the measured interval | Completion |
|---|---|---|
| P, DeepX | Prepared input, synchronous runtime execution, mapping/extraction and an owned boundary-tensor copy; inflight limit 1 | Usable host boundary tensor |
| P, Hailo-10H | Prepared UINT8 input, existing slot policy, InferModel submit/callback/poll with limit 8, serial extraction/materialization | Usable host boundary tensor |
| C | Genuine saved handoff; per-request CPU staging into pinned memory, H2D, existing TensorRT engine, D2H/synchronization and classification completion | Host output and ordered Top1/Top5 ready |
| PC | The same producer/consumer functions with FIFO depth 3 and batch 1 | The same task completion as C |

P uses a bounded sink that releases payloads/slots; its host work is not pure device time. C rotates four preloaded owned handoff buffers, whereas PC receives fresh producer payloads. The same serial consumer worker, TensorRT context/stream and pinned input buffer perform the per-request work. No necessary consumer copy or transfer is moved outside timing. Where supported, both runtimes remain resident; the inactive runtime receives no inference requests.

DeepX hands off FLOAT/NCHW. Hailo-10H hands off UINT8/NHWC; the existing suffix engine includes layout/dequantization (b059 scale 0.5378087759017944, zero point 93; b123 scale 0.6206522583961487, zero point 112). The host does not first convert that payload to FLOAT.

Recorded settings are MAXN_SUPER, CPU min=max 1.984 GHz and GPU min=max 1.173 GHz. PLAN retains the predefined rest/temperature rules and resource contracts; each report retains state comparability, temperatures, affinity and selected observed CPU/GPU/EMC clock fields. Unavailable EMC readings remain null. These readings do not establish unobserved device occupancy or all throttling causes. Setup, loading, file access, hashing, reference comparison, dumps and export are outside timing; mapping, staging and task completion remain inside.

## Validity and reproduction boundary

Each recipe repeats one saved prepared input. Current reference PASS and pre/post checks do not replace historical quality flags or establish dataset accuracy, arbitrary input/output assignment, or 360,000 distinct images. Integer handoffs use exact comparison; FLOAT uses the prechosen rtol=1e-4 and atol=1e-5; ordered Top1/Top5 must match. Original historical unknown/failed fields remain unchanged.

Shared CPU, memory, DMA, GPU/EMC and thermal/power resources, plus replay/cache/allocation differences, limit causal decomposition. The positive residual is not isolated PCIe, transfer or scheduler time. All twelve Oracle values are optimistic, and the practical 10% band is not a guaranteed accuracy bound. Four known cuts on two combinations do not demonstrate transfer to other architectures, cheap stage prediction, a fitted ranker, measurement savings or energy benefits. This is a bounded test of stage composition, not a full CNNParted/Timeloop/Accelergy reproduction.

The [offline command](README.md#offline-reproduction) recalculates numerical results from the supplied reports using the two unchanged source modules. Public input copies omit controller journals and machine-specific interpreter/root paths. Selected original clock readings are retained as `operating_clocks`; all other report fields, completion timestamps, request IDs, bindings and validity/history flags are preserved. `external-archive/…` and `external-artifacts/…` are metadata identifiers for unbundled originals, not promised local files. Hashes still describe those original artifacts, not the curated copies. Arrays, models, serial-reference files, hardware snapshots and journals remain outside the compact export, so the full source archive/array checker is not offered as a self-contained public check. The reproduction wrapper then renders both figures as PDF/SVG/PNG from the freshly evaluated block values; `--numeric-only` retains the standard-library numerical/table path.
