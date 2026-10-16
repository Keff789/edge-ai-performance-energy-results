# Stage-cost evaluator and figures

`analyse_stage_cost_test.py` and `stage_cost_oracle.py` are unchanged from experiment `stage_cost_composition_20261014`, revision `20261014T102852Z`. They use only Python's standard library. The small `reproduce.py` entry point resolves repository paths, copies the compact inputs to a temporary directory outside the repository and calls the original evaluator there.

`render_stage_costs.py` adapts only the pure plot logic from `finalize_stage_cost_report.py::plots` and renders the summary tables. It imports no controller, journal or hardware modules.

From the repository root, with Python 3.10+ and Matplotlib (tested with Python 3.10.12 / Matplotlib 3.8.4):

```bash
../local-preparation/split-venv/bin/python -I -B scripts/supplementary-studies/stage-cost-composition/reproduce.py \
  --output ../stage-cost-reproduction
```

The output must be fresh and outside the repository. Six numerical CSV/JSON exports are compared byte for byte with the [published study files](../../../results/supplementary-studies/stage-cost-composition/README.md). Inputs are the included PLAN, INPUT_REFERENCE_CHECK and 36 P/C/PC reports. The wrapper preserves the original evaluator's prediction-before-PC-read ordering and all validity checks; it adds no scientific model or fitting.

This checks stored-report arithmetic and recorded bindings/status, not actual hardware execution or unavailable reference arrays. The full original package's `offline_check.py` and independent archive checker require omitted arrays/journals and remain outside this compact delivery. The full command generates two figures in PDF/SVG/PNG and the summary CSV/Markdown/LaTeX tables from the fresh numerical outputs. All temporary files and Matplotlib cache files stay inside the output directory and are removed when the command finishes. Use `python3 -I -B` with this script and `--numeric-only` for the standard-library-only numerical/table path. The external environment path above is an example; compatible dependencies are declared in the existing [split requirements](../../split-inference/requirements.txt). See [methods](../../../results/supplementary-studies/stage-cost-composition/METHODS.md) for included work and limitations.
