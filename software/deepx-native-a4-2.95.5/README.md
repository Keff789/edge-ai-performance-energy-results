# DeepX Native A4: selected 2.95.5 source evidence

These unchanged files are selected from the final verified **2.95.5** source snapshot, completed on 16 October 2026 at 10:24 UTC. They document the execution and reporting paths used for the current main dataset’s 68 DeepX Native splits and seven DeepX Native Full replacements. The existing [2.94.0 full source archive](../README.md#onnx-splitpoint-tool) remains available for historical results.

## Execution and reporting

| Source | Scope |
|---|---|
| [native_deepx_async.py](onnx_splitpoint_tool/native_deepx_async.py) | Shared asynchronous DeepX jobs, owned input/output lifetimes, ordered waits and drain |
| [native_three_stage.py](onnx_splitpoint_tool/native_three_stage.py) | Existing bounded stage/FIFO execution |
| [DeepX split runner](onnx_splitpoint_tool/resources/remote_scripts/native_deepx_trt_e2e_from_benchmarkset.py) | A4 producer, FIFO3 and serial TensorRT consumer including task completion |
| [Full performance runner](onnx_splitpoint_tool/resources/remote_scripts/native_full_baseline_eval_runner.py) | Native Full execution and completion |
| [DeepX Full energy hot loop](onnx_splitpoint_tool/resources/remote_scripts/native_deepx_full_energy_hotloop.py) | Native Full A4 command-window execution |
| [Performance identity](onnx_splitpoint_tool/native_performance_identity.py) and [reporting](onnx_splitpoint_tool/native_performance_reporting.py) | Runtime-bound process counts, durations and throughput observations |
| [Energy quality admission](onnx_splitpoint_tool/native_energy_quality_admission.py) and [energy reporting](onnx_splitpoint_tool/native_energy_reporting.py) | Recorded admission, calibrated energy observations and repeat aggregation |
| [Native refresh workflow](onnx_splitpoint_tool/workflow/native_refresh.py) | Exact 75-identity campaign selection and accepted reuse |

A4 uses batch 1, one DeepX engine per measurement process and at most four outstanding asynchronous jobs. Native splits retain FIFO depth 3 and a serial TensorRT/task consumer. Generic and Hailo observations retain their original execution policies. The mode does not imply equal timed work, request latency, new dataset-quality evaluation or a controlled scheduling-only comparison.

The frozen continuation manifests record identical hashes for `native_deepx_async.py`, `native_three_stage.py`, the three remote execution modules listed above and `native_performance_reporting.py` throughout the continuation. Reporting and campaign-admission fixes were delivered during that continuation. The files here are the **final** reporting/workflow versions; they do not imply that every controller module was identical at every earlier start. All selected performance and energy records retain their actual runtime/source provenance in the [main dataset](../../results/split-inference/data/README.md).

## Source identity and reuse boundary

The unchanged [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) and [SHA256SUMS.txt](SHA256SUMS.txt) are the source snapshot’s existing ordinary manifest files. The manifest records package/workflow version 2.95.5 and 2,283 release files. Its recorded SHA-256 is `03bd8ee20d05bf353a8da022308372cce8fe615c744b001c8f0db122de706bd7`. Original [package metadata](pyproject.toml) and [version entry point](onnx_splitpoint_tool/__init__.py) accompany the selection.

This directory is a selected source excerpt. The manifests describe the complete external frozen source snapshot; most listed files are intentionally absent here, so a complete-tree source check cannot run against this excerpt. It is not an installable release, a self-contained hardware launcher or an additional measurement archive. No source file has been rewritten. The original [MIT license](LICENSE) applies to the included tool sources; the [repository notices](../../RIGHTS_AND_NOTICES.md) retain the separate treatment of research data and figures.

The original snapshot was `notes/CLI_CONTINUATION_20261015/installed_source_final_delivery` in report `deepx_295_gui_acceptance_remeasurement_20261015/20261015T130753Z`. Its final installed verification reports all checks passed. Git HEAD remained the older `db729b9fcde00e4bcadf9200d43282977d7bf1cc` with working changes; it is not a committed A4 revision. The older preacceptance source ZIP is historical. The main [offline reproduction command](../../scripts/split-inference/README.md) uses compact numerical inputs and does not import this excerpt or require the original report directory, raw archives, accelerator SDKs or hardware.
