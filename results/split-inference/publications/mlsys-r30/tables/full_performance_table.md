# Full Performance

Full throughput and calibrated system energy. TensorRT columns are arithmetic means of the three host-specific FPS medians and mean energies. Winner comparisons use concrete Full configurations. * marks more than 5% numeric CPU-relative quality loss. Numeric quality eligibility is retained for every actual Full in the CSV/JSON.

| Model | TRT FPS | TRT mJ/image | H8 FPS | H8 mJ/image | H10 FPS | H10 mJ/image | DeepX FPS | DeepX mJ/image |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MobileNetV3-L | 718 | 28.18 | 118* | 126.75 | 210* | 74.96 | 1469 | 12.01 |
| RegNet-X | 321 | 74.43 | 362 | 43.24 | 259 | 61.79 | 538 | 31.54 |
| ResNet-50 | 521 | 55.35 | 122 | 132.45 | 184 | 89.54 | 656 | 27.65 |
| YOLO11l | 39 | 669.75 | 11* | 1426.62 | 11 | 1659.47 | 63 | 315.23 |
| YOLO26m | 84 | 393.12 | 18* | 935.03 | 14* | 1290.53 | 80 | 239.32 |
| YOLO26s | 151 | 192.66 | 23* | 701.73 | 15* | 1108.70 | 105 | 176.81 |
| YOLOv7 | 51 | 598.39 | 32* | 549.84 | 33* | 601.83 | 83 | 269.44 |
