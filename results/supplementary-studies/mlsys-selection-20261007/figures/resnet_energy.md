# ResNet-50 / H8

19 splits and two distinct Full references; the CSV retains all observed repeat minima/maxima.

| Case | Backend | Own-window tasks/s | Full-system mJ/task | Selected by |
| --- | --- | --- | --- | --- |
| b002 | hailo8_to_trt | 540 | 55.6 | measured_generic_completion |
| b009 | hailo8_to_trt | 409 | 68.6 | NA |
| b016 | hailo8_to_trt | 400 | 68.4 | NA |
| b023 | hailo8_to_trt | 403 | 66.9 | NA |
| b031 | hailo8_to_trt | 627 | 47.7 | NA |
| b038 | hailo8_to_trt | 622 | 47.1 | NA |
| b045 | hailo8_to_trt | 561 | 48.7 | NA |
| b052 | hailo8_to_trt | 547 | 48.6 | onnx_real_boundary_hardware_aware |
| b060 | hailo8_to_trt | 616 | 42.3 | weighted_score;cycle_time_no_handover;stored_predicted_stream_fps |
| b067 | hailo8_to_trt | 491 | 47.5 | NA |
| b068 | hailo8_to_trt | 491 | 47.2 | NA |
| b074 | hailo8_to_trt | 459 | 48.4 | NA |
| b081 | hailo8_to_trt | 410 | 51.0 | NA |
| b088 | hailo8_to_trt | 380 | 52.7 | NA |
| b095 | hailo8_to_trt | 348 | 55.3 | NA |
| b103 | hailo8_to_trt | 325 | 54.0 | NA |
| b104 | hailo8_to_trt | 326 | 53.9 | NA |
| b110 | hailo8_to_trt | 285 | 58.3 | NA |
| b119 | hailo8_to_trt | 139 | 115.3 | cut_bytes_only |
| full | native_full_hailo8 | 118 | 131.4 | NA |
| full | native_full_tensorrt | 507 | 56.3 | NA |
