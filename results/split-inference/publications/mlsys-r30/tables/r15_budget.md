# Mean lost Native throughput (%) after the numerical 5% CPU-relative quality filter

Mean lost Native throughput (%) after the numerical 5% CPU-relative quality filter. Each method selects k candidates and retains their fastest Native result. Groups receive equal weight. Random values are exact expectations without replacement. Detector k=5 is unavailable.

## Classification: 151 pairs, 9 groups

| Method | k=1 | k=3 | k=5 |
| --- | --- | --- | --- |
| Generic | 32.80 | 23.77 | 20.45 |
| Calibrated Generic | 28.32 | 23.15 | 15.43 |
| Uniform random | 32.29 | 15.41 | 9.10 |
| Boundary bytes | 32.97 | 21.75 | 8.86 |

## Detection: 36 pairs, 12 groups

| Method | k=1 | k=3 | k=5 |
| --- | --- | --- | --- |
| Generic | 1.78 | 0.00 | --- |
| Uniform random | 14.09 | 0.00 | --- |

