# Table 3: Globally fastest observed deployments

Globally fastest observed Full versus globally fastest observed split, one row per model. R_global = split FPS / global Full FPS; delta_E_global (%) = 100 (split energy / global Full energy - 1). Selection uses unrounded observed cohort FPS across all setups and Native/Generic splits; exact ties use ascending UID. Energy is the mean calibrated host-inclusive J/image, displayed as mJ/image, of each exact FPS-selected UID. Energy and quality never veto the FPS selection. NA denotes a missing candidate or metric, with explicit reasons and full original records in CSV/JSON. These retrospective deployment comparisons do not imply equal quality, equal timed endpoints, an isolated split effect or statistically significant differences.

| Model | Fastest Full (backend, host) | Full FPS | Full mJ/image | Fastest split (runner, setup/cut) | Split FPS | Split mJ/image | R_global | delta_E_global (%) |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| MobileNetV3-L | DeepX (DeepX host) | 1469 | 12.01 | Native DeepX/b135 | 1552 | 12.59 | 1.06 | 4.8 |
| RegNet-X 1.6GF | DeepX (DeepX host) | 538 | 31.54 | Native H10/b123 | 1367 | 15.83 | 2.54 | -49.8 |
| ResNet-50 | DeepX (DeepX host) | 656 | 27.65 | Native H10/b095 | 1100 | 29.46 | 1.68 | 6.6 |
| YOLO11l | DeepX (DeepX host) | 63 | 315.23 | Native H10/b120 | 53 | 555.75 | 0.84 | 76.3 |
| YOLO26m | TRT (H8 host) | 85 | 400.03 | Native H10/b043 | 110 | 319.65 | 1.30 | -20.1 |
| YOLO26s | TRT (DeepX host) | 152 | 187.80 | Native H8/b021 | 187 | 157.65 | 1.23 | -16.1 |
| YOLOv7 | DeepX (DeepX host) | 83 | 269.44 | Native H8/b066 | 113 | 330.14 | 1.35 | 22.5 |
