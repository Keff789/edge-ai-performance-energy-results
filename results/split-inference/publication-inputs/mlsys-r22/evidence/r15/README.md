# Compact evidence for R15

Run from the manuscript root:

```sh
python3 analysis/review_r15.py --check-only
```

Python 3.11 or later is sufficient. No third-party dependencies, network access,
hardware, external data directories or environment variables are required. The
checker is read-only and prints a JSON report to standard output. It does not
regenerate manuscript tables or figures. The four new table fragments are
included in `sections/` and their printed numerical values are checked against
the independently reconstructed source results.

## Contents and provenance

`audit_regnet/` contains unchanged excerpts from
`MLSYS_R14_SM2_ABKLAERUNG_20261017_RESULTS.zip`. These include the numerical
quality audit, calibration inputs and results, frozen protocol, 40 RegNet raw
worker reports, and the 20 earlier Native-only ResNet raw worker reports.

`resnet_replication/` contains unchanged excerpts from
`MLSYS_R14_RESNET_FULL_REPLIKATION_20261017_RESULTS.zip`. These include the frozen
protocol, all 40 fresh worker reports and the full ResNet factorial summaries.

`SOURCE_MANIFEST.json` records each copied file's original ZIP member, size and
SHA256, the full source ZIP hashes and original source directories on SM2. Every
copied file was compared byte-for-byte with its source ZIP member when preparing
this package. All 126 source files occupy approximately 2.9 MB. The reports and
protocols retain their original content, including historical paths and labels.
The later paper interpretation does not rewrite those records.

## What the checker reconstructs

- Relative numerical quality loss for all 450 configurations, the 407 eligible
  configurations (187 Native splits, 187 Generic splits, 33 Full), the 43
  exclusions, 53 cached-label disagreements and retention of all 14 global
  winner configurations.
- Eligibility for 204 paired candidates, yielding 151 classifier pairs in nine
  groups and 36 detector pairs in twelve groups. The fixed ridge is refitted in
  nine device-specific, architecture-disjoint folds. Feature standardization is
  fitted only on training rows, with an unpenalized intercept and the stated
  MSE-plus-unit-ridge objective. All 151 held-out predictions are compared.
- Generic, calibrated Generic, boundary-bytes and exact uniform-random
  selection, including selected IDs, optimum coverage, per-group loss and
  equally weighted summaries at budgets 1, 3 and 5. Detector budget 5 remains
  unavailable. The random baseline uses the finite combinatorial distribution
  of the sample maximum, with no Monte Carlo estimation.
- All 100 raw worker reports across three separate series. Completed counts
  and makespans are reconstructed from runtime metrics, checked against report
  and cell values, and used to reconstruct 85 block contrasts and 17 summary
  estimates. The check verifies frozen schedule order, distinct process IDs,
  non-overlapping execution, protocol hashes, runtime artifact hash agreement,
  warm-up, drain and task-endpoint counters. The 40 untriggered RegNet extension
  cells remain excluded. The old Native-only and new full ResNet series are
  never pooled.
- All numerical rows in the two new main-paper and two supplement table
  fragments, including publication rounding. Nominal 95% intervals use the
  five independent block log contrasts and a Student-t critical value with
  four degrees of freedom. The interaction is a ratio of ratios, not a
  single-cut speedup.

## Scope and limits

The SHA256 records establish consistency with the supplied archives. They do
not independently authenticate the measurement hardware or the historical
external files. The compact quality and feature tables retain the results of
the original source-binding audits. This checker recomputes their arithmetic
and checks joins but does not repeat those full audits. In particular, the
large historical quality/energy records, graph proofs, functional canaries,
before/after hardware snapshots and copied runtime source trees remain in the
original result archives, which must be preserved separately.

The two fully crossed studies concern known, selected cut pairs on H10 with
the frozen current runtime chains. Their intervals are nominal five-block
intervals, without a population-generalization or simultaneous-inference
claim. They do not isolate individual copy costs, measure new energy results,
prove arbitrary-input serving performance, or establish total search-cost
savings. The calibration is retrospective grouped validation on three known
classifier architectures. Its budget counts held-out Native measurements and
does not include training, Generic acquisition, compilation or quality costs.
