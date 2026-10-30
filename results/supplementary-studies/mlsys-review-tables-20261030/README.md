# Compact deployment and quality table

This additional presentation table combines the seven source-selected global Full/split throughput winners with their calibrated energy change and direct quality difference in percentage points. The original throughput/energy and quality exports remain unchanged. Full means single-backend full-model execution. Passing the 5% numerical quality-loss criterion does not establish statistical equivalence.

- [English table](artifacts/en/tables/best_cases_quality_table.md) and [LaTeX](artifacts/en/tables/best_cases_quality_table.tex)
- [German table](artifacts/de/tables/best_cases_quality_table.md) and [LaTeX](artifacts/de/tables/best_cases_quality_table.tex)
- [Full-precision source](../../split-inference/publications/mlsys-r30/tables/r14_winner_quality.json)

Reproduce from the repository root:

```sh
python3 scripts/split-inference/render_review_tables.py --output local-output/review-tables --languages en de
```

The same export runs automatically in `scripts/reproduce_current.py`. CSV and JSON payloads retain identical values and deployment identities across languages. No hardware measurements, deployment reselection, or new quality decisions are performed.
