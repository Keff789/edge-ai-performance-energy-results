# Model facts table

Generated from the `*.export.json` sidecars in this exports directory.

| model_name | source | task_type | family | scale | parameters_m | parameters_total | gflops | layers | num_classes | input_shape | output_shapes | onnx_file_mb | onnx_nodes | end2end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| efficientnet_b0 | torchvision | classification | efficientnet | b0 | 5.289 | 5288548 | 0.386 |  | 1000 | 1x3x224x224 | 1x1000 | 20.762 | 239 |  |
| efficientnet_b2 | torchvision | classification | efficientnet | b2 | 9.11 | 9109994 | 1.088 |  | 1000 | 1x3x288x288 | 1x1000 | 35.576 | 341 |  |
| mobilenet_v3_large | torchvision | classification | mobilenet | v3_large | 5.483 | 5483032 | 0.217 |  | 1000 | 1x3x224x224 | 1x1000 | 21.235 | 140 |  |
| regnet_x_1_6gf | torchvision | classification | regnet | x_1_6gf | 9.19 | 9190136 | 1.603 |  | 1000 | 1x3x224x224 | 1x1000 | 35.376 | 135 |  |
| regnet_x_3_2gf | torchvision | classification | regnet | x_3_2gf | 15.297 | 15296552 | 3.177 |  | 1000 | 1x3x224x224 | 1x1000 | 58.782 | 184 |  |
| resnet101 | torchvision | classification | resnet | 101 | 44.549 | 44549160 | 7.801 |  | 1000 | 1x3x224x224 | 1x1000 | 170.21 | 241 |  |
| resnet50 | torchvision | classification | resnet | 50 | 25.557 | 25557032 | 4.089 |  | 1000 | 1x3x224x224 | 1x1000 | 97.628 | 122 |  |
| yolo11l.pt | ultralytics | detection | yolo11 | l | 25.372 | 25372160 | 87.613 | 357 | 80 | 1x3x640x640 | 1x84x8400 | 97.031 | 617 |  |
| yolo11s.pt | ultralytics | detection | yolo11 | s | 9.459 | 9458752 | 21.718 | 181 | 80 | 1x3x640x640 | 1x84x8400 | 36.289 | 320 |  |
| yolo26l.pt | ultralytics | detection | yolo26 | l | 26.3 | 26299704 | 93.798 | 392 | 80 | 1x3x640x640 | 1x300x6 | 94.999 | 606 |  |
| yolo26m.pt | ultralytics | detection | yolo26 | m | 21.896 | 21896248 | 75.398 | 280 | 80 | 1x3x640x640 | 1x300x6 | 78.166 | 418 |  |
| yolo26n.pt | ultralytics | detection | yolo26 | n | 2.572 | 2572280 | 6.119 | 260 | 80 | 1x3x640x640 | 1x300x6 | 9.481 | 384 |  |
| yolo26s.pt | ultralytics | detection | yolo26 | s | 10.01 | 10009784 | 22.838 | 260 | 80 | 1x3x640x640 | 1x300x6 | 36.517 | 384 |  |
| yolo26x.pt | ultralytics | detection | yolo26 | x | 58.993 | 58993368 | 209.534 | 392 | 80 | 1x3x640x640 | 1x300x6 | 212.944 | 606 |  |
| yolov7.pt | yolov7 | detection | yolov7 | base | 36.905 | 36905341 |  |  | 80 | 1x3x640x640 | 1x25200x85 | 140.902 | 350 | False |

See `model_facts.csv` for a machine-readable table and `model_facts.json` for the raw structured data.
