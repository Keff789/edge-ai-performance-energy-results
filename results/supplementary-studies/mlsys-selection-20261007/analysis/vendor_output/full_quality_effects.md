# Unique Full quality effects

Archived dataset quality, not new inference. Scores use percent, differences percentage points, and relative loss percent. The intervals are archived paired 95% bootstrap intervals. Full TensorRT companions are counted only once.

| Model | Setup / backend | Case | Metric | Candidate (%) | CPU (%) | Difference (pp) | Difference interval (pp) | Relative loss (%) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MobileNet-V3-L | DeepX/deepx | full | Top1 | 71.72 | 73.70 | -1.98 | [-2.74, -1.26] | 2.69 | reference_close |
| MobileNet-V3-L | H10/hailo10h | b001 | Top1 | 59.42 | 73.70 | -14.28 | [-15.48, -13.02] | 19.38 | accuracy_loss |
| MobileNet-V3-L | H8/hailo8 | b001 | Top1 | 60.62 | 73.70 | -13.08 | [-14.24, -11.90] | 17.75 | accuracy_loss |
| MobileNet-V3-L | DeepX/tensorrt | full | Top1 | 73.60 | 73.70 | -0.10 | [-0.22, 0.02] | 0.14 | reference_close |
| MobileNet-V3-L | H10/tensorrt | full | Top1 | 73.64 | 73.70 | -0.06 | [-0.16, 0.04] | 0.08 | reference_close |
| MobileNet-V3-L | H8/tensorrt | full | Top1 | 73.64 | 73.70 | -0.06 | [-0.14, 0.02] | 0.08 | reference_close |
| RegNet-X | DeepX/deepx | full | Top1 | 78.70 | 78.94 | -0.24 | [-0.70, 0.16] | 0.30 | reference_close |
| RegNet-X | H10/hailo10h | b001 | Top1 | 78.84 | 78.94 | -0.10 | [-0.64, 0.42] | 0.13 | reference_close |
| RegNet-X | H8/hailo8 | b001 | Top1 | 78.76 | 78.94 | -0.18 | [-0.74, 0.36] | 0.23 | reference_close |
| RegNet-X | DeepX/tensorrt | full | Top1 | 78.94 | 78.94 | 0.00 | [-0.08, 0.08] | 0.00 | reference_close |
| RegNet-X | H10/tensorrt | full | Top1 | 78.94 | 78.94 | 0.00 | [-0.08, 0.08] | 0.00 | reference_close |
| RegNet-X | H8/tensorrt | full | Top1 | 78.92 | 78.94 | -0.02 | [-0.10, 0.08] | 0.03 | reference_close |
| ResNet-50 | DeepX/deepx | full | Top1 | 80.54 | 80.44 | 0.10 | [-0.30, 0.48] | -0.12 | reference_close |
| ResNet-50 | H10/hailo10h | b002 | Top1 | 80.60 | 80.44 | 0.16 | [-0.30, 0.62] | -0.20 | reference_close |
| ResNet-50 | H8/hailo8 | b002 | Top1 | 80.32 | 80.44 | -0.12 | [-0.58, 0.32] | 0.15 | reference_close |
| ResNet-50 | DeepX/tensorrt | full | Top1 | 80.50 | 80.44 | 0.06 | [-0.06, 0.18] | -0.07 | reference_close |
| ResNet-50 | H10/tensorrt | full | Top1 | 80.50 | 80.44 | 0.06 | [-0.06, 0.18] | -0.07 | reference_close |
| ResNet-50 | H8/tensorrt | full | Top1 | 80.50 | 80.44 | 0.06 | [-0.06, 0.16] | -0.07 | reference_close |
| YOLO11l | DeepX/deepx | full | COCO_AP_50_95 | 45.67 | 46.68 | -1.01 | [-1.41, -0.68] | 2.17 | reference_close |
| YOLO11l | H10/hailo10h | b003 | COCO_AP_50_95 | 45.31 | 46.68 | -1.38 | [-1.83, -1.03] | 2.95 | reference_close |
| YOLO11l | H8/hailo8 | b003 | COCO_AP_50_95 | 44.15 | 46.68 | -2.53 | [-2.98, -2.17] | 5.42 | accuracy_loss |
| YOLO11l | DeepX/tensorrt | full | COCO_AP_50_95 | 46.68 | 46.68 | 0.00 | [-0.03, 0.04] | -0.00 | reference_close |
| YOLO11l | H10/tensorrt | full | COCO_AP_50_95 | 46.66 | 46.68 | -0.02 | [-0.05, 0.03] | 0.04 | reference_close |
| YOLO11l | H8/tensorrt | full | COCO_AP_50_95 | 46.66 | 46.68 | -0.02 | [-0.05, 0.03] | 0.04 | reference_close |
| YOLO26m | DeepX/deepx | full | COCO_AP_50_95 | 44.27 | 44.90 | -0.63 | [-0.82, -0.35] | 1.41 | reference_close |
| YOLO26m | H10/hailo10h | b003 | COCO_AP_50_95 | 40.55 | 44.90 | -4.34 | [-4.74, -3.92] | 9.68 | accuracy_loss |
| YOLO26m | H8/hailo8 | b003 | COCO_AP_50_95 | 39.65 | 44.90 | -5.25 | [-5.69, -4.74] | 11.69 | accuracy_loss |
| YOLO26m | DeepX/tensorrt | full | COCO_AP_50_95 | 44.86 | 44.90 | -0.04 | [-0.09, 0.02] | 0.10 | reference_close |
| YOLO26m | H10/tensorrt | full | COCO_AP_50_95 | 44.85 | 44.90 | -0.05 | [-0.10, -0.00] | 0.12 | reference_close |
| YOLO26m | H8/tensorrt | full | COCO_AP_50_95 | 44.82 | 44.90 | -0.08 | [-0.12, -0.02] | 0.18 | reference_close |
| YOLO26s | DeepX/deepx | full | COCO_AP_50_95 | 39.39 | 40.09 | -0.70 | [-0.94, -0.43] | 1.74 | reference_close |
| YOLO26s | H10/hailo10h | b003 | COCO_AP_50_95 | 34.17 | 40.09 | -5.92 | [-6.38, -5.47] | 14.77 | accuracy_loss |
| YOLO26s | H8/hailo8 | b003 | COCO_AP_50_95 | 32.33 | 40.09 | -7.76 | [-8.32, -7.25] | 19.36 | accuracy_loss |
| YOLO26s | DeepX/tensorrt | full | COCO_AP_50_95 | 40.11 | 40.09 | 0.02 | [-0.03, 0.06] | -0.05 | reference_close |
| YOLO26s | H10/tensorrt | full | COCO_AP_50_95 | 40.09 | 40.09 | 0.00 | [-0.04, 0.05] | -0.01 | reference_close |
| YOLO26s | H8/tensorrt | full | COCO_AP_50_95 | 40.09 | 40.09 | 0.00 | [-0.04, 0.05] | -0.01 | reference_close |
| YOLOv7 | DeepX/deepx | full | COCO_AP_50_95 | 45.86 | 46.03 | -0.17 | [-0.30, -0.06] | 0.38 | reference_close |
| YOLOv7 | H10/hailo10h | b009 | COCO_AP_50_95 | 41.52 | 46.03 | -4.52 | [-4.73, -4.26] | 9.81 | accuracy_loss |
| YOLOv7 | H8/hailo8 | b009 | COCO_AP_50_95 | 40.78 | 46.03 | -5.26 | [-5.50, -4.95] | 11.42 | accuracy_loss |
| YOLOv7 | DeepX/tensorrt | full | COCO_AP_50_95 | 46.04 | 46.03 | 0.00 | [-0.03, 0.03] | -0.01 | reference_close |
| YOLOv7 | H10/tensorrt | full | COCO_AP_50_95 | 46.02 | 46.03 | -0.02 | [-0.05, 0.01] | 0.04 | reference_close |
| YOLOv7 | H8/tensorrt | full | COCO_AP_50_95 | 46.02 | 46.03 | -0.01 | [-0.03, 0.02] | 0.03 | reference_close |
