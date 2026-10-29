# German DrawIO sources used by the dissertation

This directory contains the 17 corrected editable `.drawio` files and their
17 corrected native-text SVG exports. The corresponding vector PDFs are in
`publications/dissertation/thesis-v56/de/illustrations/`.

The authoritative inventory is
`publications/dissertation/thesis-v56/de/illustrations/DRAWIO_MANIFEST.json`.
Its paths are relative to the repository root. Each entry records the original
uploaded-source hashes, corrected-source hashes, PDF hash, exact export command,
label corrections, typography refinements, and recommended LaTeX inclusion width.

The source geometry, colors and connections retain the supplied design, with
the documented unsupported Hailo-8 blocks removed. German line breaks and local
font sizing were adjusted for the final book size. `Generic` and `Native` remain
method names. `ST.`, `SP.` and `RE.` denote Steuerung, Speicher and Rechnen.

## Reproduce the PDFs

Run the per-entry commands in the manifest from the repository root. This
requires Inkscape 1.2.2, Cairo 1.18.0, and Nimbus Sans Regular/Bold for the validated
rendering. For example:

```sh
inkscape \
  publications/dissertation/thesis-v56/de/sources/drawio/Export_SVG/01_Hardwarearchitekturen/01_Orin_NX.svg \
  --export-area-page --export-type=pdf \
  --export-filename=publications/dissertation/thesis-v56/de/illustrations/architekturen/architecture_orin_nx.pdf
```

Each of the 17 committed SVGs has been re-exported and compared with its PDF:
selectable text, vector-object counts and rendered pixels match. PDF creation
timestamps vary between exports; the stored PDF SHA-256 identifies the published
snapshot. The thesis receives only these PDFs.

`scripts/dissertation/drawio/export_drawio_de.py` documents the transformation
from the original supplied German bundle. The SVGs in this directory already
contain those corrections and typography refinements, so direct Inkscape export
is the reproduction path for this source snapshot. The paired DrawIO files retain
editable labels, explicit line breaks and synchronized text-box geometry for
subsequent editing.
