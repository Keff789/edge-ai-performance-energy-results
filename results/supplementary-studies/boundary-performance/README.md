# Measured performance along graph boundaries

YOLOv7 / H8; physical host `orin_nx_hailo8_01`.

- EN: [PDF](artifacts/en/figures/yolov7_h8_boundary_performance.pdf), [SVG](artifacts/en/figures/yolov7_h8_boundary_performance.svg), [PNG](artifacts/en/figures/yolov7_h8_boundary_performance.png), [LaTeX caption](artifacts/en/figures/yolov7_h8_boundary_performance_caption.tex)
- DE: [PDF](artifacts/de/figures/yolov7_h8_boundary_performance.pdf), [SVG](artifacts/de/figures/yolov7_h8_boundary_performance.svg), [PNG](artifacts/de/figures/yolov7_h8_boundary_performance.png), [LaTeX caption](artifacts/de/figures/yolov7_h8_boundary_performance_caption.tex)

Both languages use the same [numeric payload](data/yolov7_h8_boundary_performance.json), [measurement CSV](data/yolov7_h8_boundary_performance_measurements.csv), and [graph boundary CSV](data/yolov7_h8_boundary_performance_graph_boundaries.csv).

## Interpretation

- The lower panel contains all 308 graph positions. 307 occur in the current workflow candidate universe. Bars give logical boundary tensor size in decimal MB, not measured PCIe traffic or technical eligibility.
- The upper panel contains 22 unique Generic observations (21 quality-admissible) and 3 Native observations. Generic observations from the broader study and the paired set are merged only when identities and FPS agree.
- The thin Generic line is only a visual guide between measured, admitted points. Native observations are points only. Orange crosses show measured quality failures.
- The dashed Full reference is the fastest quality-admissible Full deployment on this physical host: 53.05532535 FPS (`native_full_tensorrt`).
- Published source files are read only. Conflicting duplicate observations, graph IDs, model hashes, and boundary byte counts cause generation to stop.

## Reproduce

From the Results repository root:

```bash
python scripts/split-inference/boundary_performance.py --model yolov7_paper --setup H8 --output /tmp/boundary-performance --languages en de --verify
```

The JSON payload records exact input paths and SHA256 hashes. `MANIFEST.json` records generated output hashes. No new hardware measurements are taken.
