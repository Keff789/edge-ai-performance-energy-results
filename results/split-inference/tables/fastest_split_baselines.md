# Selected fastest split: same-host and global Full baselines

The SAME split selected in Table 3, compared with the fastest Full on its physical host and with the globally fastest Full. This table does not reselect the largest relative gain. R_host and R_global use the explicitly named Full denominators. Selection uses unrounded observed cohort FPS across all setups and Native/Generic splits; exact ties use ascending UID. Energy is the mean calibrated host-inclusive J/image, displayed as mJ/image, of each exact FPS-selected UID. Energy and quality never veto the FPS selection. NA denotes a missing candidate or metric, with explicit reasons and full original records in CSV/JSON. These retrospective deployment comparisons do not imply equal quality, equal timed endpoints, an isolated split effect or statistically significant differences.

| Model | Selected split | Split FPS | Fastest same-host Full | Host Full FPS | Globally fastest Full | Global Full FPS | R_host | R_global |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| MobileNetV3-L | Native DeepX/b135 | 1552 | DeepX (DeepX host) | 1469 | DeepX (DeepX host) | 1469 | 1.06 | 1.06 |
| RegNet-X 1.6GF | Native H10/b123 | 1367 | TRT (H10 host) | 316 | DeepX (DeepX host) | 538 | 4.33 | 2.54 |
| ResNet-50 | Native H10/b095 | 1100 | TRT (H10 host) | 522 | DeepX (DeepX host) | 656 | 2.11 | 1.68 |
| YOLO11l | Native H10/b120 | 53 | TRT (H10 host) | 39 | DeepX (DeepX host) | 63 | 1.36 | 0.84 |
| YOLO26m | Native H10/b043 | 110 | TRT (H10 host) | 84 | TRT (H8 host) | 85 | 1.31 | 1.30 |
| YOLO26s | Native H8/b021 | 187 | TRT (H8 host) | 151 | TRT (DeepX host) | 152 | 1.24 | 1.23 |
| YOLOv7 | Native H8/b066 | 113 | TRT (H8 host) | 53 | DeepX (DeepX host) | 83 | 2.13 | 1.35 |
