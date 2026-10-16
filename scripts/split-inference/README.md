# Offline split-inference analysis

From the repository root, create a dedicated environment outside the repository and use a fresh output directory:

```bash
python3 -m venv ../split-analysis-venv
../split-analysis-venv/bin/python -m pip install -r scripts/split-inference/requirements.txt
../split-analysis-venv/bin/python -I -B scripts/split-inference/reproduce.py \
  --output ../split-analysis-output --verify
```

Python 3.10 was used for the original source analysis. The A4 publication environment uses Python 3.12.3 with the same pinned NumPy 1.26.4, SciPy 1.13.1 and Matplotlib 3.8.4 requirements. The reproduction command reports rendering differences when the environment changes. The command reads the compact inputs in `results/split-inference/data/inputs`, checks their existing manifest, and regenerates every numerical export, all 21 PDF/SVG/PNG figure families, captions, findings and methods. It uses no network, sensors, accelerators, models or datasets after dependency installation. It processes stored numerical observations; it does not reintegrate raw sensor traces or repeat a benchmark.

`--verify` runs the existing selection/aggregation/Pareto tests, an independent standard-library checker and a direct byte comparison of generated scientific artifacts with the published copies. Different plotting dependencies may change rendering bytes; a mismatch is reported rather than hidden. The independent checker verifies all 450 FPS cohorts, 1,350 energy repeats, 42 Full configurations, 204 Native/Generic pairs, 816 split/Full comparisons, all figure payloads, and the preservation of all 375 direct observations outside the A4 replacement cohort and 450 original quality selections. It also checks all 450 Pareto rows, the 21 model/setup groups, joint and runner-specific fronts, and the plotted coordinates. Front membership is recomputed from the current observations; quality remains visible and does not filter membership.

For numerical reproduction with Python alone, omit plotting dependencies and add `--numeric-only`; this verifies the numerical data and tables but skips figure generation. Both modes require an empty or nonexistent output directory. Plot cache files are placed beside that output, outside the repository.

The selection rules, including throughput maximization and energy minimization within each model/setup, are in [config.json](config.json). Scripts preserve the source calculation and rendering logic; the export changes relative data paths, extracts the unchanged quantile helper, and omits duplicate manuscript ZIPs, report matrices and output-hash registries. [Results and interpretation limits](../../results/split-inference/README.md) describe actual timed-work differences, quality losses, original flags and unresolved source limitations. Existing archive identifiers in the data are metadata, not dependencies on private files.

The analysis retains the selection, aggregation and Pareto rules of [Results revision 380dfa09](https://github.com/Keff789/onnx-splitpoint-results/tree/380dfa09aa6740acdc71908cb6e5dd5c8fc115ad/results/evaluation/paper_after_refresh16_20261013), with the current `deepx_native_a4_20261015` replacement cohort. Exactly 75 DeepX Native identities use 225 selected performance and 225 calibrated energy repeats; the remaining direct observations and all original quality selections are retained. The offline evaluator reads these compact inputs, independently of the [ONNX Splitpoint Tool sources](../../software/README.md).
