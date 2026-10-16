# Historical quality examples

Archived dataset quality, not new inference. Scores use percent, differences percentage points, and relative loss percent. The intervals are archived paired 95% bootstrap intervals. Full TensorRT companions are counted only once.

| Model | Setup / backend | Case | Metric | Candidate (%) | CPU (%) | Difference (pp) | Difference interval (pp) | Relative loss (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MobileNet-V3-L | DeepX/deepx | full | Top1 | 71.72 | 73.70 | -1.98 | [-2.74, -1.26] | 2.69 | reference_close |
| MobileNet-V3-L | DeepX/deepx | b043 | Top1 | 66.60 | 73.70 | -7.10 | [-8.04, -6.10] | 9.63 | accuracy_loss |
| MobileNet-V3-L | H10/hailo10h | b001 | Top1 | 59.42 | 73.70 | -14.28 | [-15.48, -13.02] | 19.38 | accuracy_loss |
| MobileNet-V3-L | H10/hailo10h | b001 | Top1 | 72.44 | 73.70 | -1.26 | [-1.84, -0.60] | 1.71 | reference_close |
| MobileNet-V3-L | H10/hailo10h | b119 | Top1 | 58.44 | 73.70 | -15.26 | [-16.36, -14.02] | 20.71 | accuracy_loss |
| ResNet-50 | DeepX/deepx | full | Top1 | 80.54 | 80.44 | 0.10 | [-0.30, 0.48] | -0.12 | reference_close |
| ResNet-50 | H10/hailo10h | b002 | Top1 | 80.60 | 80.44 | 0.16 | [-0.30, 0.62] | -0.20 | reference_close |
| ResNet-50 | H8/hailo8 | b002 | Top1 | 80.32 | 80.44 | -0.12 | [-0.58, 0.32] | 0.15 | reference_close |
| YOLO26s | H10/hailo10h | b003 | COCO_AP_50_95 | 34.17 | 40.09 | -5.92 | [-6.38, -5.47] | 14.77 | accuracy_loss |
| YOLO26s | H10/hailo10h | b021 | COCO_AP_50_95 | 39.21 | 40.09 | -0.88 | [-1.16, -0.59] | 2.19 | reference_close |
| YOLO26s | H8/hailo8 | b003 | COCO_AP_50_95 | 32.33 | 40.09 | -7.76 | [-8.32, -7.25] | 19.36 | accuracy_loss |
| YOLO26s | H8/hailo8 | b021 | COCO_AP_50_95 | 39.18 | 40.09 | -0.91 | [-1.18, -0.63] | 2.26 | reference_close |
