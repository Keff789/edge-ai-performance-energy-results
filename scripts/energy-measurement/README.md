# Energy analysis tools

Run from the repository root. These commands read the shared exported outcomes and write only to new output directories outside the repository. They need no hardware or raw acquisition archive.

```bash
python3 -m venv ../energy-venv
../energy-venv/bin/python -m pip install -r scripts/energy-measurement/requirements.txt
../energy-venv/bin/python scripts/energy-measurement/reproduce.py --output ../energy-tim-output
../energy-venv/bin/python scripts/energy-measurement/direct/replot.py --output ../energy-direct-output
../energy-venv/bin/python scripts/energy-measurement/plot_calibration.py --output ../energy-calibration-output
../energy-venv/bin/python -I -B scripts/energy-measurement/reproduce.py --historical-fp16-only --output ../energy-fp16-historical-output
```

The TIM command regenerates all current numerical summaries, thirteen numerical charts and the 21-marker Jetson device-comparison chart, then independently checks pair arithmetic, quantiles, rate groups and duration curves. It also generates the separately labelled historical FP16 study described below. It does not build a manuscript. The direct command makes 66 expanded workload, overview and diagnostic charts. It reuses the original TIM Figures 1.1.0 statistical and rendering functions with the finalized estimators described in the [methods](../../results/energy-measurement/METHODS.md). The calibration command plots existing verification points without fitting new coefficients.

The `--historical-fp16-only` selection runs just the [historical 13-run FP16 study](../../results/energy-measurement/galleries/historical-fp16.md). It reuses pure aggregation and plotting functions from `commonref/analysis.py`, `psd.py` and `plotting.py`: 16,159 archived reconstruction outcomes become 49 mode/rate groups, while 351 independent acquisitions and 351 per-run spectral outcomes become 27 groups each. It exports CSV/Markdown tables and six vector PDF/SVG plus PNG figure families under `historical-fp16-20260809/`. The frequency curves are explicitly declared historical aggregate inputs; this command does not repeat Welch estimation or raw reconstruction. It needs only NumPy and Matplotlib from the existing requirements. The current all-15/matched-four-second inputs and outputs remain separate.

Two standard-library-only checks are also available:

```bash
python3 scripts/energy-measurement/reproduce.py --verify-only --output ../energy-export-audit
python3 scripts/energy-measurement/audit_scope_results.py --output ../energy-scope-audit
```

The scope audit recomputes the outer hierarchy and persistent minima from 19,824 per-record rows; it does not validate the inner raw-signal reconstruction. The numerical verification is retained from TIM v0.3, with manuscript-build/hash bookkeeping removed and paths adapted to the shared inputs.

The tested environment used Python 3.10, NumPy 1.26.4, pandas 2.3.3, SciPy 1.13.1, Matplotlib 3.8.4 and PyMuPDF 1.28.2. The original TIM package dependency pins remain in [tim/requirements.txt](tim/requirements.txt); they were not the installed local check environment. Equal numerical results, rather than byte-identical PDFs across library versions, were checked.

[Raw-analysis source](raw-analysis/README.md) includes the original native reconstruction and PSD generators with their configurations. Those programs require external raw waveforms or full-resolution spectral aggregates and are not part of the self-contained commands above. A successful redraw is not a new measurement or a full raw-data reproduction. Rights remain subject to the retained [source notices](../../results/energy-measurement/RIGHTS_AND_NOTICES.md).
