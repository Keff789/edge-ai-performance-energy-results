# Generic420 RQ3: published conditional analysis

Status: **preliminary**. 420 selected configurations; 359 accepted FPS medians; 315 quality-eligible cuts in 21 model–accelerator groups. 43 measured quality failures, 1 measured quality decisions pending, 61 technical exclusions and 0 FPS measurements pending.

The candidate pool is conditional on available, quality-eligible measurements. Historical quality is not a current endpoint admission. Open decisions remain excluded; this is not a final full-quality universe. Pending identities and historical roles are in `inputs/feature_metadata.json`. Native measurements are unchanged.

Mean held-out Generic throughput loss (%); every model–accelerator group has equal weight:

| Ranking | 1 cut | 3 cuts | 5 cuts | Mean at 1, 3, 5 |
| --- | ---: | ---: | ---: | ---: |
| Boundary size | 24.875137 | 15.669239 | 5.681425 | 15.408600 |
| Standard (1, 3, 0.2) | 22.355078 | 19.559089 | 13.369527 | 18.427898 |
| Shared fitted weights | 25.112249 | 17.098464 | 6.076342 | 16.095685 |
| Fit by task | 27.134173 | 20.057827 | 9.608783 | 18.933594 |
| Fit by accelerator | 25.792706 | 13.552372 | 7.040814 | 15.461964 |
| Fit by task and accelerator | 21.029515 | 14.381382 | 9.669795 | 15.026897 |

Learned rankings hold out the complete model on every accelerator. One training fit minimizes mean loss at budgets 1, 3 and 5, and supplies the same ranking at all budgets. The primary simplex grid has step 0.0025 and includes the exact standard and pure boundary-size weights. Full-data weights are descriptive training fits, separate from held-out performance.

From the repository root, rebuild all five analyses and EN/DE figures from these published inputs:

```bash
python -B scripts/supplementary-studies/rq3-generic420/reproduce.py \
  --inputs results/supplementary-studies/rq3-generic420-20261027/inputs \
  --output /tmp/generic420-reproduced --languages en de
```

Verify a completed study with `scripts/supplementary-studies/rq3-generic420/verify.py --study STUDY`. Dependencies and the detailed scoring, holdout and sensitivity protocol are in `scripts/supplementary-studies/rq3-generic420/README.md`. No private snapshot is needed for this rebuild.
