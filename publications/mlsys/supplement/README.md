# MLSys supplement

[Read the supplement](MLSys_Supplement.pdf) or download its [LaTeX build sources](source.zip). The nine-page R32 supplement focuses on the evidence needed to assess and reproduce the main paper. It removes historical analyses and duplicate presentations from the current PDF. The main data and results are unchanged; all existing repository data remain available.

The supplement contains A: scope and quality, B: Full references and repeat ranges, C: runtime settings and completion contracts, D: artifact audit, E: selection methods and results, F: controlled scheduling, G: independent stage costs, H: energy calibration and measurement windows, and I: reproduction. Section E.1 retains the device-specific Generic calibration. Section E.2 documents graph normalization, the 15-node analytic operation-count extension, weight fitting, seven model-held-out folds and fixed-weight sensitivity checks.

The [R30 publication profile](../../../results/split-inference/publications/mlsys-r30/README.md) remains the generator profile for the paper figures and numerical tables. It includes the Weighted tables and both YOLOv7 case layouts. Its [reproduction command](../../../scripts/split-inference/README.md) preserves the frozen R22 data. The [Weighted input and result bundle](../../../results/supplementary-studies/rq2-weighted-20261020/README.md) provides graph inputs, bindings, operation rules, rankings and fold records. Older generated assets remain available even when they are no longer included in the current PDF.

The following material is available separately:

| Material removed from the current PDF | Retained source |
|---|---|
| Historical five-rule graph comparison and earlier full-budget curves | [All-cut study, rankings, curves and reproduction](../../../results/supplementary-studies/rq2-all-cuts-20261020/README.md) |
| Earlier random-budget analysis and detailed calibration group tables | [Budget table](../../../results/split-inference/publications/mlsys-r30/tables/r14_budget_details.csv), [calibration groups](../../../results/split-inference/publications/mlsys-r30/tables/r15_calibration_groups.csv) and [calibration summary](../../../results/split-inference/publications/mlsys-r30/tables/r15_calibration_summary.csv) |
| Earlier twenty-process Native-only ResNet series | [Numerical results](../../../results/split-inference/publications/mlsys-r30/tables/r15_scheduling_native_only.csv) and [original records in the RegNet evidence archive](../../../results/supplementary-studies/mlsys-evidence-mechanism-20261017/evidence/regnet_scheduling_evidence.tar.xz) |
| Top-2 splits ranked by relative same-host gain | [Complete table](../../../results/split-inference/publications/mlsys-r30/tables/current_top2_relative.csv) |
| Complete YOLOv7 split table | [Complete table](../../../results/split-inference/publications/mlsys-r30/tables/yolov7_completed_table.csv) |
| Unfiltered Generic selection groups | [All group values](../../../results/split-inference/publications/mlsys-r30/tables/current_selection_groups.csv) |
| Compiler feasibility, quality recovery and interface side experiments | [Public feasibility and quality outputs](../../../results/supplementary-studies/mlsys-selection-20261007/analysis/vendor_output/) and the immutable R31 supplement below |

The complete previous [R31 PDF](https://github.com/Keff789/edge-ai-performance-energy-results/blob/1f76a28746019d46c6265084f443370c642fb73e/publications/mlsys/supplement/MLSys_Supplement.pdf) and [R31 LaTeX source archive](https://github.com/Keff789/edge-ai-performance-energy-results/blob/1f76a28746019d46c6265084f443370c642fb73e/publications/mlsys/supplement/source.zip) preserve the earlier presentation at a fixed repository revision. For the compiler-interface probes, this archive preserves their descriptions; their original probe files are not published as standalone repository files.

The current source archive contains only the files needed to compile this supplement. It was selected from the successful build's file recorder using [package_mlsys_source.py](../../../scripts/split-inference/package_mlsys_source.py). Build with `latexmk -pdf supplement.tex`. No hardware, Python analysis or model compilation is required. SHA256SUMS covers this PDF and source archive.

Original audit records and scheduling evidence are linked from the [MLSys entry point](../README.md). This is an author-visible working document, not a claim of submission or acceptance.
