# Dissertation v56: frozen sources and exports

This snapshot separates the dissertation's typesetting files from analysis
sources. It preserves the compact inputs and historical artifacts removed
from the LaTeX package `doctor_thesis_v56_de_minimal_aktualisiert.zip` on
2026-10-28. It does not change the current scientific analysis or replace its
registered generators.

## Contents

| Path | Purpose |
| --- | --- |
| `inputs/` | Frozen CSV/JSON inputs and accompanying notes from the supplied thesis package |
| `archive/` | Twelve superseded figure PDFs and eight historical table exports |
| `provenance/` | Original source manifests and historical export documentation |
| `artifacts/energy-v41/` | Five historical English figures and the v41 numeric macro export regenerated from these inputs |
| `SOURCE_MANIFEST.json` | Original and destination paths, hashes, existing identical repository files, and generator sources |

The matching [fixed publication exports](../../../publications/dissertation/thesis-v56/README.md)
record exactly the assets used by the thesis. The six historical programs are
under [legacy-v56](../../../scripts/dissertation/legacy-v56/README.md).

Some inputs also exist in the main research collections. This compact frozen
snapshot intentionally retains the supplied versions together with the old
adapters; identical existing paths are recorded in the manifest. These copies
are not additional measurements and must not be added to a scientific cohort.

## Current analyses and historical adapters

Use [the current reproduction entry point](../../../scripts/README.md) for
current paper and dissertation results. The two ranking figure families
already have a maintained generator at
`scripts/supplementary-studies/dissertation-development-2026/plot_rankings.py`.
The historical ranking programs here do not replace it.

The old v41 energy programs were executed successfully against `inputs/energie/`.
Their five PDF outputs and historical numeric macros are preserved under
`artifacts/energy-v41/`; no hardware measurements were run. They do not reproduce
the active v43 values or every localized v56 figure. The current TIM analysis
has a different scope and must not be substituted for the old values during
source cleanup.

The old full ranking calculations require original candidate inputs absent
from this snapshot. The redesigned-figure program requires four external
source images/PDFs that were also absent from the supplied thesis ZIP. These
limits are described in the generator README. The active German PDFs are
therefore preserved as fixed presentation exports with hashes, without a claim
that every historical export can be reconstructed from these six programs.

The literature reading lists under `inputs/literatur/` and the model summaries
are supporting authoring records, not measurements. Original provenance files
retain their historical paths and hashes. `SOURCE_MANIFEST.json` provides the
new repository locations.
