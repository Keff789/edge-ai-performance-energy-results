# Complete MLSys supplement

[Read the supplement](MLSys_Supplement.pdf) or download its [LaTeX build sources](source.zip). This R31 working revision includes the all-seven-model Weighted analysis alongside the runtime settings, quality and artifact audits, scheduling protocols and energy acquisition.

Section H.2 documents full-workflow graph normalization, the 15-node analytic operation-count extension, the weight-fitting objective, seven model-held-out folds and fixed-weight sensitivity checks. Section H.1 retains the earlier complete shortlist-budget analysis. Section J retains the five fixed graph rules and their original Native reference rates.

The [R30 publication profile](../../../results/split-inference/publications/mlsys-r30/README.md) generates all active figures and numerical tables from recorded inputs. It includes the new Weighted tables and both YOLOv7 case layouts. Its [reproduction command](../../../scripts/split-inference/README.md) preserves the frozen R22 data. The [Weighted input and result bundle](../../../results/supplementary-studies/rq2-weighted-20261020/README.md) provides graph inputs, bindings, operation rules, rankings and fold records.

The source archive contains only the files needed to compile this supplement. It was selected from the successful build's file recorder using [package_mlsys_source.py](../../../scripts/split-inference/package_mlsys_source.py). Build with `latexmk -pdf supplement.tex`. No hardware, Python analysis or model compilation is required. SHA256SUMS covers this PDF and source archive.

Original audit records and scheduling evidence are linked from the [MLSys entry point](../README.md). This is an author-visible working document, not a claim of submission or acceptance.
