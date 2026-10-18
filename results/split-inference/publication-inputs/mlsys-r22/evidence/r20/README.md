# R20 evidence projections

These files make selected completed-audit records readable without bundling the entire source archive. They do not change the previous audit decisions or add measurements.

Run `python3 analysis/r20_evidence/extract.py --check-only` from the manuscript root. This read-only standard-library check verifies bundled hashes, the generator hash, endpoint agreement, workload coverage, actual DeepX acquisition rates, and CPU-relative quality arithmetic.

For exact source reconstruction, add `--archive /path/to/MLSYS_R14_SM2_ABKLAERUNG_20261017_RESULTS.zip`. The script verifies the archive and three source-member hashes, reconstructs six files in memory, and compares every byte. It never writes files or accesses devices.

- `endpoint_contracts.csv` is the unchanged original 20-row central-configuration export.
- `detector_endpoint_projection.json` retains all 96 runtime comparison contracts, 65 explicit quality comparison objects and 52 explicit performance comparison objects. All available objects agree. An absent duplicated object is not an endpoint failure. The completed audit uses the original artifact/source bindings for the remaining joins.
- The comparison contract describes required result semantics. Its NMS policy does not mean every runtime invokes NMS: an integrated or NMS-free graph can already provide the required output. The retained physical completion contracts preserve that distinction.
- `workload_contract_projection.json` contains selected unchanged facts from all 450 source rows. Explicit preprocessing objects occur for 298 classifier and 87 detector configurations. Missing objects are not filled by inference. Dataset path names do not establish a selection algorithm or random seed. Bridge precision labels do not specify every accelerator operator's arithmetic.
- `deepx_energy_window_projection.json` retains 225 actual command-window manifests for 75 DeepX Native configurations, all at 2,000 samples/s. It does not establish rates for other backends.
- `yolov7_h8_quality_projection.json` retains three configuration-minus-CPU-reference quality summaries. Their intervals must not be presented as direct split-minus-Full paired intervals. Per-image prediction arrays and bootstrap replicate samples are not included here.

`SOURCE_PROVENANCE.json` gives source ZIP/member hashes, per-file hashes and the generator hash. It deliberately does not hash itself, avoiding cyclic hashes. Source-row indices, JSON pointers and original report bindings remain in the projections. Full source files and original runtime reports require the identified archive or its separately retained originals.
