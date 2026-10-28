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

Two previously documented factual clarifications are retained:

- The unsupported ISP and H.264 blocks and their arrows are removed from the
  Hailo-8 schematic. Hailo's response confirms that Hailo-8 has no encoder:
  https://community.hailo.ai/t/ffmpeg-and-hailo-8-support/1278
- The stage-cost diagram says `Compiled subgraph`, replacing
  `Workload + calibration`, to avoid treating calibration as timed computation.

The DrawIO-cell text comparison verifies that these are the only semantic
changes. All other text values are preserved apart from whitespace and line
breaks. The manifest records original, working-source and PDF hashes.
