# Existing energy calibration

Projection of the stored fit and quality gates; no new fit or acquisition. The zero intercept is fixed. Fit residuals, point spread and repeat variability do not constitute a complete propagated sensor/reference uncertainty budget. A shared multiplicative scale cancels within a setup, but nonlinear or load-dependent error need not cancel.

| Setup | Energy cases | Rate (samples/s) | Scale factor | Max fit residual (%) | Point spread (%) | Idle drift (W) | Stored gate pass | Warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H8 | 77 | 2000 | 0.913634 | 1.45 | 1.84 | 0.003 | True | None |
| H10 | 77 | 2000 | 0.896397 | 1.60 | 2.03 | 0.005 | True | point_factor_spread_too_high;scale_factor_outside_configured_range |
| DeepX | 77 | 2000 | 0.903508 | 0.54 | 0.68 | 0.005 | True | None |
