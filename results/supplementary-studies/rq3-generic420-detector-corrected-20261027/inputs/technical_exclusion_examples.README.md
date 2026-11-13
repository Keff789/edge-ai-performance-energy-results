# Technical exclusion examples

`technical_exclusion_examples.json` contains two compiler error excerpts for cuts that remain technically excluded in `candidates.csv`. They explain why a valid graph boundary need not yield a deployable accelerator prefix.

- **YOLO11l / H10 / b031:** the compiler reports an ambiguous output shape for the feature splitter translated from `/model.2/Split`.
- **YOLO26m / H10 / b416:** the compiler rejects detector-head operators including `GatherElements` and `TopK`.

Both cases belong to the **37 compilation failures**, not the 24 other unsupported cases. Multi-tensor boundaries are supported by Generic in general. These examples do not establish that their number of tensors alone caused failure.

The source is the previously collected `execution_precision_authorities160.json` inside the listed SM2 review archive. The JSON preserves the complete recorded error strings, source archive and member hashes, JSON pointers, and the recorded compiler-receipt hashes. Private absolute paths are omitted. This extract adds explanatory evidence without changing candidate status, measurements, or analysis populations. It is not a new compiler run.
