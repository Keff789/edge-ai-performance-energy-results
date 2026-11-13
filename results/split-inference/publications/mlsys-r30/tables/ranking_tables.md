# Selectors

Historical six-selector experiment on fixed candidate sets. YOLOv7 uses historical Generic and the reported Native campaign; other models retain archived measurements. Frozen selector choices are not refitted. Energy uses matched groups excluding YOLOv7. Every group has equal weight.

| Selector | All /21 | Class. /9 | Detect. /12 | Median loss (%) | Mean loss (%) | Energy /18 (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smallest boundary bytes | 6 | 0 | 6 | 3.77 | 25.28 | 55.09 |
| Weighted graph score | 6 | 0 | 6 | 13.79 | 17.28 | 24.57 |
| H10 accelerator-fit score | 6 | 0 | 6 | 12.81 | 19.65 | 32.02 |
| Cycle without handover | 6 | 0 | 6 | 13.79 | 17.28 | 24.57 |
| Streaming-rate heuristic | 7 | 0 | 7 | 9.25 | 17.42 | 24.57 |
| Measured Generic completion | 11 | 3 | 8 | 0.00 | 12.74 | 28.07 |
