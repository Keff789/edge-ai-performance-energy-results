# Historical Native endpoint tables

The [study and input description](../../../results/supplementary-studies/native-endpoint-reconstruction/README.md) distinguish three serial repetitions, three concurrent one-image smoke repetitions, 32 decoder-only image observations, and three separate pipeline repetitions cycling 32 images.

```bash
python3 -I -B scripts/supplementary-studies/native-endpoint-reconstruction/reproduce.py --output ../native-endpoint-reproduced
```

Run from the repository root with Python 3.10+; no third-party packages are needed. The explicit output must be fresh or empty and outside the repository. Imports do not read inputs, calculate results or write files.

`report_statistics.py` contains the unchanged pure `percentile` and `summarize` functions from `onnx_splitpoint_tool/resources/native_concurrent_three_stage_yolov7/three_stage_canary.py` in the bundled v2.94.0 snapshot. The original [MIT license](LICENSE) applies to those functions. `reproduce.py` projects the retained report fields, validates cohort/parity/timing separation and source aggregates, and emits nineteen CSV, Markdown, TeX and JSON outputs. `endpoint_history.py` adds the archived 32-image pipeline aggregates and two clearly labelled manuscript-summary table families; it reuses the same statistics and table writer. The earlier one-image and decoder tables are preserved. Full precision is kept in CSV/JSON; display tables round FPS to integers and decoder milliseconds to three decimals.

Hardware launchers and raw-array diagnostics remain in the software snapshot and are not part of this offline command.
