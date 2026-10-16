# Selection stability

Ranges span nine dependent Generic/Native repeat combinations, not confidence intervals.

| Model | Setup | Candidates | Generic selection | Native best | Rate loss | Repeat minimum | Repeat maximum | Hits / 9 combinations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mobilenet_v3_large | DeepX | 17 | b062 | b056 | 1.24% | 0.00% | 3.15% | 3 |
| mobilenet_v3_large | H10 | 17 | b027 | b085 | 31.86% | 30.99% | 38.39% | 0 |
| mobilenet_v3_large | H8 | 17 | b027 | b027 | 0.00% | 0.00% | 0.00% | 9 |
| regnet_x_1_6gf | DeepX | 20 | b052 | b052 | 0.00% | 0.00% | 0.00% | 9 |
| regnet_x_1_6gf | H10 | 20 | b052 | b123 | 70.61% | 70.22% | 74.67% | 0 |
| regnet_x_1_6gf | H8 | 20 | b066 | b073 | 8.03% | 8.03% | 8.22% | 0 |
| resnet50 | DeepX | 19 | b002 | b002 | 0.00% | 0.00% | 0.00% | 9 |
| resnet50 | H10 | 19 | b002 | b095 | 52.15% | 49.76% | 53.52% | 0 |
| resnet50 | H8 | 19 | b002 | b031 | 13.92% | 13.23% | 14.61% | 0 |
| yolo11l | DeepX | 3 | b062 | b062 | 0.00% | 0.00% | 0.00% | 9 |
| yolo11l | H10 | 3 | b003 | b120 | 13.34% | 13.34% | 13.48% | 0 |
| yolo11l | H8 | 3 | b120 | b120 | 0.00% | 0.00% | 0.00% | 9 |
| yolo26m | DeepX | 3 | b043 | b043 | 0.00% | 0.00% | 0.39% | 6 |
| yolo26m | H10 | 3 | b038 | b043 | 1.64% | 0.00% | 1.66% | 3 |
| yolo26m | H8 | 3 | b043 | b043 | 0.00% | 0.00% | 0.00% | 9 |
| yolo26s | DeepX | 3 | b021 | b021 | 0.00% | 0.00% | 0.00% | 9 |
| yolo26s | H10 | 3 | b021 | b021 | 0.00% | 0.00% | 0.00% | 9 |
| yolo26s | H8 | 3 | b021 | b021 | 0.00% | 0.00% | 0.00% | 9 |
| yolov7_paper | DeepX | 3 | b044 | b044 | 0.00% | 0.00% | 38.72% | 3 |
| yolov7_paper | H10 | 3 | b066 | b044 | 17.29% | 0.00% | 18.13% | 3 |
| yolov7_paper | H8 | 3 | b044 | b066 | 57.51% | 57.46% | 57.71% | 0 |
