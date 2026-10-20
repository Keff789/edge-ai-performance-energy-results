# Complete MLSys supplement

[Read the supplement](MLSys_Supplement.pdf) or download its [LaTeX build sources](source.zip). This R26 working revision includes the complete RQ2 shortlist-budget analysis, alongside the runtime settings, quality and artifact audits, scheduling protocols and energy acquisition.

Section H.1 reports exact and near-optimal Native recovery, actual trial counts and random-selection success probabilities. Section J extends all five graph rules to complete rankings and every shortlist size. The deployment and graph-score measurement sets retain their own Native reference rates. The source archive contains only the files needed to compile this supplement.

The original numerical tables and figure data come from the [frozen R22 publication profile](../../../results/split-inference/publications/mlsys-r22/README.md). The [paper renderer](../../../scripts/split-inference/render_mlsys_paper.py) regenerates its statistical plots with uniform typography and a shared color palette. RQ2 figures and the budget table come from the [complete RQ2 analysis](../../../results/supplementary-studies/rq2-all-cuts-20261020/README.md), with its [generator and reproduction command](../../../scripts/supplementary-studies/rq2-all-cuts-20261020/README.md). The main paper now uses only the current quality-filtered budget curve and restores the per-model/device Generic-loss plot. The full graph-rule comparison remains here in Section J.

Original audit records and scheduling source evidence are linked from the [MLSys entry point](../README.md).

Build the source ZIP with `latexmk -pdf supplement.tex`. No hardware or model compilation is required. The supplement is an author-visible working document, not a claim of submission or acceptance.
