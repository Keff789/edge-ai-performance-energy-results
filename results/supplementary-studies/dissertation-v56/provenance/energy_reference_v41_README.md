# Energy reference resources for dissertation v41

This directory contains the compact, reviewable evidence used by Chapter 4 of the dissertation. It is derived from the final six-workload Jetson measurement state associated with `common_reference_psd_tool_v0.8.2`; the complete numerical full run used analysis schema 9 with tool v0.8.1, while v0.8.2 regenerated the final documentation artifacts.

## Contents

- `data/`: compact CSV summaries, automatic-pipeline summaries and generated LaTeX result macros.
- `figures/`: vector figures reproduced in the thesis plus diagnostic publication figures retained for audit.
- `generate_energy_results_v41.py`: regenerates `data/energy_results_v41.tex` from the canonical CSV inputs.
- `generate_measurement_setups_v41.py`: regenerates the vector measurement-boundary schematic.
- `generate_thesis_energy_figures_v41.py`: regenerates thesis-oriented rate, duration and frequency-band figures from packaged CSV inputs and the canonical publication figures.
- `SOURCE_SHA256.txt`: hashes of every compact source and figure in this directory.

## Regeneration

From the dissertation source root:

```bash
python3 9_resources/energy_reference_v41/generate_energy_results_v41.py
python3 9_resources/energy_reference_v41/generate_measurement_setups_v41.py
python3 9_resources/energy_reference_v41/generate_thesis_energy_figures_v41.py
```

The scripts do not access the large raw trace store. Replacing the canonical CSV inputs requires a new validated artifact export from the measurement tool before regeneration.

## Interpretation constraints

- Same-execution reconstruction isolates the numerical sampling effect; direct rate sweeps are separate physical runs.
- Derived windows and sampling-grid offsets are nested within physical runs and are not independent replications.
- PSD area after mean removal is variance, not electrical energy.
- Active-minus-idle PSD is a descriptive comparison of independent acquisitions, not causal source separation.
- The YOLO-FP32 Tektronix zero correction preserves raw values and is post-hoc and non-independent; no gain is fitted.
- The 2-kS/s bounds are empirical for the evaluated Jetson platform, module-input boundary, measurement setups, workloads, precision modes and exact-window definition.
- No complete GUM/Monte-Carlo uncertainty budget is claimed.

The detailed item-level mapping is documented in `2_body/04_energy/MEASUREMENT_ARTIFACT_MANIFEST_v41.md`.
