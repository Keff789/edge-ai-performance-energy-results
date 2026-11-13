# Historical dissertation displays

From the repository root, using the existing split-analysis environment:

```bash
../local-preparation/split-venv/bin/python -I -B scripts/supplementary-studies/dissertation-development-2026/reproduce.py --output ../dissertation-development-reproduced
```

The output directory must be fresh or empty and outside the repository. Python 3.10 and Matplotlib 3.8.4 were used for the checked rendering; Matplotlib is the only plotting dependency beyond the standard library. Imports perform no analysis or writes. All input tables and templates are inside this repository, and every generated file goes to the selected output directory, including Matplotlib's font cache in `matplotlib-cache/` and temporary files in `tmp/`.

The source's `plot_rankings.py` supplies the two layouts and cohort/duplicate/count/correlation checks; paths are explicit and SVG export is added. `render_tables.py` retains the source's decimal rounding and quality/runtime identity checks, extends the compiler-sensitivity table and renders the seven-row matrix. Its templates derive from the supplied dissertation's active table wrappers. No task metric, correlation, bootstrap interval, model or calibration is estimated here. Full-precision aggregate inputs are copied unchanged to `tables/` before rendering.

See the [study, scope and gallery](../../../results/supplementary-studies/dissertation-development-2026/README.md). Source attribution is recorded there; existing repository rights notices continue to apply.

For a seven-page table preview, change into the generated output directory and run `pdflatex -interaction=nonstopmode -halt-on-error table_preview.tex` twice. TeX Live with `lmodern`, `booktabs`, `tabularx`, `ragged2e`, `siunitx`, `float` and `longtable` is sufficient. The wrapper and all build products stay in that external output directory; the Python reproduction does not require TeX.
