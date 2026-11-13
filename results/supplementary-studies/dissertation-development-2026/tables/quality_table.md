Internal paired B500 quality. Q metrics are distinct from official COCO AP; recorded decisions use unrounded source cells.

| Setup | Path | Q | Q50 | Q75 | Quality |
| --- | --- | --- | --- | --- | --- |
| DEEPX | Split b044 | 0.460 | 0.610 | 0.498 | pass |
| DEEPX | Accelerator Full | 0.456 | 0.605 | 0.493 | pass |
| DEEPX | TensorRT Full | 0.461 | 0.610 | 0.499 | pass |
| Hailo-10H | Split b044 | 0.458 | 0.608 | 0.494 | pass |
| Hailo-10H | Accelerator Full | 0.420 | 0.610 | 0.472 | fail |
| Hailo-10H | TensorRT Full | 0.461 | 0.610 | 0.499 | pass |
| Hailo-8 | Split b044 | 0.460 | 0.607 | 0.497 | pass |
| Hailo-8 | Accelerator Full | 0.415 | 0.598 | 0.467 | fail |
| Hailo-8 | TensorRT Full | 0.461 | 0.610 | 0.499 | pass |
