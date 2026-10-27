# Graph–Generic–Native selection

This analysis reconstructs staged selection from 187 quality-admissible paired cuts in 21 model–device groups.

Order cuts by increasing boundary size, measure up to k cuts with Generic, then measure up to two Generic favourites with Native and retain the faster result.

| Maximum Generic + Native tests per group | Exact Native winner | Mean Native throughput retained |
|---|---:|---:|
| 5 + 2 | 17/21 (81.0%) | 96.20% |
| 12 + 2 | 19/21 (90.5%) | 99.65% |

The throughput percentage is the equally weighted mean of per-group ratios to the best measured Native cut. It is not the probability of finding that cut. Exact-winner counts are observed successes in this paired set.

A group with fewer than k candidates tests all of them. The paired detector groups contain only three cuts. The broader Generic study remains a separate assessment of graph preselection on more detector candidates.

The calculation uses previously measured FPS and quality-admissible candidates. Test counts exclude compilation, quality evaluation, fitting and engineering. No total search-time saving is measured.

The primary figure shows budgets 2–20 with at most two Native tests. The data also include budget one. Non-monotonic changes are retained: a new Generic favourite can displace a stronger Native candidate from the two-test shortlist.

The workflow diagram uses the 615 graph boundaries of YOLO11l to illustrate model size. Candidate-pool construction precedes the Generic and Native tests. It does not claim that the staged selection was measured over all of these graph boundaries. Box widths are schematic.

[English artifacts](artifacts/en/) · [German artifacts](artifacts/de/) · [Unrounded group data](data/group_budgets.csv) · [Aggregate results](data/summary.csv)

Reproduce from the repository root:

```sh
python3 scripts/supplementary-studies/staged-selection/reproduce.py --output local-output/staged-selection --languages en de --verify
```
