# Stage Costs

Independent four-cut stage-cost experiment. Median producer, consumer and pipeline completion rates over three blocks. Prediction is min(F_P,F_C); error is the median blockwise absolute percentage error. This cohort is separate from deployment and scheduling data.

| Model/cut | F_P | F_C | F_PC | Error (%) |
| --- | ---: | ---: | ---: | ---: |
| ResNet/DX b045 | 230 | 669 | 225 | 2.24 |
| ResNet/DX b002 | 473 | 520 | 444 | 5.50 |
| RegNet/H10 b059 | 1565 | 500 | 477 | 4.77 |
| RegNet/H10 b123 | 1577 | 1999 | 1518 | 3.85 |
