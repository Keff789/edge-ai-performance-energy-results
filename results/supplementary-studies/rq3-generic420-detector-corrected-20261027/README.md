# Generic420 RQ3: published conditional analysis

Status: **resolved_conditional_candidate_pool**. 420 selected configurations; 359 accepted FPS medians; 331 quality-eligible cuts in 21 model–accelerator groups. 28 measured quality failures, 0 measured quality decisions pending, 61 technical exclusions and 0 FPS measurements pending.

The candidate pool is conditional on available, quality-eligible measurements. Historical quality is not a current endpoint admission. All selected cases have a resolved measured-quality or technical-exclusion status. Pending identities and historical roles are in `inputs/feature_metadata.json`. Native measurements are unchanged.

Mean held-out Generic throughput loss (%); every model–accelerator group has equal weight:

| Ranking | 1 cut | 3 cuts | 5 cuts | Mean at 1, 3, 5 |
| --- | ---: | ---: | ---: | ---: |
| Boundary size | 22.224463 | 15.828006 | 6.610356 | 14.887608 |
| Standard (1, 3, 0.2) | 34.771105 | 32.265247 | 21.708820 | 29.581724 |
| Shared fitted weights | 22.481569 | 19.346566 | 10.519977 | 17.449371 |
| Fit by task | 25.463220 | 17.773157 | 10.956996 | 18.064458 |
| Fit by accelerator | 21.112468 | 15.292203 | 9.888455 | 15.431042 |
| Fit by task and accelerator | 17.741997 | 13.338409 | 9.800775 | 13.627060 |

Learned rankings hold out the complete model on every accelerator. One training fit minimizes mean loss at budgets 1, 3 and 5, and supplies the same ranking at all budgets. The primary simplex grid has step 0.0025 and includes the exact standard and pure boundary-size weights. Full-data weights are descriptive training fits, separate from held-out performance.

From the repository root, rebuild all five analyses and EN/DE figures from these published inputs:

```bash
python -B scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs "results/supplementary-studies/rq3-generic420-detector-corrected-20261027/inputs" \
  --output /tmp/generic420-reproduced --languages en de
```

Verify a completed study with `scripts/supplementary-studies/rq3-generic420/verify.py --study STUDY`. Dependencies and the detailed scoring, holdout and sensitivity protocol are in `scripts/supplementary-studies/rq3-generic420/README.md`. No private snapshot is needed for this rebuild.
