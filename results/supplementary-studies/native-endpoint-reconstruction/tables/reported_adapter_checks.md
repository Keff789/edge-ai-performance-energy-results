| Case | P2 / s | Completed / s | Checks |
| --- | --- | --- | --- |
| YOLOv7 Hailo-8/TRT b066 | 96 | 96 | 32 |
| YOLO26s Hailo-8/TRT b038 | 153 | 153 | 32 |
| YOLO11l full ORT replay | NA | NA | 16 |
| Hailo-10H YOLO26s producer | NA | 35 | 300 |
| DEEPX YOLO26s producer | NA | 40 | 300 |

Reported manuscript summaries. YOLOv7 and YOLO26s validate 32/32 pipeline images, YOLO11l validates 16/16 ORT replay images without accelerator timing, and the last two rows count 300 producer work units. Producer work units are not complete detector tasks. Source endpoint and validation status remain in CSV.
