# English DrawIO diagrams: dissertation typography

Input: the user's `Grafiken_DrawIO-7.zip`, directory `Grafiken_DE_EN/English`.
Only PDF files are installed in the LaTeX project. Working DrawIO/SVG copies
remain outside it. The original drawing archive is unchanged.

Dependencies: Inkscape and Python with PyMuPDF. Keep the four scripts together:
`update_drawio_thesis.py`, `normalize_drawio7.py`, `refine_drawio7_labels.py`,
and `export_drawio7.py`.

```sh
python3 update_drawio_thesis.py \
  --source /path/to/Grafiken_DE_EN/English \
  --output /path/to/exported-pdfs \
  --project /path/to/doctor_thesis_v56_en_final
```

The exporter normalizes main labels to approximately 8.6–8.7 pt at the
thesis text width, with secondary labels around 7.2 pt. Four architecture
figures use 60% of the text width instead of 76%. Broad diagrams use the
text width; their source fonts are enlarged, rather than shrinking their
already small labels. Manual line spacing and a few line breaks are adjusted
to avoid collisions. A small number of long narrow labels use 6.6–8.0 pt.

Two factual clarifications and one explanatory label are retained:

- The unsupported ISP and H.264 blocks and their arrows are removed from the
  Hailo-8 schematic. Hailo's response confirms that Hailo-8 has no encoder:
  https://community.hailo.ai/t/ffmpeg-and-hailo-8-support/1278
- The stage-cost diagram says `Compiled subgraph`, replacing
  `Workload + calibration`, to avoid treating calibration as timed computation.
- The system-boundary schematic says `System input and downstream power paths`,
  replacing the planning-style note about channel wiring. The drawing remains
  schematic and does not claim a wiring validation for every measurement.

The DrawIO-cell text comparison verifies that these are the only semantic
changes. All other text values are preserved apart from whitespace and line
breaks. The manifest records original, working-source and PDF hashes.

## German diagrams supplied on 2026-10-29

`export_drawio_de.py` reads the newest `Grafiken_DE_EN/Deutsch` directory and
the 17 DrawIO mappings in the project's prior `FINAL_FIGURE_ORIGINS.json`.
It writes corrected editable copies outside the LaTeX project and installs
only Inkscape-exported vector PDFs at the existing project asset paths.

```sh
python3 export_drawio_de.py \
  --source /path/to/Grafiken_DE_EN/Deutsch \
  --project /path/to/doctor_thesis_v56_de_final \
  --working /path/to/drawio_de_working \
  --manifest /path/to/logs/drawio_de_manifest.json
```

Use `width=.64\linewidth` for the four architecture PDFs and
`width=1.0\linewidth` for the other thirteen diagrams. Typography is measured
at the thesis text width of 356.75381 TeX points. Main labels are 8.5 pt and
titles 9.5 pt. Dense secondary labels use 7.0–8.0 pt; the six NV multimedia
labels in the Orin schematic use 6.6 pt and Hailo-10H's narrow maximum-compute
label uses 6.8 pt. No final label is 4–5 pt. Shapes, colors, connectors, and
the supplied design remain intact except for the verified Hailo-8 deletion.

The German export retains the three factual/explanatory corrections above,
keeps `Generic` and `Native` as method names, and adds German line breaks and
local label spacing. Resource abbreviations in the Hailo diagrams are
`ST.` (Steuerung), `SP.` (Speicher), and `RE.` (Rechnen). Their captions should
explain these abbreviations. Native SVG text is retained, and all fonts are
embedded as Nimbus Sans; the DrawIO compatibility-warning fallback is omitted.
The manifest records source, corrected source and PDF hashes, exact export
commands, label changes, recommended widths, and final font sizes.
