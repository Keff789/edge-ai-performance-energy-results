# Dissertation figures in the author's visual style

This export changes typography and colors, not the measurements or selection
results. The supplied Draw.io collection defines the palette. The dissertation
uses Nimbus Sans with blue `#2E73B6`, orange `#D18432`, green `#25896F`, text
`#18354A` and secondary lines `#64798A`. Continuous quality values retain their
Viridis scale. The paper profile remains unchanged.

`artifacts/de` contains 29 scientific/conceptual figures and the new YOLOv7
architecture. `artifacts/en` contains 16 selection/boundary figures and the
YOLOv7 architecture. The energy and archived-methods redraws in this release
are German only. Draw.io and SVG sources accompany the architecture figure.

The 32-diagram bilingual author collection is delivered separately. The LaTeX
project uses only its required PDFs and the original photos/screenshot.

## Reproduce

Run from the repository root with the existing Python dependencies, Inkscape
and the URW Base 35 Nimbus Sans fonts installed. Selection exports use the
existing `scripts/dissertation/export_thesis_selection.py` workflow with
`--language de` or `--language en`; see its README for input arguments.

```sh
python3 scripts/dissertation/render_thesis_energy_de.py --output /tmp/thesis-energy-de
python3 scripts/dissertation/render_thesis_archived_style.py --output /tmp/thesis-archived-style
python3 scripts/dissertation/verify_yolov7_topology.py
python3 scripts/dissertation/render_yolov7_architecture.py --output /tmp/yolov7-architecture
```

The boundary renderer is `scripts/split-inference/boundary_performance.py`.
It uses the same dissertation style profile and preserves its published data.

## Checks

- `VALIDATION.json`: unchanged numerical selection inputs, gallery points,
  boundary payload and energy series; selected paper exports are byte-identical.
- `ARCHIVED_STYLE_VALIDATION.json`: the 70 current-calibration points, nine
  duration points and 12 stage-cost bars agree with the archived data and
  the existing PDF vector coordinates. The DAG keeps the same six nodes,
  six directed edges and cut.
- `topology/yolov7_diagram_topology.json`: all 106 modules of the source YAML
  match the sequence of 309 operators in the archived ONNX operation audit.
  Channel dimensions and all three illustrated cut tensors agree.

The cut identifiers refer to the exported ONNX graph. b009 is before SiLU,
b044 is after the first downsampling concat, and b066 is the P3 output after
the second backbone ELAN block. The figure shows 255 output channels per
COCO head, corresponding to three anchors and 85 values per anchor.

The upstream architecture file in `sources/upstream_yolov7_training.yaml`
is from WongKinYiu/yolov7, `cfg/training/yolov7.yaml`:
https://github.com/WongKinYiu/yolov7/blob/main/cfg/training/yolov7.yaml
Its SHA256 and the frozen operation-audit hashes are recorded in the topology
JSON. This checks the diagram against archived metadata; it is not a new
model export, hardware measurement or re-fit.
