# MobileNet-V3-L quality recovery

Top1 on the same 5,000 images. Split b027 uses the corresponding accelerator prefix and TensorRT suffix; this example does not imply general recovery for every cut.

| Setup | CPU (%) | Accelerator Full (%) | Split b027 (%) | Recovered (pp) |
| --- | --- | --- | --- | --- |
| H8 | 73.70 | 60.62 | 71.58 | 10.96 |
| H10 | 73.70 | 59.42 | 72.22 | 12.80 |
| DeepX | 73.70 | 71.72 | 72.22 | 0.50 |
