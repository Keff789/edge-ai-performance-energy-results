# Retrospective Native energy selection

This additional offline analysis minimizes recorded system energy per image within each model–accelerator combination, subject to at least 95% or 99% of that combination's fastest admissible Native split throughput. It evaluates 187 quality-admissible Native cuts in 21 combinations. All candidates have joint throughput and energy evidence and pass the 5% CPU-relative quality-loss rule.

- [95% throughput floor, English LaTeX](artifacts/en/tables/energy_floor_95.tex) and [full-precision CSV](artifacts/en/tables/energy_floor_95.csv)
- [99% throughput floor, English LaTeX](artifacts/en/tables/energy_floor_99.tex)
- [German tables](artifacts/de/tables/)

At a 95% throughput floor, three combinations select a different cut. ResNet-50/H8 switches from b038 to b060, retaining 98.06% of throughput with 9.50% lower recorded energy per image. RegNet-X/DeepX and YOLO26m/H8 show smaller recorded energy reductions. At a 99% floor, only those latter two choices change. These point estimates do not establish statistical significance.

The reference is the fastest admissible Native split within the same combination, not Full execution. This analysis uses energy and throughput already measured for all admitted candidates. It does not establish a limited-budget energy-selection method, prospective search savings, or equivalence of task quality. Existing publication exports and input measurements remain unchanged.

Reproduce from the repository root:

```sh
python3 scripts/split-inference/energy_aware_selection.py \
  --dataset results/split-inference/data/PAPER_DATASET.json \
  --output local-output/native-energy-selection --languages en de
```

The analysis also runs automatically in `scripts/reproduce_current.py`. `MANIFEST.json` records source and output hashes, selection rules, and summary counts.
