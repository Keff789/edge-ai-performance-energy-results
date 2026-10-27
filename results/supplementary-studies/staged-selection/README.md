# Graph–Generic–Native selection

This analysis reconstructs staged selection from 187 quality-admissible paired cuts in 21 model–device groups.

Order cuts by increasing boundary size, measure up to k cuts with Generic, then measure up to two Generic favourites with Native and retain the faster result.

| Maximum Generic + Native tests per group | Exact Native winner | Mean Native throughput retained | Lowest retained throughput |
|---|---:|---:|---:|
| 5 + 2 | 17/21 (81.0%) | 96.20% | 45.53% |
| 12 + 2 | 19/21 (90.5%) | 99.65% | 94.52% |

For classifier groups, the two budgets retain 91.14% and 99.18% of the best Native throughput on average. Both budgets test all three paired cuts in each detector group and recover its Native winner.

The lowest five-test result is resnet50/H10: b002 reaches 500.66 FPS, compared with 1099.54 FPS at b095. The best cut has Bytes rank 12. Ranks 5–12 share the same 802,816-byte boundary, so the fixed configuration-identity tie order decides which equal-sized cut enters the five-cut shortlist. With twelve Generic tests, the selected cut is b095 and retains 100.00%. The rankings and per-group choices are preserved in the input rankings and [group results](data/group_budgets.csv).

Testing the same five-cut shortlists directly uses 81 Native tests and retains 96.20% mean throughput. The staged procedure uses 81 Generic and 42 Native tests for the same result. Fewer Native tests do not establish a reduction in total testing time. Existing Generic measurements can be reused before Native testing.

The throughput percentage is the equally weighted mean of per-group ratios to the best measured Native cut. It is not the probability of finding that cut. Exact-winner counts are observed successes in this paired set.

A group with fewer than k candidates tests all of them. The paired detector groups contain only three cuts. The broader Generic study remains a separate assessment of graph preselection on more detector candidates.

The calculation uses previously measured FPS and quality-admissible candidates. Test counts exclude compilation, quality evaluation, fitting and engineering. No total search-time saving is measured.

The primary figure compares one and two Native tests over Generic budgets 2–20. The data also include budget one. Non-monotonic changes are retained: a new Generic favourite can displace a stronger Native candidate from the two-test shortlist.

The workflow diagram uses the 615 graph boundaries of YOLO11l and an illustrative budget of five Generic tests, two Native tests and one selected split. The bottom row shows the processing stages; equal-sized squares above it show the number of options. Candidate-pool construction and Bytes ranking precede Generic testing. This budget is an illustration, not a measured full-graph selection trial for YOLO11l.

[English artifacts](artifacts/en/) · [German artifacts](artifacts/de/) · [Unrounded group data](data/group_budgets.csv) · [Aggregate results](data/summary.csv)

Reproduce from the repository root:

```sh
python3 scripts/supplementary-studies/staged-selection/reproduce.py --output local-output/staged-selection --languages en de --verify
```
