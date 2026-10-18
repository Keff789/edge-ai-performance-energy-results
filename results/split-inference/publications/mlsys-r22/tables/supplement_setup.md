# tab:supp-setup

Recorded setup and workload metadata. The YOLOv7 platform observations describe its setup comparison. Other deployments retain their own recorded settings.

| Item | Recorded setting | Evidence scope |
| --- | --- | --- |
| Performance workload | Three repetitions and 1,000 completed tasks per repetition | 204 split and 42 Full configurations. YOLOv7 combines 27 new split and 18 preserved Full repetitions |
| Batch and Generic queues | Batch 1. two workers. queue depth 2. 100 warmups. one exactly prepared feed repeated | Nine targeted pathway records, not all 204 splits |
| Native queues | Queue depth 3. 100 warmups. H10 paths additionally record 8 prefix requests in flight | The same nine targeted pathway records. runtime organization remains case-specific |
| Nominal spatial inputs | ImageNet validation 224×224 and COCO 2017 validation 640×640 | Dataset identities and available preprocessing contracts, described below |
| Orin configuration | NX 16 GB. L4T 36.4.7. matching active MAXN_SUPER definition | YOLOv7 setup comparison |
| Clock and link observations | CPU 1984 MHz. GPU 1173 MHz. no observed OC-counter increments. accelerator PCIe snapshots 8.0 GT/s ×4 | Approximately 1-Hz YOLOv7 load samples and separate link snapshots. EMC unobserved |
| TensorRT Full build | Same model, FP16 option, static FLOAT input/output shapes and workspace setting | YOLOv7 Full comparison. serialized engines and internal tactics need not be identical |
| DC energy boundary | Calibrated full-system input energy. no idle subtraction in the primary comparison | 231 cases / 693 repetitions over six models. calibration detail in the separate historical energy study |
